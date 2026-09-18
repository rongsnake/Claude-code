# Roadmap

Ordered by what would most improve the model's fidelity per unit of work.

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
