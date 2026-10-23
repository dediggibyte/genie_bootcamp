# Fjällmark Consumer Goods AB - synthetic data, complete industry model

> **All data in this folder is synthetic and fictional.** Fjällmark Consumer Goods AB, its brands, plants, retail customers and people do not exist. Names are random combinations, e-mail addresses use the reserved `example.com` domain, phone numbers contain an obviously fake `000` block, IP addresses come from the documentation ranges (RFC 5737) and retailer names are invented. Any resemblance to real companies or persons is coincidental.

The tables follow the **Lakehouse Industry Data Model - Consumer Goods v2 (MVM)** (`tools/model/consumer_goods_v2_mvm.json` at the repository root; Copyright Databricks, Inc., Databricks license - see `LICENSE.md` and `NOTICE.md` in this bundle folder, verbatim copies of `tools/model/`): exact column names and column order of the model, values that follow its value formats. **Notice:** the CSV files and `manifest.json` are derived from that model and modified for the Fjällmark Genie bootcamp (synthetic values, a subset of its tables per folder, deliberate data-quality issues). The generator is `tools/generate_data.py` (standard library only, deterministic) and the checker is `tools/verify_data.py`.

The complete model has 10 domains and 116 tables. Every CSV is stored **once**: the three bootcamp domains (consumer, finance, manufacturing - 36 tables) live in `bootcamp/data/<domain>/`, the other 7 domains (80 tables) here in `full_model/data/<domain>/`. `full_model/notebooks/01_setup_catalog.py` reads both folders.

## Contents

* `<domain>/<table>.csv` - one file per table of the 7 non-bootcamp domains (80 files); the 36 bootcamp tables are in `bootcamp/data/`. `notebooks/01_setup_catalog.py` copies all 116 files to `/Volumes/<catalog>/landing/raw_files/<domain>/<table>/<table>.csv` (one folder per table for Auto Loader).
* `manifest.json` - per domain and table (all 116 tables): `rows` (CSV data rows), `clean_rows` (rows before data-quality injection = rows after the silver rules), `scope` (`bootcamp` = consumer/finance/manufacturing, the Genie scope; `full` = the other 7 domains), `primary_key`, `dedup_order_column`, `file` (path of the CSV relative to the repository root), `bytes` and `dq_issues`.
* `README.md` - this file.

## CSV format

* UTF-8, comma separated, `\n` line endings, header row = model column names in model order.
* RFC-4180 quoting: only fields that contain a comma are quoted. Values never contain double quotes, backslashes or line breaks, so Spark's CSV reader (`read_files(..., format => 'csv', header => true)`) and any RFC-4180 reader agree. Read every column as STRING in bronze.
* Empty field = NULL. Dates `yyyy-MM-dd`, timestamps `yyyy-MM-dd HH:mm:ss` (no time zone; local plant/market time), decimals with `.` and exactly the declared scale, booleans `true`/`false` (except the documented Y/N and 1/0 mixes).
* Surrogate keys are BIGINT: `table_index * 100000 + n` where `table_index` is the 1-based position of the table in the model (product.sku = 1, ..., finance.company_code = 116). A key therefore identifies its table, e.g. `2500042` is a consumer.shopper. Guest-checkout shopper ids start at 990000001.

## The company in brief

Fjällmark Consumer Goods AB (HQ Stockholm) makes Nordic packaged foods, beverages and personal care. Group reporting currency is **EUR**; fiscal year = calendar year, fiscal period = month. Transactions run **2024-01-01 .. 2026-09-30**; balances, AR/AP status and aging are a period-end snapshot as of **2026-09-30**; the extract is dated **2026-10-15**.

| company code | legal entity | country | currency | role |
|---|---|---|---|---|
| SE01 | Fjällmark Consumer Goods AB | SWE | SEK | Group parent - HQ, DTC Sweden, Lund and Norrköping plants |
| NO01 | Fjällmark Norge AS | NOR | NOK | Sales and DTC Norway |
| DK01 | Fjällmark Danmark A/S | DNK | DKK | Sales and DTC Denmark |
| FI01 | Fjällmark Suomi Oy | FIN | EUR | Sales and DTC Finland, Tampere oat-drink plant |
| DE01 | Fjällmark Deutschland GmbH | DEU | EUR | Sales and DTC Germany and the Netherlands |
| PL01 | Fjällmark Polska Sp. z o.o. | POL | PLN | Poznań personal-care plant (Mjuk Care), local B2B, no DTC |

FX (EUR per unit, monthly average with +-2 % drift; base): SEK 0.087, NOK 0.085, DKK 0.134, PLN 0.232, EUR 1. The monthly rate used by finance is in `journal_entry_line.exchange_rate` (EUR per unit of the company-code currency).

**Brands** (product.brand): Björkö Pantry (FOOD - crispbread, granola, porridge, jams, muesli bars), Kallkälla (BEVERAGE - sparkling water, juices, oat drinks from April 2025) and Mjuk Care (PERSONAL_CARE - shampoo, conditioner, body wash, toothpaste, hand cream, deodorant). 89 SKUs with valid GTIN-13 codes (product.sku), a two-level category tree (product.product_category: 3 + 14 sub-categories).

**Plants and lines** (manufacturing): `plant_code` is the 4-character SAP-style code required by the model regex; the human-readable site tag is in `erp_plant_code` / `mes_asset_tag`.

| plant_code | erp_plant_code | facility | company | lines | line_code (mes_asset_tag) |
|---|---|---|---|---|---|
| LUND | SE-LUN | Lund Food Plant | SE01 | 4 | LUNDL1 (SE-LUN-L1), LUNDL2 (SE-LUN-L2), LUNDL3 (SE-LUN-L3), LUNDL4 (SE-LUN-L4) |
| NKPG | SE-NKP | Norrköping Beverage Plant | SE01 | 4 | NKPGL1 (SE-NKP-L1), NKPGL2 (SE-NKP-L2), NKPGL3 (SE-NKP-L3), NKPGL4 (SE-NKP-L4) |
| TMPR | FI-TMP | Tampere Oat Drink Plant | FI01 | 3 | TMPRL1 (FI-TMP-L1), TMPRL2 (FI-TMP-L2), TMPRL3 (FI-TMP-L3) |
| POZN | PL-POZ | Poznań Personal Care Plant | PL01 | 5 | POZNL1 (PL-POZ-L1), POZNL2 (PL-POZ-L2), POZNL3 (PL-POZ-L3), POZNL4 (PL-POZ-L4), POZNL5 (PL-POZ-L5) |

**Distribution centres** (distribution.distribution_facility): DCJKG Jönköping (SE01), DCOSL Oslo (NO01), DCODE Odense (DK01), DCVAN Vantaa (FI01), DCHAM Hamburg (DE01).

**DTC webshop** `fjallmark.example` in SWE, NOR, DNK, FIN, DEU and NLD (ISO 3166 alpha-3); order currency = market currency (SEK, NOK, DKK, EUR). Loyalty programme **Fjällmark Friends** with tiers Bronze, Silver, Gold and Platinum (points multiplier 1.0 / 1.25 / 1.5 / 2.0, member discount 0 / 2 / 5 / 8 %, free shipping for Gold and Platinum; 1 point per EUR of net merchandise value x multiplier, 100 points = 1 EUR, welcome bonus 100, birthday bonus 50 for members who ordered in the last 12 months). A member keeps the tier with Silver 150 points or 40.00 EUR, Gold 250 points or 60.00 EUR, Platinum 400 points or 100.00 EUR (lifetime points or qualifying spend excl. VAT in the last 12 months, `loyalty_tier.required_points` / `required_spend_usd` - the amounts are EUR); the annual review moves members below the requirement down (`loyalty_account.previous_tier`). Points pay for up to 30 % of a basket (`dtc_order.loyalty_points_redeemed`) or for gift-card rewards; about a fifth of the earned points are redeemed and unused points expire 12 months after the last activity. Subscriptions (one box SKU per delivery, 4-10 units or 1-3 crates/trays, ~25-40 EUR incl. VAT): granola boxes, oat refills, oat-drink crates, sparkling water trays, Mjuk Care refills.

**B2B**: 25 fictional retail, wholesale and foodservice customers (sales.trade_account), e.g. NorthCart Retail, Vasa Grocers, Fjordhandel, Baltic FreshMarket, Kaleva Kauppa, Alpina Drogerie; `acv_total` and `credit_limit_amount` are in the account's currency. B2B is about 99.5 % of net revenue and grows ~5 % a year. The **webshop is a small, fast-growing channel**: about 0.5 % of group net revenue, growing ~18 % a year in value (order count ~15 %, average order value slightly up after the oat-drink launch); about a third of webshop orders are subscription deliveries. Seasonality: Q4 Christmas peak (DTC orders +35 %, food), beverages peak in June-August, personal care flat.

## Business definitions and conventions

* **General ledger** (finance.journal_entry / journal_entry_line): amounts are stored as **positive** values; the direction is `debit_credit_indicator` (`D`/`C`). Every journal entry balances (sum D = sum C) in transaction, company-code and group currency. `amount_group_currency` = company-code amount x monthly FX (EUR). Chart of accounts: 26 accounts per company code with shared numbering (finance.gl_account, `account_number`, `account_group`).
* **Net Revenue (authoritative)** = sum over GL accounts with `account_group = 'REVENUE'` (3000 Revenue - trade customers, 3010 Revenue - DTC webshop, 3040 Trade discounts and rebates, 3050 Sales returns - DTC) of credit minus debit in **group currency EUR**. It excludes VAT (2610) and shipping fees (3900, `OTHER_INCOME`) and is after trade discounts and returns.

  ```sql
  SELECT je.fiscal_year, je.fiscal_period, cc.code AS company_code,
         SUM(CASE WHEN l.debit_credit_indicator = 'C' THEN l.amount_group_currency
                  ELSE -l.amount_group_currency END) AS net_revenue_eur
  FROM finance.journal_entry_line l
  JOIN finance.journal_entry je ON je.journal_entry_id = l.journal_entry_id
  JOIN finance.gl_account ga ON ga.gl_account_id = l.gl_account_id
  JOIN finance.company_code cc ON cc.company_code_id = l.company_code_id
  WHERE ga.account_group = 'REVENUE'
  GROUP BY ALL
  ```

* **COGS** = account group `COGS` (4000 standard COGS, 4100 production variances); Gross Margin = Net Revenue - COGS. Operating expenses: 5000 salaries (sales, marketing, DTC, logistics and administration staff), 6100 marketing, 6300 freight and logistics, 6400 rent, utilities, maintenance and IT, 7000 depreciation of office/IT/warehouse assets. Plant labour, plant machinery depreciation and plant energy/maintenance are product costs: they are part of the standard cost and reach the P&L through COGS. EBIT = Net Revenue + 3900 - COGS - opex is about 10-13 % for the group and positive for every company code.
* **Document types** (monthly summary documents per company code unless noted): DR billing / DTC sales, KN DTC returns, WA cost of goods sold and goods supplied to group companies, DZ customer and PSP receipts, SA payroll, payroll and plant-overhead payments, production settlement per plant, quarterly VAT returns and the 2024-01-01 opening balances, AB depreciation; AP invoices (KR) and AP payments (KZ) post one document each.
* **Inventory and intercompany**: each plant settles its completed production orders monthly (SA, `reference_document_number` PRD<plant><yyyymm>): finished goods received at standard cost (1410), production variance actual - planned (4100), raw and packaging materials consumed (1430), plant labour (2710), machinery depreciation (1290) and plant energy/maintenance (2410). Plants produce one month ahead of demand, so finished goods stay at about one month of sales. Goods made by another group company are intercompany supplies at standard cost (no margin), settled through the group cash pool in the same month (1110 lines with `trading_partner_code`, `intercompany_indicator = true`). Payroll liabilities (2710) and plant overhead accruals (2410) are paid at month end; output VAT (2610) less input VAT (1510) is settled quarterly at the end of the following month (Q3 2026 is still open on 2026-09-30); bank balances stay positive.
* **DTC order amounts** are in the market's local currency (`currency_code`): `line_subtotal = quantity_ordered * unit_price` (unit price excl. VAT), `line_discount_amount = line_subtotal * line_discount_pct / 100`, `line_net_amount = subtotal - discount`, `tax_amount = net * VAT`, `line_total_amount = net + tax`. Order header subtotal/discount/tax = sum of its lines and `order_total_amount = subtotal - discount + shipping_amount + tax_amount` (shipping is a flat VAT-inclusive fee; finance books it net of VAT to 3900 and its VAT to 2610). VAT is simplified to the standard rate: 25 % SE/NO/DK, 24 % FI, 19 % DE, 21 % NL.
* Finance recognises DTC revenue for orders with status shipped, delivered or returned (not cancelled, pending, confirmed or processing) in the month of `order_date`; returned lines (`is_returned`) are booked to 3050 in the same month.
* **AR** (finance.ar_invoice): `net_amount = gross_amount - trade_discount_amount`, `total_amount = net_amount + tax_amount`, `outstanding_balance = total_amount - amount_received - write_off_amount` (>= 0). Status and `dso_aging_bucket` are as of 2026-09-30 (bucket only for open items). **DSO** = open AR at 2026-09-30 / (billing of Jul-Sep 2026 / 92 days).
* **Manufacturing**: quantities in EA, costs in the plant's company-code currency. `yield_percentage = confirmed_quantity / order_quantity * 100` (for partially confirmed orders: of the quantity processed so far); `scrap_quantity` is part of the loss; OEE = availability x performance x quality (production_confirmation carries the three components). `actual_cost - planned_cost` of completed orders is posted monthly per plant to GL 4100 and equals `finance.cogs_allocation.variance_amount` per SKU-month.
* **Loyalty**: `loyalty_transaction.points_amount` is always positive; `points_direction` (credit/debit) and `transaction_type` (earn/redeem/adjust/expire) give the direction; balances before/after are consistent per account and `loyalty_account.points_balance = lifetime_points_earned - lifetime_points_redeemed - lifetime_points_expired`.
* **Dates**: no event lies after the extract date. Only forward-looking attributes (due, expiry/expiration, next-* such as next-review dates, requalification, warranty and depreciation end dates) may be later (up to 2036-12-31); backward-looking `last_*` dates (e.g. `last_review_date`) never are. The general ledger has no postings after the last closed period (2026-09).
* **Manufacturing capacity**: lines run in campaigns of one to three days - about 25-35 % of a two-shift calendar; `production_capacity_units_per_day` = sum of the lines' design speeds x 15 shift hours and `workforce_headcount` follows the plant labour cost. Operations start within about an hour of their schedule (`production_confirmation.scheduled_start_datetime`) unless the order was delayed.

## Storylines (S1-S7)

Headline numbers below are the KPI snapshot printed by `python3 -I tools/verify_data.py`.

**S1 - Revenue definitions conflict.** DTC "sales" from `consumer.dtc_order.order_total_amount` are gross (incl. VAT and shipping, before returns, in local currency); Finance Net Revenue (GL, EUR) excludes VAT and shipping and is after returns. For the same month, **finance DTC net revenue (GL 3010 + 3050) is 26.7 % lower than webshop gross** converted to EUR - equivalently, webshop gross is 36.4 % higher than finance. Monthly the gap is 23.7-29.7 % of gross (September 2026: 31.8 %, because orders from 29-30 September are not yet shipped). Bridge as shares of gross: VAT 18.3 %, returned lines 4.5 %, shipping fees 2.0 %, cancelled or not yet shipped orders 1.9 %; the rest reconciles exactly with GL 3010 + 3050. Authoritative definition = Finance Net Revenue. Tables: consumer.dtc_order, consumer.dtc_order_line, finance.journal_entry_line, finance.gl_account.

**S2 - Currency trap.** `amount_company_code_currency`, AR/AP amounts and DTC order amounts are in local currency (SEK, NOK, DKK, PLN, EUR). Summing revenue in company-code currency across entities gives 399 600 534 (meaningless, x7.08) instead of EUR 56 416 936 in group currency. Use `amount_group_currency` (EUR) for cross-entity totals and convert DTC orders with the monthly rate.

**S3 - Poznań line PL-POZ-L2 quality incident (March 2026).** Worn filler nozzles on line `POZNL2` (mes_asset_tag PL-POZ-L2, liquid filling of shampoo/body wash): yield 97.2 % in February -> 86.8 % in March -> 97.5 % in April; scrap 2.42 % -> 7.34 %; downtime 240 -> 724 minutes; all March orders finished late; `yield_record.yield_loss_reason_code = 'EQMALF'` (equipment malfunction; the model only allows a short upper-case code, the text is in `yield_loss_reason_description`). Fixed by maintenance on 2026-04-04 (production_line.notes, equipment 'Filler nozzle set'). Finance: production variance (GL 4100) on PL01 spikes to EUR 4 646 in March 2026. Tables: manufacturing.production_order, batch_record, yield_record, production_confirmation, production_line, equipment; finance.journal_entry_line, cogs_allocation (`variance_category = 'yield'`).

**S4 - Tampere ramp-up.** The oat-drink plant (plant_code TMPR, erp_plant_code FI-TMP) was commissioned in April 2025; average OEE of its production orders: 2025-Q2 58.3 %, 2025-Q3 63.5 %, 2025-Q4 68.4 %, 2026-Q1 74.1 %, 2026-Q2 78.4 %, 2026-Q3 78.9 % - the 78 % target is reached in June 2026. Oat-drink SKUs launch from 2025-04-22.

**S5 - Loyalty.** Gold/Platinum members order x2.95 as often as non-members and their average order value (gross, EUR) is x2.41 higher. Shoppers with `cltv_segment = 'at_risk'` (697) have no order in the 180 days before the extract (no order since 2026-04-18); `churned` = no order for more than 365 days.

| tier (shopper.loyalty_tier_id) | shoppers | orders | orders per shopper | AOV EUR |
|---|---|---|---|---|
| Non-member | 1065 | 1896 | 1.78 | 29.45 |
| Bronze | 1052 | 2217 | 2.11 | 34.41 |
| Silver | 490 | 1646 | 3.36 | 41.06 |
| Gold | 270 | 1310 | 4.85 | 69.88 |
| Platinum | 123 | 757 | 6.15 | 72.61 |

**S6 - Receivables.** Alpina Drogerie GmbH (DE01, tier 1 drugstore) disputes part of its invoices from June 2026 (`dispute_flag`, `invoice_status = 'disputed'`, `dispute_reason`); the account is on `credit_hold` since 2026-09-28 (`status_change_timestamp`) and is not billed after that day. DE01 has the largest overdue balance and the highest overdue share of open AR. DSO: DE01 65.7 days, DK01 30.8 days, FI01 31.2 days, NO01 35.2 days, PL01 37.6 days, SE01 35.8 days; group 39.2 days. Tables: finance.ar_invoice, finance.ar_payment, sales.trade_account.

**S7 - Governance.** consumer.shopper holds PII (`given_name`, `family_name`, `display_name`, `primary_email`, `primary_phone`, `birth_date`, `postal_code`) and consumer.address holds street addresses, postal codes and coordinates; consent_record holds IP addresses. Rows carry `company_code_id` (dtc_order, ar_invoice, journal_entry_line, ...) so row filters by company code (e.g. an analyst mapped to SE01 sees only Swedish rows) and column masks can be demonstrated. The model's column tags (`dbx_pii_*`, `dbx_confidential`, `dbx_restricted`, ...) are in `full_model/src/model_tags/` and are applied by the job task `model_tags`.

## Raw data-quality issues (silver must fix)

Injected deterministically at CSV-write time by `tools/datagen/dq.py`, only in the core domains (consumer, finance, manufacturing); the other domains are clean. Silver rules, in order: drop rows with an empty primary key; drop `dtc_order_line` rows with `quantity_ordered < 0`; trim + NULLIF empty; normalise enums (trim, case-fold, map to the canonical `value_regex` value); parse dates as `yyyy-MM-dd` or `dd/MM/yyyy`; map booleans true/Y/1 and false/N/0; deduplicate by primary key keeping the row with the latest `dedup_order_column` (exact copies collapse).

Totals: Booleans as Y/N or 1/0: 25 005; Dates in dd/MM/yyyy: 685; Rows with an empty primary key: 214; Enum values with stray whitespace / wrong case: 10 927; Exact duplicate rows (re-delivered extract): 857; Guest checkout lines: shopper_id NULL: 77; Guest checkout: shopper_id not in consumer.shopper: 40; Negative quantity_ordered: 10; Updated duplicates (same PK, older version): 417.

| table | issue | rows / values | columns | silver handling |
|---|---|---|---|---|
| manufacturing.manufacturing_facility | Enum values with stray whitespace / wrong case | 2 | facility_type, sustainability_rating | trim + case-fold, then map to the canonical value of the column's value_regex list |
| manufacturing.production_line | Enum values with stray whitespace / wrong case | 4 | gmp_classification, operational_status, shift_pattern | trim + case-fold, then map to the canonical value of the column's value_regex list |
| manufacturing.work_center | Enum values with stray whitespace / wrong case | 9 | capacity_unit, category, gmp_qualification_status, work_center_status, work_center_type | trim + case-fold, then map to the canonical value of the column's value_regex list |
| manufacturing.work_center | Updated duplicates (same PK, older version) | 1 | work_center_id, modified_timestamp | deduplicate on work_center_id keeping the row with the latest modified_timestamp |
| manufacturing.manufacturing_bom | Enum values with stray whitespace / wrong case | 10 | bom_status, bom_type, component_item_category, lot_size_requirement | trim + case-fold, then map to the canonical value of the column's value_regex list |
| manufacturing.manufacturing_bom | Updated duplicates (same PK, older version) | 2 | manufacturing_bom_id, last_modified_timestamp | deduplicate on manufacturing_bom_id keeping the row with the latest last_modified_timestamp |
| manufacturing.routing | Enum values with stray whitespace / wrong case | 14 | approval_status, routing_status, routing_type | trim + case-fold, then map to the canonical value of the column's value_regex list |
| manufacturing.routing | Updated duplicates (same PK, older version) | 2 | routing_id, last_modified_timestamp | deduplicate on routing_id keeping the row with the latest last_modified_timestamp |
| manufacturing.production_order | Enum values with stray whitespace / wrong case | 148 | order_type, priority, settlement_rule | trim + case-fold, then map to the canonical value of the column's value_regex list |
| manufacturing.production_order | Booleans as Y/N or 1/0 | 1100 | gmp_compliance_flag, quality_inspection_required | map true/Y/1 -> TRUE and false/N/0 -> FALSE (case-insensitive) |
| manufacturing.production_order | Exact duplicate rows (re-delivered extract) | 20 | production_order_id | deduplicate on production_order_id (exact copies collapse) |
| manufacturing.production_order | Rows with an empty primary key | 4 | production_order_id | expectation production_order_id IS NOT NULL -> DROP ROW |
| manufacturing.batch_record | Enum values with stray whitespace / wrong case | 68 | batch_status | trim + case-fold, then map to the canonical value of the column's value_regex list |
| manufacturing.batch_record | Booleans as Y/N or 1/0 | 2868 | gmp_deviation_flag, lot_genealogy_complete_flag, quality_release_flag, recall_flag, record_locked_flag, regulatory_hold_flag | map true/Y/1 -> TRUE and false/N/0 -> FALSE (case-insensitive) |
| manufacturing.batch_record | Exact duplicate rows (re-delivered extract) | 20 | batch_record_id | deduplicate on batch_record_id (exact copies collapse) |
| manufacturing.batch_record | Rows with an empty primary key | 4 | batch_record_id | expectation batch_record_id IS NOT NULL -> DROP ROW |
| manufacturing.yield_record | Enum values with stray whitespace / wrong case | 66 | shift_code | trim + case-fold, then map to the canonical value of the column's value_regex list |
| manufacturing.yield_record | Exact duplicate rows (re-delivered extract) | 20 | yield_record_id | deduplicate on yield_record_id (exact copies collapse) |
| manufacturing.yield_record | Rows with an empty primary key | 4 | yield_record_id | expectation yield_record_id IS NOT NULL -> DROP ROW |
| manufacturing.production_confirmation | Enum values with stray whitespace / wrong case | 524 | confirmation_type, operation_status, source_system_code | trim + case-fold, then map to the canonical value of the column's value_regex list |
| manufacturing.production_confirmation | Exact duplicate rows (re-delivered extract) | 60 | production_confirmation_id | deduplicate on production_confirmation_id (exact copies collapse) |
| manufacturing.production_confirmation | Rows with an empty primary key | 12 | production_confirmation_id | expectation production_confirmation_id IS NOT NULL -> DROP ROW |
| manufacturing.planned_order | Enum values with stray whitespace / wrong case | 502 | conversion_status, demand_source_type, lot_size_key, order_status, order_type, priority_code ... | trim + case-fold, then map to the canonical value of the column's value_regex list |
| manufacturing.planned_order | Exact duplicate rows (re-delivered extract) | 24 | planned_order_id | deduplicate on planned_order_id (exact copies collapse) |
| manufacturing.planned_order | Rows with an empty primary key | 5 | planned_order_id | expectation planned_order_id IS NOT NULL -> DROP ROW |
| consumer.shopper | Enum values with stray whitespace / wrong case | 368 | cltv_segment, consumer_type, gender, lifecycle_status | trim + case-fold, then map to the canonical value of the column's value_regex list |
| consumer.shopper | Dates in dd/MM/yyyy | 133 | birth_date | parse with yyyy-MM-dd first, fall back to dd/MM/yyyy |
| consumer.shopper | Dates in dd/MM/yyyy | 164 | acquisition_date | parse with yyyy-MM-dd first, fall back to dd/MM/yyyy |
| consumer.shopper | Booleans as Y/N or 1/0 | 7384 | age_verified, ccpa_subject, data_sharing_consent, email_opt_in, gdpr_subject, identity_verified ... | map true/Y/1 -> TRUE and false/N/0 -> FALSE (case-insensitive) |
| consumer.shopper | Updated duplicates (same PK, older version) | 60 | shopper_id, updated_timestamp | deduplicate on shopper_id keeping the row with the latest updated_timestamp |
| consumer.shopper | Rows with an empty primary key | 6 | shopper_id | expectation shopper_id IS NOT NULL -> DROP ROW |
| consumer.household | Enum values with stray whitespace / wrong case | 456 | cltv_band, dwelling_type, household_status, household_type, income_band, primary_channel ... | trim + case-fold, then map to the canonical value of the column's value_regex list |
| consumer.household | Updated duplicates (same PK, older version) | 36 | household_id, last_updated_timestamp | deduplicate on household_id keeping the row with the latest last_updated_timestamp |
| consumer.household | Rows with an empty primary key | 4 | household_id | expectation household_id IS NOT NULL -> DROP ROW |
| consumer.address | Enum values with stray whitespace / wrong case | 728 | address_status, address_type, data_residency_region, format_type, geocoding_accuracy, residential_indicator ... | trim + case-fold, then map to the canonical value of the column's value_regex list |
| consumer.address | Updated duplicates (same PK, older version) | 63 | address_id, updated_timestamp | deduplicate on address_id keeping the row with the latest updated_timestamp |
| consumer.address | Rows with an empty primary key | 6 | address_id | expectation address_id IS NOT NULL -> DROP ROW |
| consumer.loyalty_account | Enum values with stray whitespace / wrong case | 469 | account_status, account_type, cltv_segment, communication_preference, enrollment_channel, points_expiry_policy ... | trim + case-fold, then map to the canonical value of the column's value_regex list |
| consumer.loyalty_account | Dates in dd/MM/yyyy | 107 | enrollment_date | parse with yyyy-MM-dd first, fall back to dd/MM/yyyy |
| consumer.loyalty_account | Booleans as Y/N or 1/0 | 1449 | consent_data_sharing, consent_marketing, fraud_flag | map true/Y/1 -> TRUE and false/N/0 -> FALSE (case-insensitive) |
| consumer.loyalty_account | Updated duplicates (same PK, older version) | 39 | loyalty_account_id, updated_timestamp | deduplicate on loyalty_account_id keeping the row with the latest updated_timestamp |
| consumer.loyalty_account | Rows with an empty primary key | 4 | loyalty_account_id | expectation loyalty_account_id IS NOT NULL -> DROP ROW |
| consumer.loyalty_transaction | Enum values with stray whitespace / wrong case | 1607 | channel, fraud_review_status, points_direction, transaction_status, transaction_type | trim + case-fold, then map to the canonical value of the column's value_regex list |
| consumer.loyalty_transaction | Exact duplicate rows (re-delivered extract) | 105 | loyalty_transaction_id | deduplicate on loyalty_transaction_id (exact copies collapse) |
| consumer.loyalty_transaction | Rows with an empty primary key | 21 | loyalty_transaction_id | expectation loyalty_transaction_id IS NOT NULL -> DROP ROW |
| consumer.preference | Enum values with stray whitespace / wrong case | 444 | cltv_tier, consent_basis, inference_basis, nps_segment, preference_status, preferred_time_of_day | trim + case-fold, then map to the canonical value of the column's value_regex list |
| consumer.preference | Updated duplicates (same PK, older version) | 56 | preference_id, last_updated_timestamp | deduplicate on preference_id keeping the row with the latest last_updated_timestamp |
| consumer.preference | Rows with an empty primary key | 6 | preference_id | expectation preference_id IS NOT NULL -> DROP ROW |
| consumer.consent_record | Enum values with stray whitespace / wrong case | 1736 | capture_method, change_trigger, consent_scope, consent_status, consent_type, device_type ... | trim + case-fold, then map to the canonical value of the column's value_regex list |
| consumer.consent_record | Booleans as Y/N or 1/0 | 11364 | double_opt_in_flag, is_current_record, parental_consent_flag, profiling_consent_flag, re_consent_required_flag, third_party_sharing_flag | map true/Y/1 -> TRUE and false/N/0 -> FALSE (case-insensitive) |
| consumer.consent_record | Updated duplicates (same PK, older version) | 127 | consent_record_id, updated_timestamp | deduplicate on consent_record_id keeping the row with the latest updated_timestamp |
| consumer.consent_record | Rows with an empty primary key | 13 | consent_record_id | expectation consent_record_id IS NOT NULL -> DROP ROW |
| consumer.dtc_order | Guest checkout: shopper_id not in consumer.shopper | 40 | shopper_id | kept in silver/gold; shopper_id >= 990000000 is a guest checkout without a shopper profile (use LEFT JOIN to consumer.shopper) |
| consumer.dtc_order | Enum values with stray whitespace / wrong case | 1182 | channel_code, device_type, fulfillment_status, payment_method, payment_status | trim + case-fold, then map to the canonical value of the column's value_regex list |
| consumer.dtc_order | Exact duplicate rows (re-delivered extract) | 80 | dtc_order_id | deduplicate on dtc_order_id (exact copies collapse) |
| consumer.dtc_order | Rows with an empty primary key | 16 | dtc_order_id | expectation dtc_order_id IS NOT NULL -> DROP ROW |
| consumer.dtc_order_line | Guest checkout lines: shopper_id NULL | 77 | shopper_id | kept; shopper_id is NULL on lines of guest-checkout orders |
| consumer.dtc_order_line | Enum values with stray whitespace / wrong case | 465 | channel_code | trim + case-fold, then map to the canonical value of the column's value_regex list |
| consumer.dtc_order_line | Exact duplicate rows (re-delivered extract) | 153 | dtc_order_line_id | deduplicate on dtc_order_line_id (exact copies collapse) |
| consumer.dtc_order_line | Negative quantity_ordered | 10 | quantity_ordered | expectation quantity_ordered >= 0 -> DROP ROW |
| consumer.dtc_order_line | Rows with an empty primary key | 31 | dtc_order_line_id | expectation dtc_order_line_id IS NOT NULL -> DROP ROW |
| consumer.subscription | Enum values with stray whitespace / wrong case | 90 | cancellation_reason, channel, frequency, payment_method_type, subscription_status, subscription_type | trim + case-fold, then map to the canonical value of the column's value_regex list |
| consumer.subscription | Updated duplicates (same PK, older version) | 10 | subscription_id, updated_timestamp | deduplicate on subscription_id keeping the row with the latest updated_timestamp |
| consumer.subscription | Rows with an empty primary key | 1 | subscription_id | expectation subscription_id IS NOT NULL -> DROP ROW |
| finance.cost_center | Enum values with stray whitespace / wrong case | 2 | allocation_method, category | trim + case-fold, then map to the canonical value of the column's value_regex list |
| finance.cost_center | Updated duplicates (same PK, older version) | 1 | cost_center_id, last_modified_timestamp | deduplicate on cost_center_id keeping the row with the latest last_modified_timestamp |
| finance.profit_center | Enum values with stray whitespace / wrong case | 4 | profit_center_status, valuation_view | trim + case-fold, then map to the canonical value of the column's value_regex list |
| finance.gl_account | Enum values with stray whitespace / wrong case | 34 | account_status, account_type, balance_sheet_classification, cash_flow_category, cost_element_category, debit_credit_indicator ... | trim + case-fold, then map to the canonical value of the column's value_regex list |
| finance.gl_account | Updated duplicates (same PK, older version) | 3 | gl_account_id, last_modified_timestamp | deduplicate on gl_account_id keeping the row with the latest last_modified_timestamp |
| finance.journal_entry | Enum values with stray whitespace / wrong case | 338 | exchange_rate_type, posting_status | trim + case-fold, then map to the canonical value of the column's value_regex list |
| finance.journal_entry | Exact duplicate rows (re-delivered extract) | 53 | journal_entry_id | deduplicate on journal_entry_id (exact copies collapse) |
| finance.journal_entry | Rows with an empty primary key | 11 | journal_entry_id | expectation journal_entry_id IS NOT NULL -> DROP ROW |
| finance.journal_entry_line | Enum values with stray whitespace / wrong case | 553 | debit_credit_indicator | trim + case-fold, then map to the canonical value of the column's value_regex list |
| finance.journal_entry_line | Exact duplicate rows (re-delivered extract) | 174 | journal_entry_line_id | deduplicate on journal_entry_line_id (exact copies collapse) |
| finance.journal_entry_line | Rows with an empty primary key | 35 | journal_entry_line_id | expectation journal_entry_line_id IS NOT NULL -> DROP ROW |
| finance.ar_invoice | Enum values with stray whitespace / wrong case | 146 | dso_aging_bucket, payment_method | trim + case-fold, then map to the canonical value of the column's value_regex list |
| finance.ar_invoice | Dates in dd/MM/yyyy | 204 | due_date | parse with yyyy-MM-dd first, fall back to dd/MM/yyyy |
| finance.ar_invoice | Booleans as Y/N or 1/0 | 840 | dispute_flag | map true/Y/1 -> TRUE and false/N/0 -> FALSE (case-insensitive) |
| finance.ar_invoice | Exact duplicate rows (re-delivered extract) | 44 | ar_invoice_id | deduplicate on ar_invoice_id (exact copies collapse) |
| finance.ar_invoice | Rows with an empty primary key | 9 | ar_invoice_id | expectation ar_invoice_id IS NOT NULL -> DROP ROW |
| finance.ar_payment | Enum values with stray whitespace / wrong case | 271 | payment_channel, payment_method | trim + case-fold, then map to the canonical value of the column's value_regex list |
| finance.ar_payment | Exact duplicate rows (re-delivered extract) | 44 | ar_payment_id | deduplicate on ar_payment_id (exact copies collapse) |
| finance.ar_payment | Rows with an empty primary key | 9 | ar_payment_id | expectation ar_payment_id IS NOT NULL -> DROP ROW |
| finance.ap_invoice | Enum values with stray whitespace / wrong case | 106 | match_status, payment_method | trim + case-fold, then map to the canonical value of the column's value_regex list |
| finance.ap_invoice | Dates in dd/MM/yyyy | 77 | invoice_date | parse with yyyy-MM-dd first, fall back to dd/MM/yyyy |
| finance.ap_invoice | Exact duplicate rows (re-delivered extract) | 17 | ap_invoice_id | deduplicate on ap_invoice_id (exact copies collapse) |
| finance.ap_invoice | Rows with an empty primary key | 3 | ap_invoice_id | expectation ap_invoice_id IS NOT NULL -> DROP ROW |
| finance.ap_payment | Enum values with stray whitespace / wrong case | 91 | payment_approval_status, payment_method | trim + case-fold, then map to the canonical value of the column's value_regex list |
| finance.ap_payment | Exact duplicate rows (re-delivered extract) | 16 | ap_payment_id | deduplicate on ap_payment_id (exact copies collapse) |
| finance.ap_payment | Rows with an empty primary key | 3 | ap_payment_id | expectation ap_payment_id IS NOT NULL -> DROP ROW |
| finance.cogs_allocation | Enum values with stray whitespace / wrong case | 416 | allocation_method, costing_type, price_control_indicator, release_status, variance_category | trim + case-fold, then map to the canonical value of the column's value_regex list |
| finance.cogs_allocation | Exact duplicate rows (re-delivered extract) | 27 | cogs_allocation_id | deduplicate on cogs_allocation_id (exact copies collapse) |
| finance.cogs_allocation | Rows with an empty primary key | 5 | cogs_allocation_id | expectation cogs_allocation_id IS NOT NULL -> DROP ROW |
| finance.standard_cost | Enum values with stray whitespace / wrong case | 74 | approval_status, costing_type, release_status | trim + case-fold, then map to the canonical value of the column's value_regex list |
| finance.standard_cost | Updated duplicates (same PK, older version) | 17 | standard_cost_id, cost_estimate_modified_timestamp | deduplicate on standard_cost_id keeping the row with the latest cost_estimate_modified_timestamp |
| finance.standard_cost | Rows with an empty primary key | 2 | standard_cost_id | expectation standard_cost_id IS NOT NULL -> DROP ROW |

## Row counts

113 516 CSV rows (112 018 after the silver rules) in 116 files, 38.1 MB.

| domain | table | scope | CSV rows | clean rows | MB | dedup_order_column |
|---|---|---|---|---|---|---|
| product | sku | full | 89 | 89 | 0.05 | last_updated_timestamp |
| product | gtin_registry | full | 89 | 89 | 0.03 | last_updated_timestamp |
| product | hierarchy | full | 18 | 18 | 0.01 | updated_timestamp |
| product | product_bom | full | 89 | 89 | 0.03 | - |
| product | bom_line | full | 265 | 265 | 0.08 | last_modified_timestamp |
| product | formulation | full | 89 | 89 | 0.04 | last_modified_timestamp |
| product | formulation_ingredient | full | 217 | 217 | 0.09 | updated_timestamp |
| product | packaging_spec | full | 89 | 89 | 0.04 | last_modified_timestamp |
| product | label_spec | full | 89 | 89 | 0.06 | last_modified_timestamp |
| product | brand | full | 3 | 3 | 0.00 | last_updated_timestamp |
| product | product_category | full | 17 | 17 | 0.01 | updated_timestamp |
| product | material | full | 76 | 76 | 0.02 | last_updated_timestamp |
| product | category | full | 89 | 89 | 0.00 | - |
| manufacturing | manufacturing_facility | bootcamp | 4 | 4 | 0.00 | last_modified_timestamp |
| manufacturing | production_line | bootcamp | 16 | 16 | 0.01 | last_modified_timestamp |
| manufacturing | work_center | bootcamp | 49 | 48 | 0.02 | modified_timestamp |
| manufacturing | manufacturing_bom | bootcamp | 121 | 119 | 0.04 | last_modified_timestamp |
| manufacturing | routing | bootcamp | 121 | 119 | 0.05 | last_modified_timestamp |
| manufacturing | production_order | bootcamp | 2 021 | 1 997 | 0.83 | last_modified_timestamp |
| manufacturing | batch_record | bootcamp | 2 021 | 1 997 | 0.71 | last_modified_timestamp |
| manufacturing | yield_record | bootcamp | 2 021 | 1 997 | 0.66 | last_modified_timestamp |
| manufacturing | production_confirmation | bootcamp | 6 063 | 5 991 | 2.28 | last_modified_timestamp |
| manufacturing | planned_order | bootcamp | 2 426 | 2 397 | 0.93 | last_modified_timestamp |
| manufacturing | equipment | bootcamp | 160 | 160 | 0.08 | - |
| consumer | shopper | bootcamp | 3 066 | 3 000 | 1.18 | updated_timestamp |
| consumer | household | bootcamp | 1 840 | 1 800 | 0.67 | last_updated_timestamp |
| consumer | address | bootcamp | 3 219 | 3 150 | 1.33 | updated_timestamp |
| consumer | loyalty_account | bootcamp | 1 978 | 1 935 | 0.71 | updated_timestamp |
| consumer | loyalty_transaction | bootcamp | 10 632 | 10 506 | 3.45 | updated_timestamp |
| consumer | preference | bootcamp | 2 886 | 2 824 | 1.07 | last_updated_timestamp |
| consumer | consent_record | bootcamp | 6 485 | 6 345 | 1.91 | updated_timestamp |
| consumer | dtc_order | bootcamp | 8 096 | 8 000 | 3.33 | updated_timestamp |
| consumer | dtc_order_line | bootcamp | 15 466 | 15 272 | 5.62 | updated_timestamp |
| consumer | subscription | bootcamp | 531 | 520 | 0.18 | updated_timestamp |
| consumer | loyalty_program | bootcamp | 1 | 1 | 0.00 | record_audit_updated |
| consumer | loyalty_tier | bootcamp | 4 | 4 | 0.00 | updated_timestamp |
| supply | demand_plan | full | 45 | 45 | 0.02 | last_modified_timestamp |
| supply | forecast_version | full | 45 | 45 | 0.02 | modified_timestamp |
| supply | inventory_policy | full | 45 | 45 | 0.02 | last_modified_timestamp |
| supply | safety_stock | full | 70 | 70 | 0.03 | modified_timestamp |
| supply | replenishment_order | full | 70 | 70 | 0.03 | last_modified_timestamp |
| supply | network_node | full | 45 | 45 | 0.02 | last_modified_timestamp |
| supply | network_lane | full | 45 | 45 | 0.02 | last_modified_timestamp |
| supply | atp_record | full | 70 | 70 | 0.03 | updated_timestamp |
| supply | sop_cycle | full | 45 | 45 | 0.02 | last_modified_timestamp |
| supply | consensus_demand | full | 70 | 70 | 0.03 | last_modified_timestamp |
| supply | sku_planning_param | full | 45 | 45 | 0.02 | last_modified_timestamp |
| sales | trade_account | full | 25 | 25 | 0.01 | record_updated_timestamp |
| sales | account_contact | full | 45 | 45 | 0.02 | last_modified_timestamp |
| sales | account_address | full | 45 | 45 | 0.02 | last_modified_timestamp |
| sales | retail_store | full | 100 | 100 | 0.03 | last_modified_timestamp |
| sales | order | full | 120 | 120 | 0.05 | modified_timestamp |
| sales | invoice | full | 120 | 120 | 0.05 | last_modified_timestamp |
| sales | pricing_agreement | full | 45 | 45 | 0.02 | modified_timestamp |
| sales | pos_transaction | full | 70 | 70 | 0.03 | - |
| sales | return_order | full | 70 | 70 | 0.04 | modified_timestamp |
| sales | territory | full | 18 | 18 | 0.01 | modified_timestamp |
| sales | rep | full | 40 | 40 | 0.02 | modified_timestamp |
| sales | price_list | full | 45 | 45 | 0.02 | modified_timestamp |
| sales | price_list_item | full | 45 | 45 | 0.02 | modified_timestamp |
| sales | assignment | full | 40 | 40 | 0.01 | modified_timestamp |
| quality | inspection_plan | full | 45 | 45 | 0.02 | last_modified_timestamp |
| quality | inspection_lot | full | 70 | 70 | 0.03 | last_modified_timestamp |
| quality | inspection_result | full | 70 | 70 | 0.03 | record_updated_timestamp |
| quality | usage_decision | full | 70 | 70 | 0.03 | record_updated_timestamp |
| quality | nonconformance | full | 70 | 70 | 0.04 | updated_timestamp |
| quality | capa | full | 70 | 70 | 0.04 | last_modified_timestamp |
| quality | batch_release | full | 70 | 70 | 0.03 | last_modified_timestamp |
| quality | certificate_of_analysis | full | 70 | 70 | 0.03 | modified_timestamp |
| quality | product_complaint | full | 70 | 70 | 0.05 | last_modified_timestamp |
| quality | specification | full | 45 | 45 | 0.02 | last_modified_timestamp |
| distribution | distribution_facility | full | 5 | 5 | 0.00 | modified_timestamp |
| distribution | storage_location | full | 45 | 45 | 0.02 | last_modified_timestamp |
| distribution | inbound_receipt | full | 70 | 70 | 0.03 | last_modified_timestamp |
| distribution | inbound_receipt_line | full | 70 | 70 | 0.03 | last_modified_timestamp |
| distribution | outbound_order | full | 70 | 70 | 0.03 | last_modified_timestamp |
| distribution | outbound_order_line | full | 70 | 70 | 0.03 | - |
| distribution | pick_task | full | 70 | 70 | 0.03 | last_modified_timestamp |
| distribution | shipment | full | 70 | 70 | 0.04 | last_modified_timestamp |
| distribution | inventory_position | full | 45 | 45 | 0.02 | last_updated_timestamp |
| distribution | load_plan | full | 70 | 70 | 0.03 | last_modified_timestamp |
| procurement | supplier | full | 60 | 60 | 0.03 | modified_timestamp |
| procurement | supplier_site | full | 45 | 45 | 0.02 | last_modified_timestamp |
| procurement | supplier_contract | full | 45 | 45 | 0.02 | last_modified_timestamp |
| procurement | contract_line | full | 45 | 45 | 0.02 | last_modified_timestamp |
| procurement | purchase_requisition | full | 70 | 70 | 0.03 | last_modified_timestamp |
| procurement | purchase_order | full | 70 | 70 | 0.03 | modified_timestamp |
| procurement | po_line | full | 70 | 70 | 0.02 | last_modified_timestamp |
| procurement | goods_receipt | full | 70 | 70 | 0.03 | last_modified_timestamp |
| procurement | supplier_invoice | full | 70 | 70 | 0.03 | modified_timestamp |
| procurement | invoice_line | full | 70 | 70 | 0.03 | modified_timestamp |
| procurement | spend_category | full | 20 | 20 | 0.01 | last_modified_timestamp |
| procurement | approved_supplier_list | full | 45 | 45 | 0.02 | last_modified_timestamp |
| promotion | trade_promotion | full | 45 | 45 | 0.02 | last_modified_timestamp |
| promotion | event | full | 70 | 70 | 0.03 | modified_timestamp |
| promotion | event_sku | full | 70 | 70 | 0.03 | modified_timestamp |
| promotion | trade_calendar | full | 45 | 45 | 0.01 | last_modified_timestamp |
| promotion | trade_spend_allocation | full | 70 | 70 | 0.03 | modified_timestamp |
| promotion | funding_agreement | full | 45 | 45 | 0.03 | last_modified_timestamp |
| promotion | accrual | full | 70 | 70 | 0.03 | modified_timestamp |
| promotion | deduction | full | 70 | 70 | 0.03 | modified_timestamp |
| promotion | deduction_settlement | full | 70 | 70 | 0.02 | last_modified_timestamp |
| promotion | promoted_price | full | 45 | 45 | 0.01 | last_modified_timestamp |
| finance | cost_center | bootcamp | 41 | 40 | 0.01 | last_modified_timestamp |
| finance | profit_center | bootcamp | 16 | 16 | 0.01 | last_modified_timestamp |
| finance | gl_account | bootcamp | 159 | 156 | 0.06 | last_modified_timestamp |
| finance | ledger | bootcamp | 7 | 7 | 0.00 | last_modified_timestamp |
| finance | journal_entry | bootcamp | 5 370 | 5 306 | 1.64 | modified_timestamp |
| finance | journal_entry_line | bootcamp | 17 579 | 17 370 | 3.47 | - |
| finance | ar_invoice | bootcamp | 4 460 | 4 407 | 1.46 | modified_timestamp |
| finance | ar_payment | bootcamp | 4 497 | 4 444 | 1.77 | modified_timestamp |
| finance | ap_invoice | bootcamp | 1 763 | 1 743 | 0.66 | modified_timestamp |
| finance | ap_payment | bootcamp | 1 647 | 1 628 | 0.61 | modified_timestamp |
| finance | cogs_allocation | bootcamp | 2 711 | 2 679 | 0.89 | modified_timestamp |
| finance | standard_cost | bootcamp | 876 | 857 | 0.34 | cost_estimate_modified_timestamp |
| finance | company_code | bootcamp | 6 | 6 | 0.00 | record_audit_updated |

## Regenerate and verify

```bash
# from the repository root
python3 -I tools/generate_data.py            # writes bootcamp/data and full_model/data (CSVs, manifests, READMEs)
python3 -I tools/generate_data.py --seed 20261029   # same as the default
python3 -I tools/verify_data.py              # checks + storyline KPIs; exit code 1 on any violation
```

Python 3.10+, standard library only. The output is byte-identical for the same seed. `generate_data.py` fails if both data folders together exceed 39.5 MB (budget 40 MB). Generic tables (the 65 full-scope tables outside the curated set) are filled by the model-driven engine (`tools/datagen/engine.py`, with coherence hooks in `curated_generic.py` for retail stores, POS records, account contacts and shipments); the 36 core tables, the whole product domain (brand, category, SKU and the specifications: material, formulation, ingredients, packaging, labels, GTIN registry, BOMs, hierarchy - `curated_product_specs.py`), sales.trade_account and distribution.distribution_facility are curated (`tools/datagen/curated_*.py`).

## Simplifications

* Row counts were sized to keep every CSV below 10 MB and the folder below 40 MB, so some tables are smaller than in the original sizing (e.g. ~8 000 DTC orders, ~15 000 order lines, ~11 000 loyalty movements).
* One standard VAT rate per market for all categories; shipping fees are flat and VAT-inclusive.
* Intercompany supplies are transferred at standard cost without a margin; there is no PP&E cost account (only accumulated depreciation 1290) and no dividend or tax postings.
* All companies, retailers, carriers (NORRPOST, FJORDPOST, ...) and equipment vendors are fictional. Names of well-known business software (SAP S/4HANA, Salesforce Commerce Cloud, Siemens Opcenter, Veeva Vault) and PLC types appear only as system identifiers (`source_system_*`, `record_source_system`).
* B2B billing is summarised to one GL document per company code and month; brand splits of B2B invoices follow each customer's assortment mix.
* Generic (full-scope) tables are realistic in shape and referential integrity but are not story-driven.

