"""Switch platform: pause/unpause a LinkTap watering plan."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LinkTapConfigEntry
from .coordinator import LinkTapCoordinator
from .entity import LinkTapEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LinkTapConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LinkTap pause switches."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        LinkTapPauseSwitch(coordinator, dev_id)
        for dev_id in coordinator.config.dev_ids
    )


class LinkTapPauseSwitch(LinkTapEntity, SwitchEntity):
    """Pauses the watering plan for the configured number of hours."""

    _attr_translation_key = "pause"
    _attr_icon = "mdi:pause-circle"

    def __init__(self, coordinator: LinkTapCoordinator, dev_id: str) -> None:
        super().__init__(coordinator, dev_id)
        self._attr_unique_id = f"{dev_id}_pause"

    @property
    def is_on(self) -> bool | None:
        status = self.status
        if status is None:
            return None
        return status.is_paused

    async def async_turn_on(self, **kwargs: Any) -> None:
        hours = int(self.coordinator.get_setting(self._dev_id, "pause_hours"))
        await self.coordinator.client.async_pause(
            self.coordinator.gw_id, self._dev_id, hours
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_pause(
            self.coordinator.gw_id, self._dev_id, 0
        )
        await self.coordinator.async_request_refresh()
