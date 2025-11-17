"""Service handler function."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from awesomeversion import AwesomeVersion
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_BASE_URL,
    SERVICE_KEY_CONFIG_ENTRY,
    SERVICE_KEY_CUSTOM_COMPONENT,
    SERVICE_KEY_INSTALLED_VERSION,
    SERVICE_KEY_ONLY_STABLE,
    SERVICE_KEY_SUPPORTED_VERSIONS,
    SERVICE_KEY_VERSION,
)
from .helpers import (
    REPO_KEY_CUSTOMS,
    REPO_KEY_VERSIONS,
    async_download_and_install,
    async_fetch_custom_description,
    async_fetch_repository_description,
    get_supported_versions,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall

SERVICE_GET_CUSTOM_LIST_SCHEMA = vol.Schema(
    {vol.Required(SERVICE_KEY_CONFIG_ENTRY): cv.string},
)

SERVICE_GET_SUPPORTED_VERSIONS_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_KEY_CONFIG_ENTRY): cv.string,
        vol.Required(SERVICE_KEY_CUSTOM_COMPONENT): cv.string,
        vol.Optional(SERVICE_KEY_ONLY_STABLE): cv.boolean,
    }
)

SERVICE_DOWNLOAD_CUSTOM_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_KEY_CONFIG_ENTRY): cv.string,
        vol.Required(SERVICE_KEY_CUSTOM_COMPONENT): cv.string,
        vol.Optional(SERVICE_KEY_VERSION): cv.string,
    }
)


async def handle_service_customs_list(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, str]:
    """Download the repository customs list."""
    config_entry_id = call.data[SERVICE_KEY_CONFIG_ENTRY]

    config_data = hass.config_entries.async_get_entry(config_entry_id)
    if not config_data:
        msg = f"{config_entry_id} entry does not exist"
        raise HomeAssistantError(msg)

    try:
        repo_data = await async_fetch_repository_description(
            hass, config_data.data[CONF_BASE_URL]
        )
    except (ConnectionError, ValueError) as err:
        msg = f"Error in '{config_data.title}' data fetch"
        raise HomeAssistantError(msg) from err

    return repo_data[REPO_KEY_CUSTOMS]


async def handle_service_supported_versions(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, list[str]]:
    """Download and return all the available versions."""
    config_entry_id = call.data[SERVICE_KEY_CONFIG_ENTRY]
    custom_integration = call.data[SERVICE_KEY_CUSTOM_COMPONENT]
    only_stable = call.data.get(SERVICE_KEY_ONLY_STABLE, True)

    config_data = hass.config_entries.async_get_entry(config_entry_id)
    if not config_data:
        msg = f"{config_entry_id} entry does not exist"
        raise HomeAssistantError(msg)

    customs_list = await handle_service_customs_list(hass, call)
    if custom_integration not in customs_list:
        msg = f"{custom_integration} not present in '{config_data.title}' repository"
        raise HomeAssistantError(msg)

    try:
        custom_data = await async_fetch_custom_description(
            hass, config_data.data[CONF_BASE_URL], custom_integration
        )
    except (ConnectionError, ValueError) as err:
        msg = "Error in {custom_integration} data fetch"
        raise HomeAssistantError(msg) from err

    return {
        SERVICE_KEY_SUPPORTED_VERSIONS: [
            str(v) for v in get_supported_versions(custom_data, only_stable=only_stable)
        ]
    }


async def handle_service_custom_download(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, None | AwesomeVersion]:
    """Manage the custom version download."""
    config_entry_id = call.data[SERVICE_KEY_CONFIG_ENTRY]
    custom_integration = call.data[SERVICE_KEY_CUSTOM_COMPONENT]
    custom_version = call.data.get(SERVICE_KEY_VERSION, None)

    config_data = hass.config_entries.async_get_entry(config_entry_id)
    if not config_data:
        msg = f"Invalid config data for the config entry {config_entry_id}"
        raise HomeAssistantError(msg)

    try:
        custom_data = await async_fetch_custom_description(
            hass, config_data.data[CONF_BASE_URL], custom_integration
        )
    except (ConnectionError, ValueError) as err:
        msg = "Error in {custom_integration} data fetch"
        raise HomeAssistantError(msg) from err

    available_versions = get_supported_versions(custom_data, only_stable=False)
    try:
        latest_version = max(available_versions)
    except ValueError:
        latest_version = None
    version = (
        AwesomeVersion(custom_version) if custom_version is not None else latest_version
    )
    if version is None or version not in available_versions:
        msg = f"Version {version} not valid for {custom_integration}"
        raise HomeAssistantError(msg)

    try:
        intalled_version = await async_download_and_install(
            hass, custom_integration, version, custom_data[REPO_KEY_VERSIONS][version]
        )
    except (ConnectionError, ValueError) as err:
        raise HomeAssistantError(str(err)) from err

    return {SERVICE_KEY_INSTALLED_VERSION: intalled_version}
