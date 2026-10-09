# Reading list — building a UK bank model from the law up

Annotated, and ordered by what each thing is *for*. Editions move; check the
library catalogue for the current one rather than trusting a year quoted here.

The short answer to "what should I get first": **Gleeson on the International
Regulation of Banking**, the **BCBS consolidated Basel Framework** (free
online), the **PRA Rulebook** (free online), and **two real Pillar 3 reports**.
Those four will take you further than any ten textbooks, because the first
explains the architecture, the middle two are the actual rules, and the last
shows you what a firm has to produce at the end of it.

---

## 1. The spine: capital regulation as a lawyer sees it

**Simon Gleeson, *Gleeson on the International Regulation of Banking* (OUP).**
The single most useful book for this project. It explains *why* the capital
framework is shaped the way it is — why Tier 1 and Tier 2 exist, why the trading
book and banking book are separated, why the output floor was fought over — in
prose a lawyer can follow, without either dumbing down the mathematics or
drowning in it. Read the chapters on own funds, credit risk, the trading book
and Pillar 2 before writing a line of code.

**Simon Gleeson and Guido Guerrera, *The Law and Regulation of Bank Resolution*
(OUP).** For the MREL and resolution layer. The reason a UK bank's liability
stack has a HoldCo senior non-preferred tranche at all is resolution law, not
capital law, and this is where that comes from.

**Ross Cranston, Emilios Avgouleas, Kristin van Zwieten, Christopher Hare and
Theodor van Sante, *Principles of Banking Law* (OUP).** The standard English
academic-practitioner treatment. Chapters on bank regulation, deposit-taking
and payment give you the legal characterisation of the balance-sheet items you
are modelling.

**Michael Blair, George Walker and Robert Purves (eds), *Financial Services Law*
(OUP).** Broader and more regulatory-structural. Useful for the FSMA
architecture, the PRA/FCA split, the threshold conditions and the supervisory
process that sits behind "Pillar 2A" and "the PRA buffer".

---

## 2. Banker and customer, and the liability side

**Paget's Law of Banking (LexisNexis).** The practitioner reference on the
banker-customer relationship. Matters more than it looks: the legal nature of a
deposit is what makes it a liability of the bank, and the distinction between
operational and non-operational deposits — worth 25 percentage points of LCR
run-off — is ultimately a question about the contract and the relationship.

**Ellinger's Modern Banking Law (OUP, Ellinger, Lomnicka and Hare).** More
analytical than Paget's; better on set-off, combination of accounts and the
customer's mandate.

**Encyclopaedia of Banking Law (LexisNexis, loose-leaf).** The thing to consult
rather than read.

---

## 3. The asset side: lending, security and credit risk mitigation

**Philip Wood, *Law and Practice of International Finance* series (Sweet &
Maxwell).** Particularly *International Loans, Bonds, Guarantees, Legal
Opinions*; *Comparative Law of Security Interests and Title Finance*; and
*Set-Off and Netting, Derivatives, Clearing Systems*. Wood is the reason you can
reason about whether a guarantee or a piece of collateral will actually work in
an insolvency — which is exactly the question the credit risk mitigation rules
ask before they let you reduce a risk weight.

**Louise Gullifer and Jennifer Payne, *Corporate Finance Law: Principles and
Policy* (Hart).** Outstanding on the debt/equity boundary, subordination, and
why regulators care about the difference. The best treatment of what makes an
instrument loss-absorbing, which is the whole of AT1 and Tier 2 eligibility.

**Agasha Mugasha, *The Law of Multi-Bank Financing* / LMA documentation.** For
the mechanics of revolving credit facilities: commitment, drawdown,
cancellability. Whether a facility is "unconditionally cancellable" is a
drafting question with a 10% credit conversion factor attached to it.

**Sir Roy Goode, *Principles of Corporate Insolvency Law* (Sweet & Maxwell).**
Because loss given default is an insolvency-law question wearing a number.

---

## 4. The trading book and derivatives

**Simon Firth, *Derivatives: Law and Practice* (Sweet & Maxwell, loose-leaf).**
The practitioner text on the ISDA architecture. Close-out netting and the
enforceability of the netting opinion are what allow SA-CCR to be computed on a
net rather than gross basis — the single largest number in a dealer's
counterparty credit exposure.

**Schuyler Henderson, *Henderson on Derivatives* (LexisNexis).** Complementary
to Firth; stronger on credit derivatives, which given your CDS work will be
familiar ground.

**Alastair Hudson, *The Law on Financial Derivatives* (Sweet & Maxwell).** More
conceptual.

**Philip Wood, *Set-Off and Netting* (above).** The netting chapter is the
foundation of the whole counterparty credit framework.

---

## 5. Accounting, because half the model is accounting

**EY, *International GAAP* (Wiley).** The IFRS 9 chapters — impairment,
classification and measurement, hedge accounting. The three-stage ECL model,
significant increase in credit risk, and multiple economic scenarios are all
there in detail, with the interpretive questions banks actually argue about.

**PwC, *Manual of Accounting* / Deloitte *iGAAP*.** Alternatives; use whichever
the library has.

Why it matters: regulatory expected loss and accounting ECL are different
numbers computed over the same book, and the gap between them is deducted from
CET1 (shortfall) or added to Tier 2 (excess). You cannot model capital without
modelling the accounts.

---

## 6. Primary sources — free, authoritative, and the real answer

These are not background reading. They are the specification.

- **PRA Rulebook** (`prarulebook.co.uk`). The binding UK rules. The Parts that
  matter here: Own Funds and Eligible Liabilities; Credit Risk: Standardised
  Approach; Credit Risk: Internal Ratings Based Approach; Counterparty Credit
  Risk; Credit Valuation Adjustment Risk; Market Risk: General Provisions and
  the Market Risk Parts; Operational Risk; Output Floor; Leverage Ratio;
  Liquidity Coverage Ratio; Net Stable Funding Ratio; Disclosure (CRR).
- **BCBS, the consolidated Basel Framework** (`bis.org/basel_framework`). The
  international text, hyperlinked and navigable by paragraph. CRE for credit
  risk, MAR for market risk, OPE for operational risk, LCR/NSFR for liquidity.
  Where this codebase cites a formula, this is where it comes from.
- **PRA PS1/26, *Implementation of Basel 3.1: Final rules*** (20 January 2026).
  The final UK rules, applying from 1 January 2027. Read it alongside PS9/24,
  which it finalises.
- **PRA PS11/26, *Disclosure*** (26 March 2026). What a UK firm must actually
  publish, including the MREL templates.
- **Bank of England, *The Bank of England's approach to setting MREL*** and the
  annual external MREL publication.
- **FPC Financial Stability Reports and the *Financial Stability in Focus*
  papers on the bank capital framework.** For the direction of travel on
  leverage, buffer usability and the interaction between the CCyB, the O-SII
  buffer and Pillar 2A.
- **Bank of England stress test publications** (the annual cyclical scenario
  variable paths and results). If you want this model's stress scenario to be
  real rather than stylised, this is the file to import.

---

## 7. Read two or three real Pillar 3 reports cover to cover

Nothing substitutes for this. Pick banks with different shapes:

- a large universal UK bank with a ring-fenced body (HSBC, Barclays, NatWest,
  Lloyds) — for the full template set and the ring-fencing structure;
- a wholesale/markets-led firm — for the trading book, SA-CCR and CVA
  disclosures that dominate this model;
- a mid-sized specialist lender — for what the framework looks like without a
  trading book, and how the Strong and Simple / SDDT regime changes it.

Read them next to the annual report: the Pillar 3 gives you RWAs, own funds and
ratios; the annual report gives you the income statement, the IFRS 9 staging
tables and the scenario weights. The model in this repository needs both, and
the two must reconcile.

---

## 8. If you want the quantitative side

- **Michael Ong (ed), *The Basel Handbook*** — dated but clear on the IRB
  formula's derivation.
- **BCBS, *An Explanatory Note on the Basel II IRB Risk Weight Functions***
  (2005, free). Eleven pages, and the single best explanation of where the
  asset correlation, the 99.9% confidence level and the maturity adjustment
  come from. Read it before `banksim/credit_risk.py`.
- **Oldrich Vasicek, *Loan Portfolio Value*** (Risk, 2002). The one-factor
  model that both the IRB formula and this repository's IFRS 9 macro
  conditioning rest on.
