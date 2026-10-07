"""Fetch, save and prune Unsplash wallpapers on a schedule."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import InvalidAuth, Photo, RateLimited, UnsplashClient, UnsplashError
from .const import (
    CONF_ACCESS_KEY,
    CONF_COLLECTIONS,
    CONF_COUNT,
    CONF_FOLDER,
    CONF_HEIGHT,
    CONF_INTERVAL_HOURS,
    CONF_KEEP_DAYS,
    CONF_QUERY,
    CONF_STRICT_FILTER,
    CONF_TOPICS,
    CONF_WIDTH,
    DEFAULT_COUNT,
    DEFAULT_FOLDER,
    DEFAULT_HEIGHT,
    DEFAULT_INTERVAL_HOURS,
    DEFAULT_KEEP_DAYS,
    DEFAULT_WIDTH,
    DOMAIN,
    EVENT_NEW_IMAGE,
    FILE_PREFIX,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
# Run a scheduled fetch even if we are a few minutes early, so drift in the
# update timer never pushes a fetch a whole interval later.
EARLY_GRACE = timedelta(minutes=5)

type UnsplashConfigEntry = ConfigEntry[UnsplashCoordinator]


@dataclass(slots=True)
class WallpaperState:
    """What the entities show."""

    latest: dict[str, Any] | None = None
    latest_path: str | None = None
    last_fetch: datetime | None = None
    last_saved_count: int = 0
    file_count: int = 0
    rate_limit_remaining: int | None = None
    recent: list[dict[str, Any]] = field(default_factory=list)


def _photo_record(photo: Photo, path: Path) -> dict[str, Any]:
    return {
        "id": photo.id,
        "path": str(path),
        "description": photo.description,
        "photographer": photo.photographer,
        "photographer_url": photo.photographer_url,
        "photo_url": photo.photo_url,
        "location": photo.location,
        "color": photo.color,
        "credit": photo.credit,
        "saved_at": dt_util.utcnow().isoformat(),
    }


class UnsplashCoordinator(DataUpdateCoordinator[WallpaperState]):
    """Owns the schedule and all file-system work for one config entry."""

    config_entry: UnsplashConfigEntry

    def __init__(self, hass: HomeAssistant, entry: UnsplashConfigEntry) -> None:
        self.settings: dict[str, Any] = {**entry.data, **entry.options}
        interval = timedelta(
            hours=float(self.settings.get(CONF_INTERVAL_HOURS, DEFAULT_INTERVAL_HOURS))
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=interval,
        )
        self.interval = interval
        self.client = UnsplashClient(
            async_get_clientsession(hass), entry.data[CONF_ACCESS_KEY]
        )
        self.folder = Path(self.settings.get(CONF_FOLDER, DEFAULT_FOLDER))
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._state = WallpaperState()
        self._force = False

    async def async_load(self) -> None:
        """Restore the last fetch so a restart doesn't trigger an extra one."""
        stored = await self._store.async_load() or {}
        if last := stored.get("last_fetch"):
            self._state.last_fetch = dt_util.parse_datetime(last)
        self._state.recent = stored.get("recent", [])
        if self._state.recent:
            self._state.latest = self._state.recent[0]
            self._state.latest_path = self._state.latest.get("path")

    async def async_fetch_now(self) -> None:
        """Fetch a fresh batch immediately, ignoring the schedule."""
        self._force = True
        await self.async_refresh()

    def _due(self) -> bool:
        last = self._state.last_fetch
        return last is None or dt_util.utcnow() - last >= self.interval - EARLY_GRACE

    async def _async_update_data(self) -> WallpaperState:
        force, self._force = self._force, False
        if force or self._due():
            await self._fetch_batch()
        await self.hass.async_add_executor_job(self._housekeeping)
        self._state.rate_limit_remaining = self.client.rate_limit_remaining
        # Return a shallow copy so entities see a changed object each update.
        return replace(self._state, recent=list(self._state.recent))

    async def _fetch_batch(self) -> None:
        s = self.settings
        width = int(s.get(CONF_WIDTH, DEFAULT_WIDTH))
        height = int(s.get(CONF_HEIGHT, DEFAULT_HEIGHT))
        try:
            photos = await self.client.random_photos(
                count=int(s.get(CONF_COUNT, DEFAULT_COUNT)),
                width=width,
                height=height,
                query=(s.get(CONF_QUERY) or "").strip() or None,
                topics=(s.get(CONF_TOPICS) or "").strip() or None,
                collections=(s.get(CONF_COLLECTIONS) or "").strip() or None,
                strict_filter=bool(s.get(CONF_STRICT_FILTER, False)),
            )
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RateLimited as err:
            raise UpdateFailed(f"{err}; will retry next interval") from err
        except UnsplashError as err:
            raise UpdateFailed(str(err)) from err

        await self.hass.async_add_executor_job(self.folder.mkdir, 0o755, True, True)

        saved: list[dict[str, Any]] = []
        for photo in photos:
            path = self.folder / f"{FILE_PREFIX}{photo.id}.jpg"
            if await self.hass.async_add_executor_job(path.exists):
                continue
            try:
                content = await self.client.download(photo.url)
            except UnsplashError as err:
                _LOGGER.warning("Skipping photo %s: %s", photo.id, err)
                continue
            await self.hass.async_add_executor_job(_atomic_write, path, content)
            if photo.track_url:
                await self.client.track_download(photo.track_url)
            record = _photo_record(photo, path)
            saved.append(record)
            self.hass.bus.async_fire(
                EVENT_NEW_IMAGE, {"entry_id": self.config_entry.entry_id, **record}
            )

        self._state.last_fetch = dt_util.utcnow()
        self._state.last_saved_count = len(saved)
        if saved:
            self._state.recent = (saved + self._state.recent)[:50]
            self._state.latest = saved[0]
            self._state.latest_path = saved[0]["path"]
        await self._store.async_save(
            {
                "last_fetch": self._state.last_fetch.isoformat(),
                "recent": self._state.recent,
            }
        )
        _LOGGER.debug("Saved %d new Unsplash photo(s) to %s", len(saved), self.folder)

    def _housekeeping(self) -> None:
        """Prune old files and count what's left. Runs in the executor."""
        keep_days = int(self.settings.get(CONF_KEEP_DAYS, DEFAULT_KEEP_DAYS))
        if not self.folder.is_dir():
            self._state.file_count = 0
            return
        cutoff = time.time() - keep_days * 86400
        count = 0
        removed: set[str] = set()
        for path in self.folder.glob(f"{FILE_PREFIX}*.jpg"):
            # Never delete the photo currently shown by the image entity.
            if keep_days > 0 and str(path) != self._state.latest_path:
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                        removed.add(str(path))
                        continue
                except OSError as err:
                    _LOGGER.debug("Could not prune %s: %s", path, err)
            count += 1
        if removed:
            self._state.recent = [
                r for r in self._state.recent if r.get("path") not in removed
            ]
            _LOGGER.debug("Pruned %d old photo(s)", len(removed))
        self._state.file_count = count


def _atomic_write(path: Path, content: bytes) -> None:
    """Write via a temp file so the slideshow never reads a half-written image."""
    tmp = path.with_suffix(".part")
    tmp.write_bytes(content)
    os.replace(tmp, path)
