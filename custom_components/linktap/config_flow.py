"""Config and options flow for the LinkTap integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import LinkTapAuthError, LinkTapClient, LinkTapError
from .const import (
    DEFAULT_ACTIVE_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
    OPT_ACTIVE_POLL_INTERVAL,
    OPT_POLL_INTERVAL,
    OPT_REQUEST_TIMEOUT,
    OPT_VOL_UNIT,
    VOL_UNIT_GALLONS,
    VOL_UNIT_LITERS,
)

if TYPE_CHECKING:
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

_LOGGER = logging.getLogger(__name__)

_ZEROCONF_PREFIX = "LinkTapGw_"

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): str,
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): str,
    }
)


class LinkTapConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LinkTap."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._gw_id: str | None = None

    async def _async_validate(
        self, host: str, username: str | None, password: str | None
    ) -> str:
        """Connect to the gateway and return its 16-hex gateway id."""
        client = LinkTapClient(self.hass, host, username, password)
        gw_id = await client.async_get_gw_id()
        # Confirm the device list is reachable too (firmware/permission check).
        await client.async_get_config(gw_id)
        return gw_id

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup by IP/hostname."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            try:
                gw_id = await self._async_validate(
                    host,
                    user_input.get(CONF_USERNAME),
                    user_input.get(CONF_PASSWORD),
                )
            except LinkTapAuthError:
                errors["base"] = "invalid_auth"
            except LinkTapError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - surface unexpected issues to the user
                _LOGGER.exception("Unexpected error validating LinkTap gateway")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(gw_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=f"Amazing LinkTap {gw_id}", data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_zeroconf(
        self, discovery_info: "ZeroconfServiceInfo"
    ) -> ConfigFlowResult:
        """Handle a gateway discovered via mDNS (PDF section 5)."""
        name = discovery_info.name or ""
        if not name.startswith(_ZEROCONF_PREFIX):
            return self.async_abort(reason="not_linktap")

        properties = discovery_info.properties
        gw_id = properties.get("ID") or properties.get("id")
        if not gw_id:
            # Fall back to the service name: LinkTapGw_<id>._http._tcp.local.
            gw_id = name.split(".", 1)[0].removeprefix(_ZEROCONF_PREFIX)

        host = discovery_info.host
        await self.async_set_unique_id(gw_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._host = host
        self._gw_id = gw_id
        self.context["title_placeholders"] = {"name": f"Amazing LinkTap {gw_id}"}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding a discovered gateway."""
        errors: dict[str, str] = {}
        assert self._host is not None
        if user_input is not None:
            try:
                gw_id = await self._async_validate(self._host, None, None)
            except LinkTapAuthError:
                # Access control is enabled; collect credentials manually.
                return await self.async_step_user()
            except LinkTapError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Amazing LinkTap {gw_id}", data={CONF_HOST: self._host}
                )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"gw_id": self._gw_id, "host": self._host},
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when the gateway rejects credentials."""
        self._host = entry_data[CONF_HOST]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect new credentials and update the entry."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        assert self._host is not None
        if user_input is not None:
            try:
                await self._async_validate(
                    self._host,
                    user_input.get(CONF_USERNAME),
                    user_input.get(CONF_PASSWORD),
                )
            except LinkTapAuthError:
                errors["base"] = "invalid_auth"
            except LinkTapError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"host": self._host},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> "LinkTapOptionsFlow":
        return LinkTapOptionsFlow()


class LinkTapOptionsFlow(OptionsFlow):
    """Handle LinkTap options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # Drop empty optional values so defaults apply cleanly.
            cleaned = {k: v for k, v in user_input.items() if v not in (None, "")}
            return self.async_create_entry(title="", data=cleaned)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    OPT_POLL_INTERVAL,
                    default=opts.get(
                        OPT_POLL_INTERVAL, DEFAULT_POLL_INTERVAL.total_seconds()
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=5, max=600, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    OPT_ACTIVE_POLL_INTERVAL,
                    default=opts.get(
                        OPT_ACTIVE_POLL_INTERVAL,
                        DEFAULT_ACTIVE_POLL_INTERVAL.total_seconds(),
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=5, max=120, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    OPT_REQUEST_TIMEOUT,
                    default=opts.get(
                        OPT_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=2, max=60, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    OPT_VOL_UNIT,
                    default=opts.get(OPT_VOL_UNIT, ""),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=["", VOL_UNIT_LITERS, VOL_UNIT_GALLONS],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
