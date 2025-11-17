"""Support for my custom manager domain data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self, cast

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .entry_data import RuntimeEntryData


@dataclass
class DomainData:
    """Define a class that stores global my custom manager data in hass.data[DOMAIN]."""

    _entry_datas: dict[str, RuntimeEntryData] = field(default_factory=dict)

    @property
    def is_empty_entry_data(self) -> bool:
        """Return if no more entry in the domain."""
        return len(self._entry_datas) == 0

    def get_entry_data(self, entry: ConfigEntry) -> RuntimeEntryData:
        """
        Return the runtime entry data associated with this config entry.

        Raises KeyError if the entry isn't loaded yet.
        """
        return self._entry_datas[entry.entry_id]

    def get_entry_data_by_id(self, entry_id: str) -> RuntimeEntryData:
        """
        Return the runtime entry data associated with this config entry.

        Raises KeyError if the entry isn't loaded yet.
        """
        return self._entry_datas[entry_id]

    def set_entry_data(self, entry: ConfigEntry, entry_data: RuntimeEntryData) -> None:
        """Set the runtime entry data associated with this config entry."""
        if entry.entry_id in self._entry_datas:
            exception_message = "Entry data for this entry is already set"
            raise ValueError(exception_message)
        self._entry_datas[entry.entry_id] = entry_data

    def pop_entry_data(self, entry: ConfigEntry) -> RuntimeEntryData:
        """Pop the runtime entry data instance associated with this config entry."""
        return self._entry_datas.pop(entry.entry_id)

    @classmethod
    def get(cls, hass: HomeAssistant) -> Self:
        """Get the global DomainData instance stored in hass.data."""
        # Don't use setdefault - this is a hot code path
        if DOMAIN in hass.data:
            return cast("Self", hass.data[DOMAIN])
        ret = hass.data[DOMAIN] = cls()
        return ret
