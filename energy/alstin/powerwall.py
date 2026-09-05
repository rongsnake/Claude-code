"""pypowerwall wrapper supporting local and cloud (FleetAPI) control.

Reading live data works locally on all Powerwall models. Control works locally
only on a wired Powerwall 3 (v1r mode). On PW2/PW+ (and as our default here)
control goes through Tesla's cloud Fleet API.

pypowerwall is imported lazily so the rest of the project (and the unit tests)
load without it installed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("powerwall")

# Tesla's cloud Fleet API refuses to set a backup reserve above this value.
CLOUD_MAX_RESERVE = 80.0

VALID_MODES = {"self_consumption", "backup", "autonomous"}


@dataclass
class Reading:
    soc: float
    solar_w: float
    load_w: float
    grid_w: float
    battery_w: float
    grid_status: str

    def as_dict(self) -> dict:
        return {
            "soc": self.soc,
            "solar_w": self.solar_w,
            "load_w": self.load_w,
            "grid_w": self.grid_w,
            "battery_w": self.battery_w,
            "grid_status": self.grid_status,
        }


class PowerwallController:
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        self.control_mode = (self.cfg.get("control_mode") or "local").lower()
        self._pw = None  # lazy pypowerwall.Powerwall instance

    # ---- connection -----------------------------------------------------
    def connect(self):
        if self._pw is not None:
            return self._pw
        import pypowerwall  # lazy import

        c = self.cfg
        tz = c.get("timezone", "Europe/London")
        if self.control_mode == "cloud":
            # FleetAPI mode: credentials come from the one-time
            # `python3 -m pypowerwall setup -fleetapi` config file.
            self._pw = pypowerwall.Powerwall(
                host="",
                password="",
                email=c.get("email", ""),
                timezone=tz,
                fleetapi=True,
            )
        else:
            # Local mode. For full PW3 v1r control pass gw_pwd + rsa_key_path.
            self._pw = pypowerwall.Powerwall(
                host=c.get("host", ""),
                password=c.get("gateway_password", ""),
                email=c.get("email", ""),
                timezone=tz,
                gw_pwd=c.get("gateway_password") or None,
                rsa_key_path=c.get("rsa_key_path") or None,
            )
        log.info("Connected to Powerwall in %s mode", self.control_mode)
        return self._pw

    # ---- reading --------------------------------------------------------
    @staticmethod
    def _num(value, default=0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def read(self) -> Reading:
        pw = self.connect()
        return Reading(
            soc=self._num(pw.level()),
            solar_w=self._num(pw.solar()),
            load_w=self._num(pw.load()),
            grid_w=self._num(pw.grid()),
            battery_w=self._num(pw.battery()),
            grid_status=str(pw.grid_status() or "UNKNOWN"),
        )

    # ---- control --------------------------------------------------------
    def set_reserve(self, percent: float) -> None:
        pw = self.connect()
        pct = float(percent)
        if self.control_mode == "cloud" and pct > CLOUD_MAX_RESERVE:
            log.warning(
                "Cloud Fleet API caps reserve at %.0f%%; clamping %.0f%% -> %.0f%% "
                "(use local v1r mode for full 100%% charge)",
                CLOUD_MAX_RESERVE,
                pct,
                CLOUD_MAX_RESERVE,
            )
            pct = CLOUD_MAX_RESERVE
        pw.set_reserve(level=pct)

    def set_mode(self, mode: str) -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid Powerwall mode: {mode!r}")
        pw = self.connect()
        pw.set_mode(mode=mode)

    def set_grid_charging(self, enabled: bool) -> None:
        pw = self.connect()
        fn = getattr(pw, "set_grid_charging", None)
        if fn is None:
            raise NotImplementedError(
                "Installed pypowerwall has no set_grid_charging; upgrade it"
            )
        fn(mode=bool(enabled))
