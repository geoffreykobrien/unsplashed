"""Minimal async client for the parts of the Unsplash API this integration uses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import aiohttp

API_BASE = "https://api.unsplash.com"
TIMEOUT = aiohttp.ClientTimeout(total=60)


class UnsplashError(Exception):
    """Generic failure talking to Unsplash."""


class InvalidAuth(UnsplashError):
    """The access key was rejected."""


class RateLimited(UnsplashError):
    """The hourly request quota is used up."""


class NoResults(UnsplashError):
    """No photos matched the filters."""


@dataclass(slots=True)
class Photo:
    """One Unsplash photo, reduced to what we store and expose."""

    id: str
    url: str
    description: str | None
    photographer: str
    photographer_url: str | None
    photo_url: str | None
    location: str | None
    color: str | None
    track_url: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def credit(self) -> str:
        return f"Photo by {self.photographer} on Unsplash"

    @property
    def is_illustration(self) -> bool:
        """Unsplash has mixed illustrations into photo results since January 2025."""
        return str(self.raw.get("asset_type") or "").lower() == "illustration"

    @property
    def is_premium(self) -> bool:
        """Unsplash+ images need a paid license; never save those."""
        return bool(self.raw.get("premium") or self.raw.get("plus"))


def orientation_for(width: int, height: int) -> str:
    """Map a target size to Unsplash's orientation filter."""
    if height > width:
        return "portrait"
    if width > height:
        return "landscape"
    return "squarish"


def sized_url(raw_url: str, width: int, height: int) -> str:
    """Build an imgix URL cropped to exactly width x height.

    The raw URL already carries the `ixid` parameter Unsplash requires, so we
    append rather than rebuild the query string.
    """
    sep = "&" if "?" in raw_url else "?"
    params = {
        "w": width,
        "h": height,
        "fit": "crop",
        "crop": "entropy",
        "fm": "jpg",
        "q": 85,
    }
    return f"{raw_url}{sep}{urlencode(params)}"


def parse_photo(data: dict[str, Any], width: int, height: int) -> Photo | None:
    """Turn one API photo object into a Photo, or None if it is unusable."""
    photo_id = data.get("id")
    raw = (data.get("urls") or {}).get("raw")
    if not photo_id or not raw:
        return None
    user = data.get("user") or {}
    links = data.get("links") or {}
    return Photo(
        id=photo_id,
        url=sized_url(raw, width, height),
        description=data.get("description") or data.get("alt_description"),
        photographer=user.get("name") or user.get("username") or "Unknown",
        photographer_url=(user.get("links") or {}).get("html"),
        photo_url=links.get("html"),
        location=(data.get("location") or {}).get("name"),
        color=data.get("color"),
        track_url=links.get("download_location"),
        raw=data,
    )


class UnsplashClient:
    """Thin wrapper holding the session and access key."""

    def __init__(self, session: aiohttp.ClientSession, access_key: str) -> None:
        self._session = session
        self._key = access_key
        self.rate_limit_remaining: int | None = None

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Client-ID {self._key}", "Accept-Version": "v1"}

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with self._session.get(
                f"{API_BASE}{path}",
                params=params,
                headers=self._headers,
                timeout=TIMEOUT,
            ) as resp:
                remaining = resp.headers.get("X-Ratelimit-Remaining")
                if remaining is not None and remaining.isdigit():
                    self.rate_limit_remaining = int(remaining)
                if resp.status == 401:
                    raise InvalidAuth("Unsplash rejected the access key")
                if resp.status in (403, 429) and remaining == "0":
                    raise RateLimited("Unsplash hourly rate limit reached")
                if resp.status == 404:
                    raise NoResults("No Unsplash photos matched the filters")
                if resp.status != 200:
                    raise UnsplashError(f"Unsplash returned HTTP {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UnsplashError(f"Could not reach Unsplash: {err}") from err

    async def validate(self) -> None:
        """Cheap call that fails with InvalidAuth on a bad key."""
        await self._get_json("/topics", {"per_page": 1})

    async def list_topics(self) -> list[tuple[str, str]]:
        """Return (slug, title) for Unsplash's featured topics (1 request)."""
        data = await self._get_json(
            "/topics", {"per_page": 30, "order_by": "featured"}
        )
        topics: list[tuple[str, str]] = []
        for item in data if isinstance(data, list) else []:
            slug = item.get("slug") or item.get("id")
            if slug:
                topics.append((str(slug), str(item.get("title") or slug)))
        return topics

    async def search_photos(
        self,
        *,
        query: str,
        width: int,
        height: int,
        color: str | None = None,
        collections: str | None = None,
        strict_filter: bool = False,
        page: int = 1,
    ) -> tuple[list[Photo], int]:
        """One page (up to 30) of search results and the total page count (1 request)."""
        params: dict[str, Any] = {
            "query": query,
            "per_page": 30,
            "page": max(1, page),
            "orientation": orientation_for(width, height),
            "content_filter": "high" if strict_filter else "low",
            "order_by": "relevant",
        }
        if color:
            params["color"] = color
        if collections:
            params["collections"] = collections
        data = await self._get_json("/search/photos", params)
        if not isinstance(data, dict):
            return [], 0
        items = data.get("results") or []
        photos = [p for item in items if (p := parse_photo(item, width, height))]
        return photos, int(data.get("total_pages") or 0)

    async def random_photos(
        self,
        *,
        count: int,
        width: int,
        height: int,
        query: str | None = None,
        topics: str | None = None,
        collections: str | None = None,
        username: str | None = None,
        strict_filter: bool = False,
    ) -> list[Photo]:
        """Return up to `count` random photos matching the filters (1 request)."""
        params: dict[str, Any] = {
            "count": max(1, min(count, 30)),
            "orientation": orientation_for(width, height),
            "content_filter": "high" if strict_filter else "low",
        }
        # Unsplash won't combine query with topics/collections; query wins.
        if username:
            params["username"] = username.lstrip("@")
        elif query:
            params["query"] = query
        else:
            if topics:
                params["topics"] = topics
            if collections:
                params["collections"] = collections

        data = await self._get_json("/photos/random", params)
        items = data if isinstance(data, list) else [data]
        return [p for item in items if (p := parse_photo(item, width, height))]

    async def download(self, url: str) -> bytes:
        """Fetch image bytes from the Unsplash CDN (does not count toward the quota)."""
        try:
            async with self._session.get(url, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    raise UnsplashError(f"Image download returned HTTP {resp.status}")
                if not resp.headers.get("Content-Type", "").startswith("image/"):
                    raise UnsplashError("Image download did not return an image")
                return await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UnsplashError(f"Image download failed: {err}") from err

    async def track_download(self, track_url: str) -> None:
        """Tell Unsplash a photo was downloaded, as its API guidelines require."""
        try:
            async with self._session.get(
                track_url, headers=self._headers, timeout=TIMEOUT
            ):
                pass
        except (aiohttp.ClientError, TimeoutError):
            # Best-effort; never fail a fetch because tracking failed.
            pass
