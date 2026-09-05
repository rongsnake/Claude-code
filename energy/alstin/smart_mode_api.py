#!/usr/bin/env python3
"""API for the energy page's Auto Smart Mode (Powerwall grid-charging in the Octopus Go window).

GET  /status           live state + plan + non-secret settings (what the page polls)
POST /mode             {"enabled": true|false}   — the Auto Smart Mode toggle
POST /settings         any subset of the editable settings (validated)
POST /boost            {"minutes": 60}            — grid-charge now at any rate
POST /boost/cancel
POST /refresh          re-read the Powerwall now
GET  /plan?soc=42      what-if plan for a given state of charge

The engine (auto_smart_mode.py --daemon) owns the Powerwall; this API only edits
config.json and drops one-shot commands into requests.json.

Mounted in the Alstin Lodge dashboard (webapp.py)::

    from smart_mode_api import router as smart_mode_router
    app.include_router(smart_mode_router, prefix="/smart")

Standalone: ``uvicorn smart_mode_api:app`` (:5056).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import auto_smart_mode as asm

router = APIRouter(tags=["auto-smart-mode"])

app = FastAPI(title="Auto Smart Mode API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

EDITABLE = {
    "enabled": bool, "override_feed": bool, "window_start": str, "window_end": str, "target_soc": int,
    "battery_kwh": float, "charge_kw": float, "efficiency": float, "buffer_minutes": int,
    "shortfall_policy": str, "normal_reserve": int, "restore_mode": str, "charge_method": str,
    "hold_until_window_end": bool, "plan_time": str, "octopus_product": str, "octopus_tariff": str,
}
SECRET = {"tesla_email", "tesla_cache_file", "fleetapi_config"}
CHOICES = {
    "shortfall_policy": ("start_early", "run_late", "window_only"),
    "restore_mode": ("self_consumption", "autonomous"),
    "charge_method": ("reserve", "backup_mode"),
}


def public_config() -> dict:
    return {k: v for k, v in asm.load_config().items() if k not in SECRET}


def _validate(k: str, v):
    t = EDITABLE[k]
    try:
        v = t(v) if t is not bool else (v if isinstance(v, bool) else str(v).lower() in ("1", "true", "on"))
    except (TypeError, ValueError):
        raise HTTPException(400, f"{k}: bad value")
    if k in ("window_start", "window_end", "plan_time"):
        try:
            asm.parse_hhmm(v)
        except Exception:
            raise HTTPException(400, f"{k}: use HH:MM")
    if k == "target_soc" and not 50 <= v <= 100:
        raise HTTPException(400, "target_soc must be 50–100")
    if k == "normal_reserve" and not 0 <= v <= 100:
        raise HTTPException(400, "normal_reserve must be 0–100")
    if k in CHOICES and v not in CHOICES[k]:
        raise HTTPException(400, f"{k} must be one of {' | '.join(CHOICES[k])}")
    if k in ("battery_kwh", "charge_kw") and not v > 0:
        raise HTTPException(400, f"{k} must be > 0")
    if k == "efficiency" and not 0.5 <= v <= 1:
        raise HTTPException(400, "efficiency must be 0.5–1")
    return v


def _request(**kw) -> None:
    req = asm.load_json(asm.REQUESTS_PATH, {})
    req.update(kw)
    asm.save_json(asm.REQUESTS_PATH, req)


@router.get("/status")
def status():
    cfg = public_config()
    state = asm.load_json(asm.STATE_PATH, {})
    stale = True
    if state.get("last_tick"):
        age = (datetime.now(ZoneInfo(cfg["timezone"])) - datetime.fromisoformat(state["last_tick"])).total_seconds()
        stale = age > 3 * int(cfg["poll_seconds"])
    return {"config": cfg, "state": state, "engine_alive": not stale,
            "now": datetime.now(ZoneInfo(cfg["timezone"])).isoformat(timespec="seconds")}


class Mode(BaseModel):
    enabled: bool


@router.post("/mode")
def set_mode(m: Mode):
    return set_settings({"enabled": m.enabled})


@router.post("/settings")
def set_settings(body: dict):
    unknown = set(body) - set(EDITABLE)
    if unknown:
        raise HTTPException(400, f"unknown settings: {sorted(unknown)}")
    clean = {k: _validate(k, v) for k, v in body.items()}
    cfg = asm.load_json(asm.CONFIG_PATH, {})
    cfg.update(clean)
    asm.save_json(asm.CONFIG_PATH, cfg)
    return {"ok": True, "config": public_config()}


class Boost(BaseModel):
    minutes: int = 60


@router.post("/boost")
def boost(b: Boost):
    if not 5 <= b.minutes <= 600:
        raise HTTPException(400, "minutes must be 5–600")
    _request(boost_minutes=b.minutes)
    return {"ok": True}


@router.post("/boost/cancel")
def boost_cancel():
    _request(cancel_boost=True)
    return {"ok": True}


@router.post("/refresh")
def refresh():
    _request(refresh=True)
    return {"ok": True}


@router.get("/plan")
def plan(soc: float):
    cfg = asm.load_config()
    now = datetime.now(ZoneInfo(cfg["timezone"]))
    return asm.plan_charge(soc, cfg, now).to_json()


app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5056)
