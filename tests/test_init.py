"""Tests for LinkTap setup, entities, and the push endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

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
    # 27 entities per device (1 valve + 1 switch + 4 numbers + 11 sensors
    # + 10 binary sensors) across 2 devices.
    assert len(entities) == 54

    valve_id = ent_reg.async_get_entity_id("valve", DOMAIN, f"{D1}_valve")
    assert valve_id is not None
    assert hass.states.get(valve_id).state == "closed"


async def test_volume_split_from_total(hass: HomeAssistant) -> None:
    """Volume stays a plain current-cycle reading; Total volume is cumulative."""
    client = build_mock_client()
    await _setup(hass, client)
    ent_reg = er.async_get(hass)

    volume_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{D1}_volume")
    volume = hass.states.get(volume_id)
    # Original per-cycle value preserved, not overridden with the running total.
    assert volume.state == "12.0"
    # No state_class -> not treated as a cumulative long-term statistic.
    assert volume.attributes.get("state_class") is None

    total_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{D1}_volume_total")
    total = hass.states.get(total_id)
    assert total.attributes.get("state_class") == "total_increasing"


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


async def test_valve_open_is_optimistic(hass: HomeAssistant) -> None:
    """Opening keeps the valve 'open' even while the poll still reports idle."""
    client = build_mock_client()
    await _setup(hass, client)
    ent_reg = er.async_get(hass)
    valve_id = ent_reg.async_get_entity_id("valve", DOMAIN, f"{D1}_valve")
    assert hass.states.get(valve_id).state == "closed"

    # The mock gateway still reports is_watering=False after the command (the
    # physical valve has not actuated yet). Optimistic state must hold "open".
    await hass.services.async_call(
        "valve", "open_valve", {"entity_id": valve_id}, blocking=True
    )
    client.async_start.assert_awaited_once()
    assert hass.states.get(valve_id).state == "open"


async def test_volume_limit_number_pushes_config(hass: HomeAssistant) -> None:
    """Changing the Volume limit number pushes it to the gateway (cmd 17)."""
    client = build_mock_client()
    await _setup(hass, client)
    ent_reg = er.async_get(hass)
    number_id = ent_reg.async_get_entity_id("number", DOMAIN, f"{D1}_volume_limit")
    assert number_id is not None

    await hass.services.async_call(
        "number", "set_value", {"entity_id": number_id, "value": 5}, blocking=True
    )
    client.async_set_config.assert_awaited_once()
    args = client.async_set_config.await_args.args
    assert args[0] == GW_ID and args[1] == D1
    assert args[2] == "volume_limit" and args[3] == 5


async def test_volume_limit_skipped_without_flow_meter(hass: HomeAssistant) -> None:
    """A meter-less device (G1) does not push a volume limit to the gateway."""
    client = build_mock_client()
    await _setup(hass, client)
    ent_reg = er.async_get(hass)
    number_id = ent_reg.async_get_entity_id("number", DOMAIN, f"{D2}_volume_limit")
    assert number_id is not None

    await hass.services.async_call(
        "number", "set_value", {"entity_id": number_id, "value": 5}, blocking=True
    )
    client.async_set_config.assert_not_awaited()


async def test_duration_limit_number_pushes_seconds(hass: HomeAssistant) -> None:
    """The Duration limit number pushes total_duration in seconds (cmd 17)."""
    client = build_mock_client()
    await _setup(hass, client)
    ent_reg = er.async_get(hass)
    number_id = ent_reg.async_get_entity_id("number", DOMAIN, f"{D1}_duration_limit")
    assert number_id is not None

    await hass.services.async_call(
        "number", "set_value", {"entity_id": number_id, "value": 30}, blocking=True
    )
    client.async_set_config.assert_awaited_once()
    args = client.async_set_config.await_args.args
    assert args[0] == GW_ID and args[1] == D1
    # 30 minutes -> 1800 seconds.
    assert args[2] == "total_duration" and args[3] == 1800


async def test_total_volume_accumulates(hass: HomeAssistant) -> None:
    """The total-volume sensor integrates per-cycle volume across cycles."""
    client = build_mock_client()
    await _setup(hass, client)
    ent_reg = er.async_get(hass)
    total_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{D1}_volume_total")
    assert total_id is not None
    # First sample only sets the baseline (starting volume 12.0), adds nothing.
    assert hass.states.get(total_id).state == "0.0"

    view = LinkTapPushView(hass)
    # Volume grows within the same cycle: 12 -> 20 adds 8.
    resp = await view.post(
        _mock_push_request(
            {
                "gw_id": GW_ID,
                "dev_id": D1,
                "is_flm_plugin": True,
                "is_watering": True,
                "volume": 20.0,
            }
        )
    )
    assert resp.status == 200
    await hass.async_block_till_done()
    assert hass.states.get(total_id).state == "8.0"

    # A new cycle resets the per-cycle volume (20 -> 3), so all 3 are added.
    resp = await view.post(
        _mock_push_request(
            {
                "gw_id": GW_ID,
                "dev_id": D1,
                "is_flm_plugin": True,
                "is_watering": True,
                "volume": 3.0,
            }
        )
    )
    assert resp.status == 200
    await hass.async_block_till_done()
    assert hass.states.get(total_id).state == "11.0"


async def test_total_volume_restores(hass: HomeAssistant) -> None:
    """The running total is restored across restarts and keeps counting."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State("sensor.front_garden_total_volume", "5.0"),
                {"native_value": 5.0, "native_unit_of_measurement": "L"},
            ),
        ),
    )
    client = build_mock_client()
    await _setup(hass, client)
    ent_reg = er.async_get(hass)
    total_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{D1}_volume_total")
    assert total_id == "sensor.front_garden_total_volume"
    # Restored total, and the first post-restore sample only re-baselines.
    assert hass.states.get(total_id).state == "5.0"

    view = LinkTapPushView(hass)
    resp = await view.post(
        _mock_push_request(
            {
                "gw_id": GW_ID,
                "dev_id": D1,
                "is_flm_plugin": True,
                "is_watering": True,
                "volume": 20.0,
            }
        )
    )
    assert resp.status == 200
    await hass.async_block_till_done()
    assert hass.states.get(total_id).state == "13.0"


async def test_g1_total_volume_unavailable(hass: HomeAssistant) -> None:
    """Devices without a flow meter report total volume as unavailable."""
    client = build_mock_client()
    await _setup(hass, client)
    ent_reg = er.async_get(hass)
    total_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{D2}_volume_total")
    assert total_id is not None
    assert hass.states.get(total_id).state == STATE_UNAVAILABLE


async def test_unload(hass: HomeAssistant) -> None:
    client = build_mock_client()
    entry = await _setup(hass, client)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
