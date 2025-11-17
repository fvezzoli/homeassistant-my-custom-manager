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
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from aiohttp.client_exceptions import ClientError
from awesomeversion import AwesomeVersion, AwesomeVersionException
from homeassistant.const import __version__ as ha_version
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
)

from .const import (
    CUSTOM_MANIFEST_VERSION,
    LOGGER,
    REPO_JSON_CUSTOM,
    REPO_JSON_DESC,
    REPO_KEY_CHANGELOG,
    REPO_KEY_CUSTOMS,
    REPO_KEY_DESCRIPTION,
    REPO_KEY_HA_MAX,
    REPO_KEY_HA_MIN,
    REPO_KEY_HOMEPAGE,
    REPO_KEY_NAME,
    REPO_KEY_RELEASE_FILE,
    REPO_KEY_VERSIONS,
    REPO_REQUEST_TIMEOUT,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def awesome_version_validator(value: str) -> str:
    """Valida che la stringa sia una versione valida AwesomeVersion."""
    try:
        value = AwesomeVersion(value)
    except AwesomeVersionException as err:
        msg = f"Invalid version string: {err}"
        raise vol.Invalid(msg) from err

    return value


CUSTOM_VERSION_SCHEMA = vol.Schema(
    {
        vol.Required(REPO_KEY_HA_MIN): awesome_version_validator,
        vol.Optional(REPO_KEY_HA_MAX): awesome_version_validator,
        vol.Required(REPO_KEY_RELEASE_FILE): cv.url,
        vol.Optional(REPO_KEY_HOMEPAGE): cv.url,
    },
    extra=False,
)
CUSTOM_VERSIONS_LIST_SCHEMA = vol.Schema(
    {awesome_version_validator: CUSTOM_VERSION_SCHEMA}, extra=False
)
CUSTOM_SCHEMA = vol.Schema(
    {
        vol.Required(REPO_KEY_NAME): str,
        vol.Optional(REPO_KEY_DESCRIPTION): str,
        vol.Optional(REPO_KEY_HOMEPAGE): cv.url,
        vol.Optional(REPO_KEY_CHANGELOG): cv.url,
        vol.Required(REPO_KEY_VERSIONS): CUSTOM_VERSIONS_LIST_SCHEMA,
    },
    extra=False,
)

REPOSITORY_CUSTOM_SCHEMA = vol.Schema({str: str}, extra=False)
REPOSITORY_SCHEMA = vol.Schema(
    {
        vol.Required(REPO_KEY_NAME): str,
        vol.Optional(REPO_KEY_DESCRIPTION): str,
        vol.Optional(REPO_KEY_HOMEPAGE): cv.url,
        vol.Required(REPO_KEY_CUSTOMS): REPOSITORY_CUSTOM_SCHEMA,
    },
    extra=False,
)


async def async_fetch_repository_description(
    hass: HomeAssistant, base_url: str
) -> dict:
    """Download the repo description with custom list."""
    session = async_get_clientsession(hass)
    try:
        async with (
            session.get(
                f"{base_url}/{REPO_JSON_DESC}",
                timeout=aiohttp.ClientTimeout(total=REPO_REQUEST_TIMEOUT),
            ) as resp,
        ):
            if resp.status != HTTPStatus.OK:
                msg = f"Description request error: {resp.status}"
                raise ConnectionError(msg)

            try:
                data = await resp.json()
                return REPOSITORY_SCHEMA(data)
            except (vol.Invalid, json.JSONDecodeError) as err:
                msg = "Invalid repository description"
                raise ValueError(msg) from err

    except ClientError as err:
        msg = "HTTP request error"
        raise ConnectionError(msg) from err


async def async_fetch_custom_description(
    hass: HomeAssistant, base_url: str, component: str
) -> dict:
    """Download the different custom version available."""
    session = async_get_clientsession(hass)
    try:
        async with (
            session.get(
                f"{base_url}/{component}/{REPO_JSON_CUSTOM}",
                timeout=aiohttp.ClientTimeout(total=REPO_REQUEST_TIMEOUT),
            ) as resp,
        ):
            if resp.status != HTTPStatus.OK:
                msg = f"Description for {component} request error: {resp.status}"
                raise ConnectionError(msg)

            try:
                data = await resp.json()
                return CUSTOM_SCHEMA(data)
            except (vol.Invalid, json.JSONDecodeError) as err:
                msg = f"Invalid {component} description found"
                raise ValueError(msg) from err

    except ClientError as err:
        msg = f"HTTP request error for {component}"
        raise ConnectionError(msg) from err


def is_stable_version(version: AwesomeVersion) -> bool:
    """Return if version is stable."""
    return not (
        version.alpha or version.beta or version.dev or version.release_candidate
    )


def get_supported_versions(
    custom_data: dict, *, show_unstable: bool = True
) -> list[AwesomeVersion]:
    """Return the latest available version."""
    awesome_ha_version = AwesomeVersion(ha_version)
    return [
        AwesomeVersion(v)
        for v, data in custom_data[REPO_KEY_VERSIONS].items()
        # Filter unstable versions
        if (is_stable_version(AwesomeVersion(v)) or show_unstable)
        # Filter unsupported due to HA version
        and awesome_ha_version >= AwesomeVersion(data[REPO_KEY_HA_MIN])
        and awesome_ha_version <= AwesomeVersion(data.get(REPO_KEY_HA_MAX, ha_version))
    ]


async def async_fetch_page(hass: HomeAssistant, url: str) -> str:
    """Download the different custom version available."""
    session = async_get_clientsession(hass)
    try:
        async with (
            session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REPO_REQUEST_TIMEOUT),
            ) as resp,
        ):
            if resp.status != HTTPStatus.OK:
                msg = f"Page request error: {resp.status}"
                LOGGER.warning(msg)
                raise ConnectionError(msg)

            return await resp.text()

    except ClientError as err:
        msg = "Catch error in HTTP request"
        LOGGER.exception(msg)
        raise ConnectionError(msg) from err


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
    component: str,
    version: AwesomeVersion,
    version_desc: dict,
) -> None:
    """Download and install custom component from remote repository."""
    LOGGER.debug("Try to download custom %s@%s", component, version or "latest")

    session = async_get_clientsession(hass)
    try:
        async with (
            session.get(
                version_desc[REPO_KEY_RELEASE_FILE],
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp,
        ):
            if resp.status != HTTPStatus.OK:
                msg = f"Download release file for {component}@{version} : {resp.status}"
                LOGGER.warning(msg)
                raise ConnectionError(msg)
            data = await resp.read()

    except ClientError as err:
        msg = f"Catch error in release file for {component}@{version} download"
        LOGGER.exception(msg)
        raise ConnectionError(msg) from err

    # Extract data in memory and substitute files in the destination directory
    extract_path = hass.config.path(f"custom_components/_tmp_{component}")
    components_path = hass.config.path(f"custom_components/{component}")

    def extract_data() -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zip_data:
                namelist = zip_data.namelist()
                if not namelist:
                    msg = "Empty zip archive"
                    raise ValueError(msg)

                folder_name = namelist[0].rstrip("/")
                if Path(extract_path).exists():
                    shutil.rmtree(extract_path)
                zip_data.extractall(extract_path)
                src_path = Path(extract_path) / folder_name

                # Overwrite local files
                if Path(components_path).exists():
                    shutil.rmtree(components_path)
                shutil.copytree(src_path, components_path, dirs_exist_ok=True)
        except (FileNotFoundError, PermissionError, shutil.Error, OSError):
            msg = "Error in file extract"
            LOGGER.exception(msg)

        finally:
            # Try to remove always the temporary directory
            try:
                if Path(extract_path).exists():
                    shutil.rmtree(extract_path)
            except (FileNotFoundError, PermissionError, shutil.Error, OSError):
                LOGGER.error("Fail to remove the temporary directory")

    await hass.async_add_executor_job(extract_data)


async def check_version_installed(
    hass: HomeAssistant,
    component: str,
    component_name: str,
    version: AwesomeVersion,
    learn_more_url: None | str,
) -> None | AwesomeVersion:
    """Check the installed version and raise repair."""
    component_manifest = await async_get_local_custom_manifest(hass, component) or {}
    manifest_version = component_manifest.get(CUSTOM_MANIFEST_VERSION)
    installed_version = AwesomeVersion(manifest_version) if manifest_version else None

    translation_placeholders = {
        "component_name": component_name,
        "component": component,
        "desidered_version": version,
        "installed_version": installed_version or "[Not retrived]",
    }

    if installed_version == version:
        LOGGER.info("Installation of %s@%s completed.", component, version)
        async_create_issue(
            hass,
            component,
            "restart_required",
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="restart_required",
            learn_more_url=learn_more_url,
            translation_placeholders=translation_placeholders,
        )
    else:
        LOGGER.error("Installation of %s@%s failed.", component, version)
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
