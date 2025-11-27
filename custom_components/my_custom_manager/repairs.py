"""Repairs platform for HACS."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow

from custom_components.my_custom_manager.services import handle_service_custom_download

from .const import (
    REPO_KEY_HOMEPAGE,
    REPO_KEY_RELEASE_FILE,
    SERVICE_KEY_INSTALLED_VERSION,
)
from .domain_data import DomainData

if TYPE_CHECKING:
    from homeassistant import data_entry_flow
    from homeassistant.core import HomeAssistant


class MyCustomManagerFixFlow(RepairsFlow):
    """Handler for an restart required issue fixing flow."""

    def __init__(self, issue_id: str) -> None:
        """Init the flow."""
        self.issue_id = issue_id

    async def async_step_init(
        self, _user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of a fix flow."""
        if self.issue_id.split("_")[1] == "done":
            return await self.async_step_confirm_restart()
        return await self.async_step_retry()

    async def async_step_confirm_restart(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step of a fix flow."""
        if user_input is not None:
            await self.hass.services.async_call("homeassistant", "restart")
            return self.async_create_entry(title="", data={})

        domain_data = DomainData.get(self.hass)
        issue_data = domain_data.repairs["_".join(self.issue_id.split("_")[2:])]

        return self.async_show_form(
            step_id="confirm_restart",
            data_schema=vol.Schema({}),
            description_placeholders={
                "component": issue_data["component"],
                "component_name": issue_data["component_desc"],
                "installed_version": issue_data["installed_version"],
            },
        )

    async def async_step_retry(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step of a fix flow."""
        domain_data = DomainData.get(self.hass)
        issue_data = domain_data.repairs["_".join(self.issue_id.split("_")[2:])]
        version_desc = issue_data["version_desc"]
        more_info = (
            version_desc.get(REPO_KEY_HOMEPAGE) or version_desc[REPO_KEY_RELEASE_FILE]
        )

        if user_input is not None:
            config_data = self.hass.config_entries.async_get_entry(
                issue_data["config_id"]
            )
            if not config_data:
                return self.async_abort(
                    reason="invalid_config_entry",
                    description_placeholders={
                        "component": issue_data["component"],
                        "desired_version": issue_data["desired_version"],
                        "config_id": issue_data["config_id"],
                    },
                )

            version = await handle_service_custom_download(
                self.hass,
                config_data,
                issue_data["component"],
                issue_data["desired_version"],
                generate_issue=False,
            )

            installed_version = version[SERVICE_KEY_INSTALLED_VERSION]
            if (
                installed_version is not None
                and installed_version != issue_data["desired_version"]
            ):
                return self.async_abort(
                    reason="install_error",
                    description_placeholders={
                        "component": issue_data["component"],
                        "release": more_info,
                    },
                )

            return await self.async_step_confirm_restart(user_input=None)

        return self.async_show_form(
            step_id="retry",
            data_schema=vol.Schema({}),
            description_placeholders={
                "component": issue_data["component"],
                "component_name": issue_data["component_desc"],
                "installed_version": issue_data["installed_version"],
                "desired_version": issue_data["desired_version"],
                "release": more_info,
            },
        )


async def async_create_fix_flow(
    _hass: HomeAssistant,
    issue_id: str,
    _data: dict[str, str | int | float | None] | None = None,
    *_args: Any,
    **_kwargs: Any,
) -> None | RepairsFlow:
    """Create flow."""
    if issue_id.startswith("install_"):
        return MyCustomManagerFixFlow(issue_id)
    return None
