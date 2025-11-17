"""Adds config flow for my custom manager."""

from __future__ import annotations

from hashlib import sha1
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    CONN_CLASS_CLOUD_POLL,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_BASE_URL,
    CONF_POLL_TIME,
    DEFAULT_POLLING_HOURS,
    DOMAIN,
)
from .helpers import (
    KEY_CUSTOMS,
    KEY_DESCRIPTION,
    KEY_NAME,
    async_fetch_repository_data,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for my custom manager."""

    VERSION = 1
    MINOR_VERSION = 0
    CONNECTION_CLASS = CONN_CLASS_CLOUD_POLL

    _repo_name: str = "My custom repository"
    _data: dict

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry: ConfigEntry) -> OptionsFlow:
        """Link the Options flow to the config flow."""
        return OptionsFlowHandler()

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            try:
                base_url: str = vol.Url()(user_input[CONF_BASE_URL])  # pyright: ignore[reportCallIssue]
                base_url = base_url.rstrip("/")
            except vol.UrlInvalid:
                errors[CONF_BASE_URL] = "invalid_url"

            if errors == {}:
                await self.async_set_unique_id(
                    # sha1 is used only for unique_id generation not security
                    sha1(base_url.encode()).hexdigest(),  # noqa: S324
                    raise_on_progress=False,
                )
                self._abort_if_unique_id_configured(updates={CONF_BASE_URL: base_url})

                repo_desc = None
                try:
                    repo_desc = await async_fetch_repository_data(
                        self.hass, user_input[CONF_BASE_URL]
                    )
                except ConnectionError:
                    errors[CONF_BASE_URL] = "invalid_url"
                except ValueError:
                    errors[CONF_BASE_URL] = "invalid_repository"

                if repo_desc:
                    self._repo_name = repo_desc[KEY_NAME]
                    self._data = user_input
                    return self._show_step_welcome_form(repo_desc)

        return self._show_step_user_flow(errors)

    def _show_step_user_flow(self, errors: dict) -> ConfigFlowResult:
        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_welcome(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Confirm the entry creation."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._repo_name,
                data=self._data,
                options={CONF_POLL_TIME: DEFAULT_POLLING_HOURS},
            )

        return self._show_step_user_flow({})

    def _show_step_welcome_form(self, repo_desc: dict) -> ConfigFlowResult:
        customs_list = ""
        for custom in repo_desc[KEY_CUSTOMS]:
            customs_list += f"- **{custom}**: {repo_desc[KEY_CUSTOMS][custom]}\n"

        return self.async_show_form(
            step_id="welcome",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": repo_desc[KEY_NAME],
                "description": repo_desc[KEY_DESCRIPTION],
                "list": customs_list,
            },
        )


class OptionsFlowHandler(OptionsFlow):
    """Manage some integration options."""

    async def async_step_init(
        self, user_data: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Init options manage steps."""
        actual_polling = self.config_entry.options.get(
            CONF_POLL_TIME, DEFAULT_POLLING_HOURS
        )
        if user_data:
            polling_time = user_data[CONF_POLL_TIME]

            if actual_polling != polling_time:
                new_options = {CONF_POLL_TIME: polling_time}
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=new_options
                )
                return self.async_create_entry(title="", data=new_options)

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_POLL_TIME,
                    default=actual_polling,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=3, max=24, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            description_placeholders={"name": self.config_entry.title},
        )
