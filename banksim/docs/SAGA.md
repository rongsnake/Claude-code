# The Long Ledger — design notes

A turn-based game, in the manner of *Colonization*: one banking house from a
bench on the Rialto in 1300 to the FSB's list of global systemically important
banks. `banksim/saga.html`, built by `python -m banksim.saga.build`; a single
file, no server, deploys by copying.

The Kingsgate simulator (`dashboard.html`) is the modern era's engine seen from
the inside. This is the seven centuries that lead up to it.

## What was decided, and why

| Question | Choice | Consequence |
|---|---|---|
| Play style | Turn-based strategy | Each turn you set the lending mix, the coin kept in the till, the partners' drawings; open branches; adopt innovations; answer the court. Then history happens. |
| Where it runs | One HTML page | The Python side owns the history (`banksim/saga/*.py`) and the tests; the page's JavaScript plays the turns. Same pattern as the dashboard. |
| World | Fictional house, real history | Edward III, Charles the Bold, Philip II, Charles II, the Ayr Bank, Overend Gurney, Lehman — all land on whoever is exposed. Your house is invented; nothing else is. |
| Pacing | Era-scaled turns | 5-year turns to 1600, then 3, 2, and annual from 1950: 257 turns. History is densest where the rules change fastest. |
| Innovations | Civ-style tree | Bill of exchange, double-entry, *accomandita*, exchange fairs, joint-stock, banknotes, discounting, acceptance, telegraph, limited liability, Eurodollars, derivatives, securitisation, VaR, IRB, stress testing. Available from their historical date, bought with capital, with prerequisites. |
| Failure | Permadeath | A run you cannot meet, assets below deposits, a prince who has had enough, or two years under the capital minimum. You see what killed you and start again; the seed replays the same history. |
| The seat | Follow the money | Each era one city is the centre of gravity (Venice → Antwerp → Genoa → Amsterdam → London → New York → London). Sitting there grows deposits a fifth faster; moving costs 12% of capital and the old prince's goodwill. The seat may end anywhere: the win is designation, not London. |

## The turn

1. **Events** whose year falls in the turn fire: sovereign defaults, panics,
   plagues, trade and market shocks, rule changes, moves of the centre, offers
   from a court. All scripted in `events.py`, dated and sourced.
2. **Funding.** Deposits move toward what the house's capital and name can
   attract, with inertia; each branch's take is capped at a share of its
   city's deposit pool. Notes and wholesale funding are set as shares of
   deposits where the age and the tech allow. Every liability-side change
   arrives or leaves as coin — the double entry is kept.
3. **Rebalance** earning assets toward the weights, limited by what each book
   can realise in a turn. Money beyond the lending market goes into state debt.
4. **Income and costs.** Yields by class and era; the usury ban cuts plain
   lending's return unless it is dressed as exchange; the running costs of the
   house, heavy in the Middle Ages and thinner since; branch costs.
5. **Losses.** Base loss rates with lognormal noise; event shocks scaled by
   each class's sensitivity and the house's exposure to the cities hit;
   scripted sovereign defaults on exactly the paper you hold; agency losses at
   branches you do not control.
6. **Profit, tax (from 1965), drawings** — the MDA caps the payout inside the
   buffers from 2014.
7. **The run.** Panic from events and from your own losses; withdrawals
   against what can be found. In a panic the market for your paper collapses
   with it, so only the till counts when it matters. After 1866 a solvent house
   is lent to at a penalty; after 1979 (UK) and 1933 (US) deposit insurance
   mutes the panic. Insolvent is insolvent.
8. **Supervision.** Reserve ratios where they existed; from 1988 the Basel
   regimes with risk weights by class, IRB relief from 2007, the output floor
   from 2027; leverage ratio from 2014; resolution after two years under the
   minimum.
9. **Standing** — with the merchants, each court, and the regulator — drifts
   with results and choices and feeds back into deposits, offers and mercy.
10. **G-SIB score** from 2011: size, interconnectedness, substitutability,
    complexity, cross-jurisdictional activity, 20% each; 130 bps designates.

## The rival houses

Twenty-two real banks share the table (`rivals.py`): the Peruzzi and the
Bardi, the Medici, the Lippomano and the Pisani–Tiepolo on the Rialto, the
Fuggers and the Welsers, the Genoese, Backwell and Vyner, Hoare's, Hope & Co.,
Barings, Rothschild, Overend Gurney, the City of Glasgow Bank, the Midland,
J.P. Morgan, the Hongkong and Shanghai Bank, Warburg, BCCI, Northern Rock and
Lehman. Each has a home city, a founding year, a size by era (a share of its
home pool — STYLISED), the cities it reaches, the innovations its people know,
and its fates: HISTORICAL dates on which it failed, was absorbed, was rescued
or was gutted, each coinciding with a scripted event.

While a rival lives it **takes its share of each city's pool** — your
deposit and lending capacity there is what is left — and **competes at
court**: a prince whose city it reaches sometimes gives it the loan before
you see it, less often the higher your standing. When it **falls** it frees
the share, adds to the panic in the cities where you share a counter, and
its business goes on sale by the liquidator at a deposit premium of 2%, with
half the deposits kept and a tenth of them bad. **The turn before** a fall or
a rescue it is in distress, and can be rescued at 8% with most of the
deposits and a quarter of them bad — which is 1890, and what the Governor's
guarantee fund was for. Buying a house brings its people: the innovations it
knew are half the price to adopt. The Houses panel ranks you by deposits
against the living; the end screen counts the houses you outlived and the
ones you bought.

The fates that are also events of yours: Edward III's default kills the
Peruzzi and the Bardi; Nancy guts the Medici; Spain's 1557 stop guts the
Fuggers; the Stop of the Exchequer kills Backwell; Overend Gurney and City of
Glasgow fall on their days; Barings is rescued in 1890 and sold for £1 in
1995 (and if you have a Singapore desk and no VaR, a one-in-two chance of
their trader is yours); BCCI is closed; Northern Rock and Lehman fall in
2007 and 2008.

## Honesty: what is historical and what is a dial

Every era, city, innovation and event carries a `provenance`.

**HISTORICAL** — the dates, the shape of each shock, the sequence of rule
changes, the tech tree's availability dates and prerequisites, the Basel risk
buckets, the G-SIB categories and surcharges. Sources are in the data files;
the reading that produced them is summarised below.

**STYLISED** — every number that makes it a game: yields and loss rates by
class and era; city prosperity curves; the deposit pool (the size of the
financial world in each age, anchored to the order of magnitude of a leading
house's deposits: 300k ducats on the Rialto in 1300, £25m in London in 1700,
£3 trillion in 2027); the lending market as 1.3× the deposits reachable; the
running costs of the house (4% of assets a year in 1300, 1.5% now); offer
sizes and yields; panic magnitudes; the G-SIB indicator scalings. These were
tuned by headless playthroughs so that a prudent house survives seven
centuries and ends at the Kingsgate scale (£10–18bn of capital), an ambitious
one with nine branches and wholesale funding is designated in the 2020s at
about 135 bps, and a reckless one (4% in the till, lends every prince) dies at
the Ayr Bank, 1793, 1811 or Overend Gurney.

**The currency is displayed, not modelled.** One internal unit runs through;
eras name it ducats, guilders, pounds. The ducat and the florin were close
cousins; sterling was not. A nominal drift per era grows balance sheets the way
inflation did. This is a known simplification.

**Not modelled**: exchange rates between branches, the bill's maturity
structure, individual counterparties, the Church as a borrower distinct from
the papacy's deposits, wars as anything but shocks and forced loans,
competitors as anything but the pool's other claimants, the dilution of a
rights issue, AT1 and Tier 2 capital, LCR and NSFR beyond a proxy, Pillar 2A
beyond a flat add-on, ring-fencing's actual mechanics.

## The history behind the eras

Compiled from the sources listed in each era record; the search that produced
them is in the session log. Short form:

- **Rialto, 1300–1400.** *Banchi di scritta* under the porticoes of San
  Giacomo; transfers by spoken order; lending to merchants, the Commune and
  commodities on own account. The 1340s failures came from illiquidity, not a
  single bad borrower; a public bank was proposed and refused in 1374; the
  state supervised rather than rescued. Florence's Peruzzi (1343) and Bardi
  (1346) died on Edward III's default of ~1.5m florins, having first tied up
  their deposits. The Church forbade interest; profit lived in the exchange
  rate of a bill between two cities; "dry exchange" was the condemned shortcut.
- **Medici, 1400–1500.** A parent partnership holding majorities in
  separately capitalised branches, each with a managing minority partner;
  *accomandita* (Florence, 1408) for the ones they did not trust. The ban on
  lending to princes lifted in 1471; Portinari in Bruges lent Charles the Bold
  twice the branch's capital; Charles died at Nancy in 1477 and the branch in
  1478. Venice's run of 1499 followed war debt and the fleet lost at Zonchio.
- **Princes and fairs, 1500–1600.** Fuggers to Habsburgs, gutted in 1557;
  Genoese *asientos* and *juros*; fairs at Besançon then Piacenza (1579) where
  Europe's bankers netted bills four times a year. Philip II stopped payment
  in 1557, 1560, 1575, 1596. Antwerp sacked in 1576; Venice's last private
  bank fell in 1584 and the Banco della Piazza di Rialto opened in 1587.
- **Northern shift, 1600–1700.** Wisselbank (1609) on the Venetian model;
  the VOC's transferable shares; London goldsmiths lending to the Crown
  against next year's taxes until the Stop of the Exchequer (1672); the Bank
  of England (1694) on the Amsterdam pattern. Usury now capped, not banned.
- **Country banks and the City, 1700–1850.** South Sea (1720) and the Bubble
  Act; Barings (1762): trade, acceptance, sovereign bonds, Louisiana (1803);
  the Ayr Bank (1772), lending before its capital was paid in; 1825 closed a
  tenth of the country banks and produced joint-stock banking (1826); Peel's
  Act (1844) fixed the note issue.
- **Lombard Street, 1850–1950.** Overend Gurney refused as insolvent on 9 May
  1866, the Act suspended on the 10th, the lender of last resort born; Bagehot
  (1873); limited liability by statute (1858/62) and City of Glasgow (1878)
  showing the unlimited kind; Barings rescued by a guarantee fund (1890);
  August 1914; 1931 off gold.
- **Eurodollars to Basel, 1950–2027.** London's offshore dollar market from
  1957; Competition and Credit Control (1971) and the Lifeboat (1973–75);
  Banking Act 1979; Big Bang (1986); Basel I's 8% (1988), the first UK
  capital rule; BCCI (1991), Barings (1995); Basel II (2007) and Northern
  Rock; 2008; the FSB's first G-SIB list (2011); Basel III (2014);
  ring-fencing (2019); Basel 3.1 (2027).

## Playing it

Open `saga.html`. Set weights across the books you can lend to; keep a share
of runnable funding in coin — a fifth is prudent on the Rialto, more before a
war; decide the partners' drawings. Open branches where the prosperity bar is
high and the centre is going; lending to a prince needs a branch in his city.
Adopt what the age invents when you can afford it. When a court asks, decide
how much of what it asks. End the turn. Read the chronicle.

`Enter` ends the turn. The game saves itself to the browser; **New game**
takes a seed. The footer lists the rules in force.

## Testing

`banksim/tests/test_saga_data.py` — 39 tests on the data: eras tile the
timeline and turns shorten; cities' sovereigns exist and each era's centre is
prosperous; the tech tree is acyclic, monotone in time, and refers to real
classes; every class has numbers for every era it is live in and princes pay
most; every scripted default is preceded by a way of being exposed to that
sovereign; the spine of the story is present; the rivals' fates fall on the dates of scripted events and the famous ones on the right years; the build produces a page.

The engine is exercised headlessly with Playwright (`Saga.autoplay(turns,
opts)` is exposed on `window` for the purpose); the three strategies above are
the regression. That harness lives outside the repo's tests because the tests
are stdlib-only by rule.

## Roadmap

1. ~~Competitors.~~ Done: the rival houses above. Still to do for them:
   rivals that *grow* with their fortunes rather than following a table, and
   rivals that bid against you for a failed house.
2. **Exchange and remittance.** Real cross-rates between branches, so a bill
   earns what the rate says and a seat in the wrong city costs what it did.
3. **A council.** Partners with views, who leave with their capital if they
   lose the argument.
4. **Difficulty.** Successor-house mode below permadeath.
5. **The modern era on the real engine.** Replace the risk-weight table with
   calls into the Kingsgate engines for the last forty turns.
