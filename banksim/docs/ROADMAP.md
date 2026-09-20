# Roadmap

Ordered by what would most improve the model's fidelity per unit of work.

## Standing permission — the risk books (recorded 19 September 2026)

Gareth has said the risk books may now be drawn on. Both questions this note
originally left open are now closed — **see `RISK_BOOKS.md`** for the library
map, the Drive ids, the book-to-constant build map and the reading protocol.
`Provenance.LITERATURE` exists in `units.py`. Calibration work has not started.

### What they would actually unblock

Worth naming, because it is narrower and more valuable than "better research".
The regulatory parameters in this model are already the rules as published. What
is weak is the **calibration**, and almost all of it sits in one place:

| Currently `STYLISED` | What a credit-risk text would give it |
|---|---|
| `scenario.Z_SCALE` | The systematic factor's real scale, fitted to observed default rates rather than tuned to produce a plausible-looking stress. This is the single dial that moves impairment, IRB PD migration and the stage 2 share together, and `DESIGN.md` currently admits it is set by eye. |
| `scenario.SEGMENT_LOADINGS` | Empirical macro sensitivities by portfolio segment, instead of invented weights. |
| `ifrs9.SEGMENT_RHO` | Asset correlations from the portfolio-modelling literature rather than round numbers near the Basel values. |
| `exposures.pd_dispersion` | The real within-pool dispersion of obligor PDs, which drives the IFRS 9 stage 2 share — presently 0.75 in log PD because it produced a believable answer. |
| `ifrs9.LGD_DOWNTURN_ELASTICITY` | A grounded downturn-LGD relationship in place of a linear guess. |
| `pnl` desk betas | Observed revenue sensitivities to volatility and activity. |

A market-risk text would also close the FRTB gaps listed under **Next** — the
full CSR bucket grid and the cross-bucket correlation matrices — and a
securitisation text would open item 3.

### The honest framing

This does not make the model more *correct* in the regulatory sense; the rules
are already implemented as published. It makes the model's behaviour defensible
rather than merely plausible, which is a different and harder claim, and the one
`DESIGN.md` currently declines to make.

## Next

1. **Import the Bank of England's published stress scenario.** The single
   highest-value change. `scenario.py` already takes arbitrary macro paths; the
   annual cyclical scenario variable paths are published as a spreadsheet.
   Replacing `_acs_severe` with the real thing turns a stylised stress into a
   comparable one.
2. **Close out the FRTB simplifications.** Full vega risk weights per bucket,
   proper curvature (re-price the book under the prescribed up and down shocks
   rather than taking CVR as an input), and the published cross-bucket
   correlation matrices. The current SBM is structurally right but its vega and
   curvature numbers are indicative.
3. **Securitisation.** SEC-SA and SEC-IRBA, plus the correlation trading
   portfolio. A wholesale bank with a structured credit business cannot be
   modelled without it, and it is the one whole risk type currently missing.
4. **Quarterly rather than annual periods.** Capital, liquidity and P&L are all
   reported quarterly; annual steps hide the intra-year trough that a stress
   test is actually looking for.

## After that

5. **A proper ALM book.** Repricing gaps by bucket, basis risk, and IRRBB
   (economic value of equity and net interest income sensitivity under the six
   prescribed shocks). Currently NII is a reduced-form model with a structural
   hedge bolted on.
6. **Pillar 2A from first principles** rather than as an input: concentration
   risk, IRRBB, pension risk, operational risk add-ons. That would let the model
   show how a business-mix change moves the requirement, which is presently
   exogenous.
7. **Ring-fencing.** Kingsgate is outside the perimeter. Modelling a group with
   a ring-fenced body and a non-ring-fenced bank, each with its own capital and
   liquidity, is where the UK framework gets genuinely distinctive — and where
   the FPC's 2026 review is heading.
8. **Management actions in stress.** Real stress tests allow cost reduction,
   RWA optimisation, AT1 coupon cancellation and asset sales. Only the last two
   are modelled, and crudely.
9. **A resolution module.** Bail-in waterfall, the order in which instruments
   absorb loss, and whether MREL resources are actually sufficient given where
   the losses land.

## Structural

10. **A reporting layer beyond plain text.** The repository already has a
    static dashboard builder for the CDS work; the same pattern would serve
    here — a filterable HTML view of the projection with the Pillar 3 tables
    per year.
11. **Calibration against real disclosures.** Take a published Pillar 3 report,
    reconstruct the firm's book at the level of detail the disclosures permit,
    and check the model reproduces the disclosed RWAs by risk type. That is the
    only real test of whether the engines are right.
12. **Sensitivity and attribution.** Decompose the CET1 drawdown into
    impairment, RWA inflation, revenue loss and distributions — the walk that
    every stress test result presents and that the model currently leaves the
    reader to infer.
