"""Config and options flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    assert result["title"] == "Unsplashed: maine, coast"
    assert result["data"] == {"access_key": "good-key"}
    assert result["options"]["count"] == 3
    assert result["options"]["color"] == "any"
    assert result["options"]["include_illustrations"] is False
    assert (tmp_path / "wallpapers").is_dir()


async def test_topics_stored_as_csv(hass, aioclient_mock, tmp_path) -> None:
    result = await _to_feed_step(hass, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _feed(tmp_path, query="", topics=["nature", "my-custom-topic"])
    )
    assert result["options"]["topics"] == "nature, my-custom-topic"
    assert result["title"] == "Unsplashed: nature, my-custom-topic"


async def test_photographers_title_and_cleanup(hass, aioclient_mock, tmp_path) -> None:
    result = await _to_feed_step(hass, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _feed(tmp_path, query="", usernames="@chrislawton, nasa")
    )
    assert result["options"]["usernames"] == "chrislawton, nasa"
    assert result["title"] == "Unsplashed: @chrislawton, @nasa"


async def test_color_title(hass, aioclient_mock, tmp_path) -> None:
    result = await _to_feed_step(hass, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _feed(tmp_path, color="blue")
    )
    assert result["title"] == "Unsplashed: maine, coast (blue)"


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


async def test_options_flow_loads_topics_and_keeps_custom(hass, aioclient_mock, tmp_path) -> None:
    aioclient_mock.get(f"{API}/topics", json=TOPICS)
    aioclient_mock.get(f"{API}/photos/random", json=[])
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Unsplashed: old",
        data={"access_key": "k"},
        options={**_feed(tmp_path, query="", topics="nature, old-topic", keep_days=0)},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert _topic_options(result) == ["nature", "wallpapers", "old-topic"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _feed(tmp_path, query="", topics=["wallpapers"], include_illustrations=True)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["topics"] == "wallpapers"
    assert entry.options["include_illustrations"] is True


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
