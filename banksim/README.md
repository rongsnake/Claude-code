# banksim — a UK wholesale banking simulator

An end-to-end model of a hypothetical UK investment bank, **Kingsgate Bank plc**:
its balance sheet, its P&L, the regulatory capital and liquidity it must hold
under the UK implementation of Basel 3.1, and how all three move together
through a macroeconomic scenario.

Written from scratch in the Python standard library — no pandas, no numpy, no
scipy. It runs anywhere Python 3.10+ runs, including a Raspberry Pi.

> **Kingsgate Bank plc is fictional.** No figure here is drawn from any firm's
> accounts or regulatory returns. Regulatory parameters are the rules as
> published; the balance sheet, P&L and scenarios are invented, and every
> report says so.

## The page

`banksim/dashboard.html` is an interactive simulator built from the engine —
pick the scenario, step through the years, move Pillar 2A and the buffers,
switch the leverage regime and the dividend policy, and watch the capital
ladder move under the CET1 ratio. Build it with:

```bash
python -m banksim.build_dashboard
```

It emits two files from one template: `dashboard.html`, standalone and
deployable by copying, and `dashboard_artifact.html`, a bare fragment for
platforms that supply their own document skeleton.

The split between baked and live is deliberate. Anything needing the risk
engines or compounding through time — RWAs, the P&L, ECL, staging — is
pre-computed across a grid of scenario x unrated-corporate approach x dividend
policy. The requirement stack and everything downstream of it — buffers, the
MDA test, the leverage requirement, MREL, which constraint binds — recomputes
in the browser, which is what makes it a simulator rather than a report.

## Quick start

```bash
python -m banksim.cli snapshot                    # opening capital position
python -m banksim.cli snapshot --assumptions      # with the provenance appendix
python -m banksim.cli run --scenario acs_severe --detail
python -m banksim.cli stress                      # every scenario, compared
python -m banksim.cli stress --json out.json      # machine-readable

python -m unittest discover -s banksim/tests -t . # 119 tests
```

## What it produces

```
Stress test comparison
------------------------------------------------------------------------------
Scenario          Min CET1   Drawdown  Min lev  Cum impair   Cum PAT  Buffer
----------------------------------------------------------------------------
baseline            14.32%      0.00pp    6.94%         857     4,833       -
upside              14.82%      0.00pp    7.04%         560     7,547       -
stagflation         13.68%      0.00pp    6.88%       1,559     3,495       -
acs_severe          10.16%      3.51pp    5.89%       2,378       914    USED
```

In the severe scenario the bank takes £2.4bn of cumulative impairment, three
quarters of its lending book migrates to IFRS 9 stage 2, its CET1 ratio falls
3.21 percentage points, its RWAs *inflate* as IRB PDs migrate with the cycle,
and it drops through its combined buffer requirement so that the maximum
distributable amount caps its payout — while never coming close to its Pillar 1
minimum. Which is what a buffer is for.

Output is in the shape of the PRA's Pillar 3 templates: **UK KM1** (key
metrics), **UK OV1** (RWAs by risk type, with the output floor comparator),
**UK CR1** (IFRS 9 staging) and **UK LR2** (leverage).

## What is modelled

| Layer | Contents |
|---|---|
| Credit risk | Revised standardised approach, with the UK 65%/135% risk-sensitive treatment of unrated corporates; IRB risk-weight function with asset correlation, SME firm-size adjustment, AVC multiplier, maturity adjustment; Basel 3.1 PD/LGD/EAD input floors; CCFs; credit risk mitigation |
| Counterparty | SA-CCR (replacement cost, hedging-set add-ons, PFE multiplier, supervisory delta and duration); BA-CVA reduced form with the UK exemptions |
| Market risk | FRTB standardised: SBM across GIRR/CSR/EQ/FX/commodity with the three correlation scenarios, DRC with the hedge-benefit ratio, RRAO |
| Operational | Business Indicator → BI Component → Internal Loss Multiplier, with the PRA's ILM = 1 |
| Liquidity | LCR with HQLA caps, run-off rates, the 75% inflow cap and the net outflow floor; NSFR with ASF/RSF factors |
| Capital | Own funds and deductions; Pillar 2A SME and infrastructure lending adjustments; output floor with its transitional path; Pillar 1, Pillar 2A, combined buffer, PRA buffer; MDA quartiles; UK leverage in both its current and FPC-proposed form; MREL |
| Accounting | IFRS 9 three-stage ECL, SICR, macro conditioning, multiple weighted scenarios, default crystallisation and write-off |
| P&L | NII with a rolling structural hedge; four markets desks with differing macro betas; three fee businesses; costs with a flexing bonus pool; UK corporation tax, banking surcharge and bank levy |

## Documentation

- [`docs/DESIGN.md`](docs/DESIGN.md) — architecture, the annual loop, and an
  explicit list of what is faithful to the rules and what is simplified
- [`docs/REGULATORY_SOURCES.md`](docs/REGULATORY_SOURCES.md) — the UK position
  as modelled, dated and sourced, with the known uncertainties flagged
- [`docs/READING_LIST.md`](docs/READING_LIST.md) — English law practitioner
  texts and primary sources, annotated by what each is for
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — what to build next

## Status

Version 0.1. The core engines are implemented and tested; FRTB vega and
curvature are simplified, securitisation is not implemented, and the macro
scenarios are stylised rather than the Bank of England's published paths. Each
simplification is marked `SIMPLIFIED` in the code and listed in `DESIGN.md`.
