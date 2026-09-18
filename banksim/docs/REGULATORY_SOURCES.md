# Regulatory position as modelled

Checked September 2026. Where a rule is time-sensitive it is dated and sourced;
where the model makes a choice that could reasonably go the other way, that is
flagged. **Verify against the primary source before relying on any of it.**

### How these were checked, and the limit on that

The build environment's egress policy blocks `bankofengland.co.uk`, `bis.org`
and `prarulebook.co.uk` outright (403 at the proxy on every attempt, by
organisation policy). Nothing below was read from the primary text. It comes
from search over secondary commentary — law firms, the Big Four, specialist
advisers — triangulated across several sources where they agreed. That is good
enough to build a model against and not good enough to advise on. Anyone
relying on a number here should open the rulebook.

## Basel 3.1 in the UK

- The PRA published the **final rules in PS1/26 on 20 January 2026**,
  finalising the near-final PS9/24.
- **Implementation date: 1 January 2027**, following the PRA's January 2025
  announcement of a one-year delay (made with HM Treasury, pending clarity on
  US implementation).
- The **FRTB internal model approach is deferred a further year, to
  1 January 2028**. Everything else applies from 2027.
- The **output floor** starts at **60% on 1 January 2027**, steps to 65% (2028)
  and 70% (2029), and reaches its fully loaded **72.5% on 1 January 2030**.
  The end point of the transitional period was unchanged by the delay, which
  compressed the transition.

Modelled in `capital.OUTPUT_FLOOR_PATH`.

## Buffers

- The FPC has held the **UK countercyclical capital buffer at its 2% neutral
  setting** through 2026 (April and July 2026 FPC records).
- Capital conservation buffer 2.5%; the systemic buffer is the higher of the
  G-SII, O-SII and systemic risk buffer rates. Kingsgate carries none, being
  neither a G-SII nor a ring-fenced body.
- The PRA buffer (Pillar 2B) is firm-specific and confidential; the 1.0% used
  here is a placeholder.

## Leverage

- Current UK regime: **3.25% minimum**, higher than Basel's 3% because the UK
  exposure measure excludes qualifying central bank claims. Additional leverage
  ratio buffer at 35% of the risk-weighted systemic buffer; countercyclical
  leverage buffer at 35% of the CCyB.
- In 2026 the FPC set out a package it **intends to consult on**: reduce the
  minimum to **3%**, remove the CCLB, recalibrate the ALRB to **50%** of the
  risk-weighted systemic buffer (the Basel calibration), and introduce a
  releasable **0.25% general leverage buffer**. The FPC estimated the package
  would reduce effective leverage requirements for major UK banks by around
  20 basis points.

Both regimes are implemented; switch with `LeverageConfig(regime=...)`.

## MREL

- The Bank of England raised the indicative total-assets threshold for a
  stabilisation-power resolution strategy (and therefore an external MREL)
  **from £15–25bn to £25–40bn**, to be reviewed every three years from 2028.
- For a bail-in firm, MREL is set at the higher of twice the risk-weighted
  minimum and twice the leverage requirement, with the combined buffer required
  to be met above it.
- MREL reporting amendments apply from 1 January 2027; standardised MREL
  disclosure templates (UK KM2, UK MREL1–3) were finalised in **PS11/26**
  (26 March 2026), applying from 1 January 2027 with a first reference date of
  31 December 2026.

## Credit risk: unrated corporates (a real UK divergence)

The UK applies a **risk-sensitive approach** to unrated corporate exposures:
**65% where the firm assesses the obligor as investment grade, 135% where it
does not.** Basel and the EU both use a flat 100% for all unrated corporates,
so this is one of the clearer UK departures, and a favourable one for banks
with good internal rating systems.

Two conditions matter and are modelled:

- it requires **PRA permission** and systems capable of making the
  investment-grade distinction. Without it, the firm uses a **flat 100%**;
- a firm must apply **one approach to every unrated exposure**, including in
  the output floor comparator, so that it cannot take 65% on its good names and
  100% on its bad ones.

`SAConfig.unrated_corporate_approach` is `"risk_sensitive"` or `"flat_100"`,
and being a single switch is itself the consistency requirement. For Kingsgate
the choice moves the all-standardised comparator by about £1.1bn.

Unrated corporate SMEs take 85% under either approach.

## Pillar 1 supporting factors, and what replaced them

Basel 3.1 **removes the SME supporting factor** (which cut eligible SME RWAs by
23.81%) **and the infrastructure supporting factor** (25%). The PRA compensates
with **firm-specific Pillar 2A structural adjustments** — the SME lending
adjustment and the infrastructure lending adjustment — finalised in **PS7/25
(22 May 2025)** and applying alongside the rest of Basel 3.1 from 1 January
2027.

The PRA calibrates them firm-specifically from the change in RWAs and a capital
adjustment factor it does not publish in detail. What it states the calibration
achieves is that removing the Pillar 1 factors does not raise overall capital
requirements for that lending, and that identity is what `capital.
lending_adjustment` implements. `CapitalRequirements` therefore carries a
`pillar2a_gross` plus the two adjustments rather than a single net figure, and
UK KM1 shows the build-up.

## Market risk: a live consultation

**CP9/26 (June 2026)** — the PRA is consulting on adjustments to the internal
model approach for market risk. It does not affect this model, which uses the
standardised approach throughout, but it is the reason the FRTB-IMA date is
worth re-checking rather than assuming.

## Operational risk

The PRA sets the **Internal Loss Multiplier to 1** for all firms rather than
using internal loss data. `OpRiskConfig.use_ilm` defaults to `False` to match,
but the Basel ILM is implemented so the effect of the UK choice can be measured.

The BI bucket thresholds are stated in the code in sterling at round numbers
(£1bn / £30bn). **These are a stylised conversion** — check the PRA Rulebook
Operational Risk Part for the actual sterling thresholds.

## CVA

The UK retains exemptions from the CVA charge that Basel does not have:
transactions with a qualifying CCP, with certain sovereign and public-sector
counterparties, with pension scheme arrangements, and with **non-financial
counterparties below the EMIR clearing threshold**. The last is material for a
bank whose derivative clients are corporate hedgers. Modelled via
`NettingSet.cva_exempt`; Kingsgate applies it to its cleared and sovereign sets
but deliberately leaves its corporate hedging set in scope so the charge is
visible.

## Known uncertainties in this model

1. **Sterling BI thresholds** for operational risk. The PRA recast the euro
   thresholds into sterling; the actual figures were not recoverable from
   secondary sources, so the code uses round £1bn / £30bn. Check the
   Operational Risk Part.
2. **The capital adjustment factor** in the Pillar 2A lending adjustments. The
   PRA's own methodology is firm-specific and not published in detail; the
   model derives the adjustment from the constant-requirement identity instead.
3. **The FRTB CSR bucket grid** in `market_risk.CSR_RW` follows the Basel
   sector/credit-quality structure but the covered-bond and index buckets are
   folded in at headline weights rather than reproduced exactly.
4. **Scenario paths** are stylised throughout. `acs_severe` is *shaped* like a
   Bank of England annual cyclical scenario but the numbers are ours. To make
   the stress real, import the Bank's published variable paths.

### Resolved since the first draft

The 65% risk weight for unrated investment-grade corporates was flagged as the
single assumption most worth checking. It checks out, and the first draft was
**wrong in the other direction**: it weighted unrated non-investment-grade
corporates at 100% when the UK risk-sensitive approach puts them at 135%. Now
implemented, along with the flat-100% alternative and the consistency rule.
