"""Tests for the LinkTap config and options flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.components.zeroconf import ZeroconfServiceInfo

from custom_components.linktap.api import LinkTapAuthError, LinkTapConnectionError
from custom_components.linktap.const import DOMAIN

from .common import GW_ID, build_mock_client


async def test_user_flow_success(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.linktap.config_flow.LinkTapClient",
        return_value=build_mock_client(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "1.2.3.4"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"LinkTap {GW_ID}"
    assert result["result"].unique_id == GW_ID
    assert result["data"][CONF_HOST] == "1.2.3.4"


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    client = build_mock_client()
    client.async_get_gw_id.side_effect = LinkTapConnectionError("boom")
    with patch(
        "custom_components.linktap.config_flow.LinkTapClient", return_value=client
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "1.2.3.4"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_invalid_auth(hass: HomeAssistant) -> None:
    client = build_mock_client()
    client.async_get_gw_id.side_effect = LinkTapAuthError("nope")
    with patch(
        "custom_components.linktap.config_flow.LinkTapClient", return_value=client
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "1.2.3.4"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_duplicate_aborts(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    MockConfigEntry(
        domain=DOMAIN, unique_id=GW_ID, data={CONF_HOST: "1.2.3.4"}
    ).add_to_hass(hass)

    with patch(
        "custom_components.linktap.config_flow.LinkTapClient",
        return_value=build_mock_client(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "9.9.9.9"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_zeroconf_flow(hass: HomeAssistant) -> None:
    discovery = ZeroconfServiceInfo(
        ip_address="1.2.3.4",
        ip_addresses=["1.2.3.4"],
        hostname="linktapgw.local.",
        name=f"LinkTapGw_{GW_ID}._http._tcp.local.",
        port=80,
        type="_http._tcp.local.",
        properties={"ID": GW_ID, "vendor": "LinkTap"},
    )
    with patch(
        "custom_components.linktap.config_flow.LinkTapClient",
        return_value=build_mock_client(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "zeroconf_confirm"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == GW_ID


async def test_zeroconf_rejects_non_linktap(hass: HomeAssistant) -> None:
    discovery = ZeroconfServiceInfo(
        ip_address="1.2.3.4",
        ip_addresses=["1.2.3.4"],
        hostname="printer.local.",
        name="SomePrinter._http._tcp.local.",
        port=80,
        type="_http._tcp.local.",
        properties={},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_linktap"
