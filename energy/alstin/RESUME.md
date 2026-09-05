# RESUME — Alstin Lodge Energy Controller

Pi service optimising a Tesla Powerwall vs the Octopus price feed, replacing paid
"Netzero for Powerwall" (cancel before **12 Aug 2026**). See `README.md` for full design.

## SolarEdge hot-water diverter — NOT FIXED (status as of 2026-06-11)
The separate problem of the **SolarEdge "Smart Energy" immersion diverter** heating
water regardless of genuine surplus (draining the Powerwall / pulling peak-rate grid).
Diagnosed 2026-06-09 (full detail was only in a session transcript until now):
- **Hardware:** SE6000H HD-Wave inverter + 12×S440/Jinko 440Wp (~5.28 kWp), AC-coupled
  Tesla Powerwall 13.5 kWh on its own Gateway. Diverter is driven by the inverter
  (ZigBee/wired). Fault reported to installer Sheerwater by email 10 Aug 2024.
- **Root cause (confirmed, known limitation):** the inverter computes "excess solar"
  from its own meter and is blind to the AC-coupled Powerwall, so both grab the same
  surplus. Not a settings fix.
- **Hard constraint (verified):** the Smart Energy hot-water device has NO public
  API/Modbus hook — cannot be read or commanded from the Pi via SolarEdge.
- **Designed fix (not built, needs hardware):** gate the immersion circuit with a
  Pi-controlled relay — Shelly Pro 1 driving a 16–20 A contactor (immersion ~3 kW,
  don't switch through the Shelly contacts) — Pi enables it only on true surplus
  (exporting AND Powerwall ≳95% AND off-peak), via Shelly local HTTP. Software side
  (rule + dashboard Hot Water panel + Boost) can be built once hardware is ordered;
  needs an electrician for the contactor.
- **No-hardware interim:** in mySolarEdge, schedule water heating into the Go cheap
  window 23:30–04:30 (8.63p) and turn excess-solar mode off — on these tariffs
  exporting at 12p beats self-heating anyway, so the schedule is near-optimal.

## SolarEdge<->Tesla bridge — solar-aware charge target (2026-06-10)
**Diagnosis of "Powerwall not charging from excess solar":** the Tesla gateway CT
meters the SolarEdge fine (25-27 kWh/day in June). The battery wasn't charging from
solar because Netzero charges it to ~100% in the cheap Go window every night, so
midday PV surplus exported at Outgoing **12p** while the house still imported
6-8 kWh/day at the Go day rate **31.38p** (night 8.63p). Storing the surplus instead
is worth ~£1.20-1.80/day in summer.

**Fix (built + tested, exercised in dry-run):**
- `solar.py` — the bridge. PV forecast = Open-Meteo daily radiation × a yield
  factor self-calibrated against Tesla's own daily solar history (no SolarEdge
  credentials needed). `plan()` → tonight's overnight charge target: 100% on dull
  days, down to `min_charge_target_pct` (35) on sunny ones so PV fills the rest.
- `strategy.py` `decide(..., charge_target=)` — overrides the static 100% target.
- `feed.py` `SolarTargetCache` — refreshes 6-hourly, falls back to the static
  target on any error. New `solar:` block in config.yaml.
- Dashboard: `/api/solar` + "Overnight charge target" line in the weather card.
- `solaredge.py` + `/api/solaredge` — OPTIONAL direct Monitoring-API cross-check;
  dormant until `SOLAREDGE_API_KEY`/`SOLAREDGE_SITE_ID` go in `.env` (key: log in
  at monitoring.solaredge.com → Admin → Site Access → API Access).
- Tests: 21/21 (`test_solar.py` new, 12 tests). Live check 2026-06-10: calibrated
  k=1.436 kWh/MJ over 9 days; tomorrow dull (7.6 kWh PV) → target 100%. Correct.

**NOTE:** takes real effect only at go-live — Netzero still controls the battery
and will keep charging to 100% overnight regardless of our dry-run.

## Battery level graph + gas usage (dormant) — 2026-06-13
- **Battery level card** ("Battery level — today"): `/api/battery/history` →
  Tesla calendar history `kind="soe"` (state-of-energy %, ~15-min slots,
  midnight→now). Line chart of SoC % with a dashed reserve line; refreshes
  5-min. Same quantity as the live State-of-charge card.
- **Gas usage card** ("Gas usage — last 14 days"): `/api/gas` → daily kWh bars.
  **Dormant** (404, like solaredge.py) until `OCTOPUS_API_KEY` is in `.env`;
  the card then auto-discovers the gas MPRN+serial from account <OCTOPUS_ACCOUNT_NUMBER> and
  lights up. Until then the card shows a setup hint, not an error.
  - `octopus.py`: `account_gas_meter_points()`, `gas_consumption()` (endpoint
    `/gas-meter-points/{mprn}/meters/{serial}/consumption/`).
  - `gas.py`: dormant wrapper. `to_kwh()` converts native units — SMETS2 meters
    report kWh, older meters m³ (×`gas_kwh_per_m3` 11.1); `gas_units: auto`
    infers from magnitude. Config: `octopus.gas_mprn/gas_serial/gas_units/
    gas_kwh_per_m3` (all optional/auto).
  - **To enable gas:** on the Pi, `cd /mnt/media/ai-projects/alstin-lodge-energy
    && (umask 177 && echo 'OCTOPUS_API_KEY=sk_live_...' >> .env)` then
    `sudo systemctl restart energy-web`. Key is in octopus.energy → Personal
    details → API access. Same key also unlocks billed-consumption recon.
- Tests: 33/33 (`test_gas.py` new, 5 tests). Both endpoints verified live
  (battery 200 w/ curve; gas 404 dormant).

## Solar outlook — 14-day prospect + accuracy log (2026-06-11)
Dashboard card "Solar outlook — next 14 days": Open-Meteo daily forecast
(radiation MJ/m², mean cloud %, WMO code) × the same self-calibrated yield k
as `plan()` → predicted harvest kWh/day. Days 8+ rendered faded (lower
confidence); API tail days appear as "awaiting data" placeholders.
- `solar.py`: `daily_forecast()`, `build_outlook()` (pure), `log_outlook()`,
  `forecast_accuracy()` (pure-ish), `outlook()` orchestrator, `--snapshot` CLI.
- Every `outlook()` call snapshots predictions into `energy.db` table
  `solar_forecast_log` (PK forecast_date+target_date, INSERT OR IGNORE — first
  snapshot of the day wins). Actuals for matching = `market_tally.solar_kwh`
  merged under Tesla calendar history.
- Accuracy line (median APE by horizon bucket 0-1d/2-3d/4-7d/8-14d) appears
  after `solar.accuracy_min_days` (7) matched days; until then a progress
  placeholder shows. Config: `solar.outlook_days: 14`, `accuracy_min_days: 7`.
- `webapp.py`: `/api/solar/outlook` (30-min cache). Tests: 28/28.
- **Watch:** calibrated k (≈1.33 kWh/MJ on 2026-06-11) implies >38 kWh peak
  days from a 5.28 kWp array — biased high by a dull-day run; the track record
  will quantify it. Consider a `max_daily_kwh` clamp if it persists.

## Dashboard: energy.gcburton.org — LIVE (2026-06-09)
Login-gated web dashboard (Caddy basic_auth, user `gareth`, same pw as /cds) at
**https://energy.gcburton.org**. FastAPI/uvicorn on `127.0.0.1:5077`, systemd unit
`energy-web.service` (enabled). Reached via the existing cloudflared tunnel.
- Infra added: Cloudflare CNAME `energy` -> tunnel; `/etc/cloudflared/config.yml`
  ingress rule for `energy.gcburton.org` -> https://localhost:443; Caddy site block
  (basic_auth + reverse_proxy :5077). Backups of both configs alongside the originals.
- `webapp.py` routes: `/api/live` (FleetAPI live_status), `/api/settings` GET/POST
  (LIVE battery control: mode/reserve/grid-charging), `/api/weather` (Open-Meteo),
  `/api/prices` (current + Agile half-hourly), `/api/tally` (switch comparison).
- `market.py` = the tally engine. Baseline = your ACTUAL grid flows (Tesla 5-min
  energy history -> 30-min slots) costed on Go + Outgoing. Counterfactual = battery
  doing ACTIVE ARBITRAGE on Agile import + Agile Outgoing with the same solar/load
  (charge cheapest 3h, peak-shave, profit-gated export). delta = baseline - counterfactual
  (+ve = Agile wins). Cached per-day in `energy.db` table `market_tally`. Unit-rate
  energy only; standing charges not modelled. NO Octopus key needed (prices are public).
- `weather.py` = Open-Meteo client (no key). Refine `weather.lat/lon` in config.yaml.
- Early read (15 days): cumulative **delta ≈ -£17 (~-£420/yr)** — Agile currently LOSES
  vs Go's cheap nights. Tool is doing its job: switch not worth it yet. Watch the trend.
- Optional: add `OCTOPUS_API_KEY=...` to `.env` (gitignored, mode 600) for future
  billed-consumption reconciliation; everything works without it.

## Current state (2026-06-10)
- Code complete; **9/9 strategy tests pass** (`.venv/bin/python -m unittest test_strategy -v`).
- Octopus feed proven once in dry-run (real import prices fetched). `config.yaml` filled
  with real tariffs/MPANs (Octopus Go, region J). Account <OCTOPUS_ACCOUNT_NUMBER>.
- Mode: `control.enabled: false`, `control.dry_run: true` — **safe, never touches battery.**
- **Feed service installed + enabled (2026-06-10)** as `alstin-lodge-energy.service`, but
  dormant: `ConditionPathExists` gates it on `.env`, which holds the Octopus key and does
  not exist yet. **ONE manual step blocks everything downstream:**
  ```
  cd /mnt/media/ai-projects/alstin-lodge-energy
  (umask 177 && echo 'OCTOPUS_API_KEY=sk_live_...' > .env)
  sudo systemctl start alstin-lodge-energy && journalctl -u alstin-lodge-energy -f
  ```
  (Key is in the Octopus dashboard → API access. It used to be passed via shell env;
  it is not stored anywhere on the Pi.)
- Only 1 dry-run cycle logged (2026-06-08) → the multi-day dry-run watch starts once the
  service is running. Then go-live per README, then cancel Netzero.
- Switch tally after 15 days: cumulative **delta -£17.25 (~-£420/yr)** — Agile still loses
  to Go's cheap nights. No change in verdict.

## Tesla FleetAPI (cloud control) setup — ✅ COMPLETE (2026-06-09)
Tesla developer app credentials (in `.pypowerwall.fleetapi`, gitignored):
- Client ID `<TESLA_FLEET_CLIENT_ID>`, Client Secret set, Domain `gcburton.org`,
  Redirect `https://pypowerwall.com/code`, Audience EU (`fleet-api.prd.eu.vn.cloud.tesla.com`).

Done:
- EC P-256 keypair generated: private `tesla-fleet-private.pem` (local, gitignored via `*.pem`);
  public key **hosted** at `https://gcburton.org/.well-known/appspecific/com.tesla.3p.public-key.pem`
  (served by existing Caddy `file_server` from `/home/test/www/gcburton.org/` — no Caddyfile edit).
  Verified HTTP 200, valid TLS, no redirect/auth; published key derives from the private key.
- **Partner account registered** with Tesla (name `piwall`); re-confirmed 2026-06-09 via
  `POST /api/1/partner_accounts` → 200, and Tesla's stored `public_key` matches the hosted PEM.
- **User OAuth complete:** authorization code exchanged → `access_token` + `refresh_token`
  written to `.pypowerwall.fleetapi`. `site_id` = **<TESLA_SITE_ID>** (site name redacted,
  ac_powerwall). Live read verified via FleetAPI `get_live_status` (real SoC, not SIMULATED).
- Note: access_token lasts 8h; pypowerwall auto-refreshes using the refresh_token on 401.

If tokens ever fully expire, regenerate the authorize URL with the snippet below, sign in,
paste the `code=`, and re-run the code→token exchange.

Regenerate authorize URL:
```
.venv/bin/python - <<'PY'
import json,secrets,urllib.parse
c=json.load(open(".pypowerwall.fleetapi")); s=secrets.token_urlsafe(16)
c["_oauth_state"]=s; json.dump(c,open(".pypowerwall.fleetapi","w"),indent=2)
print("https://auth.tesla.com/oauth2/v3/authorize?"+urllib.parse.urlencode({
 "client_id":c["CLIENT_ID"],"redirect_uri":c["REDIRECT_URI"],"response_type":"code",
 "scope":"openid offline_access user_data energy_device_data energy_cmds",
 "state":s,"locale":"en-US","prompt":"login"}))
PY
```

## After FleetAPI works
- Confirm read-only: `.venv/bin/python feed.py --once` shows real SoC (not SIMULATED).
- Watch dry-run a few days. Then go-live per README: `dry_run:false` (still `enabled:false`),
  restart, sanity-check, then `enabled:true`. Cloud caps reserve at 80%.
- Only then cancel Netzero + revoke its Tesla access (README has the steps).

## Gotchas
- `sqlite3` CLI not installed on this Pi — query `energy.db` from Python, or read `energy.csv`.
- Local git repo, no remote — commit locally, nothing to push.
