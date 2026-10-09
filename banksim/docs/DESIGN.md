# banksim — design notes

## What this is

An end-to-end model of a hypothetical UK wholesale bank: its balance sheet, its
P&L, the regulatory capital and liquidity it must hold under the UK
implementation of Basel 3.1, and how all three move together through a
macroeconomic scenario.

It is written from scratch in the Python standard library. No pandas, no numpy,
no scipy — partly so it runs on a Raspberry Pi with nothing to compile, mostly
because writing the normal inverse CDF and the aggregation formulae out by hand
is the point of the exercise.

## The two organising ideas

**1. Every number carries a provenance.** A capital model is only as honest as
its inputs, and a simulator's inputs are mostly invented. `units.Provenance`
tags each one as `REGULATORY` (the rule as written), `SUPERVISORY` (firm-specific
and set by the PRA), `MARKET_REF`, `STYLISED` (made up) or `DERIVED`. Every
report carries a banner saying the bank is fictional and what share of the
registered inputs are stylised. This follows the same rule the rest of this
repository applies to scraped CDS data: never present a synthetic figure as a
real one.

**2. The same book is measured several ways at once.** A real IRB bank computes
credit RWAs on its own models *and* on the standardised approach, because the
output floor compares them. It computes regulatory expected loss *and* IFRS 9
expected credit loss over the same exposures, because the gap is a CET1
deduction. It computes a risk-weighted requirement, a leverage requirement and
an MREL requirement, and any of the three can bind. The data model therefore
separates *what an exposure is* from *how a given approach measures it*.

## Module map

```
units.py          provenance tagging, normal CDF/inverse, formatting
exposures.py      the four primitives: CreditExposure, NettingSet/Derivative,
                  TradingBook (Sensitivity/JumpToDefault), Funding/Commitment

credit_risk.py    revised standardised approach + IRB risk-weight function,
                  input floors, CCFs, credit risk mitigation
counterparty.py   SA-CCR (replacement cost, add-ons, PFE multiplier) and
                  BA-CVA (reduced), with the UK exemptions
market_risk.py    FRTB standardised: SBM (delta/vega/curvature, three
                  correlation scenarios), DRC, RRAO
op_risk.py        Business Indicator -> BI Component -> Internal Loss Multiplier
liquidity.py      LCR (HQLA caps, run-off rates, inflow cap) and NSFR
capital.py        own funds, RWA aggregation, output floor, buffers, MDA,
                  leverage (two regimes), MREL

ifrs9.py          three-stage ECL, SICR, macro conditioning, scenario weighting
scenario.py       macro paths and the systematic factor Z that drives credit
pnl.py            NII with a structural hedge, markets desks, fee businesses,
                  costs with a flexing bonus pool, UK tax (CT + surcharge + levy)

bank.py           Kingsgate Bank plc — the hypothetical firm
engine.py         the annual loop and the capital feedback
report.py         Pillar 3-shaped tables (UK KM1, OV1, CR1, LR2)
cli.py            snapshot / run / stress
```

## The annual loop

Order matters and is easy to get wrong:

1. **Defaults crystallise.** Performing balances default at their point-in-time
   PD and move into the non-performing pool; a tranche of the existing
   non-performing stock is worked out and written off. Without this step,
   provisions simply release when the macro recovers and a five-year stress
   shows *cumulative* impairment near zero, which is wrong.
2. **ECL is re-measured**, probability-weighted across the scenario set, with
   the weights tilted towards the scenario being run (a bank in a downturn does
   not keep the planning weights it set in benign conditions). The movement,
   plus write-offs, is the P&L impairment charge.
3. **IRB PDs migrate** with the cycle, dampened by a cyclicality factor, because
   UK IRB models are hybrids rather than purely through-the-cycle. This is what
   makes RWAs inflate in a downturn and squeeze the ratio from both ends.
4. **RWAs are struck** on both the live and the all-standardised basis, and the
   output floor applied.
5. **The exposure measure** is built for the leverage ratio.
6. **The P&L runs**: NII, markets, fees, costs, impairment, tax.
7. **Capital moves.** The MDA test is run on the position *before* distribution;
   the dividend is capped by it; retained earnings take the rest. AT1 coupons
   are cancelled if the bank is deep enough into its buffer.
8. **The balance sheet grows** into the next year — lending with GDP, inventory
   inversely with volatility, both reduced if the MDA bound.

Step 7 is the feedback loop that makes this a simulation rather than a
spreadsheet: a bad year cuts capital, which cuts the buffer, which caps the
dividend, which partly protects capital for the following year.

## What is faithful and what is simplified

Faithful (the rule as written, and tested):

- the IRB risk-weight function, including the asset correlation, the SME
  firm-size adjustment, the AVC multiplier for financial institutions, the
  maturity adjustment, and the Basel 3.1 PD/LGD/EAD input floors;
- the revised standardised risk-weight tables and credit conversion factors,
  including the UK risk-sensitive approach to unrated corporates (65%/135%)
  and its flat-100% alternative;
- the Pillar 2A SME and infrastructure lending adjustments that replace the
  withdrawn Pillar 1 supporting factors;
- SA-CCR: replacement cost with and without margin, supervisory duration,
  supervisory delta, maturity factor, the add-on hedging-set structure and the
  PFE multiplier;
- BA-CVA reduced form, including the UK exemptions for cleared and sovereign
  counterparties;
- the FRTB SBM aggregation: weighted sensitivities, the within-bucket and
  across-bucket formulae, the three correlation scenarios and the
  negative-root fallback, and the GIRR tenor correlation function;
- the DRC netting and weighted-to-short hedge-benefit ratio;
- the operational risk BI/BIC/ILM construction, with the PRA's ILM = 1 and the
  sterling bucket boundaries (£880m / £26bn) derived from the PRA's own
  euro-to-sterling redenomination convention;
- LCR HQLA caps, run-off rates, the 75% inflow cap and the net outflow floor;
- NSFR available and required stable funding factors;
- the capital stack, buffer hierarchy, MDA quartiles, and the
  AT1/Tier 2 shortfall interaction with buffer capacity;
- both UK leverage regimes, current and as the FPC proposed in 2026;
- the output floor and its transitional path.

Simplified, and marked `SIMPLIFIED` in the code:

- FRTB vega and curvature use a single prescribed treatment per risk class
  rather than the full per-bucket shock machinery;
- FRTB cross-bucket correlation matrices are collapsed to their dominant
  values rather than the full published matrices;
- securitisation (SEC-SA/SEC-IRBA, and the CTP) is not implemented at all;
- credit risk mitigation uses simple substitution for guarantees and assumes
  the caller has already haircut financial collateral;
- the securities financing add-on in the leverage exposure measure is a flat
  percentage rather than a full counterparty calculation;
- the macro scenarios are stylised, not the Bank of England's published paths.

## Granularity, and the one dial that moves everything

Each `CreditExposure` stands for a **pool** of loans, not a single loan. That
matters most for IFRS 9 stage transfer: a homogeneous pool crosses the SICR
threshold all at once, so the first version of this model reported the entire
performing book moving to stage 2 in year one of a stress. No bank reports
that. `stage2_share` therefore assumes obligor PDs are lognormally dispersed
within each pool (`pd_dispersion`, default 0.75 in log PD) and computes the
fraction whose conditioned PD exceeds the threshold. That gives ~7% of the book
in stage 2 in the base case and ~73% at the trough of the severe scenario.

The severe-scenario figure is still high — a real severe stress test would put
it nearer half — and the reason is `scenario.Z_SCALE`, the constant converting
weighted macro deviations into the systematic factor. It is the single most
powerful dial in the model, because impairment, IRB PD migration and the stage 2
share all key off Z together:

| `Z_SCALE` | Z at the trough | corporate PD 0.22% becomes | stage 2 share | CET1 drawdown | MDA binds |
|---|---|---|---|---|---|
| 0.80 | -1.47 | 1.06% | 67% | 2.90pp | no |
| 0.90 | -1.66 | 1.27% | 73% | 3.47pp | yes |
| 1.00 | -1.84 | 1.51% | 79% | 4.26pp | yes |

Shipped at 0.90, which puts the severe scenario where a supervisory stress test
should be — eating into the combined buffer without threatening Pillar 1. The
honest characterisation is that this is calibrated to produce a plausible-looking
stress, not derived from data. Replacing the stylised scenario with the Bank of
England's published variable paths, and fitting the segment loadings to observed
default rates, is the first item on the roadmap for exactly this reason.

## A result worth noting

For Kingsgate, **the output floor does not bind**, and will not at 72.5%. That
is not a bug. The floor compares total RWAs on both bases; market, operational,
counterparty and CVA risk are already on standardised approaches and so are
identical in both. Only the credit book differs, and a wholesale bank's credit
book is too small a share of the total for plausible IRB relief to close a
27.5% gap. The floor bites hardest on firms with large IRB mortgage books,
where modelled risk weights run at a fraction of the standardised ones. The
model reports `output_floor_headroom` so the distance can be seen.

The binding constraint for this bank is the risk-weighted CET1 requirement,
with leverage second. In the severe scenario CET1 falls through the combined
buffer requirement and the MDA caps distributions, while Pillar 1 is never
threatened — which is what a buffer is for.

## Running it

```bash
python -m banksim.cli snapshot --assumptions   # opening capital position
python -m banksim.cli run --scenario acs_severe --detail
python -m banksim.cli stress --json out.json   # all scenarios, compared
python -m unittest discover -s banksim/tests -t .
```
