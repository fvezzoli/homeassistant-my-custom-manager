"""Support for custom components update."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_BASE_URL,
    CONF_POLL_TIME,
    DOMAIN,
    LOGGER,
    MANIFEST_NAME,
    MANIFEST_VERSION,
    VERSION,
)
from .domain_data import DomainData
from .helpers import (
    KEY_LATEST,
    async_download_and_install,
    async_fetch_custom_changelog,
    async_fetch_custom_description,
    async_get_local_custom_manifest,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the updates entity for my custom components."""
    entry_domain_data = DomainData.get(hass)

    update_entity: list[ComponentUpdateEntity] = []
    for domain in entry_domain_data.custom_list:
        domain_manifest = await async_get_local_custom_manifest(hass, domain) or {}
        domain_version = domain_manifest.get(MANIFEST_VERSION, None)
        if domain_version:
            coordinator = EntityUpdateCoordinator(
                hass,
                domain,
                entry.data[CONF_BASE_URL],
                entry.options[CONF_POLL_TIME],
            )
            await coordinator.async_config_entry_first_refresh()
            update_entity.extend(
                [
                    ComponentUpdateEntity(
                        coordinator,
                        entry.data[CONF_BASE_URL],
                        domain,
                        domain_version,
                        domain_manifest.get(MANIFEST_NAME, domain),
                    )
                ]
            )

    async_add_entities(update_entity)


class EntityUpdateCoordinator(DataUpdateCoordinator):
    """Manage the periodically version update."""

    def __init__(
        self,
        hass: HomeAssistant,
        domain: str,
        base_url: str,
        update_interval: int,
    ) -> None:
        """Init and start the update coordinator."""
        self._domain = domain
        self._base_url = base_url
        super().__init__(
            hass,
            LOGGER,
            name=f"{domain}_update",
            update_interval=timedelta(hours=update_interval),
        )

    async def _async_update_data(self) -> str:
        try:
            domain_data = await async_fetch_custom_description(
                self.hass, self._base_url, self._domain
            )
        except (ConnectionError, ValueError) as err:
            msg = "Error in data fetch"
            raise UpdateFailed(msg) from err

        version = domain_data.get(KEY_LATEST)
        if not version:
            msg = "Missing latest version key"
            raise UpdateFailed(msg)

        return version


class ComponentUpdateEntity(CoordinatorEntity, UpdateEntity):
    """Entità di aggiornamento."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.RELEASE_NOTES
        | UpdateEntityFeature.SPECIFIC_VERSION
    )
    _attr_translation_key = "component_update"

    def __init__(
        self,
        coordinator: EntityUpdateCoordinator,
        base_url: str,
        domain: str,
        actual_version: str,
        name: str,
    ) -> None:
        """Init the integration update entity."""
        super().__init__(coordinator)
        self._base_url = base_url
        self._domain = domain
        self._domain_name = name
        self._attr_installed_version = actual_version
        self._attr_unique_id = f"{domain}_update"
        self._attr_in_progress = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._domain}_update")},
            model="My custom manager updater",
            name=self._domain_name,
            sw_version=VERSION,
        )

    async def async_release_notes(self) -> str | None:
        """Return the relase notes for the version."""
        try:
            return await async_fetch_custom_changelog(
                self.hass, self._base_url, self._domain
            )
        except (ConnectionError, ValueError):
            return None

    @property
    def latest_version(self) -> dict[str, Any]:
        """Latest available version."""
        return self.coordinator.data

    async def async_install(self, version: str | None, **_kwargs: Any) -> None:
        """Perform the integration download and file substitution."""
        version = version or str(self.coordinator.data)

        self._in_progress = True
        self.async_write_ha_state()

        self._attr_installed_version = await async_download_and_install(
            self.hass, self._base_url, self._domain, version
        )

        self._in_progress = False
        self.async_write_ha_state()
