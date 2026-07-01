"""Valve platform for LinkTap water control."""

from __future__ import annotations

import time

import voluptuous as vol
from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LinkTapConfigEntry
from .const import OPTIMISTIC_WINDOW
from .coordinator import LinkTapCoordinator
from .entity import LinkTapEntity

SERVICE_START_WATERING = "start_watering"
SERVICE_PAUSE = "pause"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LinkTapConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LinkTap valves."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        LinkTapValve(coordinator, dev_id) for dev_id in coordinator.config.dev_ids
    )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_START_WATERING,
        {
            vol.Required("seconds"): cv.positive_int,
            vol.Optional("volume"): vol.Coerce(float),
        },
        "async_service_start_watering",
    )
    platform.async_register_entity_service(
        SERVICE_PAUSE,
        {vol.Required("hours"): cv.positive_int},
        "async_service_pause",
    )


class LinkTapValve(LinkTapEntity, ValveEntity):
    """Water control valve for a single tap output."""

    _attr_device_class = ValveDeviceClass.WATER
    _attr_supported_features = (
        ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
    )
    _attr_reports_position = False
    _attr_name = None  # primary feature: use the device name

    def __init__(self, coordinator: LinkTapCoordinator, dev_id: str) -> None:
        super().__init__(coordinator, dev_id)
        self._attr_unique_id = f"{dev_id}_valve"
        # Optimistic state bridges the delay between issuing an open/close
        # command and the gateway reporting that it started/stopped watering.
        self._optimistic_is_closed: bool | None = None
        self._optimistic_expiry: float = 0.0

    def _actual_is_closed(self) -> bool | None:
        status = self.status
        if status is None or status.is_watering is None:
            return None
        return not status.is_watering

    @property
    def is_closed(self) -> bool | None:
        actual = self._actual_is_closed()
        optimistic = self._optimistic_is_closed
        if optimistic is not None:
            if actual is not None and actual == optimistic:
                # Gateway confirmed the requested state; drop the override.
                self._optimistic_is_closed = None
                return actual
            if time.monotonic() < self._optimistic_expiry:
                return optimistic
            # Window elapsed without confirmation; fall back to reality.
            self._optimistic_is_closed = None
        return actual

    def _set_optimistic(self, is_closed: bool) -> None:
        """Assume the requested state until the gateway confirms it."""
        self._optimistic_is_closed = is_closed
        self._optimistic_expiry = time.monotonic() + OPTIMISTIC_WINDOW
        self.async_write_ha_state()

    async def async_open_valve(self) -> None:
        """Start watering using the configured duration and volume limit."""
        duration_min = self.coordinator.get_setting(self._dev_id, "duration_min")
        volume_limit = self.coordinator.get_setting(self._dev_id, "volume_limit")
        seconds = int(duration_min * 60)
        status = self.status
        # Volume limits only apply to devices with a flow meter.
        volume = (
            volume_limit
            if volume_limit and status and status.has_flow_meter
            else None
        )
        await self.coordinator.client.async_start(
            self.coordinator.gw_id, self._dev_id, seconds, volume
        )
        self._set_optimistic(False)
        await self.coordinator.async_request_refresh()

    async def async_close_valve(self) -> None:
        await self.coordinator.client.async_stop(
            self.coordinator.gw_id, self._dev_id
        )
        self._set_optimistic(True)
        await self.coordinator.async_request_refresh()

    async def async_service_start_watering(
        self, seconds: int, volume: float | None = None
    ) -> None:
        status = self.status
        if volume and (status is None or not status.has_flow_meter):
            volume = None
        await self.coordinator.client.async_start(
            self.coordinator.gw_id, self._dev_id, seconds, volume
        )
        self._set_optimistic(False)
        await self.coordinator.async_request_refresh()

    async def async_service_pause(self, hours: int) -> None:
        await self.coordinator.client.async_pause(
            self.coordinator.gw_id, self._dev_id, hours
        )
        await self.coordinator.async_request_refresh()
