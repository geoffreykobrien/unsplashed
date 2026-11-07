"""Config and options flows for Unsplashed."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import voluptuous as vol
import hashlib

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import InvalidAuth, UnsplashClient, UnsplashError
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
    MAX_COUNT,
    MAX_USERNAMES,
    ACCOUNT_TITLE,
    SUBENTRY_FEED,
)

SETTING_KEYS = (
    CONF_QUERY,
    CONF_TOPICS,
    CONF_COLLECTIONS,
    CONF_USERNAMES,
    CONF_COLOR,
    CONF_COUNT,
    CONF_INTERVAL_HOURS,
    CONF_WIDTH,
    CONF_HEIGHT,
    CONF_FOLDER,
    CONF_KEEP_DAYS,
    CONF_STRICT_FILTER,
    CONF_INCLUDE_ILLUSTRATIONS,
)


def _csv_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _topic_selector(
    topics: list[tuple[str, str]], current: list[str]
) -> SelectSelector:
    """Multi-select of Unsplash's featured topics; other slugs can be typed in."""
    options = [SelectOptionDict(value=slug, label=title) for slug, title in topics]
    known = {slug for slug, _ in topics}
    options += [SelectOptionDict(value=c, label=c) for c in current if c not in known]
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            multiple=True,
            custom_value=True,
            mode=SelectSelectorMode.DROPDOWN,
            sort=False,
        )
    )


def _color_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[COLOR_ANY, *COLORS],
            translation_key=CONF_COLOR,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _box(min_: float, max_: float, unit: str | None = None) -> NumberSelector:
    config = NumberSelectorConfig(
        min=min_, max=max_, step=1, mode=NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _settings_schema(
    defaults: Mapping[str, Any], topics: list[tuple[str, str]] | None = None
) -> dict[vol.Marker, Any]:
    """Fields shared by setup and options. Text filters use suggested values
    so a user can clear them back to empty."""

    def text(key: str) -> vol.Optional:
        return vol.Optional(key, description={"suggested_value": defaults.get(key, "")})

    current_topics = _csv_list(defaults.get(CONF_TOPICS))
    return {
        text(CONF_QUERY): TextSelector(),
        vol.Optional(
            CONF_TOPICS, description={"suggested_value": current_topics}
        ): _topic_selector(topics or [], current_topics),
        text(CONF_COLLECTIONS): TextSelector(),
        text(CONF_USERNAMES): TextSelector(),
        vol.Required(
            CONF_COLOR, default=defaults.get(CONF_COLOR) or COLOR_ANY
        ): _color_selector(),
        vol.Required(CONF_COUNT, default=defaults.get(CONF_COUNT, DEFAULT_COUNT)): _box(
            1, MAX_COUNT
        ),
        vol.Required(
            CONF_INTERVAL_HOURS,
            default=defaults.get(CONF_INTERVAL_HOURS, DEFAULT_INTERVAL_HOURS),
        ): _box(1, 168, "h"),
        vol.Required(CONF_WIDTH, default=defaults.get(CONF_WIDTH, DEFAULT_WIDTH)): _box(
            320, 7680, "px"
        ),
        vol.Required(
            CONF_HEIGHT, default=defaults.get(CONF_HEIGHT, DEFAULT_HEIGHT)
        ): _box(320, 7680, "px"),
        vol.Required(
            CONF_FOLDER, default=defaults.get(CONF_FOLDER, DEFAULT_FOLDER)
        ): TextSelector(),
        vol.Required(
            CONF_KEEP_DAYS, default=defaults.get(CONF_KEEP_DAYS, DEFAULT_KEEP_DAYS)
        ): _box(0, 3650, "d"),
        vol.Required(
            CONF_STRICT_FILTER, default=defaults.get(CONF_STRICT_FILTER, False)
        ): BooleanSelector(),
        vol.Required(
            CONF_INCLUDE_ILLUSTRATIONS,
            default=defaults.get(CONF_INCLUDE_ILLUSTRATIONS, False),
        ): BooleanSelector(),
    }


def _normalize(user_input: dict[str, Any]) -> dict[str, Any]:
    """Coerce selector floats to ints and tidy text fields."""
    out = {k: user_input.get(k) for k in SETTING_KEYS}
    for key in (
        CONF_COUNT,
        CONF_INTERVAL_HOURS,
        CONF_WIDTH,
        CONF_HEIGHT,
        CONF_KEEP_DAYS,
    ):
        out[key] = int(out[key])
    for key in (CONF_QUERY, CONF_COLLECTIONS):
        out[key] = (out.get(key) or "").strip()
    out[CONF_TOPICS] = ", ".join(_csv_list(out.get(CONF_TOPICS)))
    out[CONF_USERNAMES] = ", ".join(
        u.lstrip("@") for u in _csv_list(out.get(CONF_USERNAMES)) if u.lstrip("@")
    )
    out[CONF_COLOR] = out.get(CONF_COLOR) or COLOR_ANY
    out[CONF_FOLDER] = str(Path(out[CONF_FOLDER].strip()))
    out[CONF_STRICT_FILTER] = bool(out[CONF_STRICT_FILTER])
    out[CONF_INCLUDE_ILLUSTRATIONS] = bool(out.get(CONF_INCLUDE_ILLUSTRATIONS))
    return out


def _check_folder(folder: str) -> str | None:
    """Return an error key if the folder can't be used. Runs in the executor."""
    path = Path(folder)
    if not path.is_absolute():
        return "folder_not_absolute"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return "folder_not_writable"
    if not os.access(path, os.W_OK):
        return "folder_not_writable"
    return None


async def _validate_settings(
    hass: HomeAssistant, settings: dict[str, Any]
) -> dict[str, str]:
    errors: dict[str, str] = {}
    if err := await hass.async_add_executor_job(_check_folder, settings[CONF_FOLDER]):
        errors[CONF_FOLDER] = err
    color = settings[CONF_COLOR] != COLOR_ANY
    usernames = _csv_list(settings[CONF_USERNAMES])
    if usernames and (
        settings[CONF_QUERY] or settings[CONF_TOPICS] or settings[CONF_COLLECTIONS] or color
    ):
        errors["base"] = "usernames_exclusive"
    elif len(usernames) > MAX_USERNAMES:
        errors[CONF_USERNAMES] = "too_many_usernames"
    elif color and settings[CONF_TOPICS]:
        errors["base"] = "color_and_topics"
    elif settings[CONF_QUERY] and (settings[CONF_TOPICS] or settings[CONF_COLLECTIONS]):
        errors["base"] = "query_and_topics"
    return errors


def _title(settings: Mapping[str, Any]) -> str:
    usernames = _csv_list(settings.get(CONF_USERNAMES))
    label = (
        ", ".join(f"@{u}" for u in usernames)
        or settings.get(CONF_QUERY)
        or settings.get(CONF_TOPICS)
        or settings.get(CONF_COLLECTIONS)
    )
    color = settings.get(CONF_COLOR)
    if color and color != COLOR_ANY:
        shade = COLORS.get(color, color)
        label = f"{label} ({shade})" if label else shade
    return label or "random"


async def _fetch_topics(hass: HomeAssistant, key: str) -> list[tuple[str, str]]:
    """Featured topics for the picker; an empty list just means free-text entry."""
    try:
        return await UnsplashClient(async_get_clientsession(hass), key).list_topics()
    except UnsplashError:
        return []


def _key_id(key: str) -> str:
    """Unique ID for an account without storing the key itself in it."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


async def _check_key(hass: HomeAssistant, key: str) -> str | None:
    client = UnsplashClient(async_get_clientsession(hass), key)
    try:
        await client.validate()
    except InvalidAuth:
        return "invalid_auth"
    except UnsplashError:
        return "cannot_connect"
    return None


_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class UnsplashedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add an Unsplash account (access key) and its first feed."""

    VERSION = 2

    def __init__(self) -> None:
        self._key: str | None = None
        self._topics: list[tuple[str, str]] = []

    @classmethod
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_FEED: FeedSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: the access key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_ACCESS_KEY].strip()
            await self.async_set_unique_id(_key_id(key))
            self._abort_if_unique_id_configured()
            if err := await _check_key(self.hass, key):
                errors["base"] = err
            else:
                self._key = key
                self._topics = await _fetch_topics(self.hass, key)
                return await self.async_step_feed()

        return self.async_show_form(
            step_id="user",
            data_schema=_KEY_SCHEMA,
            errors=errors,
            description_placeholders={
                "apps_url": "https://unsplash.com/oauth/applications"
            },
        )

    async def async_step_feed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: the first feed. More can be added later with Add feed."""
        errors: dict[str, str] = {}
        if user_input is not None:
            settings = _normalize(user_input)
            errors = await _validate_settings(self.hass, settings)
            if not errors:
                return self.async_create_entry(
                    title=ACCOUNT_TITLE,
                    data={CONF_ACCESS_KEY: self._key},
                    subentries=[
                        {
                            "data": settings,
                            "subentry_type": SUBENTRY_FEED,
                            "title": _title(settings),
                            "unique_id": None,
                        }
                    ],
                )
        return self.async_show_form(
            step_id="feed",
            data_schema=vol.Schema(_settings_schema(user_input or {}, self._topics)),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace the access key used by every feed on this account."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_ACCESS_KEY].strip()
            if not (err := await _check_key(self.hass, key)):
                return self.async_update_reload_and_abort(
                    entry, unique_id=_key_id(key), data_updates={CONF_ACCESS_KEY: key}
                )
            errors["base"] = err
        return self.async_show_form(
            step_id="reconfigure", data_schema=_KEY_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_ACCESS_KEY].strip()
            if not (err := await _check_key(self.hass, key)):
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    unique_id=_key_id(key),
                    data_updates={CONF_ACCESS_KEY: key},
                )
            errors["base"] = err
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=_KEY_SCHEMA, errors=errors
        )


class FeedSubentryFlow(ConfigSubentryFlow):
    """Add or change one feed under an Unsplash account."""

    def __init__(self) -> None:
        self._topics: list[tuple[str, str]] | None = None

    async def _load_topics(self) -> list[tuple[str, str]]:
        if self._topics is None:
            self._topics = await _fetch_topics(
                self.hass, self._get_entry().data[CONF_ACCESS_KEY]
            )
        return self._topics

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            settings = _normalize(user_input)
            errors = await _validate_settings(self.hass, settings)
            if not errors:
                return self.async_create_entry(title=_title(settings), data=settings)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                _settings_schema(user_input or {}, await self._load_topics())
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            settings = _normalize(user_input)
            errors = await _validate_settings(self.hass, settings)
            if not errors:
                # Keep internal keys (such as a migrated feed's legacy ID).
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=_title(settings),
                    data={**subentry.data, **settings},
                )
        defaults = user_input or dict(subentry.data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                _settings_schema(defaults, await self._load_topics())
            ),
            errors=errors,
        )
