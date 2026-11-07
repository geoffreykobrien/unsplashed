"""Unsplashed: save fresh Unsplash photos to a local folder on a schedule.

One config entry per Unsplash access key ("account"); each feed is a config
subentry under it, so the key is entered once for any number of feeds.
"""

from __future__ import annotations

import logging
from types import MappingProxyType

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import ACCOUNT_TITLE, CONF_ACCESS_KEY, CONF_LEGACY_ID, DOMAIN, SUBENTRY_FEED
from .coordinator import UnsplashConfigEntry, UnsplashCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.IMAGE, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: UnsplashConfigEntry) -> bool:
    """Set up every feed under this Unsplash account."""
    coordinators: dict[str, UnsplashCoordinator] = {}
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_FEED:
            continue
        coordinator = UnsplashCoordinator(hass, entry, subentry)
        await coordinator.async_load()
        await coordinator.async_config_entry_first_refresh()
        coordinators[subentry_id] = coordinator
    entry.runtime_data = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Adding, changing or removing a feed updates the entry; reload to apply.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UnsplashConfigEntry) -> bool:
    """Unload the account. Saved photos stay on disk."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: UnsplashConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: UnsplashConfigEntry) -> bool:
    """Version 1 (one feed per entry) -> 2 (account entry with feed subentries).

    The old feed becomes a subentry that keeps the old entry_id as its ID for
    unique IDs, the device and the storage file, so entity IDs, history,
    dashboards and automations are untouched.
    """
    if entry.version > 2:
        return False
    if entry.version == 2:
        return True

    feed_settings = {**entry.options, CONF_LEGACY_ID: entry.entry_id}
    title = entry.title.removeprefix("Unsplashed:").strip() or "Feed"
    subentry = ConfigSubentry(
        data=MappingProxyType(feed_settings),
        subentry_type=SUBENTRY_FEED,
        title=title,
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(entry, subentry)

    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.config_subentry_id is None:
            ent_reg.async_update_entity(
                ent.entity_id, config_subentry_id=subentry.subentry_id
            )

    dev_reg = dr.async_get(hass)
    if device := dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)}):
        dev_reg.async_update_device(
            device.id,
            add_config_entry_id=entry.entry_id,
            add_config_subentry_id=subentry.subentry_id,
        )
        dev_reg.async_update_device(
            device.id,
            remove_config_entry_id=entry.entry_id,
            remove_config_subentry_id=None,
        )

    hass.config_entries.async_update_entry(
        entry,
        title=ACCOUNT_TITLE,
        data={CONF_ACCESS_KEY: entry.data[CONF_ACCESS_KEY]},
        options={},
        version=2,
    )
    _LOGGER.info("Moved Unsplashed feed '%s' under the Unsplash account entry", title)
    return True
