"""Unsplashed: save fresh Unsplash photos to a local folder on a schedule."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import UnsplashConfigEntry, UnsplashCoordinator

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.IMAGE, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: UnsplashConfigEntry) -> bool:
    """Set up one Unsplash feed."""
    coordinator = UnsplashCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UnsplashConfigEntry) -> bool:
    """Unload a feed. Saved photos stay on disk."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: UnsplashConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
