"""The check and download manager."""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
import voluptuous as vol
from aiohttp.client_exceptions import ClientError
from awesomeversion import AwesomeVersion, AwesomeVersionException
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
)

from .const import CHANGELOG_FILE, JSON_CUSTOM, JSON_REPO_DESC, LOGGER, MANIFEST_VERSION

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_REQUEST_TIMEOUT = 5.0

KEY_DESC = "description"
KEY_CUSTOMS = "customs"
KEY_LATEST = "latest"
KEY_VERSIONS = "versions"
KEY_HA_MIN_VERSION = "min_ha"
KEY_HA_MAX_VERSION = "max_ha"
KEY_ZIP_FILE = "release_file"

REPO_CUSTOMS_LIST = vol.Schema({str: str})

REPO_DESC_VALIDATOR = vol.Schema(
    {
        vol.Required(KEY_DESC): str,
        vol.Required(KEY_CUSTOMS): REPO_CUSTOMS_LIST,
    }
)


def awesome_version_validator(value: str) -> str:
    """Valida che la stringa sia una versione valida AwesomeVersion."""
    try:
        _ = AwesomeVersion(value)
    except AwesomeVersionException as err:
        msg = f"Invalid version string: {err}"
        raise vol.Invalid(msg) from err

    return value


CUSTOM_VERSION = vol.Schema(
    {
        vol.Required(KEY_HA_MIN_VERSION): awesome_version_validator,
        vol.Optional(KEY_HA_MAX_VERSION): awesome_version_validator,
        vol.Optional(KEY_ZIP_FILE): vol.Url,
    },
)

CUSTOM_LIST_VERSIONS = vol.Schema({awesome_version_validator: CUSTOM_VERSION})

CUSTOM_DESC_VALIDATOR = vol.Schema(
    {
        vol.Required(KEY_DESC): str,
        vol.Required(KEY_LATEST): awesome_version_validator,
        vol.Required(KEY_VERSIONS): CUSTOM_LIST_VERSIONS,
    }
)


async def async_fetch_repository_data(hass: HomeAssistant, base_url: str) -> dict:
    """Download the repo description with custom list."""
    session = async_get_clientsession(hass)
    try:
        async with (
            session.get(
                f"{base_url}/{JSON_REPO_DESC}",
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
            ) as resp,
        ):
            if resp.status != HTTPStatus.OK:
                msg = f"Description request error: {resp.status}"
                LOGGER.warning(msg)
                raise ConnectionError(msg)

            data = await resp.json()
            try:
                return REPO_DESC_VALIDATOR(data)
            except vol.Invalid:
                msg = "Invalid repository description found"
                LOGGER.exception(msg)
                raise ValueError(msg) from None

    except ClientError as err:
        msg = "Catch error in HTTP request"
        LOGGER.exception(msg)
        raise ConnectionError(msg) from err


async def async_fetch_custom_description(
    hass: HomeAssistant, base_url: str, component: str
) -> dict:
    """Download the different custom version available."""
    session = async_get_clientsession(hass)
    try:
        async with (
            session.get(
                f"{base_url}/{component}/{JSON_CUSTOM}",
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
            ) as resp,
        ):
            if resp.status != HTTPStatus.OK:
                msg = f"Custom {component} request error: {resp.status}"
                LOGGER.warning(msg)
                raise ConnectionError(msg)

            data = await resp.json()
            try:
                return CUSTOM_DESC_VALIDATOR(data)
            except vol.Invalid as err:
                msg = f"Invalid custom {component} description found"
                LOGGER.exception(msg)
                raise ValueError(msg) from err

    except ClientError:
        msg = "Catch error in HTTP request"
        LOGGER.exception(msg)
        raise ConnectionError(msg) from None


async def async_fetch_custom_changelog(
    hass: HomeAssistant, base_url: str, component: str
) -> str:
    """Download the different custom version available."""
    session = async_get_clientsession(hass)
    try:
        async with (
            session.get(
                f"{base_url}/{component}/{CHANGELOG_FILE}",
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
            ) as resp,
        ):
            if resp.status != HTTPStatus.OK:
                msg = f"Changelog for {component} request error: {resp.status}"
                LOGGER.warning(msg)
                raise ConnectionError(msg)

            return await resp.text()

    except ClientError:
        msg = "Catch error in HTTP request"
        LOGGER.exception(msg)
        raise ConnectionError(msg) from None


async def async_get_local_custom_manifest(
    hass: HomeAssistant, component: str
) -> dict | None:
    """Return the custom version readed from manifest.json if exist, otherwise None."""
    custom_path = hass.config.path(f"custom_components/{component}/manifest.json")

    if not Path(custom_path).exists():
        LOGGER.debug("The %s custom does not exist", component)
        return None

    # Lettura in thread separato per non bloccare l'event loop
    def read_manifest() -> dict:
        with Path(custom_path).open("r", encoding="utf-8") as manifest:
            try:
                return json.load(manifest)
            except json.JSONDecodeError:
                msg = f"Error in {component} manifest reading"
                LOGGER.exception(msg)
                return {}

    return await hass.async_add_executor_job(read_manifest)


async def async_download_and_install(
    hass: HomeAssistant, base_url: str, component: str, version: None | str
) -> None | str:
    """Download and install custom component from remote repository."""
    LOGGER.debug("Try to download custom '%s'", component)

    try:
        repo_data = await async_fetch_repository_data(hass, base_url)
    except (ConnectionError, ValueError):
        msg = "Error in repository data fetch"
        LOGGER.exception(msg)
        raise
    if component not in repo_data[KEY_CUSTOMS]:
        msg = "The custom is not present in the repository"
        LOGGER.error(msg)
        raise ValueError(msg)

    try:
        custom_data = await async_fetch_custom_description(hass, base_url, component)
    except (ConnectionError, ValueError):
        msg = "Error in repository custom {component} data fetch"
        LOGGER.exception(msg)
        raise

    version = version or custom_data.get(KEY_LATEST)
    if version is None or version not in custom_data[KEY_VERSIONS]:
        msg = f"Version {version} of {component} is not present on repository"
        LOGGER.error(msg)
        raise ValueError(msg)

    zip_url: str = custom_data[KEY_VERSIONS].get(
        KEY_ZIP_FILE, f"{base_url}/{component}/{version}.zip"
    )

    session = async_get_clientsession(hass)
    try:
        async with (
            session.get(
                zip_url,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp,
        ):
            if resp.status != HTTPStatus.OK:
                msg = f"{component} ZIP for {version} download failed: {resp.status}"
                LOGGER.warning(msg)
                raise ConnectionError(msg)
            data = await resp.read()

    except ClientError:
        msg = "Catch error in {component} ZIP for {version} download"
        LOGGER.exception(msg)
        raise ConnectionError(msg) from None

    # Extract data in memory and substitute files in the destination directory
    extract_path = hass.config.path(f"custom_components/_tmp_{component}")
    components_path = hass.config.path(f"custom_components/{component}")

    def extract_data() -> None:
        with zipfile.ZipFile(io.BytesIO(data)) as zip_data:
            folder_name = zip_data.namelist()[0]
            if Path(extract_path).exists():
                shutil.rmtree(extract_path)
            zip_data.extractall(extract_path)
            src_path = Path(extract_path) / folder_name

            # Overwrite local files
            if Path(components_path).exists():
                shutil.rmtree(components_path)
            shutil.copytree(src_path, components_path, dirs_exist_ok=True)

            shutil.rmtree(extract_path)

    await hass.async_add_executor_job(extract_data)
    return await check_version_installed(hass, component, version, zip_url)


async def check_version_installed(
    hass: HomeAssistant, component: str, version: str, zip_url: str
) -> None | str:
    """Check the installed version and raise repair."""
    component_manifest = await async_get_local_custom_manifest(hass, component) or {}
    installed_version = component_manifest.get(MANIFEST_VERSION)

    translation_placeholders = {
        "component": component,
        "desidered_version": version,
        "installed_version": installed_version or "[Not retrived]",
    }

    if installed_version == version:
        LOGGER.info("Install version %s for %s completed.", version, component)
        async_create_issue(
            hass,
            component,
            "restart_required",
            is_fixable=True,
            severity=IssueSeverity.WARNING,
            translation_key="restart_required",
            translation_placeholders=translation_placeholders,
        )
    else:
        LOGGER.error("Error in install version %s for %s.", version, component)
        async_create_issue(
            hass,
            component,
            "update_failed",
            is_fixable=False,
            severity=IssueSeverity.ERROR,
            translation_key="update_failed",
            learn_more_url=zip_url,
            translation_placeholders=translation_placeholders,
        )

    return installed_version
