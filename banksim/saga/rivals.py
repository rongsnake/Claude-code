"""
Rival houses: the real banks that shared the pool with yours, fell in the
crises they actually fell in, and can be bought when they do.

Each rival has a home city, a founding year, a size by era (the share of its
home city's deposit pool it holds — STYLISED), the cities it reaches, the
innovations it is known for, and a list of fates — HISTORICAL dates on which
it failed, was absorbed, was rescued or was gutted. While it lives it takes
pool share in its cities and competes for a court's offers; when it falls it
frees the share, adds to the panic, and goes on sale; in the turn before a
fall it is "in distress" and can be rescued at a price, which is how Barings
survived 1890.

Sizes are shares of the home pool at full prosperity. A branch city counts
0.3 of that. The reading behind the dates is in docs/SAGA.md.
"""

RIVALS = [
    {
        "id": "peruzzi", "name": "the Peruzzi", "short": "Peruzzi", "home": "florence", "founded": 1275,
        "cities": ["florence", "london", "bruges", "avignon", "venice"], "techs": ["bill_of_exchange", "double_entry"],
        "size": {"rialto": 0.30},
        "fates": [{"year": 1343, "kind": "failed", "text": "Bankrupt with Edward III owing it 600,000 florins. The second company of Florence is gone."}],
        "text": "The second of Florence's super-companies: wool, grain, the Curia's money, and the King of England's debts.",
        "provenance": "HISTORICAL", "source": "Hunt, The Medieval Super-Companies (1994)",
    },
    {
        "id": "bardi", "name": "the Bardi", "short": "Bardi", "home": "florence", "founded": 1250,
        "cities": ["florence", "london", "bruges", "avignon", "venice", "rome"], "techs": ["bill_of_exchange", "double_entry"],
        "size": {"rialto": 0.40},
        "fates": [{"year": 1346, "kind": "failed", "text": "900,000 florins owed by Edward III. The largest bank in Europe stops, and the Acciaiuoli with it."}],
        "text": "The largest bank in Europe, with branches from London to Cyprus. Lent Edward III the wool customs and more.",
        "provenance": "HISTORICAL", "source": "Hunt (1994); Russell, 'The societies of the Bardi and the Peruzzi'",
    },
    {
        "id": "medici", "name": "the Medici", "short": "Medici", "home": "florence", "founded": 1397,
        "cities": ["florence", "rome", "venice", "bruges", "london", "lyon", "avignon"], "techs": ["double_entry", "holding", "accomandita"],
        "size": {"medici": 0.40},
        "fates": [{"year": 1478, "kind": "gutted", "size_mult": 0.5, "text": "The Bruges branch is insolvent on Charles the Bold's debts; London follows. The bank contracts to Florence, Rome and Lyon."},
                  {"year": 1494, "kind": "failed", "text": "Charles VIII marches into Florence, Piero flees, the palace is sacked and the bank dissolved."}],
        "text": "Giovanni di Bicci's house: one parent, many partnerships, the Curia's account, and for seventy years a rule against lending to princes.",
        "provenance": "HISTORICAL", "source": "de Roover, The Rise and Decline of the Medici Bank (1963)",
    },
    {
        "id": "lippomano", "name": "the Lippomano", "short": "Lippomano", "home": "venice", "founded": 1480,
        "cities": ["venice"], "techs": ["giro"],
        "size": {"medici": 0.20},
        "fates": [{"year": 1499, "kind": "failed", "text": "Stops in May 1499, the day before the crowd runs on Pisani. The family never recovers its standing."}],
        "text": "A Rialto bench that grew on the Cappello brothers' capital until they retired and left Lippomano to run it.",
        "provenance": "HISTORICAL", "source": "Mueller, The Venetian Money Market; Sanudo",
    },
    {
        "id": "pisani", "name": "the Pisani–Tiepolo", "short": "Pisani", "home": "venice", "founded": 1450,
        "cities": ["venice"], "techs": ["giro"],
        "size": {"medici": 0.25, "princes": 0.35},
        "fates": [{"year": 1584, "kind": "failed", "text": "Propped by the Mint in 1576, the last private bank on the Rialto succumbs to a run. Three years later Venice founds a public bank instead."}],
        "text": "Survived the run of 1499 when the crowd came for its coin and found it. By 1570 the only private bank left in Venice.",
        "provenance": "HISTORICAL", "source": "Mueller (1997)",
    },
    {
        "id": "fugger", "name": "the Fuggers", "short": "Fugger", "home": "augsburg", "founded": 1487,
        "cities": ["augsburg", "antwerp", "rome", "seville", "venice"], "techs": ["double_entry", "holding", "sovereign_syndicate"],
        "size": {"medici": 0.20, "princes": 0.50, "northern": 0.15},
        "fates": [{"year": 1557, "kind": "gutted", "size_mult": 0.35, "text": "Spain's bankruptcy converts the Fuggers' asientos into juros worth a fraction. The Habsburgs' bankers for forty years will never be so again."},
                  {"year": 1657, "kind": "failed", "text": "The last Fugger counting-house closes. The family keeps its titles and its land."}],
        "text": "Jakob the Rich: Tyrolean silver, Hungarian copper, the Emperor's election bought for 850,000 florins. The richest house in Europe.",
        "provenance": "HISTORICAL", "source": "Ehrenberg, Capital and Finance in the Age of the Renaissance; Steinmetz, The Richest Man Who Ever Lived",
    },
    {
        "id": "welser", "name": "the Welsers", "short": "Welser", "home": "augsburg", "founded": 1476,
        "cities": ["augsburg", "antwerp", "lyon", "seville"], "techs": ["double_entry"],
        "size": {"princes": 0.25, "northern": 0.05},
        "fates": [{"year": 1614, "kind": "failed", "text": "Matthäus Welser's bankruptcy. Venezuela, lent to the Emperor, did not pay."}],
        "text": "The Fuggers' Augsburg rivals; held Venezuela as a fief from Charles V and lost money on it.",
        "provenance": "HISTORICAL", "source": "Ehrenberg",
    },
    {
        "id": "genoese", "name": "the Genoese", "short": "Genoese", "home": "genoa", "founded": 1528,
        "cities": ["genoa", "antwerp", "seville", "lyon"], "techs": ["exchange_fairs", "sovereign_syndicate"],
        "size": {"princes": 0.45, "northern": 0.30},
        "fates": [{"year": 1627, "kind": "gutted", "size_mult": 0.4, "text": "Philip IV's stop of 1627 and the Portuguese New Christians who replace them. The Genoese keep their fairs and lose the crown."},
                  {"year": 1700, "kind": "absorbed", "text": "The last asientos are gone; Genoa's capital goes into other people's bonds."}],
        "text": "Spinola, Centurione, Grimaldi: the consortium that took the Spanish crown's debt from the Fuggers and ran the fairs at Piacenza.",
        "provenance": "HISTORICAL", "source": "Drelichman & Voth (2014)",
    },
    {
        "id": "backwell", "name": "Backwell and Vyner", "short": "Backwell", "home": "london", "founded": 1650,
        "cities": ["london"], "techs": ["banknotes"],
        "size": {"northern": 0.30},
        "fates": [{"year": 1672, "kind": "failed", "text": "The Stop of the Exchequer. Backwell owed £295,000 by the Crown; Vyner £416,000. Both are ruined, and their depositors with them."}],
        "text": "The greatest goldsmith-bankers of Lombard Street, lending the Crown next year's revenue against orders on the Exchequer.",
        "provenance": "HISTORICAL", "source": "Winter, Goldsmith Banking; Roseveare",
    },
    {
        "id": "hoare", "name": "Hoare's", "short": "Hoare's", "home": "london", "founded": 1672,
        "cities": ["london"], "techs": ["banknotes"],
        "size": {"northern": 0.05, "country": 0.05, "lombard": 0.02, "basel": 0.01},
        "fates": [],
        "text": "At the sign of the Golden Bottle on Fleet Street. Still owned by the family. Never failed, never grew much, never had to.",
        "provenance": "HISTORICAL", "source": "Hutchings, Messrs Hoare Bankers (2005)",
    },
    {
        "id": "san_giorgio", "name": "the Casa di San Giorgio", "short": "San Giorgio", "home": "genoa", "founded": 1407,
        "cities": ["genoa"], "techs": ["giro", "double_entry"],
        "size": {"medici": 0.20, "princes": 0.25, "northern": 0.20, "country": 0.10},
        "fates": [{"year": 1805, "kind": "absorbed", "text": "Napoleon annexes the Ligurian Republic and dissolves the Casa. Four centuries as the Republic's creditor, tax-farmer and bank end with a decree."}],
        "text": "The Republic of Genoa's creditors, organised as a company that collected its taxes, governed Corsica, and kept a bank of deposit.",
        "provenance": "HISTORICAL", "source": "Fratianni, 'Government Debt, Reputation and Creditors' Protections: The Tale of San Giorgio' (2006)",
    },
    {
        "id": "berenberg", "name": "Berenberg", "short": "Berenberg", "home": "hamburg", "founded": 1590,
        "cities": ["hamburg", "london"], "techs": ["bill_of_exchange", "acceptance"],
        "size": {"northern": 0.15, "country": 0.15, "lombard": 0.08, "basel": 0.01},
        "fates": [],
        "text": "Founded by Flemish Protestants fleeing Antwerp. Never failed, never sold; the oldest bank of its kind still trading.",
        "provenance": "HISTORICAL", "source": "Berenberg house history; Hauschild-Thiessen (1990)",
    },
    {
        "id": "palmer", "name": "Palmer & Co.", "short": "Palmer", "home": "calcutta", "founded": 1780,
        "cities": ["calcutta", "london"], "techs": ["bill_of_exchange"],
        "size": {"country": 0.35},
        "fates": [{"year": 1830, "kind": "failed", "text": "John Palmer, 'the prince of merchants', stops in January 1830 with debts of some £5 million, lent to indigo planters who could not pay. The other agency houses follow by 1834."}],
        "text": "The greatest of Calcutta's agency houses: deposits from the Company's servants, loans to indigo and to Indian princes.",
        "provenance": "HISTORICAL", "source": "Webster, The Twilight of the East India Company (2009)",
    },
    {
        "id": "jardine", "name": "Jardine Matheson", "short": "Jardine", "home": "hong_kong", "founded": 1832,
        "cities": ["canton", "hong_kong", "london"], "techs": ["acceptance"],
        "size": {"country": 0.15, "lombard": 0.20, "basel": 0.03},
        "fates": [],
        "text": "Founded in Canton on opium and tea; moved to Hong Kong in 1842 and never looked back. A taipan's house, not a bank, but everyone's banker in the treaty ports.",
        "provenance": "HISTORICAL", "source": "Keswick (ed.), The Thistle and the Jade (1982)",
    },
    {
        "id": "hope", "name": "Hope & Co.", "short": "Hope", "home": "amsterdam", "founded": 1762,
        "cities": ["amsterdam", "london"], "techs": ["joint_stock", "sovereign_bonds"],
        "size": {"country": 0.35},
        "fates": [{"year": 1813, "kind": "absorbed", "text": "After the French occupation the house passes to its London correspondent. Baring Brothers own the name."}],
        "text": "Amsterdam's great house: Russian, Swedish, Portuguese loans, and half of Louisiana with Barings.",
        "provenance": "HISTORICAL", "source": "Buist, At Spes Non Fracta: Hope & Co 1770–1815",
    },
    {
        "id": "barings", "name": "Barings", "short": "Barings", "home": "london", "founded": 1762,
        "cities": ["london", "amsterdam", "new_york", "singapore"], "techs": ["acceptance", "sovereign_bonds"],
        "size": {"country": 0.20, "lombard": 0.12, "basel": 0.03},
        "fates": [{"year": 1890, "kind": "rescued", "size_mult": 0.5, "text": "£21 million of Argentine paper and insolvent. The Governor's guarantee fund, raised from every house in the City in a weekend, lets it be liquidated and refounded as a limited company."},
                  {"year": 1995, "kind": "failed", "text": "Nick Leeson's futures positions in Singapore, hidden in account 88888: £827 million. Sold to ING for £1."}],
        "text": "Francis Baring's house: trade, then acceptance, then sovereign loans. 'The sixth great power.'",
        "provenance": "HISTORICAL", "source": "Ziegler, The Sixth Great Power (1988)",
    },
    {
        "id": "rothschild", "name": "N M Rothschild", "short": "Rothschild", "home": "london", "founded": 1809,
        "cities": ["london", "frankfurt", "paris"], "techs": ["sovereign_bonds", "acceptance"],
        "size": {"country": 0.30, "lombard": 0.15, "basel": 0.02},
        "fates": [],
        "text": "Nathan Mayer's house: the Waterloo bullion, the 1818 French loans, every sovereign issue of the century. Still private.",
        "provenance": "HISTORICAL", "source": "Ferguson, The House of Rothschild (1998)",
    },
    {
        "id": "overend", "name": "Overend, Gurney & Co.", "short": "Overend", "home": "london", "founded": 1800,
        "cities": ["london"], "techs": ["discounting"],
        "size": {"country": 0.15, "lombard": 0.25},
        "fates": [{"year": 1866, "kind": "failed", "text": "Refused by the Bank as insolvent on 9 May; suspends at 3.30 on the 10th. Black Friday, and the lender of last resort born the same afternoon."}],
        "text": "The corner house: the greatest discount house in the world, until it went into shipping and railways with money it had borrowed at call.",
        "provenance": "HISTORICAL", "source": "Bank of England Quarterly Bulletin 2016 Q4",
    },
    {
        "id": "glasgow", "name": "the City of Glasgow Bank", "short": "City of Glasgow", "home": "edinburgh", "founded": 1839,
        "cities": ["edinburgh"], "techs": ["branch_network"],
        "size": {"lombard": 0.15},
        "fates": [{"year": 1878, "kind": "failed", "text": "£6 million of losses hidden by false accounts. Unlimited: 1,819 shareholders called for £2,750 a share, 1,565 of them ruined."}],
        "text": "133 branches and a board that lent to itself and to Australian sheep.",
        "provenance": "HISTORICAL", "source": "Turner, Banking in Crisis (2014)",
    },
    {
        "id": "midland", "name": "the Midland Bank", "short": "Midland", "home": "london", "founded": 1836,
        "cities": ["london", "edinburgh"], "techs": ["branch_network", "limited_liability"],
        "size": {"lombard": 0.30, "basel": 0.20},
        "fates": [{"year": 1992, "kind": "absorbed", "text": "Weakened by Crocker in California, bought by HSBC. The largest bank in the world in 1934; a brand retired in 1999."}],
        "text": "Birmingham, then Threadneedle Street; by 1934 the largest bank in the world by deposits. The clearers' clearer.",
        "provenance": "HISTORICAL", "source": "Holmes & Green, Midland: 150 Years of Banking Business",
    },
    {
        "id": "morgan", "name": "J.P. Morgan", "short": "Morgan", "home": "new_york", "founded": 1871,
        "cities": ["new_york", "london", "paris"], "techs": ["sovereign_bonds", "derivatives", "var"],
        "size": {"lombard": 0.30, "basel": 0.35},
        "fates": [],
        "text": "Drexel, Morgan & Co.: stopped the panic of 1907 from a library on Madison Avenue. Split by Glass–Steagall; reunited by 1999.",
        "provenance": "HISTORICAL", "source": "Chernow, The House of Morgan (1990)",
    },
    {
        "id": "hsbc", "name": "the Hongkong and Shanghai Bank", "short": "HSBC", "home": "hong_kong", "founded": 1865,
        "cities": ["hong_kong", "london", "singapore"], "techs": ["branch_network", "eurodollar"],
        "size": {"lombard": 0.40, "basel": 0.45},
        "fates": [],
        "text": "Founded for the China trade; bought Midland in 1992 and moved its seat to London for it. A G-SIB in bucket 2 or 3 every year since the list began.",
        "provenance": "HISTORICAL", "source": "King, The History of the Hongkong and Shanghai Banking Corporation",
    },
    {
        "id": "warburg", "name": "S.G. Warburg", "short": "Warburg", "home": "london", "founded": 1946,
        "cities": ["london"], "techs": ["eurodollar", "acceptance"],
        "size": {"basel": 0.06},
        "fates": [{"year": 1995, "kind": "absorbed", "text": "After a failed merger with Morgan Stanley, bought by Swiss Bank Corporation. The last independent London investment bank of the first rank."}],
        "text": "Siegmund Warburg's house: the first Eurobond (Autostrade, 1963), the hostile takeover, Big Bang's most ambitious buyer.",
        "provenance": "HISTORICAL", "source": "Ferguson, High Financier (2010)",
    },
    {
        "id": "bcci", "name": "BCCI", "short": "BCCI", "home": "london", "founded": 1972,
        "cities": ["london", "hong_kong"], "techs": ["eurodollar"],
        "size": {"basel": 0.05},
        "fates": [{"year": 1991, "kind": "failed", "text": "Closed by the Bank of England on 5 July 1991 with $10 billion missing. Supervised in Luxembourg, booked in the Caymans, run from London."}],
        "text": "The Bank of Credit and Commerce International: a million depositors in seventy countries and no consolidated supervisor.",
        "provenance": "HISTORICAL", "source": "Bingham Report (1992)",
    },
    {
        "id": "northern_rock", "name": "Northern Rock", "short": "Northern Rock", "home": "london", "founded": 1965,
        "cities": ["london"], "techs": ["securitisation"],
        "size": {"basel": 0.04},
        "fates": [{"year": 2007, "kind": "failed", "text": "Funded three-quarters in the wholesale market, which closes in August. The first run on a British bank in 140 years, in September; nationalised in February."}],
        "text": "A Newcastle building society that became a mortgage bank with Granite, its securitisation vehicle, and 'Together' loans at 125% of value.",
        "provenance": "HISTORICAL", "source": "Treasury Committee, The Run on the Rock (2008)",
    },
    {
        "id": "lehman", "name": "Lehman Brothers", "short": "Lehman", "home": "new_york", "founded": 1850,
        "cities": ["new_york", "london"], "techs": ["derivatives", "securitisation"],
        "size": {"lombard": 0.08, "basel": 0.12},
        "fates": [{"year": 2008, "kind": "failed", "text": "15 September 2008. The largest bankruptcy in history; the interbank market closes behind it."}],
        "text": "Cotton brokers in Montgomery, Alabama; investment bankers on Wall Street; $600 billion of balance sheet at 31 times leverage.",
        "provenance": "HISTORICAL", "source": "Valukas Report (2010)",
    },
]

#: What a house's business is worth, as a share of its deposits: a deposit
#: premium of a few per cent (what Barings fetched from ING was £1 plus its
#: liabilities; what a sound franchise fetches is two to five per cent of
#: deposits), and what a rescue costs the turn before. The buyer inherits the
#: bad book, in proportion to how bad things were. STYLISED.
ACQUISITION = {
    "failed":   {"price": 0.02, "deposits_kept": 0.50, "bad_book": 0.10},
    "rescued":  {"price": 0.08, "deposits_kept": 0.85, "bad_book": 0.25},
    "absorbed": {"price": 0.05, "deposits_kept": 0.70, "bad_book": 0.04},
}
#: A branch of a rival in your city takes this share of its home size from the pool there.
BRANCH_WEIGHT = 0.3
#: How often a living rival at the same court takes the prince's business before you see it.
COURT_CONTEST = 0.35


def rival_by_id(rid: str) -> dict:
    for r in RIVALS:
        if r["id"] == rid:
            return r
    raise KeyError(rid)
