"""Support for custom components update."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

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
    REPO_KEY_CHANGELOG,
    async_download_and_install,
    async_fetch_custom_description,
    async_fetch_page,
    async_get_local_custom_manifest,
    get_latest_version,
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
    entry_runtime_data = entry_domain_data.get_entry_data(entry)

    update_entity: list[ComponentUpdateEntity] = []
    for domain in entry_runtime_data.customs_list:
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
        self._changelog_url: None | str = None

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

        self._changelog_url = domain_data.get(REPO_KEY_CHANGELOG)

        return get_latest_version(domain_data, only_stable=True)

    @property
    def changelog_url(self) -> None | str:
        """Return the changelog URL."""
        return self._changelog_url


class ComponentUpdateEntity(CoordinatorEntity, UpdateEntity):
    """Entità di aggiornamento."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
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

        self._attr_supported_features = (
            UpdateEntityFeature.INSTALL | UpdateEntityFeature.SPECIFIC_VERSION
        )
        if cast("EntityUpdateCoordinator", self.coordinator).changelog_url:
            self._attr_supported_features |= UpdateEntityFeature.RELEASE_NOTES

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
        changelog_url = cast("EntityUpdateCoordinator", self.coordinator).changelog_url
        if changelog_url:
            try:
                return await async_fetch_page(
                    self.hass,
                    changelog_url,
                )
            except (ConnectionError, ValueError):
                LOGGER.exception("Error in changelog Fetch")
                return None

        return None

    @property
    def latest_version(self) -> dict[str, Any]:
        """Latest available version."""
        return self.coordinator.data

    async def async_install(self, version: str | None, **_kwargs: Any) -> None:
        """Perform the integration download and file substitution."""
        version = version or str(self.coordinator.data)

        self._attr_in_progress = True
        self.async_write_ha_state()

        try:
            self._attr_installed_version = await async_download_and_install(
                self.hass, self._base_url, self._domain, version
            )
        finally:
            self._attr_in_progress = False
            self.async_write_ha_state()
