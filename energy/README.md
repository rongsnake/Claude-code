# Auto Smart Mode — overnight Powerwall grid-charging for the energy page

Overnight grid-charging engine for the Tesla Powerwall in the Octopus Go off-peak window (default
**00:30–05:30** UK time; Intelligent Octopus Go is 23:30–05:30 — change
`window_start`). The aim: the Powerwall is at its target charge by the end of the cheap
window (almost) every night, and never grid-charges at the peak rate unless the plan
says the window alone cannot get it there. It works by raising the Powerwall's **backup
reserve** to the target at the window start (the Powerwall then imports from the grid at
full power and stops discharging), holding it until the window ends, then restoring the
normal reserve and self-powered mode so the battery runs the house through the day.

## Where it goes
The live energy page is the **Alstin Lodge energy dashboard** at
**energy.gcburton.org**: a FastAPI app (`webapp.py`, uvicorn `:5077`, systemd unit with
an EnvironmentFile) on the Pi behind Caddy + the Cloudflare tunnel. Its source lives on
the Mac at `~/Claude/Projects/alstin-lodge-energy/` (not in git). Smart Mode is packaged
as a **drop-in** for that app:

- `auto_smart_mode.py` — the engine. `--daemon` ticks once a minute: reads the Powerwall →
  plans tonight (kWh needed ÷ grid charge rate; starts at the window start, earlier only if it
  would not fit) → raises / restores the reserve. `--plan 42` prints the plan for 42 %. `--once`
  runs one tick.
- `energy_api.py` — the API as a FastAPI **router** (`/status`, `/mode`, `/settings`,
  `/boost`, `/refresh`, `/plan?soc=`). Mounted into the dashboard at **`/smart`**; also
  runs standalone (`uvicorn energy_api:app`, `:5056`).
- `smart_mode_card.html` — the self-contained card (toggle, tonight's plan on a 24-hour
  timeline, settings, boost, log) that the installer pastes before `</body>` of the
  dashboard page. Talks to `/smart`; degrades to a local what-if planner if the API is off.
- `install_smart_mode.sh` — one-shot, idempotent installer for the Pi (see below).
- `../public/energy/index.html` — a standalone page with the same card, for use without
  the dashboard (API at `/energy/api/`). `systemd/*.service` are the standalone units.
- `test_auto_smart_mode.py` — planner + engine tests (`python3 -m unittest`).

## Shortfall policy (what "almost always" means)
One Powerwall (13.5 kWh) at 5 kW fills from empty in about three hours, so it always fits
the five-hour window. The policy matters only with several Powerwalls or a slow feed:
- `start_early` (default) — start before 00:30, just early enough to be full by 05:15.
- `run_late` — start at 00:30 and keep going past 05:30.
- `window_only` — off-peak only; the plan shows the % you will get.

## Install into the live dashboard (on the Pi)
```bash
git clone --branch claude/tesla-auto-smart-mode-8cjumu https://github.com/rongsnake/Claude-code.git ~/cc-smart
bash ~/cc-smart/energy/install_smart_mode.sh /path/to/alstin-lodge-energy      # where webapp.py lives
```
The installer copies the three files next to `webapp.py`, appends
`app.include_router(smart_mode_router, prefix="/smart")` to `webapp.py` (backup kept),
injects the card before `</body>` of the dashboard's page (backup kept; if the HTML is
built inside Python it tells you where to paste it), writes `config.json`, installs
`energy-smart.service` as a user unit with the dashboard's Python, and restarts the
dashboard unit. Then:
```bash
# in the app dir: provider=teslapy, tesla_email (and tesla_cache_file if the dashboard already has one), battery_kwh, charge_kw, normal_reserve
$EDITOR config.json
python3 -m pip install teslapy && python3 auto_smart_mode.py --once   # first run = Tesla login (paste URL)
systemctl --user restart energy-smart
curl -s http://127.0.0.1:5077/smart/status | head -c 300
```
If the dashboard already logs into Tesla with teslapy, set `tesla_cache_file` to its
cache.json and no second login is needed. Make sure **Grid charging** is allowed in the
Tesla app (Settings → Powerwall → Advanced), or the raised reserve cannot pull from the grid.
The engine only needs read (SoC, reserve, mode) + set reserve / set mode.

Leave `"provider": "dry-run"` to exercise everything against a simulated Powerwall
(`sim.json` holds its state of charge).
