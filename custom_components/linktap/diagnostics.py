"""Diagnostics support for the LinkTap integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import LinkTapConfigEntry

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, "gw_id", "dev_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LinkTapConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    devices = {
        dev_id: status.raw
        for dev_id, status in (coordinator.data or {}).items()
    }
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "gateway": {
            "version": coordinator.config.version,
            "vol_unit": coordinator.vol_unit,
            "device_count": len(coordinator.config.dev_ids),
            "push_healthy": coordinator.push_healthy,
        },
        "settings": coordinator.settings,
        "devices": async_redact_data(devices, TO_REDACT),
    }
