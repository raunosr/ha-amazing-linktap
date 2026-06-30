"""Low-level client for the LinkTap gateway local HTTP API (``/api.shtml``)."""

from __future__ import annotations

import asyncio
import json
import logging
from json import JSONDecodeError
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ALERT_ALL,
    CMD_CONFIG,
    CMD_DISMISS_ALERT,
    CMD_PAUSE,
    CMD_START,
    CMD_STATUS,
    CMD_STOP,
    DEFAULT_REQUEST_TIMEOUT,
    RETRY_ATTEMPTS,
)
from .models import LinkTapDeviceStatus, LinkTapGatewayConfig

_LOGGER = logging.getLogger(__name__)


class LinkTapError(Exception):
    """Base error for the LinkTap client."""


class LinkTapConnectionError(LinkTapError):
    """Raised when the gateway cannot be reached or returns a transient error."""


class LinkTapAuthError(LinkTapError):
    """Raised when the gateway rejects the credentials (access control enabled)."""


class LinkTapResponseError(LinkTapError):
    """Raised when the gateway returns a well-formed but unsuccessful response."""


def _extract_json(text: str) -> dict[str, Any]:
    """Parse a gateway reply that may be wrapped in HTML (PDF section 4.2).

    By default the gateway wraps its JSON reply in an HTML document, e.g.
    ``<!--#RET-->{"cmd":3,...}``. We locate the JSON object directly rather
    than stripping tags, which is robust to both wrapped and plain replies.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise JSONDecodeError("No JSON object in response", text, 0)
    return json.loads(text[start : end + 1])


class LinkTapClient:
    """Async client wrapping the gateway's ``api.shtml`` JSON command API."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        username: str | None = None,
        password: str | None = None,
        timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self._hass = hass
        self._host = host
        self._timeout = timeout
        self._auth: aiohttp.BasicAuth | None = (
            aiohttp.BasicAuth(username, password or "")
            if username
            else None
        )

    @property
    def host(self) -> str:
        return self._host

    @host.setter
    def host(self, value: str) -> None:
        self._host = value

    async def _request(self, data: dict[str, Any]) -> dict[str, Any]:
        """Send a single command, retrying transient failures with backoff."""
        url = f"http://{self._host}/api.shtml"
        headers = {"Content-Type": "application/json; charset=UTF-8"}
        session = async_get_clientsession(self._hass)

        last_err: Exception | None = None
        for attempt in range(RETRY_ATTEMPTS):
            try:
                async with asyncio.timeout(self._timeout):
                    async with session.post(
                        url, json=data, headers=headers, auth=self._auth
                    ) as resp:
                        if resp.status in (401, 403):
                            raise LinkTapAuthError(
                                f"Gateway rejected credentials (HTTP {resp.status})"
                            )
                        text = await resp.text()
                        # The gateway intermittently returns 404 for a valid
                        # request; treat it as transient and retry.
                        if resp.status == 404:
                            raise LinkTapConnectionError("Transient HTTP 404")
                        if resp.status >= 400:
                            raise LinkTapConnectionError(
                                f"Gateway returned HTTP {resp.status}"
                            )
                return _extract_json(text)
            except LinkTapAuthError:
                raise
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                JSONDecodeError,
                LinkTapConnectionError,
            ) as err:
                last_err = err
                if attempt + 1 >= RETRY_ATTEMPTS:
                    break
                # Exponential backoff: 1s, 2s, capped at 4s.
                await asyncio.sleep(min(2**attempt, 4))

        raise LinkTapConnectionError(
            f"Failed to reach LinkTap gateway at {self._host}: {last_err}"
        ) from last_err

    @staticmethod
    def _check_ret(response: dict[str, Any]) -> bool:
        """Return True when the gateway reports success (``ret == 0``)."""
        ret = response.get("ret")
        if ret is None:
            # Status/config replies have no ret field; presence implies success.
            return True
        if ret != 0:
            raise LinkTapResponseError(f"Gateway returned ret={ret}")
        return True

    # --- High-level commands ---

    async def async_get_gw_id(self) -> str:
        """Discover the gateway id by sending a status command with no ids.

        The gateway echoes its ``gw_id`` (16-hex) which is used as the config
        entry unique id (never the IP).
        """
        response = await self._request({"cmd": CMD_STATUS})
        gw_id = response.get("gw_id")
        if not gw_id:
            raise LinkTapResponseError("Gateway did not return a gw_id")
        return str(gw_id)

    async def async_get_config(self, gw_id: str) -> LinkTapGatewayConfig:
        """Fetch gateway configuration / device list (cmd 16)."""
        response = await self._request({"cmd": CMD_CONFIG, "gw_id": gw_id})
        if "end_dev" not in response:
            raise LinkTapResponseError(
                "Gateway config missing 'end_dev'; firmware may need updating"
            )
        return LinkTapGatewayConfig.from_payload(gw_id, response)

    async def async_get_status(
        self, gw_id: str, dev_id: str
    ) -> LinkTapDeviceStatus:
        """Fetch a single device's status snapshot (cmd 3)."""
        response = await self._request(
            {"cmd": CMD_STATUS, "gw_id": gw_id, "dev_id": dev_id}
        )
        return LinkTapDeviceStatus.from_payload(response)

    async def async_start(
        self,
        gw_id: str,
        dev_id: str,
        seconds: int,
        volume: float | None = None,
    ) -> bool:
        """Start instant watering (cmd 6) for a duration and optional volume."""
        data: dict[str, Any] = {
            "cmd": CMD_START,
            "gw_id": gw_id,
            "dev_id": dev_id,
            "duration": int(seconds),
        }
        if volume:
            data["volume"] = volume
        return self._check_ret(await self._request(data))

    async def async_stop(self, gw_id: str, dev_id: str) -> bool:
        """Stop watering (cmd 7)."""
        return self._check_ret(
            await self._request(
                {"cmd": CMD_STOP, "gw_id": gw_id, "dev_id": dev_id}
            )
        )

    async def async_pause(self, gw_id: str, dev_id: str, hours: int) -> bool:
        """Pause the watering plan for ``hours`` (cmd 18); 0 unpauses."""
        return self._check_ret(
            await self._request(
                {
                    "cmd": CMD_PAUSE,
                    "gw_id": gw_id,
                    "dev_id": dev_id,
                    "duration": int(hours),
                }
            )
        )

    async def async_dismiss_alert(
        self, gw_id: str, dev_id: str, alert_id: int = ALERT_ALL
    ) -> bool:
        """Dismiss one or all alerts (cmd 10)."""
        return self._check_ret(
            await self._request(
                {
                    "cmd": CMD_DISMISS_ALERT,
                    "gw_id": gw_id,
                    "dev_id": dev_id,
                    "alert": alert_id,
                    "enable": True,
                }
            )
        )
