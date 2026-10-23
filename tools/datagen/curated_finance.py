"""Curated finance domain: legal entities, chart of accounts, profit/cost centres, ledgers,
standard costs, COGS allocations, AR/AP and the general ledger.

Accounting conventions used throughout (documented in data/README.md):

* ``journal_entry_line`` amounts are stored as **positive** values; the direction is in
  ``debit_credit_indicator`` (``D``/``C``). Every journal entry balances:
  sum(D) = sum(C) in transaction, company-code and group currency.
* ``amount_group_currency`` = ``amount_company_code_currency`` * monthly FX (EUR per unit).
* **Net Revenue** (authoritative, story S1) = sum over GL accounts with
  ``account_group = 'REVENUE'`` (3000, 3010, 3040, 3050) of credit minus debit, in group
  currency EUR. It is net of VAT, trade discounts and DTC returns. Shipping fees go to
  3900 (``OTHER_INCOME``, net of the VAT they contain) and are not revenue.
* DTC revenue and B2B billing are posted as monthly summary documents per company code;
  AP invoices and AP payments post one document each.
* The P&L is calibrated to revenue (``OPEX_RATIO``): EBIT about 10-13 % for the group and
  positive for every company code. Plant labour, depreciation and overheads are product costs
  (production settlement -> standard cost -> COGS). Balance-sheet accounts have their counter
  flows: production receipts into finished goods, intercompany supplies at standard cost,
  monthly payroll payments, quarterly VAT returns and opening balances on 2024-01-01.
"""
import datetime
from decimal import Decimal

from . import engine, world
from .engine import q

D = Decimal
ZERO = D("0")


def _ts(d, h=9, m=0):
    return datetime.datetime.combine(d, datetime.time(h, m))


# --------------------------------------------------------------------------------------
# masters
# --------------------------------------------------------------------------------------

def masters(reg):
    """company_code, gl_account, profit_center, cost_center, ledger."""
    _company_codes(reg)
    _gl_accounts(reg)
    _profit_centers(reg)
    _cost_centers(reg)
    _ledgers(reg)


_NACE = {"SE01": "C10.72", "NO01": "G46.39", "DK01": "G46.39", "FI01": "C11.07", "DE01": "G46.39",
         "PL01": "C20.42"}


def _company_codes(reg):
    fqn = "finance.company_code"
    pool = reg.alloc(fqn, len(world.COMPANIES))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = dict((c["code"], pool[i]) for i, c in enumerate(world.COMPANIES))
    reg.ctx["company_id"] = ids
    rows = []
    for i, c in enumerate(world.COMPANIES):
        created = _ts(c["founded"], 10)
        fixed = {
            "company_code_id": ids[c["code"]],
            "parent_company_code_id": None if c["code"] == "SE01" else ids["SE01"],
            "address_line1": c["street"], "address_line2": None, "city": c["city"],
            "classification_type": c["classification"], "code": c["code"],
            "cost_center_code": c["code"] + "ADM", "country_code": c["country"],
            "currency_code": c["currency"], "effective_from": c["founded"], "effective_to": None,
            "email_address": "finance.%s@example.com" % c["code"].lower(),
            "industry_code": _NACE[c["code"]], "is_consolidated_entity": True, "is_public_company": False,
            "legal_name": c["name"], "lifecycle_status": "active", "name": c["short"],
            "parent_company_code": None if c["code"] == "SE01" else "SE01",
            "phone_number": c["phone"], "postal_code": c["postal"], "primary_contact_method": "email",
            "record_audit_created": created,
            "record_audit_updated": _ts(datetime.date(2025, 1, 10 + i), 14),
            "state_province": c["region"], "tax_number": c["tax_number"],
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=c["country"]))
    reg.rows[fqn] = rows


def _gl_accounts(reg):
    fqn = "finance.gl_account"
    n = len(world.COMPANIES) * len(world.GL)
    pool = reg.alloc(fqn, n)
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    k = 0
    for c in world.COMPANIES:
        for g in world.GL:
            ids[(c["code"], g["number"])] = pool[k]
            k += 1
    reg.ctx["gl"] = ids
    parent_of = {"3040": "3000", "3050": "3010", "4100": "4000"}
    rows = []
    k = 0
    for c in world.COMPANIES:
        for g in world.GL:
            num = g["number"]
            bs = g["fs"] in ("balance_sheet", "retained_earnings")
            pl = not bs
            bs_class = "not_applicable"
            if g["type"] == "asset":
                bs_class = "non_current_asset" if num == "1290" else "current_asset"
            elif g["type"] == "liability":
                bs_class = "current_liability"
            elif g["type"] == "equity":
                bs_class = "equity"
            created = _ts(c["founded"] + datetime.timedelta(days=3), 9)
            if num in ("2810",):
                created = _ts(world.LOYALTY_PROGRAM["launched"], 9)
            fixed = {
                "gl_account_id": ids[(c["code"], num)],
                "company_code_id": reg.ctx["company_id"][c["code"]],
                "parent_chart_of_accounts_gl_account_id": ids[(c["code"], parent_of[num])] if num in parent_of else None,
                "primary_chart_of_accounts_gl_account_id": ids[("SE01", num)],
                "account_group": g["group"], "account_name": g["name"], "account_number": num,
                "account_short_name": g["short"], "account_status": "active", "account_type": g["type"],
                "balance_sheet_classification": bs_class, "blocked_for_posting_flag": False,
                "budget_control_flag": g["group"] in ("OPEX",),
                "cash_flow_category": ("investing" if num == "1290" else "financing" if g["type"] == "equity"
                                       else "operating"),
                "consolidation_account_number": "G" + num,
                "cost_center_required_flag": g["group"] in ("OPEX", "COGS"),
                "cost_element_category": "primary" if pl else "not_applicable",
                "cost_element_flag": pl,
                "currency_code": c["currency"], "debit_credit_indicator": g["side"],
                "field_status_group": {"REVENUE": "G029", "OTHER_INCOME": "G029", "COGS": "G004",
                                       "OPEX": "G004", "ASSET": "G001", "LIABILITY": "G001",
                                       "EQUITY": "G001"}[g["group"]],
                "financial_statement_category": g["fs"], "financial_statement_line_item": g["fs_line"],
                "intercompany_clearing_flag": False, "line_item_display_flag": True,
                "open_item_management_flag": num in ("1210", "1240", "2110", "2410"),
                "pl_category": g["pl"],
                "planning_level": "profit_center" if g["group"] in ("REVENUE", "COGS") else
                ("cost_center" if g["group"] == "OPEX" else "company_code"),
                "posting_allowed_flag": True, "profit_center_required_flag": pl,
                "reconciliation_account_flag": num in ("1210", "2110"),
                "retained_earnings_account_flag": num == "2990",
                "sort_key": "009" if num in ("1210", "2110") else "001",
                "sox_control_account_flag": num in ("1210", "2110", "1410", "3000", "3010", "4000"),
                "tax_category": ("output_tax" if num in ("3000", "3010", "3900", "2610") else
                                 "input_tax" if num in ("1510", "6100", "6300", "6400", "1430") else "non_taxable"),
                "tax_code_allowed_flag": num in ("3000", "3010", "3900", "6100", "6300", "6400", "1430"),
                "valid_from_date": created.date(), "valid_to_date": None, "created_timestamp": created,
            }
            rows.append(gen.row(k, rnd, fixed, anchor=created, country=c["country"]))
            k += 1
    reg.rows[fqn] = rows


# profit centres: code, name, type, level, parent code, brand, channel, company, gl number
PROFIT_CENTERS = [
    ("GROUP", "Fjällmark Group", "business_unit", 1, None, None, None, "SE01", None),
    ("BJORKO", "Björkö Pantry", "brand", 2, "GROUP", "BJORKO", None, "SE01", None),
    ("KALLKALLA", "Kallkälla", "brand", 2, "GROUP", "KALLKALLA", None, "SE01", None),
    ("MJUKCARE", "Mjuk Care", "brand", 2, "GROUP", "MJUKCARE", None, "SE01", None),
    ("BJORKODTC", "Björkö Pantry - Direct to Consumer", "channel", 3, "BJORKO", "BJORKO", "dtc", "SE01", "3010"),
    ("BJORKORET", "Björkö Pantry - Retail Trade", "channel", 3, "BJORKO", "BJORKO", "retail", "SE01", "3000"),
    ("KALLDTC", "Kallkälla - Direct to Consumer", "channel", 3, "KALLKALLA", "KALLKALLA", "dtc", "SE01", "3010"),
    ("KALLRET", "Kallkälla - Retail Trade", "channel", 3, "KALLKALLA", "KALLKALLA", "retail", "SE01", "3000"),
    ("MJUKDTC", "Mjuk Care - Direct to Consumer", "channel", 3, "MJUKCARE", "MJUKCARE", "dtc", "SE01", "3010"),
    ("MJUKRET", "Mjuk Care - Retail Trade", "channel", 3, "MJUKCARE", "MJUKCARE", "retail", "SE01", "3000"),
    ("PLTLUND", "Lund Food Plant", "cost_center", 2, "GROUP", "BJORKO", None, "SE01", "4100"),
    ("PLTNKPG", "Norrköping Beverage Plant", "cost_center", 2, "GROUP", "KALLKALLA", None, "SE01", "4100"),
    ("PLTTMPR", "Tampere Oat Drink Plant", "cost_center", 2, "GROUP", "KALLKALLA", None, "FI01", "4100"),
    ("PLTPOZN", "Poznań Personal Care Plant", "cost_center", 2, "GROUP", "MJUKCARE", None, "PL01", "4100"),
    ("CORPHQ", "Corporate Headquarters", "business_unit", 2, "GROUP", None, None, "SE01", "5000"),
    ("LOGISTICS", "Nordic Logistics", "business_unit", 2, "GROUP", None, None, "SE01", "6300"),
]
BRAND_PC = {"BJORKO": ("BJORKODTC", "BJORKORET"), "KALLKALLA": ("KALLDTC", "KALLRET"),
            "MJUKCARE": ("MJUKDTC", "MJUKRET")}
PLANT_PC = {"LUND": "PLTLUND", "NKPG": "PLTNKPG", "TMPR": "PLTTMPR", "POZN": "PLTPOZN"}
BUSINESS_AREA = {"BJORKO": "FOOD", "KALLKALLA": "BEVG", "MJUKCARE": "PCAR", None: "CORP"}


def _profit_centers(reg):
    fqn = "finance.profit_center"
    pool = reg.alloc(fqn, len(PROFIT_CENTERS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = dict((pc[0], pool[i]) for i, pc in enumerate(PROFIT_CENTERS))
    reg.ctx["pc"] = ids
    rows = []
    owners = ["Karin Lindqvist", "Johan Ek", "Maja Holm", "Erik Sandberg", "Sara Nyström", "Per Wallin"]
    for i, (code, name, typ, lvl, parent, brand, channel, comp, gl) in enumerate(PROFIT_CENTERS):
        c = world.COMPANY[comp]
        start = datetime.date(2019, 1, 1) if code != "PLTTMPR" else datetime.date(2024, 10, 1)
        if brand and code == brand:
            start = world.BRAND[brand]["launch"]
        owner = owners[i % len(owners)]
        fn_, ln_ = owner.split(" ")
        cat_code = world.BRAND[brand]["category"].replace("_", "")[:10] if brand else None
        fixed = {
            "profit_center_id": ids[code], "company_code_id": reg.ctx["company_id"][comp],
            "gl_account_id": reg.ctx["gl"][(comp, gl)] if gl else None,
            "parent_profit_center_id": ids[parent] if parent else None,
            "address_line_1": c["street"], "address_line_2": None, "city": c["city"],
            "brand_code": brand, "business_area_code": BUSINESS_AREA[brand], "channel_code": channel,
            "code": code, "consolidation_unit_code": "CU" + comp, "controlling_area_code": "FJ01",
            "cost_center_group_code": "CCG" + (brand or "CORP")[:6], "country_code": c["country"],
            "created_timestamp": _ts(start, 8), "currency_code": c["currency"],
            "description": "Profit centre for %s (hierarchy level %d)." % (name, lvl),
            "email_address": "controlling.%s@example.com" % code.lower(), "fax_number": None,
            "functional_area_code": "SALE" if channel else ("PROD" if typ == "cost_center" else "ADMN"),
            "geographic_region_code": c["country"], "hierarchy_level": lvl,
            "lock_indicator": False, "name": name, "phone_number": c["phone"],
            "planning_enabled_flag": True, "postal_code": c["postal"], "product_category_code": cat_code,
            "profit_center_status": "active", "profit_center_type": typ,
            "responsible_person_email": engine.email_for(fn_, ln_, rnd, 100 + i),
            "responsible_person_name": owner, "segment_code": (cat_code or "CORPORATE")[:10],
            "short_name": code.title()[:12], "sox_control_flag": False, "state_province_code": None,
            "tax_jurisdiction_code": comp + "VAT", "valid_from_date": start, "valid_to_date": None,
            "valuation_view": "profit_center" if lvl == 3 else "legal",
        }
        rows.append(gen.row(i, rnd, fixed, anchor=_ts(start), country=c["country"]))
    reg.rows[fqn] = rows


# cost centres: code, name, company, group/type, function, profit centre, plant/location, dept, category
COST_CENTERS = [
    ("SE01MGMT", "Group Management", "SE01", "ADMIN", "administration", "ADMN", "CORPHQ", "STHM", "MGT", "overhead"),
    ("SE01FIN", "Group Finance and Controlling", "SE01", "ADMIN", "administration", "ADMN", "CORPHQ", "STHM", "FIN", "overhead"),
    ("SE01IT", "Group IT and Data", "SE01", "ADMIN", "service", "ADMN", "CORPHQ", "STHM", "ITD", "overhead"),
    ("SE01MKBJ", "Brand Marketing Björkö Pantry", "SE01", "MARKETING", "marketing", "MRKT", "BJORKO", "STHM", "MKT", "indirect"),
    ("SE01MKKK", "Brand Marketing Kallkälla", "SE01", "MARKETING", "marketing", "MRKT", "KALLKALLA", "STHM", "MKT", "indirect"),
    ("SE01MKMC", "Brand Marketing Mjuk Care", "SE01", "MARKETING", "marketing", "MRKT", "MJUKCARE", "STHM", "MKT", "indirect"),
    ("SE01DTC", "DTC Webshop Operations Sweden", "SE01", "DTC", "sales", "SALE", "BJORKODTC", "STHM", "DTC", "indirect"),
    ("SE01SAL", "Sales Sweden", "SE01", "SALES", "sales", "SALE", "BJORKORET", "STHM", "SAL", "indirect"),
    ("SE01CS", "Customer Service Nordics", "SE01", "SALES", "service", "SALE", "CORPHQ", "STHM", "CSV", "overhead"),
    ("SE01PLUN", "Lund Plant Production", "SE01", "PRODUCTION", "production", "PROD", "PLTLUND", "LUND", "PRD", "direct"),
    ("SE01MLUN", "Lund Plant Maintenance", "SE01", "PRODUCTION", "maintenance", "PROD", "PLTLUND", "LUND", "MNT", "indirect"),
    ("SE01PNKP", "Norrköping Plant Production", "SE01", "PRODUCTION", "production", "PROD", "PLTNKPG", "NKPG", "PRD", "direct"),
    ("SE01MNKP", "Norrköping Plant Maintenance", "SE01", "PRODUCTION", "maintenance", "PROD", "PLTNKPG", "NKPG", "MNT", "indirect"),
    ("SE01LJKG", "Logistics DC Jönköping", "SE01", "LOGISTICS", "logistics", "LOGI", "LOGISTICS", "JKG1", "LOG", "indirect"),
    ("NO01SAL", "Sales Norway", "NO01", "SALES", "sales", "SALE", "KALLRET", "OSLO", "SAL", "indirect"),
    ("NO01DTC", "DTC Webshop Operations Norway", "NO01", "DTC", "sales", "SALE", "KALLDTC", "OSLO", "DTC", "indirect"),
    ("NO01LOSL", "Logistics DC Oslo", "NO01", "LOGISTICS", "logistics", "LOGI", "LOGISTICS", "OSL1", "LOG", "indirect"),
    ("NO01ADM", "Administration Norway", "NO01", "ADMIN", "administration", "ADMN", "CORPHQ", "OSLO", "ADM", "overhead"),
    ("DK01SAL", "Sales Denmark", "DK01", "SALES", "sales", "SALE", "BJORKORET", "CPHG", "SAL", "indirect"),
    ("DK01DTC", "DTC Webshop Operations Denmark", "DK01", "DTC", "sales", "SALE", "BJORKODTC", "CPHG", "DTC", "indirect"),
    ("DK01LODE", "Logistics DC Odense", "DK01", "LOGISTICS", "logistics", "LOGI", "LOGISTICS", "ODE1", "LOG", "indirect"),
    ("DK01ADM", "Administration Denmark", "DK01", "ADMIN", "administration", "ADMN", "CORPHQ", "CPHG", "ADM", "overhead"),
    ("FI01SAL", "Sales Finland", "FI01", "SALES", "sales", "SALE", "KALLRET", "HELS", "SAL", "indirect"),
    ("FI01DTC", "DTC Webshop Operations Finland", "FI01", "DTC", "sales", "SALE", "KALLDTC", "HELS", "DTC", "indirect"),
    ("FI01PTMP", "Tampere Plant Production", "FI01", "PRODUCTION", "production", "PROD", "PLTTMPR", "TMPR", "PRD", "direct"),
    ("FI01MTMP", "Tampere Plant Maintenance", "FI01", "PRODUCTION", "maintenance", "PROD", "PLTTMPR", "TMPR", "MNT", "indirect"),
    ("FI01QTMP", "Tampere Plant Quality", "FI01", "PRODUCTION", "quality", "PROD", "PLTTMPR", "TMPR", "QAS", "indirect"),
    ("FI01LVAN", "Logistics DC Vantaa", "FI01", "LOGISTICS", "logistics", "LOGI", "LOGISTICS", "VAN1", "LOG", "indirect"),
    ("DE01SALD", "Sales DACH", "DE01", "SALES", "sales", "SALE", "MJUKRET", "HMBG", "SAL", "indirect"),
    ("DE01SALB", "Sales Benelux", "DE01", "SALES", "sales", "SALE", "MJUKRET", "HMBG", "SAL", "indirect"),
    ("DE01DTC", "DTC Webshop Operations Germany and Netherlands", "DE01", "DTC", "sales", "SALE", "MJUKDTC", "HMBG", "DTC", "indirect"),
    ("DE01LHAM", "Logistics DC Hamburg", "DE01", "LOGISTICS", "logistics", "LOGI", "LOGISTICS", "HAM1", "LOG", "indirect"),
    ("DE01CRM", "Credit Management Germany", "DE01", "ADMIN", "administration", "ADMN", "CORPHQ", "HMBG", "FIN", "overhead"),
    ("DE01ADM", "Administration Germany", "DE01", "ADMIN", "administration", "ADMN", "CORPHQ", "HMBG", "ADM", "overhead"),
    ("PL01PPOZ", "Poznań Plant Production", "PL01", "PRODUCTION", "production", "PROD", "PLTPOZN", "POZN", "PRD", "direct"),
    ("PL01MPOZ", "Poznań Plant Maintenance", "PL01", "PRODUCTION", "maintenance", "PROD", "PLTPOZN", "POZN", "MNT", "indirect"),
    ("PL01QPOZ", "Poznań Plant Quality", "PL01", "PRODUCTION", "quality", "PROD", "PLTPOZN", "POZN", "QAS", "indirect"),
    ("PL01WPOZ", "Poznań Plant Warehouse", "PL01", "LOGISTICS", "logistics", "LOGI", "PLTPOZN", "POZN", "LOG", "indirect"),
    ("PL01ADM", "Administration Poland", "PL01", "ADMIN", "administration", "ADMN", "CORPHQ", "POZN", "ADM", "overhead"),
    ("PL01PROC", "Procurement Poland", "PL01", "ADMIN", "service", "PURC", "PLTPOZN", "POZN", "PUR", "overhead"),
]
_CC_DEFAULT_GL = {"ADMIN": "5000", "MARKETING": "6100", "DTC": "6300", "SALES": "5000", "PRODUCTION": "5000",
                  "LOGISTICS": "6300"}
_REGION = {"SE01": "NORD", "NO01": "NORD", "DK01": "NORD", "FI01": "NORD", "DE01": "DACH", "PL01": "CEE"}


def _cost_centers(reg):
    fqn = "finance.cost_center"
    pool = reg.alloc(fqn, len(COST_CENTERS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = dict((cc[0], pool[i]) for i, cc in enumerate(COST_CENTERS))
    reg.ctx["cc"] = ids
    reg.ctx["cc_rows"] = COST_CENTERS
    rows = []
    for i, (code, name, comp, grp, typ, func, pc, loc, dept, cat) in enumerate(COST_CENTERS):
        c = world.COMPANY[comp]
        start = c["founded"] + datetime.timedelta(days=20)
        if code.endswith("TMP"):
            start = datetime.date(2024, 10, 1)
        brand = None
        for pcrow in PROFIT_CENTERS:
            if pcrow[0] == pc:
                brand = pcrow[5]
        plant_code = loc if loc in world.PLANT or loc in ("JKG1", "OSL1", "ODE1", "VAN1", "HAM1") else None
        parent = comp + "ADM" if comp != "SE01" else "SE01MGMT"
        if code == parent:
            parent = None if comp == "SE01" else "SE01MGMT"
        fixed = {
            "cost_center_id": ids[code], "company_code_id": reg.ctx["company_id"][comp],
            "gl_account_id": reg.ctx["gl"][(comp, _CC_DEFAULT_GL[grp])],
            "profit_center_id": reg.ctx["pc"][pc],
            "activity_type_indicator": typ in ("production", "maintenance"),
            "allocation_method": "activity_based" if typ == "production" else ("assessment" if cat == "overhead" else "direct"),
            "budget_profile_code": "BP%s" % ("01" if grp in ("ADMIN",) else "02"),
            "business_area_code": BUSINESS_AREA[brand], "category": cat, "code": code,
            "controlling_area_code": "FJ01", "cost_center_group": grp, "cost_center_status": "active",
            "cost_center_type": typ, "country_code": c["country"], "currency_code": c["currency"],
            "department_code": dept, "description": "%s (%s, %s)" % (name, c["short"], grp.title()),
            "functional_area_code": func, "hierarchy_area": "FJ" + grp[:6], "location_code": loc,
            "lock_indicator": False, "name": name, "parent_cost_center_code": parent,
            "plant_code": plant_code, "region_code": _REGION[comp], "source_system_code": "SAPS4",
            "statistical_indicator": False, "valid_from_date": start, "valid_to_date": None,
            "created_timestamp": _ts(start, 9),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=_ts(start), country=c["country"]))
    reg.rows[fqn] = rows


_RETENTION = {"SE01": 7, "NO01": 5, "DK01": 5, "FI01": 10, "DE01": 10, "PL01": 5}


def _ledgers(reg):
    fqn = "finance.ledger"
    pool = reg.alloc(fqn, len(world.COMPANIES) + 1)
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    rows = []
    for i, c in enumerate(world.COMPANIES):
        ids[c["code"]] = pool[i]
        start = c["founded"]
        fixed = {
            "ledger_id": pool[i], "company_code_id": reg.ctx["company_id"][c["code"]],
            "gl_account_id": reg.ctx["gl"][(c["code"], "2990")], "accounting_principle": "IFRS",
            "audit_trail_enabled": True, "base_currency_code": c["currency"], "code": "0L" + c["code"],
            "consolidation_ledger_flag": False, "currency_type": "local",
            "description": "Leading ledger (IFRS) of %s in %s." % (c["name"], c["currency"]),
            "effective_end_date": None, "effective_start_date": start, "fiscal_year_variant": "K4",
            "is_leading_ledger": True, "ledger_status": "active", "ledger_type": "leading",
            "name": "Leading ledger %s" % c["code"], "posting_period_variant": "FJ01",
            "retention_period_years": _RETENTION[c["code"]], "sox_compliant_flag": False,
            "supports_cost_of_sales_accounting": True, "supports_profit_center_accounting": True,
            "supports_segment_reporting": True, "valuation_view": "legal", "created_timestamp": _ts(start, 8),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=_ts(start), country=c["country"]))
    i = len(world.COMPANIES)
    ids["GROUP"] = pool[i]
    start = datetime.date(2019, 1, 1)
    fixed = {
        "ledger_id": pool[i], "company_code_id": reg.ctx["company_id"]["SE01"],
        "gl_account_id": reg.ctx["gl"][("SE01", "2990")], "accounting_principle": "management",
        "audit_trail_enabled": True, "base_currency_code": "EUR", "code": "GRPMGMT",
        "consolidation_ledger_flag": True, "currency_type": "group",
        "description": "Group management ledger in EUR used for consolidated brand and channel reporting.",
        "effective_end_date": None, "effective_start_date": start, "fiscal_year_variant": "K4",
        "is_leading_ledger": False, "ledger_status": "active", "ledger_type": "extension",
        "name": "Group management ledger (EUR)", "posting_period_variant": "FJ01",
        "retention_period_years": 10, "sox_compliant_flag": False, "supports_cost_of_sales_accounting": True,
        "supports_profit_center_accounting": True, "supports_segment_reporting": True,
        "valuation_view": "group", "created_timestamp": _ts(start, 8),
    }
    rows.append(gen.row(i, rnd, fixed, anchor=_ts(start), country="SWE"))
    reg.ctx["ledger"] = ids
    reg.rows[fqn] = rows


# --------------------------------------------------------------------------------------
# standard costs (after product + manufacturing masters)
# --------------------------------------------------------------------------------------

_SPLIT = {  # raw, packaging, labour, machine OH, variable OH, fixed OH, freight-in
    "FOOD": ("0.48", "0.17", "0.12", "0.08", "0.06", "0.06", "0.03"),
    "BEVERAGE": ("0.30", "0.35", "0.08", "0.10", "0.06", "0.07", "0.04"),
    "PERSONAL_CARE": ("0.38", "0.27", "0.12", "0.08", "0.05", "0.07", "0.03"),
}
_COMPONENTS_SC = ("raw_material_cost", "packaging_material_cost", "direct_labor_cost", "machine_overhead_cost",
                  "variable_overhead_cost", "fixed_overhead_cost", "freight_in_cost")
_COMPONENTS_CA = ("raw_material_cost", "packaging_cost", "direct_labor_cost", "machine_overhead_cost",
                  "variable_overhead_cost", "fixed_overhead_cost", "freight_in_cost")


def split_cost(total, category, places="0.0001"):
    """Split a unit cost into components that add up exactly to ``total``."""
    shares = [D(x) for x in _SPLIT[category]]
    parts = [(total * s).quantize(D(places)) for s in shares]
    parts[0] += total - sum(parts)
    return parts


def standard_costs(reg):
    from .curated_manufacturing import unit_cost_local, plant_currency, PLANT_CC
    fqn = "finance.standard_cost"
    rnd = reg.rng(fqn)
    specs = []
    for s in world.SKUS:
        for y in (2024, 2025, 2026):
            start = datetime.date(y, 1, 1)
            end = datetime.date(y, 12, 31)
            if s["launch"] > end:
                continue
            specs.append((s, y, "standard", max(start, s["launch"]), None if y == 2026 else end))
            if y in (2024, 2025):
                specs.append((s, y + 1, "planned", datetime.date(y + 1, 1, 1),
                              datetime.date(y + 1, 12, 31) if y + 1 < 2026 else None))
            for h in (1, 2):
                hs = datetime.date(y, 1 if h == 1 else 7, 1)
                he = datetime.date(y, 6 if h == 1 else 12, 30 if h == 1 else 31)
                if he > world.TXN_END or s["launch"] > he:
                    continue
                specs.append((s, y, "actual", max(hs, s["launch"]), he))
    specs.sort(key=lambda x: (x[0]["index"], x[1], x[2], x[3]))
    pool = reg.alloc(fqn, len(specs))
    gen = reg.gen(fqn)
    rows = []
    reg.ctx["std_cost_id"] = {}
    for i, (s, y, ctype, vfrom, vto) in enumerate(specs):
        plant = s["plant"]
        cur = plant_currency(plant)
        std = unit_cost_local(s, y, plant)
        prev = unit_cost_local(s, y - 1, plant) if y > 2024 else (std / D("1.03")).quantize(D("0.0001"))
        total = std
        ratio = D(1)
        if ctype == "actual":
            ratio = reg.ctx.get("actual_ratio", {}).get((s["code"], y, 1 if vto.month <= 6 else 2), D(1))
            total = (std * ratio).quantize(D("0.0001"))
        parts = split_cost(total, s["category"])
        if ctype == "standard":
            created = datetime.datetime(y - 1, 11, 20, 9, 0) + datetime.timedelta(minutes=i % 300)
            release = datetime.date(y - 1, 12, 15)
            rel_status = "released" if y == 2026 else "archived"
            appr = "approved"
            reg.ctx["std_cost_id"][(s["code"], y)] = pool[i]
        elif ctype == "planned":
            created = datetime.datetime(y - 1, 10, 1, 9, 0) + datetime.timedelta(minutes=i % 300)
            release = None
            rel_status = "locked" if y <= 2026 else "draft"
            appr = "approved"
        else:
            created = datetime.datetime.combine(vto + datetime.timedelta(days=8), datetime.time(7, 30))
            release = vto + datetime.timedelta(days=10)
            rel_status = "locked"
            appr = "approved"
        if created < datetime.datetime.combine(s["launch"] - datetime.timedelta(days=60), datetime.time(9)):
            created = datetime.datetime.combine(s["launch"] - datetime.timedelta(days=60), datetime.time(9))
        approved_ts = created + datetime.timedelta(days=5)
        if release is not None and release < approved_ts.date():
            release = approved_ts.date()
        if approved_ts > world.EXTRACT_TS:
            approved_ts = world.EXTRACT_TS
        fixed = {
            "standard_cost_id": pool[i], "cost_center_id": reg.ctx["cc"][PLANT_CC[plant][0]],
            "primary_standard_manufacturing_facility_id": reg.ctx["plant_id"][plant],
            "primary_standard_sku_id": reg.ctx["sku_id"][s["code"]],
            "approval_status": appr, "approved_by": "Karin Lindqvist", "approved_timestamp": approved_ts,
            "bom_usage": "production", "cost_estimate_created_by": "SVC_COSTING",
            "cost_estimate_created_timestamp": created, "cost_estimate_modified_by": "SVC_COSTING",
            "cost_estimate_modified_timestamp": approved_ts,
            "cost_estimate_number": "CE-%s-%d-%s" % (s["code"], y, ctype[:3].upper()),
            "cost_variance_amount": (total - prev).quantize(D("0.0001")),
            "cost_variance_percentage": ((total - prev) / prev * 100).quantize(D("0.01")) if prev else D("0.00"),
            "costing_lot_size": D("1000.000"), "costing_lot_size_uom": "EA", "costing_sheet": "COGS01",
            "costing_type": ctype, "costing_version": {"standard": "STD1", "planned": "PLN1", "actual": "ACT1"}[ctype],
            "currency_code": cur, "fiscal_period": "%02d" % (1 if ctype != "actual" else vto.month),
            "fiscal_year": str(y), "notes": ("Annual standard cost roll %d" % y if ctype == "standard" else
                                             "Planning estimate for %d budget" % y if ctype == "planned" else
                                             "Actual costing H%d %d" % (1 if vto.month <= 6 else 2, y)),
            "previous_standard_cost": prev, "release_date": release, "release_status": rel_status,
            "routing_usage": "production", "total_standard_cost": total, "valid_from_date": vfrom,
            "valid_to_date": vto, "valuation_variant": "001",
        }
        for name, val in zip(_COMPONENTS_SC, parts):
            fixed[name] = val
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=world.PLANT[plant]["country"]))
    reg.rows[fqn] = rows


# --------------------------------------------------------------------------------------
# transactions: COGS allocation, AR, AP, general ledger
# --------------------------------------------------------------------------------------

def _q2(x):
    return q(x, 2)


def receivables(reg):
    """B2B billing (ar_invoice) and customer payments (ar_payment); runs before production so that
    production volumes can be planned from the demand."""
    _accounts_receivable(reg)


def transactions(reg):
    _cogs_allocation(reg)
    _accounts_payable(reg)
    _general_ledger(reg)
    for po in reg.rows["manufacturing.production_order"]:
        po.pop("_meta", None)


def _production_by_sku_month(reg):
    out = {}
    for po in reg.rows["manufacturing.production_order"]:
        m = po["_meta"]
        if m["progress"] < 1.0:
            continue
        fin = po["actual_finish_timestamp"]
        key = (m["sku"]["code"], fin.year, fin.month)
        agg = out.setdefault(key, {"planned": D(0), "actual": D(0), "qty": D(0), "conf": D(0),
                                   "incident": False, "plant": m["plant"]})
        agg["planned"] += po["planned_cost"]
        agg["actual"] += po["actual_cost"]
        agg["qty"] += po["order_quantity"]
        agg["conf"] += po["confirmed_quantity"]
        agg["incident"] = agg["incident"] or m["incident"]
    return out


def _cogs_allocation(reg):
    from .curated_manufacturing import unit_cost_local, plant_currency, PLANT_CC
    fqn = "finance.cogs_allocation"
    rnd = reg.rng(fqn)
    prod = _production_by_sku_month(reg)
    reg.ctx["prod_by_sku_month"] = prod
    specs = []
    for s in world.SKUS:
        for (y, m) in world.MONTHS:
            ms, me = world.month_start(y, m), world.month_end(y, m)
            if s["launch"] > me:
                continue
            if s["plant"] == "TMPR" and ms < world.TAMPERE_START:
                continue
            if not (world.sku_available(s, ms) or world.sku_available(s, me)) and (s["code"], y, m) not in prod:
                continue
            specs.append((s, y, m))
    specs.sort(key=lambda x: (x[1], x[2], x[0]["index"]))
    pool = reg.alloc(fqn, len(specs))
    gen = reg.gen(fqn)
    rows = []
    for i, (s, y, m) in enumerate(specs):
        plant = s["plant"]
        cur = plant_currency(plant)
        std = unit_cost_local(s, y, plant)
        agg = prod.get((s["code"], y, m))
        if agg and agg["planned"] > 0:
            ratio = agg["actual"] / agg["planned"]
            variance = _q2(agg["actual"] - agg["planned"])
        else:
            ratio, variance = D(1), D("0.00")
        actual_unit = (std * ratio).quantize(D("0.01"))
        parts = split_cost(actual_unit, s["category"], "0.01")
        if agg and agg["incident"]:
            vcat = "yield"
        elif plant == "TMPR" and variance > 0 and (y, m) < (2026, 1):
            vcat = "efficiency"
        elif agg is None:
            vcat = "volume"
        else:
            vcat = "quantity" if variance > 0 else "price"
        me = world.month_end(y, m)
        created = datetime.datetime.combine(me + datetime.timedelta(days=3), datetime.time(6, 15))
        fixed = {
            "cogs_allocation_id": pool[i], "cost_center_id": reg.ctx["cc"][PLANT_CC[plant][0]],
            "manufacturing_facility_id": reg.ctx["plant_id"][plant],
            "product_bom_id": reg.ctx["product_bom_id"][s["code"]],
            "profit_center_id": reg.ctx["pc"][PLANT_PC_OF[plant]],
            "routing_id": reg.ctx["routing_of"][s["code"]], "sku_id": reg.ctx["sku_id"][s["code"]],
            "standard_cost_id": reg.ctx["std_cost_id"].get((s["code"], y)),
            "allocation_date": me, "allocation_method": "standard" if agg is None else "weighted_average",
            "approved_by": "Karin Lindqvist", "approved_timestamp": created + datetime.timedelta(days=2),
            "costing_lot_size": D("1000.000"), "costing_sheet": "COGS01", "costing_type": "actual",
            "costing_version": "ACT1", "created_timestamp": created, "currency_code": cur,
            "depreciation_cost": (parts[3] * D("0.4")).quantize(D("0.01")), "fiscal_period": m, "fiscal_year": y,
            "lot_size_unit": "EA", "modified_timestamp": created + datetime.timedelta(days=2, hours=3),
            "notes": ("Yield loss on PL-POZ-L2 (worn filler nozzles) increased actual cost" if agg and agg["incident"]
                      else None if agg else "No production in period - valued at standard"),
            "price_control_indicator": "S", "release_status": "released" if (y, m) < (2026, 9) else "draft",
            "total_cost_amount": actual_unit, "validity_end_date": me, "validity_start_date": world.month_start(y, m),
            "valuation_class": "7920", "variance_amount": variance, "variance_category": vcat,
        }
        for name, val in zip(_COMPONENTS_CA, parts):
            fixed[name] = val
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=world.PLANT[plant]["country"]))
    reg.rows[fqn] = rows


PLANT_PC_OF = PLANT_PC

_AR_DIST_CHANNEL = {"grocery": "10", "convenience": "10", "discount": "10", "specialty": "10", "organic": "10",
                    "health_food": "10", "drugstore": "12", "pharmacy": "12", "cash_and_carry": "20",
                    "beverage_wholesale": "20", "foodservice": "30"}
_DISPUTE_REASONS = [("PRICE", "Price discrepancy against the agreed 2026 promotional price list"),
                    ("SHORTSHIP", "Short-shipment claim: quantities on invoice not received at DC"),
                    ("DAMAGE", "Damaged goods claim for leaking body wash cartons")]
DISPUTE_SHARE = 0.34
B2B_VOLUME = 0.9          # invoices per month = trade account frequency x this factor


def _pay_days(t, billing, rnd):
    """Days from billing to payment. Nordic customers pay close to their 30-day terms; German and
    Dutch customers (45-day terms) a little late; Alpina Drogerie (S6) much later once it disputes."""
    tier = t["tier"]
    if t["company"] == "DE01":
        if t["key"] == world.DISPUTE_ACCOUNT:
            mean = 61 if billing >= world.DISPUTE_FROM else 50
            sd = 7
        else:
            mean, sd = 47, 8
    elif t["company"] == "PL01":
        mean, sd = 34, 5
    else:
        mean = {"tier_1_national": 35, "tier_2_regional": 37}.get(tier, 41)
        sd = {"tier_1_national": 2, "tier_2_regional": 4}.get(tier, 6)
    return max(5, int(round(rnd.gauss(mean, sd))))


def _brand_split(amount, mix_keys, mix):
    parts = [(amount * D(str(w))).quantize(D("0.01")) for w in mix]
    diff = amount - sum(parts)
    j = mix.index(max(mix))
    parts[j] += diff
    return dict(zip(mix_keys, parts))


def _accounts_receivable(reg):
    fq_i, fq_p = "finance.ar_invoice", "finance.ar_payment"
    rnd = reg.rng(fq_i)
    prnd = reg.rng(fq_p)
    brands = ("BJORKO", "KALLKALLA", "MJUKCARE")
    cat_of = {"BJORKO": "FOOD", "KALLKALLA": "BEVERAGE", "MJUKCARE": "PERSONAL_CARE"}
    specs = []
    for t in world.TRADE:
        comp = world.COMPANY[t["company"]]
        for (y, m) in world.MONTHS:
            ms, me = world.month_start(y, m), world.month_end(y, m)
            # volume growth (b2b_growth, +5 % a year) is applied once - to the invoice value, not the count
            n = max(1, int(round(t["per_month"] * B2B_VOLUME * rnd.uniform(0.95, 1.05))))
            for k in range(n):
                day = ms + datetime.timedelta(days=rnd.randint(0, (me - ms).days))
                if t["key"] == world.DISPUTE_ACCOUNT and day > world.CREDIT_HOLD_DATE:
                    continue        # no new deliveries once the account is on credit hold
                if day.weekday() >= 5:
                    day -= datetime.timedelta(days=day.weekday() - 4)
                    if day < ms:
                        day = ms
                # brand mix with seasonality and some noise
                raw = [t["mix"][j] * world.b2b_season(cat_of[b], m) * rnd.uniform(0.85, 1.15) for j, b in enumerate(brands)]
                tot = sum(raw) or 1.0
                mix = [round(r / tot, 4) for r in raw]
                season = sum(t["mix"][j] * world.b2b_season(cat_of[b], m) for j, b in enumerate(brands))
                gross_eur = t["avg_eur"] * season * world.b2b_growth(y, m) * rnd.lognormvariate(0, 0.25)
                specs.append((day, t, mix, gross_eur))
    specs.sort(key=lambda x: (x[0], x[1]["key"]))
    ipool = reg.alloc(fq_i, len(specs))
    as_of = world.AS_OF_DATE
    invoices = []
    payments = []
    dispute_seq = 0
    for i, (day, t, mix, gross_eur) in enumerate(specs):
        comp = world.COMPANY[t["company"]]
        cur = comp["currency"]
        gross = _q2(D(str(gross_eur)) / world.fx_d(cur, day.year, day.month))
        td_rate = D({"tier_1_national": "0.09", "tier_2_regional": "0.07", "tier_3_local": "0.05",
                     "tier_4_independent": "0.03"}[t["tier"]])
        trade_disc = _q2(gross * td_rate)
        net = gross - trade_disc
        intra_eu = t["country"] != comp["country"]
        vat = D(0) if intra_eu else world.VAT_RATE[comp["country"]]
        tax = _q2(net * vat)
        total = net + tax
        due = day + datetime.timedelta(days=t["terms"])
        meta = {"t": t, "mix": mix, "brands": brands, "intra_eu": intra_eu, "payments": []}
        disputed = False
        if t["key"] == world.DISPUTE_ACCOUNT and day >= world.DISPUTE_FROM:
            rnd.random()                     # keeps the random sequence of the other invoices stable
            dispute_seq += 1
            disputed = dispute_seq % 3 == 1  # every third Alpina invoice from June 2026 (~DISPUTE_SHARE)
        deduction = D(0)
        ded_reason = None
        dispute_reason = None
        if disputed:
            code, text = _DISPUTE_REASONS[rnd.randrange(len(_DISPUTE_REASONS))]
            ded_reason, dispute_reason = code, text
        elif rnd.random() < 0.08:
            deduction = _q2(total * D(str(round(rnd.uniform(0.01, 0.04), 4))))
            ded_reason = rnd.choice(["PROMO", "SHORTSHIP", "DAMAGE", "PRICE"])
        received = D(0)
        write_off = None
        wo_date = None
        last_pay = None
        if not disputed:
            pd_ = day + datetime.timedelta(days=_pay_days(t, day, prnd))
            if pd_ <= as_of:
                first = total - deduction
                meta["payments"].append((pd_, first, deduction, ded_reason))
                received += first
                last_pay = pd_
                if deduction > 0:
                    pd2 = pd_ + datetime.timedelta(days=prnd.randint(20, 75))
                    if pd2 <= as_of and prnd.random() < 0.7:
                        meta["payments"].append((pd2, deduction, D(0), None))
                        received += deduction
                        last_pay = pd2
                    elif (as_of - pd_).days > 150:
                        write_off = deduction
                        wo_date = pd_ + datetime.timedelta(days=prnd.randint(120, 150))
        outstanding = total - received - (write_off or D(0))
        if disputed:
            status = "disputed"
        elif outstanding == 0 and write_off:
            status = "written_off"
        elif outstanding == 0:
            status = "paid"
        elif received > 0:
            status = "partially_paid"
        else:
            status = "open"
        bucket = None
        dunning = 0
        last_dun = None
        if outstanding > 0:
            past = (as_of - due).days
            bucket = ("current" if past <= 0 else "1_30_days" if past <= 30 else "31_60_days" if past <= 60
                      else "61_90_days" if past <= 90 else "over_90_days" if past <= 120 else "over_120_days")
            dunning = 0 if past <= 0 else (1 if past <= 14 else (2 if past <= 30 else 3))
            if dunning:
                last_dun = due + datetime.timedelta(days=7 * dunning)
                if last_dun > as_of:
                    last_dun = as_of
        created = engine.as_dt(day) + datetime.timedelta(hours=18, minutes=prnd.randint(0, 59))
        modified = engine.as_dt(last_pay or wo_date or last_dun or day) + datetime.timedelta(hours=20)
        if disputed:
            modified = engine.as_dt(day + datetime.timedelta(days=prnd.randint(10, 40))) + datetime.timedelta(hours=11)
            if modified.date() > as_of:
                modified = engine.as_dt(as_of) + datetime.timedelta(hours=11)
        fixed = {
            "ar_invoice_id": ipool[i], "company_code_id": reg.ctx["company_id"][t["company"]],
            "gl_account_id": reg.ctx["gl"][(t["company"], "1210")], "sales_invoice_id": reg.pick("sales.invoice", rnd),
            "shopper_id": None, "trade_account_id": reg.ctx["trade_id"][t["key"]],
            "amount_received": received, "billing_date": day, "billing_document_type": "F2",
            "clearing_date": last_pay if status == "paid" else (wo_date if status == "written_off" else None),
            "clearing_reference": ("CLR%010d" % (i + 1)) if status in ("paid", "written_off") else None,
            "created_timestamp": created, "currency_code": cur, "deduction_amount": deduction if deduction else (
                D("0.00") if not disputed else D("0.00")),
            "deduction_reason_code": ded_reason, "dispute_flag": disputed, "dispute_reason": dispute_reason,
            "distribution_channel": _AR_DIST_CHANNEL[t["channel"]], "dso_aging_bucket": bucket, "due_date": due,
            "dunning_level": dunning, "fiscal_period": day.month, "fiscal_year": day.year, "gl_posting_date": day,
            "gross_amount": gross, "invoice_number": "90%08d" % (i + 1), "invoice_status": status,
            "last_dunning_date": last_dun, "modified_by_user": "SVCAR" if not disputed else "KHOLM07",
            "modified_timestamp": min(modified, world.EXTRACT_TS), "net_amount": net, "outstanding_balance": outstanding,
            "payment_date": last_pay, "payment_method": "edi_payment" if t["tier"] in ("tier_1_national", "tier_2_regional") else "wire_transfer",
            "payment_terms_code": "NET%d" % t["terms"], "revenue_recognition_date": day,
            "sales_order_number": "SO%08d" % (40000000 + i), "sales_organization": t["company"],
            "shipment_number": "80%08d" % (i + 1), "tax_amount": tax, "total_amount": total,
            "trade_discount_amount": trade_disc, "write_off_amount": write_off, "write_off_date": wo_date,
            "write_off_reason_code": "SMALLBAL" if write_off else None,
        }
        row = reg.gen(fq_i).row(i, rnd, fixed, anchor=created, country=t["country"])
        row["_meta"] = meta
        invoices.append(row)
    reg.rows[fq_i] = invoices
    # payments
    pspecs = []
    for inv in invoices:
        for (pd_, amt, ded, ded_reason) in inv["_meta"]["payments"]:
            pspecs.append((pd_, inv, amt, ded, ded_reason))
    pspecs.sort(key=lambda x: (x[0], x[1]["ar_invoice_id"]))
    ppool = reg.alloc(fq_p, len(pspecs))
    gen = reg.gen(fq_p)
    prows = []
    cc_fin = {"SE01": "SE01FIN", "NO01": "NO01ADM", "DK01": "DK01ADM", "FI01": "FI01SAL", "DE01": "DE01CRM",
              "PL01": "PL01ADM"}
    for i, (pd_, inv, amt, ded, ded_reason) in enumerate(pspecs):
        t = inv["_meta"]["t"]
        comp = world.COMPANY[t["company"]]
        edi = t["tier"] in ("tier_1_national", "tier_2_regional")
        partial = amt < inv["total_amount"]
        ts = engine.as_dt(pd_) + datetime.timedelta(hours=7, minutes=prnd.randint(0, 120))
        fixed = {
            "ar_payment_id": ppool[i], "ar_invoice_id": inv["ar_invoice_id"],
            "company_code_id": inv["company_code_id"], "cost_center_id": reg.ctx["cc"][cc_fin[t["company"]]],
            "gl_account_id": reg.ctx["gl"][(t["company"], "1110")], "invoice_id": inv["sales_invoice_id"],
            "shopper_id": None, "trade_account_id": inv["trade_account_id"], "applied_amount": amt,
            "bank_account_code": 440100 + world.COMPANIES.index(comp),
            "bank_reference_number": "BNK%s%010d" % (t["company"], i + 1),
            "business_area_code": BUSINESS_AREA[["BJORKO", "KALLKALLA", "MJUKCARE"][inv["_meta"]["mix"].index(max(inv["_meta"]["mix"]))]],
            "check_number": None, "clearing_document_number": "14%08d" % (i + 1), "company_code": t["company"],
            "created_by_user": "SVC_BANK", "created_timestamp": ts, "days_to_pay": (pd_ - inv["billing_date"]).days,
            "deduction_amount": ded, "deduction_notes": ("Customer deducted %s on remittance advice" % ded_reason) if ded else None,
            "deduction_reason_code": ded_reason if ded else None, "discount_amount": D("0.00"),
            "due_date": inv["due_date"], "edi_transaction_set_reference": ("820%012d" % (i + 1)) if edi else None,
            "exchange_rate": D("1.000000"), "fiscal_period": pd_.month, "fiscal_year": pd_.year,
            "local_currency_amount": amt, "local_currency_code": comp["currency"], "lockbox_batch_number": None,
            "modified_by_user": "SVC_BANK", "modified_timestamp": ts + datetime.timedelta(hours=2),
            "overpayment_flag": False, "partial_payment_flag": partial, "payment_amount": amt,
            "payment_channel": "edi_820" if edi else "bank_transfer", "payment_currency_code": comp["currency"],
            "payment_date": pd_, "payment_document_number": "RA%010d" % (i + 1),
            "payment_method": "electronic_funds_transfer" if edi else "wire_transfer", "payment_processor_code": None,
            "payment_status": "partially_applied" if partial else "applied", "payment_terms_code": inv["payment_terms_code"],
            "posting_date": pd_, "remittance_advice_number": ("RMT%010d" % (i + 1)) if edi else None,
            "reversal_date": None, "reversal_flag": False, "reversal_reason_code": None,
            "short_payment_flag": bool(ded), "value_date": pd_ + datetime.timedelta(days=1),
        }
        prows.append(gen.row(i, prnd, fixed, anchor=ts, country=t["country"]))
    reg.rows[fq_p] = prows


# --------------------------------------------------------------------------------------
# financial plan: revenue per company, cost ratios, demand per plant
# --------------------------------------------------------------------------------------
# operating cost ratios as a share of each company's net revenue (EUR). Plant labour, plant
# depreciation and plant overheads are product costs (in standard cost -> COGS), not opex.
OPEX_RATIO = {  # payroll 5000, marketing 6100, freight/logistics 6300, rent/utilities/IT 6400, depreciation 7000
    "SE01": {"5000": "0.200", "6100": "0.080", "6300": "0.080", "6400": "0.050", "7000": "0.030"},
    "NO01": {"5000": "0.160", "6100": "0.080", "6300": "0.080", "6400": "0.050", "7000": "0.020"},
    "DK01": {"5000": "0.160", "6100": "0.080", "6300": "0.080", "6400": "0.050", "7000": "0.020"},
    "FI01": {"5000": "0.160", "6100": "0.080", "6300": "0.080", "6400": "0.050", "7000": "0.020"},
    "DE01": {"5000": "0.160", "6100": "0.080", "6300": "0.080", "6400": "0.050", "7000": "0.020"},
    "PL01": {"5000": "0.220", "6100": "0.060", "6300": "0.080", "6400": "0.060", "7000": "0.030"},
}
# standard cost structure -> where conversion costs come from (shares of actual production cost)
_COST_SHARE = {  # materials (raw+packaging+freight-in), plant labour (labour+fixed OH), depreciation, other overhead
    "FOOD": ("0.68", "0.18", "0.08", "0.06"),
    "BEVERAGE": ("0.69", "0.15", "0.10", "0.06"),
    "PERSONAL_CARE": ("0.68", "0.19", "0.08", "0.05"),
}
BRAND_PLANT = {"BJORKO": "LUND", "KALLKALLA": "NKPG", "MJUKCARE": "POZN"}
PLANT_COMPANY = dict((p["code"], p["company"]) for p in world.PLANTS)
_BRANDS = ("BJORKO", "KALLKALLA", "MJUKCARE")


def tampere_share(y, m):
    """Share of Kallkälla B2B volume that is oat drink made in Tampere (10 % at launch, 30 % from mid-2026)."""
    if (y, m) < (2025, 5):
        return D(0)
    k = world.month_index(y, m) - world.month_index(2025, 5)
    return min(D("0.30"), D("0.10") + D(k) * D("0.0167"))


def cogs_plan(reg):
    """Standard cost of goods sold per company-month, split by brand, channel and producing plant.

    {(company, y, m): {(brand, channel, plant): amount in company currency}}. B2B COGS = billed gross
    x the brand's standard-cost/list-price ratio; DTC COGS = order lines' cost_of_goods_sold. Used for
    the COGS postings and to plan production volumes (plants produce one month ahead of demand).
    """
    if "cogs_plan" in reg.ctx:
        return reg.ctx["cogs_plan"]
    from .curated_consumer import std_cost_factor
    ratio = _brand_cost_ratio()
    plan = {}
    gross = {}
    for inv in reg.rows["finance.ar_invoice"]:
        meta = inv["_meta"]
        d = inv["billing_date"]
        g = _brand_split(inv["gross_amount"], meta["brands"], meta["mix"])
        a = gross.setdefault((meta["t"]["company"], d.year, d.month), {})
        for b in meta["brands"]:
            a[b] = a.get(b, D(0)) + g[b]
    for (comp, y, m), a in gross.items():
        p = plan.setdefault((comp, y, m), {})
        for b in _BRANDS:
            amt = _q2(a.get(b, D(0)) * ratio[b] * std_cost_factor(y))
            if b == "KALLKALLA":
                oat = _q2(amt * tampere_share(y, m))
                p[(b, "B2B", "TMPR")] = oat
                p[(b, "B2B", "NKPG")] = amt - oat
            else:
                p[(b, "B2B", BRAND_PLANT[b])] = amt
    sku_of = reg.ctx["sku_by_id"]
    orders = dict((o["dtc_order_id"], o) for o in reg.rows["consumer.dtc_order"])
    for ln in reg.rows["consumer.dtc_order_line"]:
        o = orders[ln["dtc_order_id"]]
        if o["order_status"] not in ("shipped", "delivered", "returned"):
            continue
        comp = _company_of_id(reg, o["company_code_id"])
        d = o["order_date"]
        s = sku_of[ln["sku_id"]]
        key = (s["brand"], "DTC", s["plant"])
        p = plan.setdefault((comp, d.year, d.month), {})
        p[key] = p.get(key, D(0)) + ln["cost_of_goods_sold"]
    for p in plan.values():
        for key in p:
            p[key] = _q2(p[key])
    reg.ctx["cogs_plan"] = plan
    return plan


def plant_demand_eur(reg):
    """{(plant, y, m): standard cost of goods sold in EUR} over all selling companies."""
    out = {}
    for (comp, y, m), p in cogs_plan(reg).items():
        rate = world.fx_d(world.COMPANY[comp]["currency"], y, m)
        for (b, ch, plant), amt in p.items():
            out[(plant, y, m)] = out.get((plant, y, m), D(0)) + amt * rate
    return out


def net_revenue_plan(reg):
    """{(company, year): net revenue EUR} from B2B invoices (net of trade discounts) and DTC lines
    (shipped/delivered/returned orders, after returns)."""
    if "revenue_plan" in reg.ctx:
        return reg.ctx["revenue_plan"]
    out = {}
    for inv in reg.rows["finance.ar_invoice"]:
        comp = inv["_meta"]["t"]["company"]
        d = inv["billing_date"]
        rate = world.fx_d(world.COMPANY[comp]["currency"], d.year, d.month)
        out[(comp, d.year)] = out.get((comp, d.year), D(0)) + inv["net_amount"] * rate
    orders = dict((o["dtc_order_id"], o) for o in reg.rows["consumer.dtc_order"])
    for ln in reg.rows["consumer.dtc_order_line"]:
        o = orders[ln["dtc_order_id"]]
        if o["order_status"] not in ("shipped", "delivered", "returned") or ln["is_returned"]:
            continue
        comp = _company_of_id(reg, o["company_code_id"])
        d = o["order_date"]
        rate = world.fx_d(o["currency_code"], d.year, d.month)
        out[(comp, d.year)] = out.get((comp, d.year), D(0)) + ln["line_net_amount"] * rate
    reg.ctx["revenue_plan"] = out
    return out


def monthly_revenue_eur(reg, comp, y):
    """Average monthly net revenue (EUR) of a company in a year (2026: January-September)."""
    months_in_year = 9 if y == world.TXN_END.year else 12
    return net_revenue_plan(reg).get((comp, y), D(0)) / months_in_year


def production_cost_by_month(reg):
    """{(plant, y, m): (planned, actual)} of production orders completed in the month (plant currency)."""
    out = {}
    for po in reg.rows["manufacturing.production_order"]:
        meta = po["_meta"]
        if meta["progress"] < 1.0:
            continue
        fin = po["actual_finish_timestamp"]
        if (fin.year, fin.month) > (world.TXN_END.year, world.TXN_END.month):
            continue
        a = out.setdefault((meta["plant"], fin.year, fin.month), [D(0), D(0)])
        a[0] += po["planned_cost"]
        a[1] += po["actual_cost"]
    return out


def cost_shares(plant):
    return tuple(D(x) for x in _COST_SHARE[world.PLANT[plant]["category"]])


# --------------------------------------------------------------------------------------
# accounts payable: material purchases follow production, opex invoices follow the cost plan
# --------------------------------------------------------------------------------------
_AP_OPEX = [  # (category, gl account, share of the account's monthly budget, typical invoice EUR)
    ("marketing_services", "6100", "1.00", 15000), ("freight_and_logistics", "6300", "1.00", 14000),
    ("utilities_and_energy", "6400", "0.55", 9000), ("maintenance_and_spares", "6400", "0.25", 6000),
    ("it_services", "6400", "0.20", 5000)]


def _split_amount(total, n, rnd):
    w = [rnd.uniform(0.6, 1.4) for _ in range(n)]
    tw = sum(w)
    return [total * w_ / tw for w_ in w]


def _accounts_payable(reg):
    fq_i, fq_p = "finance.ap_invoice", "finance.ap_payment"
    rnd = reg.rng(fq_i)
    prnd = reg.rng(fq_p)
    specs = []
    # 1. raw and packaging materials: producers buy what their plants consume (plus a little stock)
    prod = production_cost_by_month(reg)
    first_month = {}
    for (plant, y, m) in sorted(prod):
        first_month.setdefault(plant, (y, m))
    for (plant, y, m), (planned, actual) in sorted(prod.items()):
        comp = PLANT_COMPANY[plant]
        factor = rnd.uniform(0.99, 1.05)
        if (y, m) == first_month[plant] and (y, m) > (world.TXN_START.year, world.TXN_START.month):
            factor += 1.0           # a plant that starts in the window buys an initial month of stock
        mat_local = actual * cost_shares(plant)[0] * D(str(factor))
        mat_eur = float(mat_local * world.fx_d(world.COMPANY[comp]["currency"], y, m))
        n = max(2, int(round(mat_eur / 45000.0)))
        for k, amt in enumerate(_split_amount(mat_eur, n, rnd)):
            cat = ("raw_materials", "1430") if k % 3 != 2 else ("packaging", "1430")
            day = world.month_start(y, m) + datetime.timedelta(days=rnd.randint(0, 27))
            specs.append((day, comp, cat, amt))
    # 2. operating costs: marketing, freight, rent/utilities/maintenance/IT sized to the cost ratios
    for comp in sorted(OPEX_RATIO):
        for (y, m) in world.MONTHS:
            rev = float(monthly_revenue_eur(reg, comp, y))
            for name, gl, share, typical in _AP_OPEX:
                budget = rev * float(OPEX_RATIO[comp][gl]) * float(share) * rnd.uniform(0.85, 1.15)
                if budget <= 0:
                    continue
                n = max(1, int(round(budget / typical)))
                for amt in _split_amount(budget, n, rnd):
                    day = world.month_start(y, m) + datetime.timedelta(days=rnd.randint(0, 27))
                    specs.append((day, comp, (name, gl), amt))
    specs.sort(key=lambda s: (s[0], s[1]))
    ipool = reg.alloc(fq_i, len(specs))
    gen = reg.gen(fq_i)
    invoices = []
    pay_specs = []
    cc_for = {"SE01": {"1430": "SE01PLUN", "6300": "SE01LJKG", "6100": "SE01MKBJ", "6400": "SE01MLUN"},
              "PL01": {"1430": "PL01PPOZ", "6300": "PL01WPOZ", "6100": "PL01ADM", "6400": "PL01MPOZ"},
              "FI01": {"1430": "FI01PTMP", "6300": "FI01LVAN", "6100": "FI01DTC", "6400": "FI01MTMP"},
              "DE01": {"1430": "DE01LHAM", "6300": "DE01LHAM", "6100": "DE01DTC", "6400": "DE01ADM"},
              "NO01": {"1430": "NO01LOSL", "6300": "NO01LOSL", "6100": "NO01DTC", "6400": "NO01ADM"},
              "DK01": {"1430": "DK01LODE", "6300": "DK01LODE", "6100": "DK01DTC", "6400": "DK01ADM"}}
    pc_for = {"SE01": "PLTLUND", "PL01": "PLTPOZN", "FI01": "PLTTMPR", "DE01": "LOGISTICS", "NO01": "LOGISTICS",
              "DK01": "LOGISTICS"}
    as_of = world.AS_OF_DATE
    for i, (day, comp, cat, amt_eur) in enumerate(specs):
        c = world.COMPANY[comp]
        local = c["currency"]
        foreign = local in ("SEK", "PLN") and cat[0] in ("raw_materials", "packaging") and rnd.random() < 0.25
        cur = "EUR" if foreign else local
        rate = None
        if foreign:
            rate = (D(1) / world.fx_d(local, day.year, day.month)).quantize(D("0.00001"))
        net = _q2(D(str(amt_eur)) if cur == "EUR" else D(str(amt_eur)) / world.fx_d(cur, day.year, day.month))
        vat = world.VAT_RATE[c["country"]]
        tax = _q2(net * vat)
        gross = net + tax
        terms = rnd.choice([30, 30, 45, 60])
        disc_avail = _q2(gross * D("0.02")) if terms == 30 and rnd.random() < 0.3 else D("0.00")
        due = day + datetime.timedelta(days=terms)
        # posted within the period: invoices received at month end are posted on the last day
        posting = min(day + datetime.timedelta(days=rnd.randint(1, 5)), world.month_end(day.year, day.month))
        blocked = rnd.random() < 0.04
        pay_day = None
        disc_taken = D("0.00")
        if not blocked:
            if disc_avail > 0 and rnd.random() < 0.7:
                pay_day = day + datetime.timedelta(days=rnd.randint(7, 10))
                disc_taken = disc_avail
            else:
                pay_day = due + datetime.timedelta(days=rnd.randint(-3, 6))
            if pay_day > as_of:
                pay_day = None
                disc_taken = D("0.00")
        status = "paid" if pay_day else ("on_hold" if blocked else ("approved" if (as_of - day).days > 10 else "posted"))
        supplier = reg.pick("procurement.supplier", rnd)
        created = engine.as_dt(posting) + datetime.timedelta(hours=9, minutes=rnd.randint(0, 300))
        fixed = {
            "ap_invoice_id": ipool[i], "company_code_id": reg.ctx["company_id"][comp],
            "cost_center_id": reg.ctx["cc"][cc_for[comp][cat[1]]], "gl_account_id": reg.ctx["gl"][(comp, cat[1])],
            "goods_receipt_id": reg.pick("procurement.goods_receipt", rnd) if cat[1] == "1430" else None,
            "profit_center_id": reg.ctx["pc"][pc_for[comp]],
            "purchase_order_id": reg.pick("procurement.purchase_order", rnd) if cat[1] == "1430" else None,
            "supplier_id": supplier, "supplier_invoice_id": reg.pick("procurement.supplier_invoice", rnd),
            "baseline_date": day, "clearing_document_number": None, "created_by_user": "SVCAPINV",
            "created_timestamp": created, "currency_code": cur, "discount_amount": disc_avail, "due_date": due,
            "early_payment_discount_taken": disc_taken, "exchange_rate": rate,
            "fiscal_period": posting.month, "fiscal_year": posting.year, "gross_amount": gross,
            "invoice_category": cat[0], "invoice_date": day,
            "invoice_description": "%s - %s" % (cat[0].replace("_", " ").capitalize(), c["short"]),
            "invoice_status": status, "match_status": ("matched" if cat[1] == "1430" and not blocked else
                                                       "variance_pending" if blocked else "override_approved"),
            "modified_by_user": "SVCAPINV", "net_amount": net, "payment_amount": (gross - disc_taken) if pay_day else None,
            "payment_block_code": "R" if blocked else None, "payment_date": pay_day,
            "payment_method": "ach" if comp in ("SE01", "NO01", "DK01", "FI01") else "wire_transfer",
            "payment_terms_code": "NT%02d" % terms, "posting_date": posting,
            "reference_document_number": "GR%08d" % (i + 1) if cat[1] == "1430" else None,
            "tax_amount": tax, "tax_code": "V1", "vendor_invoice_number": "INV-%d-%05d" % (day.year, (supplier * 7 + i) % 100000),
            "withholding_tax_amount": D("0.00"),
            "modified_timestamp": engine.as_dt(pay_day or posting) + datetime.timedelta(hours=15),
        }
        row = gen.row(i, rnd, fixed, anchor=created, country=c["country"])
        row["_meta"] = {"comp": comp, "cat": cat, "rate": rate, "cur": cur}
        invoices.append(row)
        if pay_day:
            pay_specs.append((pay_day, row))
    reg.rows[fq_i] = invoices
    pay_specs.sort(key=lambda x: (x[0], x[1]["ap_invoice_id"]))
    ppool = reg.alloc(fq_p, len(pay_specs))
    gen = reg.gen(fq_p)
    prows = []
    for i, (pd_, inv) in enumerate(pay_specs):
        meta = inv["_meta"]
        comp = meta["comp"]
        c = world.COMPANY[comp]
        local_rate = meta["rate"] or D(1)
        net_pay = inv["gross_amount"] - inv["early_payment_discount_taken"]
        ts = engine.as_dt(pd_) + datetime.timedelta(hours=5, minutes=prnd.randint(0, 59))
        released = prnd.random() < 0.03
        fixed = {
            "ap_payment_id": ppool[i], "ap_invoice_id": inv["ap_invoice_id"], "company_code_id": inv["company_code_id"],
            "cost_center_id": inv["cost_center_id"], "gl_account_id": reg.ctx["gl"][(comp, "1110")],
            "profit_center_id": inv["profit_center_id"], "supplier_id": inv["supplier_id"],
            "supplier_invoice_id": inv["supplier_invoice_id"], "approved_by": "Sara Nyström" if comp == "SE01" else "Payment approver %s" % comp,
            "approved_date": pd_ - datetime.timedelta(days=1), "bank_account_code": 550100 + world.COMPANIES.index(c),
            "clearing_date": pd_, "clearing_document_number": None, "created_timestamp": ts,
            "discount_amount": inv["early_payment_discount_taken"],
            "discount_due_date": inv["invoice_date"] + datetime.timedelta(days=10) if inv["discount_amount"] > 0 else None,
            "due_date": inv["due_date"], "exchange_rate": local_rate.quantize(D("0.000001")),
            "local_currency_amount": _q2(net_pay * local_rate), "local_currency_code": c["currency"],
            "modified_by": "SVC_F110", "modified_timestamp": ts + datetime.timedelta(hours=1),
            "net_payment_amount": net_pay, "payment_amount": inv["gross_amount"], "payment_approval_status": "approved",
            "payment_block_code": "R" if released else None,
            "payment_block_reason": "Price variance above tolerance - released after buyer confirmation" if released else None,
            "payment_block_released_by": "Sara Nyström" if released else None,
            "payment_block_released_date": (pd_ - datetime.timedelta(days=prnd.randint(1, 4))) if released else None,
            "payment_currency_code": inv["currency_code"], "payment_date": pd_,
            "payment_document_number": "15%08d" % (i + 1), "payment_method": "ACH" if inv["payment_method"] == "ach" else "wire_transfer",
            "payment_notes": ("Early payment discount taken" if inv["early_payment_discount_taken"] > 0 else
                              "Paid after price variance clarification" if released else None),
            "payment_reference_number": "PAYREF%08d" % (i + 1),
            "payment_run_code": "F110-%s-%s" % (comp, pd_.strftime("%Y%m%d")), "payment_status": "cleared",
            "payment_terms": "Net %d days" % int(inv["payment_terms_code"][2:]),
            "remittance_advice_sent_date": pd_, "remittance_advice_sent_flag": True, "created_by": "SVC_F110",
        }
        prow = gen.row(i, prnd, fixed, anchor=ts, country=c["country"])
        prow["_meta"] = {"inv": inv}
        prows.append(prow)
    reg.rows[fq_p] = prows


# --------------------------------------------------------------------------------------
# general ledger
# --------------------------------------------------------------------------------------

class _JE(object):
    """A journal entry under construction (amounts in transaction currency)."""

    def __init__(self, comp, posting, doc_type, header_text, ref, src, tcode, txn_cur=None, rate=None,
                 cc=None, pc=None, main_gl=None, func="ADMN", ba="CORP", doc_date=None, terms=None, baseline=None):
        self.comp = comp
        self.posting = posting
        self.doc_type = doc_type
        self.header_text = header_text
        self.ref = ref
        self.src = src
        self.tcode = tcode
        c = world.COMPANY[comp]
        self.local = c["currency"]
        self.txn_cur = txn_cur or self.local
        self.rate = rate          # local per 1 txn unit (None = same currency)
        self.cc, self.pc, self.main_gl = cc, pc, main_gl
        self.func, self.ba = func, ba
        self.doc_date = doc_date or posting
        self.terms, self.baseline = terms, baseline
        self.intercompany = False
        self.lines = []

    def add(self, gl, dc, amount, text, cc=None, pc=None, func=None, ba=None, tax=None, tax_code=None,
            customer=None, vendor=None, plant=None, due=None, assign=None, pkey=None, order=None, tp=None):
        if amount is None or amount == 0:
            return
        if amount < 0:
            amount, dc = -amount, ("C" if dc == "D" else "D")
            if tax is not None:
                tax = -tax
        self.lines.append({"gl": gl, "dc": dc, "amt": _q2(amount), "text": text, "cc": cc, "pc": pc,
                           "func": func or self.func, "ba": ba or self.ba, "tax": tax, "tax_code": tax_code,
                           "customer": customer, "vendor": vendor, "plant": plant, "due": due, "assign": assign,
                           "pkey": pkey, "order": order, "tp": tp})

    def balance_check(self):
        d = sum(l["amt"] for l in self.lines if l["dc"] == "D")
        c = sum(l["amt"] for l in self.lines if l["dc"] == "C")
        return d - c


def _general_ledger(reg):
    jes = []
    jes += _je_opening(reg)
    jes += _je_dtc(reg)
    jes += _je_b2b(reg)
    jes += _je_cogs(reg)
    jes += _je_production(reg)
    jes += _je_cash(reg)
    jes += _je_payroll_depreciation(reg)
    jes += _je_ap(reg)
    jes += _je_vat_settlement(reg, jes)
    jes = [je for je in jes if je.lines]
    jes.sort(key=lambda je: (je.posting, je.comp, je.doc_type, je.ref))
    _write_journal(reg, jes)


def _ym_iter():
    for (y, m) in world.MONTHS:
        yield y, m, world.month_end(y, m)


def _local(comp, eur, y, m):
    return _q2(D(str(eur)) / world.fx_d(world.COMPANY[comp]["currency"], y, m))


def _je_opening(reg):
    """Opening balances on 2024-01-01: bank (about 1.5 months of revenue), finished goods (one month
    of the plant's sales at standard cost) and raw/packaging materials (one month of consumption)."""
    out = []
    demand = plant_demand_eur(reg)
    for comp in [c["code"] for c in world.COMPANIES]:
        je = _JE(comp, world.TXN_START, "SA", "Opening balances 2024", "OPN%s2024" % comp, "SAP_FI", "FBB1",
                 main_gl="2990", func="ADMN")
        cash = monthly_revenue_eur(reg, comp, 2024) * D("1.5")
        fg = sum((demand.get((pl, 2024, 1), D(0)) for pl, c in PLANT_COMPANY.items() if c == comp), D(0))
        mat = sum((demand.get((pl, 2024, 1), D(0)) * cost_shares(pl)[0] for pl, c in PLANT_COMPANY.items() if c == comp), D(0))
        je.add("1110", "D", _local(comp, cash, 2024, 1), "Opening balance bank")
        je.add("1410", "D", _local(comp, fg, 2024, 1), "Opening balance finished goods")
        je.add("1430", "D", _local(comp, mat, 2024, 1), "Opening balance raw and packaging materials")
        je.add("2990", "C", sum((l["amt"] for l in je.lines), D(0)), "Opening balance equity")
        out.append(je)
    return out


def _je_dtc(reg):
    out = []
    agg = {}
    sku_of = reg.ctx["sku_by_id"]
    orders = dict((o["dtc_order_id"], o) for o in reg.rows["consumer.dtc_order"])
    for ln in reg.rows["consumer.dtc_order_line"]:
        o = orders[ln["dtc_order_id"]]
        if o["order_status"] not in ("shipped", "delivered", "returned"):
            continue
        comp = _company_of_id(reg, o["company_code_id"])
        d = o["order_date"]
        key = (comp, d.year, d.month)
        a = agg.setdefault(key, {"rev": {}, "vat": D(0), "ship": D(0), "ship_net": D(0), "ret": {}, "ret_vat": D(0),
                                 "orders": set()})
        brand = sku_of[ln["sku_id"]]["brand"]
        a["rev"][brand] = a["rev"].get(brand, D(0)) + ln["line_net_amount"]
        a["vat"] += ln["tax_amount"]
        if ln["is_returned"]:
            a["ret"][brand] = a["ret"].get(brand, D(0)) + ln["line_net_amount"]
            a["ret_vat"] += ln["tax_amount"]
        if o["dtc_order_id"] not in a["orders"]:
            a["orders"].add(o["dtc_order_id"])
            a["ship"] += o["shipping_amount"]
            # the shipping fee includes VAT: net to 3900, VAT to 2610
            a["ship_net"] += _q2(o["shipping_amount"] / (1 + _order_vat(o)))
    reg.ctx["dtc_agg"] = agg
    for (comp, y, m) in sorted(agg):
        a = agg[(comp, y, m)]
        me = world.month_end(y, m)
        tag = "%s%d%02d" % (comp, y, m)
        dtc_cc = reg.ctx["cc"][comp + "DTC"]
        je = _JE(comp, me, "DR", "DTC webshop sales %d-%02d" % (y, m), "DTC" + tag, "SFCC_DTC", "VF01",
                 cc=dtc_cc, pc=reg.ctx["pc"][BRAND_PC["BJORKO"][0]], main_gl="3010", func="SALE")
        psp = D(0)
        for b in _BRANDS:
            amt = _q2(a["rev"].get(b, D(0)))
            if amt:
                je.add("3010", "C", amt, "DTC webshop revenue %s %d-%02d" % (world.BRAND[b]["name"], y, m),
                       cc=dtc_cc, pc=reg.ctx["pc"][BRAND_PC[b][0]], ba=BUSINESS_AREA[b], tax_code="A1")
                psp += amt
        ship = _q2(a["ship"])
        ship_net = _q2(a["ship_net"])
        vat = _q2(a["vat"]) + (ship - ship_net)
        je.add("2610", "C", vat, "Output VAT on DTC sales and shipping %d-%02d" % (y, m), tax=vat, tax_code="A1")
        je.add("3900", "C", ship_net, "Shipping fees charged to consumers (net of VAT) %d-%02d" % (y, m), cc=dtc_cc,
               pc=reg.ctx["pc"]["LOGISTICS"])
        je.add("1240", "D", psp + vat + ship_net, "Payment service provider receivable %d-%02d" % (y, m),
               assign="PSP" + tag)
        out.append(je)
        if a["ret"]:
            jr = _JE(comp, me, "KN", "DTC returns and refunds %d-%02d" % (y, m), "RET" + tag, "SFCC_DTC", "VF01",
                     cc=dtc_cc, pc=reg.ctx["pc"][BRAND_PC["BJORKO"][0]], main_gl="3050", func="SALE")
            tot = D(0)
            for b in _BRANDS:
                amt = _q2(a["ret"].get(b, D(0)))
                if amt:
                    jr.add("3050", "D", amt, "DTC sales returns %s %d-%02d" % (world.BRAND[b]["name"], y, m),
                           cc=dtc_cc, pc=reg.ctx["pc"][BRAND_PC[b][0]], ba=BUSINESS_AREA[b], tax_code="A1")
                    tot += amt
            rv = _q2(a["ret_vat"])
            jr.add("2610", "D", rv, "Output VAT reversal on DTC returns %d-%02d" % (y, m), tax=rv, tax_code="A1")
            jr.add("1240", "C", tot + rv, "Refunds via payment service provider %d-%02d" % (y, m), assign="PSP" + tag)
            out.append(jr)
            a["refund"] = tot + rv
        else:
            a["refund"] = D(0)
        a["psp_in"] = psp + vat + ship_net
    return out


def _order_vat(o):
    """VAT rate of a DTC order (its lines carry tax = net x VAT; fall back to the market rate)."""
    net = o["subtotal_amount"] - o["discount_amount"]
    if net:
        return (o["tax_amount"] / net).quantize(D("0.01"))
    return world.VAT_RATE.get(o.get("ip_country_code"), D("0.25"))


def _company_of_id(reg, cid):
    inv = reg.ctx.setdefault("_comp_by_id", dict((v, k) for k, v in reg.ctx["company_id"].items()))
    return inv[cid]


def _je_b2b(reg):
    out = []
    agg = {}
    for inv in reg.rows["finance.ar_invoice"]:
        meta = inv["_meta"]
        t = meta["t"]
        d = inv["billing_date"]
        key = (t["company"], d.year, d.month)
        a = agg.setdefault(key, {"gross": {}, "td": {}, "tax": D(0), "total": D(0), "zero": D(0)})
        g = _brand_split(inv["gross_amount"], meta["brands"], meta["mix"])
        td = _brand_split(inv["trade_discount_amount"], meta["brands"], meta["mix"])
        for b in meta["brands"]:
            a["gross"][b] = a["gross"].get(b, D(0)) + g[b]
            a["td"][b] = a["td"].get(b, D(0)) + td[b]
        a["tax"] += inv["tax_amount"]
        a["total"] += inv["total_amount"]
    reg.ctx["b2b_agg"] = agg
    for (comp, y, m) in sorted(agg):
        a = agg[(comp, y, m)]
        me = world.month_end(y, m)
        tag = "%s%d%02d" % (comp, y, m)
        sales_cc = {"SE01": "SE01SAL", "NO01": "NO01SAL", "DK01": "DK01SAL", "FI01": "FI01SAL", "DE01": "DE01SALD",
                    "PL01": "PL01ADM"}[comp]
        cc = reg.ctx["cc"][sales_cc]
        je = _JE(comp, me, "DR", "Trade customer billing %d-%02d" % (y, m), "BIL" + tag, "SAP_SD", "VF01",
                 cc=cc, pc=reg.ctx["pc"][BRAND_PC["BJORKO"][1]], main_gl="3000", func="SALE")
        for b in _BRANDS:
            je.add("3000", "C", a["gross"].get(b, D(0)), "Revenue trade customers %s %d-%02d" % (world.BRAND[b]["name"], y, m),
                   cc=cc, pc=reg.ctx["pc"][BRAND_PC[b][1]], ba=BUSINESS_AREA[b], tax_code="A1")
        for b in _BRANDS:
            je.add("3040", "D", a["td"].get(b, D(0)), "Trade discounts %s %d-%02d" % (world.BRAND[b]["name"], y, m),
                   cc=cc, pc=reg.ctx["pc"][BRAND_PC[b][1]], ba=BUSINESS_AREA[b])
        je.add("2610", "C", a["tax"], "Output VAT on trade billing %d-%02d" % (y, m), tax=a["tax"], tax_code="A1")
        je.add("1210", "D", a["total"], "Trade receivables from billing %d-%02d" % (y, m),
               customer="CSUM" + comp, assign="BIL" + tag, pkey="01")
        out.append(je)
    return out


def _brand_cost_ratio():
    out = {}
    for b in _BRANDS:
        skus = [s for s in world.SKUS if s["brand"] == b]
        out[b] = sum(s["std_cost_eur"] for s in skus) / sum(s["list_eur"] for s in skus)
    return out


def _je_cogs(reg):
    """COGS at standard per company-month. Goods made in the company's own plants are issued from
    its finished-goods stock (1410); goods made by another group company are intercompany supplies
    at standard cost, settled through the group cash pool (1110) in the same month."""
    out = []
    plan = cogs_plan(reg)
    reg.ctx["ic_supply"] = {}
    for (comp, y, m) in sorted(plan):
        p = plan[(comp, y, m)]
        me = world.month_end(y, m)
        tag = "%s%d%02d" % (comp, y, m)
        je = _JE(comp, me, "WA", "Cost of goods sold %d-%02d" % (y, m), "COGS" + tag, "SAP_MM", "VL02N",
                 cc=None, pc=reg.ctx["pc"][BRAND_PC["BJORKO"][1]], main_gl="4000", func="PROD")
        by_brand_ch = {}
        by_producer = {}
        for (b, ch, plant), amt in p.items():
            by_brand_ch[(b, ch)] = by_brand_ch.get((b, ch), D(0)) + amt
            prod_comp = PLANT_COMPANY[plant]
            by_producer[prod_comp] = by_producer.get(prod_comp, D(0)) + amt
        for b in _BRANDS:
            for ch, idx in (("DTC", 0), ("B2B", 1)):
                je.add("4000", "D", by_brand_ch.get((b, ch), D(0)), "COGS %s %s %d-%02d" % (
                    "DTC" if ch == "DTC" else "trade", world.BRAND[b]["name"], y, m),
                    pc=reg.ctx["pc"][BRAND_PC[b][idx]], ba=BUSINESS_AREA[b])
        for prod_comp in sorted(by_producer):
            amt = _q2(by_producer[prod_comp])
            if prod_comp == comp:
                je.add("1410", "C", amt, "Finished goods issued %d-%02d" % (y, m))
            else:
                je.add("1110", "C", amt, "Intercompany supplies from %s at standard cost %d-%02d" % (prod_comp, y, m),
                       tp=prod_comp)
                eur = amt * world.fx_d(world.COMPANY[comp]["currency"], y, m)
                key = (prod_comp, y, m)
                reg.ctx["ic_supply"][key] = reg.ctx["ic_supply"].get(key, D(0)) + eur
        je.intercompany = len(by_producer) > 1 or comp not in by_producer
        out.append(je)
    # the producing companies: goods supplied to group companies leave their finished-goods stock
    for (prod_comp, y, m) in sorted(reg.ctx["ic_supply"]):
        eur = reg.ctx["ic_supply"][(prod_comp, y, m)]
        amt = _local(prod_comp, eur, y, m)
        je = _JE(prod_comp, world.month_end(y, m), "WA", "Goods supplied to group companies %d-%02d" % (y, m),
                 "ICS%s%d%02d" % (prod_comp, y, m), "SAP_MM", "VL02N", main_gl="1410", func="PROD")
        je.add("1110", "D", amt, "Intercompany receipts via group cash pool %d-%02d" % (y, m))
        je.add("1410", "C", amt, "Finished goods supplied to group companies at standard cost %d-%02d" % (y, m))
        je.intercompany = True
        out.append(je)
    return out


def _je_production(reg):
    """Monthly production settlement per plant: finished goods received at standard cost (1410), the
    production variance actual - planned (4100), and the consumed resources at actual cost: raw and
    packaging materials (1430), plant labour (2710), machinery depreciation (1290) and plant energy
    and maintenance (2410)."""
    out = []
    from .curated_manufacturing import PLANT_CC
    prod = production_cost_by_month(reg)
    reg.ctx["plant_accruals"] = {}
    for (plant, y, m) in sorted(prod):
        planned, actual = prod[(plant, y, m)]
        comp = world.PLANT[plant]["company"]
        me = world.month_end(y, m)
        pcode = PLANT_PC[plant]
        cc = reg.ctx["cc"][PLANT_CC[plant][0]]
        erp = world.PLANT[plant]["erp"]
        mat_s, lab_s, dep_s, _ = cost_shares(plant)
        planned, actual = _q2(planned), _q2(actual)
        mat, lab, dep = _q2(actual * mat_s), _q2(actual * lab_s), _q2(actual * dep_s)
        oh = actual - mat - lab - dep
        je = _JE(comp, me, "SA", "Production settlement %s %d-%02d" % (world.PLANT[plant]["name"], y, m),
                 "PRD%s%d%02d" % (plant, y, m), "SAP_PP", "KO88", cc=cc, pc=reg.ctx["pc"][pcode], main_gl="4100",
                 func="PROD", ba=BUSINESS_AREA[world.PLANT[plant]["brand"]])
        je.add("1410", "D", planned, "Finished goods received at standard cost %s %d-%02d" % (erp, y, m), plant=plant)
        je.add("4100", "D", actual - planned, "Production variance %s %d-%02d" % (erp, y, m), cc=cc,
               pc=reg.ctx["pc"][pcode], plant=plant)
        je.add("1430", "C", mat, "Raw and packaging materials consumed %s %d-%02d" % (erp, y, m), plant=plant)
        je.add("2710", "C", lab, "Plant labour %s %d-%02d" % (erp, y, m), cc=cc, plant=plant)
        je.add("1290", "C", dep, "Depreciation of plant machinery %s %d-%02d" % (erp, y, m), plant=plant)
        je.add("2410", "C", oh, "Plant energy and maintenance %s %d-%02d" % (erp, y, m), cc=cc, plant=plant)
        out.append(je)
        acc = reg.ctx["plant_accruals"].setdefault((comp, y, m), [D(0), D(0)])
        acc[0] += lab
        acc[1] += oh
    return out


def _je_cash(reg):
    out = []
    rec = {}
    for p in reg.rows["finance.ar_payment"]:
        d = p["payment_date"]
        comp = p["company_code"]
        rec[(comp, d.year, d.month)] = rec.get((comp, d.year, d.month), D(0)) + p["local_currency_amount"]
    for (comp, y, m) in sorted(rec):
        me = world.month_end(y, m)
        tag = "%s%d%02d" % (comp, y, m)
        je = _JE(comp, me, "DZ", "Customer payments received %d-%02d" % (y, m), "CSH" + tag, "SAP_FI", "FEBAN",
                 main_gl="1110", func="ADMN")
        je.add("1110", "D", rec[(comp, y, m)], "Bank receipts trade customers %d-%02d" % (y, m))
        je.add("1210", "C", rec[(comp, y, m)], "Clearing trade receivables %d-%02d" % (y, m),
               customer="CSUM" + comp, pkey="15")
        out.append(je)
    for (comp, y, m), a in sorted(reg.ctx["dtc_agg"].items()):
        me = world.month_end(y, m)
        tag = "%s%d%02d" % (comp, y, m)
        net_cash = a["psp_in"] - a["refund"]
        je = _JE(comp, me, "DZ", "PSP settlements %d-%02d" % (y, m), "PSP" + tag, "SAP_FI", "FEBAN", main_gl="1110")
        je.add("1110", "D", net_cash, "Payment service provider payouts %d-%02d" % (y, m))
        je.add("1240", "C", net_cash, "Clearing PSP receivable %d-%02d" % (y, m), assign="PSP" + tag)
        out.append(je)
    return out


# non-plant payroll split over the company's cost centres (relative weights)
_PAYROLL_WEIGHTS = {
    "SE01": [("SE01MGMT", 2.0), ("SE01FIN", 1.5), ("SE01IT", 1.2), ("SE01MKBJ", 0.6), ("SE01MKKK", 0.6),
             ("SE01MKMC", 0.6), ("SE01DTC", 1.0), ("SE01SAL", 2.2), ("SE01CS", 0.9), ("SE01LJKG", 1.6)],
    "NO01": [("NO01SAL", 2.0), ("NO01DTC", 0.6), ("NO01LOSL", 1.2), ("NO01ADM", 0.8)],
    "DK01": [("DK01SAL", 2.0), ("DK01DTC", 0.6), ("DK01LODE", 1.2), ("DK01ADM", 0.8)],
    "FI01": [("FI01SAL", 2.0), ("FI01DTC", 0.6), ("FI01LVAN", 1.2)],
    "DE01": [("DE01SALD", 2.0), ("DE01SALB", 0.8), ("DE01DTC", 0.6), ("DE01LHAM", 1.2), ("DE01CRM", 0.5),
             ("DE01ADM", 0.8)],
    "PL01": [("PL01ADM", 1.5), ("PL01PROC", 0.8), ("PL01WPOZ", 1.0)],
}
_JUNE_HOLIDAY_PAY = D("1.40")   # holiday pay in June; the other months share the rest of the year


def _je_payroll_depreciation(reg):
    """Monthly payroll of non-plant staff (5000 -> 2710), the payment of all payroll liabilities and
    plant overheads of the month (2710/2410 -> 1110) and depreciation of non-plant assets (7000)."""
    out = []
    rnd = reg.rng("finance.journal_entry", "payroll")
    accr = reg.ctx.get("plant_accruals", {})
    for comp in sorted(_PAYROLL_WEIGHTS):
        weights = _PAYROLL_WEIGHTS[comp]
        tw = sum(w for _, w in weights)
        for (y, m) in world.MONTHS:
            me = world.month_end(y, m)
            tag = "%s%d%02d" % (comp, y, m)
            rev = monthly_revenue_eur(reg, comp, y)
            season = _JUNE_HOLIDAY_PAY if m == 6 else (12 - _JUNE_HOLIDAY_PAY) / 11
            payroll_eur = rev * D(OPEX_RATIO[comp]["5000"]) * season
            je = _JE(comp, me - datetime.timedelta(days=2), "SA", "Payroll %d-%02d" % (y, m), "PAY" + tag, "SAP_HR",
                     "PCPOST", main_gl="5000", func="ADMN")
            tot = D(0)
            for cc_code, w in weights:
                eur = payroll_eur * D(str(w / tw)) * D(str(round(rnd.uniform(0.98, 1.02), 4)))
                amt = _local(comp, eur, y, m)
                cc_row = [c for c in COST_CENTERS if c[0] == cc_code][0]
                je.add("5000", "D", amt, "Salaries %s %d-%02d" % (cc_row[1], y, m), cc=reg.ctx["cc"][cc_code],
                       pc=reg.ctx["pc"][cc_row[6]], func=cc_row[5])
                tot += amt
            je.add("2710", "C", tot, "Net salaries and social charges payable %d-%02d" % (y, m))
            out.append(je)
            plant_lab, plant_oh = accr.get((comp, y, m), (D(0), D(0)))
            jp = _JE(comp, me, "SA", "Payroll and plant overheads paid %d-%02d" % (y, m), "PPY" + tag, "SAP_FI",
                     "F110", main_gl="1110", func="ADMN")
            jp.add("2710", "D", tot + plant_lab, "Salaries, social charges and plant labour paid %d-%02d" % (y, m))
            jp.add("2410", "D", plant_oh, "Plant energy and maintenance paid %d-%02d" % (y, m))
            jp.add("1110", "C", tot + plant_lab + plant_oh, "Bank payments payroll and plant overheads %d-%02d" % (y, m))
            out.append(jp)
            dep = _local(comp, rev * D(OPEX_RATIO[comp]["7000"]), y, m)
            jd = _JE(comp, me, "AB", "Depreciation run %d-%02d" % (y, m), "DEP" + tag, "SAP_AA", "AFAB",
                     main_gl="7000", func="ADMN")
            jd.add("7000", "D", dep, "Depreciation office, IT and warehouse equipment %d-%02d" % (y, m))
            jd.add("1290", "C", dep, "Accumulated depreciation %d-%02d" % (y, m))
            out.append(jd)
    return out


def _je_ap(reg):
    out = []
    for inv in reg.rows["finance.ap_invoice"]:
        meta = inv["_meta"]
        comp = meta["comp"]
        cat = meta["cat"]
        vendor = "V%07d" % (inv["supplier_id"] % 10000000)
        je = _JE(comp, inv["posting_date"], "KR", "Vendor invoice %s" % inv["vendor_invoice_number"],
                 "AP%08d" % (inv["ap_invoice_id"] % 100000000), "SAP_MM", "MIRO", txn_cur=inv["currency_code"],
                 rate=meta["rate"], cc=inv["cost_center_id"], pc=inv["profit_center_id"], main_gl=cat[1],
                 func="PURC" if cat[1] == "1430" else "ADMN", doc_date=inv["invoice_date"], terms=inv["payment_terms_code"],
                 baseline=inv["baseline_date"])
        je.add(cat[1], "D", inv["net_amount"], "%s %s" % (cat[0].replace("_", " ").capitalize(), inv["vendor_invoice_number"]),
               cc=inv["cost_center_id"] if cat[1] != "1430" else None, pc=inv["profit_center_id"],
               order=("IO%s%04d" % (comp, inv["invoice_date"].year * 10 % 10000 + inv["invoice_date"].month)) if cat[1] == "6100" else None)
        je.add("1510", "D", inv["tax_amount"], "Input VAT %s" % inv["vendor_invoice_number"], tax=inv["tax_amount"], tax_code="V1")
        je.add("2110", "C", inv["gross_amount"], "Vendor liability %s" % inv["vendor_invoice_number"], vendor=vendor,
               due=inv["due_date"], pkey="31")
        je.ap_invoice = inv
        out.append(je)
    for pay in reg.rows["finance.ap_payment"]:
        inv = pay["_meta"]["inv"]
        meta = inv["_meta"]
        comp = meta["comp"]
        vendor = "V%07d" % (inv["supplier_id"] % 10000000)
        je = _JE(comp, pay["payment_date"], "KZ", "Outgoing payment %s" % pay["payment_run_code"],
                 "PY%08d" % (pay["ap_payment_id"] % 100000000), "SAP_FI", "F110", txn_cur=inv["currency_code"],
                 rate=meta["rate"], main_gl="2110", func="ADMN")
        je.add("2110", "D", pay["payment_amount"], "Clear vendor liability %s" % inv["vendor_invoice_number"],
               vendor=vendor, pkey="25")
        je.add("1110", "C", pay["net_payment_amount"], "Bank payment %s" % pay["payment_reference_number"])
        je.add(meta["cat"][1], "C", pay["discount_amount"], "Early payment discount %s" % inv["vendor_invoice_number"])
        je.ap_payment = pay
        out.append(je)
    return out


def _je_vat_settlement(reg, jes):
    """Quarterly VAT returns: output VAT (2610) less input VAT (1510) of the quarter is paid to (or
    refunded by) the tax authority at the end of the following month. Q3 2026 is still payable on
    2026-09-30."""
    vat = {}
    for je in jes:
        q = (je.posting.year, (je.posting.month - 1) // 3 + 1)
        for ln in je.lines:
            if ln["gl"] not in ("2610", "1510"):
                continue
            loc = _q2(ln["amt"] * je.rate) if je.rate else ln["amt"]
            sign = 1 if ln["dc"] == ("C" if ln["gl"] == "2610" else "D") else -1
            a = vat.setdefault((je.comp, q), {"2610": D(0), "1510": D(0)})
            a[ln["gl"]] += sign * loc
    out = []
    for (comp, (y, qn)), a in sorted(vat.items()):
        m_after = qn * 3 + 1
        yy = y + (1 if m_after > 12 else 0)
        mm = m_after - 12 if m_after > 12 else m_after
        posting = world.month_end(yy, mm)
        if posting > world.TXN_END:
            continue
        je = _JE(comp, posting, "SA", "VAT return %d Q%d" % (y, qn), "VAT%s%dQ%d" % (comp, y, qn), "SAP_FI", "FB41",
                 main_gl="2610", func="ADMN")
        je.add("2610", "D", a["2610"], "Output VAT %d Q%d" % (y, qn))
        je.add("1510", "C", a["1510"], "Input VAT %d Q%d" % (y, qn))
        je.add("1110", "C", a["2610"] - a["1510"], "VAT paid to the tax authority %d Q%d" % (y, qn))
        out.append(je)
    return out


_DOC_PREFIX = {"DR": "18", "KN": "17", "WA": "49", "SA": "10", "DZ": "14", "AB": "11", "KR": "51", "KZ": "15"}
_POST_KEY = {"D": "40", "C": "50"}


def _write_journal(reg, jes):
    fq_h, fq_l = "finance.journal_entry", "finance.journal_entry_line"
    hpool = reg.alloc(fq_h, len(jes))
    nlines = sum(len(je.lines) for je in jes)
    lpool = reg.alloc(fq_l, nlines)
    hgen, lgen = reg.gen(fq_h), reg.gen(fq_l)
    hrnd, lrnd = reg.rng(fq_h), reg.rng(fq_l)
    counters = {}
    hrows, lrows = [], []
    k = 0
    docnos = []
    kz_of_invoice = {}
    for je in jes:
        prefix = _DOC_PREFIX[je.doc_type]
        counters[prefix] = counters.get(prefix, 0) + 1
        docnos.append("%s%08d" % (prefix, counters[prefix]))
        if hasattr(je, "ap_payment"):
            kz_of_invoice[je.ap_payment["ap_invoice_id"]] = (docnos[-1], je.ap_payment["payment_date"])
    for i, je in enumerate(jes):
        docno = docnos[i]
        y, m = je.posting.year, je.posting.month
        g_rate = world.fx_d(je.local, y, m)
        # amounts per line in local and group currency, then fix rounding to keep balance
        for ln in je.lines:
            ln["loc"] = _q2(ln["amt"] * je.rate) if je.rate else ln["amt"]
            ln["grp"] = _q2(ln["loc"] * g_rate)
        for field in ("loc", "grp"):
            diff = sum(l[field] for l in je.lines if l["dc"] == "D") - sum(l[field] for l in je.lines if l["dc"] == "C")
            if diff:
                tgt = max((l for l in je.lines if l["dc"] == "C"), key=lambda l: l[field])
                tgt[field] += diff
        assert je.balance_check() == 0, (je.ref, je.balance_check())
        posted_ts = engine.as_dt(je.posting) + datetime.timedelta(hours=19, minutes=hrnd.randint(0, 50))
        if je.doc_type in ("KR", "KZ"):
            posted_ts = engine.as_dt(je.posting) + datetime.timedelta(hours=10, minutes=hrnd.randint(0, 300))
        entry = je.posting if je.doc_type in ("KR", "KZ") else je.posting + datetime.timedelta(days=hrnd.randint(1, 4))
        created_ts = engine.as_dt(entry) + datetime.timedelta(hours=8, minutes=hrnd.randint(0, 400))
        if created_ts > world.EXTRACT_TS:
            created_ts = world.EXTRACT_TS - datetime.timedelta(hours=2)
        main_gl = je.main_gl or je.lines[0]["gl"]
        clearing, clearing_doc = None, None
        if hasattr(je, "ap_invoice") and je.ap_invoice["ap_invoice_id"] in kz_of_invoice:
            clearing_doc, clearing = kz_of_invoice[je.ap_invoice["ap_invoice_id"]]
            je.ap_invoice["clearing_document_number"] = clearing_doc
        hid = hpool[i]
        fixed = {
            "journal_entry_id": hid, "company_code_id": reg.ctx["company_id"][je.comp],
            "cost_center_id": je.cc if je.cc else None, "gl_account_id": reg.ctx["gl"][(je.comp, main_gl)],
            "ledger_id": reg.ctx["ledger"][je.comp], "product_category_id": None, "profit_center_id": je.pc,
            "approval_timestamp": created_ts + datetime.timedelta(hours=hrnd.randint(1, 20)),
            "baseline_payment_date": je.baseline, "batch_input_session": ("%s-%d%02d" % (je.src, y, m)) if je.doc_type not in ("KR", "KZ") else None,
            "business_area_code": je.ba, "clearing_date": clearing, "clearing_document_number": clearing_doc,
            "controlling_area": "FJ01", "created_timestamp": created_ts, "currency_code": je.txn_cur,
            "document_date": je.doc_date, "document_number": docno, "document_type": je.doc_type,
            "entry_date": entry, "exchange_rate": je.rate, "exchange_rate_type": "M", "fiscal_period": m,
            "fiscal_year": y, "functional_area_code": je.func[:4], "header_text": je.header_text,
            "intercompany_indicator": je.intercompany, "ledger_group": "0L", "local_currency_code": je.local,
            "modified_timestamp": created_ts + datetime.timedelta(hours=hrnd.randint(1, 30)),
            "payment_terms_code": je.terms, "posting_date": je.posting, "posting_status": "posted",
            "reference_document_number": je.ref, "reversal_indicator": False, "reversal_reason_code": None,
            "reversed_document_number": None, "source_system_code": je.src, "sox_control_flag": je.doc_type in ("DR", "WA", "KR"),
            "tax_reporting_date": je.posting, "transaction_code": je.tcode,
            "trading_partner_company_code": (sorted(set(l["tp"] for l in je.lines if l["tp"]))[0]
                                             if any(l["tp"] for l in je.lines) else None),
        }
        if fixed["approval_timestamp"] > world.EXTRACT_TS:
            fixed["approval_timestamp"] = world.EXTRACT_TS
        if fixed["modified_timestamp"] > world.EXTRACT_TS:
            fixed["modified_timestamp"] = world.EXTRACT_TS
        hrows.append(hgen.row(i, hrnd, fixed, anchor=created_ts, country=world.COMPANY[je.comp]["country"]))
        if hasattr(je, "ap_payment"):
            je.ap_payment["clearing_document_number"] = docno
        for n, ln in enumerate(je.lines, start=1):
            gl = ln["gl"]
            pkey = ln["pkey"] or _POST_KEY[ln["dc"]]
            lfixed = {
                "journal_entry_line_id": lpool[k], "company_code_id": reg.ctx["company_id"][je.comp],
                "cost_center_id": ln["cc"], "gl_account_id": reg.ctx["gl"][(je.comp, gl)], "journal_entry_id": hid,
                "profit_center_id": ln["pc"], "amount_company_code_currency": ln["loc"],
                "amount_group_currency": ln["grp"], "amount_transaction_currency": ln["amt"],
                "assignment_field": ln["assign"] or (je.ref if (ln["customer"] or ln["vendor"]) else None),
                "baseline_payment_date": je.baseline if ln["due"] else None,
                "business_area_code": ln["ba"],
                "clearing_date": clearing if (ln["vendor"] and ln["dc"] == "C") else (je.posting if ln["vendor"] else None),
                "clearing_document_number": clearing_doc if (ln["vendor"] and ln["dc"] == "C") else (docno if ln["vendor"] else None),
                "company_code_currency_code": je.local, "customer_account_number": ln["customer"],
                "debit_credit_indicator": ln["dc"], "due_date": ln["due"], "exchange_rate": g_rate.quantize(D("0.000001")),
                "functional_area_code": ln["func"], "group_currency_code": "EUR", "internal_order_number": ln["order"],
                "line_item_number": n, "material_number": None, "payment_terms_code": je.terms if ln["due"] else None,
                "plant_code": ln["plant"], "posting_key": pkey, "quantity": None,
                "reference_document_number": je.ref, "reversal_indicator": False, "reversed_document_number": None,
                "special_gl_indicator": None, "storage_location_code": None, "tax_amount": ln["tax"],
                "tax_code": ln["tax_code"], "text_description": ln["text"], "trading_partner_code": ln["tp"],
                "transaction_currency_code": je.txn_cur, "unit_of_measure": None,
                "value_date": (je.posting + datetime.timedelta(days=1)) if gl in ("1110",) else None,
                "vendor_account_number": ln["vendor"], "wbs_element_code": None,
            }
            lrows.append(lgen.row(k, lrnd, lfixed, anchor=created_ts, country=world.COMPANY[je.comp]["country"]))
            k += 1
    reg.rows[fq_h] = hrows
    reg.rows[fq_l] = lrows
    for inv in reg.rows["finance.ap_invoice"]:
        inv.pop("_kz_doc", None)
        inv.pop("_meta", None)
    for p in reg.rows["finance.ap_payment"]:
        p.pop("_meta", None)
    for inv in reg.rows["finance.ar_invoice"]:
        inv.pop("_meta", None)
