"""
The tech tree: financial innovations the house can adopt.

Civilization-style, as the player chose: each innovation becomes available at
its historical date, costs capital and sometimes standing to adopt, needs its
prerequisites, and unlocks actions or changes the engine's parameters.
Adopting early gives an edge; never adopting leaves you exposed to the thing
it protects against.

`available` is HISTORICAL — the first documented use, or the statute. `cost` is
STYLISED and expressed as a share of the house's equity, so that it scales
through seven centuries. Effects are keys the engine understands:

  unlock_class     a borrower class becomes lendable (see borrowers.py)
  unlock_funding   a liability type becomes usable
  agency           multiplies the branch agency-loss rate (lower is better)
  liquidity        adds to the effective liquidity of a class
  yield            adds to the yield of a class
  loss             multiplies the loss rate of a class
  panic            multiplies run panic (lower is better)
  branch_cost      multiplies the cost of opening and running branches
  capital_raise    allows raising outside equity (share of equity per turn)
  fraud            multiplies the chance of an internal fraud event
"""

TECHS = [
    {
        "id": "giro", "name": "Giro transfer", "available": 1300, "cost": 0.0,
        "requires": [], "starting": True,
        "effects": {"unlock_funding": "deposits"},
        "text": "Transfer between accounts by book entry on a spoken order. The thing a banco di scritta is.",
        "provenance": "HISTORICAL", "source": "Mueller (1997): tabulae cambii on the Rialto from the 13th century",
    },
    {
        "id": "bill_of_exchange", "name": "Bill of exchange", "available": 1300, "cost": 0.10,
        "requires": ["giro"],
        "effects": {"unlock_class": "trade_bills", "yield": {"merchants": 0.02}},
        "text": (
            "Pay here, collect there, in another coin at a rate you set. The Church sees "
            "exchange, not interest. Lets you earn on money without a usurious loan, and "
            "makes a foreign branch worth having."
        ),
        "provenance": "HISTORICAL", "source": "de Roover, 'cambium per litteras'; Cajetan, De cambiis (1499)",
    },
    {
        "id": "double_entry", "name": "Double-entry bookkeeping", "available": 1340, "cost": 0.08,
        "requires": ["giro"],
        "effects": {"agency": 0.60, "fraud": 0.50},
        "text": (
            "Every entry twice, debit and credit, so the books must balance and a "
            "branch manager's lies show. In Genoa by 1340; Pacioli prints it in 1494."
        ),
        "provenance": "HISTORICAL", "source": "Genoese massari ledgers 1340; Pacioli, Summa (1494)",
    },
    {
        "id": "marine_insurance", "name": "Marine insurance", "available": 1350, "cost": 0.06,
        "requires": ["bill_of_exchange"],
        "effects": {"loss": {"trade_bills": 0.70, "merchants": 0.85}},
        "text": "Premium contracts on a hull and its cargo. Genoa and Florence by the 1350s; your merchant borrowers stop drowning with their ships.",
        "provenance": "HISTORICAL", "source": "Earliest surviving premium policies, Genoa 1347",
    },
    {
        "id": "holding", "name": "Parent and branch partnerships", "available": 1400, "cost": 0.10,
        "requires": ["double_entry"],
        "effects": {"branch_cost": 0.75, "agency": 0.80},
        "text": (
            "The Medici design: a parent partnership in the seat city holds the majority "
            "of each branch, the local manager the minority, each branch with its own "
            "capital and books. Prefigures the holding company."
        ),
        "provenance": "HISTORICAL", "source": "de Roover (1963), ch. 4",
    },
    {
        "id": "accomandita", "name": "Limited partnership (accomandita)", "available": 1408, "cost": 0.12,
        "requires": ["double_entry"],
        "effects": {"branch_liability": "limited"},
        "text": (
            "Florentine statute of 1408: a sleeping partner is liable only for what he "
            "put in. The Medici used it for branches they did not trust. A branch can "
            "now fail without taking the house with it."
        ),
        "provenance": "HISTORICAL", "source": "Florentine statute on accomandita, 1408; de Roover",
    },
    {
        "id": "exchange_fairs", "name": "Exchange fairs", "available": 1460, "cost": 0.08,
        "requires": ["bill_of_exchange"],
        "effects": {"liquidity": {"trade_bills": 0.25}, "yield": {"trade_bills": 0.01}},
        "text": (
            "Geneva, then Lyon, then Besançon and Piacenza: bankers meet four times a "
            "year and net every bill against every other with almost no coin. Your "
            "bills become something you can turn into money."
        ),
        "provenance": "HISTORICAL", "source": "Boyer-Xambeu, Deleplace & Gillard, Private Money and Public Currencies",
    },
    {
        "id": "sovereign_syndicate", "name": "Syndicated sovereign loans", "available": 1520, "cost": 0.10,
        "requires": ["exchange_fairs"],
        "effects": {"loss": {"princes": 0.75}, "yield": {"princes": 0.01}},
        "text": (
            "The Genoese asiento: a consortium lends the Crown against named revenues, "
            "and a stop becomes a negotiated rescheduling into juros rather than a total "
            "loss. Defaults still hurt. They stop being fatal."
        ),
        "provenance": "HISTORICAL", "source": "Drelichman & Voth (2014) on the Genoese asientos",
    },
    {
        "id": "joint_stock", "name": "Joint-stock company", "available": 1602, "cost": 0.15,
        "requires": ["holding"],
        "effects": {"capital_raise": 0.25},
        "text": (
            "The VOC sells transferable shares to the public in 1602. You can raise equity "
            "from strangers, and they can sell it on. In England the Bubble Act of 1720 "
            "takes this away again for a century."
        ),
        "provenance": "HISTORICAL", "source": "VOC charter 1602; Bubble Act 1720; its repeal 1825",
    },
    {
        "id": "banknotes", "name": "Banknotes", "available": 1660, "cost": 0.10,
        "requires": ["giro"],
        "effects": {"unlock_funding": "notes"},
        "text": (
            "Goldsmiths' receipts that pass hand to hand become money you print. The "
            "cheapest funding there is, and the most runnable. Peel's Act of 1844 ends "
            "new issue in England."
        ),
        "provenance": "HISTORICAL", "source": "Winter, Goldsmith Banking; Bank Charter Act 1844",
    },
    {
        "id": "discounting", "name": "Bill discounting", "available": 1700, "cost": 0.06,
        "requires": ["bill_of_exchange"],
        "effects": {"liquidity": {"trade_bills": 0.30}, "unlock_class": "discount_market"},
        "text": "Buy a bill before it falls due at less than face. The London discount market, and Overend Gurney's whole business.",
        "provenance": "HISTORICAL", "source": "King, History of the London Discount Market (1936)",
    },
    {
        "id": "acceptance", "name": "Acceptance business", "available": 1760, "cost": 0.08,
        "requires": ["discounting"],
        "effects": {"yield": {"trade_bills": 0.015}, "unlock_class": "acceptances"},
        "text": (
            "Put your name on another merchant's bill for a commission and it becomes "
            "a bank bill, discountable anywhere. The merchant bank's trade, Barings to "
            "Kleinwort. In 1914 the Bank of England bought all of them."
        ),
        "provenance": "HISTORICAL", "source": "Chapman, The Rise of Merchant Banking (1984)",
    },
    {
        "id": "clearing_house", "name": "Clearing house", "available": 1773, "cost": 0.05,
        "requires": ["banknotes"],
        "effects": {"liquidity": {"cash": 0.0}, "panic": 0.85},
        "text": "The London bankers' clerks stop walking between counting-houses and meet in one room. Settlement risk falls, and so does the size of the till you need.",
        "provenance": "HISTORICAL", "source": "London Clearing House, Lombard Street, 1773",
    },
    {
        "id": "sovereign_bonds", "name": "Sovereign bond underwriting", "available": 1800, "cost": 0.12,
        "requires": ["acceptance", "joint_stock"],
        "effects": {"unlock_class": "foreign_bonds", "yield": {"princes": 0.01}},
        "text": (
            "Instead of lending the Crown your own money, sell its bonds to the public "
            "and keep the commission. Barings and Hope do it for Louisiana in 1803; "
            "Rothschild does it for everyone after Waterloo."
        ),
        "provenance": "HISTORICAL", "source": "Ziegler, The Sixth Great Power; Ferguson, The House of Rothschild",
    },
    {
        "id": "telegraph", "name": "Telegraph", "available": 1851, "cost": 0.06,
        "requires": ["clearing_house"],
        "effects": {"agency": 0.50, "branch_cost": 0.80},
        "text": "Dover–Calais cable 1851, Atlantic 1866. A branch manager can be asked a question and answer it the same day. The information lag that let Portinari ruin Bruges is over.",
        "provenance": "HISTORICAL", "source": "Submarine Telegraph Company 1851; Atlantic cable 1866",
    },
    {
        "id": "limited_liability", "name": "Limited liability", "available": 1858, "cost": 0.08,
        "requires": ["joint_stock"],
        "effects": {"liability": "limited", "capital_raise": 0.35, "panic": 0.90},
        "text": (
            "Companies Act 1862, extended to banks: a shareholder loses his shares and "
            "nothing else. Investors come who would never have risked their houses. "
            "City of Glasgow's shareholders in 1878 had not registered — and lost everything."
        ),
        "provenance": "HISTORICAL", "source": "Joint Stock Banks Act 1858; Companies Act 1862; Turner, Banking in Crisis (2014)",
    },
    {
        "id": "branch_network", "name": "Branch banking at scale", "available": 1870, "cost": 0.15,
        "requires": ["telegraph", "limited_liability"],
        "effects": {"unlock_class": "retail", "branch_cost": 0.60, "panic": 0.90},
        "text": "Hundreds of branches, one balance sheet. Deposits from the public at large, diversified by town and trade. The clearing banks' century.",
        "provenance": "HISTORICAL", "source": "Capie & Collins on the amalgamation movement",
    },
    {
        "id": "eurodollar", "name": "Eurodollar market", "available": 1957, "cost": 0.08,
        "requires": ["acceptance"],
        "effects": {"unlock_funding": "wholesale", "unlock_class": "syndicated_loans"},
        "text": "Dollars held outside America, lent from London, beyond the Fed's reach. The thing that made the City a world centre again.",
        "provenance": "HISTORICAL", "source": "Schenk, 'The origins of the Eurodollar market in London 1955–1963'",
    },
    {
        "id": "derivatives", "name": "Swaps and derivatives", "available": 1981, "cost": 0.12,
        "requires": ["eurodollar"],
        "effects": {"unlock_class": "trading_book"},
        "text": "IBM–World Bank currency swap, 1981. A markets business, and with it counterparty risk, CVA, and the trader who hides his losses in account 88888.",
        "provenance": "HISTORICAL", "source": "ISDA history; Barings 1995",
    },
    {
        "id": "securitisation", "name": "Securitisation", "available": 1985, "cost": 0.10,
        "requires": ["derivatives"],
        "effects": {"liquidity": {"mortgages": 0.30}, "yield": {"mortgages": 0.005}},
        "text": "Pool the mortgages, tranche the pool, sell the tranches. Frees capital — until 2007, when no one will buy them and the pool comes home.",
        "provenance": "HISTORICAL", "source": "Northern Rock's Granite programme; the 2007 ABCP freeze",
    },
    {
        "id": "var", "name": "Value at risk", "available": 1994, "cost": 0.08,
        "requires": ["derivatives"],
        "effects": {"loss": {"trading_book": 0.75}, "fraud": 0.70},
        "text": "One number for the whole trading book, 99% of the time. RiskMetrics, 1994. Regulators let you use it for capital in 1996. It does not cover the other 1%.",
        "provenance": "HISTORICAL", "source": "J.P. Morgan RiskMetrics (1994); Market Risk Amendment (1996)",
    },
    {
        "id": "irb", "name": "Internal ratings-based models", "available": 2007, "cost": 0.15,
        "requires": ["var", "branch_network"],
        "effects": {"capital_relief": 0.25},
        "text": "Basel II: your own PDs and LGDs set your risk weights, with permission. Capital falls — and the output floor of 2027 says it cannot fall below 72.5% of the standardised number.",
        "provenance": "HISTORICAL", "source": "BCBS Basel II (2004), UK implementation 2007; PRA PS1/26 output floor",
    },
    {
        "id": "stress_testing", "name": "Stress testing", "available": 2014, "cost": 0.08,
        "requires": ["irb"],
        "effects": {"panic": 0.80, "loss": {"trading_book": 0.90}},
        "text": "The Bank's annual scenario. Can your capital take it? If the answer is credible, so is your franchise when the next one is real.",
        "provenance": "HISTORICAL", "source": "Bank of England concurrent stress tests from 2014",
    },
]


def tech_by_id(tid: str) -> dict:
    for t in TECHS:
        if t["id"] == tid:
            return t
    raise KeyError(tid)
