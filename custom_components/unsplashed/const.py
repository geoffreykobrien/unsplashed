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
CONF_USERNAMES: Final = "usernames"
CONF_COLOR: Final = "color"
CONF_INCLUDE_ILLUSTRATIONS: Final = "include_illustrations"

DEFAULT_FOLDER: Final = "/media/wallpapers"
DEFAULT_WIDTH: Final = 1080
DEFAULT_HEIGHT: Final = 1920
DEFAULT_COUNT: Final = 3
DEFAULT_INTERVAL_HOURS: Final = 24
DEFAULT_KEEP_DAYS: Final = 30

MAX_COUNT: Final = 30
MAX_USERNAMES: Final = 10

COLOR_ANY: Final = "any"
# Unsplash's search color filter values, with the word used as the search
# query when the user picks a color but no search words.
COLORS: Final = {
    "black_and_white": "black and white",
    "black": "black",
    "white": "white",
    "yellow": "yellow",
    "orange": "orange",
    "red": "red",
    "purple": "purple",
    "magenta": "magenta",
    "green": "green",
    "teal": "teal",
    "blue": "blue",
}
FILE_PREFIX: Final = "unsplash_"

EVENT_NEW_IMAGE: Final = f"{DOMAIN}_new_image"

SUBENTRY_FEED: Final = "feed"
# Feeds migrated from 0.2.x keep their old entry_id as the ID used for entity
# unique IDs, the device and the storage file, so nothing changes for them.
CONF_LEGACY_ID: Final = "legacy_id"
ACCOUNT_TITLE: Final = "Unsplash"
