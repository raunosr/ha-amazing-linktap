"""Typed model for LinkTap water-timer status payloads.

Both the polled ``CMD_STATUS`` (cmd 3) response queried with a ``dev_id`` and the
gateway's push payload (PDF section 4.1) are flat JSON objects keyed by the field
names below, so a single parser serves both paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _as_bool(value: Any) -> bool | None:
    """Coerce a gateway flag to bool, preserving ``None`` when absent."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes")
    return bool(value)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class LinkTapDeviceStatus:
    """Parsed status snapshot for a single water timer (tap output)."""

    dev_id: str
    raw: dict[str, Any] = field(repr=False)

    # Connectivity / mode
    is_rf_linked: bool | None = None
    is_flm_plugin: bool | None = None
    is_watering: bool | None = None
    is_manual_mode: bool | None = None
    is_paused: bool | None = None
    child_lock: int | None = None

    # Alerts
    is_fall: bool | None = None
    is_cutoff: bool | None = None
    is_leak: bool | None = None
    is_clog: bool | None = None
    is_broken: bool | None = None

    # Measurements
    signal: int | None = None
    battery: int | None = None
    total_duration: int | None = None
    remain_duration: int | None = None
    failsafe_duration: int | None = None

    # Flow-meter only (None when no flow meter is plugged in, e.g. G1 devices)
    speed: float | None = None
    volume: float | None = None
    volume_limit: float | None = None

    # Watering plan
    plan_mode: int | None = None
    plan_sn: int | None = None

    @property
    def has_flow_meter(self) -> bool:
        """Whether a flow meter is connected (drives speed/volume availability)."""
        return bool(self.is_flm_plugin)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LinkTapDeviceStatus":
        """Build a status object from a raw gateway status/push payload."""
        has_flm = _as_bool(payload.get("is_flm_plugin"))
        # Without a flow meter the gateway reports zeros that would be misleading;
        # surface them as unavailable instead.
        speed = _as_float(payload.get("speed")) if has_flm else None
        volume = _as_float(payload.get("volume")) if has_flm else None
        volume_limit = _as_float(payload.get("volume_limit")) if has_flm else None

        return cls(
            dev_id=str(payload.get("dev_id", "")),
            raw=payload,
            is_rf_linked=_as_bool(payload.get("is_rf_linked")),
            is_flm_plugin=has_flm,
            is_watering=_as_bool(payload.get("is_watering")),
            is_manual_mode=_as_bool(payload.get("is_manual_mode")),
            is_paused=_as_bool(payload.get("is_paused")),
            child_lock=_as_int(payload.get("child_lock")),
            is_fall=_as_bool(payload.get("is_fall")),
            is_cutoff=_as_bool(payload.get("is_cutoff")),
            is_leak=_as_bool(payload.get("is_leak")),
            is_clog=_as_bool(payload.get("is_clog")),
            is_broken=_as_bool(payload.get("is_broken")),
            signal=_as_int(payload.get("signal")),
            battery=_as_int(payload.get("battery")),
            total_duration=_as_int(payload.get("total_duration")),
            remain_duration=_as_int(payload.get("remain_duration")),
            failsafe_duration=_as_int(payload.get("failsafe_duration")),
            speed=speed,
            volume=volume,
            volume_limit=volume_limit,
            plan_mode=_as_int(payload.get("plan_mode")),
            plan_sn=_as_int(payload.get("plan_sn")),
        )


@dataclass(frozen=True, slots=True)
class LinkTapGatewayConfig:
    """Gateway configuration returned by ``CMD_CONFIG`` (cmd 16)."""

    gw_id: str
    version: str | None
    vol_unit: str
    dev_ids: list[str]
    dev_names: list[str]
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_payload(
        cls, gw_id: str, payload: dict[str, Any]
    ) -> "LinkTapGatewayConfig":
        dev_ids = [str(d) for d in payload.get("end_dev", [])]
        dev_names = [str(n) for n in payload.get("dev_name", [])]
        # Defend against mismatched lengths by falling back to the dev id.
        if len(dev_names) < len(dev_ids):
            dev_names += dev_ids[len(dev_names):]
        return cls(
            gw_id=gw_id,
            version=payload.get("ver"),
            vol_unit=str(payload.get("vol_unit", "L")),
            dev_ids=dev_ids,
            dev_names=dev_names,
            raw=payload,
        )

    def name_for(self, dev_id: str) -> str:
        """Friendly name for a device id, falling back to the id itself."""
        try:
            return self.dev_names[self.dev_ids.index(dev_id)]
        except (ValueError, IndexError):
            return dev_id
