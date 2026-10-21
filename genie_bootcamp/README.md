# Databricks Genie Bootcamp — Scandinavian Retail

A hands-on bootcamp that builds a medallion lakehouse (Bronze → Silver → Gold) on synthetic retail data and
puts a **Databricks AI/BI Genie** space on top of it. Participants run every notebook manually, step by step.

**Scenario:** a retailer with 10 stores in **Sweden, Norway and Denmark** plus one online store. It sells
three Scandinavian brands, with 5 products each:

| Brand | Home country | Category | Seasonal peak |
|---|---|---|---|
| Electrolux | Sweden | Home Appliances | Black Friday |
| LEGO | Denmark | Toys | Christmas |
| Helly Hansen | Norway | Outdoor Apparel | Winter (Oct–Feb) |

> All data is **synthetic**. The brand names are used for realism only. Every price, cost, volume, customer and
> financial figure is invented and has no connection to the real companies. PII is fake (`example.com` emails,
> `+46 000 ...` style phone numbers). Amounts are in **EUR**.

---

## Repository layout

```
data/raw/<entity>/2026-10-21-raw-<entity>.csv   27 source extracts
notebooks/2026-10-21-00-setup.py                catalog, schemas, volume, copy CSVs
notebooks/2026-10-21-01-bronze.py               raw ingestion (PySpark)
notebooks/2026-10-21-02-silver.py               cleaning + conforming (SQL + PySpark)
notebooks/2026-10-21-03-gold.py                 star schema + metric validation (SQL)
genie/2026-10-21-genie-instructions.md          Genie space instructions + sample questions
scripts/2026-10-21-generate-synthetic-data.py   reproducible data generator (seed 42)
```

## Prerequisites
- A Unity Catalog–enabled workspace, with permission to create a catalog (or an existing catalog you can use;
  set the `catalog` widget accordingly)
- Serverless or a DBR 14.3+ cluster (PySpark 3.5 functions such as `F.nullif` are used)
- A SQL warehouse (Pro or Serverless) for the Genie space
- This repo cloned as a **Git folder** (Workspace → Create → Git folder → this repo, branch `feature/bootcamp_notebook`)

## Demo run order

| Step | Notebook / action | What participants see |
|---|---|---|
| 00 | `2026-10-21-00-setup` | Catalog `retail_bootcamp`; schemas `landing`, `bronze`, `silver`, `gold`; volume `landing.raw_files` with 27 CSVs |
| 01 | `2026-10-21-01-bronze` | 27 `bronze.<system>_<entity>_raw` tables, all STRING, with lineage columns; the raw quality issues |
| 02 | `2026-10-21-02-silver` | 15 clean tables + `order_items_quarantine`; data-quality summary |
| 03 | `2026-10-21-03-gold` | 6 dims + 6 facts with comments and PK/FK; the 5 metric values checked against this README |
| 04 | Create the Genie space | See "Create the Genie space" below |

Every notebook can be re-run safely.

## Source systems → Bronze tables

| Source | Code | Extracts → `bronze.<code>_<entity>_raw` |
|---|---|---|
| CRM | `crm` | customers, customer_addresses, loyalty_members |
| E-commerce | `ecom` | web_sessions, cart_events, online_orders, online_order_items |
| POS | `pos` | store_orders, store_order_items |
| ERP | `erp` | products, product_categories, suppliers, purchase_orders |
| WMS | `wms` | inventory_snapshots, inventory_movements, shipments |
| Payment gateway | `pay` | payments, refunds |
| Returns portal | `rtn` | returns |
| Marketing | `mkt` | promotions, campaigns |
| Finance GL | `fin` | gl_entries, budgets, cost_centres |
| Master data | `mdm` | stores, channels, country_region |

Some extracts have no Silver table of their own. loyalty_members, product_categories, channels and
country_region enrich other Silver tables. customer_addresses, cart_events, inventory_movements, refunds,
campaigns and cost_centres stay in Bronze as extra material for exploration exercises.

## Data volumes

| Item | Volume |
|---|---|
| Customers | 200 (Sweden 80, Norway 62, Denmark 55, Faroe Islands 3) + 6 duplicate rows |
| Products / brands | 15 / 3 |
| Stores | 10 physical + 1 online (ON01) |
| Order lines | 2,001 raw → **1,990 valid** + 11 quarantined, in 1,324 orders (2024-01 to 2026-09) |
| Web sessions | 5,000 (431 converted) |
| Inventory | 14,850 rows: 15 products × 11 locations × 90 days |
| Returns | 159 |
| Finance | 33 months × 11 stores of GL actuals and budget |

## Injected data-quality issues (fixed in Silver)

| Issue | Where | Fix |
|---|---|---|
| Exact duplicate rows | customers (6), products (2), store_order_items (8), payments (5), web_sessions (10) | `QUALIFY ROW_NUMBER()` / `dropDuplicates` on the business key |
| Extra spaces and mixed casing | names, cities, countries, loyalty tiers, order status, payment methods | `trim`, `initcap`, mapping tables |
| Non-ISO date `dd.MM.yyyy` | customers.signup_date (~15 % of rows) | `coalesce(try_to_date(.., 'yyyy-MM-dd'), try_to_date(.., 'dd.MM.yyyy'))` |
| Native country names | Sverige, Norge, Danmark | CASE mapping to English names |
| Country without a region | Faroe Islands (3 customers) | region = `Unassigned` |
| Quantity 0 | 8 order lines | `silver.order_items_quarantine`, reason `QUANTITY_NOT_POSITIVE` |
| Unknown customer | 2 orders / 3 lines for `C9999` | quarantine, reason `UNKNOWN_CUSTOMER` |

## Gold star schema

**Dimensions:** `dim_customer`, `dim_product`, `dim_store`, `dim_date` (2024–2026, Scandinavian public holidays),
`dim_promotion` (with `PR00` = no promotion), `dim_supplier`.

**Facts:** `fact_order_line`, `fact_web_session`, `fact_inventory_daily`, `fact_returns`, `fact_shipment`,
`fact_finance_monthly`.

Modelling notes:
- Online orders have `store_id = 'ON01'`. Warehouse `WH01` stock is reported under `ON01` in `fact_inventory_daily`.
- `customer_segment`: VIP = lifetime net sales ≥ 2,000 EUR or Platinum tier. New = signed up within 180 days of
  2026-09-30, or at most 1 order. Everything else is Regular.
- `is_on_time` = delivered within the 3-day delivery promise.
- `fact_finance_monthly` comes from the general ledger and is **not** additive with order-line revenue.

## The 5 bootcamp metrics — actual values

These are checked by the last cell of `03-gold`. Genie answers should match them.

| # | Metric | Definition | Value |
|---|---|---|---|
| 1 | Net Revenue | `SUM(net_sales) − SUM(refund_amount)` | **604,798.15 EUR** (650,801.55 net sales − 46,003.40 refunds) |
| 2 | Gross Margin % | `SUM(gross_profit) / SUM(net_sales) × 100` | **40.84 %** |
| 3 | Online Conversion Rate % | sessions with `ordered_flag` / total sessions × 100 | **8.62 %** (431 / 5,000) |
| 4 | Return Rate % | `SUM(return_qty) / SUM(quantity) × 100` | **7.19 %** (175 / 2,435 units) |
| 5 | Stock-out Rate % | rows with `is_stock_out` / total inventory rows × 100 | **2.44 %** (363 / 14,850) |

Net sales split: Electrolux ≈ 404k, Helly Hansen ≈ 128k, LEGO ≈ 119k EUR. Store channel ≈ 443k, Online ≈ 208k EUR.

## Create the Genie space

1. Open **Genie** → **New**, and pick a Pro or Serverless SQL warehouse.
2. Add the tables from `retail_bootcamp.gold`: all six `dim_*` and all six `fact_*` tables.
3. Open **Instructions** and paste the *General instructions* section from `genie/2026-10-21-genie-instructions.md`.
4. Add the SQL expressions and the example query from the same file.
5. Add the 8 sample questions.
6. Test with the 5 metrics above. For example, ask "What is our gross margin %?" and check that the answer is 40.8 %.

## Regenerating the data

```bash
python scripts/2026-10-21-generate-synthetic-data.py   # writes data/raw/..., seed 42 → identical output
```
If you change the seed or the volumes, update `EXPECTED` in `03-gold` and the metric table above.
