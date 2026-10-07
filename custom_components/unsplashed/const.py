"""Constants for Unsplashed."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "unsplashed"

CONF_ACCESS_KEY: Final = "access_key"
CONF_FOLDER: Final = "folder"
CONF_WIDTH: Final = "width"
CONF_HEIGHT: Final = "height"
CONF_QUERY: Final = "query"
CONF_TOPICS: Final = "topics"
CONF_COLLECTIONS: Final = "collections"
CONF_COUNT: Final = "count"
CONF_INTERVAL_HOURS: Final = "interval_hours"
CONF_KEEP_DAYS: Final = "keep_days"
CONF_STRICT_FILTER: Final = "strict_content_filter"

DEFAULT_FOLDER: Final = "/media/wallpapers"
DEFAULT_WIDTH: Final = 1080
DEFAULT_HEIGHT: Final = 1920
DEFAULT_COUNT: Final = 3
DEFAULT_INTERVAL_HOURS: Final = 24
DEFAULT_KEEP_DAYS: Final = 30

MAX_COUNT: Final = 30
FILE_PREFIX: Final = "unsplash_"

EVENT_NEW_IMAGE: Final = f"{DOMAIN}_new_image"
