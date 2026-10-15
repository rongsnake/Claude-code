"""
Eras: the spans of the game, how fast time passes in each, which city is the
centre of gravity, and which rules apply.

Rules are flags and numbers the engine reads each turn. They change at era
boundaries and, within eras, through scripted events (see events.py) — the
1866 suspension of Peel's Act creates the lender of last resort mid-era, for
instance. The era table gives the opening state; events overwrite fields.

Turn length is what the player chose: five-year turns until 1600, then faster
as history gets denser, annual from 1950. 257 turns in all.

Currency is displayed, not modelled: the engine keeps one unit and each era
names it and scales it. That is a simplification — the ducat and the florin
were near-equal gold coins, sterling was not — and it is labelled STYLISED.
A nominal drift per era lets balance sheets grow the way the real ones did.
"""

ERAS = [
    {
        "id": "rialto",
        "name": "Banchi di scritta",
        "subtitle": "The bench on the Rialto",
        "start": 1300, "end": 1400, "turn_years": 5,
        "centre": "venice",
        "currency": "ducats", "currency_symbol": "d.", "nominal_drift": 0.000,
        "intro": (
            "Under the porticoes of San Giacomo di Rialto, bankers sit at benches with "
            "a ledger open. Merchants hold accounts and pay one another by a spoken "
            "order to the scribe; no coin moves. The deposits are lent — to merchants "
            "fitting out galleys for the Levant, to the Commune in wartime, and into "
            "pepper and copper on the banker's own account. The Church forbids "
            "interest, so profit hides inside the bill of exchange. Banks fail often, "
            "and when they fail the state does not save them."
        ),
        "rules": {
            "usury": "ban",             # interest only through exchange; plain loans earn little
            "usury_cap": None,
            "liability": "unlimited",   # partners liable to the last ducat
            "joint_stock": False,
            "lolr": False,              # no lender of last resort
            "deposit_insurance": False,
            "supervision": "none",      # none | sureties | reserve | prudential | basel
            "reserve_floor": 0.0,       # required liquid share of deposits
            "capital_regime": None,     # see borrowers.CAPITAL_REGIMES
            "notes_allowed": False,
            "gold_standard": False,
            "own_account_trade": True,  # banker may trade commodities on own book
        },
        "provenance": "HISTORICAL",
        "source": "Mueller, The Venetian Money Market (1997); Lane & Mueller, Money and Banking in Medieval and Renaissance Venice",
    },
    {
        "id": "medici",
        "name": "The Medici century",
        "subtitle": "Branches, partners and princes",
        "start": 1400, "end": 1500, "turn_years": 5,
        "centre": "venice",
        "currency": "ducats", "currency_symbol": "d.", "nominal_drift": 0.000,
        "intro": (
            "Florence shows how a house grows: not one firm but a parent partnership "
            "holding majority stakes in separately capitalised branches — Rome, Venice, "
            "Bruges, London, Lyon — each with its own manager holding a minority. "
            "Limited partnership by accomandita keeps a foreign branch's debts away "
            "from the parent. The temptation is the same everywhere: a prince who wants "
            "money and will remember who gave it. Lending to princes was banned in the "
            "Medici until 1471; seven years later Bruges was gone."
        ),
        "rules": {
            "usury": "ban", "usury_cap": None,
            "liability": "unlimited", "joint_stock": False,
            "lolr": False, "deposit_insurance": False,
            "supervision": "sureties", "reserve_floor": 0.0,
            "capital_regime": None, "notes_allowed": False,
            "gold_standard": False, "own_account_trade": True,
        },
        "provenance": "HISTORICAL",
        "source": "de Roover, The Rise and Decline of the Medici Bank 1397–1494 (1963)",
    },
    {
        "id": "princes",
        "name": "Princes and fairs",
        "subtitle": "Habsburg asientos and the Genoese",
        "start": 1500, "end": 1600, "turn_years": 5,
        "centre": "antwerp",
        "currency": "ducats", "currency_symbol": "d.", "nominal_drift": 0.010,
        "intro": (
            "Silver from the Americas and a Habsburg empire that never has enough of "
            "it. The Fuggers finance Charles V and are gutted by Spain's stop of 1557; "
            "the Genoese take the crown's debt through asientos and juros and run their "
            "own exchange fairs, where Europe's bankers meet four times a year to net "
            "their bills with almost no coin. Philip II stops payment in 1557, 1560, "
            "1575 and 1597. Antwerp is the centre until the Spanish Fury of 1576; then "
            "the money moves north. Venice gets its first bank supervisor in 1524 and "
            "its first public bank in 1587, after its last private one dies in a run."
        ),
        "rules": {
            "usury": "ban", "usury_cap": None,
            "liability": "unlimited", "joint_stock": False,
            "lolr": False, "deposit_insurance": False,
            "supervision": "sureties", "reserve_floor": 0.0,
            "capital_regime": None, "notes_allowed": False,
            "gold_standard": False, "own_account_trade": True,
        },
        "provenance": "HISTORICAL",
        "source": "Drelichman & Voth, Lending to the Borrower from Hell (2014); Ehrenberg, Capital and Finance in the Age of the Renaissance",
    },
    {
        "id": "northern",
        "name": "The northern shift",
        "subtitle": "Wisselbank, goldsmiths and the Bank of England",
        "start": 1600, "end": 1700, "turn_years": 5,
        "centre": "amsterdam",
        "currency": "guilders", "currency_symbol": "fl.", "nominal_drift": 0.005,
        "intro": (
            "Amsterdam founds its Wisselbank in 1609 on the Venetian model and gives "
            "the Dutch a unit of account the whole world trusts. The East India Company "
            "sells shares to the public. In London goldsmiths become bankers: they take "
            "deposits, issue notes against them, and lend to the Crown against next "
            "year's taxes — until Charles II stops the Exchequer in 1672 and the "
            "greatest of them go down. The answer, in 1694, is a bank of the state's "
            "own, on the Amsterdam pattern. Interest is now lawful, but capped."
        ),
        "rules": {
            "usury": "cap", "usury_cap": 0.06,
            "liability": "unlimited", "joint_stock": True,
            "lolr": False, "deposit_insurance": False,
            "supervision": "none", "reserve_floor": 0.0,
            "capital_regime": None, "notes_allowed": True,
            "gold_standard": False, "own_account_trade": True,
        },
        "provenance": "HISTORICAL",
        "source": "Quinn & Roberds on the Wisselbank; Winter, Goldsmith Banking: A History; Kynaston, Till Time's Last Sand",
    },
    {
        "id": "country",
        "name": "Country banks and the City",
        "subtitle": "Bubbles, bills and the Bank Charter Act",
        "start": 1700, "end": 1850, "turn_years": 3,
        "centre": "london",
        "currency": "pounds", "currency_symbol": "£", "nominal_drift": 0.008,
        "intro": (
            "London is the centre now. The South Sea Bubble bursts in 1720 and the "
            "Bubble Act freezes the joint-stock company for a century. Merchant houses "
            "— Barings from 1762 — trade goods, then accept bills, then float "
            "sovereign loans; the Louisiana Purchase is a Barings bond. Country banks "
            "spring up on a landowner's name and a printing press: the Ayr Bank's notes "
            "are two-thirds of Scotland's currency when it fails in 1772. The panic of "
            "1825 closes a tenth of them, and Parliament answers with joint-stock banks, "
            "then in 1844 with Peel's Act fixing the note issue to gold."
        ),
        "rules": {
            "usury": "cap", "usury_cap": 0.05,
            "liability": "unlimited", "joint_stock": False,   # Bubble Act 1720; events relax
            "lolr": False, "deposit_insurance": False,
            "supervision": "none", "reserve_floor": 0.0,
            "capital_regime": None, "notes_allowed": True,
            "gold_standard": True, "own_account_trade": True,
        },
        "provenance": "HISTORICAL",
        "source": "Pressnell, Country Banking in the Industrial Revolution; Kosmetatos, The 1772–73 British Credit Crisis",
    },
    {
        "id": "lombard",
        "name": "Lombard Street",
        "subtitle": "The lender of last resort",
        "start": 1850, "end": 1950, "turn_years": 2,
        "centre": "london",
        "currency": "pounds", "currency_symbol": "£", "nominal_drift": 0.012,
        "intro": (
            "Overend Gurney asks the Bank of England for help on 9 May 1866 and is "
            "refused as insolvent; the next day it stops, Peel's Act is suspended, and "
            "the lender of last resort is born — Bagehot writes it down in 1873. Only "
            "one joint-stock bank in six founded since 1844 survives the year. Limited "
            "liability arrives by statute; City of Glasgow in 1878 shows what the "
            "unlimited kind does to shareholders. Barings is rescued by a guarantee "
            "fund in 1890. In 1914 the Stock Exchange shuts for five months and the "
            "Bank buys the accepting houses' bills. Sterling leaves gold in 1931."
        ),
        "rules": {
            "usury": "none", "usury_cap": None,
            "liability": "unlimited", "joint_stock": True,   # limited liability by event 1858/62
            "lolr": False, "deposit_insurance": False,        # LOLR by event 1866
            "supervision": "none", "reserve_floor": 0.0,
            "capital_regime": None, "notes_allowed": False,   # Peel's Act: issue concentrated at the Bank
            "gold_standard": True, "own_account_trade": True,
        },
        "provenance": "HISTORICAL",
        "source": "Bagehot, Lombard Street (1873); Bank of England Quarterly Bulletin 2016 Q4, 'The demise of Overend Gurney'",
    },
    {
        "id": "basel",
        "name": "From Eurodollars to Basel",
        "subtitle": "Deregulation, capital rules and the G-SIB",
        "start": 1950, "end": 2027, "turn_years": 1,
        "centre": "london",
        "currency": "pounds", "currency_symbol": "£", "nominal_drift": 0.035,
        "intro": (
            "The Eurodollar market makes London the world's offshore banker from the "
            "late 1950s. Competition and Credit Control in 1971 lets credit loose and "
            "the secondary banking crisis follows; the clearers' Lifeboat lends 40% of "
            "their capital to keep the fringe afloat. Big Bang, 1986. Basel I in 1988 "
            "is the first capital rule a British bank ever had: 8% of risk-weighted "
            "assets. BCCI, Barings, 2008, ring-fencing. From 2011 the FSB names the "
            "banks whose failure would matter everywhere, and charges them for it. "
            "That list is where this game ends."
        ),
        "rules": {
            "usury": "none", "usury_cap": None,
            "liability": "limited", "joint_stock": True,
            "lolr": True, "deposit_insurance": False,          # 1979 by event
            "supervision": "prudential", "reserve_floor": 0.08,  # liquidity ratios of the period
            "capital_regime": None,                             # basel1 by event 1988
            "notes_allowed": False, "gold_standard": False, "own_account_trade": True,
        },
        "provenance": "HISTORICAL",
        "source": "Capie, The Bank of England 1950s to 1979; Reid, The Secondary Banking Crisis; BCBS 1988; FSB G-SIB methodology",
    },
]


def era_for_year(year: int) -> dict:
    for era in ERAS:
        if era["start"] <= year < era["end"]:
            return era
    return ERAS[-1]


def total_turns() -> int:
    return sum((e["end"] - e["start"]) // e["turn_years"] for e in ERAS)
