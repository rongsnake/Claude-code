"""
Borrower classes — what the house can put its money into — and the capital
regimes that, from 1988, weight them.

Each class has, per era, a base yield and a base annual loss rate, a liquidity
score (how much of it can be turned into coin in a run, 0–1), and
sensitivities to the shocks events throw: sovereign default, trade collapse,
property, markets, plague. The engine applies tech effects on top.

All yields and loss rates are STYLISED — they are tuned so that the game's
trade-offs resemble the historical ones (princes pay best and end worst;
commodities on own account are volatile; bills are liquid once there are fairs
to clear them), not fitted to any series. Where there is a well-known number
behind a dial it is noted.

Yields are annual. The engine multiplies by turn length.
"""

#: Era ids in order, for the per-era tables below.
ERA_IDS = ["rialto", "medici", "princes", "northern", "country", "lombard", "basel"]

BORROWERS = [
    {
        "id": "cash", "name": "Coin in the till", "short": "Cash",
        "from": 1300, "liquidity": 1.00,
        "yield":  {"rialto": 0.00, "medici": 0.00, "princes": 0.00, "northern": 0.00, "country": 0.00, "lombard": 0.00, "basel": 0.02},
        "loss":   {"rialto": 0.00, "medici": 0.00, "princes": 0.00, "northern": 0.00, "country": 0.00, "lombard": 0.00, "basel": 0.00},
        "shock":  {},
        "text": "Earns nothing, answers every withdrawal. The share of deposits you keep here is the oldest decision in banking.",
    },
    {
        "id": "merchants", "name": "Loans to merchants", "short": "Merchants",
        "from": 1300, "liquidity": 0.35,
        "yield":  {"rialto": 0.09, "medici": 0.08, "princes": 0.08, "northern": 0.06, "country": 0.05, "lombard": 0.045, "basel": 0.055},
        "loss":   {"rialto": 0.030, "medici": 0.028, "princes": 0.028, "northern": 0.022, "country": 0.020, "lombard": 0.015, "basel": 0.012},
        "shock":  {"trade": 1.0, "plague": 0.8, "markets": 0.3},
        "text": "Advances to traders against goods and reputation. Under the usury ban the return has to be dressed as exchange, or it is sin.",
        "usury_exposed": True,
    },
    {
        "id": "trade_bills", "name": "Bills of exchange", "short": "Bills",
        "from": 1300, "liquidity": 0.45, "requires_tech": "bill_of_exchange",
        "yield":  {"rialto": 0.10, "medici": 0.09, "princes": 0.08, "northern": 0.055, "country": 0.045, "lombard": 0.035, "basel": 0.04},
        "loss":   {"rialto": 0.025, "medici": 0.022, "princes": 0.020, "northern": 0.015, "country": 0.012, "lombard": 0.010, "basel": 0.008},
        "shock":  {"trade": 1.2, "markets": 0.4},
        "text": "Drawn in one city, payable in another. The exchange rate carries the interest. Short-dated, self-liquidating, and the core of a merchant bank.",
    },
    {
        "id": "princes", "name": "Loans to princes", "short": "Princes",
        "from": 1300, "liquidity": 0.05,
        "yield":  {"rialto": 0.20, "medici": 0.18, "princes": 0.16, "northern": 0.10, "country": 0.07, "lombard": 0.05, "basel": 0.06},
        "loss":   {"rialto": 0.020, "medici": 0.020, "princes": 0.025, "northern": 0.020, "country": 0.010, "lombard": 0.008, "basel": 0.010},
        "shock":  {"sovereign": 1.0},
        "text": (
            "The best rate in the market and the worst collateral: a king's word. Edward III, "
            "Charles the Bold, Philip II, Charles II. Brings standing at court — and the "
            "king's enemies for yours."
        ),
    },
    {
        "id": "state_bonds", "name": "State debt", "short": "State debt",
        "from": 1300, "liquidity": 0.50,
        "yield":  {"rialto": 0.05, "medici": 0.05, "princes": 0.06, "northern": 0.045, "country": 0.035, "lombard": 0.03, "basel": 0.045},
        "loss":   {"rialto": 0.005, "medici": 0.005, "princes": 0.010, "northern": 0.005, "country": 0.002, "lombard": 0.001, "basel": 0.001},
        "shock":  {"sovereign": 0.4, "markets": 0.5},
        "text": "Venice's Monte, Castile's juros, England's consols, gilts. Funded debt of a state that taxes. Safer than a prince's promise because it is everyone's.",
    },
    {
        "id": "commodities", "name": "Trade on own account", "short": "Own account",
        "from": 1300, "liquidity": 0.15, "until": 1700,
        "yield":  {"rialto": 0.16, "medici": 0.14, "princes": 0.12, "northern": 0.10},
        "loss":   {"rialto": 0.060, "medici": 0.055, "princes": 0.050, "northern": 0.045},
        "shock":  {"trade": 1.8, "plague": 1.0, "markets": 0.8},
        "text": (
            "Pepper, copper, alum, wool, bought with depositors' money and held for the "
            "price. What the Rialto banks were doing in the 1340s when they could not "
            "pay out. Venice banned it for bankers in 1467."
        ),
    },
    {
        "id": "discount_market", "name": "Discounted bills", "short": "Discounts",
        "from": 1700, "liquidity": 0.70, "requires_tech": "discounting",
        "yield":  {"country": 0.04, "lombard": 0.03, "basel": 0.035},
        "loss":   {"country": 0.010, "lombard": 0.008, "basel": 0.006},
        "shock":  {"trade": 0.9, "markets": 0.8},
        "text": "Buy a bill at a discount, hold it to maturity or rediscount it at the Bank. The most liquid earning asset there is — until 1866, when the Bank would not.",
    },
    {
        "id": "acceptances", "name": "Acceptances", "short": "Acceptances",
        "from": 1760, "liquidity": 0.60, "requires_tech": "acceptance",
        "yield":  {"country": 0.03, "lombard": 0.025, "basel": 0.025},
        "loss":   {"country": 0.008, "lombard": 0.006, "basel": 0.005},
        "shock":  {"trade": 1.0, "sovereign": 0.5},
        "text": "Your name on a merchant's bill, for a commission. Off your balance sheet until the merchant fails; then on it, all at once. In August 1914 every accepting house in London was insolvent on paper.",
    },
    {
        "id": "foreign_bonds", "name": "Foreign loans", "short": "Foreign loans",
        "from": 1800, "liquidity": 0.40, "requires_tech": "sovereign_bonds",
        "yield":  {"country": 0.065, "lombard": 0.055, "basel": 0.07},
        "loss":   {"country": 0.030, "lombard": 0.025, "basel": 0.020},
        "shock":  {"sovereign": 1.0, "markets": 0.8},
        "text": "Latin American republics in 1825, Argentina in 1890, Russia in 1917, Mexico in 1982. You underwrite, you hold what you cannot place, and the country does not pay.",
    },
    {
        "id": "mortgages", "name": "Property and mortgages", "short": "Property",
        "from": 1700, "liquidity": 0.10,
        "yield":  {"country": 0.045, "lombard": 0.04, "basel": 0.05},
        "loss":   {"country": 0.008, "lombard": 0.006, "basel": 0.008},
        "shock":  {"property": 1.5},
        "text": "Lending on land. Slow, safe, and the thing that sinks banks when prices turn: 1866, 1973, 1990, 2008.",
    },
    {
        "id": "industry", "name": "Industrial lending", "short": "Industry",
        "from": 1800, "liquidity": 0.20,
        "yield":  {"country": 0.055, "lombard": 0.05, "basel": 0.06},
        "loss":   {"country": 0.020, "lombard": 0.015, "basel": 0.015},
        "shock":  {"markets": 0.7, "trade": 0.6},
        "text": "Mills, railways, shipyards, then everything. Term loans against the enterprise rather than the goods.",
    },
    {
        "id": "retail", "name": "Retail banking", "short": "Retail",
        "from": 1870, "liquidity": 0.15, "requires_tech": "branch_network",
        "yield":  {"lombard": 0.045, "basel": 0.055},
        "loss":   {"lombard": 0.006, "basel": 0.010},
        "shock":  {"property": 0.6, "markets": 0.2},
        "text": "Overdrafts, personal loans, cards. Granular, sticky, and from 2019 behind a ring-fence you cannot reach across.",
    },
    {
        "id": "syndicated_loans", "name": "Syndicated and Euromarket loans", "short": "Syndicated",
        "from": 1957, "liquidity": 0.30, "requires_tech": "eurodollar",
        "yield":  {"basel": 0.06},
        "loss":   {"basel": 0.018},
        "shock":  {"sovereign": 0.8, "markets": 0.6},
        "text": "Dollars lent from London to corporates and sovereigns in a syndicate. The recycling of petrodollars, and the Latin American debt crisis of 1982.",
    },
    {
        "id": "trading_book", "name": "Markets and trading", "short": "Trading",
        "from": 1981, "liquidity": 0.55, "requires_tech": "derivatives",
        "yield":  {"basel": 0.09},
        "loss":   {"basel": 0.030},
        "shock":  {"markets": 1.3, "sovereign": 0.3},
        "text": "Rates, FX, credit, equities, on your own book and your clients'. The highest return and the fattest tail. FRTB prices the tail from 2027.",
    },
]

#: Liability types. `cost` is the rate paid, per era; `runnable` is how much
#: of it can leave in a panic within a turn. STYLISED.
FUNDING = [
    {"id": "equity",    "name": "Partners' capital", "runnable": 0.0,
     "cost": {e: 0.0 for e in ERA_IDS}},
    {"id": "deposits",  "name": "Deposits", "runnable": 0.6,
     "cost": {"rialto": 0.0, "medici": 0.0, "princes": 0.0, "northern": 0.01, "country": 0.015, "lombard": 0.015, "basel": 0.025}},
    {"id": "notes",     "name": "Banknotes in circulation", "runnable": 0.8, "requires_tech": "banknotes",
     "cost": {"northern": 0.0, "country": 0.0, "lombard": 0.0, "basel": 0.0}},
    {"id": "wholesale", "name": "Wholesale and interbank", "runnable": 0.9, "requires_tech": "eurodollar",
     "cost": {"basel": 0.04}},
]

#: Capital regimes, from 1988. Risk weights by borrower class. HISTORICAL in
#: shape (Basel I's four buckets; Basel II/III's finer grid; the 3.1 output
#: floor), STYLISED in the mapping of game classes onto real exposure classes.
CAPITAL_REGIMES = {
    "basel1": {
        "name": "Basel I", "from": 1988, "minimum": 0.08, "cet1_min": 0.04,
        "buffers": 0.0, "output_floor": None,
        "rw": {"cash": 0.0, "state_bonds": 0.0, "princes": 0.0, "foreign_bonds": 1.0,
               "merchants": 1.0, "trade_bills": 0.2, "discount_market": 0.2, "acceptances": 1.0,
               "mortgages": 0.5, "industry": 1.0, "retail": 1.0, "syndicated_loans": 1.0,
               "trading_book": 1.0},
        "text": "8% of risk-weighted assets, four buckets: 0% OECD sovereigns, 20% banks, 50% mortgages, 100% everything else.",
    },
    "basel2": {
        "name": "Basel II", "from": 2007, "minimum": 0.08, "cet1_min": 0.02,
        "buffers": 0.0, "output_floor": None,
        "rw": {"cash": 0.0, "state_bonds": 0.0, "princes": 0.0, "foreign_bonds": 1.0,
               "merchants": 1.0, "trade_bills": 0.2, "discount_market": 0.2, "acceptances": 1.0,
               "mortgages": 0.35, "industry": 1.0, "retail": 0.75, "syndicated_loans": 1.0,
               "trading_book": 0.6},
        "text": "Three pillars; the standardised grid gets finer and the IRB banks model their own. Tier 1 could be 2% CET1. Which is why 2008 went the way it did.",
    },
    "basel3": {
        "name": "Basel III / CRD IV", "from": 2014, "minimum": 0.08, "cet1_min": 0.045,
        "buffers": 0.025, "output_floor": None,
        "rw": {"cash": 0.0, "state_bonds": 0.0, "princes": 0.0, "foreign_bonds": 1.0,
               "merchants": 1.0, "trade_bills": 0.2, "discount_market": 0.2, "acceptances": 1.0,
               "mortgages": 0.35, "industry": 1.0, "retail": 0.75, "syndicated_loans": 1.0,
               "trading_book": 0.9},
        "text": "CET1 of 4.5% plus a 2.5% conservation buffer, a countercyclical buffer, and a G-SIB surcharge. Leverage ratio and LCR beside it. The MDA caps your dividend inside the buffers.",
    },
    "basel31": {
        "name": "Basel 3.1", "from": 2027, "minimum": 0.08, "cet1_min": 0.045,
        "buffers": 0.025, "output_floor": 0.725,
        "rw": {"cash": 0.0, "state_bonds": 0.0, "princes": 0.0, "foreign_bonds": 1.0,
               "merchants": 1.0, "trade_bills": 0.2, "discount_market": 0.2, "acceptances": 1.0,
               "mortgages": 0.35, "industry": 1.0, "retail": 0.75, "syndicated_loans": 1.0,
               "trading_book": 1.1},
        "text": "PRA PS1/26, 1 January 2027: the revised standardised approach, unrated corporates at 65%/135%, FRTB, and an output floor so IRB cannot fall below 72.5% of standardised. Where the Kingsgate model lives.",
    },
}

#: G-SIB assessment: five categories at 20% each. The thresholds are STYLISED
#: scalings of the FSB method to this game's balance-sheet numbers; the
#: categories and the bucket surcharges are HISTORICAL (BCBS 2011, updated 2013).
GSIB = {
    "from": 2011,
    "categories": ["size", "interconnectedness", "substitutability", "complexity", "cross_jurisdictional"],
    "weight": 0.20,
    "designation_score": 130,   # basis points of the indicator score
    "buckets": [(130, 0.010), (230, 0.015), (330, 0.020), (430, 0.025), (530, 0.035)],
    "text": "Size, interconnectedness, substitutability, complexity and cross-jurisdictional activity, 20% each. 130 bps and you are on the list, with a 1% surcharge; each bucket above adds 0.5%.",
}
