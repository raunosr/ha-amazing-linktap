"""Shared helpers for LinkTap tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.linktap.models import (
    LinkTapDeviceStatus,
    LinkTapGatewayConfig,
)

GW_ID = "1234ABCD5678EF90"

D1 = "d1"  # device with a flow meter
D2 = "g1"  # device without a flow meter (e.g. G1)

CONFIG = LinkTapGatewayConfig.from_payload(
    GW_ID,
    {
        "end_dev": [D1, D2],
        "dev_name": ["Front Garden", "Back Garden"],
        "vol_unit": "L",
        "ver": "G609",
    },
)

D1_STATUS = {
    "dev_id": D1,
    "is_rf_linked": True,
    "is_flm_plugin": True,
    "is_watering": False,
    "is_manual_mode": False,
    "is_paused": False,
    "signal": 90,
    "battery": 80,
    "total_duration": 900,
    "remain_duration": 0,
    "failsafe_duration": 1800,
    "speed": 2.5,
    "volume": 12.0,
    "volume_limit": 0,
    "plan_mode": 1,
    "plan_sn": 42,
}

D2_STATUS = {
    "dev_id": D2,
    "is_rf_linked": True,
    "is_flm_plugin": False,  # no flow meter
    "is_watering": False,
    "is_paused": False,
    "signal": 70,
    "battery": 55,
    "total_duration": 600,
    "remain_duration": 0,
    "speed": 0,
    "volume": 0,
    "volume_limit": 0,
    "plan_mode": 0,
}

_STATUS_BY_DEV = {D1: D1_STATUS, D2: D2_STATUS}


def build_mock_client() -> MagicMock:
    """Return a mock LinkTapClient with realistic async behaviour."""
    client = MagicMock()
    client.host = "1.2.3.4"
    client.async_get_gw_id = AsyncMock(return_value=GW_ID)
    client.async_get_config = AsyncMock(return_value=CONFIG)

    async def _status(gw_id, dev_id):
        return LinkTapDeviceStatus.from_payload(dict(_STATUS_BY_DEV[dev_id]))

    client.async_get_status = AsyncMock(side_effect=_status)
    client.async_start = AsyncMock(return_value=True)
    client.async_stop = AsyncMock(return_value=True)
    client.async_pause = AsyncMock(return_value=True)
    client.async_dismiss_alert = AsyncMock(return_value=True)
    return client
