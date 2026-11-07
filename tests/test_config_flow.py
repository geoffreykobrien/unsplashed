"""Config and options flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER

from custom_components.unsplashed.const import DOMAIN

API = "https://api.unsplash.com"
TOPICS = [
    {"id": "t1", "slug": "nature", "title": "Nature"},
    {"id": "t2", "slug": "wallpapers", "title": "Wallpapers"},
]


def _feed(tmp_path, **overrides):
    data = {
        "query": "maine, coast",
        "topics": [],
        "collections": "",
        "usernames": "",
        "color": "any",
        "count": 3,
        "interval_hours": 24,
        "width": 1080,
        "height": 1920,
        "folder": str(tmp_path / "wallpapers"),
        "keep_days": 30,
        "strict_content_filter": False,
        "include_illustrations": False,
    }
    data.update(overrides)
    return data


async def _to_feed_step(hass, aioclient_mock):
    aioclient_mock.get(f"{API}/topics", json=TOPICS)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"access_key": " good-key "}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "feed"
    return result


def _topic_options(result) -> list[str]:
    schema = result["data_schema"].schema
    key = next(k for k in schema if str(k) == "topics")
    return [o["value"] for o in schema[key].config["options"]]


async def test_user_flow_creates_entry(hass: HomeAssistant, aioclient_mock, tmp_path) -> None:
    result = await _to_feed_step(hass, aioclient_mock)
    assert _topic_options(result) == ["nature", "wallpapers"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _feed(tmp_path)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Unsplash"
    assert result["data"] == {"access_key": "good-key"}
    entry = result["result"]
    (feed,) = entry.subentries.values()
    assert feed.subentry_type == "feed"
    assert feed.title == "maine, coast"
    assert feed.data["count"] == 3
    assert feed.data["color"] == "any"
    assert feed.data["include_illustrations"] is False
    assert (tmp_path / "wallpapers").is_dir()


async def test_topics_stored_as_csv(hass, aioclient_mock, tmp_path) -> None:
    result = await _to_feed_step(hass, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _feed(tmp_path, query="", topics=["nature", "my-custom-topic"])
    )
    (feed,) = result["result"].subentries.values()
    assert feed.data["topics"] == "nature, my-custom-topic"
    assert feed.title == "nature, my-custom-topic"


async def test_photographers_title_and_cleanup(hass, aioclient_mock, tmp_path) -> None:
    result = await _to_feed_step(hass, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _feed(tmp_path, query="", usernames="@chrislawton, nasa")
    )
    (feed,) = result["result"].subentries.values()
    assert feed.data["usernames"] == "chrislawton, nasa"
    assert feed.title == "@chrislawton, @nasa"


async def test_color_title(hass, aioclient_mock, tmp_path) -> None:
    result = await _to_feed_step(hass, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _feed(tmp_path, color="blue")
    )
    (feed,) = result["result"].subentries.values()
    assert feed.title == "maine, coast (blue)"


async def test_bad_key(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(f"{API}/topics", status=401)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"access_key": "bad"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_filter_conflicts(hass, aioclient_mock, tmp_path) -> None:
    result = await _to_feed_step(hass, aioclient_mock)
    flow_id = result["flow_id"]
    cases = [
        (_feed(tmp_path, topics=["nature"]), {"base": "query_and_topics"}),
        (_feed(tmp_path, usernames="nasa"), {"base": "usernames_exclusive"}),
        (_feed(tmp_path, query="", topics=["nature"], color="blue"), {"base": "color_and_topics"}),
        (_feed(tmp_path, query="", usernames=",".join(f"u{i}" for i in range(11))), {"usernames": "too_many_usernames"}),
        (_feed(tmp_path, folder="wallpapers"), {"folder": "folder_not_absolute"}),
    ]
    for data, errors in cases:
        result = await hass.config_entries.flow.async_configure(flow_id, data)
        assert result["errors"] == errors, data


def _account(tmp_path, **feed):
    return MockConfigEntry(
        domain=DOMAIN,
        title="Unsplash",
        version=2,
        data={"access_key": "k"},
        subentries_data=[
            {
                "data": _feed(tmp_path, **feed),
                "subentry_type": "feed",
                "title": "old",
                "unique_id": None,
            }
        ],
    )


async def test_add_feed_reuses_key(hass, aioclient_mock, tmp_path) -> None:
    aioclient_mock.get(f"{API}/topics", json=TOPICS)
    aioclient_mock.get(f"{API}/photos/random", json=[])
    entry = _account(tmp_path, keep_days=0)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert "access_key" not in [str(k) for k in result["data_schema"].schema]
    assert _topic_options(result) == ["nature", "wallpapers"]

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        _feed(tmp_path, query="", topics=["wallpapers"], width=1920, height=1080,
              folder=str(tmp_path / "tv")),
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    titles = sorted(s.title for s in entry.subentries.values())
    assert titles == ["old", "wallpapers"]
    await hass.async_block_till_done()
    # The account reloaded and now runs both feeds, each with its own device.
    assert len(entry.runtime_data) == 2
    assert hass.states.get("button.unsplashed_wallpapers_fetch_now") is not None
    assert hass.states.get("button.unsplashed_old_fetch_now") is not None
    # The topic list was fetched with the account's saved key.
    topic_call = next(c for c in aioclient_mock.mock_calls if "/topics" in str(c[1]))
    assert topic_call[3]["Authorization"] == "Client-ID k"


async def test_reconfigure_feed_keeps_custom_topic_and_legacy_id(hass, aioclient_mock, tmp_path) -> None:
    aioclient_mock.get(f"{API}/topics", json=TOPICS)
    aioclient_mock.get(f"{API}/photos/random", json=[])
    entry = _account(tmp_path, query="", topics="nature, old-topic", keep_days=0, legacy_id="OLD")
    entry.add_to_hass(hass)
    (feed,) = entry.subentries.values()

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": feed.subentry_id},
    )
    assert result["step_id"] == "reconfigure"
    assert _topic_options(result) == ["nature", "wallpapers", "old-topic"]
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], _feed(tmp_path, query="", topics=["wallpapers"], include_illustrations=True)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    feed = entry.subentries[feed.subentry_id]
    assert feed.data["topics"] == "wallpapers"
    assert feed.data["include_illustrations"] is True
    assert feed.data["legacy_id"] == "OLD"
    assert feed.title == "wallpapers"


async def test_same_key_aborts(hass, aioclient_mock, tmp_path) -> None:
    import hashlib

    entry = _account(tmp_path)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, unique_id=hashlib.sha256(b"k").hexdigest()[:16]
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"access_key": "k"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_account_key(hass, aioclient_mock, tmp_path) -> None:
    aioclient_mock.get(f"{API}/topics", json=[])
    aioclient_mock.get(f"{API}/photos/random", json=[])
    entry = _account(tmp_path, keep_days=0)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"access_key": "new-key"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["access_key"] == "new-key"


async def test_topic_list_failure_falls_back(hass, aioclient_mock) -> None:
    """If the topic list can't load, the picker still accepts typed slugs."""
    aioclient_mock.get(f"{API}/topics", params={"per_page": "1"}, json=[])
    aioclient_mock.get(
        f"{API}/topics", params={"per_page": "30", "order_by": "featured"}, status=500
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"access_key": "k"}
    )
    assert result["step_id"] == "feed"
    assert _topic_options(result) == []
