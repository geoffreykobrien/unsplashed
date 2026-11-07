"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnsplashCoordinator


def feed_device_name(title: str) -> str:
    return f"Unsplashed: {title}"


class UnsplashEntity(CoordinatorEntity[UnsplashCoordinator]):
    """Groups all of a feed's entities under one service device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: UnsplashCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.feed_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.feed_id)},
            name=feed_device_name(coordinator.subentry.title),
            manufacturer="Unsplash",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://unsplash.com/oauth/applications",
        )
