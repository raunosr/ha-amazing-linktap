# LinkTap — Local HTTP API (Home Assistant)

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

1. Add this repository as a custom repository in HACS (category: *Integration*).
2. Install **LinkTap (Local HTTP API)** and restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration → LinkTap**. Discovered
   gateways appear automatically; otherwise enter the gateway IP/hostname.

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
| `sensor` | Signal, Battery, durations, flow speed, volume, plan info | |
| `binary_sensor` | Watering, manual mode, linked, flow meter, paused, alerts | |

Devices without a flow meter (e.g. G1) report **flow speed / volume** as *unavailable*
rather than misleading zeros.

## Disclaimer

Not affiliated with LinkTap. Use of the gateway's HTTP API is at your own risk.
