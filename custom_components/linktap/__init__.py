"""The LinkTap (Local HTTP API) integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .api import LinkTapAuthError, LinkTapClient, LinkTapError
from .const import (
    DEFAULT_ACTIVE_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
    MANUFACTURER,
    OPT_ACTIVE_POLL_INTERVAL,
    OPT_POLL_INTERVAL,
    OPT_REQUEST_TIMEOUT,
    OPT_VOL_UNIT,
    PLATFORMS,
)
from .coordinator import LinkTapCoordinator
from .push import async_register_coordinator, async_unregister_coordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class LinkTapRuntimeData:
    """Runtime objects stored on the config entry."""

    client: LinkTapClient
    coordinator: LinkTapCoordinator


type LinkTapConfigEntry = ConfigEntry[LinkTapRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, entry: LinkTapConfigEntry
) -> bool:
    """Set up LinkTap from a config entry."""
    host = entry.data[CONF_HOST]
    timeout = entry.options.get(OPT_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)
    client = LinkTapClient(
        hass,
        host,
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
        timeout=timeout,
    )

    try:
        gw_id = await client.async_get_gw_id()
        config = await client.async_get_config(gw_id)
    except LinkTapAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except LinkTapError as err:
        raise ConfigEntryNotReady(
            f"Unable to reach LinkTap gateway at {host}: {err}"
        ) from err

    poll_interval = timedelta(
        seconds=entry.options.get(
            OPT_POLL_INTERVAL, DEFAULT_POLL_INTERVAL.total_seconds()
        )
    )
    active_poll_interval = timedelta(
        seconds=entry.options.get(
            OPT_ACTIVE_POLL_INTERVAL, DEFAULT_ACTIVE_POLL_INTERVAL.total_seconds()
        )
    )

    coordinator = LinkTapCoordinator(
        hass, client, config, poll_interval, active_poll_interval
    )
    if vol_unit := entry.options.get(OPT_VOL_UNIT):
        coordinator.vol_unit = vol_unit

    await coordinator.async_config_entry_first_refresh()

    # Register the gateway as a hub device so each tap output's via_device resolves.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, gw_id)},
        manufacturer=MANUFACTURER,
        name=f"LinkTap Gateway {gw_id}",
        model="LinkTap Gateway",
        sw_version=config.version,
        configuration_url=f"http://{host}/",
    )

    async_register_coordinator(hass, coordinator)
    entry.runtime_data = LinkTapRuntimeData(client=client, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: LinkTapConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and (data := entry.runtime_data) is not None:
        async_unregister_coordinator(hass, data.coordinator.gw_id)
    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: LinkTapConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
