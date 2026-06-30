"""Shared entity base for LinkTap tap-output devices."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import LinkTapCoordinator
from .models import LinkTapDeviceStatus


class LinkTapEntity(CoordinatorEntity[LinkTapCoordinator]):
    """Base entity for a single LinkTap water timer (tap output)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LinkTapCoordinator, dev_id: str) -> None:
        super().__init__(coordinator)
        self._dev_id = dev_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev_id)},
            name=coordinator.config.name_for(dev_id),
            manufacturer=MANUFACTURER,
            model=dev_id,
            via_device=(DOMAIN, coordinator.gw_id),
            configuration_url=f"http://{coordinator.client.host}/",
        )

    @property
    def status(self) -> LinkTapDeviceStatus | None:
        """Latest parsed status for this device, if available."""
        return self.coordinator.status_for(self._dev_id)

    @property
    def available(self) -> bool:
        """Available while the coordinator has data for this device."""
        return super().available and self.status is not None
