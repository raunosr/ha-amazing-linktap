"""Constants for the LinkTap local HTTP API integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "linktap"
MANUFACTURER: Final = "LinkTap"

# --- Gateway local HTTP API command codes (api.shtml POST `cmd`) ---
# Confirmed against reference implementations and the official spec
# (LinkTap Gateway MQTT Client Integration, sections 4.1/4.2).
CMD_STATUS: Final = 3  # per-device status snapshot (also the push payload format, PDF 4.1)
CMD_START: Final = 6  # start instant watering
CMD_STOP: Final = 7  # stop watering
CMD_DISMISS_ALERT: Final = 10  # dismiss an alert
CMD_CONFIG: Final = 16  # gateway configuration / device enumeration
CMD_SET_CONFIG: Final = 17  # set a persistent per-device config value (SetDeviceConfigReq)
CMD_PAUSE: Final = 18  # pause/unpause the watering plan

# --- CMD_SET_CONFIG (cmd 17) tags ---
# The gateway accepts exactly two persistent config tags (openHAB SetDeviceConfigReq).
CONFIG_TAG_VOLUME_LIMIT: Final = "volume_limit"  # water volume limit (gateway vol_unit)
CONFIG_TAG_DURATION_LIMIT: Final = "total_duration"  # watering duration limit (seconds)

# --- Alert ids (CMD_DISMISS_ALERT `alert` field) ---
ALERT_ALL: Final = 0
ALERT_FALL: Final = 1
ALERT_SHUTDOWN: Final = 2
ALERT_CUTOFF: Final = 3
ALERT_HIGH_FLOW: Final = 4
ALERT_LOW_FLOW: Final = 5

ALERT_LOOKUP: Final = {
    "all": ALERT_ALL,
    "fall": ALERT_FALL,
    "shutdown": ALERT_SHUTDOWN,
    "cutoff": ALERT_CUTOFF,
    "high_flow": ALERT_HIGH_FLOW,
    "low_flow": ALERT_LOW_FLOW,
}

# --- Config entry / options keys ---
OPT_POLL_INTERVAL: Final = "poll_interval"  # seconds, while push is healthy
OPT_ACTIVE_POLL_INTERVAL: Final = "active_poll_interval"  # seconds, push unreachable
OPT_REQUEST_TIMEOUT: Final = "request_timeout"  # seconds, per HTTP request
OPT_VOL_UNIT: Final = "vol_unit"  # override gateway-reported volume unit

# --- Defaults ---
DEFAULT_POLL_INTERVAL: Final = timedelta(seconds=30)
DEFAULT_ACTIVE_POLL_INTERVAL: Final = timedelta(seconds=12)
DEFAULT_REQUEST_TIMEOUT: Final = 10
# Gateway reports every 2 minutes even when unchanged (PDF 4.1); if we have not
# heard a push within this window we assume push is unreachable and poll actively.
PUSH_WATCHDOG: Final = timedelta(minutes=3)
RETRY_ATTEMPTS: Final = 3

DEFAULT_DURATION_MIN: Final = 15
DEFAULT_VOLUME_LIMIT: Final = 0
DEFAULT_PAUSE_HOURS: Final = 24
DEFAULT_DURATION_LIMIT_MIN: Final = 0  # 0 = no persistent duration limit
MAX_DURATION_MIN: Final = 1440
MAX_DURATION_LIMIT_MIN: Final = MAX_DURATION_MIN
MAX_PAUSE_HOURS: Final = 96

# --- Volume unit handling ---
# The gateway reports its volume unit as "L" or "Gal" (CMD_CONFIG `vol_unit`).
VOL_UNIT_LITERS: Final = "L"
VOL_UNIT_GALLONS: Final = "Gal"

# --- Push view ---
PUSH_URL: Final = "/api/linktap/push"

# Hold a valve's requested (optimistic) open/closed state for this long after an
# open/close command, until the gateway confirms it started/stopped watering.
# The physical valve takes a moment to actuate, so an immediate status poll still
# reports the old state; without this the UI toggle would flicker back.
OPTIMISTIC_WINDOW: Final = 30.0

# --- Watering plan modes (status `plan_mode`) ---
PLAN_MODES: Final = [
    "N/A",
    "Instant",
    "Calendar",
    "7-Day",
    "Odd-Even",
    "Interval",
    "Month",
]

PLATFORMS: Final = ["valve", "switch", "number", "sensor", "binary_sensor"]
