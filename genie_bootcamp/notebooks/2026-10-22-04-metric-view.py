# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 04 · Metric View — Retail Bootcamp KPIs (SQL)
# MAGIC
# MAGIC One governed Unity Catalog **metric view**, `retail_bootcamp.gold.kpi_metrics`, holding the 5 headline KPIs.
# MAGIC Genie, dashboards and SQL users all read the same formula, so they all get the same number.
# MAGIC
# MAGIC | # | KPI | Formula | Validated value |
# MAGIC |---|---|---|---|
# MAGIC | 1 | 💶 Net Revenue | `SUM(net_sales) − SUM(refund_amount)` | 604,798.15 EUR |
# MAGIC | 2 | 📈 Gross Margin % | `SUM(gross_profit) / SUM(net_sales)` | 40.84 % |
# MAGIC | 3 | 🛒 Online Conversion Rate % | ordered sessions / all web sessions | 8.62 % |
# MAGIC | 4 | ↩️ Return Rate % | `SUM(return_qty) / SUM(quantity)` (units) | 7.19 % |
# MAGIC | 5 | 📦 Stock-out Rate % | stock-out snapshots / all snapshots | 2.44 % |
# MAGIC
# MAGIC Formulas follow `genie_one/2026-10-21-kpi-methodology.md`. Percentages are stored as **0–1 ratios** and
# MAGIC displayed as % by the `percentage` format.
# MAGIC
# MAGIC **Grain of the source:** one row per **month × store** (33 months × 11 stores). Each fact is aggregated
# MAGIC to that grain on its own and then joined, so returns, web sessions and stock never multiply sales rows.
# MAGIC
# MAGIC > Run `03-gold` first. The view uses fully qualified names in `retail_bootcamp`; if you use another catalog,
# MAGIC > replace `retail_bootcamp` in the cell below.
# MAGIC >
# MAGIC > 🔐 After `05-governance` the view returns only the data the signed-in user is entitled to (row filters on the
# MAGIC > gold tables apply through the view). The validated values hold for an **admin before 05 adds Services & Gifts**.
# MAGIC > Non-admins see empty Online Conversion, because web sessions are admin-only.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Create the metric view
# MAGIC
# MAGIC | Source CTE | Fact table | Dated by | Notes |
# MAGIC |---|---|---|---|
# MAGIC | `spine` | `dim_date` × `dim_store` | month | Every month (2024-01 → 2026-09) × every store, even with no sales. Not built on finance, because `05-governance` makes finance admin-only |
# MAGIC | `order_agg` | `fact_order_line` | order date | Net sales, gross profit, units |
# MAGIC | `returns_agg` | `fact_returns` | **return date** | Refunds and returned units |
# MAGIC | `web_session_agg` | `fact_web_session` | session date | Online only, so assigned to `ON01` |
# MAGIC | `inventory_agg` | `fact_inventory_daily` | snapshot date | Last 90 days only (2026-07-03 → 2026-09-30) |

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE VIEW retail_bootcamp.gold.kpi_metrics
# MAGIC WITH METRICS
# MAGIC LANGUAGE YAML
# MAGIC AS $$
# MAGIC   version: 1.1
# MAGIC   comment: >
# MAGIC     Nordhem Retail Group headline KPIs at month x store grain: Net Revenue, Gross Margin %,
# MAGIC     Online Conversion Rate %, Return Rate % and Stock-out Rate %. All amounts in EUR.
# MAGIC     Data runs 2024-01-01 to 2026-09-30. Stock-out data covers only 2026-07-03 to 2026-09-30.
# MAGIC   source: >
# MAGIC     WITH spine AS (
# MAGIC       SELECT m.month_date, s.store_id
# MAGIC       FROM (SELECT DISTINCT DATE_TRUNC('MONTH', date) AS month_date
# MAGIC             FROM retail_bootcamp.gold.dim_date
# MAGIC             WHERE date <= DATE'2026-09-30') m
# MAGIC       CROSS JOIN retail_bootcamp.gold.dim_store s
# MAGIC     ),
# MAGIC     order_agg AS (
# MAGIC       SELECT DATE_TRUNC('MONTH', to_date(CAST(date_key AS STRING), 'yyyyMMdd')) AS month_date,
# MAGIC              store_id,
# MAGIC              SUM(net_sales)    AS net_sales,
# MAGIC              SUM(gross_profit) AS gross_profit,
# MAGIC              SUM(quantity)     AS units_sold
# MAGIC       FROM retail_bootcamp.gold.fact_order_line
# MAGIC       GROUP BY 1, 2
# MAGIC     ),
# MAGIC     returns_agg AS (
# MAGIC       SELECT DATE_TRUNC('MONTH', to_date(CAST(date_key AS STRING), 'yyyyMMdd')) AS month_date,
# MAGIC              store_id,
# MAGIC              SUM(refund_amount) AS refund_amount,
# MAGIC              SUM(return_qty)    AS returned_units
# MAGIC       FROM retail_bootcamp.gold.fact_returns
# MAGIC       GROUP BY 1, 2
# MAGIC     ),
# MAGIC     web_session_agg AS (
# MAGIC       SELECT DATE_TRUNC('MONTH', to_date(CAST(date_key AS STRING), 'yyyyMMdd')) AS month_date,
# MAGIC              'ON01' AS store_id,
# MAGIC              COUNT(*)               AS web_sessions,
# MAGIC              COUNT_IF(ordered_flag) AS web_orders
# MAGIC       FROM retail_bootcamp.gold.fact_web_session
# MAGIC       GROUP BY 1, 2
# MAGIC     ),
# MAGIC     inventory_agg AS (
# MAGIC       SELECT DATE_TRUNC('MONTH', to_date(CAST(date_key AS STRING), 'yyyyMMdd')) AS month_date,
# MAGIC              store_id,
# MAGIC              COUNT(*)               AS inv_snapshots,
# MAGIC              COUNT_IF(is_stock_out) AS stock_out_snapshots
# MAGIC       FROM retail_bootcamp.gold.fact_inventory_daily
# MAGIC       GROUP BY 1, 2
# MAGIC     )
# MAGIC     SELECT spine.month_date,
# MAGIC            spine.store_id,
# MAGIC            ds.store_name,
# MAGIC            ds.channel,
# MAGIC            ds.country,
# MAGIC            ds.region,
# MAGIC            COALESCE(oa.net_sales, 0)           AS net_sales,
# MAGIC            COALESCE(oa.gross_profit, 0)        AS gross_profit,
# MAGIC            COALESCE(oa.units_sold, 0)          AS units_sold,
# MAGIC            COALESCE(ra.refund_amount, 0)       AS refund_amount,
# MAGIC            COALESCE(ra.returned_units, 0)      AS returned_units,
# MAGIC            COALESCE(ws.web_sessions, 0)        AS web_sessions,
# MAGIC            COALESCE(ws.web_orders, 0)          AS web_orders,
# MAGIC            COALESCE(ia.inv_snapshots, 0)       AS inv_snapshots,
# MAGIC            COALESCE(ia.stock_out_snapshots, 0) AS stock_out_snapshots
# MAGIC     FROM spine
# MAGIC     LEFT JOIN order_agg       oa ON spine.month_date = oa.month_date AND spine.store_id = oa.store_id
# MAGIC     LEFT JOIN returns_agg     ra ON spine.month_date = ra.month_date AND spine.store_id = ra.store_id
# MAGIC     LEFT JOIN web_session_agg ws ON spine.month_date = ws.month_date AND spine.store_id = ws.store_id
# MAGIC     LEFT JOIN inventory_agg   ia ON spine.month_date = ia.month_date AND spine.store_id = ia.store_id
# MAGIC     LEFT JOIN retail_bootcamp.gold.dim_store ds ON spine.store_id = ds.store_id
# MAGIC
# MAGIC   dimensions:
# MAGIC     - name: Month
# MAGIC       expr: month_date
# MAGIC       display_name: Month
# MAGIC       comment: First day of the calendar month. Sales are dated by order date, returns by return date.
# MAGIC       format:
# MAGIC         type: date
# MAGIC         date_format: locale_short_month
# MAGIC       synonyms:
# MAGIC         - month_date
# MAGIC         - period
# MAGIC         - month_name
# MAGIC     - name: Year
# MAGIC       expr: YEAR(month_date)
# MAGIC       display_name: Year
# MAGIC       comment: Calendar year (2024, 2025, 2026). 2026 runs to 30 September only.
# MAGIC       synonyms:
# MAGIC         - calendar year
# MAGIC     - name: Season
# MAGIC       expr: >
# MAGIC         CASE WHEN MONTH(month_date) IN (12, 1, 2) THEN 'Winter'
# MAGIC              WHEN MONTH(month_date) IN (3, 4, 5)  THEN 'Spring'
# MAGIC              WHEN MONTH(month_date) IN (6, 7, 8)  THEN 'Summer'
# MAGIC              ELSE 'Autumn' END
# MAGIC       display_name: Season
# MAGIC       comment: Retail season, same rule as dim_date.season. Winter = Dec-Feb, Spring = Mar-May, Summer = Jun-Aug, Autumn = Sep-Nov.
# MAGIC     - name: Store
# MAGIC       expr: store_id
# MAGIC       display_name: Store
# MAGIC       comment: Store business key. ST01-ST10 are physical stores, ON01 is the online store.
# MAGIC       synonyms:
# MAGIC         - store_id
# MAGIC         - location
# MAGIC     - name: Store Name
# MAGIC       expr: store_name
# MAGIC       display_name: Store Name
# MAGIC       comment: Human-readable store name, e.g. Mall of Scandinavia or Online Store.
# MAGIC     - name: Channel
# MAGIC       expr: channel
# MAGIC       display_name: Channel
# MAGIC       comment: Sales channel, either Store (physical) or Online (web shop ON01).
# MAGIC       synonyms:
# MAGIC         - sales channel
# MAGIC         - store type
# MAGIC     - name: Country
# MAGIC       expr: country
# MAGIC       display_name: Country
# MAGIC       comment: Country of the store. The online store is run from Sweden.
# MAGIC     - name: Region
# MAGIC       expr: region
# MAGIC       display_name: Region
# MAGIC       comment: >
# MAGIC         STORE region (Scandinavia East = Sweden, West = Norway, South = Denmark). Scandinavia East
# MAGIC         includes the online store ON01; filter Channel = 'Store' for a like-for-like store comparison.
# MAGIC       synonyms:
# MAGIC         - store region
# MAGIC         - market
# MAGIC
# MAGIC   measures:
# MAGIC     - name: Net Revenue
# MAGIC       expr: SUM(net_sales) - SUM(refund_amount)
# MAGIC       display_name: Net Revenue
# MAGIC       comment: >
# MAGIC         KPI 1. Net sales after promotion discounts minus refunds for returns, in EUR.
# MAGIC         Full-period value 604,798.15 EUR. Use Net Sales when the user just says "revenue" or "sales".
# MAGIC       format:
# MAGIC         type: currency
# MAGIC         currency_code: EUR
# MAGIC         decimal_places:
# MAGIC           type: exact
# MAGIC           places: 2
# MAGIC       synonyms:
# MAGIC         - net revenue
# MAGIC         - revenue after returns
# MAGIC     - name: Net Sales
# MAGIC       expr: SUM(net_sales)
# MAGIC       display_name: Net Sales
# MAGIC       comment: Order-line sales after promotion discounts, before refunds, in EUR. The default meaning of "revenue" and "sales".
# MAGIC       format:
# MAGIC         type: currency
# MAGIC         currency_code: EUR
# MAGIC         decimal_places:
# MAGIC           type: exact
# MAGIC           places: 2
# MAGIC       synonyms:
# MAGIC         - revenue
# MAGIC         - sales
# MAGIC         - turnover
# MAGIC     - name: Refunds
# MAGIC       expr: SUM(refund_amount)
# MAGIC       display_name: Refunds
# MAGIC       comment: Amount refunded to customers for returns, in EUR, dated by return date.
# MAGIC       format:
# MAGIC         type: currency
# MAGIC         currency_code: EUR
# MAGIC         decimal_places:
# MAGIC           type: exact
# MAGIC           places: 2
# MAGIC       synonyms:
# MAGIC         - refund amount
# MAGIC     - name: Gross Margin Pct
# MAGIC       expr: SUM(gross_profit) / NULLIF(SUM(net_sales), 0)
# MAGIC       display_name: Gross Margin %
# MAGIC       comment: KPI 2. Gross profit (net sales minus COGS) as a share of net sales. Full-period value 40.84 %.
# MAGIC       format:
# MAGIC         type: percentage
# MAGIC         decimal_places:
# MAGIC           type: exact
# MAGIC           places: 1
# MAGIC       synonyms:
# MAGIC         - gross margin
# MAGIC         - margin
# MAGIC         - GM
# MAGIC     - name: Online Conversion Rate Pct
# MAGIC       expr: SUM(web_orders) / NULLIF(SUM(web_sessions), 0)
# MAGIC       display_name: Online Conversion Rate %
# MAGIC       comment: >
# MAGIC         KPI 3. Web sessions that ended in an order as a share of all web sessions (incl. anonymous).
# MAGIC         Online only (ON01); physical stores have no conversion rate. Full-period value 8.62 %.
# MAGIC       format:
# MAGIC         type: percentage
# MAGIC         decimal_places:
# MAGIC           type: exact
# MAGIC           places: 1
# MAGIC       synonyms:
# MAGIC         - conversion rate
# MAGIC         - conversion
# MAGIC         - web conversion
# MAGIC     - name: Return Rate Pct
# MAGIC       expr: SUM(returned_units) / NULLIF(SUM(units_sold), 0)
# MAGIC       display_name: Return Rate %
# MAGIC       comment: >
# MAGIC         KPI 4. Returned units as a share of units sold. Returns are dated by return date.
# MAGIC         Full-period value 7.19 % (175 / 2,435 units).
# MAGIC       format:
# MAGIC         type: percentage
# MAGIC         decimal_places:
# MAGIC           type: exact
# MAGIC           places: 1
# MAGIC       synonyms:
# MAGIC         - return rate
# MAGIC         - returns rate
# MAGIC     - name: Stock Out Rate Pct
# MAGIC       expr: SUM(stock_out_snapshots) / NULLIF(SUM(inv_snapshots), 0)
# MAGIC       display_name: Stock-out Rate %
# MAGIC       comment: >
# MAGIC         KPI 5. Daily product x location snapshots with available stock <= 0, as a share of all snapshots.
# MAGIC         Covers 2026-07-03 to 2026-09-30 only. Warehouse WH01 is reported as ON01. Full-period value 2.44 %.
# MAGIC       format:
# MAGIC         type: percentage
# MAGIC         decimal_places:
# MAGIC           type: exact
# MAGIC           places: 1
# MAGIC       synonyms:
# MAGIC         - stock out
# MAGIC         - stockout
# MAGIC         - out of stock
# MAGIC     - name: Units Sold
# MAGIC       expr: SUM(units_sold)
# MAGIC       display_name: Units Sold
# MAGIC       comment: Units sold on order lines.
# MAGIC       synonyms:
# MAGIC         - quantity
# MAGIC         - units
# MAGIC $$

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Validate against the README values
# MAGIC If any line says `DIFF`, the metric view and `kpi-methodology.md` disagree. Fix the view.
# MAGIC Run this as an admin, before `05-governance` (05 adds Services & Gifts sales, which moves the numbers).

# COMMAND ----------

row = spark.sql("""
  SELECT MEASURE(`Net Revenue`)                      AS net_revenue,
         MEASURE(`Gross Margin Pct`) * 100           AS gross_margin_pct,
         MEASURE(`Online Conversion Rate Pct`) * 100 AS conversion_pct,
         MEASURE(`Return Rate Pct`) * 100            AS return_rate_pct,
         MEASURE(`Stock Out Rate Pct`) * 100         AS stock_out_pct
  FROM retail_bootcamp.gold.kpi_metrics
""").first()

EXPECTED = {  # values recorded in README.md
    "Net Revenue (EUR)":        (row.net_revenue,      604798.15),
    "Gross Margin %":           (row.gross_margin_pct, 40.84),
    "Online Conversion Rate %": (row.conversion_pct,   8.62),
    "Return Rate %":            (row.return_rate_pct,  7.19),
    "Stock-out Rate %":         (row.stock_out_pct,    2.44),
}
for k, (a, v) in EXPECTED.items():
    status = "OK " if abs(round(float(a), 2) - v) < 0.01 else "DIFF"
    print(f"{status}  {k:<26} actual={float(a):>14,.2f}   expected={v:>14,.2f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Example queries
# MAGIC Measures are read with `MEASURE()` and dimensions are grouped with `GROUP BY ALL`.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- All 5 KPIs by channel
# MAGIC SELECT `Channel`,
# MAGIC        MEASURE(`Net Revenue`)                AS net_revenue,
# MAGIC        MEASURE(`Gross Margin Pct`)           AS gross_margin_pct,
# MAGIC        MEASURE(`Online Conversion Rate Pct`) AS online_conversion_pct,
# MAGIC        MEASURE(`Return Rate Pct`)            AS return_rate_pct,
# MAGIC        MEASURE(`Stock Out Rate Pct`)         AS stock_out_pct
# MAGIC FROM retail_bootcamp.gold.kpi_metrics
# MAGIC GROUP BY ALL
# MAGIC ORDER BY net_revenue DESC

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Monthly trend, last 12 months
# MAGIC SELECT `Month`,
# MAGIC        MEASURE(`Net Revenue`)                AS net_revenue,
# MAGIC        MEASURE(`Gross Margin Pct`)           AS gross_margin_pct,
# MAGIC        MEASURE(`Online Conversion Rate Pct`) AS online_conversion_pct,
# MAGIC        MEASURE(`Return Rate Pct`)            AS return_rate_pct,
# MAGIC        MEASURE(`Stock Out Rate Pct`)         AS stock_out_pct
# MAGIC FROM retail_bootcamp.gold.kpi_metrics
# MAGIC GROUP BY ALL
# MAGIC ORDER BY `Month` DESC
# MAGIC LIMIT 12

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Like-for-like store comparison by region (online excluded)
# MAGIC SELECT `Region`,
# MAGIC        MEASURE(`Net Sales`)        AS net_sales,
# MAGIC        MEASURE(`Gross Margin Pct`) AS gross_margin_pct,
# MAGIC        MEASURE(`Return Rate Pct`)  AS return_rate_pct
# MAGIC FROM retail_bootcamp.gold.kpi_metrics
# MAGIC WHERE `Channel` = 'Store'
# MAGIC GROUP BY ALL
# MAGIC ORDER BY net_sales DESC
