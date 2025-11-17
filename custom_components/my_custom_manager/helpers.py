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
from homeassistant.const import __version__ as ha_version
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
)

from .const import JSON_CUSTOM, JSON_REPO_DESC, LOGGER, MANIFEST_VERSION

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_REQUEST_TIMEOUT = 5.0

KEY_CHANGELOG = "changelog"
KEY_CUSTOMS = "customs"
KEY_DESCRIPTION = "description"
KEY_HA_MIN_VERSION = "ha_min"
KEY_HA_MAX_VERSION = "ha_max"
KEY_HOMEPAGE = "homepage"
KEY_NAME = "name"
KEY_RELEASE_FILE = "release_file"
KEY_VERSIONS = "versions"

## Repository schemas


def awesome_version_validator(value: str) -> str:
    """Valida che la stringa sia una versione valida AwesomeVersion."""
    try:
        _ = AwesomeVersion(value)
    except AwesomeVersionException as err:
        msg = f"Invalid version string: {err}"
        raise vol.Invalid(msg) from err

    return value


CUSTOM_VERSION_SCHEMA = vol.Schema(
    {
        vol.Required(KEY_HA_MIN_VERSION): awesome_version_validator,
        vol.Optional(KEY_HA_MAX_VERSION): awesome_version_validator,
        vol.Required(KEY_RELEASE_FILE): vol.Url(),  # pyright: ignore[reportCallIssue]
        vol.Optional(KEY_HOMEPAGE): vol.Url(),  # pyright: ignore[reportCallIssue]
    },
    extra=False,
)
CUSTOM_VERSIONS_LIST_SCHEMA = vol.Schema(
    {awesome_version_validator: CUSTOM_VERSION_SCHEMA}, extra=False
)
CUSTOM_SCHEMA = vol.Schema(
    {
        vol.Required(KEY_NAME): str,
        vol.Optional(KEY_DESCRIPTION): str,
        vol.Optional(KEY_HOMEPAGE): vol.Url(),  # pyright: ignore[reportCallIssue]
        vol.Optional(KEY_CHANGELOG): vol.Url(),  # pyright: ignore[reportCallIssue]
        vol.Required(KEY_VERSIONS): CUSTOM_VERSIONS_LIST_SCHEMA,
    },
    extra=False,
)

REPOSITORY_CUSTOM_SCHEMA = vol.Schema({str: str}, extra=False)
REPOSITORY_SCHEMA = vol.Schema(
    {
        vol.Required(KEY_NAME): str,
        vol.Optional(KEY_DESCRIPTION): str,
        vol.Optional(KEY_HOMEPAGE): vol.Url(),  # pyright: ignore[reportCallIssue]
        vol.Required(KEY_CUSTOMS): REPOSITORY_CUSTOM_SCHEMA,
    },
    extra=False,
)


def is_stable_version(version: AwesomeVersion) -> bool:
    """Return if version is stable."""
    return not (
        version.alpha or version.beta or version.dev or version.release_candidate
    )


def get_supported_versions(
    custom_data: dict, *, only_stable: bool = True
) -> list[AwesomeVersion]:
    """Return the latest available version."""
    awesome_ha_version = AwesomeVersion(ha_version)
    return [
        AwesomeVersion(v)
        for v, data in custom_data[KEY_VERSIONS].items()
        # Filter unstable versions
        if (is_stable_version(AwesomeVersion(v)) or not only_stable)
        and awesome_ha_version >= AwesomeVersion(data[KEY_HA_MIN_VERSION])
        and awesome_ha_version
        <= AwesomeVersion(data.get(KEY_HA_MAX_VERSION, ha_version))
    ]


def get_latest_version(custom_data: dict, *, only_stable: bool = True) -> str:
    """Return the latest available version."""
    return str(max(get_supported_versions(custom_data, only_stable=only_stable)))


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

            try:
                data = await resp.json()
                return REPOSITORY_SCHEMA(data)
            except (vol.Invalid, json.JSONDecodeError) as err:
                msg = "Invalid repository description found"
                LOGGER.exception(msg)
                raise ValueError(msg) from err

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

            try:
                data = await resp.json()
                return CUSTOM_SCHEMA(data)
            except (vol.Invalid, json.JSONDecodeError) as err:
                msg = f"Invalid custom {component} description found"
                LOGGER.exception(msg)
                raise ValueError(msg) from err

    except ClientError:
        msg = f"Catch error in HTTP request for {component}"
        LOGGER.exception(msg)
        raise ConnectionError(msg) from None


async def async_fetch_page(hass: HomeAssistant, url: str) -> str:
    """Download the different custom version available."""
    session = async_get_clientsession(hass)
    try:
        async with (
            session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
            ) as resp,
        ):
            if resp.status != HTTPStatus.OK:
                msg = f"Page request error: {resp.status}"
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
    """Return the custom version read from manifest.json if exist, otherwise None."""
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
    hass: HomeAssistant,
    base_url: str,
    component: str,
    version: None | str = "",
    *,
    only_stable: bool = True,
) -> None | str:
    """Download and install custom component from remote repository."""
    LOGGER.debug("Try to download custom '%s'@'%s'", component, version or "latest")

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
        msg = f"Error in repository custom {component} data fetch"
        LOGGER.exception(msg)
        raise

    version = (
        version or get_latest_version(custom_data, only_stable=only_stable) or None
    )
    if version is None or version not in custom_data[KEY_VERSIONS]:
        msg = "No valid version {version} for {component} requested"
        LOGGER.error(msg)
        raise ValueError(msg)

    session = async_get_clientsession(hass)
    try:
        async with (
            session.get(
                custom_data[KEY_VERSIONS][version][KEY_RELEASE_FILE],
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp,
        ):
            if resp.status != HTTPStatus.OK:
                msg = f"Download release file for {component}@{version} : {resp.status}"
                LOGGER.warning(msg)
                raise ConnectionError(msg)
            data = await resp.read()

    except ClientError:
        msg = f"Catch error in release file for {component}@{version} download"
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

    learn_more_url = custom_data[KEY_VERSIONS][version].get(
        KEY_HOMEPAGE
    ) or custom_data[KEY_VERSIONS][version].get(KEY_RELEASE_FILE)
    return await check_version_installed(hass, component, version, learn_more_url)


async def check_version_installed(
    hass: HomeAssistant, component: str, version: str, learn_more_url: str
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
            learn_more_url=learn_more_url,
            translation_placeholders=translation_placeholders,
        )

    return installed_version
