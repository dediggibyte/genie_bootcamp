"""Curated master data outside the Genie scope that the core domains depend on:
``sales.trade_account`` (25 fictional retail/wholesale customers) and
``distribution.distribution_facility`` (5 distribution centres).
"""
import datetime
from decimal import Decimal

from . import engine, world
from .curated_finance import BRAND_PC

D = Decimal

_TDP = {"tier_1_national": (420, 900), "tier_2_regional": (60, 220), "tier_3_local": (8, 40),
        "tier_4_independent": (1, 3)}
_RATING = {"tier_1_national": "A", "tier_2_regional": "BBB", "tier_3_local": "BB", "tier_4_independent": "B"}
_TAXFMT = {"SWE": "SE55%08d01", "NOR": "NO9%08dMVA", "DNK": "DK3%07d", "FIN": "FI2%07d",
           "DEU": "DE3%08d", "NLD": "NL8%08dB01", "POL": "PL7%09d"}


def _ts(d, h=9, m=0):
    return datetime.datetime.combine(d, datetime.time(h, m))


def generate(reg):
    _trade_accounts(reg)
    _distribution_facilities(reg)


def _trade_accounts(reg):
    fqn = "sales.trade_account"
    pool = reg.alloc(fqn, len(world.TRADE))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    rows = []
    for i, t in enumerate(world.TRADE):
        ids[t["key"]] = pool[i]
        country = t["country"]
        city = world.city(country, t["hq"])
        opened = datetime.date(2012 + (i * 3) % 10, 1 + (i * 5) % 12, 1 + (i * 7) % 27)
        comp = world.COMPANY[t["company"]]
        mix = t["mix"]
        dom_brand = ["BJORKO", "KALLKALLA", "MJUKCARE"][mix.index(max(mix))]
        fn_ = rnd.choice(world.FIRST_NAMES[country])
        ln_ = rnd.choice(world.LAST_NAMES[country])
        annual_eur = t["avg_eur"] * t["per_month"] * 12
        status, prev, reason, changed = "active", None, None, None
        last_order = datetime.date(2026, 9, 30) - datetime.timedelta(days=rnd.randint(0, 6))
        if t["key"] == world.DISPUTE_ACCOUNT:
            status, prev = "credit_hold", "active"
            reason = "Invoices disputed since June 2026 (pricing and short-shipment claims); new orders on credit hold"
            changed = _ts(world.CREDIT_HOLD_DATE, 10, 22)
            last_order = world.CREDIT_HOLD_DATE - datetime.timedelta(days=2)
        fixed = {
            "trade_account_id": pool[i], "profit_center_id": reg.ctx["pc"][BRAND_PC[dom_brand][1]],
            "account_close_date": None, "account_open_date": opened, "account_status": status,
            "account_tier": t["tier"], "account_type": t["type"],
            # annual contract value in the account's currency (about the expected annual billing)
            "acv_total": (D(str(annual_eur * 1.05)) / D(str(world.FX_BASE[comp["currency"]]))).quantize(D("0.01")),
            "credit_limit_amount": (D(str(t["avg_eur"] * t["per_month"] * 2.5)) /
                                    D(str(world.FX_BASE[comp["currency"]]))).quantize(D("1000")),
            "credit_rating": _RATING[t["tier"]], "currency_code": comp["currency"], "dba_name": t["dba"],
            "dsd_delivery_flag": False, "duns_number": "%09d" % (350000000 + i * 1234567 % 99999999),
            "edi_capable_flag": t["tier"] in ("tier_1_national", "tier_2_regional"),
            "gln": world.gtin13("7350098", 500 + i),
            "headquarters_address_line1": engine.street_address(country, rnd), "headquarters_address_line2": None,
            "headquarters_city": city[0], "headquarters_country_code": country,
            "headquarters_postal_code": engine.postal_code(city[4], rnd), "headquarters_state_province": city[1],
            "last_order_date": last_order,
            "legal_entity_name": t["legal"],
            "minimum_order_quantity": {"tier_1_national": 120, "tier_2_regional": 60}.get(t["tier"], 24),
            "otif_sla_target_percent": D("98.00") if t["tier"] == "tier_1_national" else D("95.00"),
            "payment_method": "edi_payment" if t["tier"] in ("tier_1_national", "tier_2_regional") else "wire_transfer",
            "payment_terms_code": "NET%d" % t["terms"], "previous_status": prev,
            "primary_contact_email": engine.email_for(fn_, ln_, rnd, 2000 + i),
            "primary_contact_name": "%s %s" % (fn_, ln_), "primary_contact_phone": engine.phone(country, rnd),
            "primary_language_code": world.COUNTRY_LANG[country][:2],
            "record_created_timestamp": _ts(opened - datetime.timedelta(days=14)),
            "record_updated_timestamp": changed or _ts(datetime.date(2026, 3, 1) + datetime.timedelta(days=i * 5), 15),
            "status_change_reason": reason, "status_change_timestamp": changed,
            "status_changed_by_user": "KHOLM07" if changed else None, "tax_exemption_flag": False,
            "tax_number": _TAXFMT[country] % (1000 + i * 37), "tdp_count": rnd.randint(*_TDP[t["tier"]]),
            "trade_channel": t["channel"], "vmi_enabled_flag": t["tier"] == "tier_1_national",
        }
        rows.append(gen.row(i, rnd, fixed, anchor=_ts(opened), country=country))
    reg.ctx["trade_id"] = ids
    reg.rows[fqn] = rows


def _distribution_facilities(reg):
    fqn = "distribution.distribution_facility"
    pool = reg.alloc(fqn, len(world.DCS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    rows = []
    logistic_cc = {"DCJKG": "SE01LJKG", "DCOSL": "NO01LOSL", "DCODE": "DK01LODE", "DCVAN": "FI01LVAN",
                   "DCHAM": "DE01LHAM"}
    for i, d in enumerate(world.DCS):
        ids[d["code"]] = pool[i]
        big = d["code"] in ("DCJKG", "DCHAM")
        fixed = {
            "distribution_facility_id": pool[i], "company_code_id": reg.ctx["company_id"][d["company"]],
            "cost_center_id": reg.ctx["cc"][logistic_cc[d["code"]]],
            "address_line_1": d["street"], "address_line_2": None, "city": d["city"], "closed_date": None,
            "contact_email": "dc.%s@example.com" % d["city"].lower().replace("ö", "o").replace("ø", "o"),
            "contact_phone": engine.phone(d["country"], rnd), "country_code": d["country"],
            "created_timestamp": _ts(d["opened"] - datetime.timedelta(days=60)),
            "cross_dock_enabled_flag": big, "cycle_count_frequency_days": 30 if big else 45,
            "dc_code": d["code"], "dc_name": d["name"], "dock_doors_inbound": 14 if big else 6,
            "dock_doors_outbound": 22 if big else 8, "dsd_hub_flag": False, "facility_type": d["type"],
            "fsc_certified_flag": True, "gmp_certified_flag": d["code"] in ("DCJKG", "DCHAM", "DCVAN"),
            "hazmat_certified_flag": big, "inventory_rotation_method": "fefo",
            "latitude": D(str(d["lat"])).quantize(D("0.0000001")), "longitude": D(str(d["lon"])).quantize(D("0.0000001")),
            "lease_expiration_date": None if big else datetime.date(2030, 12, 31),
            "modified_timestamp": _ts(datetime.date(2026, 4, 2 + i), 13), "opened_date": d["opened"],
            "operating_hours_weekday": "06:00-22:00" if big else "07:00-19:00",
            "operating_hours_weekend": "08:00-16:00" if big else None, "operational_status": "active",
            "osa_target_percentage": D("97.50"), "otif_target_percentage": D("96.00"),
            "ownership_type": "owned" if big else "leased", "postal_code": d["postal"],
            "sap_plant_code": d["sap"], "sap_storage_location": "0001", "shifts_per_day": 2 if big else 1,
            "state_province": d["region"], "storage_capacity_pallet_positions": 24000 if big else 9000,
            "temperature_controlled_flag": d["type"] in ("chilled", "multi_temperature"),
            "time_zone": world.COUNTRY_TZ[d["country"]],
            "total_capacity_sqft": D("320000.00") if big else D("140000.00"),
            "wms_site_code": "WMS_" + d["code"],
        }
        rows.append(gen.row(i, rnd, fixed, anchor=_ts(d["opened"]), country=d["country"]))
    reg.ctx["dc_id"] = ids
    reg.rows[fqn] = rows
