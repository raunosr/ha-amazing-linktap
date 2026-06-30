"""HTTP endpoint that receives status pushes from LinkTap gateways.

The gateway's "HTTP Client" (PDF section 4.1) POSTs a device status payload to a
user-configured Server URL whenever a device changes, and at least every two
minutes. Point that Server URL at ``http://<home-assistant>:8123/api/linktap/push``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, PUSH_URL

if TYPE_CHECKING:
    from .coordinator import LinkTapCoordinator

_LOGGER = logging.getLogger(__name__)

_REGISTRY_KEY = "push_registry"
_VIEW_KEY = "push_view_registered"


@callback
def async_register_coordinator(
    hass: HomeAssistant, coordinator: "LinkTapCoordinator"
) -> None:
    """Register a coordinator so pushes can be routed to it, adding the view once."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    registry: dict[str, "LinkTapCoordinator"] = domain_data.setdefault(
        _REGISTRY_KEY, {}
    )
    registry[coordinator.gw_id] = coordinator

    if not domain_data.get(_VIEW_KEY):
        hass.http.register_view(LinkTapPushView(hass))
        domain_data[_VIEW_KEY] = True


@callback
def async_unregister_coordinator(
    hass: HomeAssistant, gw_id: str
) -> None:
    """Remove a coordinator from the push registry on unload."""
    registry = hass.data.get(DOMAIN, {}).get(_REGISTRY_KEY, {})
    registry.pop(gw_id, None)


class LinkTapPushView(HomeAssistantView):
    """Receives gateway status POSTs and dispatches them to coordinators."""

    url = PUSH_URL
    name = "api:linktap:push"
    # The gateway cannot present a Home Assistant token; this LAN endpoint is
    # unauthenticated but only acts on payloads matching a known gateway/device.
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Handle a status push from a gateway."""
        try:
            payload = await request.json()
        except ValueError:
            _LOGGER.debug("Discarding LinkTap push with invalid JSON body")
            return web.Response(status=400, text="invalid json")

        if not isinstance(payload, dict):
            return web.Response(status=400, text="invalid payload")

        registry: dict[str, "LinkTapCoordinator"] = self._hass.data.get(
            DOMAIN, {}
        ).get(_REGISTRY_KEY, {})

        coordinator = self._resolve(registry, payload)
        if coordinator is None:
            _LOGGER.debug("No coordinator for LinkTap push: %s", payload)
            return web.Response(status=202, text="unknown device")

        coordinator.async_handle_push(payload)
        return web.Response(status=200, text="ok")

    @staticmethod
    def _resolve(
        registry: dict[str, "LinkTapCoordinator"], payload: dict
    ) -> "LinkTapCoordinator | None":
        """Find the coordinator owning this payload by gw_id, then by dev_id."""
        gw_id = payload.get("gw_id")
        if gw_id and gw_id in registry:
            return registry[gw_id]
        dev_id = payload.get("dev_id")
        if dev_id:
            for coordinator in registry.values():
                if dev_id in coordinator.config.dev_ids:
                    return coordinator
        return None
