"""
Custom integration for manage personal customs integration.

For more details about this integration, please refer to
https://git.villavasco.ovh/home-assistant/my-custom-manager/
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from homeassistant.core import ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError

from .const import (
    CONF_BASE_URL,
    CUSTOM_MANIFEST_VERSION,
    DOMAIN,
    LOGGER,
    PLATFORMS,
    SERVICE_DOWNLOAD_CUSTOM,
    SERVICE_GET_CUSTOM_LIST,
    SERVICE_GET_SUPPORTED_VERSIONS,
    SERVICE_KEY_CONFIG_ENTRY,
    SERVICE_KEY_CUSTOM_COMPONENT,
    SERVICE_KEY_ONLY_STABLE,
    SERVICE_KEY_VERSION,
)
from .domain_data import DomainData
from .entry_data import RuntimeEntryData
from .helpers import (
    REPO_KEY_CUSTOMS,
    async_fetch_repository_description,
    async_get_local_custom_manifest,
)
from .services import (
    SERVICE_DOWNLOAD_CUSTOM_SCHEMA,
    SERVICE_GET_CUSTOM_LIST_SCHEMA,
    SERVICE_GET_SUPPORTED_VERSIONS_SCHEMA,
    handle_service_custom_download,
    handle_service_customs_list,
    handle_service_supported_versions,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Register the component integration services."""
    domain_data = DomainData.get(hass)
    domain_data.actual_version = (
        await async_get_local_custom_manifest(hass, DOMAIN) or {}
    ).get(CUSTOM_MANIFEST_VERSION, "")

    def get_entry_data_from_id(config_entry_id: str) -> ConfigEntry:
        """Return the config entry data from id."""
        config_data = hass.config_entries.async_get_entry(config_entry_id)
        if not config_data:
            msg = f"{config_entry_id} entry does not exist"
            raise HomeAssistantError(msg)
        return config_data

    async def handle_customs_list(call: ServiceCall) -> ServiceResponse:
        """Download the repository customs list."""
        config_entry_id = call.data[SERVICE_KEY_CONFIG_ENTRY]
        return cast(
            "ServiceResponse",
            await handle_service_customs_list(
                hass, get_entry_data_from_id(config_entry_id)
            ),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CUSTOM_LIST,
        handle_customs_list,
        schema=SERVICE_GET_CUSTOM_LIST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    async def handle_supported_versions(call: ServiceCall) -> ServiceResponse:
        """Download and return all the available versions."""
        config_entry_id = call.data[SERVICE_KEY_CONFIG_ENTRY]
        custom_integration = call.data[SERVICE_KEY_CUSTOM_COMPONENT]
        only_stable = call.data.get(SERVICE_KEY_ONLY_STABLE, True)
        return cast(
            "ServiceResponse",
            await handle_service_supported_versions(
                hass,
                get_entry_data_from_id(config_entry_id),
                custom_integration,
                only_stable=only_stable,
            ),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_SUPPORTED_VERSIONS,
        handle_supported_versions,
        schema=SERVICE_GET_SUPPORTED_VERSIONS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    async def handle_custom_download(call: ServiceCall) -> ServiceResponse:
        """Manage the custom version download."""
        config_entry_id = call.data[SERVICE_KEY_CONFIG_ENTRY]
        custom_integration = call.data[SERVICE_KEY_CUSTOM_COMPONENT]
        custom_version = call.data.get(SERVICE_KEY_VERSION, None)
        return cast(
            "ServiceResponse",
            await handle_service_custom_download(
                hass,
                get_entry_data_from_id(config_entry_id),
                custom_integration,
                custom_version,
            ),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DOWNLOAD_CUSTOM,
        handle_custom_download,
        schema=SERVICE_DOWNLOAD_CUSTOM_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up my custom update manager from config entry."""
    base_url = entry.data[CONF_BASE_URL]
    entry_runtime_data = RuntimeEntryData(entry_id=entry.entry_id)

    LOGGER.debug("Check repository descriptions for: %s", entry.title)

    try:
        repo_desc = await async_fetch_repository_description(hass, base_url)
    except (ConnectionError, ValueError) as err:
        msg = f"Error in the '{entry.title}' data fetch"
        raise ConfigEntryNotReady(msg) from err
    entry_runtime_data.customs_list = list(repo_desc.get(REPO_KEY_CUSTOMS, {}).keys())

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
        hass.services.async_remove(DOMAIN, SERVICE_GET_CUSTOM_LIST)
        hass.services.async_remove(DOMAIN, SERVICE_GET_SUPPORTED_VERSIONS)
        hass.services.async_remove(DOMAIN, SERVICE_DOWNLOAD_CUSTOM)

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
