"""
Custom integration for manage personal customs integration.

For more details about this integration, please refer to
https://git.villavasco.ovh/home-assistant/my-custom-manager/
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import CONF_BASE_URL, DOMAIN, LOGGER, PLATFORMS
from .domain_data import DomainData
from .entry_data import RuntimeEntryData
from .helpers import (
    KEY_CUSTOMS,
    async_download_and_install,
    async_fetch_repository_data,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall

SERVICE_DOWNLOAD_CUSTOM = "download_custom"
SERVICE_DOWNLOAD_LIST = "download_list"

SERVICE_DOWNLOAD_CUSTOM_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry"): cv.string,
        vol.Required("component"): cv.string,
        vol.Optional("version"): cv.string,
    }
)

SERVICE_DOWNLOAD_LIST_SCHEMA = vol.Schema(
    {vol.Required("config_entry"): cv.string},
)


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Register the component integration services."""

    async def handle_custom_list(call: ServiceCall) -> None:
        """Download the repository customs list."""
        config_data = hass.config_entries.async_get_entry(call.data["config_entry"])
        if not config_data:
            msg = "Invalid config data"
            raise ValueError(msg)

        try:
            repo_data = await async_fetch_repository_data(
                hass, config_data.data[CONF_BASE_URL]
            )
        except (ConnectionError, ValueError) as err:
            msg = f"Error in the '{config_data.title}' data fetch"
            raise ValueError(msg) from err

        return repo_data[KEY_CUSTOMS]

    async def handle_custom_download(call: ServiceCall) -> None:
        """Manage the custom version download."""
        custom_integration = call.data["component"]
        custom_version = call.data.get("version", None)
        config_data = hass.config_entries.async_get_entry(call.data["config_entry"])
        if not config_data:
            msg = "Invalid config data"
            raise ValueError(msg)

        try:
            await async_download_and_install(
                hass,
                config_data.data[CONF_BASE_URL],
                custom_integration,
                custom_version,
            )
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_DOWNLOAD_LIST,
        handle_custom_list,
        schema=SERVICE_DOWNLOAD_LIST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DOWNLOAD_CUSTOM,
        handle_custom_download,
        schema=SERVICE_DOWNLOAD_CUSTOM_SCHEMA,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up my custom update manager from config entry."""
    base_url = entry.data[CONF_BASE_URL]
    entry_runtime_data = RuntimeEntryData(entry_id=entry.entry_id)

    LOGGER.debug("Check repository descriptions for: %s", entry.title)

    try:
        repo_desc = await async_fetch_repository_data(hass, base_url)
    except (ConnectionError, ValueError) as err:
        msg = f"Error in the '{entry.title}' data fetch"
        raise ConfigEntryNotReady(msg) from err
    entry_runtime_data.customs_list = list(repo_desc.get(KEY_CUSTOMS, {}).keys())

    domain_data = DomainData.get(hass)
    domain_data.set_entry_data(entry, entry_runtime_data)

    entry_runtime_data.update_unlistener = entry.add_update_listener(update_listener)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update when config_entry options update."""
    LOGGER.debug("Config entry was updated, rerunning setup")
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove integration from Home Assistant."""
    LOGGER.info("Unload config entry")

    domain_data = DomainData.get(hass)
    entry_data = domain_data.pop_entry_data(entry)

    if entry_data.update_unlistener is not None:
        entry_data.update_unlistener()
    entry_data.update_unlistener = None

    if domain_data.is_empty_entry_data:
        hass.services.async_remove(DOMAIN, SERVICE_DOWNLOAD_CUSTOM)
        hass.services.async_remove(DOMAIN, SERVICE_DOWNLOAD_LIST)

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
