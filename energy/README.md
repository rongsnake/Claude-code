# Energy — Auto Smart Mode for energy.gcburton.org

`energy/alstin/` is the **Alstin Lodge energy dashboard** itself (secrets-free snapshot
of the app that runs on the Pi at `/mnt/media/ai-projects/alstin-lodge-energy`: FastAPI
`webapp.py` on :5077 behind Caddy + the Cloudflare tunnel, plus the `feed.py` optimiser
loop). Auto Smart Mode lives inside it:

- `alstin/auto_smart_mode.py` — the engine (`--daemon`, one tick a minute). At the start of
  the Octopus Go window (00:30) it turns grid charging on, sets the reserve to the target and
  switches the Powerwall to **Backup-only** (Tesla's cloud API caps the reserve at 80 %, but
  Backup-only fills to 100 %); holds until 05:30; then restores the normal reserve and
  self-powered mode. Re-asserts if the app changes it mid-window; restores on disable, boost
  expiry or restart. Uses the dashboard's own Fleet API token file (`.pypowerwall.fleetapi`),
  so no new login. Stands down (and says so on the card) if `feed.py` live control is on.
- `alstin/smart_mode_api.py` — router mounted at **`/smart`** in `webapp.py`
  (`/status`, `/mode`, `/settings`, `/boost`, `/refresh`, `/plan?soc=`).
- `alstin/web/smart_mode_card.html` — the card, placed under *Battery controls* in
  `web/index.html`: toggle, tonight's plan on a 24-hour timeline, KPIs, settings, Boost, log.
- `alstin/energy-smart.service` — system unit (User=test, the app's `.venv`).
- `alstin/test_auto_smart_mode.py` — 21 tests (`cd energy/alstin && python3 -m unittest`).
- `install_smart_mode.sh` — puts all of the above onto the Pi's live copy (idempotent,
  backups kept) and starts the service.
- `../public/energy/index.html` + `systemd/` — standalone page/units, not needed on the Pi.

## Go live on the Pi
```bash
git clone --branch claude/tesla-auto-smart-mode-8cjumu https://github.com/rongsnake/Claude-code.git ~/cc-smart
sudo bash ~/cc-smart/energy/install_smart_mode.sh          # default app dir /mnt/media/ai-projects/alstin-lodge-energy
curl -s http://127.0.0.1:5077/smart/status | head -c 300   # engine_alive should be true
```
Then open energy.gcburton.org: the **Auto Smart Mode** card is under Battery controls,
switched on by default. Settings (window, target, normal reserve, charge method) are on
the card; `config.json` next to `webapp.py` holds them.

Tesla app: **Grid charging must be allowed** (the engine turns it on itself, but check
once). `config.yaml` `control.enabled` should stay `false` (feed.py dry-run) so the two
loops don't fight; the card shows a red *conflict* pill if they would.

## Shortfall policy
One Powerwall (13.5 kWh) at 5 kW fills from empty in ≈3 h, so it always fits the 5-hour
window; `start_early` / `run_late` / `window_only` only matter with more storage or a
slower feed. Times on the card are always UK time.
