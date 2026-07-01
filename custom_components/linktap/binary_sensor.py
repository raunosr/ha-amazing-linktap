"""Binary sensor platform for LinkTap water timers (status flags and alerts)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LinkTapConfigEntry
from .const import ALERT_ALL, ALERT_LOOKUP
from .coordinator import LinkTapCoordinator
from .entity import LinkTapEntity
from .models import LinkTapDeviceStatus

SERVICE_DISMISS_ALERT = "dismiss_alert"
SERVICE_DISMISS_ALERTS = "dismiss_alerts"


@dataclass(frozen=True, kw_only=True)
class LinkTapBinaryDescription(BinarySensorEntityDescription):
    """Describes a LinkTap binary sensor."""

    value_fn: Callable[[LinkTapDeviceStatus], bool | None]
    # Alert key matching ALERT_LOOKUP (e.g. "fall"); None for non-alert flags.
    alert_key: str | None = None


BINARY_SENSORS: tuple[LinkTapBinaryDescription, ...] = (
    LinkTapBinaryDescription(
        key="is_watering",
        translation_key="is_watering",
        icon="mdi:water",
        value_fn=lambda s: s.is_watering,
    ),
    LinkTapBinaryDescription(
        key="is_manual_mode",
        translation_key="is_manual_mode",
        icon="mdi:gesture-tap-button",
        value_fn=lambda s: s.is_manual_mode,
    ),
    LinkTapBinaryDescription(
        key="is_rf_linked",
        translation_key="is_rf_linked",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.is_rf_linked,
    ),
    LinkTapBinaryDescription(
        key="is_flm_plugin",
        translation_key="is_flm_plugin",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.is_flm_plugin,
    ),
    LinkTapBinaryDescription(
        key="is_paused",
        translation_key="is_paused",
        icon="mdi:pause-circle",
        value_fn=lambda s: s.is_paused,
    ),
    LinkTapBinaryDescription(
        key="alert_fall",
        translation_key="alert_fall",
        device_class=BinarySensorDeviceClass.PROBLEM,
        alert_key="fall",
        value_fn=lambda s: s.is_fall,
    ),
    LinkTapBinaryDescription(
        key="alert_cutoff",
        translation_key="alert_cutoff",
        device_class=BinarySensorDeviceClass.PROBLEM,
        alert_key="cutoff",
        value_fn=lambda s: s.is_cutoff,
    ),
    LinkTapBinaryDescription(
        key="alert_leak",
        translation_key="alert_leak",
        device_class=BinarySensorDeviceClass.PROBLEM,
        alert_key="high_flow",
        value_fn=lambda s: s.is_leak,
    ),
    LinkTapBinaryDescription(
        key="alert_clog",
        translation_key="alert_clog",
        device_class=BinarySensorDeviceClass.PROBLEM,
        alert_key="low_flow",
        value_fn=lambda s: s.is_clog,
    ),
    LinkTapBinaryDescription(
        key="alert_broken",
        translation_key="alert_broken",
        device_class=BinarySensorDeviceClass.PROBLEM,
        alert_key="shutdown",
        value_fn=lambda s: s.is_broken,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LinkTapConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LinkTap binary sensors."""
    coordinator = entry.runtime_data.coordinator
    entities: list[LinkTapBinarySensor] = []
    for dev_id in coordinator.config.dev_ids:
        for description in BINARY_SENSORS:
            entities.append(LinkTapBinarySensor(coordinator, dev_id, description))
    async_add_entities(entities)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_DISMISS_ALERT, {}, "async_dismiss_alert"
    )
    platform.async_register_entity_service(
        SERVICE_DISMISS_ALERTS, {}, "async_dismiss_alerts"
    )


class LinkTapBinarySensor(LinkTapEntity, BinarySensorEntity):
    """A LinkTap status flag or alert."""

    entity_description: LinkTapBinaryDescription

    def __init__(
        self,
        coordinator: LinkTapCoordinator,
        dev_id: str,
        description: LinkTapBinaryDescription,
    ) -> None:
        super().__init__(coordinator, dev_id)
        self.entity_description = description
        self._attr_unique_id = f"{dev_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        status = self.status
        if status is None:
            return None
        return self.entity_description.value_fn(status)

    async def async_dismiss_alert(self) -> None:
        """Dismiss the alert this entity represents (no-op for status flags)."""
        alert_key = self.entity_description.alert_key
        if alert_key is None:
            return
        await self.coordinator.client.async_dismiss_alert(
            self.coordinator.gw_id,
            self._dev_id,
            ALERT_LOOKUP.get(alert_key, ALERT_ALL),
        )
        await self.coordinator.async_request_refresh()

    async def async_dismiss_alerts(self) -> None:
        """Dismiss all alerts for this device."""
        await self.coordinator.client.async_dismiss_alert(
            self.coordinator.gw_id, self._dev_id, ALERT_ALL
        )
        await self.coordinator.async_request_refresh()
