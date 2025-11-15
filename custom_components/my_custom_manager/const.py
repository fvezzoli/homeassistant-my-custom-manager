"""Constants for integration_blueprint."""

from logging import Logger, getLogger

from homeassistant.const import Platform

VERSION = "1.0.0"
LOGGER: Logger = getLogger(__package__)

DOMAIN = "my_custom_manager"

PLATFORMS = [Platform.UPDATE]

DEFAULT_POLLING_HOURS = 6

JSON_REPO_DESC = "repository.json"
JSON_CUSTOM = "custom.json"

CONF_BASE_URL = "base_url"
CONF_POLL_TIME = "polling_time"

MANIFEST_VERSION = "version"
MANIFEST_NAME = "name"
