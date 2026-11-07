"""Fetch, save and prune Unsplash wallpapers on a schedule."""

from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    InvalidAuth,
    NoResults,
    Photo,
    RateLimited,
    UnsplashClient,
    UnsplashError,
)
from .const import (
    CONF_ACCESS_KEY,
    CONF_COLLECTIONS,
    CONF_COLOR,
    CONF_COUNT,
    CONF_FOLDER,
    CONF_HEIGHT,
    CONF_INCLUDE_ILLUSTRATIONS,
    CONF_INTERVAL_HOURS,
    CONF_KEEP_DAYS,
    CONF_LEGACY_ID,
    CONF_QUERY,
    CONF_STRICT_FILTER,
    CONF_TOPICS,
    CONF_USERNAMES,
    CONF_WIDTH,
    COLOR_ANY,
    COLORS,
    DEFAULT_COUNT,
    DEFAULT_FOLDER,
    DEFAULT_HEIGHT,
    DEFAULT_INTERVAL_HOURS,
    DEFAULT_KEEP_DAYS,
    DEFAULT_WIDTH,
    DOMAIN,
    EVENT_NEW_IMAGE,
    FILE_PREFIX,
    MAX_COUNT,
    MAX_USERNAMES,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
# Run a scheduled fetch even if we are a few minutes early, so drift in the
# update timer never pushes a fetch a whole interval later.
EARLY_GRACE = timedelta(minutes=5)

type UnsplashConfigEntry = ConfigEntry[dict[str, "UnsplashCoordinator"]]


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

    def __init__(
        self, hass: HomeAssistant, entry: UnsplashConfigEntry, subentry: ConfigSubentry
    ) -> None:
        self.subentry = subentry
        self.settings: dict[str, Any] = dict(subentry.data)
        # Stable ID for unique IDs, the device and storage.
        self.feed_id: str = self.settings.get(CONF_LEGACY_ID) or subentry.subentry_id
        interval = timedelta(
            hours=float(self.settings.get(CONF_INTERVAL_HOURS, DEFAULT_INTERVAL_HOURS))
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title}",
            update_interval=interval,
        )
        self.interval = interval
        self.client = UnsplashClient(
            async_get_clientsession(hass), entry.data[CONF_ACCESS_KEY]
        )
        self.folder = Path(self.settings.get(CONF_FOLDER, DEFAULT_FOLDER))
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{self.feed_id}"
        )
        self._state = WallpaperState()
        self._force = False
        # Last known number of search result pages, so color-filtered fetches
        # can jump to a random page instead of always taking the top results.
        self._search_pages: int = 0

    async def async_load(self) -> None:
        """Restore the last fetch so a restart doesn't trigger an extra one."""
        stored = await self._store.async_load() or {}
        if last := stored.get("last_fetch"):
            self._state.last_fetch = dt_util.parse_datetime(last)
        self._state.recent = stored.get("recent", [])
        self._search_pages = int(stored.get("search_pages") or 0)
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
        try:
            photos = await self._choose_photos()
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
                EVENT_NEW_IMAGE,
                {
                    "entry_id": self.config_entry.entry_id,
                    "feed_id": self.feed_id,
                    "feed": self.subentry.title,
                    **record,
                },
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
                "search_pages": self._search_pages,
            }
        )
        _LOGGER.debug("Saved %d new Unsplash photo(s) to %s", len(saved), self.folder)

    async def _choose_photos(self) -> list[Photo]:
        """Pick this fetch's photos according to the feed's filters.

        Three modes, in order of precedence:
        - Color: Unsplash only supports a color filter on search, so this uses
          /search/photos (search words, or the color's name when there are
          none) on a random results page.
        - Photographers: /photos/random per username, splitting the count.
        - Everything else: one /photos/random call with query/topics/collections.

        Illustrations (unless allowed) and Unsplash+ images are dropped. Each
        call asks for extra results so the filtering still leaves enough.
        """
        s = self.settings
        width = int(s.get(CONF_WIDTH, DEFAULT_WIDTH))
        height = int(s.get(CONF_HEIGHT, DEFAULT_HEIGHT))
        count = int(s.get(CONF_COUNT, DEFAULT_COUNT))
        strict = bool(s.get(CONF_STRICT_FILTER, False))
        include_ill = bool(s.get(CONF_INCLUDE_ILLUSTRATIONS, False))
        query = _clean(s.get(CONF_QUERY))
        topics = _clean(s.get(CONF_TOPICS))
        collections = _clean(s.get(CONF_COLLECTIONS))
        color = _clean(s.get(CONF_COLOR))
        color = None if color in (None, COLOR_ANY) else color
        usernames = _split(s.get(CONF_USERNAMES))[:MAX_USERNAMES]
        ask = count if include_ill else min(MAX_COUNT, max(count * 2, count + 3))

        candidates: list[Photo]
        if color:
            search_query = query or COLORS.get(color, color)
            page = random.randint(1, min(self._search_pages, 20)) if self._search_pages else 1
            candidates, total = await self.client.search_photos(
                query=search_query, width=width, height=height, color=color,
                collections=collections, strict_filter=strict, page=page,
            )
            if not candidates and page > 1:
                candidates, total = await self.client.search_photos(
                    query=search_query, width=width, height=height, color=color,
                    collections=collections, strict_filter=strict, page=1,
                )
            self._search_pages = total
            random.shuffle(candidates)
        elif usernames:
            random.shuffle(usernames)
            per_user = _split_count(count, len(usernames))
            candidates = []
            for username, n in zip(usernames, per_user, strict=False):
                if n <= 0:
                    continue
                extra = n if include_ill else min(MAX_COUNT, n * 2 + 1)
                try:
                    candidates += await self.client.random_photos(
                        count=extra, width=width, height=height,
                        username=username, strict_filter=strict,
                    )
                except NoResults:
                    _LOGGER.warning(
                        "Unsplash found no photos for photographer '%s' in this orientation",
                        username,
                    )
        else:
            candidates = await self.client.random_photos(
                count=ask, width=width, height=height, query=query,
                topics=topics, collections=collections, strict_filter=strict,
            )

        seen: set[str] = set()
        picked: list[Photo] = []
        for photo in candidates:
            if photo.id in seen or photo.is_premium:
                continue
            if photo.is_illustration and not include_ill:
                continue
            seen.add(photo.id)
            picked.append(photo)
        if usernames and not color:
            # Interleave so one photographer doesn't fill the whole batch.
            picked = _interleave(picked)
        return picked[:count]

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


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _split(value: Any) -> list[str]:
    return [part.strip().lstrip("@") for part in str(value or "").split(",") if part.strip().lstrip("@")]


def _split_count(total: int, buckets: int) -> list[int]:
    """Spread `total` photos across `buckets` photographers as evenly as possible."""
    if buckets <= 0:
        return []
    base, extra = divmod(total, buckets)
    return [base + (1 if i < extra else 0) for i in range(buckets)]


def _interleave(photos: list[Photo]) -> list[Photo]:
    """Round-robin photos by photographer."""
    groups: dict[str, list[Photo]] = {}
    for photo in photos:
        groups.setdefault(photo.photographer, []).append(photo)
    out: list[Photo] = []
    while any(groups.values()):
        for key in list(groups):
            if groups[key]:
                out.append(groups[key].pop(0))
    return out
