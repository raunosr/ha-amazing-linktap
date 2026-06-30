"""Sensor platform for LinkTap water timers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LinkTapConfigEntry
from .const import PLAN_MODES
from .coordinator import LinkTapCoordinator
from .entity import LinkTapEntity
from .models import LinkTapDeviceStatus


def _plan_mode_string(status: LinkTapDeviceStatus) -> str | None:
    if status.plan_mode is None:
        return None
    if 0 <= status.plan_mode < len(PLAN_MODES):
        return PLAN_MODES[status.plan_mode]
    return str(status.plan_mode)


@dataclass(frozen=True, kw_only=True)
class LinkTapSensorDescription(SensorEntityDescription):
    """Describes a LinkTap sensor."""

    value_fn: Callable[[LinkTapDeviceStatus], Any]
    flm_only: bool = False
    # Resolve unit from the gateway volume unit ("L"/"Gal") when set.
    unit_kind: str | None = None  # "volume" or "flow"


SENSORS: tuple[LinkTapSensorDescription, ...] = (
    LinkTapSensorDescription(
        key="signal",
        translation_key="signal",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
        value_fn=lambda s: s.signal,
    ),
    LinkTapSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.battery,
    ),
    LinkTapSensorDescription(
        key="total_duration",
        translation_key="total_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.total_duration,
    ),
    LinkTapSensorDescription(
        key="remain_duration",
        translation_key="remain_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.remain_duration,
    ),
    LinkTapSensorDescription(
        key="failsafe_duration",
        translation_key="failsafe_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.failsafe_duration,
    ),
    LinkTapSensorDescription(
        key="speed",
        translation_key="speed",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        unit_kind="flow",
        flm_only=True,
        icon="mdi:speedometer",
        value_fn=lambda s: s.speed,
    ),
    LinkTapSensorDescription(
        key="volume",
        translation_key="volume",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        unit_kind="volume",
        flm_only=True,
        icon="mdi:water",
        value_fn=lambda s: s.volume,
    ),
    LinkTapSensorDescription(
        key="volume_limit",
        translation_key="volume_limit",
        device_class=SensorDeviceClass.WATER,
        suggested_display_precision=1,
        unit_kind="volume",
        flm_only=True,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:water-outline",
        value_fn=lambda s: s.volume_limit,
    ),
    LinkTapSensorDescription(
        key="plan_mode",
        translation_key="plan_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-clock",
        value_fn=_plan_mode_string,
    ),
    LinkTapSensorDescription(
        key="plan_sn",
        translation_key="plan_sn",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:identifier",
        value_fn=lambda s: s.plan_sn,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LinkTapConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LinkTap sensors."""
    coordinator = entry.runtime_data.coordinator
    entities: list[LinkTapSensor] = []
    for dev_id in coordinator.config.dev_ids:
        for description in SENSORS:
            entities.append(LinkTapSensor(coordinator, dev_id, description))
    async_add_entities(entities)


class LinkTapSensor(LinkTapEntity, SensorEntity):
    """A read-only LinkTap sensor."""

    entity_description: LinkTapSensorDescription

    def __init__(
        self,
        coordinator: LinkTapCoordinator,
        dev_id: str,
        description: LinkTapSensorDescription,
    ) -> None:
        super().__init__(coordinator, dev_id)
        self.entity_description = description
        self._attr_unique_id = f"{dev_id}_{description.key}"

        gallons = str(coordinator.vol_unit).lower().startswith("g")
        if description.unit_kind == "volume":
            self._attr_native_unit_of_measurement = (
                UnitOfVolume.GALLONS if gallons else UnitOfVolume.LITERS
            )
        elif description.unit_kind == "flow":
            self._attr_native_unit_of_measurement = (
                UnitOfVolumeFlowRate.GALLONS_PER_MINUTE
                if gallons
                else UnitOfVolumeFlowRate.LITERS_PER_MINUTE
            )

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        # Devices without a flow meter (e.g. G1) report misleading zeros; mark
        # flow/volume sensors unavailable instead.
        if self.entity_description.flm_only:
            status = self.status
            return status is not None and status.has_flow_meter
        return True

    @property
    def native_value(self) -> Any:
        status = self.status
        if status is None:
            return None
        return self.entity_description.value_fn(status)
