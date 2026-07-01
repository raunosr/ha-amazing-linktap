"""Tests for LinkTap setup, entities, and the push endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.linktap.const import DOMAIN
from custom_components.linktap.push import LinkTapPushView

from .common import D1, D2, GW_ID, build_mock_client


def _mock_push_request(payload: dict) -> MagicMock:
    """Build a minimal aiohttp-style request whose json() returns payload."""
    request = MagicMock()
    request.json = AsyncMock(return_value=payload)
    return request


async def _setup(hass: HomeAssistant, client):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=GW_ID, data={CONF_HOST: "1.2.3.4"}
    )
    entry.add_to_hass(hass)
    with patch("custom_components.linktap.LinkTapClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_setup_creates_entities(hass: HomeAssistant) -> None:
    client = build_mock_client()
    entry = await _setup(hass, client)

    assert entry.state is ConfigEntryState.LOADED

    ent_reg = er.async_get(hass)
    entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    # 25 entities per device (1 valve + 1 switch + 3 numbers + 10 sensors
    # + 10 binary sensors) across 2 devices.
    assert len(entities) == 50

    valve_id = ent_reg.async_get_entity_id("valve", DOMAIN, f"{D1}_valve")
    assert valve_id is not None
    assert hass.states.get(valve_id).state == "closed"


async def test_g1_flow_sensors_unavailable(hass: HomeAssistant) -> None:
    """Devices without a flow meter report flow/volume as unavailable."""
    client = build_mock_client()
    await _setup(hass, client)

    ent_reg = er.async_get(hass)
    for key in ("speed", "volume", "volume_limit"):
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{D2}_{key}")
        assert entity_id is not None, key
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # The flow-equipped device reports real values.
    speed_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{D1}_speed")
    assert hass.states.get(speed_id).state == "2.5"


async def test_push_updates_state(hass: HomeAssistant) -> None:
    client = build_mock_client()
    await _setup(hass, client)
    ent_reg = er.async_get(hass)
    valve_id = ent_reg.async_get_entity_id("valve", DOMAIN, f"{D1}_valve")
    assert hass.states.get(valve_id).state == "closed"

    view = LinkTapPushView(hass)
    request = _mock_push_request(
        {"gw_id": GW_ID, "dev_id": D1, "is_watering": True, "is_flm_plugin": True}
    )
    resp = await view.post(request)
    assert resp.status == 200
    await hass.async_block_till_done()

    assert hass.states.get(valve_id).state == "open"


async def test_push_unknown_device_ignored(hass: HomeAssistant) -> None:
    client = build_mock_client()
    await _setup(hass, client)

    view = LinkTapPushView(hass)
    request = _mock_push_request({"gw_id": "OTHER", "dev_id": "nope"})
    resp = await view.post(request)
    assert resp.status == 202


async def test_valve_open_calls_start(hass: HomeAssistant) -> None:
    client = build_mock_client()
    await _setup(hass, client)
    ent_reg = er.async_get(hass)
    valve_id = ent_reg.async_get_entity_id("valve", DOMAIN, f"{D1}_valve")

    await hass.services.async_call(
        "valve", "open_valve", {"entity_id": valve_id}, blocking=True
    )
    # Default duration is 15 minutes -> 900 seconds.
    client.async_start.assert_awaited_once()
    args = client.async_start.await_args.args
    assert args[0] == GW_ID and args[1] == D1 and args[2] == 900


async def test_unload(hass: HomeAssistant) -> None:
    client = build_mock_client()
    entry = await _setup(hass, client)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
