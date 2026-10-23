"""The fictional world of Fjällmark Consumer Goods AB.

Everything here is invented for the bootcamp: legal entities, brands, products, plants,
distribution centres, retail trade accounts and people. Retailer names are deliberately
fictional (never real chains). The constants are the single source of truth that the
curated generators use so that all tables tell one consistent story.

Time model
----------
* master data is created before 2024 (mostly 2015-2023)
* transactions run 2024-01-01 .. 2026-09-30 (``TXN_START`` .. ``TXN_END``)
* AR/AP status, aging buckets and balances are a snapshot as of ``AS_OF_DATE``
  (period-end close 2026-09-30); the extract itself is dated ``EXTRACT_DATE``
* no event date lies after ``EXTRACT_DATE``; only forward-looking attribute columns (due
  dates, expiry/expiration dates, next-maintenance/review dates, warranty and depreciation
  end dates - "future" role in ``engine.date_role``) may lie after it, up to ``FUTURE_MAX``
"""
import datetime
import math
from decimal import Decimal

D = Decimal

TXN_START = datetime.date(2024, 1, 1)
TXN_END = datetime.date(2026, 9, 30)
AS_OF_DATE = datetime.date(2026, 9, 30)
EXTRACT_DATE = datetime.date(2026, 10, 15)
EXTRACT_TS = datetime.datetime(2026, 10, 15, 6, 0, 0)
FUTURE_MAX = datetime.date(2036, 12, 31)
MASTER_START = datetime.date(2015, 1, 1)

GROUP_CURRENCY = "EUR"
COMPANY_NAME = "Fjällmark Consumer Goods AB"
WEBSHOP = "fjallmark.example"


def months(start=TXN_START, end=TXN_END):
    """[(year, month)] for every month in the transaction window."""
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


MONTHS = months()


def month_start(y, m):
    return datetime.date(y, m, 1)


def month_end(y, m):
    nxt = datetime.date(y + (m // 12), (m % 12) + 1, 1)
    return nxt - datetime.timedelta(days=1)


def month_index(y, m):
    """0 for 2024-01, 1 for 2024-02, ..."""
    return (y - TXN_START.year) * 12 + (m - TXN_START.month)


# --------------------------------------------------------------------------------------
# legal entities, currencies, FX
# --------------------------------------------------------------------------------------

COMPANIES = [
    {"code": "SE01", "name": "Fjällmark Consumer Goods AB", "short": "Fjällmark Sweden",
     "country": "SWE", "currency": "SEK", "city": "Stockholm", "region": "SE-AB",
     "postal": "111 52", "street": "Klarabergsgatan 21", "phone": "+46 8 000 0100",
     "tax_number": "SE559900010001", "role": "Group parent - HQ, DTC Sweden, Lund and Norrköping plants",
     "classification": "parent", "language": "sv", "founded": datetime.date(2009, 3, 2)},
    {"code": "NO01", "name": "Fjällmark Norge AS", "short": "Fjällmark Norway",
     "country": "NOR", "currency": "NOK", "city": "Oslo", "region": "NO-03",
     "postal": "0150", "street": "Dronningens gate 8", "phone": "+47 22 00 01 00",
     "tax_number": "NO999000101MVA", "role": "Sales and DTC Norway",
     "classification": "subsidiary", "language": "no", "founded": datetime.date(2014, 5, 12)},
    {"code": "DK01", "name": "Fjällmark Danmark A/S", "short": "Fjällmark Denmark",
     "country": "DNK", "currency": "DKK", "city": "København", "region": "DK-84",
     "postal": "1050", "street": "Bredgade 30", "phone": "+45 33 00 01 00",
     "tax_number": "DK99000101", "role": "Sales and DTC Denmark",
     "classification": "subsidiary", "language": "da", "founded": datetime.date(2015, 9, 1)},
    {"code": "FI01", "name": "Fjällmark Suomi Oy", "short": "Fjällmark Finland",
     "country": "FIN", "currency": "EUR", "city": "Tampere", "region": "FI-11",
     "postal": "33100", "street": "Hämeenkatu 12", "phone": "+358 3 000 0100",
     "tax_number": "FI99000101", "role": "Sales and DTC Finland, Tampere oat-drink plant",
     "classification": "subsidiary", "language": "fi", "founded": datetime.date(2016, 2, 15)},
    {"code": "DE01", "name": "Fjällmark Deutschland GmbH", "short": "Fjällmark Germany",
     "country": "DEU", "currency": "EUR", "city": "Hamburg", "region": "DE-HH",
     "postal": "20095", "street": "Mönckebergstraße 7", "phone": "+49 40 000 0100",
     "tax_number": "DE999000101", "role": "Sales and DTC Germany and the Netherlands",
     "classification": "subsidiary", "language": "de", "founded": datetime.date(2017, 6, 1)},
    {"code": "PL01", "name": "Fjällmark Polska Sp. z o.o.", "short": "Fjällmark Poland",
     "country": "POL", "currency": "PLN", "city": "Poznań", "region": "PL-30",
     "postal": "61-001", "street": "ul. Głogowska 150", "phone": "+48 61 000 0100",
     "tax_number": "PL9990001010", "role": "Poznań personal-care plant (Mjuk Care), local B2B, no DTC",
     "classification": "subsidiary", "language": "pl", "founded": datetime.date(2018, 4, 9)},
]
COMPANY = dict((c["code"], c) for c in COMPANIES)
DTC_COMPANIES = ("SE01", "NO01", "DK01", "FI01", "DE01")

# EUR per one unit of local currency (group currency is EUR)
FX_BASE = {"SEK": 0.087, "NOK": 0.085, "DKK": 0.134, "PLN": 0.232, "EUR": 1.0}
_FX_PHASE = {"SEK": 0.0, "NOK": 1.3, "DKK": 2.1, "PLN": 3.7, "EUR": 0.0}


def fx(currency, y, m):
    """Monthly average rate, EUR per unit of ``currency`` (drift within +-2 %)."""
    base = FX_BASE[currency]
    if currency == "EUR":
        return 1.0
    t = month_index(y, m)
    ph = _FX_PHASE[currency]
    drift = 0.012 * math.sin(t / 4.0 + ph) + 0.007 * math.sin(t / 1.7 + 2 * ph)
    return round(base * (1.0 + drift), 6)


def fx_d(currency, y, m):
    return D(str(fx(currency, y, m)))


# --------------------------------------------------------------------------------------
# DTC markets
# --------------------------------------------------------------------------------------

# Parcel carriers are fictional (codes of invented regional delivery companies) - the data set
# deliberately contains no real carrier, retailer or equipment-vendor names.
MARKETS = [
    {"country": "SWE", "company": "SE01", "currency": "SEK", "vat": D("0.25"), "share": 0.35,
     "ship_fee": D("29.00"), "free_ship_over": D("400.00"), "lang": "sv-SE", "tz": "Europe/Stockholm",
     "dc": "DCJKG", "carrier": ["NORRPOST", "BUDEXPRESS", "HEMBUD"]},
    {"country": "NOR", "company": "NO01", "currency": "NOK", "vat": D("0.25"), "share": 0.15,
     "ship_fee": D("39.00"), "free_ship_over": D("420.00"), "lang": "nb-NO", "tz": "Europe/Oslo",
     "dc": "DCOSL", "carrier": ["FJORDPOST", "NORRPOST"]},
    {"country": "DNK", "company": "DK01", "currency": "DKK", "vat": D("0.25"), "share": 0.12,
     "ship_fee": D("29.00"), "free_ship_over": D("270.00"), "lang": "da-DK", "tz": "Europe/Copenhagen",
     "dc": "DCODE", "carrier": ["DANSKBUD", "NORRPOST"]},
    {"country": "FIN", "company": "FI01", "currency": "EUR", "vat": D("0.24"), "share": 0.13,
     "ship_fee": D("2.95"), "free_ship_over": D("35.00"), "lang": "fi-FI", "tz": "Europe/Helsinki",
     "dc": "DCVAN", "carrier": ["SUOMIKURIIRI", "NORRPOST"]},
    {"country": "DEU", "company": "DE01", "currency": "EUR", "vat": D("0.19"), "share": 0.17,
     "ship_fee": D("3.49"), "free_ship_over": D("35.00"), "lang": "de-DE", "tz": "Europe/Berlin",
     "dc": "DCHAM", "carrier": ["PAKETBLITZ", "ELBEKURIER", "NORRPOST"]},
    {"country": "NLD", "company": "DE01", "currency": "EUR", "vat": D("0.21"), "share": 0.08,
     "ship_fee": D("3.49"), "free_ship_over": D("35.00"), "lang": "nl-NL", "tz": "Europe/Amsterdam",
     "dc": "DCHAM", "carrier": ["POLDERPOST", "NORRPOST"]},
]
MARKET = dict((mk["country"], mk) for mk in MARKETS)

# standard VAT per country (simplification: the standard rate is applied to all categories)
VAT_RATE = {"SWE": D("0.25"), "NOR": D("0.25"), "DNK": D("0.25"), "FIN": D("0.24"),
            "DEU": D("0.19"), "NLD": D("0.21"), "POL": D("0.23"), "AUT": D("0.20")}

COUNTRY_NAMES = {"SWE": "Sweden", "NOR": "Norway", "DNK": "Denmark", "FIN": "Finland",
                 "DEU": "Germany", "NLD": "Netherlands", "POL": "Poland", "AUT": "Austria"}
COUNTRY_TZ = {"SWE": "Europe/Stockholm", "NOR": "Europe/Oslo", "DNK": "Europe/Copenhagen",
              "FIN": "Europe/Helsinki", "DEU": "Europe/Berlin", "NLD": "Europe/Amsterdam",
              "POL": "Europe/Warsaw", "AUT": "Europe/Vienna"}
COUNTRY_LANG = {"SWE": "sv-SE", "NOR": "nb-NO", "DNK": "da-DK", "FIN": "fi-FI", "DEU": "de-DE",
                "NLD": "nl-NL", "POL": "pl-PL", "AUT": "de-AT"}
COUNTRY_CCY = {"SWE": "SEK", "NOR": "NOK", "DNK": "DKK", "FIN": "EUR", "DEU": "EUR",
               "NLD": "EUR", "POL": "PLN", "AUT": "EUR"}
# fake mobile numbers: country code, mobile prefix, then an obviously fake "000" block and
# ``tail`` random digits so that the national significant number has the right length
# (SE 9, NO 8, DK 8, FI 9, DE 10, NL 9, PL 9, AT 10 digits)
COUNTRY_PHONE = {"SWE": ("+46", "70", 4), "NOR": ("+47", "4", 4), "DNK": ("+45", "20", 3),
                 "FIN": ("+358", "40", 4), "DEU": ("+49", "151", 4), "NLD": ("+31", "6", 5),
                 "POL": ("+48", "500", 3), "AUT": ("+43", "660", 4)}
PHONE_NSN_DIGITS = {"SWE": 9, "NOR": 8, "DNK": 8, "FIN": 9, "DEU": 10, "NLD": 9, "POL": 9, "AUT": 10}

# cities: (name, ISO 3166-2, lat, lon, postal template) - '#' = digit, '@' = upper letter
CITIES = {
    "SWE": [("Stockholm", "SE-AB", 59.3293, 18.0686, "1## ##"), ("Göteborg", "SE-O", 57.7089, 11.9746, "4## ##"),
            ("Malmö", "SE-M", 55.6050, 13.0038, "21# ##"), ("Uppsala", "SE-C", 59.8586, 17.6389, "75# ##"),
            ("Lund", "SE-M", 55.7047, 13.1910, "22# ##"), ("Västerås", "SE-U", 59.6099, 16.5448, "72# ##"),
            ("Örebro", "SE-T", 59.2753, 15.2134, "70# ##"), ("Linköping", "SE-E", 58.4108, 15.6214, "58# ##"),
            ("Norrköping", "SE-E", 58.5877, 16.1924, "60# ##"), ("Jönköping", "SE-F", 57.7826, 14.1618, "55# ##"),
            ("Umeå", "SE-AC", 63.8258, 20.2630, "90# ##"), ("Luleå", "SE-BD", 65.5848, 22.1547, "97# ##")],
    "NOR": [("Oslo", "NO-03", 59.9139, 10.7522, "0###"), ("Bergen", "NO-46", 60.3913, 5.3221, "50##"),
            ("Trondheim", "NO-50", 63.4305, 10.3951, "70##"), ("Stavanger", "NO-11", 58.9700, 5.7331, "40##"),
            ("Tromsø", "NO-55", 69.6492, 18.9553, "90##"), ("Drammen", "NO-33", 59.7439, 10.2045, "30##"),
            ("Kristiansand", "NO-42", 58.1599, 8.0182, "46##")],
    "DNK": [("København", "DK-84", 55.6761, 12.5683, "1###"), ("Aarhus", "DK-82", 56.1629, 10.2039, "80##"),
            ("Odense", "DK-83", 55.4038, 10.4024, "50##"), ("Aalborg", "DK-81", 57.0488, 9.9217, "90##"),
            ("Esbjerg", "DK-83", 55.4765, 8.4594, "67##"), ("Roskilde", "DK-85", 55.6415, 12.0803, "40##")],
    "FIN": [("Helsinki", "FI-18", 60.1699, 24.9384, "00###"), ("Espoo", "FI-18", 60.2055, 24.6559, "02###"),
            ("Tampere", "FI-11", 61.4978, 23.7610, "33###"), ("Turku", "FI-19", 60.4518, 22.2666, "20###"),
            ("Oulu", "FI-14", 65.0121, 25.4651, "90###"), ("Vantaa", "FI-18", 60.2934, 25.0378, "01###"),
            ("Jyväskylä", "FI-08", 62.2426, 25.7473, "40###")],
    "DEU": [("Hamburg", "DE-HH", 53.5511, 9.9937, "20###"), ("Berlin", "DE-BE", 52.5200, 13.4050, "10###"),
            ("München", "DE-BY", 48.1351, 11.5820, "80###"), ("Köln", "DE-NW", 50.9375, 6.9603, "50###"),
            ("Frankfurt am Main", "DE-HE", 50.1109, 8.6821, "60###"), ("Stuttgart", "DE-BW", 48.7758, 9.1829, "70###"),
            ("Düsseldorf", "DE-NW", 51.2277, 6.7735, "40###"), ("Leipzig", "DE-SN", 51.3397, 12.3731, "04###"),
            ("Bremen", "DE-HB", 53.0793, 8.8017, "28###"), ("Hannover", "DE-NI", 52.3759, 9.7320, "30###")],
    "NLD": [("Amsterdam", "NL-NH", 52.3676, 4.9041, "10## @@"), ("Rotterdam", "NL-ZH", 51.9244, 4.4777, "30## @@"),
            ("Utrecht", "NL-UT", 52.0907, 5.1214, "35## @@"), ("Den Haag", "NL-ZH", 52.0705, 4.3007, "25## @@"),
            ("Eindhoven", "NL-NB", 51.4416, 5.4697, "56## @@"), ("Groningen", "NL-GR", 53.2194, 6.5665, "97## @@")],
    "POL": [("Poznań", "PL-30", 52.4064, 16.9252, "6#-###"), ("Warszawa", "PL-14", 52.2297, 21.0122, "0#-###"),
            ("Wrocław", "PL-02", 51.1079, 17.0385, "5#-###"), ("Kraków", "PL-12", 50.0647, 19.9450, "3#-###"),
            ("Gdańsk", "PL-22", 54.3520, 18.6466, "8#-###")],
}

STREETS = {
    "SWE": ["Storgatan", "Kungsgatan", "Drottninggatan", "Björkvägen", "Ekvägen", "Skolgatan",
            "Järnvägsgatan", "Tallvägen", "Sjövägen", "Hamngatan", "Lingonstigen", "Granvägen"],
    "NOR": ["Storgata", "Kirkegata", "Strandveien", "Bjørkeveien", "Skogveien", "Havnegata",
            "Fjellveien", "Elvegata"],
    "DNK": ["Østergade", "Vestergade", "Søndergade", "Nørregade", "Strandvejen", "Skovvej",
            "Kirkevej", "Engvej"],
    "FIN": ["Koivukuja", "Rantatie", "Kirkkokatu", "Asemakatu", "Puistokatu", "Mäntytie",
            "Järvitie", "Kauppakatu"],
    "DEU": ["Hauptstraße", "Bahnhofstraße", "Lindenstraße", "Gartenweg", "Schulstraße",
            "Birkenweg", "Hafenstraße", "Ahornweg"],
    "NLD": ["Kerkstraat", "Dorpsstraat", "Molenweg", "Stationsweg", "Lindelaan", "Havenkade",
            "Beukenlaan", "Prinsengracht"],
    "POL": ["ul. Polna", "ul. Leśna", "ul. Słoneczna", "ul. Kościelna", "ul. Ogrodowa", "ul. Lipowa"],
}

# given names by gender (shopper gender is drawn first, then a name from the matching pool;
# persons in generic tables use the union below)
FIRST_NAMES_F = {
    "SWE": ["Anna", "Maja", "Elin", "Sara", "Ebba", "Linnea", "Ida", "Wilma", "Klara", "Alva", "Frida",
            "Saga", "Tove", "Lisa", "Ingrid", "Astrid"],
    "NOR": ["Ingrid", "Nora", "Sofie", "Emma", "Thea", "Ragnhild", "Live", "Hedda", "Marte", "Tuva"],
    "DNK": ["Mette", "Freja", "Ida", "Laura", "Signe", "Karen", "Caroline", "Asta", "Line", "Nanna"],
    "FIN": ["Aino", "Emilia", "Sanna", "Helmi", "Kaisa", "Venla", "Noora", "Ilona", "Elina", "Minna"],
    "DEU": ["Lena", "Hannah", "Lea", "Marie", "Sophie", "Mia", "Laura", "Katharina", "Julia", "Anna"],
    "NLD": ["Sanne", "Lotte", "Eva", "Fleur", "Iris", "Noor", "Femke", "Maud", "Roos", "Anouk"],
    "POL": ["Anna", "Katarzyna", "Agnieszka", "Magdalena", "Joanna", "Zofia", "Ewa", "Natalia"],
}
FIRST_NAMES_M = {
    "SWE": ["Erik", "Lars", "Johan", "Oskar", "Gustav", "Karl", "Nils", "Axel", "Viktor", "Hugo", "Emil",
            "Anton", "Per", "Olof"],
    "NOR": ["Ola", "Henrik", "Magnus", "Sindre", "Jonas", "Even", "Eirik", "Kristian", "Sverre", "Aksel"],
    "DNK": ["Rasmus", "Mads", "Søren", "Frederik", "Mikkel", "Jens", "Kasper", "Christian", "Troels", "Anders"],
    "FIN": ["Mikko", "Juha", "Ville", "Antti", "Lauri", "Eero", "Teemu", "Jari", "Oskari", "Tuomas"],
    "DEU": ["Lukas", "Jonas", "Felix", "Paul", "Leon", "Maximilian", "Tobias", "Moritz", "Niklas", "Florian"],
    "NLD": ["Daan", "Bram", "Thijs", "Sem", "Ruben", "Jesse", "Lars", "Joris", "Stijn", "Pieter"],
    "POL": ["Piotr", "Tomasz", "Paweł", "Michał", "Krzysztof", "Marek", "Jakub"],
}
FIRST_NAMES = dict((c, FIRST_NAMES_F[c] + FIRST_NAMES_M[c]) for c in FIRST_NAMES_F)
LAST_NAMES = {
    "SWE": ["Lindqvist", "Andersson", "Berg", "Holm", "Sjöberg", "Nyström", "Ek", "Lundgren",
            "Forsberg", "Wallin", "Engström", "Dahl", "Hedlund", "Sandberg", "Bergström", "Nordin",
            "Åberg", "Lindahl", "Strand", "Hellström", "Blom", "Eklund", "Söderberg", "Falk"],
    "NOR": ["Haugen", "Johansen", "Lie", "Bakken", "Solberg", "Moen", "Strand", "Dahl", "Berge",
            "Lunde", "Aas", "Nygård", "Hagen", "Fjeld", "Myhre", "Brekke"],
    "DNK": ["Nielsen", "Jensen", "Kjær", "Mortensen", "Lund", "Holm", "Skov", "Bruun", "Dam",
            "Krogh", "Vestergaard", "Bech", "Juhl", "Thygesen", "Lindberg", "Friis"],
    "FIN": ["Virtanen", "Korhonen", "Mäkinen", "Nieminen", "Laine", "Heikkinen", "Koskinen",
            "Järvinen", "Lehtonen", "Saarinen", "Salminen", "Tuominen", "Rantanen", "Karjalainen"],
    "DEU": ["Becker", "Hoffmann", "Schulz", "Krüger", "Wagner", "Neumann", "Schwarz", "Zimmermann",
            "Braun", "Hartmann", "Lange", "Werner", "Lehmann", "Köhler", "Vogel", "Fuchs"],
    "NLD": ["de Vries", "Jansen", "Bakker", "Visser", "Smit", "Meijer", "Mulder", "de Boer",
            "Bos", "Vos", "Peters", "Hendriks", "Dekker", "Brouwer"],
    "POL": ["Nowak", "Wójcik", "Woźniak", "Mazur", "Krawczyk", "Kaczmarek", "Zając", "Król",
            "Wieczorek", "Pawlak"],
}

# --------------------------------------------------------------------------------------
# brands, categories, SKUs
# --------------------------------------------------------------------------------------

BRANDS = [
    {"code": "BJORKO", "name": "Björkö Pantry", "short": "Björkö", "category": "FOOD",
     "category_name": "Food", "plant": "LUND", "launch": datetime.date(2011, 4, 1), "tier": "premium",
     "segment": "Health-conscious Nordic families", "ean_prefix": "7350099",
     "positioning": "Wholesome Nordic pantry staples - crispbread, granola, porridge and berry jams made from Scandinavian oats and rye.",
     "handle": "@bjorkopantry", "sub_brands": ["Björkö Crisp", "Björkö Morning", "Björkö Berry"]},
    {"code": "KALLKALLA", "name": "Kallkälla", "short": "Kallkälla", "category": "BEVERAGE",
     "category_name": "Beverages", "plant": "NKPG", "launch": datetime.date(2013, 5, 15), "tier": "mass",
     "segment": "Active urban adults", "ean_prefix": "7350099",
     "positioning": "Clean Nordic refreshment - sparkling spring water, juices and oat drinks with no artificial sweeteners.",
     "handle": "@kallkalla", "sub_brands": ["Kallkälla Sparkling", "Kallkälla Juice", "Kallkälla Oat"]},
    {"code": "MJUKCARE", "name": "Mjuk Care", "short": "Mjuk Care", "category": "PERSONAL_CARE",
     "category_name": "Personal Care", "plant": "POZN", "launch": datetime.date(2016, 9, 1), "tier": "mass",
     "segment": "Sensitive-skin households", "ean_prefix": "7350099",
     "positioning": "Gentle, dermatologist-tested personal care inspired by Nordic botanicals - birch, oat and lingonberry.",
     "handle": "@mjukcare", "sub_brands": ["Mjuk Care Hair", "Mjuk Care Body", "Mjuk Care Smile"]},
]
BRAND = dict((b["code"], b) for b in BRANDS)

# level-2 categories: code -> (name, parent L1, description)
SUBCATEGORIES = [
    ("CRISPBREAD", "Crispbread", "FOOD", "Rye and wholegrain crispbread"),
    ("GRANOLA", "Granola & Muesli", "FOOD", "Baked granola and muesli"),
    ("SNACKBAR", "Snack Bars", "FOOD", "Oat-based muesli bars"),
    ("PORRIDGE", "Porridge & Oats", "FOOD", "Oat porridge and oat flakes"),
    ("JAM", "Jams & Spreads", "FOOD", "Nordic berry jams and marmalades"),
    ("SPARKLING", "Sparkling Water", "BEVERAGE", "Flavoured and natural sparkling spring water"),
    ("JUICE", "Juices & Nectars", "BEVERAGE", "Juices, nectars and berry drinks"),
    ("OATDRINK", "Oat Drinks", "BEVERAGE", "Plant-based oat drinks"),
    ("HAIRCARE", "Hair Care", "PERSONAL_CARE", "Shampoo and conditioner"),
    ("BODYCARE", "Body Care", "PERSONAL_CARE", "Body wash and hand soap"),
    ("ORALCARE", "Oral Care", "PERSONAL_CARE", "Toothpaste"),
    ("SKINCARE", "Hand & Skin Care", "PERSONAL_CARE", "Hand creams"),
    ("DEODORANT", "Deodorants", "PERSONAL_CARE", "Roll-on, stick and spray deodorants"),
    ("GIFTSET", "Gift Sets", "PERSONAL_CARE", "Seasonal gift sets and travel kits"),
]
TOP_CATEGORIES = [("FOOD", "Food", "Packaged Nordic foods"),
                  ("BEVERAGE", "Beverages", "Non-alcoholic beverages"),
                  ("PERSONAL_CARE", "Personal Care", "Hair, body, oral and skin care")]

# SKU spec: (code, brand, subcat, name, form, content, uom, pack, list_eur, cost_ratio, line,
#            season, flavour_or_scent, launch)
# list_eur = B2B list price per consumer unit (EUR, excl. VAT); consumer price ~ list * 1.6
_SKU_ROWS = [
    # Björkö Pantry - Lund (LUND)
    ("BP-CRISP-RYE-250", "BJORKO", "CRISPBREAD", "Rye Crispbread 250 g", "bar", 250, "g", 1, "1.45", 0.46, "LUNDL1", None, "Rye", None),
    ("BP-CRISP-RYE-500", "BJORKO", "CRISPBREAD", "Rye Crispbread 500 g", "bar", 500, "g", 1, "2.55", 0.44, "LUNDL1", None, "Rye", None),
    ("BP-CRISP-SES-250", "BJORKO", "CRISPBREAD", "Sesame Crispbread 250 g", "bar", 250, "g", 1, "1.65", 0.47, "LUNDL1", None, "Sesame", None),
    ("BP-CRISP-SEED-220", "BJORKO", "CRISPBREAD", "Seeded Crispbread 220 g", "bar", 220, "g", 1, "1.85", 0.45, "LUNDL1", None, "Seeds", None),
    ("BP-CRISP-THIN-190", "BJORKO", "CRISPBREAD", "Thin Crispbread 190 g", "bar", 190, "g", 1, "1.55", 0.46, "LUNDL1", None, "Rye", None),
    ("BP-CRISP-SOUR-240", "BJORKO", "CRISPBREAD", "Sourdough Crispbread 240 g", "bar", 240, "g", 1, "1.95", 0.44, "LUNDL1", None, "Sourdough", None),
    ("BP-CRISP-GF-200", "BJORKO", "CRISPBREAD", "Gluten-free Crispbread 200 g", "bar", 200, "g", 1, "2.35", 0.50, "LUNDL1", None, "Buckwheat", None),
    ("BP-CRISP-MINI-150", "BJORKO", "CRISPBREAD", "Crispbread Minis 150 g", "bar", 150, "g", 1, "1.35", 0.47, "LUNDL1", None, "Rye", None),
    ("BP-CRISP-GING-200", "BJORKO", "CRISPBREAD", "Gingerbread Crispbread 200 g", "bar", 200, "g", 1, "1.95", 0.45, "LUNDL1", "XMAS", "Gingerbread", None),
    ("BP-GRAN-LING-450", "BJORKO", "GRANOLA", "Lingonberry Granola 450 g", "powder", 450, "g", 1, "2.95", 0.44, "LUNDL2", None, "Lingonberry", None),
    ("BP-GRAN-HONEY-450", "BJORKO", "GRANOLA", "Honey & Almond Granola 450 g", "powder", 450, "g", 1, "2.95", 0.45, "LUNDL2", None, "Honey almond", None),
    ("BP-GRAN-BLUE-450", "BJORKO", "GRANOLA", "Blueberry Granola 450 g", "powder", 450, "g", 1, "2.95", 0.45, "LUNDL2", None, "Blueberry", None),
    ("BP-GRAN-HONEY-900", "BJORKO", "GRANOLA", "Honey & Almond Granola 900 g Family Pack", "powder", 900, "g", 1, "5.25", 0.43, "LUNDL2", None, "Honey almond", None),
    ("BP-GRAN-GING-450", "BJORKO", "GRANOLA", "Gingerbread Granola 450 g", "powder", 450, "g", 1, "3.15", 0.44, "LUNDL2", "XMAS", "Gingerbread", None),
    ("BP-MUES-NORD-750", "BJORKO", "GRANOLA", "Nordic Muesli 750 g", "powder", 750, "g", 1, "2.65", 0.47, "LUNDL2", None, "Nordic berries", None),
    ("BP-MUES-FRUIT-750", "BJORKO", "GRANOLA", "Fruit Muesli 750 g", "powder", 750, "g", 1, "2.65", 0.48, "LUNDL2", None, "Apple raisin", None),
    ("BP-BAR-BLUE-6X30", "BJORKO", "SNACKBAR", "Muesli Bars Blueberry 6 x 30 g", "bar", 180, "g", 6, "2.15", 0.49, "LUNDL4", None, "Blueberry", None),
    ("BP-BAR-APPLE-6X30", "BJORKO", "SNACKBAR", "Muesli Bars Oat & Apple 6 x 30 g", "bar", 180, "g", 6, "2.15", 0.49, "LUNDL4", None, "Apple", None),
    ("BP-BAR-CHOC-6X30", "BJORKO", "SNACKBAR", "Muesli Bars Dark Chocolate 6 x 30 g", "bar", 180, "g", 6, "2.25", 0.50, "LUNDL4", None, "Dark chocolate", None),
    ("BP-PORR-ORIG-500", "BJORKO", "PORRIDGE", "Oat Porridge Original 500 g", "powder", 500, "g", 1, "1.55", 0.43, "LUNDL3", None, "Original", None),
    ("BP-PORR-CINN-8X35", "BJORKO", "PORRIDGE", "Oat Porridge Cinnamon & Apple 8 x 35 g", "powder", 280, "g", 8, "2.45", 0.46, "LUNDL3", None, "Cinnamon apple", None),
    ("BP-PORR-BLUE-8X35", "BJORKO", "PORRIDGE", "Oat Porridge Blueberry 8 x 35 g", "powder", 280, "g", 8, "2.45", 0.46, "LUNDL3", None, "Blueberry", None),
    ("BP-OATS-JUMBO-1KG", "BJORKO", "PORRIDGE", "Jumbo Oat Flakes 1 kg", "powder", 1, "kg", 1, "1.85", 0.48, "LUNDL3", None, "Oat", None),
    ("BP-OATS-ORG-750", "BJORKO", "PORRIDGE", "Organic Oat Flakes 750 g", "powder", 750, "g", 1, "1.95", 0.47, "LUNDL3", None, "Oat", None),
    ("BP-PORR-RYE-500", "BJORKO", "PORRIDGE", "Rye & Oat Porridge 500 g", "powder", 500, "g", 1, "1.65", 0.45, "LUNDL3", None, "Rye oat", None),
    ("BP-JAM-LING-340", "BJORKO", "JAM", "Lingonberry Jam 340 g", "gel", 340, "g", 1, "2.25", 0.42, "LUNDL4", None, "Lingonberry", None),
    ("BP-JAM-LING-600", "BJORKO", "JAM", "Lingonberry Jam 600 g", "gel", 600, "g", 1, "3.45", 0.41, "LUNDL4", None, "Lingonberry", None),
    ("BP-JAM-CLOUD-220", "BJORKO", "JAM", "Cloudberry Jam 220 g", "gel", 220, "g", 1, "4.95", 0.38, "LUNDL4", None, "Cloudberry", None),
    ("BP-JAM-BLUE-340", "BJORKO", "JAM", "Blueberry Jam 340 g", "gel", 340, "g", 1, "2.25", 0.43, "LUNDL4", None, "Blueberry", None),
    ("BP-JAM-STRAW-340", "BJORKO", "JAM", "Strawberry & Rhubarb Jam 340 g", "gel", 340, "g", 1, "2.25", 0.43, "LUNDL4", None, "Strawberry rhubarb", None),
    ("BP-JAM-BUCK-220", "BJORKO", "JAM", "Sea Buckthorn Marmalade 220 g", "gel", 220, "g", 1, "3.25", 0.40, "LUNDL4", None, "Sea buckthorn", None),
    # Kallkälla - Norrköping (NKPG) and Tampere (TMPR)
    ("KK-SPK-LEM-033C", "KALLKALLA", "SPARKLING", "Sparkling Water Lemon 0.33 L can", "liquid", 330, "ml", 1, "0.55", 0.42, "NKPGL2", None, "Lemon", None),
    ("KK-SPK-LIME-033C", "KALLKALLA", "SPARKLING", "Sparkling Water Lime 0.33 L can", "liquid", 330, "ml", 1, "0.55", 0.42, "NKPGL2", None, "Lime", None),
    ("KK-SPK-ELD-033C", "KALLKALLA", "SPARKLING", "Sparkling Water Elderflower 0.33 L can", "liquid", 330, "ml", 1, "0.59", 0.41, "NKPGL2", None, "Elderflower", None),
    ("KK-SPK-NAT-033C", "KALLKALLA", "SPARKLING", "Sparkling Water Natural 0.33 L can", "liquid", 330, "ml", 1, "0.49", 0.43, "NKPGL2", None, "Natural", None),
    ("KK-SPK-LINGL-033C", "KALLKALLA", "SPARKLING", "Sparkling Water Lingonberry & Lime 0.33 L can", "liquid", 330, "ml", 1, "0.62", 0.41, "NKPGL2", "SUMMER", "Lingonberry lime", None),
    ("KK-SPK-LEM-150P", "KALLKALLA", "SPARKLING", "Sparkling Water Lemon 1.5 L", "liquid", 1.5, "L", 1, "0.95", 0.40, "NKPGL1", None, "Lemon", None),
    ("KK-SPK-LIME-150P", "KALLKALLA", "SPARKLING", "Sparkling Water Lime 1.5 L", "liquid", 1.5, "L", 1, "0.95", 0.40, "NKPGL1", None, "Lime", None),
    ("KK-SPK-ELD-150P", "KALLKALLA", "SPARKLING", "Sparkling Water Elderflower 1.5 L", "liquid", 1.5, "L", 1, "0.99", 0.40, "NKPGL1", None, "Elderflower", None),
    ("KK-SPK-NAT-150P", "KALLKALLA", "SPARKLING", "Sparkling Water Natural 1.5 L", "liquid", 1.5, "L", 1, "0.85", 0.41, "NKPGL1", None, "Natural", None),
    ("KK-SPK-LEM-6X033", "KALLKALLA", "SPARKLING", "Sparkling Water Lemon 6 x 0.33 L", "liquid", 1980, "ml", 6, "2.95", 0.42, "NKPGL4", None, "Lemon", None),
    ("KK-SPK-LIME-6X033", "KALLKALLA", "SPARKLING", "Sparkling Water Lime 6 x 0.33 L", "liquid", 1980, "ml", 6, "2.95", 0.42, "NKPGL4", None, "Lime", None),
    ("KK-SPK-ELD-6X033", "KALLKALLA", "SPARKLING", "Sparkling Water Elderflower 6 x 0.33 L", "liquid", 1980, "ml", 6, "3.15", 0.41, "NKPGL4", None, "Elderflower", None),
    ("KK-SPK-LEM-24X033", "KALLKALLA", "SPARKLING", "Sparkling Water Lemon 24 x 0.33 L tray", "liquid", 7920, "ml", 24, "10.90", 0.43, "NKPGL4", None, "Lemon", None),
    ("KK-JCE-APPLE-1L", "KALLKALLA", "JUICE", "Apple Juice 1 L", "liquid", 1, "L", 1, "1.65", 0.47, "NKPGL3", None, "Apple", None),
    ("KK-JCE-ORANGE-1L", "KALLKALLA", "JUICE", "Orange Juice 1 L", "liquid", 1, "L", 1, "1.75", 0.49, "NKPGL3", None, "Orange", None),
    ("KK-JCE-BLACK-1L", "KALLKALLA", "JUICE", "Blackcurrant Nectar 1 L", "liquid", 1, "L", 1, "1.85", 0.45, "NKPGL3", None, "Blackcurrant", None),
    ("KK-JCE-APPELD-1L", "KALLKALLA", "JUICE", "Apple & Elderflower Juice 1 L", "liquid", 1, "L", 1, "1.85", 0.46, "NKPGL3", None, "Apple elderflower", None),
    ("KK-JCE-LING-1L", "KALLKALLA", "JUICE", "Lingonberry Drink 1 L", "liquid", 1, "L", 1, "1.95", 0.44, "NKPGL3", None, "Lingonberry", None),
    ("KK-JCE-BLUESM-075", "KALLKALLA", "JUICE", "Blueberry Smoothie 0.75 L", "liquid", 750, "ml", 1, "2.25", 0.48, "NKPGL3", None, "Blueberry", None),
    ("KK-JCE-GLOGG-075", "KALLKALLA", "JUICE", "Spiced Glögg Juice 0.75 L", "liquid", 750, "ml", 1, "2.45", 0.42, "NKPGL3", "XMAS", "Spiced berry", None),
    ("KK-OAT-ORIG-1L", "KALLKALLA", "OATDRINK", "Oat Drink Original 1 L", "liquid", 1, "L", 1, "1.45", 0.47, "TMPRL2", None, "Original", datetime.date(2025, 4, 22)),
    ("KK-OAT-BARI-1L", "KALLKALLA", "OATDRINK", "Oat Drink Barista 1 L", "liquid", 1, "L", 1, "1.75", 0.46, "TMPRL2", None, "Barista", datetime.date(2025, 4, 22)),
    ("KK-OAT-CHOC-1L", "KALLKALLA", "OATDRINK", "Oat Drink Chocolate 1 L", "liquid", 1, "L", 1, "1.85", 0.48, "TMPRL2", None, "Chocolate", datetime.date(2025, 5, 20)),
    ("KK-OAT-UNSW-1L", "KALLKALLA", "OATDRINK", "Oat Drink Unsweetened 1 L", "liquid", 1, "L", 1, "1.55", 0.47, "TMPRL2", None, "Unsweetened", datetime.date(2025, 5, 20)),
    ("KK-OAT-ORG-1L", "KALLKALLA", "OATDRINK", "Oat Drink Organic 1 L", "liquid", 1, "L", 1, "1.95", 0.49, "TMPRL2", None, "Organic", datetime.date(2025, 9, 1)),
    ("KK-OAT-VAN-025", "KALLKALLA", "OATDRINK", "Oat Drink Vanilla 0.25 L", "liquid", 250, "ml", 1, "0.85", 0.50, "TMPRL3", None, "Vanilla", datetime.date(2025, 6, 2)),
    ("KK-OAT-ORIG-6X1L", "KALLKALLA", "OATDRINK", "Oat Drink Original 6 x 1 L crate", "liquid", 6, "L", 6, "8.25", 0.47, "TMPRL3", None, "Original", datetime.date(2025, 4, 22)),
    ("KK-OAT-BARI-6X1L", "KALLKALLA", "OATDRINK", "Oat Drink Barista 6 x 1 L crate", "liquid", 6, "L", 6, "9.90", 0.46, "TMPRL3", None, "Barista", datetime.date(2025, 4, 22)),
    # Mjuk Care - Poznań (POZN); POZNL2 = PL-POZ-L2 liquid filling
    ("MC-SHP-BIRCH-250", "MJUKCARE", "HAIRCARE", "Shampoo Gentle Birch 250 ml", "liquid", 250, "ml", 1, "2.45", 0.38, "POZNL2", None, "Birch", None),
    ("MC-SHP-BIRCH-500", "MJUKCARE", "HAIRCARE", "Shampoo Gentle Birch 500 ml", "liquid", 500, "ml", 1, "3.95", 0.36, "POZNL2", None, "Birch", None),
    ("MC-SHP-NETTLE-250", "MJUKCARE", "HAIRCARE", "Shampoo Volume Nettle 250 ml", "liquid", 250, "ml", 1, "2.55", 0.38, "POZNL2", None, "Nettle", None),
    ("MC-SHP-JUNIP-250", "MJUKCARE", "HAIRCARE", "Shampoo Anti-dandruff Juniper 250 ml", "liquid", 250, "ml", 1, "2.95", 0.37, "POZNL2", None, "Juniper", None),
    ("MC-SHP-FAM-500", "MJUKCARE", "HAIRCARE", "Shampoo Family 500 ml", "liquid", 500, "ml", 1, "3.45", 0.40, "POZNL2", None, "Mild", None),
    ("MC-SHP-REFILL-750", "MJUKCARE", "HAIRCARE", "Shampoo Refill Pouch 750 ml", "liquid", 750, "ml", 1, "4.25", 0.35, "POZNL2", None, "Birch", None),
    ("MC-CON-BIRCH-200", "MJUKCARE", "HAIRCARE", "Conditioner Gentle Birch 200 ml", "liquid", 200, "ml", 1, "2.55", 0.39, "POZNL2", None, "Birch", None),
    ("MC-CON-OAT-200", "MJUKCARE", "HAIRCARE", "Conditioner Repair Oat 200 ml", "liquid", 200, "ml", 1, "2.75", 0.38, "POZNL2", None, "Oat", None),
    ("MC-CON-FAM-500", "MJUKCARE", "HAIRCARE", "Conditioner Family 500 ml", "liquid", 500, "ml", 1, "3.55", 0.40, "POZNL2", None, "Mild", None),
    ("MC-BW-MINT-250", "MJUKCARE", "BODYCARE", "Body Wash Arctic Mint 250 ml", "liquid", 250, "ml", 1, "2.25", 0.39, "POZNL2", None, "Arctic mint", None),
    ("MC-BW-MINT-500", "MJUKCARE", "BODYCARE", "Body Wash Arctic Mint 500 ml", "liquid", 500, "ml", 1, "3.65", 0.37, "POZNL2", None, "Arctic mint", None),
    ("MC-BW-LING-250", "MJUKCARE", "BODYCARE", "Body Wash Lingonberry 250 ml", "liquid", 250, "ml", 1, "2.25", 0.39, "POZNL2", None, "Lingonberry", None),
    ("MC-BW-SENS-400", "MJUKCARE", "BODYCARE", "Body Wash Sensitive Unscented 400 ml", "liquid", 400, "ml", 1, "2.95", 0.38, "POZNL2", None, "Unscented", None),
    ("MC-BW-REFILL-750", "MJUKCARE", "BODYCARE", "Body Wash Refill Pouch 750 ml", "liquid", 750, "ml", 1, "3.95", 0.35, "POZNL2", None, "Arctic mint", None),
    ("MC-HS-CLOUD-300", "MJUKCARE", "BODYCARE", "Hand Soap Cloudberry 300 ml", "liquid", 300, "ml", 1, "1.95", 0.41, "POZNL2", None, "Cloudberry", None),
    ("MC-HS-REFILL-750", "MJUKCARE", "BODYCARE", "Hand Soap Refill Pouch 750 ml", "liquid", 750, "ml", 1, "3.25", 0.36, "POZNL2", None, "Cloudberry", None),
    ("MC-TP-MINT-75", "MJUKCARE", "ORALCARE", "Toothpaste Fresh Mint 75 ml", "gel", 75, "ml", 1, "1.65", 0.40, "POZNL3", None, "Fresh mint", None),
    ("MC-TP-SENS-75", "MJUKCARE", "ORALCARE", "Toothpaste Sensitive 75 ml", "gel", 75, "ml", 1, "2.25", 0.38, "POZNL3", None, "Mild mint", None),
    ("MC-TP-KIDS-50", "MJUKCARE", "ORALCARE", "Toothpaste Kids Strawberry 50 ml", "gel", 50, "ml", 1, "1.75", 0.41, "POZNL3", None, "Strawberry", None),
    ("MC-TP-WHITE-75", "MJUKCARE", "ORALCARE", "Toothpaste Whitening 75 ml", "gel", 75, "ml", 1, "2.45", 0.37, "POZNL3", None, "Peppermint", None),
    ("MC-HC-OAT-75", "MJUKCARE", "SKINCARE", "Hand Cream Oat & Birch 75 ml", "cream", 75, "ml", 1, "2.65", 0.36, "POZNL3", None, "Oat birch", None),
    ("MC-HC-INT-100", "MJUKCARE", "SKINCARE", "Hand Cream Intensive 100 ml", "cream", 100, "ml", 1, "3.25", 0.35, "POZNL3", None, "Unscented", None),
    ("MC-HC-TRAV-30", "MJUKCARE", "SKINCARE", "Hand Cream Travel 30 ml", "cream", 30, "ml", 1, "1.45", 0.42, "POZNL3", None, "Oat birch", None),
    ("MC-DEO-FRESH-50", "MJUKCARE", "DEODORANT", "Deodorant Roll-on Fresh 50 ml", "liquid", 50, "ml", 1, "1.95", 0.39, "POZNL4", None, "Fresh", None),
    ("MC-DEO-SENS-50", "MJUKCARE", "DEODORANT", "Deodorant Roll-on Sensitive 50 ml", "liquid", 50, "ml", 1, "1.95", 0.39, "POZNL4", None, "Unscented", None),
    ("MC-DEO-LING-50", "MJUKCARE", "DEODORANT", "Deodorant Roll-on Lingonberry 50 ml", "liquid", 50, "ml", 1, "2.05", 0.39, "POZNL4", None, "Lingonberry", None),
    ("MC-DEO-CEDAR-75", "MJUKCARE", "DEODORANT", "Deodorant Stick Cedar 75 g", "stick", 75, "g", 1, "2.35", 0.38, "POZNL4", None, "Cedar", None),
    ("MC-DEO-ARCT-150", "MJUKCARE", "DEODORANT", "Deodorant Spray Arctic 150 ml", "spray", 150, "ml", 1, "2.45", 0.40, "POZNL4", None, "Arctic", None),
    ("MC-GIFT-WINTER", "MJUKCARE", "GIFTSET", "Mjuk Care Winter Gift Set", "liquid", 1, "units", 3, "8.95", 0.42, "POZNL5", "XMAS", "Lingonberry", None),
    ("MC-GIFT-TRAVEL", "MJUKCARE", "GIFTSET", "Mjuk Care Travel Kit", "liquid", 1, "units", 4, "5.95", 0.44, "POZNL5", None, "Mixed", None),
]

SKU_FIELDS = ("code", "brand", "subcat", "name", "form", "content", "uom", "pack", "list_eur",
              "cost_ratio", "line", "season", "flavour", "launch")


def _check_digit(digits12):
    total = 0
    for i, ch in enumerate(reversed(digits12)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return str((10 - total % 10) % 10)


def gtin13(prefix7, item_ref):
    """A valid GTIN-13 for a 7-digit GS1 company prefix and a 5-digit item reference."""
    body = "%s%05d" % (prefix7, item_ref)
    return body + _check_digit(body)


def _build_skus():
    out = []
    for i, row in enumerate(_SKU_ROWS):
        s = dict(zip(SKU_FIELDS, row))
        brand = BRAND[s["brand"]]
        s["full_name"] = "%s %s" % (brand["name"], s["name"])
        s["list_eur"] = D(s["list_eur"])
        s["std_cost_eur"] = (s["list_eur"] * D(str(s["cost_ratio"]))).quantize(D("0.0001"))
        # recommended consumer price incl. VAT (EUR), a little above list * 1.6
        s["rsp_eur"] = (s["list_eur"] * D("1.62")).quantize(D("0.01"))
        s["category"] = brand["category"]
        s["plant"] = s["line"][:4]
        s["gtin"] = gtin13(brand["ean_prefix"], 10 + i * 7)
        s["index"] = i
        if s["launch"] is None:
            s["launch"] = datetime.date(2016 + (i % 7), 1 + (i * 5) % 12, 1 + (i * 3) % 27)
            if s["launch"] < brand["launch"]:
                s["launch"] = brand["launch"] + datetime.timedelta(days=30 + i * 11)
        out.append(s)
    return out


SKUS = _build_skus()
SKU = dict((s["code"], s) for s in SKUS)

SHELF_LIFE_DAYS = {"CRISPBREAD": 365, "GRANOLA": 300, "SNACKBAR": 270, "PORRIDGE": 450,
                   "JAM": 540, "SPARKLING": 365, "JUICE": 240, "OATDRINK": 270, "HAIRCARE": 1095,
                   "BODYCARE": 1095, "ORALCARE": 730, "SKINCARE": 900, "DEODORANT": 900,
                   "GIFTSET": 900}

# --------------------------------------------------------------------------------------
# plants, lines, distribution centres
# --------------------------------------------------------------------------------------

PLANTS = [
    {"code": "LUND", "erp": "SE-LUN", "name": "Lund Food Plant", "company": "SE01", "country": "SWE",
     "city": "Lund", "region": "SE-M", "postal": "224 78", "street": "Höjebrovägen 18",
     "lat": 55.7047, "lon": 13.1910, "brand": "BJORKO", "category": "FOOD", "type": "integrated",
     "commissioned": datetime.date(2011, 2, 1), "headcount": 210, "oee": 76.0, "yield": 97.6},
    {"code": "NKPG", "erp": "SE-NKP", "name": "Norrköping Beverage Plant", "company": "SE01", "country": "SWE",
     "city": "Norrköping", "region": "SE-E", "postal": "602 28", "street": "Industrigatan 41",
     "lat": 58.5877, "lon": 16.1924, "brand": "KALLKALLA", "category": "BEVERAGE", "type": "filling",
     "commissioned": datetime.date(2013, 3, 1), "headcount": 165, "oee": 79.0, "yield": 98.4},
    {"code": "TMPR", "erp": "FI-TMP", "name": "Tampere Oat Drink Plant", "company": "FI01", "country": "FIN",
     "city": "Tampere", "region": "FI-11", "postal": "33720", "street": "Hervannan valtaväylä 9",
     "lat": 61.4978, "lon": 23.7610, "brand": "KALLKALLA", "category": "BEVERAGE", "type": "integrated",
     "commissioned": datetime.date(2025, 4, 1), "headcount": 74, "oee": 78.0, "yield": 97.8},
    {"code": "POZN", "erp": "PL-POZ", "name": "Poznań Personal Care Plant", "company": "PL01", "country": "POL",
     "city": "Poznań", "region": "PL-30", "postal": "61-249", "street": "ul. Głogowska 401",
     "lat": 52.4064, "lon": 16.9252, "brand": "MJUKCARE", "category": "PERSONAL_CARE", "type": "integrated",
     "commissioned": datetime.date(2016, 6, 1), "headcount": 240, "oee": 77.0, "yield": 97.2},
]
PLANT = dict((p["code"], p) for p in PLANTS)

# (line_code, plant, short tag used on the shop floor, name, line_type, design speed units/h).
# Design speeds fit the volumes of a mid-sized producer: lines run in campaigns of one to three days,
# about 25-35 % of a two-shift calendar (all plants run two shifts on weekdays).
LINES = [
    ("LUNDL1", "LUND", "SE-LUN-L1", "Crispbread baking and wrapping", "packaging", 1500),
    ("LUNDL2", "LUND", "SE-LUN-L2", "Granola and muesli baking", "blending", 720),
    ("LUNDL3", "LUND", "SE-LUN-L3", "Porridge and oat flake packing", "packaging", 1100),
    ("LUNDL4", "LUND", "SE-LUN-L4", "Jam cooking and muesli bar line", "filling", 900),
    ("NKPGL1", "NKPG", "SE-NKP-L1", "PET bottling 1.5 L", "filling", 2700),
    ("NKPGL2", "NKPG", "SE-NKP-L2", "Can filling 0.33 L", "filling", 3600),
    ("NKPGL3", "NKPG", "SE-NKP-L3", "Juice aseptic carton line", "filling", 1100),
    ("NKPGL4", "NKPG", "SE-NKP-L4", "Multipack and palletizing", "palletizing", 500),
    ("TMPRL1", "TMPR", "FI-TMP-L1", "Oat base enzymatic processing", "blending", 450),
    ("TMPRL2", "TMPR", "FI-TMP-L2", "Aseptic carton filling 1 L", "filling", 450),
    ("TMPRL3", "TMPR", "FI-TMP-L3", "Small format filling and crate packing", "packaging", 350),
    ("POZNL1", "POZN", "PL-POZ-L1", "Bulk mixing and blending", "blending", 450),
    ("POZNL2", "POZN", "PL-POZ-L2", "Liquid filling - shampoo and body wash", "filling", 450),
    ("POZNL3", "POZN", "PL-POZ-L3", "Tube filling - toothpaste and hand cream", "filling", 700),
    ("POZNL4", "POZN", "PL-POZ-L4", "Deodorant roll-on, stick and spray", "filling", 600),
    ("POZNL5", "POZN", "PL-POZ-L5", "Gift set assembly and palletizing", "assembly", 180),
]
SHIFT_HOURS_PER_DAY = 15.0      # two shifts of 7.5 productive hours
LINE = dict((ln[0], ln) for ln in LINES)

# S3 incident: PL-POZ-L2 filler nozzle wear, March 2026; the nozzle set was replaced on
# INCIDENT_END = 2026-04-04 (orders scheduled from that day run normally)
INCIDENT_LINE = "POZNL2"
INCIDENT_START = datetime.date(2026, 3, 1)
INCIDENT_END = datetime.date(2026, 4, 4)
REPAIR_DATE = INCIDENT_END
INCIDENT_REASON_CODE = "EQMALF"
INCIDENT_REASON_TEXT = ("Equipment malfunction - worn filler nozzles on PL-POZ-L2 caused under-fill "
                        "and leaking caps; rejected at checkweigher")

# S4 ramp-up: Tampere OEE from ~55 % (2025-04) to the 78 % target, reached by June 2026
TAMPERE_START = datetime.date(2025, 4, 1)
TAMPERE_RAMP_END = datetime.date(2026, 5, 20)
TAMPERE_OEE_START = 55.0
TAMPERE_OEE_TARGET = 78.8

DCS = [
    {"code": "DCJKG", "name": "Jönköping Distribution Centre", "company": "SE01", "country": "SWE",
     "city": "Jönköping", "region": "SE-F", "postal": "553 03", "street": "Logistikvägen 4",
     "lat": 57.7826, "lon": 14.1618, "sap": "JKG1", "type": "multi_temperature", "opened": datetime.date(2012, 8, 1)},
    {"code": "DCOSL", "name": "Oslo Distribution Centre", "company": "NO01", "country": "NOR",
     "city": "Oslo", "region": "NO-03", "postal": "0668", "street": "Lagerveien 12",
     "lat": 59.9139, "lon": 10.7522, "sap": "OSL1", "type": "ambient", "opened": datetime.date(2015, 3, 1)},
    {"code": "DCODE", "name": "Odense Distribution Centre", "company": "DK01", "country": "DNK",
     "city": "Odense", "region": "DK-83", "postal": "5220", "street": "Lagervej 3",
     "lat": 55.4038, "lon": 10.4024, "sap": "ODE1", "type": "ambient", "opened": datetime.date(2016, 1, 15)},
    {"code": "DCVAN", "name": "Vantaa Distribution Centre", "company": "FI01", "country": "FIN",
     "city": "Vantaa", "region": "FI-18", "postal": "01510", "street": "Varastotie 7",
     "lat": 60.2934, "lon": 25.0378, "sap": "VAN1", "type": "chilled", "opened": datetime.date(2016, 10, 1)},
    {"code": "DCHAM", "name": "Hamburg Distribution Centre", "company": "DE01", "country": "DEU",
     "city": "Hamburg", "region": "DE-HH", "postal": "21107", "street": "Logistikring 15",
     "lat": 53.5511, "lon": 9.9937, "sap": "HAM1", "type": "multi_temperature", "opened": datetime.date(2017, 9, 1)},
]
DC = dict((d["code"], d) for d in DCS)

# --------------------------------------------------------------------------------------
# B2B trade accounts (fictional retailers - never real chains)
# --------------------------------------------------------------------------------------
# (key, legal name, dba, country, company, tier, account_type, trade_channel,
#  brand mix (food, beverage, personal care), payment terms days, invoices per month,
#  avg gross EUR per invoice, headquarters city)
TRADE_ACCOUNTS = [
    ("NORTHCART", "NorthCart Retail AB", "NorthCart", "SWE", "SE01", "tier_1_national", "retailer", "grocery", (0.45, 0.35, 0.20), 30, 14, 24000, "Stockholm"),
    ("VASA", "Vasa Grocers AB", "Vasa Grocers", "SWE", "SE01", "tier_2_regional", "retailer", "grocery", (0.50, 0.35, 0.15), 30, 7, 9000, "Uppsala"),
    ("SKARGARD", "Skärgård Livs Ekonomisk Förening", "Skärgård Livs", "SWE", "SE01", "tier_3_local", "retailer", "convenience", (0.40, 0.50, 0.10), 30, 3, 3200, "Stockholm"),
    ("POLARAPO", "Polar Apotek & Hälsa AB", "Polar Apotek", "SWE", "SE01", "tier_2_regional", "retailer", "pharmacy", (0.05, 0.05, 0.90), 30, 6, 7500, "Luleå"),
    ("NFSP", "Nordic Foodservice Partners AB", "NFS Partners", "SWE", "SE01", "tier_2_regional", "foodservice_operator", "foodservice", (0.60, 0.40, 0.00), 30, 6, 6800, "Göteborg"),
    ("MALARWH", "Mälardalen Wholesale AB", "Mälardalen Grossist", "SWE", "SE01", "tier_3_local", "wholesaler", "cash_and_carry", (0.45, 0.40, 0.15), 30, 3, 4200, "Västerås"),
    ("GOTLAND", "Gotland Gårdsbutik AB", "Gårdsbutiken Visby", "SWE", "SE01", "tier_4_independent", "retailer", "specialty", (0.60, 0.30, 0.10), 30, 2, 1400, "Visby"),
    ("FJORDHANDEL", "Fjordhandel AS", "Fjordhandel", "NOR", "NO01", "tier_1_national", "retailer", "grocery", (0.40, 0.40, 0.20), 30, 12, 21000, "Oslo"),
    ("NORDLYS", "Nordlys Dagligvare AS", "Nordlys", "NOR", "NO01", "tier_2_regional", "retailer", "grocery", (0.45, 0.40, 0.15), 30, 6, 8200, "Tromsø"),
    ("BERGENHK", "Bergen Helsekost AS", "Bergen Helsekost", "NOR", "NO01", "tier_3_local", "retailer", "health_food", (0.55, 0.25, 0.20), 30, 3, 2600, "Bergen"),
    ("LOFOTEN", "Lofoten Kiosk AS", "Lofoten Kiosk", "NOR", "NO01", "tier_4_independent", "retailer", "convenience", (0.30, 0.60, 0.10), 30, 2, 1100, "Svolvær"),
    ("BALTICFM", "Baltic FreshMarket A/S", "Baltic FreshMarket", "DNK", "DK01", "tier_1_national", "retailer", "grocery", (0.40, 0.40, 0.20), 30, 12, 19000, "København"),
    ("ORESUND", "Øresund Discount ApS", "Øresund Discount", "DNK", "DK01", "tier_2_regional", "retailer", "discount", (0.45, 0.45, 0.10), 30, 6, 7000, "Roskilde"),
    ("JYLLAND", "Jylland Grossist A/S", "Jylland Grossist", "DNK", "DK01", "tier_3_local", "wholesaler", "cash_and_carry", (0.50, 0.35, 0.15), 30, 3, 3800, "Aarhus"),
    ("KALEVA", "Kaleva Kauppa Oy", "Kaleva", "FIN", "FI01", "tier_1_national", "retailer", "grocery", (0.40, 0.45, 0.15), 30, 12, 20000, "Helsinki"),
    ("SAIMAA", "Saimaa Market Oy", "Saimaa Market", "FIN", "FI01", "tier_2_regional", "retailer", "grocery", (0.45, 0.40, 0.15), 30, 6, 7600, "Lappeenranta"),
    ("LAPPIAPT", "Lappi Apteekki Oy", "Lappi Apteekki", "FIN", "FI01", "tier_3_local", "retailer", "pharmacy", (0.05, 0.05, 0.90), 30, 3, 2900, "Rovaniemi"),
    ("ALPINA", "Alpina Drogerie GmbH", "Alpina Drogerie", "DEU", "DE01", "tier_1_national", "retailer", "drugstore", (0.15, 0.15, 0.70), 45, 10, 18000, "München"),
    ("RHEINLAND", "Rheinland Frischmarkt GmbH", "Rheinland Frischmarkt", "DEU", "DE01", "tier_2_regional", "retailer", "grocery", (0.45, 0.40, 0.15), 45, 6, 8800, "Köln"),
    ("HANSEBIO", "Hanse Biomarkt GmbH", "Hanse Biomarkt", "DEU", "DE01", "tier_3_local", "retailer", "organic", (0.55, 0.30, 0.15), 45, 3, 3100, "Bremen"),
    ("ALPENGV", "Alpen Getränke Vertrieb GmbH", "Alpen Getränke", "DEU", "DE01", "tier_3_local", "distributor", "beverage_wholesale", (0.00, 1.00, 0.00), 45, 3, 4600, "München"),
    ("POLDER", "Polder Supermarkten B.V.", "Polder Supermarkt", "NLD", "DE01", "tier_2_regional", "retailer", "grocery", (0.45, 0.40, 0.15), 45, 6, 8100, "Rotterdam"),
    ("GRACHTEN", "Grachten Drogist B.V.", "Grachten Drogist", "NLD", "DE01", "tier_3_local", "retailer", "drugstore", (0.05, 0.10, 0.85), 45, 3, 2800, "Amsterdam"),
    ("WARTA", "Warta Drogerie Sp. z o.o.", "Warta Drogerie", "POL", "PL01", "tier_2_regional", "retailer", "drugstore", (0.00, 0.05, 0.95), 30, 6, 6200, "Poznań"),
    ("WIELKOP", "Wielkopolska Hurt Sp. z o.o.", "Wielkopolska Hurt", "POL", "PL01", "tier_3_local", "wholesaler", "cash_and_carry", (0.05, 0.10, 0.85), 30, 3, 3400, "Poznań"),
]
TA_FIELDS = ("key", "legal", "dba", "country", "company", "tier", "type", "channel", "mix",
             "terms", "per_month", "avg_eur", "hq")
TRADE = [dict(zip(TA_FIELDS, r)) for r in TRADE_ACCOUNTS]
TRADE_BY_KEY = dict((t["key"], t) for t in TRADE)
# store-operating retail banners (shoppers' preferred banners, retail_store rows); wholesalers,
# cash & carry, food service and beverage distributors run no consumer-facing stores
RETAIL_CHANNELS = ("grocery", "convenience", "discount", "specialty", "organic", "health_food", "drugstore",
                   "pharmacy")
RETAIL_BANNERS = [t for t in TRADE if t["type"] == "retailer" and t["channel"] in RETAIL_CHANNELS]

# cities that are only used as headquarters of trade accounts
EXTRA_CITIES = {
    "SWE": [("Visby", "SE-I", 57.6348, 18.2948, "621 ##")],
    "NOR": [("Svolvær", "NO-18", 68.2343, 14.5683, "83##")],
    "FIN": [("Lappeenranta", "FI-02", 61.0587, 28.1887, "53###"), ("Rovaniemi", "FI-10", 66.5039, 25.7294, "96###")],
}


def city(country, name):
    """The CITIES / EXTRA_CITIES tuple of ``name`` in ``country``."""
    for c in CITIES.get(country, []) + EXTRA_CITIES.get(country, []):
        if c[0] == name:
            return c
    raise KeyError((country, name))

# S6: Alpina Drogerie disputes invoices from June 2026 onwards
DISPUTE_ACCOUNT = "ALPINA"
DISPUTE_FROM = datetime.date(2026, 6, 1)
CREDIT_HOLD_DATE = datetime.date(2026, 9, 28)   # new orders blocked from this day (no billing after it)

# --------------------------------------------------------------------------------------
# loyalty programme
# --------------------------------------------------------------------------------------

LOYALTY_PROGRAM = {"code": "FJFRIENDS", "name": "Fjällmark Friends", "launched": datetime.date(2019, 3, 1)}
# name, code, rank, points multiplier, member discount %, free shipping, required points (lifetime),
# required qualifying spend in the last 12 months (EUR; model column required_spend_usd), share of
# members at enrolment. The annual tier review moves members who meet neither the points nor the
# spend requirement of their tier down to the highest tier they qualify for.
LOYALTY_TIERS = [
    ("Bronze", "BRONZE", 1, D("1.00"), D("0.00"), False, 0, D("0.00"), 0.48),
    ("Silver", "SILVER", 2, D("1.25"), D("2.00"), False, 150, D("40.00"), 0.28),
    ("Gold", "GOLD", 3, D("1.50"), D("5.00"), True, 250, D("60.00"), 0.16),
    ("Platinum", "PLATINUM", 4, D("2.00"), D("8.00"), True, 400, D("100.00"), 0.08),
]
TIER_FIELDS = ("name", "code", "rank", "multiplier", "discount_pct", "free_shipping",
               "required_points", "required_spend", "share")
TIERS = [dict(zip(TIER_FIELDS, t)) for t in LOYALTY_TIERS]
TIER = dict((t["name"], t) for t in TIERS)
POINT_VALUE_EUR = D("0.01")  # 100 points = 1 EUR

# --------------------------------------------------------------------------------------
# seasonality and growth
# --------------------------------------------------------------------------------------

_ORDER_SEASON = {1: 0.90, 2: 0.86, 3: 0.95, 4: 0.96, 5: 1.00, 6: 1.08, 7: 1.08, 8: 1.05,
                 9: 0.98, 10: 1.02, 11: 1.35, 12: 1.35}


def order_season(month):
    """Relative DTC order volume by calendar month (Q4 Christmas peak)."""
    return _ORDER_SEASON[month]


def category_season(category, month, season_tag=None):
    """Relative demand weight of a product category in a month."""
    w = 1.0
    if category == "BEVERAGE" and month in (6, 7, 8):
        w *= 1.40
    if category == "FOOD" and month in (11, 12):
        w *= 1.30
    if category == "PERSONAL_CARE" and month in (11, 12):
        w *= 0.72          # personal care is flat: offsets the general Christmas peak in order volume
    if season_tag == "XMAS":
        w = w * 2.5 if month in (11, 12) else 0.0
    if season_tag == "SUMMER":
        w = w * 1.8 if month in (5, 6, 7, 8) else 0.0
    return w


def dtc_growth(y, m):
    """Growth of the DTC order count (~15 % a year); with a stable to slightly rising average order
    value DTC sales value grows ~18 % a year."""
    return 1.15 ** (month_index(y, m) / 12.0)


def b2b_growth(y, m):
    """B2B grows 5 % year on year."""
    return 1.05 ** (month_index(y, m) / 12.0)


def b2b_season(category, month):
    """B2B billing seasonality: beverages peak in summer, food at Christmas, personal care flat."""
    w = 1.0
    if category == "BEVERAGE" and month in (6, 7, 8):
        w = 1.40
    elif category == "FOOD" and month in (11, 12):
        w = 1.35
    return w


def sku_available(sku, day):
    """True when ``sku`` can be sold/produced on ``day`` (launch date and seasonality)."""
    if day < sku["launch"]:
        return False
    if sku["season"] == "XMAS" and day.month not in (10, 11, 12):
        return False
    if sku["season"] == "SUMMER" and day.month not in (5, 6, 7, 8):
        return False
    return True


def local_price_excl_vat(sku, market):
    """DTC unit price (excl. VAT) in the market currency, from a rounded shelf price."""
    cur = market["currency"]
    rsp_local = sku["rsp_eur"] / D(str(FX_BASE[cur]))
    if cur in ("SEK", "NOK", "DKK"):
        shelf = (rsp_local).quantize(D("1")) - D("0.10")      # e.g. 29.90
        if shelf < D("5"):
            shelf = D("4.90")
    else:
        shelf = rsp_local.quantize(D("0.1")) - D("0.01")      # e.g. 2.49
        if shelf < D("0.5"):
            shelf = D("0.49")
    return (shelf / (D(1) + market["vat"])).quantize(D("0.0001"))


# --------------------------------------------------------------------------------------
# GL chart of accounts (shared numbering, one copy per company code)
# --------------------------------------------------------------------------------------
# number, name, short, group, account_type, pl_category, fs_category, fs_line, normal side
GL_ACCOUNTS = [
    ("1110", "Bank - operating account", "Bank", "ASSET", "asset", "not_applicable", "balance_sheet", "Cash and cash equivalents", "debit"),
    ("1210", "Trade receivables", "Trade AR", "ASSET", "asset", "not_applicable", "balance_sheet", "Trade and other receivables", "debit"),
    ("1240", "Payment service provider clearing", "PSP clearing", "ASSET", "asset", "not_applicable", "balance_sheet", "Trade and other receivables", "debit"),
    ("1290", "Accumulated depreciation - machinery", "Acc. depreciation", "ASSET", "asset", "not_applicable", "balance_sheet", "Property, plant and equipment", "credit"),
    ("1410", "Finished goods inventory", "FG inventory", "ASSET", "asset", "not_applicable", "balance_sheet", "Inventories", "debit"),
    ("1420", "Work in progress", "WIP", "ASSET", "asset", "not_applicable", "balance_sheet", "Inventories", "debit"),
    ("1430", "Raw and packaging materials", "Materials", "ASSET", "asset", "not_applicable", "balance_sheet", "Inventories", "debit"),
    ("1510", "Input VAT receivable", "Input VAT", "ASSET", "asset", "not_applicable", "balance_sheet", "Other current assets", "debit"),
    ("2110", "Trade payables", "Trade AP", "LIABILITY", "liability", "not_applicable", "balance_sheet", "Trade and other payables", "credit"),
    ("2410", "Accrued expenses", "Accruals", "LIABILITY", "liability", "not_applicable", "balance_sheet", "Trade and other payables", "credit"),
    ("2610", "Output VAT payable", "Output VAT", "LIABILITY", "liability", "not_applicable", "balance_sheet", "Other current liabilities", "credit"),
    ("2710", "Payroll liabilities", "Payroll liab.", "LIABILITY", "liability", "not_applicable", "balance_sheet", "Other current liabilities", "credit"),
    ("2810", "Loyalty points liability", "Loyalty liab.", "LIABILITY", "liability", "not_applicable", "balance_sheet", "Contract liabilities", "credit"),
    ("2990", "Retained earnings", "Ret. earnings", "EQUITY", "equity", "not_applicable", "retained_earnings", "Retained earnings", "credit"),
    ("3000", "Revenue - trade customers", "Rev. trade", "REVENUE", "revenue", "net_revenue", "income_statement", "Net revenue", "credit"),
    ("3010", "Revenue - DTC webshop", "Rev. DTC", "REVENUE", "revenue", "net_revenue", "income_statement", "Net revenue", "credit"),
    ("3040", "Trade discounts and rebates", "Trade discounts", "REVENUE", "revenue", "net_revenue", "income_statement", "Net revenue", "debit"),
    ("3050", "Sales returns - DTC", "DTC returns", "REVENUE", "revenue", "net_revenue", "income_statement", "Net revenue", "debit"),
    ("3900", "Shipping fees charged to consumers", "Shipping income", "OTHER_INCOME", "revenue", "ebitda", "income_statement", "Other operating income", "credit"),
    ("4000", "Cost of goods sold - standard cost", "COGS", "COGS", "expense", "cogs", "income_statement", "Cost of goods sold", "debit"),
    ("4100", "Production variances", "Prod. variance", "COGS", "expense", "cogs", "income_statement", "Cost of goods sold", "debit"),
    ("5000", "Salaries and wages", "Salaries", "OPEX", "expense", "operating_expense", "income_statement", "Personnel expenses", "debit"),
    ("6100", "Marketing and advertising", "Marketing", "OPEX", "expense", "operating_expense", "income_statement", "Selling and marketing expenses", "debit"),
    ("6300", "Freight and logistics", "Freight", "OPEX", "expense", "operating_expense", "income_statement", "Distribution expenses", "debit"),
    ("6400", "Rent, utilities and maintenance", "Rent & utilities", "OPEX", "expense", "operating_expense", "income_statement", "Administrative expenses", "debit"),
    ("7000", "Depreciation - machinery and equipment", "Depreciation", "OPEX", "expense", "ebit", "income_statement", "Depreciation and amortisation", "debit"),
]
GL_FIELDS = ("number", "name", "short", "group", "type", "pl", "fs", "fs_line", "side")
GL = [dict(zip(GL_FIELDS, g)) for g in GL_ACCOUNTS]
GL_BY_NUMBER = dict((g["number"], g) for g in GL)
REVENUE_ACCOUNTS = tuple(g["number"] for g in GL if g["group"] == "REVENUE")
