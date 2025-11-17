"""Service handler function."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from awesomeversion import AwesomeVersion
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_BASE_URL,
    REPO_KEY_HOMEPAGE,
    REPO_KEY_NAME,
    REPO_KEY_RELEASE_FILE,
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
    check_version_installed,
    get_supported_versions,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

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
    hass: HomeAssistant, config_data: ConfigEntry
) -> dict[str, str]:
    """Download the repository customs list."""
    try:
        repo_data = await async_fetch_repository_description(
            hass, config_data.data[CONF_BASE_URL]
        )
    except (ConnectionError, ValueError) as err:
        msg = f"Error in '{config_data.title}' data fetch"
        raise HomeAssistantError(msg) from err

    return repo_data[REPO_KEY_CUSTOMS]


async def handle_service_supported_versions(
    hass: HomeAssistant,
    config_data: ConfigEntry,
    custom_integration: str,
    *,
    only_stable: bool,
) -> dict[str, list[str]]:
    """Download and return all the available versions."""
    customs_list = await handle_service_customs_list(hass, config_data)
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
    hass: HomeAssistant,
    config_data: ConfigEntry,
    custom_integration: str,
    custom_version: None | str,
) -> dict[str, None | AwesomeVersion]:
    """Manage the custom version download."""
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

    version_desc = custom_data[REPO_KEY_VERSIONS][version]
    try:
        await async_download_and_install(
            hass, custom_integration, version, version_desc
        )
    except (ConnectionError, ValueError) as err:
        raise HomeAssistantError(str(err)) from err

    learn_more_url: None | str = version_desc.get(
        REPO_KEY_HOMEPAGE
    ) or version_desc.get(REPO_KEY_RELEASE_FILE)
    intalled_version = await check_version_installed(
        hass,
        custom_integration,
        custom_data[REPO_KEY_NAME],
        version,
        learn_more_url,
    )

    return {SERVICE_KEY_INSTALLED_VERSION: intalled_version}
