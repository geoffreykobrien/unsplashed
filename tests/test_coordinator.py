"""Fetching, saving, scheduling and pruning."""

from __future__ import annotations

import os
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.unsplashed.const import DOMAIN, EVENT_NEW_IMAGE

from .conftest import make_photo

API = "https://api.unsplash.com"
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


def _entry(tmp_path, **options) -> MockConfigEntry:
    opts = {
        "query": "maine",
        "topics": "",
        "collections": "",
        "count": 2,
        "interval_hours": 24,
        "width": 1080,
        "height": 1920,
        "folder": str(tmp_path),
        "keep_days": 30,
        "strict_content_filter": False,
    }
    opts.update(options)
    return MockConfigEntry(
        domain=DOMAIN, title="Unsplashed: maine", data={"access_key": "k"}, options=opts
    )


def _mock_api(aioclient_mock, ids) -> None:
    aioclient_mock.get(f"{API}/photos/random", json=[make_photo(i) for i in ids])
    for i in ids:
        aioclient_mock.get(
            f"https://images.unsplash.com/photo-{i}",
            content=JPEG,
            headers={"Content-Type": "image/jpeg"},
        )
        aioclient_mock.get(f"{API}/photos/{i}/download", json={"url": "x"})


async def test_setup_downloads_and_tracks(
    hass: HomeAssistant, aioclient_mock, tmp_path
) -> None:
    _mock_api(aioclient_mock, ["aaa", "bbb"])
    events = []
    hass.bus.async_listen(EVENT_NEW_IMAGE, events.append)

    entry = _entry(tmp_path)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert (tmp_path / "unsplash_aaa.jpg").read_bytes() == JPEG
    assert (tmp_path / "unsplash_bbb.jpg").exists()
    assert not list(tmp_path.glob("*.part"))
    assert len(events) == 2

    tracked = [str(c[1]) for c in aioclient_mock.mock_calls if "/download" in str(c[1])]
    assert len(tracked) == 2

    # Query string sent to Unsplash.
    random_call = next(
        c for c in aioclient_mock.mock_calls if "/photos/random" in str(c[1])
    )
    assert random_call[1].query["orientation"] == "portrait"
    assert random_call[1].query["query"] == "maine"

    assert hass.states.get("sensor.unsplashed_maine_photos_in_folder").state == "2"
    assert (
        hass.states.get("sensor.unsplashed_maine_latest_photo_credit").state
        == "Photo by Jane Doe on Unsplash"
    )
    assert hass.states.get("image.unsplashed_maine_latest_photo") is not None


async def test_restart_does_not_refetch(
    hass: HomeAssistant, aioclient_mock, tmp_path
) -> None:
    _mock_api(aioclient_mock, ["aaa"])
    entry = _entry(tmp_path, count=1)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    calls_after_first = aioclient_mock.call_count

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == calls_after_first


async def test_fetch_now_button(hass: HomeAssistant, aioclient_mock, tmp_path) -> None:
    _mock_api(aioclient_mock, ["aaa"])
    entry = _entry(tmp_path, count=1)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    aioclient_mock.clear_requests()
    _mock_api(aioclient_mock, ["ccc"])
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.unsplashed_maine_fetch_now"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert (tmp_path / "unsplash_ccc.jpg").exists()


async def test_scheduled_fetch(
    hass: HomeAssistant, aioclient_mock, tmp_path, freezer
) -> None:
    _mock_api(aioclient_mock, ["aaa"])
    entry = _entry(tmp_path, count=1, interval_hours=1)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    aioclient_mock.clear_requests()
    _mock_api(aioclient_mock, ["ddd"])
    freezer.tick(timedelta(hours=1, minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert (tmp_path / "unsplash_ddd.jpg").exists()


async def test_not_due_early(
    hass: HomeAssistant, aioclient_mock, tmp_path, freezer
) -> None:
    """A refresh well before the interval only does housekeeping."""
    _mock_api(aioclient_mock, ["aaa"])
    entry = _entry(tmp_path, count=1, interval_hours=24)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    calls = aioclient_mock.call_count

    freezer.tick(timedelta(hours=2))
    await entry.runtime_data.async_refresh()
    assert aioclient_mock.call_count == calls


async def test_prunes_old_files_only_ours(
    hass: HomeAssistant, aioclient_mock, tmp_path
) -> None:
    old = tmp_path / "unsplash_old.jpg"
    old.write_bytes(JPEG)
    stale = time.time() - 40 * 86400
    os.utime(old, (stale, stale))
    family = tmp_path / "family.jpg"
    family.write_bytes(JPEG)
    os.utime(family, (stale, stale))

    _mock_api(aioclient_mock, ["aaa"])
    entry = _entry(tmp_path, count=1, keep_days=30)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert not old.exists()
    assert family.exists()
    assert (tmp_path / "unsplash_aaa.jpg").exists()


async def test_bad_key_starts_reauth(
    hass: HomeAssistant, aioclient_mock, tmp_path
) -> None:
    aioclient_mock.get(f"{API}/photos/random", status=401)
    entry = _entry(tmp_path)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_rate_limit_retries(
    hass: HomeAssistant, aioclient_mock, tmp_path
) -> None:
    aioclient_mock.get(
        f"{API}/photos/random", status=403, headers={"X-Ratelimit-Remaining": "0"}
    )
    entry = _entry(tmp_path)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


def _mock_downloads(aioclient_mock, ids) -> None:
    for i in ids:
        aioclient_mock.get(
            f"https://images.unsplash.com/photo-{i}",
            content=JPEG,
            headers={"Content-Type": "image/jpeg"},
        )
        aioclient_mock.get(f"{API}/photos/{i}/download", json={"url": "x"})


async def test_illustrations_and_plus_filtered(hass, aioclient_mock, tmp_path) -> None:
    photos = [
        {**make_photo("ill"), "asset_type": "illustration"},
        {**make_photo("plus"), "premium": True},
        {**make_photo("ok1"), "asset_type": "photo"},
        make_photo("ok2"),
    ]
    aioclient_mock.get(f"{API}/photos/random", json=photos)
    _mock_downloads(aioclient_mock, ["ill", "plus", "ok1", "ok2"])
    entry = _entry(tmp_path, count=2)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (tmp_path / "unsplash_ok1.jpg").exists()
    assert (tmp_path / "unsplash_ok2.jpg").exists()
    assert not (tmp_path / "unsplash_ill.jpg").exists()
    assert not (tmp_path / "unsplash_plus.jpg").exists()
    # Asked Unsplash for extra photos to make up for the filtering.
    random_call = next(c for c in aioclient_mock.mock_calls if "/photos/random" in str(c[1]))
    assert int(random_call[1].query["count"]) > 2


async def test_illustrations_allowed(hass, aioclient_mock, tmp_path) -> None:
    aioclient_mock.get(
        f"{API}/photos/random",
        json=[{**make_photo("ill"), "asset_type": "illustration"}],
    )
    _mock_downloads(aioclient_mock, ["ill"])
    entry = _entry(tmp_path, count=1, include_illustrations=True)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (tmp_path / "unsplash_ill.jpg").exists()


async def test_color_uses_search(hass, aioclient_mock, tmp_path) -> None:
    aioclient_mock.get(
        f"{API}/search/photos",
        json={"total": 2, "total_pages": 5, "results": [make_photo("b1"), make_photo("b2")]},
    )
    _mock_downloads(aioclient_mock, ["b1", "b2"])
    entry = _entry(tmp_path, query="", color="blue", count=2)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    call = next(c for c in aioclient_mock.mock_calls if "/search/photos" in str(c[1]))
    q = call[1].query
    assert q["color"] == "blue"
    assert q["query"] == "blue"  # color name used when there are no search words
    assert q["orientation"] == "portrait"
    assert (tmp_path / "unsplash_b1.jpg").exists()
    assert entry.runtime_data._search_pages == 5


async def test_photographers_split_and_interleave(hass, aioclient_mock, tmp_path) -> None:
    def by(user, ids):
        return [make_photo(i, name=user) for i in ids]

    # aioclient_mock matches on params, so each username gets its own response.
    aioclient_mock.get(
        f"{API}/photos/random", params={"username": "alice"}, json=by("Alice", ["a1", "a2", "a3"])
    )
    aioclient_mock.get(
        f"{API}/photos/random", params={"username": "bob"}, json=by("Bob", ["b1", "b2", "b3"])
    )
    _mock_downloads(aioclient_mock, ["a1", "a2", "a3", "b1", "b2", "b3"])
    entry = _entry(tmp_path, query="", usernames="alice, @bob", count=2)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    users = sorted(
        c[1].query["username"] for c in aioclient_mock.mock_calls if "/photos/random" in str(c[1])
    )
    assert users == ["alice", "bob"]
    saved = sorted(p.name for p in tmp_path.glob("unsplash_*.jpg"))
    # One from each photographer.
    assert len(saved) == 2
    assert any(n.startswith("unsplash_a") for n in saved)
    assert any(n.startswith("unsplash_b") for n in saved)
