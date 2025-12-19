"""Service handler function."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from awesomeversion import AwesomeVersion
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
)

from .const import (
    CONF_BASE_URL,
    CONF_SHOW_UNSTABLE,
    DEFAULT_SHOW_UNSTABLE,
    DOMAIN,
    LOGGER,
    REPO_KEY_NAME,
    SERVICE_KEY_CONFIG_ENTRY,
    SERVICE_KEY_CUSTOM_COMPONENT,
    SERVICE_KEY_INSTALLED_VERSION,
    SERVICE_KEY_SHOW_UNSTABLE,
    SERVICE_KEY_SUPPORTED_VERSIONS,
    SERVICE_KEY_VERSION,
)
from .domain_data import DomainData
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
        vol.Optional(SERVICE_KEY_SHOW_UNSTABLE): cv.boolean,
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
    show_unstable: bool,
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
        msg = f"Error in {custom_integration} data fetch"
        raise HomeAssistantError(msg) from err

    return {
        SERVICE_KEY_SUPPORTED_VERSIONS: [
            str(v)
            for v in get_supported_versions(custom_data, show_unstable=show_unstable)
        ]
    }


async def handle_service_custom_download(
    hass: HomeAssistant,
    config_data: ConfigEntry,
    custom_integration: str,
    custom_version: None | str,
    *,
    generate_issue: bool = True,
) -> dict[str, None | AwesomeVersion]:
    """Manage the custom version download."""
    try:
        custom_data = await async_fetch_custom_description(
            hass, config_data.data[CONF_BASE_URL], custom_integration
        )
    except (ConnectionError, ValueError) as err:
        msg = f"Error in {custom_integration} data fetch"
        raise HomeAssistantError(msg) from err

    show_unstable = config_data.options.get(CONF_SHOW_UNSTABLE, DEFAULT_SHOW_UNSTABLE)
    if custom_version is not None:
        show_unstable = True
    available_versions = get_supported_versions(
        custom_data,
        show_unstable=show_unstable,
    )
    if len(available_versions) == 0:
        msg = f"No available version present for {custom_integration}"
        raise HomeAssistantError(msg)

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

    installed_version = await check_version_installed(
        hass,
        custom_integration,
    )

    domain_data = DomainData.get(hass)
    domain_data.repairs[custom_integration] = {
        "component": custom_integration,
        "component_desc": custom_data[REPO_KEY_NAME],
        "desired_version": version,
        "installed_version": installed_version or "[Not retrived]",
        "config_id": config_data.entry_id,
        "version_desc": version_desc,
    }

    issue_type = "failed"
    issue_severity = IssueSeverity.ERROR
    if installed_version is not None and installed_version == version:
        LOGGER.info("Installation of %s@%s completed.", custom_integration, version)
        issue_type = "done"
        issue_severity = IssueSeverity.WARNING
    else:
        LOGGER.error("Installation of %s@%s failed.", custom_integration, version)

    if generate_issue:
        async_create_issue(
            hass=hass,
            domain=DOMAIN,
            issue_id=f"install_{issue_type}_{custom_integration}",
            is_fixable=True,
            issue_domain=DOMAIN,
            severity=issue_severity,
            translation_key="custom_install_end",
            translation_placeholders={
                "component_name": custom_data[REPO_KEY_NAME],
                "issue_type": issue_type,
            },
        )

    return {SERVICE_KEY_INSTALLED_VERSION: installed_version}
