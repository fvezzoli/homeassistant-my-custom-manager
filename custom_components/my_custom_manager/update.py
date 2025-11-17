"""Support for custom components update."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from awesomeversion import AwesomeVersion
from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_BASE_URL,
    CONF_POLL_TIME,
    CONF_SHOW_UNSTABLE,
    CUSTOM_MANIFEST_NAME,
    CUSTOM_MANIFEST_VERSION,
    DEFAULT_POLLING_HOURS,
    DEFAULT_SHOW_UNSTABLE,
    DOMAIN,
    LOGGER,
    SERVICE_KEY_INSTALLED_VERSION,
)
from .domain_data import DomainData
from .helpers import (
    REPO_KEY_CHANGELOG,
    async_fetch_custom_description,
    async_fetch_page,
    async_get_local_custom_manifest,
    get_supported_versions,
)
from .services import handle_service_custom_download

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
    for custom_integration in entry_runtime_data.customs_list:
        custom_manifest = (
            await async_get_local_custom_manifest(hass, custom_integration) or {}
        )
        local_custom_version = custom_manifest.get(CUSTOM_MANIFEST_VERSION, None)
        if local_custom_version:
            coordinator = EntityUpdateCoordinator(
                hass,
                custom_integration,
                entry,
            )
            await coordinator.async_config_entry_first_refresh()
            update_entity.extend(
                [
                    ComponentUpdateEntity(
                        coordinator,
                        entry,
                        custom_integration,
                        local_custom_version,
                        custom_manifest.get(CUSTOM_MANIFEST_NAME, custom_integration),
                    )
                ]
            )

    async_add_entities(update_entity)


class EntityUpdateCoordinator(DataUpdateCoordinator):
    """Manage the periodically version update."""

    def __init__(
        self,
        hass: HomeAssistant,
        custom_integration: str,
        entry: ConfigEntry,
    ) -> None:
        """Init and start the update coordinator."""
        self._custom_integration = custom_integration
        self._entry = entry

        self._changelog_url: None | str = None

        super().__init__(
            hass,
            LOGGER,
            name=f"{custom_integration}_update",
            update_interval=timedelta(
                hours=entry.options.get(CONF_POLL_TIME, DEFAULT_POLLING_HOURS)
            ),
        )

    async def _async_update_data(self) -> str:
        try:
            custom_repo_data = await async_fetch_custom_description(
                self.hass, self._entry.data[CONF_BASE_URL], self._custom_integration
            )
        except (ConnectionError, ValueError):
            msg = "Error in data fetch"
            LOGGER.exception(msg)
            raise UpdateFailed(msg) from None

        self._changelog_url = custom_repo_data.get(REPO_KEY_CHANGELOG, None)

        supported_versions = get_supported_versions(
            custom_repo_data,
            show_unstable=self._entry.options.get(
                CONF_SHOW_UNSTABLE, DEFAULT_SHOW_UNSTABLE
            ),
        )
        return str(max(supported_versions))

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
        config_entry: ConfigEntry,
        custom_integration: str,
        actual_version: str,
        name: str,
    ) -> None:
        """Init the integration update entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._custom_integration = custom_integration
        self._custom_name = name
        self._attr_installed_version = actual_version
        self._attr_unique_id = f"{custom_integration}_update"
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
            identifiers={(DOMAIN, f"{self._custom_integration}_update")},
            model="My custom manager updater",
            name=self._custom_name,
            sw_version=DomainData.get(self.hass).actual_version,
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

    async def async_install(
        self,
        version: str | None,
        _backup: bool,  # noqa: FBT001
        **_kwargs: Any,
    ) -> None:
        """Perform the integration download and file substitution."""
        version = version or str(self.coordinator.data)
        if version is None:
            msg = "Requested version is not valid"
            raise HomeAssistantError(msg)
        version = AwesomeVersion(version)

        self._attr_in_progress = True
        self.async_write_ha_state()

        returned_version: AwesomeVersion | None = None
        try:
            returned_version = (
                await handle_service_custom_download(
                    self.hass,
                    self._config_entry,
                    self._custom_integration,
                    str(version),
                )
            ).get(SERVICE_KEY_INSTALLED_VERSION, None)
        finally:
            self._attr_installed_version = (
                str(returned_version) if returned_version else None
            )

            self._attr_in_progress = False
            self.async_write_ha_state()
