"""Sensors describing the feed."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import UnsplashConfigEntry, UnsplashCoordinator, WallpaperState
from .entity import UnsplashEntity


@dataclass(frozen=True, kw_only=True)
class UnsplashSensorDescription(SensorEntityDescription):
    value_fn: Callable[[WallpaperState], Any]
    attrs_fn: Callable[[WallpaperState], dict[str, Any]] | None = None


def _latest_attrs(state: WallpaperState) -> dict[str, Any]:
    latest = state.latest or {}
    return {
        k: latest.get(k)
        for k in (
            "description",
            "photographer",
            "photographer_url",
            "photo_url",
            "location",
            "color",
            "path",
        )
    }


SENSORS: tuple[UnsplashSensorDescription, ...] = (
    UnsplashSensorDescription(
        key="latest_credit",
        icon="mdi:camera-account",
        value_fn=lambda s: (s.latest or {}).get("credit"),
        attrs_fn=_latest_attrs,
    ),
    UnsplashSensorDescription(
        key="image_count",
        icon="mdi:folder-image",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.file_count,
    ),
    UnsplashSensorDescription(
        key="last_fetch",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s: s.last_fetch,
        attrs_fn=lambda s: {"new_images": s.last_saved_count},
    ),
    UnsplashSensorDescription(
        key="rate_limit_remaining",
        icon="mdi:speedometer",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.rate_limit_remaining,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnsplashConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(UnsplashSensor(entry.runtime_data, d) for d in SENSORS)


class UnsplashSensor(UnsplashEntity, SensorEntity):
    entity_description: UnsplashSensorDescription

    def __init__(
        self, coordinator: UnsplashCoordinator, description: UnsplashSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if fn := self.entity_description.attrs_fn:
            return fn(self.coordinator.data)
        return None
