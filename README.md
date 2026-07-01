<img src="images/icon.png" alt="Amazing LinkTap" width="128" align="right" />

# Amazing LinkTap — Local HTTP API (Home Assistant)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![CI](https://github.com/raunosr/ha-amazing-linktap/actions/workflows/ci.yml/badge.svg)](https://github.com/raunosr/ha-amazing-linktap/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Control LinkTap gateways and their water timers (TapLinker, ValveLinker, D1) entirely
over the gateway's **local HTTP API** (`/api.shtml` on your LAN). No cloud, no MQTT broker.

- **Local push + polling fallback** — the gateway pushes status changes to Home Assistant
  (every change, plus a 2‑minute keepalive). If pushes stop arriving, the integration
  automatically falls back to active polling.
- **One device per tap output** — multi‑outlet timers create one Home Assistant device per
  output, each with a `valve` for water control.
- **Modern Home Assistant patterns** — `DataUpdateCoordinator`, config flow with Zeroconf
  discovery, reauth, and an options flow.

## Requirements

- A LinkTap gateway (e.g. GW‑01/GW‑02) reachable on your LAN, with recent firmware.
- The gateway's **Local HTTP API** enabled on its admin page.
- Static IP (or DNS/mDNS hostname) recommended for the gateway.

## Installation (HACS)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=raunosr&repository=ha-amazing-linktap&category=integration)

1. Add this repository as a custom repository in HACS (category: *Integration*) — or use
   the button above to open it directly in HACS.
2. Install **Amazing LinkTap** and restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration → Amazing LinkTap**. Discovered
   gateways appear automatically; otherwise enter the gateway IP/hostname.

<details>
<summary>Manual installation (without HACS)</summary>

Copy the `custom_components/linktap` folder into your Home Assistant `config/custom_components`
directory and restart Home Assistant.
</details>

## Enabling push (recommended)

On the gateway admin page, enable the **HTTP Client** and set the **Server URL** to your
Home Assistant instance, e.g. `http://<home-assistant-ip>:8123/api/linktap/push`.
If push is not configured, the integration still works using polling.

> Tip: in the gateway's *Local HTTP API* settings you may disable "Wrap the gateway's
> response in HTML". This integration handles both wrapped and plain‑JSON responses.

## Entities (per tap output)

| Platform | Entity | Notes |
|---|---|---|
| `valve` | Watering valve | Open starts watering using the Duration / Volume Limit numbers |
| `switch` | Pause | Pauses the watering plan for the Pause Duration hours |
| `number` | Watering Duration, Volume Limit, Pause Duration | Inputs consumed by the valve |
| `sensor` | Signal, Battery, durations, flow speed, volume, total volume, plan info | |
| `binary_sensor` | Watering, manual mode, linked, flow meter, paused, alerts | |

Devices without a flow meter (e.g. G1) report **flow speed / volume / total volume** as
*unavailable* rather than misleading zeros.

### Total volume (cumulative)

The gateway's local API only reports the volume of the **current** watering cycle, so there is
no lifetime figure to read directly. The **Total volume** sensor integrates each cycle's volume
in Home Assistant and persists across restarts (`state_class: total_increasing`), making it
usable in the Energy dashboard or with a Utility Meter for daily/monthly periods.

> Limitation: because the total is integrated from status snapshots, a very short cycle that
> both starts and finishes between two updates can be under‑counted. Enabling push (above)
> minimises this, since the gateway reports on every change.

## Disclaimer

Not affiliated with LinkTap. Use of the gateway's HTTP API is at your own risk.

## License

Released under the [MIT License](LICENSE).
