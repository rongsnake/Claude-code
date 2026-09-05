"""Apply a Decision to the Powerwall, behind hard safety rails.

Nothing is ever sent to the battery unless BOTH:
    control.enabled is true  AND  control.dry_run is false.
Otherwise the intended action is only logged.
"""
from __future__ import annotations

import logging
from typing import Optional

from strategy import Decision

log = logging.getLogger("controller")


def _is_live(control_cfg: dict) -> bool:
    enabled = bool(control_cfg.get("enabled", False))
    dry_run = bool(control_cfg.get("dry_run", True))
    return enabled and not dry_run


def apply(decision: Decision, powerwall, control_cfg: dict) -> str:
    """Apply (or log) `decision`. Returns a human-readable note for storage."""
    intent = (
        f"action={decision.action} mode={decision.mode} "
        f"reserve={decision.reserve:.0f}% grid_charging={decision.grid_charging} "
        f"({decision.reason})"
    )

    if not _is_live(control_cfg):
        why = "control disabled" if not control_cfg.get("enabled", False) else "dry-run"
        note = f"DRY RUN [{why}]: would {intent}"
        log.info(note)
        return note

    if powerwall is None:
        note = f"LIVE but no Powerwall connection; skipped: {intent}"
        log.warning(note)
        return note

    # Live control path.
    try:
        powerwall.set_mode(decision.mode)
        powerwall.set_reserve(decision.reserve)
        powerwall.set_grid_charging(decision.grid_charging)
        note = f"APPLIED: {intent}"
        log.info(note)
        return note
    except Exception as exc:  # never let a control error crash the loop
        note = f"CONTROL ERROR applying {intent}: {exc}"
        log.exception(note)
        return note
