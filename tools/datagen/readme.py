"""Render ``bootcamp/data/README.md`` (variant ``bootcamp``: the 36 tables of consumer, finance and
manufacturing) and ``full_model/data/README.md`` (variant ``full``: all 116 tables) from the world definition, the manifest, the data-quality log
and the KPI snapshot computed by ``tools/verify_data.py``. Deterministic: no timestamps.
"""
from . import engine, world

SIZE_GUARD_MB = 39.5

_ISSUE_TITLES = {
    "exact_duplicate_rows": "Exact duplicate rows (re-delivered extract)",
    "updated_duplicate_rows": "Updated duplicates (same PK, older version)",
    "enum_case_whitespace": "Enum values with stray whitespace / wrong case",
    "date_format_ddmmyyyy": "Dates in dd/MM/yyyy",
    "boolean_mixed_format": "Booleans as Y/N or 1/0",
    "empty_primary_key": "Rows with an empty primary key",
    "negative_quantity_lines": "Negative quantity_ordered",
    "guest_checkout_orphans": "Guest checkout: shopper_id not in consumer.shopper",
    "guest_checkout_lines": "Guest checkout lines: shopper_id NULL",
}


def _fmt_int(n):
    return "{:,}".format(int(n)).replace(",", " ")


def _table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def render(manifest, report, seed, variant="full"):
    k = report.get("kpis") or {}
    boot = variant == "bootcamp"
    n_files = sum(len(t) for t in manifest.values())
    L = []
    a = L.append
    if boot:
        a("# Fjällmark Consumer Goods AB - synthetic data for the Genie bootcamp")
    else:
        a("# Fjällmark Consumer Goods AB - synthetic data, complete industry model")
    a("")
    a("> **All data in this folder is synthetic and fictional.** Fjällmark Consumer Goods AB, its brands, plants, "
      "retail customers and people do not exist. Names are random combinations, e-mail addresses use the reserved "
      "`example.com` domain, phone numbers contain an obviously fake `000` block, IP addresses come from the "
      "documentation ranges (RFC 5737) and retailer names are invented. Any resemblance to real companies or "
      "persons is coincidental.")
    a("")
    a("The tables follow the **Lakehouse Industry Data Model - Consumer Goods v2 (MVM)** "
      "(`tools/model/consumer_goods_v2_mvm.json` at the repository root; Copyright Databricks, Inc., Databricks "
      "license - see `LICENSE.md` and `NOTICE.md` in this bundle folder, verbatim copies of `tools/model/`): exact "
      "column names and column order of the model, values that follow its value formats. **Notice:** the CSV files "
      "and `manifest.json` are derived from that model and modified for the Fjällmark Genie bootcamp (synthetic "
      "values, a subset of its tables per folder, deliberate data-quality issues). The generator "
      "is `tools/generate_data.py` (standard library only, deterministic) and the checker is `tools/verify_data.py`.")
    a("")
    if boot:
        a("This folder holds the **%d tables of the three bootcamp domains** - consumer, finance and manufacturing - "
          "the data behind the bootcamp's Genie Agent. The complete model (10 domains, 116 tables) is in "
          "`full_model/` at the repository root; its setup notebook reads these files from here (every CSV is "
          "stored only once)." % n_files)
    else:
        a("The complete model has 10 domains and 116 tables. Every CSV is stored **once**: the three bootcamp "
          "domains (consumer, finance, manufacturing - 36 tables) live in `bootcamp/data/<domain>/`, the other "
          "7 domains (80 tables) here in `full_model/data/<domain>/`. `full_model/notebooks/01_setup_catalog.py` "
          "reads both folders.")
    a("")
    a("## Contents")
    a("")
    if boot:
        a("* `<domain>/<table>.csv` - one file per table (%d files). `notebooks/01_setup_catalog.py` copies them to "
          "`/Volumes/<catalog>/landing/raw_files/<domain>/<table>/<table>.csv` (one folder per table for Auto "
          "Loader)." % n_files)
    else:
        a("* `<domain>/<table>.csv` - one file per table of the 7 non-bootcamp domains (80 files); the 36 bootcamp "
          "tables are in `bootcamp/data/`. `notebooks/01_setup_catalog.py` copies all 116 files to "
          "`/Volumes/<catalog>/landing/raw_files/<domain>/<table>/<table>.csv` (one folder per table for Auto "
          "Loader).")
    a("* `manifest.json` - per domain and table (%s): `rows` (CSV data rows), `clean_rows` (rows before data-quality "
      "injection = rows after the silver rules), `scope` (`bootcamp` = consumer/finance/manufacturing, the Genie "
      "scope; `full` = the other 7 domains), `primary_key`, `dedup_order_column`, `file` (path of the CSV relative "
      "to the repository root), `bytes` and `dq_issues`." % ("the %d bootcamp tables" % n_files if boot else
                                                              "all 116 tables"))
    a("* `README.md` - this file.")
    a("")
    a("## CSV format")
    a("")
    a("* UTF-8, comma separated, `\\n` line endings, header row = model column names in model order.")
    a("* RFC-4180 quoting: only fields that contain a comma are quoted. Values never contain double quotes, "
      "backslashes or line breaks, so Spark's CSV reader (`read_files(..., format => 'csv', header => true)`) and "
      "any RFC-4180 reader agree. Read every column as STRING in bronze.")
    a("* Empty field = NULL. Dates `yyyy-MM-dd`, timestamps `yyyy-MM-dd HH:mm:ss` (no time zone; local plant/market "
      "time), decimals with `.` and exactly the declared scale, booleans `true`/`false` (except the documented "
      "Y/N and 1/0 mixes).")
    a("* Surrogate keys are BIGINT: `table_index * 100000 + n` where `table_index` is the 1-based position of the "
      "table in the model (product.sku = 1, ..., finance.company_code = 116). A key therefore identifies its table, "
      "e.g. `2500042` is a consumer.shopper. Guest-checkout shopper ids start at %d." % (engine.GUEST_ID_BASE + 1)
      + (" Foreign keys into domains that are not part of the bootcamp (e.g. `sku_id` -> product.sku, "
         "`trade_account_id` -> sales.trade_account) keep their values, but the referenced tables are only built "
         "by the full model." if boot else ""))
    a("")
    a("## The company in brief")
    a("")
    a("Fjällmark Consumer Goods AB (HQ Stockholm) makes Nordic packaged foods, beverages and personal care. Group "
      "reporting currency is **EUR**; fiscal year = calendar year, fiscal period = month. Transactions run "
      "**2024-01-01 .. 2026-09-30**; balances, AR/AP status and aging are a period-end snapshot as of **%s**; the "
      "extract is dated **%s**." % (world.AS_OF_DATE, world.EXTRACT_DATE))
    a("")
    a(_table(["company code", "legal entity", "country", "currency", "role"],
             [(c["code"], c["name"], c["country"], c["currency"], c["role"]) for c in world.COMPANIES]))
    a("")
    a("FX (EUR per unit, monthly average with +-2 %% drift; base): SEK %.3f, NOK %.3f, DKK %.3f, PLN %.3f, EUR 1. "
      "The monthly rate used by finance is in `journal_entry_line.exchange_rate` (EUR per unit of the company-code "
      "currency)." % (world.FX_BASE["SEK"], world.FX_BASE["NOK"], world.FX_BASE["DKK"], world.FX_BASE["PLN"]))
    a("")
    if boot:
        a("**Brands**: Björkö Pantry (FOOD - crispbread, granola, porridge, jams, muesli bars), Kallkälla (BEVERAGE - "
          "sparkling water, juices, oat drinks from April 2025) and Mjuk Care (PERSONAL_CARE - shampoo, conditioner, "
          "body wash, toothpaste, hand cream, deodorant), %d SKUs. The product domain is not part of the bootcamp; "
          "the product attributes Genie needs are carried in the bootcamp tables: `consumer.dtc_order_line` "
          "(`product_name`, `brand_code`, `product_category_code`, `gtin`), `finance.profit_center` (`brand_code`, "
          "`product_category_code`; one profit centre per brand and channel) and `finance.standard_cost` "
          "(`cost_estimate_number` contains the SKU code)." % len(world.SKUS))
    else:
        a("**Brands** (product.brand): Björkö Pantry (FOOD - crispbread, granola, porridge, jams, muesli bars), "
          "Kallkälla (BEVERAGE - sparkling water, juices, oat drinks from April 2025) and Mjuk Care (PERSONAL_CARE - "
          "shampoo, conditioner, body wash, toothpaste, hand cream, deodorant). %d SKUs with valid GTIN-13 codes "
          "(product.sku), a two-level category tree (product.product_category: 3 + %d sub-categories)."
          % (len(world.SKUS), len(world.SUBCATEGORIES)))
    a("")
    a("**Plants and lines** (manufacturing): `plant_code` is the 4-character SAP-style code required by the model "
      "regex; the human-readable site tag is in `erp_plant_code` / `mes_asset_tag`.")
    a("")
    rows = []
    for p in world.PLANTS:
        lines = [ln for ln in world.LINES if ln[1] == p["code"]]
        rows.append((p["code"], p["erp"], p["name"], p["company"], len(lines),
                     ", ".join("%s (%s)" % (ln[0], ln[2]) for ln in lines)))
    a(_table(["plant_code", "erp_plant_code", "facility", "company", "lines", "line_code (mes_asset_tag)"], rows))
    a("")
    if not boot:
        a("**Distribution centres** (distribution.distribution_facility): " + ", ".join(
            "%s %s (%s)" % (d["code"], d["city"], d["company"]) for d in world.DCS) + ".")
        a("")
    tiers = [t for t in world.TIERS if t["rank"] > 1]
    a("**DTC webshop** `%s` in SWE, NOR, DNK, FIN, DEU and NLD (ISO 3166 alpha-3); order currency = market "
      "currency (SEK, NOK, DKK, EUR). Loyalty programme **Fjällmark Friends** with tiers Bronze, Silver, Gold and "
      "Platinum (points multiplier 1.0 / 1.25 / 1.5 / 2.0, member discount 0 / 2 / 5 / 8 %%, free shipping for "
      "Gold and Platinum; 1 point per EUR of net merchandise value x multiplier, 100 points = 1 EUR, welcome "
      "bonus 100, birthday bonus 50 for members who ordered in the last 12 months). A member keeps the tier with "
      "%s (lifetime points or qualifying spend excl. VAT in the last 12 months, `loyalty_tier.required_points` / "
      "`required_spend_usd` - the amounts are EUR); the annual review moves members below the requirement down "
      "(`loyalty_account.previous_tier`). Points pay for up to 30 %% of a basket (`dtc_order."
      "loyalty_points_redeemed`) or for gift-card rewards; about a fifth of the earned points are redeemed and "
      "unused points expire 12 months after the last activity. Subscriptions (one box SKU per delivery, 4-10 "
      "units or 1-3 crates/trays, ~25-40 EUR incl. VAT): granola boxes, oat refills, oat-drink crates, sparkling "
      "water trays, Mjuk Care refills." % (world.WEBSHOP, ", ".join(
          "%s %d points or %s EUR" % (t["name"], t["required_points"], t["required_spend"]) for t in tiers)))
    a("")
    a("**B2B**: %d fictional retail, wholesale and foodservice customers (sales.trade_account%s), e.g. NorthCart "
      "Retail, Vasa Grocers, Fjordhandel, Baltic FreshMarket, Kaleva Kauppa, Alpina Drogerie; `acv_total` and "
      "`credit_limit_amount` are in the account's currency. B2B is about 99.5 %% of net revenue and grows ~5 %% "
      "a year. The **webshop is a small, fast-growing channel**: about 0.5 %% of group net revenue, growing "
      "~18 %% a year in value (order count ~15 %%, average order value slightly up after the oat-drink launch); "
      "about a third of webshop orders are subscription deliveries. Seasonality: Q4 Christmas peak (DTC orders "
      "+35 %%, food), beverages peak in June-August, personal care flat."
      % (len(world.TRADE), "; full model only - in the bootcamp the receivables carry `trade_account_id`" if boot else ""))
    a("")
    a("## Business definitions and conventions")
    a("")
    a("* **General ledger** (finance.journal_entry / journal_entry_line): amounts are stored as **positive** "
      "values; the direction is `debit_credit_indicator` (`D`/`C`). Every journal entry balances (sum D = sum C) "
      "in transaction, company-code and group currency. `amount_group_currency` = company-code amount x monthly FX "
      "(EUR). Chart of accounts: 26 accounts per company code with shared numbering (finance.gl_account, "
      "`account_number`, `account_group`).")
    a("* **Net Revenue (authoritative)** = sum over GL accounts with `account_group = 'REVENUE'` (3000 Revenue - "
      "trade customers, 3010 Revenue - DTC webshop, 3040 Trade discounts and rebates, 3050 Sales returns - DTC) of "
      "credit minus debit in **group currency EUR**. It excludes VAT (2610) and shipping fees (3900, "
      "`OTHER_INCOME`) and is after trade discounts and returns.")
    a("")
    a("  ```sql")
    a("  SELECT je.fiscal_year, je.fiscal_period, cc.code AS company_code,")
    a("         SUM(CASE WHEN l.debit_credit_indicator = 'C' THEN l.amount_group_currency")
    a("                  ELSE -l.amount_group_currency END) AS net_revenue_eur")
    a("  FROM finance.journal_entry_line l")
    a("  JOIN finance.journal_entry je ON je.journal_entry_id = l.journal_entry_id")
    a("  JOIN finance.gl_account ga ON ga.gl_account_id = l.gl_account_id")
    a("  JOIN finance.company_code cc ON cc.company_code_id = l.company_code_id")
    a("  WHERE ga.account_group = 'REVENUE'")
    a("  GROUP BY ALL")
    a("  ```")
    a("")
    a("* **COGS** = account group `COGS` (4000 standard COGS, 4100 production variances); Gross Margin = Net Revenue - "
      "COGS. Operating expenses: 5000 salaries (sales, marketing, DTC, logistics and administration staff), 6100 "
      "marketing, 6300 freight and logistics, 6400 rent, utilities, maintenance and IT, 7000 depreciation of "
      "office/IT/warehouse assets. Plant labour, plant machinery depreciation and plant energy/maintenance are "
      "product costs: they are part of the standard cost and reach the P&L through COGS. EBIT = Net Revenue + 3900 "
      "- COGS - opex is about 10-13 % for the group and positive for every company code.")
    a("* **Document types** (monthly summary documents per company code unless noted): DR billing / DTC sales, "
      "KN DTC returns, WA cost of goods sold and goods supplied to group companies, DZ customer and PSP receipts, "
      "SA payroll, payroll and plant-overhead payments, production settlement per plant, quarterly VAT returns and "
      "the 2024-01-01 opening balances, AB depreciation; AP invoices (KR) and AP payments (KZ) post one document "
      "each.")
    a("* **Inventory and intercompany**: each plant settles its completed production orders monthly (SA, "
      "`reference_document_number` PRD<plant><yyyymm>): finished goods received at standard cost (1410), "
      "production variance actual - planned (4100), raw and packaging materials consumed (1430), plant labour "
      "(2710), machinery depreciation (1290) and plant energy/maintenance (2410). Plants produce one month ahead of "
      "demand, so finished goods stay at about one month of sales. Goods made by another group company are "
      "intercompany supplies at standard cost (no margin), settled through the group cash pool in the same month "
      "(1110 lines with `trading_partner_code`, `intercompany_indicator = true`). Payroll liabilities (2710) and plant "
      "overhead accruals (2410) are paid at month end; output VAT (2610) less input VAT (1510) is settled quarterly "
      "at the end of the following month (Q3 2026 is still open on 2026-09-30); bank balances stay positive.")
    a("* **DTC order amounts** are in the market's local currency (`currency_code`): `line_subtotal = "
      "quantity_ordered * unit_price` (unit price excl. VAT), `line_discount_amount = line_subtotal * "
      "line_discount_pct / 100`, `line_net_amount = subtotal - discount`, `tax_amount = net * VAT`, "
      "`line_total_amount = net + tax`. Order header subtotal/discount/tax = sum of its lines and "
      "`order_total_amount = subtotal - discount + shipping_amount + tax_amount` (shipping is a flat VAT-inclusive "
      "fee; finance books it net of VAT to 3900 and its VAT to 2610). VAT is simplified to the standard rate: "
      "25 % SE/NO/DK, 24 % FI, 19 % DE, 21 % NL.")
    a("* Finance recognises DTC revenue for orders with status shipped, delivered or returned (not cancelled, "
      "pending, confirmed or processing) in the month of `order_date`; returned lines (`is_returned`) are booked "
      "to 3050 in the same month.")
    a("* **AR** (finance.ar_invoice): `net_amount = gross_amount - trade_discount_amount`, `total_amount = "
      "net_amount + tax_amount`, `outstanding_balance = total_amount - amount_received - write_off_amount` (>= 0). "
      "Status and `dso_aging_bucket` are as of %s (bucket only for open items). **DSO** = open AR at %s / "
      "(billing of Jul-Sep 2026 / 92 days)." % (world.AS_OF_DATE, world.AS_OF_DATE))
    a("* **Manufacturing**: quantities in EA, costs in the plant's company-code currency. `yield_percentage = "
      "confirmed_quantity / order_quantity * 100` (for partially confirmed orders: of the quantity processed so "
      "far); `scrap_quantity` is part of the loss; OEE = availability x performance x quality "
      "(production_confirmation carries the three components). `actual_cost - planned_cost` of completed orders "
      "is posted monthly per plant to GL 4100 and equals `finance.cogs_allocation.variance_amount` per SKU-month.")
    a("* **Loyalty**: `loyalty_transaction.points_amount` is always positive; `points_direction` (credit/debit) and "
      "`transaction_type` (earn/redeem/adjust/expire) give the direction; balances before/after are consistent per "
      "account and `loyalty_account.points_balance = lifetime_points_earned - lifetime_points_redeemed - "
      "lifetime_points_expired`.")
    a("* **Dates**: no event lies after the extract date. Only forward-looking attributes (due, expiry/expiration, "
      "next-* such as next-review dates, requalification, warranty and depreciation end dates) may be later (up to "
      "%s); backward-looking `last_*` dates (e.g. `last_review_date`) never are. The general ledger has no "
      "postings after the last closed period (2026-09)." % world.FUTURE_MAX)
    a("* **Manufacturing capacity**: lines run in campaigns of one to three days - about 25-35 % of a two-shift "
      "calendar; `production_capacity_units_per_day` = sum of the lines' design speeds x 15 shift hours and "
      "`workforce_headcount` follows the plant labour cost. Operations start within about an hour of their "
      "schedule (`production_confirmation.scheduled_start_datetime`) unless the order was delayed.")
    a("")
    a("## Storylines (S1-S7)")
    a("")
    a("Headline numbers below are the KPI snapshot printed by `python3 -I tools/verify_data.py`.")
    a("")
    s1 = k.get("S1", {})
    br = s1.get("bridge_pct_of_gross") or {}
    rng = s1.get("gap_range_shipped_months_pct") or [0, 0]
    a("**S1 - Revenue definitions conflict.** DTC \"sales\" from `consumer.dtc_order.order_total_amount` are gross "
      "(incl. VAT and shipping, before returns, in local currency); Finance Net Revenue (GL, EUR) excludes VAT and "
      "shipping and is after returns. For the same month, **finance DTC net revenue (GL 3010 + 3050) is %.1f %% "
      "lower than webshop gross** converted to EUR - equivalently, webshop gross is %.1f %% higher than finance. "
      "Monthly the gap is %.1f-%.1f %% of gross (September 2026: %.1f %%, because orders from 29-30 September are "
      "not yet shipped). Bridge as shares of gross: VAT %.1f %%, returned lines %.1f %%, shipping fees %.1f %%, "
      "cancelled or not yet shipped orders %.1f %%; the rest reconciles exactly with GL 3010 + 3050. "
      "Authoritative definition = Finance Net Revenue. Tables: consumer.dtc_order, consumer.dtc_order_line, "
      "finance.journal_entry_line, finance.gl_account."
      % (s1.get("overall_gap_pct", 0) or 0, s1.get("gross_over_net_pct", 0) or 0, rng[0], rng[1],
         (s1.get("last_month") or {}).get("gap_pct", 0), br.get("vat", 0), br.get("returns", 0),
         br.get("shipping", 0), br.get("not_recognised", 0)))
    a("")
    s2 = k.get("S2", {})
    a("**S2 - Currency trap.** `amount_company_code_currency`, AR/AP amounts and DTC order amounts are in local "
      "currency (SEK, NOK, DKK, PLN, EUR). Summing revenue in company-code currency across entities gives %s "
      "(meaningless, x%.2f) instead of EUR %s in group currency. Use `amount_group_currency` (EUR) for cross-entity "
      "totals and convert DTC orders with the monthly rate."
      % (_fmt_int(s2.get("naive_sum_company_code_currency", 0)), s2.get("naive_over_correct_ratio") or 0,
         _fmt_int(s2.get("correct_sum_group_currency_eur", 0))))
    a("")
    s3 = dict((m["month"], m) for m in k.get("S3", {}).get("months", []))
    mar, feb, apr = s3.get("2026-03", {}), s3.get("2026-02", {}), s3.get("2026-04", {})
    a("**S3 - Poznań line PL-POZ-L2 quality incident (March 2026).** Worn filler nozzles on line `POZNL2` "
      "(mes_asset_tag PL-POZ-L2, liquid filling of shampoo/body wash): yield %.1f %% in February -> %.1f %% in March "
      "-> %.1f %% in April; scrap %.2f %% -> %.2f %%; downtime %s -> %s minutes; all March orders finished late; "
      "`yield_record.yield_loss_reason_code = 'EQMALF'` (equipment malfunction; the model only allows a short "
      "upper-case code, the text is in `yield_loss_reason_description`). Fixed by maintenance on %s "
      "(production_line.notes, equipment 'Filler nozzle set'). Finance: production variance (GL 4100) on PL01 spikes "
      "to EUR %s in March 2026. Tables: manufacturing.production_order, batch_record, yield_record, "
      "production_confirmation, production_line, equipment; finance.journal_entry_line, cogs_allocation "
      "(`variance_category = 'yield'`)."
      % (feb.get("yield_pct", 0), mar.get("yield_pct", 0), apr.get("yield_pct", 0), feb.get("scrap_pct", 0),
         mar.get("scrap_pct", 0), feb.get("downtime_min", 0), mar.get("downtime_min", 0),
         world.REPAIR_DATE.isoformat(), _fmt_int(mar.get("pl01_production_variance_eur", 0))))
    a("")
    q = k.get("S4", {}).get("quarters", [])
    a("**S4 - Tampere ramp-up.** The oat-drink plant (plant_code TMPR, erp_plant_code FI-TMP) was commissioned in "
      "April 2025; average OEE of its production orders: " + ", ".join(
          "%s %.1f %%" % (x["quarter"], x["avg_oee_pct"]) for x in q) + " - the 78 % target is reached in June 2026. "
      "Oat-drink SKUs launch from 2025-04-22.")
    a("")
    s5 = k.get("S5", {})
    a("**S5 - Loyalty.** Gold/Platinum members order x%.2f as often as non-members and their average order value "
      "(gross, EUR) is x%.2f higher. Shoppers with `cltv_segment = 'at_risk'` (%d) have no order in the 180 days "
      "before the extract (no order since 2026-04-18); `churned` = no order for more than 365 days."
      % (s5.get("gold_platinum_vs_non_member_frequency_ratio") or 0, s5.get("gold_platinum_vs_non_member_aov_ratio") or 0,
         s5.get("at_risk_shoppers") or 0))
    a("")
    if s5.get("tiers"):
        a(_table(["tier (shopper.loyalty_tier_id)", "shoppers", "orders", "orders per shopper", "AOV EUR"],
                 [(t["tier"], t["shoppers"], t["orders"], "%.2f" % t["orders_per_shopper"], "%.2f" % t["aov_eur"])
                  for t in s5["tiers"]]))
        a("")
    s6 = k.get("S6", {})
    a("**S6 - Receivables.** Alpina Drogerie GmbH (DE01, tier 1 drugstore) disputes part of its invoices from June "
      "2026 (`dispute_flag`, `invoice_status = 'disputed'`, `dispute_reason`); the account is on `credit_hold` since "
      "%s (`status_change_timestamp`) and is not billed after that day. DE01 has the largest overdue balance and "
      "the highest overdue share of open AR. DSO: " % world.CREDIT_HOLD_DATE.isoformat()
      + ", ".join("%s %.1f days" % (r["company_code"], r["dso_days"]) for r in s6.get("company_codes", []))
      + "; group %.1f days. Tables: finance.ar_invoice, finance.ar_payment%s."
      % (s6.get("group_dso_days") or 0, "" if boot else ", sales.trade_account"))
    a("")
    a("**S7 - Governance.** consumer.shopper holds PII (`given_name`, `family_name`, `display_name`, "
      "`primary_email`, `primary_phone`, `birth_date`, `postal_code`) and consumer.address holds street addresses, "
      "postal codes and coordinates; consent_record holds IP addresses. Rows carry `company_code_id` "
      "(dtc_order, ar_invoice, journal_entry_line, ...) so row filters by company code (e.g. an analyst mapped to "
      "SE01 sees only Swedish rows) and column masks can be demonstrated%s. The model's column tags (`dbx_pii_*`, "
      "`dbx_confidential`, `dbx_restricted`, ...) are %s."
      % (" (`bootcamp/notebooks/03_governance.py`)" if boot else "",
         "in `bootcamp/model_tags/` and are applied by the job task `model_tags`" if boot
         else "in `full_model/src/model_tags/` and are applied by the job task `model_tags`"))
    a("")
    a("## Raw data-quality issues (silver must fix)")
    a("")
    a("Injected deterministically at CSV-write time by `tools/datagen/dq.py`, only in the core domains (consumer, "
      "finance, manufacturing); the other domains are clean. Silver rules, in order: drop rows with an empty "
      "primary key; drop `dtc_order_line` rows with `quantity_ordered < 0`; trim + NULLIF empty; normalise enums "
      "(trim, case-fold, map to the canonical `value_regex` value); parse dates as `yyyy-MM-dd` or `dd/MM/yyyy`; "
      "map booleans true/Y/1 and false/N/0; deduplicate by primary key keeping the row with the latest "
      "`dedup_order_column` (exact copies collapse).")
    a("")
    rows = []
    totals = {}
    for dom, tables in manifest.items():
        for name, meta in tables.items():
            for iss in meta["dq_issues"]:
                totals[iss["issue"]] = totals.get(iss["issue"], 0) + iss["rows_or_values"]
                cols = ", ".join(iss.get("columns", [])[:6]) + (" ..." if len(iss.get("columns", [])) > 6 else "")
                rows.append(("%s.%s" % (dom, name), _ISSUE_TITLES.get(iss["issue"], iss["issue"]),
                             iss["rows_or_values"], cols or "-", iss["handling"]))
    a("Totals: " + "; ".join("%s: %s" % (_ISSUE_TITLES.get(i, i), _fmt_int(n)) for i, n in sorted(totals.items())) + ".")
    a("")
    a(_table(["table", "issue", "rows / values", "columns", "silver handling"], rows))
    a("")
    a("## Row counts")
    a("")
    rows = []
    for dom, tables in manifest.items():
        for name, meta in tables.items():
            rows.append((dom, name, meta["scope"], _fmt_int(meta["rows"]), _fmt_int(meta["clean_rows"]),
                         "%.2f" % (meta["bytes"] / 1e6), meta["dedup_order_column"] or "-"))
    tot_rows = sum(m["rows"] for t in manifest.values() for m in t.values())
    tot_clean = sum(m["clean_rows"] for t in manifest.values() for m in t.values())
    tot_bytes = sum(m["bytes"] for t in manifest.values() for m in t.values())
    a("%s CSV rows (%s after the silver rules) in %d files, %.1f MB." % (_fmt_int(tot_rows), _fmt_int(tot_clean),
                                                                         n_files, tot_bytes / 1e6))
    a("")
    a(_table(["domain", "table", "scope", "CSV rows", "clean rows", "MB", "dedup_order_column"], rows))
    a("")
    a("## Regenerate and verify")
    a("")
    a("```bash")
    a("# from the repository root")
    a("python3 -I tools/generate_data.py            # writes bootcamp/data and full_model/data (CSVs, manifests, READMEs)")
    a("python3 -I tools/generate_data.py --seed %d   # same as the default" % seed)
    a("python3 -I tools/verify_data.py              # checks + storyline KPIs; exit code 1 on any violation")
    a("```")
    a("")
    a("Python 3.10+, standard library only. The output is byte-identical for the same seed. `generate_data.py` "
      "fails if both data folders together exceed %.1f MB (budget 40 MB). Generic tables (the 65 full-scope tables outside "
      "the curated set) are filled by the model-driven engine (`tools/datagen/engine.py`, with coherence hooks in "
      "`curated_generic.py` for retail stores, POS records, account contacts and shipments); the 36 core tables, the "
      "whole product domain (brand, category, SKU and the specifications: material, formulation, ingredients, "
      "packaging, labels, GTIN registry, BOMs, hierarchy - `curated_product_specs.py`), sales.trade_account and "
      "distribution.distribution_facility are curated (`tools/datagen/curated_*.py`)." % (SIZE_GUARD_MB,))
    a("")
    a("## Simplifications")
    a("")
    a("* Row counts were sized to keep every CSV below 10 MB and the folder below 40 MB, so some tables are smaller "
      "than in the original sizing (e.g. ~8 000 DTC orders, ~15 000 order lines, ~11 000 loyalty movements).")
    a("* One standard VAT rate per market for all categories; shipping fees are flat and VAT-inclusive.")
    a("* Intercompany supplies are transferred at standard cost without a margin; there is no PP&E cost account "
      "(only accumulated depreciation 1290) and no dividend or tax postings.")
    a("* All companies, retailers, carriers (NORRPOST, FJORDPOST, ...) and equipment vendors are fictional. Names "
      "of well-known business software (SAP S/4HANA, Salesforce Commerce Cloud, Siemens Opcenter, Veeva Vault) and "
      "PLC types appear only as system identifiers (`source_system_*`, `record_source_system`).")
    a("* B2B billing is summarised to one GL document per company code and month; brand splits of B2B invoices "
      "follow each customer's assortment mix.")
    a("* Generic (full-scope) tables are realistic in shape and referential integrity but are not story-driven.")
    a("")
    return "\n".join(L) + "\n"


def write(path, reg, manifest, report, seed, variant="full"):
    text = render(manifest, report, seed, variant)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
