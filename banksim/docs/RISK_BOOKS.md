# The risk books — library map and build plan

Mapped 20 September 2026. Standing permission to draw on these was recorded on
19 September; this closes the two questions that note left open — what the
books are, and how a figure taken from them gets tagged.

## Where they are, and how this session reaches them

Gareth's path is `pinas/riskbooks` — the piNAS. That filesystem is not
reachable from this build container. What *is* reachable, through the Google
Drive connector, is the Drive copy at **`RiskBooks/`** (owner gcburton@gmail.com,
folder id `1tl7lYw9G7CTJQPbYB35QKhoZ-SD9zFyL`), and it has the same content.
Treat Drive as the working copy and the NAS as canonical.

**Read path that works:** `read_file_content` on a title's PDF returns clean
extracted text, tables included. The chapter HTMLs are 1–6 MB each (base64
images inline) and are the wrong tool for reading; the PDF is the right one.

## Layout

Three levels below `RiskBooks/`, one folder per title:

```
RiskBooks/
  RiskBooks_download_plan.csv   <- the master catalogue (regime, wave, bank_model,
                                   tier, theme, title, url, why)
  RiskBooks_mapped.csv          <- earlier tiered map, superseded by the plan
  Banking/                      <- 49 titles, bank_model = Y, 3 waves, 13 themes
  Insurance (Solvency II)/      <- 8 titles, not for this build
  Risk Misc/                    <- 42 titles, not for this build
    Wave N - <theme>/
      <title>/
        <title>.pdf             <- 2–25 MB, the file to read
        <title>.epub
        cover.png
        chapters/
          NN - <chapter title>.html   <- risk.net LaTeXML capture, one per chapter
```

The chapter HTML format, and its defects, are documented in the
`risk-books-pdf` skill: body in `.chapter-page-content`, footnotes as
`span.ltx_note`, tables as `table.ltx_tabular`. The capture is known to drop
`$` signs, em dashes and some en dashes, so year ranges glue ("2007–15" becomes
"200715"), "US$5–10 billion" becomes "US510 billion", and "0–25bp" becomes
"025bp". **Any number lifted from a chapter must be read against that list
before it goes near the model.** The PDF was typeset from the same capture and
carries the same artefacts where they were not repaired.

## Upload status

Uploading was in progress when mapped (folders created 04:27–05:52Z on
20 September). **39 of the 49 banking titles** had folders with the PDF
present. The ten not yet present:

- Landmarks in XVA · Margin in Derivatives Trading *(Wave 1, counterparty)*
- The Basel Handbook 2nd ed *(Wave 1, regulatory capital)*
- Network Theory and Financial Risk · Portfolio Compression · Systemic
  Operational Risk · Systemic Risk Assessment and Oversight, 1st and 2nd eds
  *(Wave 2, systemic risk)*
- The Handbook of ALM, 1st and 2nd eds *(Wave 3, ALM)*

Re-list the wave folder before assuming a title is absent.

## The banking catalogue, with Drive ids

Wave and theme folders (under `Banking/`, id `1ZQCDV1INVp5MxC1Ru0E-ucWa0VmwJETs`):

| Wave · theme | Folder id |
|---|---|
| 1 · Counterparty risk, collateral & margin | `1kgciaSnnBw1E7KwWacxMSpU9DiEVt0D4` |
| 1 · Credit derivatives & CDS | `1kbKJAGD0kugUgPJnmwdihNHs-e9jK8jW` |
| 1 · Credit risk & modelling | `1J0f-TJmi1S54P9671uVRILSLebuxarVa` |
| 1 · Regulatory capital & Basel | `1l83S9Qg_EO_PCzZBpl8JE-vC3N-PvLoY` |
| 2 · Accounting & impairment | `1cInvCDqYX0v8vHz1C1kWwdIzxmFSBkLY` |
| 2 · Credit risk & modelling | `1JaefvZMSe2H6TgaYyPO0ZpjmE9kUaQsV` |
| 2 · Market risk & FRTB | `1MpfLHJu3hSS6JTyMt9phOZrpGcOII7BX` |
| 2 · Model risk & validation | `1E1Hvjjins-56mTtkmphZl2T7Wo7jnsaL` |
| 2 · Regulatory capital & Basel | `1dvWhKpC-EIHodSFPcnMtOnJ0hz1_z36V` |
| 2 · Stress testing & economic capital | `1oQRVM-QRr_EwT37ALz-UjuhQr4X_8fdT` |
| 2 · Systemic risk & market structure | `1xATDOnP9LFAj4nG8vTYd_Zi22FJtInrZ` |
| 3 · ALM, IRRBB & liquidity | `1kEXabRmdNgo3D3neqKD7oE8IVFiMizkT` |
| 3 · Operational, conduct & non-financial risk | `1FK5vf_T_zbAKMv69NgseF-54IpoQinDL` |

Title folders present, with the PDF file id where already fetched
(list the folder for the rest — one call each):

| Title | Folder id | PDF id |
|---|---|---|
| Collateral and Financial Plumbing (2nd Impression) | `1stqXYoYAPTcSenxWBYhjrJpCHCEQgj3b` | |
| Collateral Markets and Financial Plumbing (3rd ed) | `163xKfE9xvuymF_9F8Zr9trO7aPHw6f9S` | |
| Counterparty Risk Management: Measurement, Pricing and Regulation | `11IM0dEZc14eGzs5Ce_BNdcyg2Qli-fP-` | `1HNxz8HfQUMS1LxChlV4xWGVq_4H2652E` |
| Credit Default Swaps: The Vanilla Essence | `1OLheK8ylFCtO9RFT_gJFlVzKVtxlOJC_` | |
| Credit Derivatives | `18SmS0VvJfsnUxZG3j_erIfGx1vCJ5pfz` | |
| Correlation Risk Management and Modelling | `1vxaC1wPhVIni768ETbnON1saDPK85h2t` | `1WOseB2OEfeHzv0sOIFvco7fmjtFiMhJM` |
| Credit Modelling: Advanced Topics (2nd edition) | `1NRd_oXUOVyYbTHNNa4Izx0KQYsF-DNV6` | `17o45PYn_tmoPg4i-r_TqyrT9ldONJhB6` |
| Credit Risk Measurement and Management: Disruption and Evolution | `1in2f2mGpKLZ4i-N1tpOv7I8I8nE3xCFf` | |
| Adapting to Basel III, IV and the post financial crisis era (2nd ed) | `18X4eR4wnHLQjDdhpqijhtOXU5XNVyo-y` | |
| Basel III and Beyond | `1lPedYGJvEhZcLPD7H0f1skcNNk_ltdZ3` | `1Gs74pzqt0exi5ZEqUyC4ZdGwbT6EpvN4` |
| Derivatives Markets: The New Regulatory Paradigm | `1iecI3VNyq4ekhtgNdOUP4MiTfZz6sga5` | |
| Economic Capital | `1vOln5HeaiVd1IUqWJ9SqQHmn2mfEtGTG` | `1TrRJ2-AVzZeqOotcS1skbbUQYVxNI4zQ` |
| Firm-wide Stress Testing and Economic Capital | `1nmmdpDtETuToxcxiT4lF5pX43GC_Kn63` | |
| The CECL Handbook: A Practitioner's Guide | `1QgAh6TfrjrkNR78PwaVN-cCloW9Lrz-G` | |
| The New Impairment Model under IFRS 9 | `1pbKTQan8ubZbRBKYdcYw87DvkwtqoWfl` | `1rHaei5ZuFApnYLS58o0cJhcqNEjeuUVE` |
| Country and Political Risk (2nd edition) | `1ZhCLux4NS6eS5HAb6sbwnFQHasS_k3Lv` | |
| Hedging Wisely | `1Tx2P2KyZi7TDZs035KtemM6m_l5PCi5O` | |
| Reinventing Retail Lending Analytics (Breeden) | `1llTxdocPWqPUUgBxz4m96N17DXnMA2JQ` | |
| Tail Risk Hedging | `1WjaJGc7iDMaIC4lUFPT9kZXX_LizrK09` | |
| The Handbook of Corporate Financial Risk (2nd ed) | `1XZVmWqV9VPrwvbpZL6_LpKOGCsahELJp` | |
| Market Risk Modelling (2nd edition) | `1cgngL5hUVdq4ygtbcuECFqIL15xZcH8G` | |
| The FRTB: Concepts, Implications and Implementation (Sharma & Beckwith) | `19z0jie-fpYlTo9x-OzYLd8nluUYdFrXM` | `1r3TToDhkoqd_8-Yoh-oT1G6xy7Id-tlq` |
| Model Risk and Uncertainty | `1JHrZciOUxRHW0KE0OyWc6FVTwH-PR8j-` | |
| Risk Model Validation (2nd edition) | `1iPAXy2RGkMf9oclahFNWt4zHLxn6IX3_` | |
| BCBS 239: Guiding Principles for Compliance | `1u5SgynCNuaYCTa-5mNrBod25NGMDZ152` | |
| Risk, Capital and Value-Based Management | `1GZVNuHEp-mmkpJSJs2f5WTMa4n-eSBKx` | |
| CCAR and Beyond | `1O0ZLgPIZ7cT78FCRwSpo0UlvkrnNZDGQ` | |
| Stress Testing for Financial Institutions | `1jWDHmnLRwm8QlAMryQkRkH69Lx2ZCNHo` | |
| Stress Testing: Approaches, Methods and Applications, 1st ed | `1cESplKhE0MUghLhzm4DWrgue5-OiS-eE` | |
| Stress Testing: Approaches, Methods and Applications, 2nd ed | `1pmrgpXyGXrveSX9hgFlsM0GB2cuSvXLQ` | `1aW5FgUSzOgmK1g70E1S4X-z-Tfhm-DOv` |
| Europe's New Supervisory Tool | `1-BsKGCqyocGo5o2TU4iDpMXcmGzSwme7` | |
| Lessons from the Financial Crisis | `1bh876jBpgeLm_wNe_fR2N6c6E39R-PJL` | |
| Managing Systemic Exposure | `1xUMj1EIrGJg01AtCponNaDDH78TNurVb` | |
| Interest Rate Risk in the Banking Book (Newson) | `17SYYuCN9UGAmSr9EeRpOpNQroTYPXKhm` | `1bQtWTekPpoyrnfJx0T37WgZW5F-o_pLh` |
| Liquidity Modelling | `1pW_frQ263NmkUcAGS2xBxQvUXXkcbeig` | |
| Liquidity Risk Management and Supervision | `13EommhTmvvywgwlL29H6P-GZQDWB6Swe` | |
| Managing Illiquid Assets | `1DNgpxBO44-r0n_ZQ6idikZnxWzE3PGDM` | |
| Operational Risk Capital Models | `1zDrl8baSk7v8UF11wodlBQdvnTbbvWxh` | |
| Operational Risk Capital Models (2nd edition) | `1Sl7qxYIfYBEJ75x2-5n6FbtwgPxYfgQK` | `1Q25rTUN3R-R72TGNCy4USBP00XzQgwXI` |

## Build map — which book grounds which part of the model

This is the point of the exercise. The regulatory parameters are already the
rules as published; what the books change is the **calibration**, and the
FRTB and scenario gaps. Ordered by value to the build.

### 1. The systematic factor — `scenario.Z_SCALE`, `SEGMENT_LOADINGS`, `ifrs9.SEGMENT_RHO`

The single most powerful dial in the model, presently tuned by eye.

- **Credit Modelling: Advanced Topics** — ch 3 *Predicting Annual Default
  Rates and Implications for Market Prices* (the empirical default-rate cycle
  the factor has to reproduce); ch 12 *Credit Cycle-dependent Stochastic Credit
  Spreads and Rating Category Transitions* (migration through the cycle, which
  is what `PD_CYCLICALITY` in the engine stands in for)
- **Correlation Risk Management and Modelling** — asset correlation by segment,
  to replace the round numbers near the Basel values in `SEGMENT_RHO`
- **Economic Capital** — the one-factor framework these all rest on, and the
  confidence-level logic behind the 99.9% in the IRB formula

### 2. Downturn LGD — `ifrs9.LGD_DOWNTURN_ELASTICITY`

- **Credit Modelling: Advanced Topics** — ch 4 *An Ensemble Model for Recovery
  Value in Default*: recovery as a function of the cycle, which is exactly the
  relationship the linear guess approximates

### 3. IFRS 9 staging — `exposures.pd_dispersion`, the SICR thresholds, the stage 2 share

- **The New Impairment Model under IFRS 9** — SICR construction, the low credit
  risk exemption in practice, and what banks actually report for stage 2 in
  a downturn (the 73% at the trough of `acs_severe` needs a benchmark)
- **The CECL Handbook** — the US analogue; useful for lifetime-loss estimation
  under multiple scenarios

### 4. FRTB — the CSR bucket grid, cross-bucket correlations, vega and curvature

The largest remaining *fidelity* gap: market risk is ~30% of Kingsgate's RWAs
and the SBM ships with collapsed correlation matrices and simplified vega.

- **The FRTB: Concepts, Implications and Implementation** (Sharma & Beckwith)
  — the full bucket tables, the gamma matrices, the vega liquidity horizons,
  and the curvature shock machinery
- **Market Risk Modelling (2nd ed)** — the method behind them

### 5. Counterparty and collateral — SA-CCR add-ons, CVA, margin

- **Counterparty Risk Management: Measurement, Pricing and Regulation** —
  exposure profiles, the alpha factor's origin, netting-set maturity
- **Collateral and Financial Plumbing** (both editions) — variation margin
  mechanics behind the NSFR derivative-netting fix, and the reverse repo book
- **Margin in Derivatives Trading**, **Landmarks in XVA** — pending upload

### 6. Scenario design — replace the stylised `acs_severe`

- **Stress Testing: Approaches, Methods and Applications** (both eds),
  **Stress Testing for Financial Institutions**, **CCAR and Beyond**,
  **Firm-wide Stress Testing and Economic Capital** — how supervisory
  scenarios are built and how banks translate macro paths into segment PDs.
  Second only to importing the Bank of England's published variable paths.

### 7. IRRBB and ALM — roadmap item 5

- **Interest Rate Risk in the Banking Book** (Newson) — value vs income
  approaches, behavioural assumptions for non-dated liabilities, the structural
  hedge. Read and confirmed extractable; ch 1 alone corrects the balance-sheet
  framing the NII model uses.
- **Liquidity Modelling**, **Liquidity Risk Management and Supervision** —
  behind the LCR/NSFR run-off and stability assumptions
- **The Handbook of ALM** (both eds) — pending upload

### 8. Operational risk — the ILM and loss distributions

- **Operational Risk Capital Models** (both eds) — what the PRA's ILM = 1
  actually switches off, and the loss-distribution basis for a Pillar 2 add-on

### 9. Pillar 2A from first principles — roadmap item 6

- **Economic Capital**, **Risk, Capital and Value-Based Management** —
  concentration risk and capital allocation, so Pillar 2A can be built rather
  than input

### 10. Framework cross-checks and validation standards

- **Basel III and Beyond**, **Adapting to Basel III, IV** — second opinions on
  the regulatory parameters, useful given they were sourced from secondary
  commentary
- **Risk Model Validation**, **Model Risk and Uncertainty** — the standard any
  of this calibration should be held to

## Reading protocol

1. Fetch the PDF text via Drive (`read_file_content` on the PDF id). Large
   books come back truncated; go chapter by chapter from the HTML only if the
   PDF cut off before the chapter needed.
2. Check every extracted number against the scrape-corruption list above.
   A glued range or a dropped `$` is not a typo to guess past; it is a reason
   to find the figure in a second place or leave it out.
3. Tag it. A figure from a textbook is neither `REGULATORY` nor `STYLISED`:
   it is **`Provenance.LITERATURE`**, and the `Assumption.source` field carries
   the citation — title, chapter, and table or page. The assumptions appendix
   then says which book a number came from.
4. Prefer a range from two books to a point from one. Where they disagree,
   record both and say why one was chosen.
5. Nothing here makes the model more *correct* in the regulatory sense. It
   makes the behaviour defensible rather than merely plausible — a different
   claim, and the one `DESIGN.md` currently declines to make.
