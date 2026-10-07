"""Button to fetch a new batch immediately."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import UnsplashConfigEntry
from .entity import UnsplashEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnsplashConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FetchNowButton(entry.runtime_data, "fetch_now")])


class FetchNowButton(UnsplashEntity, ButtonEntity):
    """Fetch a new batch of photos now. Uses 1 + count API requests."""

    _attr_icon = "mdi:image-refresh"

    async def async_press(self) -> None:
        await self.coordinator.async_fetch_now()
