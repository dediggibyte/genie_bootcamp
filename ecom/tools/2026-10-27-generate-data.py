#!/usr/bin/env python3
"""Generate the source data of the ecom bootcamp (Nordvik Group, three domains).

Writes, deterministically (same script -> same bytes):

  ecom/data/<domain>/<DATE>-<table>.csv   source files, every file below 50 rows
  ecom/data/<DATE>-manifest.json          per file: rows, clean rows, primary key, columns, data-quality issues
  ecom/data/<DATE>-expected-answers.json  the numbers the Genie benchmarks, dashboards and README quote

The clean data is built first; the expected answers are computed from it. The CSV files then get a few
deliberate data-quality problems (extra whitespace, wrong case, a second date format, a duplicate row, a row
without a key) that the silver layer of the pipeline repairs exactly, so silver = the clean data.

All records are synthetic. Brand and model names are used only to describe products; every store, dealer,
customer, order, sale, subscription and invoice is fictional.

Usage (from the repo root, standard library only):

  python3 -I ecom/tools/2026-10-27-generate-data.py           # write the files
  python3 -I ecom/tools/2026-10-27-generate-data.py --check   # exit 1 if a file is missing or stale
"""
import csv
import io
import json
import os
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATE = "2026-10-27"                      # file-name prefix (organisation naming rule)
DATA = "ecom/data"
SCRIPT = "ecom/tools/%s-generate-data.py" % DATE
MAX_ROWS = 49                            # every source file stays below 50 rows
SEED = 20261027


def money(x) -> str:
    return str(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def r2(x) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def month_start(d: date) -> date:
    return d.replace(day=1)


# Fictional people. Phone numbers come from the Swedish range reserved for fiction (070-174 06 05 ... 99).
FIRST = ["Anna", "Erik", "Sara", "Johan", "Emma", "Lars", "Maja", "Oskar", "Elin", "Viktor", "Ida", "Nils",
         "Klara", "Axel", "Linnea", "Hugo", "Wilma", "Isak", "Alva", "Leo", "Freja", "Elias", "Tove", "Adam",
         "Saga", "Filip", "Ebba", "Theo", "Nora", "Gustav", "Agnes", "Melvin", "Selma", "Albin", "Stella", "Jonas"]
LAST = ["Lindqvist", "Berg", "Holm", "Sjöberg", "Ek", "Nyström", "Ahlgren", "Forsberg", "Wallin", "Engström",
        "Lund", "Dahl", "Hedlund", "Strand", "Blom", "Sandberg", "Åberg", "Norén", "Falk", "Lindgren",
        "Björk", "Sundberg", "Hägg", "Ström", "Vik", "Nordin", "Öberg", "Hammar", "Lilja", "Moberg",
        "Rask", "Sköld", "Ljung", "Kvist", "Borg", "Fors"]
CITIES = ["Stockholm", "Göteborg", "Malmö", "Uppsala", "Västerås", "Örebro", "Linköping", "Umeå"]


def ascii_mail(text: str) -> str:
    return (text.lower().replace("å", "a").replace("ä", "a").replace("ö", "o").replace(" ", "."))


def phone(i: int) -> str:
    n = 605 + i
    return "+46 70 174 %02d %02d" % (n // 100 + 6 if n >= 700 else 6, n % 100) if False else "+46 70 174 06 %02d" % (5 + i) if 5 + i < 100 else "+46 70 174 06 99"


def person(i: int):
    first, last = FIRST[i % len(FIRST)], LAST[(i * 7) % len(LAST)]
    return first, last, "%s.%s@example.com" % (ascii_mail(first), ascii_mail(last))


def days(rng, start: date, end: date) -> date:
    return start + timedelta(days=rng.randrange((end - start).days + 1))


H1_START, H1_END = date(2026, 1, 1), date(2026, 6, 30)

# =============================================================================================================
# Retail and Commerce - Nordvik Retail (stores + webshop)
# =============================================================================================================

BRANDS = [  # brand_id, brand_name, category, country_of_origin
    ("B01", "Apple", "electronics", "US"), ("B02", "Samsung", "electronics", "KR"), ("B03", "Google", "electronics", "US"),
    ("B04", "H&M", "fashion", "SE"), ("B05", "Åhléns", "fashion", "SE"), ("B06", "Yves Saint Laurent", "beauty", "FR"),
    ("B07", "Jean Paul Gaultier", "beauty", "FR"), ("B08", "Dior", "beauty", "FR"), ("B09", "Chanel", "beauty", "FR"),
]
PRODUCTS = [  # product_id, product_name, brand_id, subcategory, list_price_sek, unit_cost_sek
    ("P001", "iPhone 16 128 GB", "B01", "phone", 11990, 8900), ("P002", "iPhone 16 Pro 256 GB", "B01", "phone", 15990, 11900),
    ("P003", "MacBook Air 13 M3", "B01", "laptop", 14990, 11200), ("P004", "iPad Air 11", "B01", "tablet", 8990, 6600),
    ("P005", "Galaxy S25 128 GB", "B02", "phone", 11490, 8300), ("P006", "Galaxy S25 Ultra 256 GB", "B02", "phone", 16490, 12100),
    ("P007", "Galaxy Tab S10", "B02", "tablet", 10990, 7900), ("P008", "Galaxy Book4", "B02", "laptop", 12990, 9700),
    ("P009", "Pixel 9 128 GB", "B03", "phone", 9990, 7200), ("P010", "Pixel 9 Pro 256 GB", "B03", "phone", 12490, 9100),
    ("P011", "Pixel Tablet", "B03", "tablet", 6490, 4600),
    ("P012", "Slim Jeans", "B04", "jeans", 399, 150), ("P013", "Loose Fit Jeans", "B04", "jeans", 449, 170),
    ("P014", "Denim Jacket", "B04", "jacket", 599, 230), ("P015", "Puffer Jacket", "B04", "jacket", 899, 360),
    ("P016", "Hoodie Sweatshirt", "B04", "sweatshirt", 299, 110), ("P017", "Crew-neck Sweatshirt", "B04", "sweatshirt", 249, 90),
    ("P018", "Wool Blend Blazer", "B05", "office_wear", 1499, 620), ("P019", "Tailored Trousers", "B05", "office_wear", 899, 360),
    ("P020", "Cotton Office Shirt", "B05", "office_wear", 599, 220), ("P021", "Knitted Cardigan", "B05", "office_wear", 799, 310),
    ("P022", "Libre Eau de Parfum 50 ml", "B06", "perfume", 1395, 560), ("P023", "Black Opium Eau de Parfum 50 ml", "B06", "perfume", 1295, 520),
    ("P024", "Le Male Eau de Toilette 125 ml", "B07", "perfume", 1095, 430), ("P025", "Scandal Eau de Parfum 50 ml", "B07", "perfume", 1150, 460),
    ("P026", "Sauvage Eau de Toilette 100 ml", "B08", "perfume", 1450, 580), ("P027", "J'adore Eau de Parfum 50 ml", "B08", "perfume", 1395, 560),
    ("P028", "N°5 Eau de Parfum 50 ml", "B09", "perfume", 1750, 720), ("P029", "Bleu de Chanel Eau de Parfum 100 ml", "B09", "perfume", 1850, 760),
]
STORES = [  # store_id, store_name, city, region_code, channel, opened_date
    ("S01", "Nordvik Retail Stockholm City", "Stockholm", "STO", "store", "2015-03-01"),
    ("S02", "Nordvik Retail Kista", "Stockholm", "STO", "store", "2018-09-15"),
    ("S03", "Nordvik Retail Göteborg Nordstan", "Göteborg", "GOT", "store", "2016-04-01"),
    ("S04", "Nordvik Retail Göteborg Frölunda", "Göteborg", "GOT", "store", "2021-11-01"),
    ("S05", "Nordvik Retail Malmö Triangeln", "Malmö", "MAL", "store", "2017-05-20"),
    ("S06", "Nordvik Webshop", "Stockholm", "ONLINE", "online", "2019-01-10"),
]


def build_retail(rng):
    brand_of = {b[0]: b for b in BRANDS}
    brands = [{"brand_id": b[0], "brand_name": b[1], "category": b[2], "country_of_origin": b[3]} for b in BRANDS]
    products = [{"product_id": p[0], "sku": "NR-%s" % p[0][1:], "product_name": p[1], "brand_id": p[2],
                 "category": brand_of[p[2]][2], "subcategory": p[3], "list_price_sek": money(p[4]),
                 "unit_cost_sek": money(p[5]), "launch_date": str(date(2024, 1, 15) + timedelta(days=22 * i))}
                for i, p in enumerate(PRODUCTS)]
    stores = [dict(zip(("store_id", "store_name", "city", "region_code", "channel", "opened_date"), s)) for s in STORES]
    tiers = ["none", "none", "silver", "gold"]
    customers = []
    for i in range(36):
        first, last, mail = person(i)
        customers.append({"customer_id": "C%03d" % (i + 1), "first_name": first, "last_name": last, "email": mail,
                          "phone": "+46 70 174 06 %02d" % (5 + i), "city": CITIES[i % len(CITIES)],
                          "loyalty_tier": tiers[(i * 3) % 4], "signup_date": str(date(2023, 1, 9) + timedelta(days=29 * i))})
    store_w = ["S01"] * 3 + ["S02"] * 2 + ["S03"] * 2 + ["S04"] + ["S05"] * 2 + ["S06"] * 4
    orders, lines = [], []
    price = {p["product_id"]: Decimal(p["list_price_sek"]) for p in products}
    for i in range(40):
        oid = "O%04d" % (i + 1)
        status = "cancelled" if i in (7, 21, 33) else "completed"
        store = store_w[rng.randrange(len(store_w))]
        pay = rng.choice(["card", "card", "swish", "klarna", "invoice"]) if store == "S06" else rng.choice(["card", "card", "swish"])
        orders.append({"order_id": oid, "order_date": str(days(rng, H1_START, H1_END)),
                       "customer_id": "C%03d" % (rng.randrange(36) + 1), "store_id": store,
                       "payment_method": pay, "order_status": status})
        for _ in range(2 if i % 5 == 0 else 1):
            pid = PRODUCTS[rng.randrange(len(PRODUCTS))][0]
            qty = rng.choice([1, 1, 2]) if price[pid] < 1000 else 1
            disc = (price[pid] * qty * Decimal("0.10")) if rng.random() < 0.25 else Decimal(0)
            lines.append({"order_line_id": "L%04d" % (len(lines) + 1), "order_id": oid, "product_id": pid,
                          "quantity": str(qty), "unit_price_sek": money(price[pid]), "discount_sek": money(disc)})
    completed = {o["order_id"] for o in orders if o["order_status"] == "completed"}
    reasons = ["wrong_size", "changed_mind", "defect", "damaged"]
    returns = []
    for ln in [x for x in lines if x["order_id"] in completed][2::4][:10]:
        o = next(o for o in orders if o["order_id"] == ln["order_id"])
        qty = int(ln["quantity"])
        refund = Decimal(ln["unit_price_sek"]) * qty - Decimal(ln["discount_sek"])
        returns.append({"return_id": "R%03d" % (len(returns) + 1), "order_line_id": ln["order_line_id"],
                        "return_date": str(date.fromisoformat(o["order_date"]) + timedelta(days=rng.randrange(3, 20))),
                        "quantity": str(qty), "reason": reasons[len(returns) % 4], "refund_sek": money(refund)})
    return {"brands": brands, "products": products, "stores": stores, "customers": customers,
            "orders": orders, "order_lines": lines, "returns": returns}


def retail_answers(t):
    prod = {p["product_id"]: p for p in t["products"]}
    brand = {b["brand_id"]: b["brand_name"] for b in t["brands"]}
    store = {s["store_id"]: s for s in t["stores"]}
    orders = {o["order_id"]: o for o in t["orders"]}
    sales = []
    for ln in t["order_lines"]:
        o = orders[ln["order_id"]]
        if o["order_status"] != "completed":
            continue
        q, p, d = int(ln["quantity"]), Decimal(ln["unit_price_sek"]), Decimal(ln["discount_sek"])
        net = p * q - d
        sales.append({"line": ln["order_line_id"], "order": o["order_id"], "month": o["order_date"][:7],
                      "region": store[o["store_id"]]["region_code"], "channel": store[o["store_id"]]["channel"],
                      "category": prod[ln["product_id"]]["category"], "brand": brand[prod[ln["product_id"]]["brand_id"]],
                      "units": q, "net": net, "cost": Decimal(prod[ln["product_id"]]["unit_cost_sek"]) * q})
    ret_units = sum(int(r["quantity"]) for r in t["returns"])

    def agg(rows):
        net = sum(r["net"] for r in rows)
        n_orders = len({r["order"] for r in rows})
        return {"net_revenue_sek": r2(net), "units_sold": sum(r["units"] for r in rows), "orders": n_orders,
                "average_order_value_sek": r2(net / n_orders) if n_orders else None,
                "gross_margin_pct": r2((net - sum(r["cost"] for r in rows)) / net * 100) if net else None}

    by = lambda key: {k: agg([r for r in sales if r[key] == k]) for k in sorted({r[key] for r in sales})}
    total = agg(sales)
    total["return_rate_pct"] = r2(Decimal(ret_units) / total["units_sold"] * 100)
    total["refund_amount_sek"] = r2(sum(Decimal(r["refund_sek"]) for r in t["returns"]))
    total["returns"] = len(t["returns"])
    rev_by_brand = {b: v["net_revenue_sek"] for b, v in by("brand").items()}
    return {"period": "2026-01-01 to 2026-06-30, completed orders only, SEK",
            "total": total, "by_category": by("category"), "by_region": by("region"), "by_month": by("month"),
            "by_channel": by("channel"), "top_brand_by_revenue": max(rev_by_brand, key=rev_by_brand.get),
            "fact_sales_rows": len(sales), "fact_sales_rows_by_region": {k: v for k, v in
                                                                         sorted(defaultdict_count(sales, "region").items())},
            "cancelled_orders": sum(1 for o in t["orders"] if o["order_status"] == "cancelled")}


def defaultdict_count(rows, key):
    out = defaultdict(int)
    for r in rows:
        out[r[key]] += 1
    return dict(out)


# =============================================================================================================
# Mobility and Automotive - Nordvik Mobility (dealers + workshops)
# =============================================================================================================

MODELS = [  # model_id, brand, model_name, vehicle_type, body_type, powertrain, list_price_sek
    ("M01", "Volvo", "XC60 Plug-in Hybrid", "car", "suv", "hybrid", 689000), ("M02", "Volvo", "EX30", "car", "suv", "ev", 449000),
    ("M03", "Volvo", "EX90", "car", "suv", "ev", 1095000), ("M04", "Tesla", "Model Y", "car", "suv", "ev", 499990),
    ("M05", "Tesla", "Model 3", "car", "sedan", "ev", 449990), ("M06", "Volkswagen", "ID.4", "car", "suv", "ev", 489900),
    ("M07", "Volkswagen", "Golf", "car", "hatchback", "petrol", 329900), ("M08", "Toyota", "RAV4 Hybrid", "car", "suv", "hybrid", 469900),
    ("M09", "Toyota", "Corolla Hybrid", "car", "hatchback", "hybrid", 309900), ("M10", "BMW", "i4", "car", "sedan", "ev", 619000),
    ("M11", "Kia", "EV6", "car", "suv", "ev", 529900), ("M12", "Volkswagen", "ID. Buzz Cargo", "van", "van", "ev", 549000),
    ("M13", "Ford", "Transit Custom", "van", "van", "diesel", 399000), ("M14", "Scania", "R 450", "truck", "tractor_unit", "diesel", 1650000),
    ("M15", "Volvo", "FH Electric", "truck", "tractor_unit", "ev", 3450000), ("M16", "Mercedes-Benz", "eActros 600", "truck", "tractor_unit", "ev", 3690000),
]
DEALERS = [  # dealer_id, dealer_name, city, region_code, has_workshop
    ("D01", "Nordvik Mobility Stockholm Bromma", "Stockholm", "STO", "true"),
    ("D02", "Nordvik Mobility Täby", "Stockholm", "STO", "true"),
    ("D03", "Nordvik Mobility Göteborg Hisingen", "Göteborg", "GOT", "true"),
    ("D04", "Nordvik Mobility Malmö Bulltofta", "Malmö", "MAL", "true"),
    ("D05", "Nordvik Mobility Umeå", "Umeå", "UME", "false"),
    ("D06", "Nordvik Truck Center Södertälje", "Södertälje", "STO", "true"),
]
FLEETS = ["Lindqvist Bygg AB", "Norrsken Logistik AB", "Kustfrakt AB", "Granit Transport AB", "Solberga El AB",
          "Fjällgård Leveranser AB"]


def build_mobility(rng):
    models = [dict(zip(("model_id", "brand", "model_name", "vehicle_type", "body_type", "powertrain"), m[:6]),
                   model_year="2026", list_price_sek=money(m[6])) for m in MODELS]
    dealers = [dict(zip(("dealer_id", "dealer_name", "city", "region_code", "has_workshop"), d)) for d in DEALERS]
    customers = []
    for i in range(30):
        if i < len(FLEETS):
            name, ctype = FLEETS[i], "fleet"
            mail = "fleet@%s.example.com" % ascii_mail(name.split()[0])
        else:
            first, last, mail = person(i + 3)
            name, ctype = "%s %s" % (first, last), "private"
        customers.append({"customer_id": "K%03d" % (i + 1), "customer_type": ctype, "customer_name": name,
                          "email": mail, "phone": "+46 70 174 06 %02d" % (40 + i), "city": CITIES[(i * 3) % len(CITIES)]})
    fleet_ids = [c["customer_id"] for c in customers if c["customer_type"] == "fleet"]
    private_ids = [c["customer_id"] for c in customers if c["customer_type"] == "private"]
    model = {m["model_id"]: m for m in models}
    car_models = [m["model_id"] for m in models if m["vehicle_type"] == "car"]
    work_models = [m["model_id"] for m in models if m["vehicle_type"] != "car"]
    sales, vehicles, sold_on = [], [], {}
    for i in range(38):
        is_work = i % 4 == 0
        mid = rng.choice(work_models if is_work else car_models)
        truck = model[mid]["vehicle_type"] == "truck"
        dealer = "D06" if truck else rng.choice(["D01", "D01", "D02", "D03", "D03", "D04", "D05"])
        cust = rng.choice(fleet_ids if is_work else (private_ids + fleet_ids[:2]))
        lp = Decimal(model[mid]["list_price_sek"])
        disc = (lp * Decimal(rng.choice(["0", "0.02", "0.04", "0.06"]))).quantize(Decimal("1"))
        vin = "NVK%s%011d" % (mid[1:], 70000000 + i * 7919)
        vehicles.append((vin, mid, cust))
        sold_on[vin] = days(rng, H1_START, H1_END)
        sales.append({"sale_id": "VS%03d" % (i + 1), "sale_date": str(sold_on[vin]), "dealer_id": dealer,
                      "customer_id": cust, "model_id": mid, "vin": vin, "sale_price_sek": money(lp),
                      "discount_sek": money(disc), "financing": rng.choice(["cash", "loan", "lease", "lease"])})
    # vehicles already on the road (bought earlier, serviced now)
    for i in range(14):
        mid = rng.choice(car_models + work_models[:2])
        vehicles.append(("NVK%s%011d" % (mid[1:], 50000000 + i * 6271), mid, rng.choice(private_ids + fleet_ids)))
    svc_types = [("annual_service", 3.0), ("tyre_change", 1.0), ("brake_service", 2.5), ("battery_check", 1.5),
                 ("software_update", 0.5), ("warranty_repair", 4.0)]
    visits = []
    for i in range(44):
        vin, mid, cust = vehicles[rng.randrange(len(vehicles))]
        truck = model[mid]["vehicle_type"] == "truck"
        stype, hours = svc_types[rng.randrange(len(svc_types))]
        if model[mid]["powertrain"] == "ev" and stype == "annual_service":
            stype, hours = "battery_check", 1.5
        hours = hours * (2 if truck else 1)
        rate = Decimal(1450 if truck else 1150)
        parts = Decimal(rng.choice([0, 450, 900, 1800, 3200])) * (3 if truck else 1)
        warranty = stype == "warranty_repair"
        labour = rate * Decimal(str(hours))
        visit_date = days(rng, H1_START, H1_END)
        dealer = "D06" if truck else rng.choice(["D01", "D02", "D03", "D04"])
        mileage = rng.randrange(8, 160) * 1000 * (4 if truck else 1)
        if vin in sold_on:  # sold this half-year: the visit comes after the sale, at low mileage
            sold = sold_on[vin]
            visit_date = sold + timedelta(days=(visit_date - H1_START).days * (H1_END - sold).days // (H1_END - H1_START).days)
            mileage = max(1000, mileage // 10000 * 1000)
        visits.append({"visit_id": "SV%03d" % (i + 1), "visit_date": str(visit_date), "dealer_id": dealer,
                       "customer_id": cust, "model_id": mid, "vin": vin, "service_type": stype,
                       "labour_hours": "%.1f" % hours, "labour_cost_sek": money(labour), "parts_cost_sek": money(parts),
                       "billed_amount_sek": money(0 if warranty else labour + parts),
                       "warranty": "true" if warranty else "false",
                       "mileage_km": str(mileage)})
    return {"vehicle_models": models, "dealers": dealers, "customers": customers, "vehicle_sales": sales,
            "service_visits": visits}


def mobility_answers(t):
    model = {m["model_id"]: m for m in t["vehicle_models"]}
    dealer = {d["dealer_id"]: d for d in t["dealers"]}
    s = [{"month": x["sale_date"][:7], "region": dealer[x["dealer_id"]]["region_code"],
          "brand": model[x["model_id"]]["brand"], "model": "%s %s" % (model[x["model_id"]]["brand"], model[x["model_id"]]["model_name"]),
          "vtype": model[x["model_id"]]["vehicle_type"], "ev": model[x["model_id"]]["powertrain"] == "ev",
          "rev": Decimal(x["sale_price_sek"]) - Decimal(x["discount_sek"])} for x in t["vehicle_sales"]]
    v = [{"month": x["visit_date"][:7], "region": dealer[x["dealer_id"]]["region_code"], "type": x["service_type"],
          "rev": Decimal(x["billed_amount_sek"]), "hours": Decimal(x["labour_hours"]), "warranty": x["warranty"] == "true"}
         for x in t["service_visits"]]

    def sagg(rows):
        n = len(rows)
        rev = sum(r["rev"] for r in rows)
        return {"units_sold": n, "vehicle_revenue_sek": r2(rev), "average_sale_price_sek": r2(rev / n) if n else None,
                "ev_share_pct": r2(Decimal(sum(r["ev"] for r in rows)) / n * 100) if n else None}

    def vagg(rows):
        n = len(rows)
        return {"service_visits": n, "service_revenue_sek": r2(sum(r["rev"] for r in rows)),
                "labour_hours": float(sum(r["hours"] for r in rows)),
                "warranty_share_pct": r2(Decimal(sum(r["warranty"] for r in rows)) / n * 100) if n else None}

    units_by_model = defaultdict_count(s, "model")
    return {"period": "2026-01-01 to 2026-06-30, SEK (sales: price after discount; service: amount billed to the customer)",
            "sales_total": sagg(s), "sales_by_vehicle_type": {k: sagg([r for r in s if r["vtype"] == k]) for k in sorted({r["vtype"] for r in s})},
            "sales_by_region": {k: sagg([r for r in s if r["region"] == k]) for k in sorted({r["region"] for r in s})},
            "sales_by_month": {k: sagg([r for r in s if r["month"] == k]) for k in sorted({r["month"] for r in s})},
            "top_model_by_units": max(sorted(units_by_model), key=units_by_model.get),
            "service_total": vagg(v),
            "service_by_type": {k: vagg([r for r in v if r["type"] == k]) for k in sorted({r["type"] for r in v})},
            "service_by_region": {k: vagg([r for r in v if r["region"] == k]) for k in sorted({r["region"] for r in v})},
            "fact_vehicle_sales_rows_by_region": dict(sorted(defaultdict_count(s, "region").items())),
            "fact_service_visits_rows_by_region": dict(sorted(defaultdict_count(v, "region").items()))}


# =============================================================================================================
# Telecommunications and Media - Nordvik Connect (operator)
# =============================================================================================================

PLANS = [  # plan_id, plan_name, plan_type, segment, monthly_fee_sek, data_allowance_gb ('' = unlimited), included_streaming
    ("T01", "Mobil 5G Unlimited", "mobile", "consumer", 449, "", ""),
    ("T02", "Mobil 20 GB", "mobile", "consumer", 299, "20", ""),
    ("T03", "Mobil 5 GB", "mobile", "consumer", 199, "5", ""),
    ("T04", "Fiber 250/250", "broadband", "consumer", 399, "", ""),
    ("T05", "Fiber 1000/1000", "broadband", "consumer", 549, "", ""),
    ("T06", "TV Bas with Netflix Standard", "tv_streaming", "consumer", 349, "", "Netflix Standard"),
    ("T07", "Streaming Duo: Netflix and Spotify Premium", "tv_streaming", "consumer", 399, "", "Netflix Standard; Spotify Premium"),
    ("T08", "Family Bundle 5G + Fiber + Disney+", "bundle", "consumer", 999, "", "Disney+ Standard"),
    ("T09", "Max and Spotify add-on", "tv_streaming", "consumer", 229, "", "Max; Spotify Premium"),
    ("T10", "Företag Mobil 5G Unlimited", "mobile", "business", 399, "", ""),
    ("T11", "Företag Mobil 50 GB", "mobile", "business", 299, "50", ""),
    ("T12", "Företag Fiber 1000/1000", "broadband", "business", 799, "", ""),
]
COMPANIES = ["Bergslagen Konsult AB", "Havsbris Design AB", "Mälardalens Redovisning AB", "Polaris Event AB",
             "Skärgårdens Bageri AB", "Tallskogen IT AB"]


def build_telecom(rng):
    plans = [dict(zip(("plan_id", "plan_name", "plan_type", "segment"), p[:4]), monthly_fee_sek=money(p[4]),
                  data_allowance_gb=p[5], included_streaming=p[6]) for p in PLANS]
    customers = []
    for i in range(20):
        if i < len(COMPANIES):
            name, seg = COMPANIES[i], "business"
            mail = "it@%s.example.com" % ascii_mail(COMPANIES[i].split()[0])
        else:
            first, last, mail = person(i + 11)
            name, seg = "%s %s" % (first, last), "consumer"
        customers.append({"customer_id": "N%03d" % (i + 1), "customer_segment": seg, "customer_name": name,
                          "email": mail, "phone": "+46 70 174 06 %02d" % (75 + i), "city": CITIES[(i * 5) % len(CITIES)],
                          "signup_date": str(date(2022, 2, 1) + timedelta(days=41 * i))})
    plan = {p["plan_id"]: p for p in plans}
    consumer_plans = [p["plan_id"] for p in plans if p["segment"] == "consumer"]
    business_plans = [p["plan_id"] for p in plans if p["segment"] == "business"]
    subs = []
    for i in range(24):
        c = customers[i % 20] if i < 20 else customers[6 + (i - 20) * 3]
        pid = rng.choice(business_plans if c["customer_segment"] == "business" else consumer_plans)
        cancelled = i in (9, 17)
        subs.append({"subscription_id": "SUB%03d" % (i + 1), "customer_id": c["customer_id"], "plan_id": pid,
                     "start_date": str(date(2024, 3, 1) + timedelta(days=23 * i)),
                     "end_date": "2026-05-31" if cancelled else "", "status": "cancelled" if cancelled else "active",
                     "sales_channel": rng.choice(["online", "online", "store", "telesales"])})
    seg_of = {c["customer_id"]: c["customer_segment"] for c in customers}
    invoices, usage = [], []
    for month in (date(2026, 5, 1), date(2026, 6, 1)):
        for s in subs:
            if s["end_date"] and date.fromisoformat(s["end_date"]) < month:
                continue
            fee = Decimal(plan[s["plan_id"]]["monthly_fee_sek"])
            extra = Decimal(rng.choice([0, 0, 0, 49, 99])) if plan[s["plan_id"]]["plan_type"] == "mobile" else Decimal(0)
            amount = fee + extra
            inv_date = month + timedelta(days=27 if month.month == 5 else 29)
            due = inv_date + timedelta(days=30)
            if month.month == 5:
                status = rng.choice(["paid"] * 8 + ["overdue"] * 2)
            else:
                status = rng.choice(["paid"] * 5 + ["open"] * 2)
            invoices.append({"invoice_id": "INV%04d" % (len(invoices) + 1), "subscription_id": s["subscription_id"],
                             "billing_month": str(month), "invoice_date": str(inv_date), "due_date": str(due),
                             "amount_excl_vat_sek": money(amount), "vat_sek": money(amount * Decimal("0.25")),
                             "payment_status": status})
            ptype = plan[s["plan_id"]]["plan_type"]
            data_gb = {"mobile": rng.uniform(3, 45), "bundle": rng.uniform(150, 400), "broadband": rng.uniform(250, 900),
                       "tv_streaming": rng.uniform(40, 120)}[ptype]
            usage.append({"usage_id": "U%04d" % (len(usage) + 1), "subscription_id": s["subscription_id"],
                          "usage_month": str(month), "data_gb": "%.1f" % data_gb,
                          "voice_minutes": str(rng.randrange(60, 900)) if ptype in ("mobile", "bundle") else "0",
                          "sms_count": str(rng.randrange(5, 120)) if ptype in ("mobile", "bundle") else "0",
                          "streaming_hours": "%.1f" % (rng.uniform(20, 90) if ptype in ("tv_streaming", "bundle") else rng.uniform(0, 6))})
    return {"plans": plans, "customers": customers, "subscriptions": subs, "invoices": invoices, "usage": usage}


def telecom_answers(t):
    plan = {p["plan_id"]: p for p in t["plans"]}
    seg = {c["customer_id"]: c["customer_segment"] for c in t["customers"]}
    sub = {s["subscription_id"]: s for s in t["subscriptions"]}
    inv = [{"month": i["billing_month"][:7], "sub": i["subscription_id"], "seg": seg[sub[i["subscription_id"]]["customer_id"]],
            "ptype": plan[sub[i["subscription_id"]]["plan_id"]]["plan_type"], "amount": Decimal(i["amount_excl_vat_sek"]),
            "status": i["payment_status"]} for i in t["invoices"]]
    use = [{"month": u["usage_month"][:7], "sub": u["subscription_id"], "seg": seg[sub[u["subscription_id"]]["customer_id"]],
            "gb": Decimal(u["data_gb"]), "stream": Decimal(u["streaming_hours"]), "voice": int(u["voice_minutes"])}
           for u in t["usage"]]

    def bagg(rows):
        n_sub = len({r["sub"] for r in rows})
        rev = sum(r["amount"] for r in rows)
        return {"billed_revenue_sek": r2(rev), "invoices": len(rows), "billed_subscriptions": n_sub,
                "arpu_sek": r2(rev / n_sub) if n_sub else None,
                "overdue_amount_sek": r2(sum(r["amount"] for r in rows if r["status"] == "overdue")),
                "paid_share_pct": r2(Decimal(sum(r["status"] == "paid" for r in rows)) / len(rows) * 100) if rows else None}

    def uagg(rows):
        n_sub = len({r["sub"] for r in rows})
        gb = sum(r["gb"] for r in rows)
        return {"data_gb": float(gb), "avg_data_gb_per_subscription": r2(gb / n_sub) if n_sub else None,
                "voice_minutes": sum(r["voice"] for r in rows), "streaming_hours": float(sum(r["stream"] for r in rows)),
                "active_subscriptions": n_sub}

    by = lambda rows, key, f: {k: f([r for r in rows if r[key] == k]) for k in sorted({r[key] for r in rows})}
    return {"period": "billing and usage months 2026-05 and 2026-06, SEK excl. VAT",
            "billing_by_month": by(inv, "month", bagg), "billing_by_segment_june": by([r for r in inv if r["month"] == "2026-06"], "seg", bagg),
            "billing_by_plan_type_june": by([r for r in inv if r["month"] == "2026-06"], "ptype", bagg),
            "usage_by_month": by(use, "month", uagg), "usage_by_segment_june": by([r for r in use if r["month"] == "2026-06"], "seg", uagg),
            "active_subscriptions_now": sum(1 for s in t["subscriptions"] if s["status"] == "active"),
            "fact_billing_rows_by_segment": dict(sorted(defaultdict_count(inv, "seg").items())),
            "fact_usage_rows_by_segment": dict(sorted(defaultdict_count(use, "seg").items()))}


# =============================================================================================================
# data-quality issues (applied to the CSV only; silver repairs them exactly)
# =============================================================================================================

PRIMARY_KEYS = {
    "retail": {"brands": "brand_id", "products": "product_id", "stores": "store_id", "customers": "customer_id",
               "orders": "order_id", "order_lines": "order_line_id", "returns": "return_id"},
    "mobility": {"vehicle_models": "model_id", "dealers": "dealer_id", "customers": "customer_id",
                 "vehicle_sales": "sale_id", "service_visits": "visit_id"},
    "telecom": {"plans": "plan_id", "customers": "customer_id", "subscriptions": "subscription_id",
                "invoices": "invoice_id", "usage": "usage_id"},
}


def dirty(domain, tables):
    """Copy of the clean tables with the documented data-quality issues injected. Returns (tables, issues)."""
    t = {k: [dict(r) for r in v] for k, v in tables.items()}
    issues = defaultdict(list)

    def note(table, issue, n, handling):
        issues[table].append({"issue": issue, "rows": n, "silver_handling": handling})

    if domain == "retail":
        t["stores"][3]["region_code"] = " got"
        note("stores", "region code in lower case with a leading space", 1, "trim + upper case")
        for i in (2, 11):
            t["customers"][i]["loyalty_tier"] = {2: " Gold", 11: "SILVER"}.get(i, t["customers"][i]["loyalty_tier"])
        note("customers", "loyalty tier with whitespace / upper case", 2, "trim + lower case")
        t["customers"].append(dict(t["customers"][5]))
        note("customers", "exact duplicate row", 1, "one row per customer_id")
        for i in (4, 18):
            d = date.fromisoformat(t["orders"][i]["order_date"])
            t["orders"][i]["order_date"] = d.strftime("%d/%m/%Y")
        note("orders", "order date as dd/MM/yyyy", 2, "parse both date formats")
        t["order_lines"].append({"order_line_id": "", "order_id": "O0003", "product_id": "P012", "quantity": "1",
                                 "unit_price_sek": "399.00", "discount_sek": "0.00"})
        note("order_lines", "row without order_line_id (legacy feed)", 1, "expectation drops the row")
    elif domain == "mobility":
        t["dealers"][2]["region_code"] = "got "
        note("dealers", "region code in lower case with a trailing space", 1, "trim + upper case")
        t["customers"].append(dict(t["customers"][8]))
        note("customers", "exact duplicate row", 1, "one row per customer_id")
        t["vehicle_sales"].append(dict(t["vehicle_sales"][0], sale_id=""))
        note("vehicle_sales", "row without sale_id", 1, "expectation drops the row")
        for i in (3, 15, 27):
            t["service_visits"][i]["warranty"] = {"true": "Y", "false": "N"}[t["service_visits"][i]["warranty"]]
        note("service_visits", "warranty flag as Y / N", 3, "map Y/N, true/false to BOOLEAN")
    elif domain == "telecom":
        t["customers"][2]["customer_segment"] = "Business "
        note("customers", "segment with upper case and a trailing space", 1, "trim + lower case")
        t["invoices"].append(dict(t["invoices"][10]))
        note("invoices", "exact duplicate row", 1, "one row per invoice_id")
        for i in (1, 30):
            t["usage"][i]["usage_month"] = date.fromisoformat(t["usage"][i]["usage_month"]).strftime("%d/%m/%Y")
        note("usage", "usage month as dd/MM/yyyy", 2, "parse both date formats")
    return t, dict(issues)


def to_csv(rows) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def build():
    rng = random.Random(SEED)
    clean = {"retail": build_retail(rng), "mobility": build_mobility(rng), "telecom": build_telecom(rng)}
    files, manifest = {}, {"_notice": ("GENERATED FILE - do not edit by hand; regenerate with python3 -I %s. "
                                       "Synthetic data of the fictional Nordvik Group; brand and model names only "
                                       "describe products. rows = rows in the CSV, clean_rows = rows silver keeps."
                                       % SCRIPT)}
    for domain, tables in clean.items():
        written, issues = dirty(domain, tables)
        manifest[domain] = {}
        for name, rows in written.items():
            if len(rows) > MAX_ROWS:
                raise ValueError("%s.%s has %d rows (max %d)" % (domain, name, len(rows), MAX_ROWS))
            rel = "%s/%s/%s-%s.csv" % (DATA, domain, DATE, name)
            files[rel] = to_csv(rows)
            manifest[domain][name] = {"file": rel, "rows": len(rows), "clean_rows": len(tables[name]),
                                      "primary_key": PRIMARY_KEYS[domain][name], "columns": list(rows[0]),
                                      "dq_issues": issues.get(name, [])}
    answers = {"_notice": "GENERATED FILE - computed by %s from the clean data (what silver and gold contain)." % SCRIPT,
               "retail": retail_answers(clean["retail"]), "mobility": mobility_answers(clean["mobility"]),
               "telecom": telecom_answers(clean["telecom"])}
    files["%s/%s-manifest.json" % (DATA, DATE)] = json.dumps(manifest, indent=1, ensure_ascii=False) + "\n"
    files["%s/%s-expected-answers.json" % (DATA, DATE)] = json.dumps(answers, indent=1, ensure_ascii=False) + "\n"
    return files


def main(argv):
    check = "--check" in argv
    files = build()
    stale = []
    for rel, text in sorted(files.items()):
        path = os.path.join(ROOT, rel)
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if old == text:
            continue
        stale.append(rel)
        if not check:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
    print("%s: %d files (%d %s)" % (SCRIPT, len(files), len(stale), "stale" if check else "written"))
    for s in stale if check else []:
        print("  stale: " + s)
    return 1 if check and stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
