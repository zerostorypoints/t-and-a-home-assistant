"""Diagnostics download."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import TAConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TAConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": {"host": entry.data.get("host"), "options": dict(entry.options)},
        "device": asdict(coordinator.device),
        "radio_favorites": list(coordinator.radio_favorites),
        "state": asdict(coordinator.data) if coordinator.data else None,
    }
