"""DataUpdateCoordinator for a LinkTap gateway and its water timers."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import LinkTapClient, LinkTapError
from .const import (
    DEFAULT_ACTIVE_POLL_INTERVAL,
    DEFAULT_DURATION_LIMIT_MIN,
    DEFAULT_DURATION_MIN,
    DEFAULT_PAUSE_HOURS,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_VOLUME_LIMIT,
    DOMAIN,
    PUSH_WATCHDOG,
)
from .models import LinkTapDeviceStatus, LinkTapGatewayConfig

_LOGGER = logging.getLogger(__name__)


class LinkTapCoordinator(DataUpdateCoordinator[dict[str, LinkTapDeviceStatus]]):
    """Coordinates status for all tap outputs behind a single gateway.

    Push updates (PDF section 4.1) are primary; polling is a fallback that runs
    relaxed while pushes arrive and speeds up when the push watchdog trips.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: LinkTapClient,
        config: LinkTapGatewayConfig,
        poll_interval: timedelta = DEFAULT_POLL_INTERVAL,
        active_poll_interval: timedelta = DEFAULT_ACTIVE_POLL_INTERVAL,
    ) -> None:
        self.client = client
        self.config = config
        self.gw_id = config.gw_id
        self.vol_unit = config.vol_unit
        self._poll_interval = poll_interval
        self._active_poll_interval = active_poll_interval
        self._last_push: datetime | None = None
        # User-controlled watering inputs per device, consumed by the valve and
        # pause switch. Seeded with defaults; number entities update these and
        # restore their persisted values on startup.
        self.settings: dict[str, dict[str, float]] = {
            dev_id: {
                "duration_min": DEFAULT_DURATION_MIN,
                "volume_limit": DEFAULT_VOLUME_LIMIT,
                "pause_hours": DEFAULT_PAUSE_HOURS,
                "duration_limit_min": DEFAULT_DURATION_LIMIT_MIN,
            }
            for dev_id in config.dev_ids
        }
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {config.gw_id}",
            update_interval=active_poll_interval,
        )

    @property
    def push_healthy(self) -> bool:
        """Whether a push was received recently enough to trust the channel."""
        if self._last_push is None:
            return False
        return dt_util.utcnow() - self._last_push < PUSH_WATCHDOG

    def _next_interval(self) -> timedelta:
        """Relaxed interval while push is healthy, active otherwise (jittered)."""
        if self.push_healthy:
            return self._poll_interval
        jitter = timedelta(milliseconds=random.randint(0, 1500))
        return self._active_poll_interval + jitter

    async def _async_update_data(self) -> dict[str, LinkTapDeviceStatus]:
        """Poll every device behind the gateway."""
        try:
            statuses = await asyncio.gather(
                *(
                    self.client.async_get_status(self.gw_id, dev_id)
                    for dev_id in self.config.dev_ids
                )
            )
        except LinkTapError as err:
            raise UpdateFailed(
                f"Error communicating with LinkTap gateway {self.gw_id}: {err}"
            ) from err

        self.update_interval = self._next_interval()
        return {status.dev_id or dev_id: status
                for dev_id, status in zip(self.config.dev_ids, statuses)}

    @callback
    def async_handle_push(self, payload: dict[str, Any]) -> None:
        """Merge a pushed status payload and refresh affected entities."""
        status = LinkTapDeviceStatus.from_payload(payload)
        if not status.dev_id:
            _LOGGER.debug("Ignoring push payload without dev_id: %s", payload)
            return
        if status.dev_id not in self.config.dev_ids:
            _LOGGER.debug(
                "Ignoring push for unknown device %s on gateway %s",
                status.dev_id,
                self.gw_id,
            )
            return

        self._last_push = dt_util.utcnow()
        data = dict(self.data or {})
        data[status.dev_id] = status
        # Push is healthy: relax polling cadence on the next cycle.
        self.update_interval = self._poll_interval
        self.async_set_updated_data(data)

    def status_for(self, dev_id: str) -> LinkTapDeviceStatus | None:
        """Return the latest status for a device id, if available."""
        if not self.data:
            return None
        return self.data.get(dev_id)

    def get_setting(self, dev_id: str, key: str) -> float:
        """Return a user-controlled watering input for a device."""
        return self.settings.get(dev_id, {}).get(key, 0)

    def set_setting(self, dev_id: str, key: str, value: float) -> None:
        """Update a user-controlled watering input for a device."""
        self.settings.setdefault(dev_id, {})[key] = value
