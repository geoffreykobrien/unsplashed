"""Config and options flows for Unsplashed."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import InvalidAuth, UnsplashClient, UnsplashError
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
    MAX_COUNT,
)

SETTING_KEYS = (
    CONF_QUERY,
    CONF_TOPICS,
    CONF_COLLECTIONS,
    CONF_COUNT,
    CONF_INTERVAL_HOURS,
    CONF_WIDTH,
    CONF_HEIGHT,
    CONF_FOLDER,
    CONF_KEEP_DAYS,
    CONF_STRICT_FILTER,
)


def _box(min_: float, max_: float, unit: str | None = None) -> NumberSelector:
    config = NumberSelectorConfig(
        min=min_, max=max_, step=1, mode=NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _settings_schema(defaults: Mapping[str, Any]) -> dict[vol.Marker, Any]:
    """Fields shared by setup and options. Text filters use suggested values
    so a user can clear them back to empty."""

    def text(key: str) -> vol.Optional:
        return vol.Optional(key, description={"suggested_value": defaults.get(key, "")})

    return {
        text(CONF_QUERY): TextSelector(),
        text(CONF_TOPICS): TextSelector(),
        text(CONF_COLLECTIONS): TextSelector(),
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
    for key in (CONF_QUERY, CONF_TOPICS, CONF_COLLECTIONS):
        out[key] = (out.get(key) or "").strip()
    out[CONF_FOLDER] = str(Path(out[CONF_FOLDER].strip()))
    out[CONF_STRICT_FILTER] = bool(out[CONF_STRICT_FILTER])
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
    if settings[CONF_QUERY] and (settings[CONF_TOPICS] or settings[CONF_COLLECTIONS]):
        errors["base"] = "query_and_topics"
    return errors


def _title(settings: Mapping[str, Any]) -> str:
    label = (
        settings.get(CONF_QUERY)
        or settings.get(CONF_TOPICS)
        or settings.get(CONF_COLLECTIONS)
    )
    return f"Unsplashed: {label}" if label else "Unsplashed: random"


class UnsplashedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up an Unsplash wallpaper feed."""

    VERSION = 1

    async def _check_key(self, key: str) -> str | None:
        client = UnsplashClient(async_get_clientsession(self.hass), key)
        try:
            await client.validate()
        except InvalidAuth:
            return "invalid_auth"
        except UnsplashError:
            return "cannot_connect"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_ACCESS_KEY].strip()
            settings = _normalize(user_input)
            errors = await _validate_settings(self.hass, settings)
            if not errors and (err := await self._check_key(key)):
                errors["base"] = err
            if not errors:
                return self.async_create_entry(
                    title=_title(settings),
                    data={CONF_ACCESS_KEY: key},
                    options=settings,
                )

        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ACCESS_KEY, default=defaults.get(CONF_ACCESS_KEY, "")
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                **_settings_schema(defaults),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "apps_url": "https://unsplash.com/oauth/applications"
            },
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
            if not (err := await self._check_key(key)):
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_ACCESS_KEY: key}
                )
            errors["base"] = err
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return UnsplashedOptionsFlow()


class UnsplashedOptionsFlow(OptionsFlow):
    """Change filters, size, schedule and storage after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            settings = _normalize(user_input)
            errors = await _validate_settings(self.hass, settings)
            if not errors:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=_title(settings)
                )
                return self.async_create_entry(data=settings)

        defaults = user_input or {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(_settings_schema(defaults)),
            errors=errors,
        )
