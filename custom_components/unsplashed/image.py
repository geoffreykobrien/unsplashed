"""Image entity showing the newest saved photo."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import UnsplashConfigEntry, UnsplashCoordinator
from .entity import UnsplashEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnsplashConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LatestImage(hass, entry.runtime_data)])


class LatestImage(UnsplashEntity, ImageEntity):
    """Serves the newest saved file straight from disk."""

    _attr_content_type = "image/jpeg"

    def __init__(self, hass: HomeAssistant, coordinator: UnsplashCoordinator) -> None:
        UnsplashEntity.__init__(self, coordinator, "latest")
        ImageEntity.__init__(self, hass)
        self._path: str | None = None
        self._sync()

    def _sync(self) -> None:
        path = self.coordinator.data.latest_path if self.coordinator.data else None
        if path != self._path:
            self._path = path
            self._cached_image = None
            self._attr_image_last_updated = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sync()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        if not self._path:
            return None
        path = Path(self._path)
        try:
            return await self.hass.async_add_executor_job(path.read_bytes)
        except OSError:
            return None
