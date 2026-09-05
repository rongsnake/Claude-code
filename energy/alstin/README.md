# Alstin Lodge Energy Controller

A Raspberry Pi service that optimises a Tesla Powerwall against the Octopus Energy
price feed. Intended to **replace the paid "Netzero for Powerwall" app** (subscription
renews **12 Aug 2026** — cancel before then, see below).

**Starts safe: monitoring + dry-run only. Control is disabled by default.**

## What it optimises (priority order)
1. Charge the Powerwall from the grid during the cheapest Octopus Go window.
2. Maximise export earnings — only when export actually pays well.
3. Discharge to cover the house at peak import prices.
4. Otherwise maximise solar self-use.

## Files
| File | Purpose |
|------|---------|
| `octopus.py` | Octopus REST client (account, import/export rates, consumption) + `Rate` |
| `powerwall.py` | pypowerwall wrapper, local **and** cloud (FleetAPI) control |
| `strategy.py` | Pure decision logic — `decide(...)`, unit-testable |
| `controller.py` | Applies a Decision behind hard safety rails |
| `storage.py` | Appends each cycle to SQLite + CSV |
| `feed.py` | Main loop (`--once`, `--no-powerwall`, `--no-prices`) |
| `discover.py` | Reads `$OCTOPUS_API_KEY`, prints meters/tariffs/prices, `--write`s config |
| `config.yaml` | Live config (gitignored). Key is **never** stored here |
| `test_strategy.py` | Tests for the four rules |
| `alstin-lodge-energy.service` | systemd unit |

## Setup
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export OCTOPUS_API_KEY=sk_live_...        # never commit this
python3 discover.py --write               # fill in tariffs/MPANs, show next 24h prices
.venv/bin/python feed.py --once --no-powerwall   # prove the Octopus feed
.venv/bin/python -m unittest test_strategy -v
```

## Powerwall control: local vs cloud
- **cloud (default here)** — Tesla Fleet API. Works on PW2 / PW+ / PW3. Needed because
  we're replacing Netzero, which controls via Tesla's cloud. One-time setup:
  ```bash
  .venv/bin/python -m pypowerwall setup -fleetapi
  ```
  ⚠️ Tesla's cloud caps the backup reserve at **80%**; `reserve_charge_target: 100`
  is clamped to 80% (logged). Full 100% needs local mode.
- **local** — direct LAN. Full control (`set_reserve`/`set_mode`/`set_grid_charging`)
  only on a **wired Powerwall 3** in v1r mode (needs Gateway password + RSA key).
  Find the Gateway: `.venv/bin/python -m pypowerwall scan`

## Watching it run (dry-run)
Foreground:
```bash
export OCTOPUS_API_KEY=...
.venv/bin/python feed.py            # prints a status line each cycle
```
Each cycle logs the intended action prefixed `DRY RUN [...]` and never touches the
battery. Inspect history any time:
```bash
sqlite3 energy.db 'SELECT ts,soc,action,reserve,grid_charging,note FROM cycles ORDER BY ts DESC LIMIT 20;'
column -s, -t energy.csv | less -S
```

## Going live (only once you're happy)
1. Watch dry-run logs for a few days and confirm the actions match what you'd want.
2. Complete the FleetAPI setup and set `powerwall.control_mode: cloud`.
3. In `config.yaml` set `control.dry_run: false` first (still `enabled: false` =
   safe, no-op), restart, confirm it still logs sanely.
4. Flip `control.enabled: true`. **Now it controls the battery.** Restart the service.
5. To pull the plug instantly: set `control.enabled: false` and restart — or stop
   the service entirely.

## Run 24/7 with systemd
```bash
sudo cp alstin-lodge-energy.service /etc/systemd/system/
sudo nano /etc/systemd/system/alstin-lodge-energy.service   # set OCTOPUS_API_KEY=, check User/paths
sudo systemctl daemon-reload
sudo systemctl enable --now alstin-lodge-energy
journalctl -u alstin-lodge-energy -f      # live logs
sudo systemctl restart alstin-lodge-energy   # after a config change
```

## Cancelling Netzero (do once the controller is proven, before 12 Aug 2026)
**1. Cancel the Apple subscription**
- iPhone/iPad: Settings → tap your name → **Subscriptions** → **Netzero / Netzero for
  Powerwall** → **Cancel Subscription**. (Or App Store → profile icon → Subscriptions.)
- Mac: App Store → your name → **Account Settings** → Manage Subscriptions.
- Confirm the renewal date shown is on/after **12 Aug 2026** and that it now says
  "expires" rather than "renews". You keep access until the paid period ends.

**2. Revoke Netzero's Tesla third-party access** (so it can no longer control the battery)
- Sign in at **https://accounts.tesla.com** → **Security** / **Third-Party Apps** (also
  reachable in the Tesla app: profile → Security & Privacy → Third-Party Apps).
- Find the **Netzero** entry and **Revoke access**.
- This is independent of the App Store cancellation — do both. Our controller's
  FleetAPI token is separate and stays valid.

> Don't revoke Tesla access until this controller has been running live and steady,
> or you'll have no automation in between.
