"""Runtime entry data for my custom manager stored in hass.data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import CALLBACK_TYPE


@dataclass
class RuntimeEntryData:
    """Store runtime data for my custom manager config entries."""

    entry_id: str
    update_unlistener: CALLBACK_TYPE | None = None
    customs_list: list[str] = field(default_factory=list)
