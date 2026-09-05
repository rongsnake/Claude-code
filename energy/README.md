# Energy page — Auto Smart Mode

Overnight Tesla charging engine for the Octopus Go off-peak window
(default **00:30–05:30**, UK time; Intelligent Octopus Go is 23:30–05:30 — change
`window_start`). The aim: the car is at its target charge by the end of the cheap
window (almost) every night, and never charges at the peak rate unless the plan
says the window alone cannot get it there.

## Pieces
- `auto_smart_mode.py` — the engine. `--daemon` ticks once a minute:
  reads the car → plans tonight (kWh needed ÷ charger rate → start time so it
  finishes 15 min before the window ends) → starts / stops charging accordingly.
  `--plan 42` prints the plan for a 42 % state of charge. `--once` runs one tick.
- `energy_api.py` — FastAPI on `:5056`: `/status`, `/mode`, `/settings`, `/boost`,
  `/refresh`, `/plan?soc=`. The page polls it every 30 s and degrades to a local
  what-if planner when it is off.
- `../public/energy/index.html` — the page: toggle, tonight's plan on a 24-hour
  timeline, settings, boost button and the engine log.
- `systemd/*.service` — user units, same pattern as `cds-api.service`.
- `test_auto_smart_mode.py` — planner + engine tests (`python3 -m unittest`).

## Shortfall policy (what "almost always" means)
A 75 kWh pack on a 7.4 kW charger gains ≈ 33 kWh (≈ 45 %) in the 5-hour window.
From below ~55 % it cannot reach 100 % on off-peak alone, so:
- `start_early` (default) — start before 00:30, just early enough to be full by 05:15.
- `run_late` — start at 00:30 and keep going past 05:30.
- `window_only` — off-peak only; the plan shows the % you will get.

## Install on the Pi
```bash
pip install teslapy fastapi uvicorn requests
cd ~/Claude-code/energy && python3 auto_smart_mode.py --init-config
# edit config.json: "provider": "teslapy", "tesla_email": "...", battery_kwh, charger_kw
python3 auto_smart_mode.py --once            # first run does the Tesla OAuth (paste URL)
mkdir -p ~/.config/systemd/user && cp systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now energy-smart energy-api
rsync -av ../public/energy/index.html gcburton.org:/var/www/gated/energy/index.html
```
Caddy, inside the existing gated site block (mirrors `/cds/api/*`):
```
handle_path /energy/api/* {
    reverse_proxy localhost:5056 { flush_interval -1 }
}
```
Leave `"provider": "dry-run"` to exercise everything against a simulated car
(`sim.json` holds its state of charge).
