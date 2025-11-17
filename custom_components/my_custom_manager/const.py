"""Constants for integration_blueprint."""

from logging import Logger, getLogger

from homeassistant.const import Platform

LOGGER: Logger = getLogger(__package__)

DOMAIN = "my_custom_manager"

PLATFORMS = [Platform.UPDATE]

# Entry configuration

DEFAULT_POLLING_HOURS = 6
DEFAULT_SHOW_UNSTABLE = False

CONF_BASE_URL = "base_url"
CONF_POLL_TIME = "polling_time"
CONF_SHOW_UNSTABLE = "show_unstable"

# Local custom manifest

CUSTOM_MANIFEST_NAME = "name"
CUSTOM_MANIFEST_VERSION = "version"

# Repository description

REPO_JSON_DESC = "repository.json"
REPO_JSON_CUSTOM = "custom.json"

REPO_REQUEST_TIMEOUT = 5.0

REPO_KEY_CHANGELOG = "changelog"
REPO_KEY_CUSTOMS = "customs"
REPO_KEY_DESCRIPTION = "description"
REPO_KEY_HA_MIN = "ha_min"
REPO_KEY_HA_MAX = "ha_max"
REPO_KEY_HOMEPAGE = "homepage"
REPO_KEY_NAME = "name"
REPO_KEY_RELEASE_FILE = "release_file"
REPO_KEY_VERSIONS = "versions"

# Services

SERVICE_GET_CUSTOM_LIST = "get_customs_list"
SERVICE_GET_SUPPORTED_VERSIONS = "get_supported_versions"
SERVICE_DOWNLOAD_CUSTOM = "download_custom"

SERVICE_KEY_CONFIG_ENTRY = "config_entry"
SERVICE_KEY_CUSTOM_COMPONENT = "component"
SERVICE_KEY_INSTALLED_VERSION = "installed_version"
SERVICE_KEY_SHOW_UNSTABLE = "show_unstable"
SERVICE_KEY_SUPPORTED_VERSIONS = "supported_versions"
SERVICE_KEY_VERSION = "version"
