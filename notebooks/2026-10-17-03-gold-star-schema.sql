-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 03 · Gold star schema (SQL)
-- MAGIC
-- MAGIC 4 dimensions + 4 facts for the Genie space. **Every table and column has a COMMENT**, because Genie reads them.
-- MAGIC Primary and foreign keys are declared (informational constraints), so Genie knows the join paths.
-- MAGIC
-- MAGIC | Dimensions | Facts |
-- MAGIC |---|---|
-- MAGIC | `dim_product`, `dim_customer`, `dim_store`, `dim_date` | `fact_sales`, `fact_returns`, `fact_production`, `fact_finance` |
-- MAGIC
-- MAGIC Run order inside this notebook: **drop facts → recreate dimensions → create facts → validate**.
-- MAGIC Re-running this notebook recreates the tables and removes the row filters and masks, so re-run Notebook 04 afterwards.
-- MAGIC
-- MAGIC **Re-running after Notebook 04:** `silver.customers` is masked by then. Run this notebook as a member of `bootcamp_admins`, or first run the rollback cell in Notebook 04 (section 8). Otherwise masked names, emails and phones are copied into `gold.dim_customer` as if they were real values.

-- COMMAND ----------

USE CATALOG fashion_bootcamp;
USE SCHEMA gold;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1. Drop the fact tables first (they hold foreign keys to the dimensions)

-- COMMAND ----------

DROP TABLE IF EXISTS fashion_bootcamp.gold.fact_returns;
DROP TABLE IF EXISTS fashion_bootcamp.gold.fact_sales;
DROP TABLE IF EXISTS fashion_bootcamp.gold.fact_production;
DROP TABLE IF EXISTS fashion_bootcamp.gold.fact_finance;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2. Dimensions

-- COMMAND ----------

-- dim_product
CREATE OR REPLACE TABLE fashion_bootcamp.gold.dim_product (
  product_id        STRING        NOT NULL COMMENT 'Product identifier, e.g. P001. Primary key.',
  product_name      STRING                 COMMENT 'Product name.',
  brand             STRING                 COMMENT 'Fashion house: YSL, Zara, Louis Vuitton, Chanel, Gucci, Dior, Prada, Armani.',
  brand_tier        STRING                 COMMENT 'Brand positioning: Luxury, Premium (Armani) or Fast Fashion (Zara).',
  category          STRING                 COMMENT 'Product category: Handbags, Leather Goods, Clothing, Shoes, Jewelry, Accessories, Perfumes.',
  collection        STRING                 COMMENT 'Collection the product belongs to, e.g. FW25, SS26 or Permanent.',
  material          STRING                 COMMENT 'Main material.',
  list_price_eur    DECIMAL(12,2)          COMMENT 'Current full retail price per unit in EUR.',
  unit_cost_eur     DECIMAL(12,2)          COMMENT 'Cost of goods per unit in EUR.',
  max_discount_pct  DECIMAL(5,2)           COMMENT 'Pricing policy cap: highest allowed discount percentage (0-100 scale). A sale with discount_pct above this is a policy breach.',
  CONSTRAINT pk_dim_product PRIMARY KEY (product_id)
)
COMMENT 'Product dimension: one row per product with brand, tier, category, price, cost and discount policy cap.';

INSERT INTO fashion_bootcamp.gold.dim_product
SELECT product_id, product_name, brand, brand_tier, category, collection, material,
       list_price_eur, unit_cost_eur, max_discount_pct
FROM fashion_bootcamp.silver.products;

-- COMMAND ----------

-- dim_customer
CREATE OR REPLACE TABLE fashion_bootcamp.gold.dim_customer (
  customer_id          STRING NOT NULL COMMENT 'Customer identifier, e.g. C001. Primary key.',
  customer_name        STRING          COMMENT 'Customer full name (PII, masked for users without PII access).',
  email                STRING          COMMENT 'Customer email address (PII, masked for users without PII access).',
  phone                STRING          COMMENT 'Customer phone number (PII, masked for users without PII access).',
  gender               STRING          COMMENT 'Customer gender: Female or Male.',
  age_group            STRING          COMMENT 'Age band derived from date of birth: 18-24, 25-34, 35-44, 45-54, 55+.',
  country              STRING          COMMENT 'Country where the customer lives.',
  city                 STRING          COMMENT 'City where the customer lives.',
  region               STRING          COMMENT 'Customer region (where the customer lives): Western, Northern, Southern, Central or Eastern Europe. Use this region for Online sales.',
  customer_segment     STRING          COMMENT 'Customer segment: VIC (Very Important Client), Regular or New.',
  loyalty_tier         STRING          COMMENT 'Loyalty programme tier: Platinum, Gold, Silver or Bronze.',
  first_purchase_date  DATE            COMMENT 'Date of the customer''s first purchase.',
  CONSTRAINT pk_dim_customer PRIMARY KEY (customer_id)
)
COMMENT 'Customer dimension: one row per customer with demographics, segment, loyalty tier and home region. Contains PII.';

INSERT INTO fashion_bootcamp.gold.dim_customer
SELECT customer_id, concat_ws(' ', first_name, last_name), email, phone, gender, age_group,
       country, city, region, customer_segment, loyalty_tier, first_purchase_date
FROM fashion_bootcamp.silver.customers;

-- COMMAND ----------

-- dim_store
CREATE OR REPLACE TABLE fashion_bootcamp.gold.dim_store (
  store_id        STRING NOT NULL COMMENT 'Store identifier, e.g. S01. Primary key.',
  store_name      STRING          COMMENT 'Store name.',
  channel         STRING          COMMENT 'Sales channel: Boutique, Department Store, Outlet or Online.',
  country         STRING          COMMENT 'Country where the store is located.',
  city            STRING          COMMENT 'City where the store is located.',
  region          STRING          COMMENT 'Store region (where the sale happened): Western, Northern, Southern, Central or Eastern Europe.',
  store_size_sqm  INT             COMMENT 'Selling area in square metres (0 for Online).',
  opening_date    DATE            COMMENT 'Date the store opened.',
  CONSTRAINT pk_dim_store PRIMARY KEY (store_id)
)
COMMENT 'Store dimension: one row per store or online shop with channel, location and region.';

INSERT INTO fashion_bootcamp.gold.dim_store
SELECT store_id, store_name, channel, country, city, region, store_size_sqm, opening_date
FROM fashion_bootcamp.silver.stores;

-- COMMAND ----------

-- dim_date: generated calendar 2024-01-01 to 2026-12-31
CREATE OR REPLACE TABLE fashion_bootcamp.gold.dim_date (
  date_key         INT     NOT NULL COMMENT 'Date key in yyyyMMdd format, e.g. 20251212. Primary key.',
  full_date        DATE             COMMENT 'Calendar date.',
  day_name         STRING           COMMENT 'Day of the week, e.g. Monday.',
  week_of_year     INT              COMMENT 'ISO week number (1-53).',
  month_num        INT              COMMENT 'Month number (1-12).',
  month_name       STRING           COMMENT 'Month name, e.g. December.',
  quarter          INT              COMMENT 'Calendar quarter (1-4).',
  year             INT              COMMENT 'Calendar year.',
  season           STRING           COMMENT 'Meteorological season: Winter (Dec-Feb), Spring (Mar-May), Summer (Jun-Aug), Autumn (Sep-Nov).',
  fashion_season   STRING           COMMENT 'Fashion selling season: SSyy = Spring/Summer (Feb-Jul), FWyy = Fall/Winter (Aug-Jan). January belongs to the previous year''s FW season.',
  sales_event      STRING           COMMENT 'Retail calendar event: Winter Sale (Jan), Valentines Week (Feb 7-14), Summer Sale (Jun 25-Jul 31), FW Launch (Sep 1-15), Black Friday Week (Nov 24-30), Holiday Season (Dec 1-24), otherwise Regular.',
  is_promo_period  BOOLEAN          COMMENT 'True during markdown periods: Winter Sale, Summer Sale and Black Friday Week.',
  is_weekend       BOOLEAN          COMMENT 'True on Saturday and Sunday.',
  CONSTRAINT pk_dim_date PRIMARY KEY (date_key)
)
COMMENT 'Date dimension (2024-2026) with fashion seasons and retail sales events for seasonality analysis.';

INSERT INTO fashion_bootcamp.gold.dim_date
SELECT
  date_key, full_date, day_name, week_of_year, month_num, month_name, quarter, year, season, fashion_season,
  sales_event,
  sales_event IN ('Winter Sale', 'Summer Sale', 'Black Friday Week') AS is_promo_period,
  is_weekend
FROM (
  SELECT
    CAST(date_format(d, 'yyyyMMdd') AS INT) AS date_key,
    d                                       AS full_date,
    date_format(d, 'EEEE')                  AS day_name,
    weekofyear(d)                           AS week_of_year,
    month(d)                                AS month_num,
    date_format(d, 'MMMM')                  AS month_name,
    quarter(d)                              AS quarter,
    year(d)                                 AS year,
    CASE WHEN month(d) IN (12, 1, 2) THEN 'Winter'
         WHEN month(d) IN (3, 4, 5)  THEN 'Spring'
         WHEN month(d) IN (6, 7, 8)  THEN 'Summer'
         ELSE 'Autumn' END                  AS season,
    CASE WHEN month(d) BETWEEN 2 AND 7 THEN concat('SS', date_format(d, 'yy'))
         WHEN month(d) >= 8            THEN concat('FW', date_format(d, 'yy'))
         ELSE concat('FW', right(CAST(year(d) - 1 AS STRING), 2)) END AS fashion_season,
    CASE WHEN month(d) = 1                                   THEN 'Winter Sale'
         WHEN month(d) = 2  AND day(d) BETWEEN 7 AND 14      THEN 'Valentines Week'
         WHEN (month(d) = 6 AND day(d) >= 25) OR month(d) = 7 THEN 'Summer Sale'
         WHEN month(d) = 9  AND day(d) <= 15                 THEN 'FW Launch'
         WHEN month(d) = 11 AND day(d) >= 24                 THEN 'Black Friday Week'
         WHEN month(d) = 12 AND day(d) <= 24                 THEN 'Holiday Season'
         ELSE 'Regular' END                 AS sales_event,
    dayofweek(d) IN (1, 7)                  AS is_weekend
  FROM (SELECT explode(sequence(DATE'2024-01-01', DATE'2026-12-31', INTERVAL 1 DAY)) AS d)
);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3. Facts

-- COMMAND ----------

-- fact_sales (order-line grain)
CREATE TABLE fashion_bootcamp.gold.fact_sales (
  sales_line_id        STRING        NOT NULL COMMENT 'Order line identifier, e.g. SL001. Primary key; one row per order line.',
  order_id             STRING                 COMMENT 'Order identifier; an order can contain several lines.',
  order_date_key       INT                    COMMENT 'Order date as yyyyMMdd; joins to dim_date.date_key.',
  customer_id          STRING                 COMMENT 'Customer who bought; joins to dim_customer.',
  product_id           STRING                 COMMENT 'Product sold; joins to dim_product.',
  store_id             STRING                 COMMENT 'Store or online shop where the sale happened; joins to dim_store.',
  quantity             INT                    COMMENT 'Units sold on the line.',
  unit_list_price_eur  DECIMAL(12,2)          COMMENT 'Full list price per unit at the time of sale, EUR.',
  gross_sales_eur      DECIMAL(12,2)          COMMENT 'Gross sales before discount = quantity x unit_list_price_eur, EUR.',
  discount_pct         DECIMAL(5,2)           COMMENT 'Discount given on the line, percentage on a 0-100 scale.',
  discount_amount_eur  DECIMAL(12,2)          COMMENT 'Discount amount = round(gross_sales_eur x discount_pct / 100, 2), EUR.',
  net_sales_eur        DECIMAL(12,2)          COMMENT 'Revenue. Net sales after discount = gross_sales_eur - discount_amount_eur, EUR. Use this column for revenue.',
  cogs_eur             DECIMAL(12,2)          COMMENT 'Cost of goods sold = quantity x unit_cost_eur, EUR.',
  gross_profit_eur     DECIMAL(12,2)          COMMENT 'Profit for product, brand, customer and promotion analysis = net_sales_eur - cogs_eur, EUR. Negative means a loss-making line.',
  promotion_type       STRING                 COMMENT 'Promotion applied: None, Summer Sale, Winter Sale, Black Friday, VIC Private Sale, Manager Override.',
  payment_method       STRING                 COMMENT 'Payment method, e.g. Credit Card, Debit Card, PayPal, Apple Pay, Bank Transfer.',
  order_status         STRING                 COMMENT 'Order line status: Completed, Partially Returned or Returned.',
  CONSTRAINT pk_fact_sales PRIMARY KEY (sales_line_id),
  CONSTRAINT fk_sales_date     FOREIGN KEY (order_date_key) REFERENCES fashion_bootcamp.gold.dim_date (date_key),
  CONSTRAINT fk_sales_customer FOREIGN KEY (customer_id)    REFERENCES fashion_bootcamp.gold.dim_customer (customer_id),
  CONSTRAINT fk_sales_product  FOREIGN KEY (product_id)     REFERENCES fashion_bootcamp.gold.dim_product (product_id),
  CONSTRAINT fk_sales_store    FOREIGN KEY (store_id)       REFERENCES fashion_bootcamp.gold.dim_store (store_id)
)
COMMENT 'Sales fact at order-line grain with gross, discount, net sales (revenue), COGS and gross profit in EUR.';

INSERT INTO fashion_bootcamp.gold.fact_sales
SELECT
  sales_line_id, order_id, order_date_key, customer_id, product_id, store_id, quantity,
  unit_list_price_eur, gross_sales_eur, discount_pct, discount_amount_eur,
  CAST(gross_sales_eur - discount_amount_eur AS DECIMAL(12,2))             AS net_sales_eur,
  cogs_eur,
  CAST(gross_sales_eur - discount_amount_eur - cogs_eur AS DECIMAL(12,2))  AS gross_profit_eur,
  promotion_type, payment_method, order_status
FROM (
  SELECT
    s.sales_line_id, s.order_id,
    CAST(date_format(s.order_date, 'yyyyMMdd') AS INT)                                    AS order_date_key,
    s.customer_id, s.product_id, s.store_id, s.quantity, s.unit_list_price_eur,
    CAST(s.quantity * s.unit_list_price_eur AS DECIMAL(12,2))                              AS gross_sales_eur,
    s.discount_pct,
    CAST(round(s.quantity * s.unit_list_price_eur * s.discount_pct / 100, 2) AS DECIMAL(12,2)) AS discount_amount_eur,
    CAST(s.quantity * p.unit_cost_eur AS DECIMAL(12,2))                                    AS cogs_eur,
    s.promotion_type, s.payment_method, s.order_status
  FROM fashion_bootcamp.silver.sales s
  JOIN fashion_bootcamp.silver.products p ON s.product_id = p.product_id
);

-- COMMAND ----------

-- fact_returns
CREATE TABLE fashion_bootcamp.gold.fact_returns (
  return_id                 STRING        NOT NULL COMMENT 'Return identifier, e.g. R001. Primary key.',
  sales_line_id             STRING                 COMMENT 'Original order line that was returned; joins to fact_sales.',
  order_id                  STRING                 COMMENT 'Original order identifier.',
  return_date_key           INT                    COMMENT 'Return date as yyyyMMdd; joins to dim_date.date_key.',
  customer_id               STRING                 COMMENT 'Customer who returned; joins to dim_customer.',
  product_id                STRING                 COMMENT 'Product returned; joins to dim_product.',
  store_id                  STRING                 COMMENT 'Store of the original sale; joins to dim_store.',
  return_qty                INT                    COMMENT 'Units returned. Return rate = SUM(return_qty) / SUM(fact_sales.quantity).',
  refund_amount_eur         DECIMAL(12,2)          COMMENT 'Amount refunded to the customer, EUR. Net revenue = SUM(net_sales_eur) - SUM(refund_amount_eur).',
  return_reason             STRING                 COMMENT 'Reason for return, e.g. Wrong Size, Changed Mind, Defective.',
  return_channel            STRING                 COMMENT 'How the item came back: Online, In Store or Courier.',
  is_restockable            BOOLEAN                COMMENT 'True if the item can be resold.',
  return_handling_cost_eur  DECIMAL(12,2)          COMMENT 'Cost of processing the return, EUR.',
  CONSTRAINT pk_fact_returns PRIMARY KEY (return_id),
  CONSTRAINT fk_returns_sales    FOREIGN KEY (sales_line_id)   REFERENCES fashion_bootcamp.gold.fact_sales (sales_line_id),
  CONSTRAINT fk_returns_date     FOREIGN KEY (return_date_key) REFERENCES fashion_bootcamp.gold.dim_date (date_key),
  CONSTRAINT fk_returns_customer FOREIGN KEY (customer_id)     REFERENCES fashion_bootcamp.gold.dim_customer (customer_id),
  CONSTRAINT fk_returns_product  FOREIGN KEY (product_id)      REFERENCES fashion_bootcamp.gold.dim_product (product_id),
  CONSTRAINT fk_returns_store    FOREIGN KEY (store_id)        REFERENCES fashion_bootcamp.gold.dim_store (store_id)
)
COMMENT 'Returns fact: one row per return with quantity, refund, reason, channel and handling cost.';

INSERT INTO fashion_bootcamp.gold.fact_returns
SELECT return_id, sales_line_id, order_id, CAST(date_format(return_date, 'yyyyMMdd') AS INT),
       customer_id, product_id, store_id, return_qty, refund_amount_eur, return_reason,
       return_channel, is_restockable, return_handling_cost_eur
FROM fashion_bootcamp.silver.returns;

-- COMMAND ----------

-- fact_production
CREATE TABLE fashion_bootcamp.gold.fact_production (
  production_batch_id        STRING        NOT NULL COMMENT 'Production batch identifier, e.g. PB001. Primary key.',
  product_id                 STRING                 COMMENT 'Product produced; joins to dim_product.',
  production_month_key       INT                    COMMENT 'First day of the production month as yyyyMMdd; joins to dim_date.date_key.',
  factory_country            STRING                 COMMENT 'Country of the factory or supplier.',
  factory_city               STRING                 COMMENT 'City of the factory or supplier.',
  units_planned              INT                    COMMENT 'Units planned for the batch.',
  units_produced             INT                    COMMENT 'Units actually produced.',
  units_defective            INT                    COMMENT 'Units failing quality control. Defect rate = units_defective / units_produced.',
  unit_production_cost_eur   DECIMAL(12,2)          COMMENT 'Production cost per unit, EUR.',
  total_production_cost_eur  DECIMAL(14,2)          COMMENT 'Total batch cost = units_produced x unit_production_cost_eur, EUR.',
  lead_time_days             INT                    COMMENT 'Days from order to delivery of the batch.',
  is_on_time                 BOOLEAN                COMMENT 'True if the batch was delivered on time; false means late.',
  CONSTRAINT pk_fact_production PRIMARY KEY (production_batch_id),
  CONSTRAINT fk_production_product FOREIGN KEY (product_id)           REFERENCES fashion_bootcamp.gold.dim_product (product_id),
  CONSTRAINT fk_production_month   FOREIGN KEY (production_month_key) REFERENCES fashion_bootcamp.gold.dim_date (date_key)
)
COMMENT 'Production fact: one row per batch with volumes, defects, cost, lead time and on-time delivery.';

INSERT INTO fashion_bootcamp.gold.fact_production
SELECT production_batch_id, product_id, CAST(date_format(production_month, 'yyyyMMdd') AS INT),
       factory_country, factory_city, units_planned, units_produced, units_defective,
       unit_production_cost_eur,
       CAST(units_produced * unit_production_cost_eur AS DECIMAL(14,2)),
       lead_time_days, is_on_time
FROM fashion_bootcamp.silver.production;

-- COMMAND ----------

-- fact_finance (store x month)
CREATE TABLE fashion_bootcamp.gold.fact_finance (
  finance_id                   STRING        NOT NULL COMMENT 'Finance row identifier, e.g. F001. Primary key; one row per store per month.',
  month_date_key               INT                    COMMENT 'First day of the month as yyyyMMdd; joins to dim_date.date_key.',
  store_id                     STRING                 COMMENT 'Store; joins to dim_store.',
  revenue_eur                  DECIMAL(14,2)          COMMENT 'Booked monthly store revenue (P&L), EUR. Different grain from fact_sales; never add the two together.',
  cogs_eur                     DECIMAL(14,2)          COMMENT 'Monthly cost of goods sold, EUR.',
  gross_profit_eur             DECIMAL(14,2)          COMMENT 'Monthly gross profit = revenue_eur - cogs_eur, EUR.',
  marketing_cost_eur           DECIMAL(14,2)          COMMENT 'Monthly marketing cost, EUR.',
  staff_cost_eur               DECIMAL(14,2)          COMMENT 'Monthly staff cost, EUR.',
  rent_cost_eur                DECIMAL(14,2)          COMMENT 'Monthly rent cost, EUR.',
  logistics_cost_eur           DECIMAL(14,2)          COMMENT 'Monthly logistics cost, EUR.',
  operating_profit_eur         DECIMAL(14,2)          COMMENT 'Operating profit = gross_profit_eur - marketing - staff - rent - logistics, EUR. Negative means a loss-making store.',
  budget_revenue_eur           DECIMAL(14,2)          COMMENT 'Budgeted monthly revenue, EUR.',
  budget_operating_profit_eur  DECIMAL(14,2)          COMMENT 'Budgeted monthly operating profit, EUR. Variance = operating_profit_eur - budget_operating_profit_eur.',
  CONSTRAINT pk_fact_finance PRIMARY KEY (finance_id),
  CONSTRAINT fk_finance_month FOREIGN KEY (month_date_key) REFERENCES fashion_bootcamp.gold.dim_date (date_key),
  CONSTRAINT fk_finance_store FOREIGN KEY (store_id)       REFERENCES fashion_bootcamp.gold.dim_store (store_id)
)
COMMENT 'Store P&L fact at store x month grain: revenue, costs, operating profit and budget. Use for P&L, costs and budget questions.';

INSERT INTO fashion_bootcamp.gold.fact_finance
SELECT
  finance_id, CAST(date_format(month_date, 'yyyyMMdd') AS INT), store_id,
  revenue_eur, cogs_eur,
  CAST(revenue_eur - cogs_eur AS DECIMAL(14,2)),
  marketing_cost_eur, staff_cost_eur, rent_cost_eur, logistics_cost_eur,
  CAST(revenue_eur - cogs_eur - marketing_cost_eur - staff_cost_eur - rent_cost_eur - logistics_cost_eur AS DECIMAL(14,2)),
  budget_revenue_eur, budget_operating_profit_eur
FROM fashion_bootcamp.silver.finance;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4. Validate the 5 Genie metrics

-- COMMAND ----------

WITH s AS (
  SELECT SUM(f.net_sales_eur) AS net, SUM(f.gross_sales_eur) AS gross, SUM(f.discount_amount_eur) AS disc,
         SUM(f.gross_profit_eur) AS gp, SUM(f.quantity) AS qty,
         COUNT_IF(f.discount_pct > p.max_discount_pct) AS breaches
  FROM fashion_bootcamp.gold.fact_sales f
  JOIN fashion_bootcamp.gold.dim_product p USING (product_id)
),
r AS (SELECT SUM(refund_amount_eur) AS refunds, SUM(return_qty) AS rqty FROM fashion_bootcamp.gold.fact_returns),
fin AS (SELECT SUM(operating_profit_eur) AS op, SUM(revenue_eur) AS rev, SUM(budget_operating_profit_eur) AS bop
        FROM fashion_bootcamp.gold.fact_finance),
m AS (
  SELECT '1. Net Revenue (EUR)'                    AS metric, CAST(s.net - r.refunds AS DECIMAL(14,2))             AS actual, CAST(16537.20 AS DECIMAL(14,2)) AS expected FROM s, r
  UNION ALL SELECT '2. Gross Margin %',              CAST(round(s.gp / s.net * 100, 2) AS DECIMAL(14,2)),        CAST(76.89 AS DECIMAL(14,2))   FROM s
  UNION ALL SELECT '3a. Discount Rate %',            CAST(round(s.disc / s.gross * 100, 2) AS DECIMAL(14,2)),    CAST(5.33 AS DECIMAL(14,2))    FROM s
  UNION ALL SELECT '3b. Discount policy breaches',   CAST(s.breaches AS DECIMAL(14,2)),                          CAST(2 AS DECIMAL(14,2))       FROM s
  UNION ALL SELECT '4. Return Rate %',               CAST(round(r.rqty * 100.0 / s.qty, 2) AS DECIMAL(14,2)),    CAST(26.67 AS DECIMAL(14,2))   FROM s, r
  UNION ALL SELECT '5a. Operating Margin %',         CAST(round(fin.op / fin.rev * 100, 2) AS DECIMAL(14,2)),    CAST(38.48 AS DECIMAL(14,2))   FROM fin
  UNION ALL SELECT '5b. Operating profit vs budget', CAST(fin.op - fin.bop AS DECIMAL(14,2)),                    CAST(-200000 AS DECIMAL(14,2)) FROM fin
)
SELECT metric, actual, expected, CASE WHEN actual = expected THEN 'PASS' ELSE 'FAIL' END AS result
FROM m ORDER BY metric;

-- COMMAND ----------

-- Detail checks: the loss line, the breaches and the loss-making store
SELECT 'Loss line' AS check_name, sales_line_id AS id, gross_profit_eur AS value, 'SL001, -4.60' AS expected
FROM fashion_bootcamp.gold.fact_sales WHERE gross_profit_eur < 0
UNION ALL
SELECT 'Policy breach', f.sales_line_id, f.discount_pct, 'SL001 and SL005'
FROM fashion_bootcamp.gold.fact_sales f JOIN fashion_bootcamp.gold.dim_product p USING (product_id)
WHERE f.discount_pct > p.max_discount_pct
UNION ALL
SELECT 'Loss-making store', concat(f.store_id, ' ', st.store_name), f.operating_profit_eur, 'S08 Warsaw Outlet, -68000'
FROM fashion_bootcamp.gold.fact_finance f JOIN fashion_bootcamp.gold.dim_store st USING (store_id)
WHERE f.operating_profit_eur < 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 5. Referential check (every count should be 0)

-- COMMAND ----------

SELECT 'fact_sales -> dim_customer' AS relationship, count(*) AS orphans
FROM fashion_bootcamp.gold.fact_sales f LEFT ANTI JOIN fashion_bootcamp.gold.dim_customer d USING (customer_id)
UNION ALL SELECT 'fact_sales -> dim_product', count(*)
FROM fashion_bootcamp.gold.fact_sales f LEFT ANTI JOIN fashion_bootcamp.gold.dim_product d USING (product_id)
UNION ALL SELECT 'fact_sales -> dim_store', count(*)
FROM fashion_bootcamp.gold.fact_sales f LEFT ANTI JOIN fashion_bootcamp.gold.dim_store d USING (store_id)
UNION ALL SELECT 'fact_sales -> dim_date', count(*)
FROM fashion_bootcamp.gold.fact_sales f LEFT ANTI JOIN fashion_bootcamp.gold.dim_date d ON f.order_date_key = d.date_key
UNION ALL SELECT 'fact_returns -> fact_sales', count(*)
FROM fashion_bootcamp.gold.fact_returns f LEFT ANTI JOIN fashion_bootcamp.gold.fact_sales d USING (sales_line_id)
UNION ALL SELECT 'fact_returns -> dim_date', count(*)
FROM fashion_bootcamp.gold.fact_returns f LEFT ANTI JOIN fashion_bootcamp.gold.dim_date d ON f.return_date_key = d.date_key
UNION ALL SELECT 'fact_production -> dim_product', count(*)
FROM fashion_bootcamp.gold.fact_production f LEFT ANTI JOIN fashion_bootcamp.gold.dim_product d USING (product_id)
UNION ALL SELECT 'fact_production -> dim_date', count(*)
FROM fashion_bootcamp.gold.fact_production f LEFT ANTI JOIN fashion_bootcamp.gold.dim_date d ON f.production_month_key = d.date_key
UNION ALL SELECT 'fact_finance -> dim_store', count(*)
FROM fashion_bootcamp.gold.fact_finance f LEFT ANTI JOIN fashion_bootcamp.gold.dim_store d USING (store_id)
UNION ALL SELECT 'fact_finance -> dim_date', count(*)
FROM fashion_bootcamp.gold.fact_finance f LEFT ANTI JOIN fashion_bootcamp.gold.dim_date d ON f.month_date_key = d.date_key;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 6. Genie space general instructions
-- MAGIC Paste these into the Genie space **Instructions** (also saved as `2026-10-17-genie-space-instructions.md`).
-- MAGIC
-- MAGIC - Revenue = `fact_sales.net_sales_eur`. Net revenue additionally subtracts refunds (`fact_returns.refund_amount_eur`).
-- MAGIC - Product, brand, customer and promotion profit = `gross_profit_eur`. P&L, costs and budget come from `fact_finance`.
-- MAGIC - Loss = `gross_profit_eur < 0` or `operating_profit_eur < 0`.
-- MAGIC - Discount policy breach = `discount_pct > max_discount_pct`. Percentages are on a 0-100 scale.
-- MAGIC - Defect rate = `units_defective / units_produced`.
-- MAGIC - Never add `fact_sales` revenue and `fact_finance` revenue together (different grain).
-- MAGIC - Seasonality uses `dim_date`: `month_name`, `season`, `fashion_season`, `sales_event`, `is_promo_period`.
-- MAGIC - Store region = where the sale happened; customer region = where the customer lives. For Online sales, use customer region.
-- MAGIC - VIC = Very Important Client.
