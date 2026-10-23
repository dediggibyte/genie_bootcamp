"""Curated product master data: brand, product_category, category and sku.

Three brands (Björkö Pantry, Kallkälla, Mjuk Care), a two-level category hierarchy
(FOOD / BEVERAGE / PERSONAL_CARE with 14 sub-categories) and the ~90 SKUs defined in
``world.SKUS`` with valid GTIN-13 codes, list prices and standard costs.
"""
import datetime
from decimal import Decimal

from . import world

D = Decimal


def _ts(d, h=9):
    return datetime.datetime.combine(d, datetime.time(h, 0))


_BRAND_EXTRA = {
    "BJORKO": {"division": "Foods division", "plm": "mature", "reg": "EU General Food Law (Regulation 178/2002)",
               "gmp": "FSSC22000-LUND-2019", "sust": "multiple", "tm": "EUTM 017820461"},
    "KALLKALLA": {"division": "Beverages division", "plm": "growth", "reg": "EU General Food Law (Regulation 178/2002)",
                  "gmp": "FSSC22000-NKPG-2020", "sust": "iso_14001", "tm": "EUTM 018004377"},
    "MJUKCARE": {"division": "Personal Care division", "plm": "growth", "reg": "EU Cosmetics Regulation 1223/2009",
                 "gmp": "ISO22716-POZN-2021", "sust": "rspo", "tm": "EUTM 018322095"},
}


def generate(reg):
    _brands(reg)
    _product_categories(reg)
    _skus(reg)
    _category(reg)


def _brands(reg):
    fqn = "product.brand"
    pool = reg.alloc(fqn, len(world.BRANDS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    rows = []
    for i, b in enumerate(world.BRANDS):
        ids[b["code"]] = pool[i]
        x = _BRAND_EXTRA[b["code"]]
        created = _ts(b["launch"] - datetime.timedelta(days=120))
        fixed = {
            "brand_id": pool[i], "company_code_id": reg.ctx["company_id"]["SE01"],
            "gl_account_id": reg.ctx["gl"][("SE01", "3000")], "profit_center_id": reg.ctx["pc"][b["code"]],
            "architecture_type": "master_brand", "brand_status": "active", "created_timestamp": created,
            "distribution_channel": "omnichannel", "divestiture_date": None, "ean_prefix": b["ean_prefix"],
            "equity_methodology": "internal_scorecard", "geographic_scope": "regional",
            "gmp_certification_ref": x["gmp"], "is_licensed_brand": False,
            "last_updated_timestamp": _ts(datetime.date(2026, 2, 3 + i), 11),
            "launch_date": b["launch"], "launch_year": b["launch"].year, "license_expiry_date": None,
            "msrp_currency_code": "EUR", "name": b["name"], "nps_tracking_enabled": True,
            "owner_division": x["division"], "plm_stage": x["plm"], "positioning_statement": b["positioning"],
            "primary_category": b["category_name"], "primary_country_code": "SWE",
            "regulatory_classification": x["reg"], "short_name": b["short"], "social_media_handle": b["handle"],
            "source_system_brand_code": "BR" + b["code"][:6], "source_system_code": "SAP_S4",
            "sustainability_certification": x["sust"], "target_consumer_segment": b["segment"],
            "tier": b["tier"], "trade_promotion_eligible": True, "trademark_jurisdiction": "SWE",
            "trademark_registration_ref": x["tm"],
            "website_url": "https://www.%s/%s" % (world.WEBSHOP, b["name"].lower().replace(" ", "-").replace("ä", "a").replace("ö", "o")),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country="SWE"))
    reg.ctx["brand_id"] = ids
    reg.rows[fqn] = rows


def _product_categories(reg):
    fqn = "product.product_category"
    n = len(world.TOP_CATEGORIES) + len(world.SUBCATEGORIES)
    pool = reg.alloc(fqn, n)
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    k = 0
    for code, _, _ in world.TOP_CATEGORIES:
        ids[code] = pool[k]
        k += 1
    for code, _, _, _ in world.SUBCATEGORIES:
        ids[code] = pool[k]
        k += 1
    cat_brand = {"FOOD": "BJORKO", "BEVERAGE": "KALLKALLA", "PERSONAL_CARE": "MJUKCARE"}
    rows = []
    k = 0
    created = _ts(datetime.date(2016, 1, 11))
    for order, (code, name, desc) in enumerate(world.TOP_CATEGORIES):
        fixed = {
            "product_category_id": ids[code], "parent_category_product_category_id": None,
            "parent_product_category_id": None, "profit_center_id": reg.ctx["pc"][cat_brand[code]],
            "business_unit": "regional", "category_code": code, "category_description": desc,
            "category_name": name, "category_status": "active", "classification": code.lower(),
            "classification_type": "category", "created_timestamp": created, "display_order": order + 1,
            "effective_from": created.date(), "effective_until": None, "hierarchy_level": 1,
            "hierarchy_path": "/%d" % ids[code],
            "image_url": "https://www.%s/img/categories/%s.jpg" % (world.WEBSHOP, code.lower()),
            "is_leaf": False, "marketing_tag": name, "product_category_status": "active",
            "source_system_code": "MG%02d" % (order + 1),
        }
        rows.append(gen.row(k, rnd, fixed, anchor=created, country="SWE"))
        k += 1
    for order, (code, name, parent, desc) in enumerate(world.SUBCATEGORIES):
        fixed = {
            "product_category_id": ids[code], "parent_category_product_category_id": ids[parent],
            "parent_product_category_id": ids[parent], "profit_center_id": reg.ctx["pc"][cat_brand[parent]],
            "business_unit": "regional", "category_code": code, "category_description": desc,
            "category_name": name, "category_status": "active", "classification": parent.lower(),
            "classification_type": "sub_category", "created_timestamp": created, "display_order": order + 1,
            "effective_from": created.date(), "effective_until": None, "hierarchy_level": 2,
            "hierarchy_path": "/%d/%d" % (ids[parent], ids[code]),
            "image_url": "https://www.%s/img/categories/%s.jpg" % (world.WEBSHOP, code.lower()),
            "is_leaf": True, "marketing_tag": name, "product_category_status": "active",
            "source_system_code": "MG%02d%02d" % (1 + [c[0] for c in world.TOP_CATEGORIES].index(parent), order + 1),
        }
        rows.append(gen.row(k, rnd, fixed, anchor=created, country="SWE"))
        k += 1
    reg.ctx["category_id"] = ids
    reg.rows[fqn] = rows


_INCI = {
    "HAIRCARE": "Aqua, Sodium Laureth Sulfate, Cocamidopropyl Betaine, Glycerin, Betula Alba Leaf Extract, Sodium Chloride, Parfum, Citric Acid, Sodium Benzoate",
    "BODYCARE": "Aqua, Sodium Laureth Sulfate, Cocamidopropyl Betaine, Glycerin, Avena Sativa Kernel Extract, Parfum, Citric Acid, Potassium Sorbate",
    "ORALCARE": "Hydrated Silica, Sorbitol, Aqua, Glycerin, Xylitol, Sodium Fluoride, Aroma, Cellulose Gum, Sodium Benzoate",
    "SKINCARE": "Aqua, Glycerin, Butyrospermum Parkii Butter, Cetearyl Alcohol, Avena Sativa Kernel Extract, Panthenol, Parfum",
    "DEODORANT": "Aqua, Alcohol Denat., Glycerin, Hydroxyethylcellulose, Parfum, Triethyl Citrate, Tocopherol",
    "GIFTSET": "See individual products in the set",
}
_PACKAGING = {"CRISPBREAD": "cardboard", "GRANOLA": "composite", "SNACKBAR": "composite", "PORRIDGE": "paper",
              "JAM": "glass", "SPARKLING": "plastic", "JUICE": "composite", "OATDRINK": "composite",
              "HAIRCARE": "plastic", "BODYCARE": "plastic", "ORALCARE": "plastic", "SKINCARE": "plastic",
              "DEODORANT": "plastic", "GIFTSET": "cardboard"}


def _weights(s):
    """(net kg, gross kg, volume ml) for a SKU."""
    content, uom = D(str(s["content"])), s["uom"]
    if uom == "g":
        net = content / 1000
    elif uom == "kg":
        net = content
    elif uom == "ml":
        net = content / 1000
    elif uom == "L":
        net = content
    else:
        net = D("0.6")
    vol = None
    if uom == "ml":
        vol = content
    elif uom == "L":
        vol = content * 1000
    pack = D("0.08") if s["subcat"] in ("JAM",) else D("0.03")
    if s["code"].endswith("033C") or "033" in s["code"]:
        pack = D("0.015") * s["pack"]
    gross = net * (1 + D("0.06")) + pack
    return net.quantize(D("0.0001")), gross.quantize(D("0.0001")), (vol.quantize(D("0.0001")) if vol is not None else None)


def _skus(reg):
    fqn = "product.sku"
    pool = reg.alloc(fqn, len(world.SKUS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    rows = []
    plant_cc = {"LUND": "SE01PLUN", "NKPG": "SE01PNKP", "TMPR": "FI01PTMP", "POZN": "PL01PPOZ"}
    for i, s in enumerate(world.SKUS):
        ids[s["code"]] = pool[i]
        brand = world.BRAND[s["brand"]]
        plant = world.PLANT[s["plant"]]
        net, gross, vol = _weights(s)
        created = _ts(s["launch"] - datetime.timedelta(days=75 + (i % 40)))
        pc_brand = s["category"] == "PERSONAL_CARE"
        portfolio = "seasonal" if s["season"] else ("innovation" if s["subcat"] == "OATDRINK" else
                                                    ("core" if i % 3 else "strategic"))
        lifecycle = "launch" if s["launch"] >= datetime.date(2025, 6, 1) else (
            "growth" if s["launch"] >= datetime.date(2023, 1, 1) or s["subcat"] == "OATDRINK" else "mature")
        fixed = {
            "sku_id": pool[i], "brand_id": reg.ctx["brand_id"][s["brand"]],
            "company_code_id": reg.ctx["company_id"]["SE01"], "cost_center_id": reg.ctx["cc"][plant_cc[s["plant"]]],
            "gl_account_id": reg.ctx["gl"][("SE01", "3000")],
            "manufacturing_facility_id": reg.ctx["plant_id"][s["plant"]],
            "product_category_id": reg.ctx["category_id"][s["subcat"]],
            "profit_center_id": reg.ctx["pc"][s["brand"]],
            "code": s["code"], "color": ("White" if s["subcat"] in ("ORALCARE", "SKINCARE") else
                                         "Clear" if s["subcat"] in ("HAIRCARE", "BODYCARE") else None) if pc_brand else None,
            "country_of_origin": plant["country"], "created_timestamp": created, "currency_code": "EUR",
            "discontinuation_date": None, "ean": s["gtin"], "fefo_threshold_pct": D("66.00") if s["category"] != "PERSONAL_CARE" else D("50.00"),
            "gross_weight_kg": gross, "gtin": s["gtin"],
            "inci_declaration": _INCI.get(s["subcat"]) if pc_brand else None,
            "is_hazardous": s["form"] == "spray", "is_recyclable_packaging": s["subcat"] not in ("GRANOLA", "SNACKBAR"),
            "is_regulated_product": pc_brand, "is_sustainable": s["subcat"] in ("OATDRINK", "PORRIDGE", "CRISPBREAD") or "REFILL" in s["code"],
            "last_updated_timestamp": _ts(datetime.date(2026, 1, 15) + datetime.timedelta(days=i), 10),
            "launch_date": s["launch"], "lifecycle_stage": lifecycle, "msrp": s["rsp_eur"],
            "net_content": D(str(s["content"])), "net_content_uom": s["uom"], "net_weight_kg": net,
            "pack_size": s["pack"], "packaging_material_type": ("aluminum" if s["code"].endswith("033C") or "X033" in s["code"]
                                                                 else _PACKAGING[s["subcat"]]),
            "portfolio_classification": portfolio, "product_form": s["form"], "product_name": s["full_name"],
            "regulatory_category": "cosmetic" if pc_brand else "food",
            "scent": s["flavour"] if pc_brand else None, "short_description": s["full_name"][:60],
            "sku_status": "active", "standard_cost": s["std_cost_eur"],
            "storage_conditions": "refrigerated" if s["code"] == "KK-JCE-BLUESM-075" else (
                "flammable" if s["form"] == "spray" else "ambient"),
            "sub_brand": brand["sub_brands"][0 if s["subcat"] in ("CRISPBREAD", "SPARKLING", "HAIRCARE") else
                                             (1 if s["subcat"] in ("GRANOLA", "SNACKBAR", "PORRIDGE", "JUICE", "BODYCARE", "SKINCARE", "DEODORANT", "GIFTSET") else 2)],
            "subcategory": dict((c[0], c[1]) for c in world.SUBCATEGORIES)[s["subcat"]],
            "target_demographic": "kids" if "KIDS" in s["code"] else ("family" if "FAM" in s["code"] or s["category"] == "FOOD" else "adult"),
            "total_shelf_life_days": world.SHELF_LIFE_DAYS[s["subcat"]], "upc": None,
            "variant": s["flavour"], "volume_ml": vol,
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country="SWE"))
    reg.ctx["sku_id"] = ids
    reg.ctx["sku_by_id"] = dict((pool[i], s) for i, s in enumerate(world.SKUS))
    reg.rows[fqn] = rows


def _category(reg):
    fqn = "product.category"
    pool = reg.alloc(fqn, len(world.SKUS))
    rows = []
    for i, s in enumerate(world.SKUS):
        rows.append({"category_id": pool[i], "sku_id": reg.ctx["sku_id"][s["code"]]})
    reg.rows[fqn] = rows
