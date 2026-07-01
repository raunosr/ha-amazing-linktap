"""Number inputs that control LinkTap watering (consumed by the valve/switch)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import EntityCategory, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LinkTapConfigEntry
from .api import LinkTapError
from .const import (
    CONFIG_TAG_DURATION_LIMIT,
    CONFIG_TAG_VOLUME_LIMIT,
    DEFAULT_DURATION_LIMIT_MIN,
    DEFAULT_DURATION_MIN,
    DEFAULT_PAUSE_HOURS,
    DEFAULT_VOLUME_LIMIT,
    MAX_DURATION_LIMIT_MIN,
    MAX_DURATION_MIN,
    MAX_PAUSE_HOURS,
    VOL_UNIT_GALLONS,
)
from .coordinator import LinkTapCoordinator
from .entity import LinkTapEntity


@dataclass(frozen=True, kw_only=True)
class LinkTapNumberDescription(NumberEntityDescription):
    """Describes a LinkTap watering input number."""

    setting_key: str
    default: float
    # When set, changing the number also pushes a persistent config value to the
    # gateway (cmd 17) using this tag. ``config_scale`` converts the displayed
    # value to the API unit (e.g. minutes -> seconds).
    config_tag: str | None = None
    config_scale: float = 1.0


NUMBERS: tuple[LinkTapNumberDescription, ...] = (
    LinkTapNumberDescription(
        key="watering_duration",
        translation_key="watering_duration",
        setting_key="duration_min",
        default=DEFAULT_DURATION_MIN,
        native_min_value=1,
        native_max_value=MAX_DURATION_MIN,
        native_step=1,
        # UnitOfTime.MINUTES == "min"; "m" would mean months in Home Assistant.
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer",
    ),
    LinkTapNumberDescription(
        key="volume_limit",
        translation_key="volume_limit",
        setting_key="volume_limit",
        default=DEFAULT_VOLUME_LIMIT,
        native_min_value=0,
        native_max_value=10000,
        native_step=1,
        icon="mdi:water",
        # Pushed to the gateway so the diagnostic "Volume limit" sensor reflects it.
        config_tag=CONFIG_TAG_VOLUME_LIMIT,
    ),
    LinkTapNumberDescription(
        key="duration_limit",
        translation_key="duration_limit",
        setting_key="duration_limit_min",
        default=DEFAULT_DURATION_LIMIT_MIN,
        native_min_value=0,
        native_max_value=MAX_DURATION_LIMIT_MIN,
        native_step=1,
        # UnitOfTime.MINUTES == "min"; "m" would mean months in Home Assistant.
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-alert",
        # Persistent per-device duration limit (cmd 17 total_duration, in seconds).
        config_tag=CONFIG_TAG_DURATION_LIMIT,
        config_scale=60,
    ),
    LinkTapNumberDescription(
        key="pause_duration",
        translation_key="pause_duration",
        setting_key="pause_hours",
        default=DEFAULT_PAUSE_HOURS,
        native_min_value=1,
        native_max_value=MAX_PAUSE_HOURS,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:pause-circle",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LinkTapConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LinkTap number inputs."""
    coordinator = entry.runtime_data.coordinator
    entities: list[LinkTapNumber] = []
    for dev_id in coordinator.config.dev_ids:
        for description in NUMBERS:
            entities.append(LinkTapNumber(coordinator, dev_id, description))
    async_add_entities(entities)


class LinkTapNumber(LinkTapEntity, RestoreNumber):
    """A persisted watering input stored on the coordinator."""

    entity_description: LinkTapNumberDescription
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: LinkTapCoordinator,
        dev_id: str,
        description: LinkTapNumberDescription,
    ) -> None:
        super().__init__(coordinator, dev_id)
        self.entity_description = description
        self._attr_unique_id = f"{dev_id}_{description.key}"
        # The volume unit follows the gateway's reported unit (L / Gal).
        if description.key == "volume_limit":
            self._attr_native_unit_of_measurement = (
                UnitOfVolume.GALLONS
                if str(coordinator.vol_unit).lower().startswith("g")
                else UnitOfVolume.LITERS
            )

    @property
    def available(self) -> bool:
        """Inputs are local settings, available whenever the gateway responds."""
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> float:
        return self.coordinator.get_setting(
            self._dev_id, self.entity_description.setting_key
        )

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.set_setting(
            self._dev_id, self.entity_description.setting_key, value
        )
        self.async_write_ha_state()
        await self._async_push_config(value)

    async def _async_push_config(self, value: float) -> None:
        """Push a persistent config value to the gateway (cmd 17), if configured."""
        tag = self.entity_description.config_tag
        if tag is None:
            return
        # Volume limits only apply to devices with a flow meter; pushing one to a
        # meter-less device (e.g. G1) is meaningless, so skip it.
        if tag == CONFIG_TAG_VOLUME_LIMIT:
            status = self.coordinator.status_for(self._dev_id)
            if status is not None and not status.has_flow_meter:
                return
        api_value = int(value * self.entity_description.config_scale)
        try:
            await self.coordinator.client.async_set_config(
                self.coordinator.gw_id, self._dev_id, tag, api_value
            )
        except LinkTapError as err:
            raise HomeAssistantError(
                f"Failed to set {self.entity_description.key} on the LinkTap "
                f"gateway: {err}"
            ) from err
        # Refresh so the gateway re-reports the value (e.g. the diagnostic sensor).
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self.coordinator.set_setting(
                self._dev_id,
                self.entity_description.setting_key,
                last.native_value,
            )
            self.async_write_ha_state()
