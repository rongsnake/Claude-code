"""
Cities and sovereigns.

A city is a node the house can open a branch in. Each has a prosperity curve by
era — how much deposit and lending business a branch there can attract, 0 to 1
— and the sovereign whose defaults land on anyone holding its paper.

The prosperity numbers are STYLISED: they are a reading of each city's weight
in European (then world) finance, not a measured series. The dates each city
opens and the sovereign it answers to are HISTORICAL.

Prosperity is keyed by era id. A city absent from an era cannot be opened in
it; a city present at 0.0 can be opened but will earn nothing.
"""

CITIES = [
    {
        "id": "venice", "name": "Venice", "region": "Italy",
        "sovereign": "venice", "opens": 1300,
        "prosperity": {"rialto": 1.00, "medici": 0.95, "princes": 0.70, "northern": 0.35,
                       "country": 0.10, "lombard": 0.05, "basel": 0.05},
        "blurb": "The Rialto. Giro banking, the Levant galleys, forced loans to the Commune.",
    },
    {
        "id": "florence", "name": "Florence", "region": "Italy",
        "sovereign": "florence", "opens": 1300,
        "prosperity": {"rialto": 0.90, "medici": 1.00, "princes": 0.55, "northern": 0.20,
                       "country": 0.05, "lombard": 0.05, "basel": 0.05},
        "blurb": "The super-companies, then the Medici. Papal banking and the wool trade.",
    },
    {
        "id": "genoa", "name": "Genoa", "region": "Italy",
        "sovereign": "genoa", "opens": 1300,
        "prosperity": {"rialto": 0.70, "medici": 0.60, "princes": 0.95, "northern": 0.50,
                       "country": 0.10, "lombard": 0.05, "basel": 0.05},
        "blurb": "Rival of Venice; from 1557 the Habsburgs' bankers and masters of the exchange fairs.",
    },
    {
        "id": "rome", "name": "Rome", "region": "Italy",
        "sovereign": "papacy", "opens": 1300,
        "prosperity": {"rialto": 0.60, "medici": 0.80, "princes": 0.50, "northern": 0.25,
                       "country": 0.10, "lombard": 0.05, "basel": 0.05},
        "blurb": "The Curia's banker collects tithes across Christendom and moves them without coin.",
    },
    {
        "id": "bruges", "name": "Bruges", "region": "Low Countries",
        "sovereign": "burgundy", "opens": 1300,
        "prosperity": {"rialto": 0.75, "medici": 0.85, "princes": 0.20, "northern": 0.05,
                       "country": 0.02, "lombard": 0.02, "basel": 0.02},
        "blurb": "The north's exchange, until the Zwin silts and Antwerp takes the trade.",
    },
    {
        "id": "london", "name": "London", "region": "England",
        "sovereign": "england", "opens": 1300,
        "prosperity": {"rialto": 0.45, "medici": 0.50, "princes": 0.45, "northern": 0.70,
                       "country": 1.00, "lombard": 1.00, "basel": 1.00},
        "blurb": "Wool, then the Crown's debts, then everyone's. Lombard Street is named for your predecessors.",
    },
    {
        "id": "avignon", "name": "Avignon", "region": "France",
        "sovereign": "papacy", "opens": 1309,
        "prosperity": {"rialto": 0.65, "medici": 0.25, "princes": 0.05},
        "blurb": "The popes are here from 1309 to 1377, and so is their money.",
    },
    {
        "id": "lyon", "name": "Lyon", "region": "France",
        "sovereign": "france", "opens": 1420,
        "prosperity": {"medici": 0.55, "princes": 0.80, "northern": 0.35, "country": 0.15,
                       "lombard": 0.10, "basel": 0.10},
        "blurb": "Four fairs a year; the French crown's banker and the Italians' clearing house.",
    },
    {
        "id": "antwerp", "name": "Antwerp", "region": "Low Countries",
        "sovereign": "spain", "opens": 1480,
        "prosperity": {"medici": 0.30, "princes": 1.00, "northern": 0.30, "country": 0.10,
                       "lombard": 0.10, "basel": 0.10},
        "blurb": "The Bourse of 1531, the pepper and silver trade, and the Fuggers' counter. Sacked in 1576.",
    },
    {
        "id": "augsburg", "name": "Augsburg", "region": "Germany",
        "sovereign": "empire", "opens": 1450,
        "prosperity": {"medici": 0.40, "princes": 0.75, "northern": 0.20, "country": 0.05,
                       "lombard": 0.05, "basel": 0.05},
        "blurb": "The Fuggers and the Welsers: Tyrolean silver, Hungarian copper, the Emperor's election.",
    },
    {
        "id": "seville", "name": "Seville", "region": "Spain",
        "sovereign": "spain", "opens": 1500,
        "prosperity": {"princes": 0.85, "northern": 0.45, "country": 0.10, "lombard": 0.05, "basel": 0.05},
        "blurb": "Where the silver fleets land, and where the Crown impounds them.",
    },
    {
        "id": "amsterdam", "name": "Amsterdam", "region": "Low Countries",
        "sovereign": "netherlands", "opens": 1585,
        "prosperity": {"princes": 0.40, "northern": 1.00, "country": 0.60, "lombard": 0.25, "basel": 0.20},
        "blurb": "The Wisselbank, the VOC, the first stock exchange and the first bubble.",
    },
    {
        "id": "frankfurt", "name": "Frankfurt", "region": "Germany",
        "sovereign": "empire", "opens": 1600,
        "prosperity": {"northern": 0.35, "country": 0.40, "lombard": 0.35, "basel": 0.40},
        "blurb": "The Rothschilds' first house; later the Bundesbank's and the ECB's city.",
    },
    {
        "id": "paris", "name": "Paris", "region": "France",
        "sovereign": "france", "opens": 1600,
        "prosperity": {"northern": 0.45, "country": 0.55, "lombard": 0.55, "basel": 0.45},
        "blurb": "Law's Mississippi scheme, the haute banque, the Crédit Mobilier.",
    },
    {
        "id": "edinburgh", "name": "Edinburgh", "region": "Scotland",
        "sovereign": "england", "opens": 1695,
        "prosperity": {"country": 0.45, "lombard": 0.35, "basel": 0.30},
        "blurb": "Free banking, the Ayr Bank, and the City of Glasgow's unlimited shareholders.",
    },
    {
        "id": "new_york", "name": "New York", "region": "United States",
        "sovereign": "usa", "opens": 1790,
        "prosperity": {"country": 0.30, "lombard": 0.80, "basel": 1.00},
        "blurb": "Wall Street. After 1914 the dollar's centre; after 1945 the world's.",
    },
    {
        "id": "hong_kong", "name": "Hong Kong", "region": "Asia",
        "sovereign": "england", "opens": 1842,
        "prosperity": {"lombard": 0.35, "basel": 0.65},
        "blurb": "Ceded by the Treaty of Nanking in 1842: the China trade, then Asia's dollar market.",
    },
    {
        "id": "singapore", "name": "Singapore", "region": "Asia",
        "sovereign": "singapore", "opens": 1965,
        "prosperity": {"basel": 0.55},
        "blurb": "The Asian dollar market from 1968; where Barings' Leeson sat.",
    },
    {
        "id": "zurich", "name": "Zürich", "region": "Switzerland",
        "sovereign": "switzerland", "opens": 1850,
        "prosperity": {"lombard": 0.30, "basel": 0.50},
        "blurb": "Neutral money, private banking, and the Basel Committee's neighbours.",
    },
    # ---- the wider world: hinted at on the map until their era opens them
    {
        "id": "lisbon", "name": "Lisbon", "region": "Portugal",
        "sovereign": "portugal", "opens": 1300,
        "prosperity": {"rialto": 0.30, "medici": 0.40, "princes": 0.75, "northern": 0.35,
                       "country": 0.20, "lombard": 0.10, "basel": 0.10},
        "blurb": "The Tagus and the Casa da Índia: after 1498 the pepper of Malabar lands here first.",
    },
    {
        "id": "alexandria", "name": "Alexandria", "region": "Levant",
        "sovereign": "levant", "opens": 1300,
        "prosperity": {"rialto": 0.70, "medici": 0.70, "princes": 0.30, "northern": 0.15,
                       "country": 0.10, "lombard": 0.25, "basel": 0.10},
        "blurb": "Where the Red Sea's spices meet the Venetian galleys, under the Mamluk sultan's customs.",
    },
    {
        "id": "constantinople", "name": "Constantinople", "region": "Levant",
        "sovereign": "levant", "opens": 1300,
        "prosperity": {"rialto": 0.60, "medici": 0.40, "princes": 0.45, "northern": 0.30,
                       "country": 0.20, "lombard": 0.15, "basel": 0.15},
        "blurb": "Venice's quarter and Genoa's Pera; after 1453 the Sultan's capital and the Black Sea's market.",
    },
    {
        "id": "hamburg", "name": "Hamburg", "region": "Germany",
        "sovereign": "hanse", "opens": 1300,
        "prosperity": {"rialto": 0.30, "medici": 0.35, "princes": 0.30, "northern": 0.45,
                       "country": 0.50, "lombard": 0.45, "basel": 0.30},
        "blurb": "The Hanse's North Sea gate; its Bank of 1619 copies Amsterdam's; Berenberg since 1590.",
    },
    {
        "id": "goa", "name": "Goa", "region": "India",
        "sovereign": "portugal", "opens": 1510,
        "prosperity": {"princes": 0.60, "northern": 0.40, "country": 0.15},
        "blurb": "Albuquerque takes it in 1510: the Estado da Índia's capital and the Carreira's eastern end.",
    },
    {
        "id": "canton", "name": "Canton", "region": "China",
        "sovereign": "china", "opens": 1557,
        "prosperity": {"princes": 0.35, "northern": 0.40, "country": 0.65, "lombard": 0.35, "basel": 0.30},
        "blurb": "Through Macau from 1557, then the Thirteen Factories: China sells tea and silk and wants only silver.",
    },
    {
        "id": "batavia", "name": "Batavia", "region": "East Indies",
        "sovereign": "voc", "opens": 1619,
        "prosperity": {"northern": 0.60, "country": 0.50, "lombard": 0.30, "basel": 0.15},
        "blurb": "Coen founds it in 1619 as the VOC's Asian headquarters: nutmeg, cloves, and the inter-Asian trade.",
    },
    {
        "id": "bombay", "name": "Bombay", "region": "India",
        "sovereign": "eic", "opens": 1668,
        "prosperity": {"northern": 0.20, "country": 0.45, "lombard": 0.60, "basel": 0.40},
        "blurb": "Catherine of Braganza's dowry, leased to the Company in 1668: cotton, opium for China, and later the Raj's port.",
    },
    {
        "id": "calcutta", "name": "Calcutta", "region": "India",
        "sovereign": "eic", "opens": 1690,
        "prosperity": {"country": 0.60, "lombard": 0.55, "basel": 0.20},
        "blurb": "Job Charnock's factory of 1690; after Plassey in 1757 the capital of the Company's Bengal.",
    },
    {
        "id": "sydney", "name": "Sydney", "region": "Australia",
        "sovereign": "england", "opens": 1788,
        "prosperity": {"country": 0.05, "lombard": 0.25, "basel": 0.35},
        "blurb": "A penal colony in 1788; wool, then gold in 1851, and the Bank of New South Wales from 1817.",
    },
    {
        "id": "buenos_aires", "name": "Buenos Aires", "region": "Argentina",
        "sovereign": "argentina", "opens": 1810,
        "prosperity": {"country": 0.15, "lombard": 0.45, "basel": 0.20},
        "blurb": "Independent from 1810; Barings' loan of 1824 defaults in 1827, and the boom of the 1880s is Barings' undoing.",
    },
    {
        "id": "tokyo", "name": "Tokyo", "region": "Japan",
        "sovereign": "japan", "opens": 1868,
        "prosperity": {"lombard": 0.30, "basel": 0.75},
        "blurb": "Edo renamed in 1868: the Meiji state, the zaibatsu banks, and from 1980 the world's largest lenders.",
    },
    {
        "id": "dubai", "name": "Dubai", "region": "Gulf",
        "sovereign": "gulf", "opens": 1971,
        "prosperity": {"basel": 0.40},
        "blurb": "A pearling town that became the Gulf's financial centre; the DIFC from 2004.",
    },
]
#: The deposit pool: how much money the financial world has to place, at the
#: start of each era, in thousands of the display currency, for a city at full
#: prosperity. The engine interpolates geometrically between anchors and scales
#: by each city's prosperity; no one house can hold more than a share of it.
#: This is what anchors the game to historical scale — a bench on the Rialto
#: cannot become the Medici in a generation however well it lends — and it is
#: STYLISED: a reading of the order of magnitude of deposits available in the
#: leading centre of each age, not a measured series.
DEPOSIT_POOL = {
    1300: 300,            # thousand ducats: the Rialto banks together
    1400: 600,            # Florence and Venice at the Medici's founding
    1500: 2_000,          # the Antwerp century opens
    1600: 8_000,          # guilders: Amsterdam and the VOC
    1700: 25_000,         # pounds: London after the Bank's founding
    1850: 150_000,        # the joint-stock banks and the discount market
    1950: 5_000_000,      # the clearers after the war
    2027: 3_000_000_000,  # about £3 trillion of UK deposits
}
#: The largest share of a city's pool one house can hold. STYLISED.
MAX_POOL_SHARE = 0.30
#: Good borrowers are scarcer than depositors think: the lending market the
#: house can reach is this multiple of the deposits it can attract. Money
#: beyond it sits in state debt. STYLISED.
LENDING_MARKET = 1.3

#: Sovereigns the house can lend to. `base_yield` is the premium a prince pays
#: above merchant lending in the era given; `reliability` is a prior on
#: repayment that the scripted defaults then override. STYLISED, tuned so that
#: lending to princes is the best-paying and worst-ending thing you can do.
#: `seat` is the city where the court sits, which is where its banner stands on
#: the map; a house with a branch there can reach it. `from`/`until` bound a
#: court that did not always exist — the two chartered companies. HISTORICAL.
SOVEREIGNS = {
    "venice":      {"name": "the Republic of Venice",   "title": "the Doge",              "reliability": 0.90, "seat": "venice"},
    "florence":    {"name": "the Commune of Florence",  "title": "the Signoria",          "reliability": 0.75, "seat": "florence"},
    "genoa":       {"name": "the Republic of Genoa",    "title": "the Doge of Genoa",     "reliability": 0.80, "seat": "genoa"},
    "papacy":      {"name": "the Papacy",               "title": "His Holiness",          "reliability": 0.85, "seat": "rome",
                    "seat_by_year": [(1309, "avignon"), (1377, "rome")]},
    "england":     {"name": "the Crown of England",     "title": "the King of England",   "reliability": 0.55, "seat": "london"},
    "france":      {"name": "the Crown of France",      "title": "the King of France",    "reliability": 0.50, "seat": "paris"},
    "burgundy":    {"name": "the Duchy of Burgundy",    "title": "the Duke of Burgundy",  "reliability": 0.45, "seat": "bruges",
                    "until": 1482},  # Mary of Burgundy d. 27 Mar 1482; the Low Countries pass to the Habsburgs
    "spain":       {"name": "the Spanish Habsburgs",    "title": "the Catholic King",     "reliability": 0.35, "seat": "seville"},
    "empire":      {"name": "the Holy Roman Emperor",   "title": "the Emperor",           "reliability": 0.45, "seat": "augsburg"},
    "netherlands": {"name": "the United Provinces",     "title": "the States General",    "reliability": 0.90, "seat": "amsterdam"},
    "usa":         {"name": "the United States",        "title": "the Treasury",          "reliability": 0.95, "seat": "new_york"},
    "china":       {"name": "the Qing Empire",          "title": "the Son of Heaven",     "reliability": 0.50, "seat": "canton"},
    "singapore":   {"name": "Singapore",                "title": "the Republic",          "reliability": 0.95, "seat": "singapore"},
    "switzerland": {"name": "the Swiss Confederation",  "title": "the Confederation",     "reliability": 0.98, "seat": "zurich"},
    # foreign governments borrowing in the London market: their chests go to
    # the market they borrow in, not to their own capitals
    "emerging":    {"name": "foreign governments",      "title": "a foreign finance ministry", "reliability": 0.60, "seat": "london"},
    # the wider world
    "portugal":    {"name": "the Crown of Portugal",    "title": "the King of Portugal",  "reliability": 0.60, "seat": "lisbon"},
    "levant":      {"name": "the Sultanate",            "title": "the Sultan",            "reliability": 0.55, "seat": "constantinople"},
    "hanse":       {"name": "the Free City of Hamburg", "title": "the Senate of Hamburg", "reliability": 0.90, "seat": "hamburg"},
    "argentina":   {"name": "the Argentine Republic",   "title": "the Argentine finance ministry", "reliability": 0.45, "seat": "buenos_aires"},
    "japan":       {"name": "the Empire of Japan",      "title": "the Ministry of Finance", "reliability": 0.85, "seat": "tokyo"},
    "gulf":        {"name": "the Emirate",              "title": "the Ruler",             "reliability": 0.80, "seat": "dubai"},
    "india":       {"name": "the Government of India",  "title": "the Viceroy",           "reliability": 0.85, "seat": "calcutta"},
    # the chartered companies, which governed territory and borrowed like states.
    # The EIC's governing body was literally the Court of Directors, which sat
    # in East India House on Leadenhall Street; the VOC's Heeren XVII met in
    # Amsterdam. Their seats are where their courts met, not where they ruled.
    "voc":         {"name": "the Dutch East India Company", "title": "the Heeren XVII",   "reliability": 0.75, "seat": "amsterdam",
                    "from": 1602, "until": 1800},  # chartered 20 Mar 1602; nationalised 1796, charter lapsed 31 Dec 1799
    "eic":         {"name": "the East India Company",   "title": "the Court of Directors", "reliability": 0.80, "seat": "london",
                    "from": 1600, "until": 1874},  # charter 31 Dec 1600; dissolved by the East India Stock Dividend Redemption Act 1873, effective 1 Jun 1874
}
