# Mac source snapshot — Alstin Lodge energy dashboard

Secrets-free copy of the app that serves **energy.gcburton.org** (FastAPI/uvicorn
`webapp.py` on the Pi, port 5077, plus the `feed.py` controller loop).

## Source path (Mac)

```
/Users/garethburton/Claude/Projects/Raspberry Pi/alstin-lodge-energy
```

(Deployed on the Pi at `/mnt/media/ai-projects/alstin-lodge-energy`, per the
`.service` files.)

## Excluded from this copy

Everything gitignored or secret-bearing: `.env`, `config.yaml` (live account
config — `config.example.yaml` is the committed template), `energy.csv` /
`*.db` data files, `*.pem` keys, `.pypowerwall.fleetapi` (Tesla tokens),
`__pycache__` / venvs. Doc references to the live Octopus account number,
Tesla Fleet client ID, and Tesla site ID were replaced with placeholders.

## .env — variable names only (values live in `.env` on the Pi, mode 600)

- `OCTOPUS_API_KEY` — optional; enables billed-consumption reconciliation and
  the gas usage card. Prices and the tally work without it.
- `SOLAREDGE_API_KEY` — optional; SolarEdge Monitoring API cross-check only.
- `SOLAREDGE_SITE_ID` — optional; pairs with the SolarEdge key.

`.env` is loaded by systemd (`EnvironmentFile=` in both `.service` units), not
by python-dotenv.

## Tesla authentication

The app does **not** hold Tesla credentials in `.env`. It talks to the
Powerwall via **pypowerwall in Fleet API (cloud) mode**
(`powerwall.control_mode: cloud` in config):

1. One-time setup: `python3 -m pypowerwall setup -fleetapi` — registers a
   Tesla developer app (client ID/secret, domain `gcburton.org`, EU audience
   `fleet-api.prd.eu.vn.cloud.tesla.com`), an EC P-256 keypair (private
   `tesla-fleet-private.pem` local; public key hosted at
   `https://gcburton.org/.well-known/appspecific/com.tesla.3p.public-key.pem`),
   and a partner account with Tesla.
2. User OAuth (scopes `openid offline_access user_data energy_device_data
   energy_cmds`) yields an `access_token` + `refresh_token`, stored with the
   app credentials in **`.pypowerwall.fleetapi`** (gitignored, on the Pi).
3. At runtime `powerwall.py` constructs `pypowerwall.Powerwall(...,
   fleetapi=True)`, which reads that file. Access tokens last ~8h;
   pypowerwall auto-refreshes with the refresh token on 401.
4. Cloud mode caps the backup reserve at 80%; full control would need local
   PW3 v1r mode (gateway password + RSA key).

If tokens fully expire, RESUME.md ("Tesla FleetAPI setup") has the
regenerate-authorize-URL snippet to redo the code→token exchange.
