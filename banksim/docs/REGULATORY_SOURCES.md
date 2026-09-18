# Regulatory position as modelled

Checked September 2026. Where a rule is time-sensitive it is dated and sourced;
where the model makes a choice that could reasonably go the other way, that is
flagged. **Verify against the primary source before relying on any of it.**

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

1. **The 65% risk weight for unrated investment-grade corporates.** This is the
   Basel treatment for jurisdictions that do not permit external ratings. The
   UK does permit them. Whether the PRA's final rules retain a 65% IG weight,
   and on what conditions, is the single assumption here most worth checking
   against PS1/26. Toggle with `SAConfig.allow_ig_corporate_65`.
2. **Sterling BI thresholds** for operational risk, as above.
3. **The FRTB CSR bucket grid** in `market_risk.CSR_RW` follows the Basel
   sector/credit-quality structure but the covered-bond and index buckets are
   folded in at headline weights rather than reproduced exactly.
4. **Scenario paths** are stylised throughout. `acs_severe` is *shaped* like a
   Bank of England annual cyclical scenario but the numbers are ours. To make
   the stress real, import the Bank's published variable paths.
