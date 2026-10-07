"""Config and options flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.unsplashed.const import DOMAIN

API = "https://api.unsplash.com"


def _input(tmp_path, **overrides):
    data = {
        "access_key": "good-key",
        "query": "maine, coast",
        "topics": "",
        "collections": "",
        "count": 3,
        "interval_hours": 24,
        "width": 1080,
        "height": 1920,
        "folder": str(tmp_path / "wallpapers"),
        "keep_days": 30,
        "strict_content_filter": False,
    }
    data.update(overrides)
    return data


async def test_user_flow_creates_entry(
    hass: HomeAssistant, aioclient_mock, tmp_path
) -> None:
    aioclient_mock.get(f"{API}/topics", json=[])
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _input(tmp_path)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Unsplashed: maine, coast"
    assert result["data"] == {"access_key": "good-key"}
    assert result["options"]["count"] == 3
    assert (tmp_path / "wallpapers").is_dir()


async def test_bad_key(hass: HomeAssistant, aioclient_mock, tmp_path) -> None:
    aioclient_mock.get(f"{API}/topics", status=401)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _input(tmp_path)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_query_and_topics_rejected(hass: HomeAssistant, tmp_path) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _input(tmp_path, topics="nature")
    )
    assert result["errors"] == {"base": "query_and_topics"}


async def test_relative_folder_rejected(hass: HomeAssistant, tmp_path) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _input(tmp_path, folder="wallpapers")
    )
    assert result["errors"] == {"folder": "folder_not_absolute"}
