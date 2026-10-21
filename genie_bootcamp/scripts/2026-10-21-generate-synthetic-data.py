"""
Synthetic data generator for the Databricks Genie Bootcamp (Scandinavian retail).

Scope : Sweden, Norway, Denmark - 10 stores + 1 online channel
Brands: Electrolux (SE), LEGO (DK), Helly Hansen (NO) - 5 products each
Period: 2024-01-01 .. 2026-09-30, amounts in EUR, fake PII only.

The product names refer to real brands for realism; every price, cost, volume and
customer in this dataset is invented and has nothing to do with the real companies.

Data-quality issues are injected on purpose for the Silver layer to fix:
  * exact duplicate rows                       (customers, products, store items, payments, sessions)
  * extra spaces and mixed casing             (names, cities, countries, tiers, payment methods)
  * one non-ISO date format                    (customers.signup_date as dd.MM.yyyy)
  * invalid order lines                        (quantity 0, unknown customer C9999)
  * countries without a region                 (Faroe Islands customers)

Usage:  python 2026-10-21-generate-synthetic-data.py [output_root]
        default output_root = ../data/raw  (relative to this script)
"""
import os
import sys
import datetime as dt
import numpy as np
import pandas as pd

SEED = 42
RUN_DATE = "2026-10-21"
START = dt.date(2024, 1, 1)
END = dt.date(2026, 9, 30)
INV_DAYS = 90
TARGET_VALID_LINES = 1990

rng = np.random.default_rng(SEED)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "data", "raw")


def d(x):
    return x.strftime("%Y-%m-%d")


def ts(x):
    return x.strftime("%Y-%m-%d %H:%M:%S")


def write(entity, df):
    folder = os.path.join(OUT, entity)
    os.makedirs(folder, exist_ok=True)
    df.to_csv(os.path.join(folder, f"{RUN_DATE}-raw-{entity}.csv"), index=False)
    print(f"{entity:<22} {len(df):>6} rows")


def dup_rows(df, n):
    """Append n exact duplicate rows (DQ issue) and shuffle."""
    extra = df.sample(n=n, random_state=int(rng.integers(1e6)))
    return pd.concat([df, extra]).sample(frac=1, random_state=int(rng.integers(1e6))).reset_index(drop=True)


def messy(s, p=0.12):
    """Randomly add spaces / change casing."""
    r = rng.random()
    if r < p / 3:
        return f"  {s}"
    if r < 2 * p / 3:
        return f"{s.upper()} "
    if r < p:
        return s.lower()
    return s


# ------------------------------------------------------------------ master data
country_region = pd.DataFrame([
    ("SE", "Sweden", "Scandinavia East"),
    ("NO", "Norway", "Scandinavia West"),
    ("DK", "Denmark", "Scandinavia South"),
], columns=["country_code", "country_name", "region"])   # Faroe Islands intentionally missing

channels = pd.DataFrame([("STORE", "Store", "Physical store"), ("ONLINE", "Online", "Web shop")],
                        columns=["channel_id", "channel_name", "description"])

stores = pd.DataFrame([
    ("ST01", "Mall of Scandinavia", "STORE", "Sweden", "Stockholm", "2015-11-12"),
    ("ST02", "Gallerian Stockholm", "STORE", "Sweden", "Stockholm", "2012-03-01"),
    ("ST03", "Nordstan Gothenburg", "STORE", "Sweden", "Gothenburg", "2014-05-20"),
    ("ST04", "Emporia Malmo", "STORE", "Sweden", "Malmo", "2016-09-15"),
    ("ST05", "Storo Oslo", "STORE", "Norway", "Oslo", "2013-04-10"),
    ("ST06", "Byporten Oslo", "STORE", "Norway", "Oslo", "2018-02-01"),
    ("ST07", "Lagunen Bergen", "STORE", "Norway", "Bergen", "2017-10-05"),
    ("ST08", "Fields Copenhagen", "STORE", "Denmark", "Copenhagen", "2014-03-01"),
    ("ST09", "Stroget Copenhagen", "STORE", "Denmark", "Copenhagen", "2011-06-18"),
    ("ST10", "Bruuns Galleri Aarhus", "STORE", "Denmark", "Aarhus", "2019-08-22"),
    ("ON01", "Online Store", "ONLINE", "Sweden", "Stockholm", "2015-01-01"),
], columns=["store_id", "store_name", "channel_id", "country", "city", "opening_date"])
STORE_IDS = stores.store_id.tolist()[:10]
STORE_COUNTRY = dict(zip(stores.store_id, stores.country))

# ------------------------------------------------------------------ ERP
suppliers = pd.DataFrame([
    ("SUP01", "Electrolux Nordic AB", "Sweden", 21, 60),
    ("SUP02", "LEGO Nordic A/S", "Denmark", 14, 45),
    ("SUP03", "Helly Hansen AS", "Norway", 28, 30),
], columns=["supplier_id", "supplier_name", "country", "lead_time_days", "payment_terms_days"])

product_categories = pd.DataFrame([
    ("CAT01", "Home Appliances", "Dishwashers"),
    ("CAT02", "Home Appliances", "Laundry"),
    ("CAT03", "Home Appliances", "Floor Care"),
    ("CAT04", "Home Appliances", "Cooking"),
    ("CAT05", "Home Appliances", "Air Care"),
    ("CAT06", "Toys", "Construction Sets"),
    ("CAT07", "Toys", "Display Models"),
    ("CAT08", "Outdoor Apparel", "Shell Jackets"),
    ("CAT09", "Outdoor Apparel", "Midlayers"),
    ("CAT10", "Outdoor Apparel", "Base Layers"),
    ("CAT11", "Outdoor Apparel", "Rainwear"),
    ("CAT12", "Outdoor Apparel", "Ski Jackets"),
], columns=["category_id", "category_name", "sub_category_name"])

# product_id, sku, name, brand, category_id, supplier, list_price, unit_cost, launch_date, season_profile
P = [
    ("P001", "ELX-DW600", "Electrolux 600 Series Dishwasher", "Electrolux", "CAT01", "SUP01", 649.00, 410.00, "2023-03-01", "bf"),
    ("P002", "ELX-WM700", "Electrolux 700 Series Washing Machine", "Electrolux", "CAT02", "SUP01", 799.00, 505.00, "2023-01-15", "bf"),
    ("P003", "ELX-VCQ9", "Electrolux Pure Q9 Cordless Vacuum", "Electrolux", "CAT03", "SUP01", 349.00, 205.00, "2023-09-01", "bf"),
    ("P004", "ELX-IH800", "Electrolux 800 Series Induction Hob", "Electrolux", "CAT04", "SUP01", 899.00, 575.00, "2024-02-01", "bf"),
    ("P005", "ELX-AP500", "Electrolux UltimateHome 500 Air Purifier", "Electrolux", "CAT05", "SUP01", 299.00, 170.00, "2024-04-01", "summer"),
    ("P006", "LEG-TEC-SC", "LEGO Technic Supercar", "LEGO", "CAT06", "SUP02", 449.00, 250.00, "2023-06-01", "xmas"),
    ("P007", "LEG-CTY-FS", "LEGO City Fire Station", "LEGO", "CAT06", "SUP02", 89.00, 44.00, "2023-01-01", "xmas"),
    ("P008", "LEG-FRD-HC", "LEGO Friends Heartlake Cafe", "LEGO", "CAT06", "SUP02", 49.00, 23.00, "2024-01-01", "xmas"),
    ("P009", "LEG-CRT-PS", "LEGO Creator 3-in-1 Pirate Ship", "LEGO", "CAT06", "SUP02", 99.00, 50.00, "2023-08-01", "xmas"),
    ("P010", "LEG-ICN-FB", "LEGO Icons Flower Bouquet", "LEGO", "CAT07", "SUP02", 59.00, 28.00, "2023-02-01", "flat"),
    ("P011", "HH-ODN-SH", "Helly Hansen Odin Shell Jacket", "Helly Hansen", "CAT08", "SUP03", 449.00, 195.00, "2023-08-15", "winter"),
    ("P012", "HH-CRW-ML", "Helly Hansen Crew Midlayer Jacket", "Helly Hansen", "CAT09", "SUP03", 179.00, 78.00, "2023-08-15", "winter"),
    ("P013", "HH-LFA-MB", "Helly Hansen Lifa Merino Base Layer", "Helly Hansen", "CAT10", "SUP03", 79.00, 33.00, "2023-09-01", "winter"),
    ("P014", "HH-MSS-RJ", "Helly Hansen Moss Rain Jacket", "Helly Hansen", "CAT11", "SUP03", 69.00, 27.00, "2023-03-01", "summer"),
    ("P015", "HH-ULR-SK", "Helly Hansen Ullr Ski Jacket", "Helly Hansen", "CAT12", "SUP03", 299.00, 130.00, "2024-09-01", "winter"),
]
products = pd.DataFrame([p[:9] for p in P], columns=[
    "product_id", "sku", "product_name", "brand", "category_id", "supplier_id",
    "list_price", "unit_cost", "launch_date"])
products["is_active"] = "Y"
PROFILE = {p[0]: p[9] for p in P}
PRICE = dict(zip(products.product_id, products.list_price))
COST = dict(zip(products.product_id, products.unit_cost))
LAUNCH = {p[0]: dt.date.fromisoformat(p[8]) for p in P}
PIDS = products.product_id.tolist()

# ------------------------------------------------------------------ marketing
campaigns = pd.DataFrame([
    ("CMP01", "Black Friday 2024", "Paid social + email", "2024-11-18", "2024-12-02", 45000),
    ("CMP02", "Christmas 2024", "TV + display", "2024-12-03", "2024-12-23", 60000),
    ("CMP03", "Summer Sale 2024", "Email + search", "2024-06-17", "2024-07-31", 30000),
    ("CMP04", "Summer Sale 2025", "Email + search", "2025-06-16", "2025-07-31", 32000),
    ("CMP05", "Black Friday 2025", "Paid social + email", "2025-11-17", "2025-12-01", 50000),
    ("CMP06", "Christmas 2025", "TV + display", "2025-12-02", "2025-12-23", 65000),
    ("CMP07", "Winter Outdoor 2025", "Outdoor media", "2025-10-01", "2025-10-31", 20000),
    ("CMP08", "Summer Sale 2026", "Email + search", "2026-06-15", "2026-07-31", 34000),
], columns=["campaign_id", "campaign_name", "media_mix", "start_date", "end_date", "budget_eur"])

promotions = pd.DataFrame([
    ("PR01", "Black Friday 2024", "Seasonal discount", 20, "2024-11-25", "2024-12-02", "CMP01"),
    ("PR02", "Christmas Gift Deal 2024", "Seasonal discount", 10, "2024-12-03", "2024-12-23", "CMP02"),
    ("PR03", "Summer Sale 2024", "Clearance", 15, "2024-06-17", "2024-07-31", "CMP03"),
    ("PR04", "Summer Sale 2025", "Clearance", 15, "2025-06-16", "2025-07-31", "CMP04"),
    ("PR05", "Black Friday 2025", "Seasonal discount", 25, "2025-11-24", "2025-12-01", "CMP05"),
    ("PR06", "Christmas Gift Deal 2025", "Seasonal discount", 10, "2025-12-02", "2025-12-23", "CMP06"),
    ("PR07", "Winter Outdoor Week", "Category discount", 20, "2025-10-01", "2025-10-31", "CMP07"),
    ("PR08", "Summer Sale 2026", "Clearance", 15, "2026-06-15", "2026-07-31", "CMP08"),
    ("PR09", "Loyalty Spring Bonus", "Loyalty", 5, "2025-03-01", "2025-04-30", None),
], columns=["promotion_id", "promotion_name", "promotion_type", "discount_pct", "start_date", "end_date", "campaign_id"])
PROMOS = [(r.promotion_id, r.discount_pct, dt.date.fromisoformat(r.start_date), dt.date.fromisoformat(r.end_date))
          for r in promotions.itertuples()]

# ------------------------------------------------------------------ CRM
FIRST_F = ["Anna", "Emma", "Maja", "Ingrid", "Astrid", "Freja", "Ida", "Sofie", "Nora", "Elsa",
           "Linnea", "Sara", "Karin", "Mette", "Hanna", "Liv", "Signe", "Julie", "Klara", "Tove"]
FIRST_M = ["Erik", "Lars", "Magnus", "Oskar", "Nils", "Anders", "Mikkel", "Johan", "Henrik", "Jonas",
           "Lukas", "Emil", "Mathias", "Olav", "Sven", "Kasper", "Viktor", "Axel", "Frederik", "Jakob"]
LAST = ["Andersson", "Johansson", "Karlsson", "Nilsson", "Eriksson", "Larsson", "Lindqvist", "Berg",
        "Hansen", "Johansen", "Olsen", "Larsen", "Haugen", "Bakke", "Nielsen", "Jensen", "Pedersen",
        "Christensen", "Sorensen", "Dahl", "Lund", "Holm", "Strand", "Moller", "Vik"]
CITIES = {"Sweden": ["Stockholm", "Gothenburg", "Malmo", "Uppsala"],
          "Norway": ["Oslo", "Bergen", "Trondheim", "Stavanger"],
          "Denmark": ["Copenhagen", "Aarhus", "Odense", "Aalborg"],
          "Faroe Islands": ["Torshavn"]}
NATIVE = {"Sweden": "Sverige", "Norway": "Norge", "Denmark": "Danmark"}
DIAL = {"Sweden": "46", "Norway": "47", "Denmark": "45", "Faroe Islands": "298"}

n_cust = 200
cust_rows, clean_customers = [], []
countries = rng.choice(["Sweden", "Norway", "Denmark"], size=n_cust, p=[0.42, 0.29, 0.29]).tolist()
for i in (17, 88, 151):
    countries[i] = "Faroe Islands"
for i in range(n_cust):
    cid = f"C{i + 1:04d}"
    gender = rng.choice(["F", "M", "X"], p=[0.49, 0.49, 0.02])
    fn = rng.choice(FIRST_F if gender == "F" else FIRST_M if gender == "M" else FIRST_F + FIRST_M)
    ln = rng.choice(LAST)
    country = countries[i]
    city = rng.choice(CITIES[country])
    dob = dt.date(1950, 1, 1) + dt.timedelta(days=int(rng.integers(0, 365 * 55)))
    if rng.random() < 0.6:
        signup = dt.date(2021, 1, 1) + dt.timedelta(days=int(rng.integers(0, 1095)))
    else:
        signup = START + dt.timedelta(days=int(rng.integers(0, (dt.date(2026, 8, 31) - START).days)))
    active = rng.random() < 0.92
    clean_customers.append((cid, signup, country))
    g_raw = {"F": rng.choice(["F", "Female", "female "]), "M": rng.choice(["M", "Male", " male"]), "X": "X"}[gender]
    c_raw = country
    if country in NATIVE and rng.random() < 0.10:
        c_raw = NATIVE[country]
    signup_raw = signup.strftime("%d.%m.%Y") if rng.random() < 0.15 else d(signup)
    cust_rows.append(dict(
        customer_id=cid, first_name=messy(fn), last_name=messy(ln),
        email=f"{fn.lower()}.{ln.lower()}{i + 1}@example.com" if rng.random() > 0.05 else f"{fn}.{ln}{i + 1}@EXAMPLE.com ",
        phone=f"+{DIAL[country]} 000 {rng.integers(1000, 9999)} {rng.integers(100, 999)}",
        gender=g_raw, date_of_birth=d(dob), country=messy(c_raw), city=messy(city),
        signup_date=signup_raw, is_active=rng.choice(["Y", "y", "Y "]) if active else rng.choice(["N", "n"])))
customers = dup_rows(pd.DataFrame(cust_rows), 6)
CUST_SIGNUP = {c: s for c, s, _ in clean_customers}
CUST_COUNTRY = {c: k for c, _, k in clean_customers}
CUSTS = [c for c, _, _ in clean_customers]

addr = []
for c, _, country in clean_customers:
    addr.append((f"A{len(addr) + 1:05d}", c, "Home", f"Exempelgatan {rng.integers(1, 120)}",
                 f"{rng.integers(1000, 9999)}", rng.choice(CITIES[country]), country))
    if rng.random() < 0.25:
        addr.append((f"A{len(addr) + 1:05d}", c, "Delivery", f"Testvagen {rng.integers(1, 80)}",
                     f"{rng.integers(1000, 9999)}", rng.choice(CITIES[country]), country))
customer_addresses = pd.DataFrame(addr, columns=["address_id", "customer_id", "address_type", "street",
                                                 "postal_code", "city", "country"])

loy = []
for c in CUSTS:
    if rng.random() < 0.7:
        tier = rng.choice(["Bronze", "Silver", "Gold", "Platinum"], p=[0.45, 0.30, 0.18, 0.07])
        loy.append((f"L{len(loy) + 1:04d}", c, messy(tier, 0.2), int(rng.integers(0, 25000)), d(CUST_SIGNUP[c])))
loyalty_members = pd.DataFrame(loy, columns=["member_id", "customer_id", "loyalty_tier", "points_balance", "enrolled_date"])

# ------------------------------------------------------------------ orders (POS + e-commerce)
days = [START + dt.timedelta(days=k) for k in range((END - START).days + 1)]


def day_weight(x):
    w = 1.0
    if x.month == 11 and 22 <= x.day <= 30:
        w = 4.5                                   # Black Friday week
    elif x.month == 12 and x.day <= 23:
        w = 2.6                                   # Christmas shopping
    elif (x.month == 6 and x.day >= 15) or x.month == 7:
        w = 1.8                                   # Summer sale
    elif x.month in (1, 2):
        w = 0.7
    if x.weekday() >= 5:
        w *= 1.3
    return w * (1 + 0.12 * (x.year - 2024))      # mild growth


dw = np.array([day_weight(x) for x in days])
dw = dw / dw.sum()


def product_weight(pid, x):
    prof, m = PROFILE[pid], x.month
    w = 1.0
    if prof == "bf" and m == 11:
        w = 3.0
    if prof == "xmas" and m == 12:
        w = 3.5
    if prof == "winter":
        w = 2.5 if m in (10, 11, 12, 1, 2) else 0.4
    if prof == "summer":
        w = 2.2 if m in (5, 6, 7, 8) else 0.6
    if LAUNCH[pid] > x:
        w = 0.0
    return w


def promo_for(x):
    hits = [p for p in PROMOS if p[2] <= x <= p[3]]
    if hits and rng.random() < 0.75:
        return hits[0]
    return None


on_orders, on_items, st_orders, st_items = [], [], [], []
valid_lines = 0
on_seq = st_seq = oi_seq = si_seq = 0
order_facts = []   # clean truth for checks: (channel, order_id, ts, cust, store, promo, items)
while valid_lines < TARGET_VALID_LINES:
    day = days[int(rng.choice(len(days), p=dw))]
    online = rng.random() < 0.32
    eligible = [c for c in CUSTS if CUST_SIGNUP[c] <= day]
    if not online:
        store = rng.choice(STORE_IDS)
        local = [c for c in eligible if CUST_COUNTRY[c] == STORE_COUNTRY[store]]
        cust = rng.choice(local if local and rng.random() < 0.85 else eligible)
        t = dt.datetime.combine(day, dt.time(int(rng.integers(10, 20)), int(rng.integers(0, 60)), int(rng.integers(0, 60))))
    else:
        store = "ON01"
        cust = rng.choice(eligible)
        t = dt.datetime.combine(day, dt.time(int(rng.choice(range(24), p=np.array(
            [1, 1, 1, 1, 1, 1, 2, 3, 4, 5, 5, 5, 6, 6, 5, 5, 5, 6, 8, 10, 11, 10, 7, 3]) / 112)),
            int(rng.integers(0, 60)), int(rng.integers(0, 60))))
    pw = np.array([product_weight(p, day) for p in PIDS])
    n_lines = int(rng.choice([1, 2, 3], p=[0.62, 0.28, 0.10]))
    picks = rng.choice(PIDS, size=min(n_lines, int((pw > 0).sum())), replace=False, p=pw / pw.sum())
    promo = promo_for(day)
    if online:
        on_seq += 1
        oid = f"WEB-{on_seq:06d}"
        pay = rng.choice(["Card", "Klarna", "Swish", "Vipps", "MobilePay"], p=[0.45, 0.25, 0.12, 0.09, 0.09])
    else:
        st_seq += 1
        oid = f"POS-{st_seq:06d}"
        local_mobile = {"Sweden": "Swish", "Norway": "Vipps", "Denmark": "MobilePay"}[STORE_COUNTRY[store]]
        pay = rng.choice(["Card", local_mobile, "Cash"], p=[0.68, 0.24, 0.08])
    items = []
    for pid in picks:
        qty = int(rng.choice([1, 1, 1, 1, 2, 2, 3])) if PRICE[pid] < 150 else 1
        price = PRICE[pid]
        disc = round(qty * price * promo[1] / 100, 2) if promo else 0.0
        if online:
            oi_seq += 1
            iid = f"WEBI-{oi_seq:07d}"
        else:
            si_seq += 1
            iid = f"POSI-{si_seq:07d}"
        items.append((iid, pid, qty, price, disc))
    status = "Completed"
    if online and (END - day).days < 3:
        status = "Processing"
    hdr = dict(order_id=oid, order_ts=ts(t), customer_id=cust, promotion_id=promo[0] if promo else "",
               order_status=messy(status, 0.1), payment_method=messy(pay, 0.15))
    if online:
        on_orders.append(hdr)
        on_items += [dict(order_item_id=i, order_id=oid, product_id=p, quantity=q, unit_price=f"{u:.2f}",
                          discount_amount=f"{di:.2f}") for i, p, q, u, di in items]
    else:
        hdr["store_id"] = store
        st_orders.append(hdr)
        st_items += [dict(order_item_id=i, order_id=oid, product_id=p, quantity=q, unit_price=f"{u:.2f}",
                          discount_amount=f"{di:.2f}") for i, p, q, u, di in items]
    order_facts.append(dict(channel="Online" if online else "Store", order_id=oid, ts=t, customer_id=cust,
                            store_id=store, pay=pay, status=status, items=items))
    valid_lines += len(items)

# ---- inject invalid order lines
# (a) quantity 0 on existing orders
for lst, prefix in ((st_items, "POSI"), (on_items, "WEBI")):
    for k in range(4):
        base = lst[int(rng.integers(0, len(lst)))]
        nid = f"{prefix}-9{k + 1:06d}"
        lst.append(dict(order_item_id=nid, order_id=base["order_id"], product_id=rng.choice(PIDS),
                        quantity=0, unit_price=base["unit_price"], discount_amount="0.00"))
# (b) orders from an unknown customer (C9999)
for k in range(2):
    day = days[int(rng.integers(0, len(days)))]
    oid = f"POS-9{k + 1:05d}"
    st_orders.append(dict(order_id=oid, order_ts=ts(dt.datetime.combine(day, dt.time(14, 5, 0))), customer_id="C9999",
                          promotion_id="", order_status="Completed", payment_method="Card", store_id="ST02"))
    for j in range(1 + k):
        pid = PIDS[int(rng.integers(0, 15))]
        st_items.append(dict(order_item_id=f"POSI-8{k}{j:05d}", order_id=oid, product_id=pid, quantity=1,
                             unit_price=f"{PRICE[pid]:.2f}", discount_amount="0.00"))

online_orders = pd.DataFrame(on_orders)
online_order_items = pd.DataFrame(on_items)
store_orders = pd.DataFrame(st_orders)[["order_id", "order_ts", "store_id", "customer_id", "promotion_id",
                                        "order_status", "payment_method"]]
store_order_items = dup_rows(pd.DataFrame(st_items), 8)

# ------------------------------------------------------------------ e-commerce sessions + cart events
sessions, carts = [], []
s_seq = 0
web_facts = [o for o in order_facts if o["channel"] == "Online"]
for o in web_facts:
    s_seq += 1
    sid = f"S{s_seq:06d}"
    start = o["ts"] - dt.timedelta(minutes=int(rng.integers(5, 45)))
    sessions.append(dict(session_id=sid, customer_id=o["customer_id"], session_start_ts=ts(start),
                         device=rng.choice(["Mobile", "Desktop", "Tablet"], p=[0.58, 0.34, 0.08]),
                         traffic_source=rng.choice(["Organic", "Paid Search", "Email", "Social", "Direct"],
                                                   p=[0.28, 0.22, 0.2, 0.12, 0.18]),
                         pages_viewed=int(rng.integers(4, 25)), added_to_cart_flag=1, ordered_flag=1))
    for iid, pid, q, _, _ in o["items"]:
        carts.append((sid, start + dt.timedelta(minutes=2), pid, "add_to_cart", q))
    if rng.random() < 0.2:
        carts.append((sid, start + dt.timedelta(minutes=3), rng.choice(PIDS), "add_to_cart", 1))
        carts.append((sid, start + dt.timedelta(minutes=4), carts[-1][2], "remove_from_cart", 1))
for o in web_facts:
    pass
order_session = {o["order_id"]: f"S{k + 1:06d}" for k, o in enumerate(web_facts)}
online_orders.insert(3, "session_id", online_orders.order_id.map(order_session).fillna(""))

while len(sessions) < 5000:
    s_seq += 1
    sid = f"S{s_seq:06d}"
    day = days[int(rng.choice(len(days), p=dw))]
    start = dt.datetime.combine(day, dt.time(int(rng.integers(0, 24)), int(rng.integers(0, 60)), int(rng.integers(0, 60))))
    known = rng.random() < 0.55
    cust = rng.choice([c for c in CUSTS if CUST_SIGNUP[c] <= day]) if known else ""
    added = int(rng.random() < 0.22)
    sessions.append(dict(session_id=sid, customer_id=cust, session_start_ts=ts(start),
                         device=rng.choice(["Mobile", "Desktop", "Tablet"], p=[0.62, 0.30, 0.08]),
                         traffic_source=rng.choice(["Organic", "Paid Search", "Email", "Social", "Direct"],
                                                   p=[0.30, 0.22, 0.12, 0.20, 0.16]),
                         pages_viewed=int(rng.integers(1, 14)), added_to_cart_flag=added, ordered_flag=0))
    if added:
        pid = rng.choice(PIDS)
        carts.append((sid, start + dt.timedelta(minutes=1), pid, "add_to_cart", 1))
        if rng.random() < 0.4:
            carts.append((sid, start + dt.timedelta(minutes=2), pid, "remove_from_cart", 1))
web_sessions = pd.DataFrame(sessions).sort_values("session_start_ts").reset_index(drop=True)
web_sessions = dup_rows(web_sessions, 10)
cart_events = pd.DataFrame([(f"E{k + 1:06d}", s, ts(t), p, e, q) for k, (s, t, p, e, q) in enumerate(carts)],
                           columns=["event_id", "session_id", "event_ts", "product_id", "event_type", "quantity"])

# ------------------------------------------------------------------ payments, shipments, returns, refunds
pays, ships, rets, refs = [], [], [], []
for o in order_facts:
    total = sum(q * u - di for _, _, q, u, di in o["items"])
    pid_ = f"PAY-{len(pays) + 1:06d}"
    pays.append(dict(payment_id=pid_, order_id=o["order_id"],
                     payment_ts=ts(o["ts"] + dt.timedelta(seconds=int(rng.integers(5, 90)))),
                     amount=f"{total:.2f}", payment_method=o["pay"], payment_status="Captured"))
    if o["channel"] == "Online":
        ship = o["ts"].date() + dt.timedelta(days=int(rng.choice([0, 1, 1, 2])))
        dd_ = int(rng.choice([1, 2, 2, 3, 3, 4, 5, 6], p=[0.12, 0.22, 0.18, 0.2, 0.1, 0.08, 0.06, 0.04]))
        delivery = ship + dt.timedelta(days=dd_)
        delivered = delivery <= END
        ships.append(dict(shipment_id=f"SHP-{len(ships) + 1:06d}", order_id=o["order_id"], warehouse_id="WH01",
                          ship_date=d(ship) if ship <= END else "", delivery_date=d(delivery) if delivered else "",
                          carrier=rng.choice(["PostNord", "Bring", "DHL Express", "Budbee"], p=[0.4, 0.25, 0.2, 0.15]),
                          shipping_cost=f"{rng.choice([4.9, 6.9, 9.9, 14.9]):.2f}",
                          delivery_status="Delivered" if delivered else ("In Transit" if ship <= END else "Pending")))
    for iid, p, q, u, di in o["items"]:
        rp = 0.12 if PROFILE[p] in ("winter", "summer") and p >= "P011" else 0.05
        if o["channel"] == "Online":
            rp *= 1.6
        rdate = o["ts"].date() + dt.timedelta(days=int(rng.integers(3, 30)))
        if rng.random() < rp and rdate <= END:
            rq = int(rng.integers(1, q + 1))
            amt = round((q * u - di) / q * rq, 2)
            rid = f"RET-{len(rets) + 1:05d}"
            rets.append(dict(return_id=rid, order_item_id=iid, return_date=d(rdate), return_qty=rq,
                             refund_amount=f"{amt:.2f}",
                             return_reason=rng.choice(["Wrong size", "Damaged on arrival", "Changed mind",
                                                       "Not as described", "Defective"],
                                                      p=[0.3, 0.15, 0.3, 0.12, 0.13] if p >= "P011"
                                                      else [0.0, 0.3, 0.35, 0.15, 0.2])))
            refs.append(dict(refund_id=f"REF-{len(refs) + 1:05d}", return_id=rid, payment_id=pid_,
                             refund_ts=ts(dt.datetime.combine(rdate + dt.timedelta(days=2), dt.time(9, 0))),
                             amount=f"{amt:.2f}", refund_status="Processed"))
payments = dup_rows(pd.DataFrame(pays), 5)
shipments = pd.DataFrame(ships)
returns = pd.DataFrame(rets)
refunds = pd.DataFrame(refs)

# ------------------------------------------------------------------ WMS inventory (last 90 days)
inv_days = [END - dt.timedelta(days=k) for k in range(INV_DAYS - 1, -1, -1)]
locations = STORE_IDS + ["WH01"]
snaps, moves = [], []
for loc in locations:
    for pid in PIDS:
        big = loc == "WH01"
        rop = (12 if PRICE[pid] > 300 else 25) * (4 if big else 1)
        on = int(rop * rng.uniform(1.2, 3.0))
        for k, x in enumerate(inv_days):
            sold = int(rng.poisson(rop * 0.09 * product_weight(pid, x) + 0.05))
            sold = min(sold, on)
            on -= sold
            if sold:
                moves.append((x, pid, loc, "Sale", -sold))
            if on <= rop * 0.4 and rng.random() < 0.35:
                rec = int(rop * rng.uniform(1.5, 2.5))
                on += rec
                moves.append((x, pid, loc, "Receipt", rec))
            if rng.random() < 0.01:
                adj = -int(rng.integers(1, 3))
                adj = max(adj, -on)
                on += adj
                if adj:
                    moves.append((x, pid, loc, "Adjustment", adj))
            reserved = int(rng.integers(0, max(1, min(on, 4) + 1))) if on > 0 else 0
            snaps.append(dict(snapshot_date=d(x), product_id=pid, location_id=loc, on_hand_qty=on,
                              reserved_qty=reserved, reorder_point=rop))
inventory_snapshots = pd.DataFrame(snaps)
inventory_movements = pd.DataFrame(
    [(f"MV-{k + 1:06d}", ts(dt.datetime.combine(x, dt.time(18, 0))), p, l, t, q) for k, (x, p, l, t, q) in enumerate(moves)],
    columns=["movement_id", "movement_ts", "product_id", "location_id", "movement_type", "quantity"])

# ------------------------------------------------------------------ ERP purchase orders
pos = []
sup_of = dict(zip(products.product_id, products.supplier_id))
lead = dict(zip(suppliers.supplier_id, suppliers.lead_time_days))
for pid in PIDS:
    x = max(START, LAUNCH[pid])
    while x <= END:
        exp = x + dt.timedelta(days=lead[sup_of[pid]])
        rec = exp + dt.timedelta(days=int(rng.integers(-3, 10)))
        q = int((40 if PRICE[pid] > 300 else 120) * rng.uniform(0.7, 1.4))
        pos.append(dict(po_id=f"PO-{len(pos) + 1:05d}", supplier_id=sup_of[pid], product_id=pid, order_date=d(x),
                        expected_date=d(exp), received_date=d(rec) if rec <= END else "",
                        qty_ordered=q, qty_received=(q - int(rng.integers(0, 4))) if rec <= END else 0,
                        unit_cost=f"{COST[pid]:.2f}"))
        x += dt.timedelta(days=int(rng.integers(35, 60)))
purchase_orders = pd.DataFrame(pos)

# ------------------------------------------------------------------ Finance GL (monthly, all stores incl. online)
cost_centres, gl, bud = [], [], []
for s in stores.store_id:
    cost_centres.append((f"CC-{s}-OPS", f"{s} Store Operations", s, "Operations"))
    cost_centres.append((f"CC-{s}-MKT", f"{s} Local Marketing", s, "Marketing"))
cost_centres = pd.DataFrame(cost_centres, columns=["cost_centre", "cost_centre_name", "store_id", "department"])
months = pd.date_range(START, END, freq="MS")
SEASON_M = {1: 0.75, 2: 0.7, 3: 0.85, 4: 0.9, 5: 0.95, 6: 1.1, 7: 1.15, 8: 0.95, 9: 0.9, 10: 1.0, 11: 1.45, 12: 1.75}
for s in stores.store_id:
    base = rng.uniform(140000, 260000) if s != "ON01" else 420000
    for m in months:
        m_end = (m + pd.offsets.MonthEnd(0)).date()
        growth = 1 + 0.06 * (m.year - 2024)
        rev = base * SEASON_M[m.month] * growth * rng.uniform(0.92, 1.08)
        cogs = rev * rng.uniform(0.52, 0.58)
        lines = [("4000", "Revenue", f"CC-{s}-OPS", rev), ("5000", "COGS", f"CC-{s}-OPS", cogs),
                 ("6100", "Operating Expense", f"CC-{s}-OPS", rev * rng.uniform(0.14, 0.17)),
                 ("6200", "Operating Expense", f"CC-{s}-OPS", base * (0.05 if s == "ON01" else 0.11)),
                 ("6300", "Operating Expense", f"CC-{s}-MKT", rev * rng.uniform(0.03, 0.06)),
                 ("6400", "Operating Expense", f"CC-{s}-OPS", base * 0.02 * rng.uniform(0.9, 1.3))]
        for acc, at, cc, amt in lines:
            gl.append(dict(entry_id=f"GL-{len(gl) + 1:06d}", posting_date=d(m_end), account_code=acc,
                           account_type=at, cost_centre=cc, store_id=s, amount=f"{amt:.2f}"))
        brev = base * SEASON_M[m.month] * growth * 1.03
        for at, amt in (("Revenue", brev), ("COGS", brev * 0.55), ("Operating Expense", brev * 0.21 + base * 0.12)):
            bud.append(dict(month=d(m.date()), store_id=s, account_type=at, budget_amount=f"{amt:.2f}"))
gl_entries = pd.DataFrame(gl)
budgets = pd.DataFrame(bud)

# ------------------------------------------------------------------ write
products_out = dup_rows(products, 2)
for name, df in [
    ("customers", customers), ("customer_addresses", customer_addresses), ("loyalty_members", loyalty_members),
    ("web_sessions", web_sessions), ("cart_events", cart_events), ("online_orders", online_orders),
    ("online_order_items", online_order_items), ("store_orders", store_orders), ("store_order_items", store_order_items),
    ("products", products_out), ("product_categories", product_categories), ("suppliers", suppliers),
    ("purchase_orders", purchase_orders), ("inventory_snapshots", inventory_snapshots),
    ("inventory_movements", inventory_movements), ("shipments", shipments), ("payments", payments),
    ("refunds", refunds), ("returns", returns), ("promotions", promotions), ("campaigns", campaigns),
    ("gl_entries", gl_entries), ("budgets", budgets), ("cost_centres", cost_centres), ("stores", stores),
    ("channels", channels), ("country_region", country_region),
]:
    write(name, df)
print(f"valid order lines generated: {valid_lines}")
