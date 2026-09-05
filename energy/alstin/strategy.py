"""Pure battery-optimisation decision logic. No network, fully unit-testable.

Priority order (highest first):
  1. Charge from grid in the cheapest Octopus Go window.
  2. Export when export actually pays well.
  3. Discharge to cover the house at peak import prices.
  4. Otherwise maximise solar self-use.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional, Sequence

# Octopus / Tesla mode strings used by the decision logic.
MODE_AUTONOMOUS = "autonomous"
MODE_SELF = "self_consumption"

ACTION_CHARGE = "charge"
ACTION_EXPORT = "export"
ACTION_DISCHARGE = "discharge"
ACTION_SELF_USE = "self_use"


@dataclass
class StrategyConfig:
    reserve_floor: float = 10.0
    reserve_charge_target: float = 100.0
    cheap_charge_hours: float = 3.0
    cheap_price_threshold_p: float = 15.0
    export_price_threshold_p: float = 30.0


@dataclass
class Decision:
    action: str
    mode: str
    reserve: float
    grid_charging: bool
    reason: str


# A "Rate-like" object only needs value_inc_vat, covers(when) and duration_hours().
class _RateLike:  # documentation helper; real Rate comes from octopus.py
    value_inc_vat: float

    def covers(self, when: dt.datetime) -> bool: ...
    def duration_hours(self) -> float: ...


def price_at(rates: Sequence, when: dt.datetime) -> Optional[float]:
    """Return the unit price (p/kWh) covering `when`, or None if not found."""
    for r in rates:
        if r.covers(when):
            return r.value_inc_vat
    return None


def cheapest_slots(rates: Sequence, hours: float) -> list:
    """Return the cheapest rate slots whose durations sum to >= `hours`.

    Slots are returned in price order (cheapest first). Open-ended slots
    (duration inf) count as covering all remaining hours.
    """
    ordered = sorted(rates, key=lambda r: r.value_inc_vat)
    chosen: list = []
    acc = 0.0
    for r in ordered:
        if acc >= hours:
            break
        chosen.append(r)
        acc += r.duration_hours()
    return chosen


def in_cheap_window(now: dt.datetime, import_rates: Sequence, hours: float) -> bool:
    """True if `now` falls inside one of the cheapest slots covering `hours`."""
    for r in cheapest_slots(import_rates, hours):
        if r.covers(now):
            return True
    return False


def decide(
    now: dt.datetime,
    import_rates: Sequence,
    export_rates: Sequence,
    soc: float,
    cfg: StrategyConfig,
    charge_target: Optional[float] = None,
) -> Decision:
    """Return the intended Decision for this moment. Pure function.

    `charge_target` overrides cfg.reserve_charge_target when given - the
    solar-aware target from solar.plan(), which leaves overnight headroom so
    tomorrow's PV surplus charges the battery instead of exporting at 12p.
    """
    imp = price_at(import_rates, now)
    exp = price_at(export_rates, now)
    floor = cfg.reserve_floor
    target = charge_target if charge_target is not None else cfg.reserve_charge_target

    # Rule 1: cheapest import window + cheap enough + room to charge.
    if (
        imp is not None
        and imp <= cfg.cheap_price_threshold_p
        and soc < target
        and in_cheap_window(now, import_rates, cfg.cheap_charge_hours)
    ):
        label = "solar-aware target" if charge_target is not None else "target"
        return Decision(
            action=ACTION_CHARGE,
            mode=MODE_AUTONOMOUS,
            reserve=target,
            grid_charging=True,
            reason=(
                f"cheapest window, import {imp:.2f}p <= "
                f"{cfg.cheap_price_threshold_p:.0f}p, SoC {soc:.0f}% < "
                f"{label} {target:.0f}%"
            ),
        )

    # Rule 2: export pays well and we have surplus above the floor.
    if exp is not None and exp >= cfg.export_price_threshold_p and soc > floor:
        return Decision(
            action=ACTION_EXPORT,
            mode=MODE_AUTONOMOUS,
            reserve=floor,
            grid_charging=False,
            reason=(
                f"export {exp:.2f}p >= {cfg.export_price_threshold_p:.0f}p, "
                f"SoC {soc:.0f}% > floor {floor:.0f}%"
            ),
        )

    # Rule 3: import is expensive and we have charge to spend covering the house.
    if imp is not None and imp > cfg.cheap_price_threshold_p and soc > floor:
        return Decision(
            action=ACTION_DISCHARGE,
            mode=MODE_SELF,
            reserve=floor,
            grid_charging=False,
            reason=(
                f"peak import {imp:.2f}p > {cfg.cheap_price_threshold_p:.0f}p, "
                f"discharge to cover house (SoC {soc:.0f}% > floor {floor:.0f}%)"
            ),
        )

    # Rule 4: default to solar self-use.
    return Decision(
        action=ACTION_SELF_USE,
        mode=MODE_SELF,
        reserve=floor,
        grid_charging=False,
        reason="no price trigger; maximise solar self-use",
    )
