# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Gold — star schema for Genie (SQL)
# MAGIC
# MAGIC 6 dimensions + 6 facts, every table and column commented, PK/FK constraints declared
# MAGIC (informational in Unity Catalog — Genie uses them to understand joins).
# MAGIC
# MAGIC ```
# MAGIC dim_date ─┐            ┌─ dim_customer
# MAGIC dim_store ┼─ fact_order_line ─┼─ dim_product ── dim_supplier
# MAGIC           │            └─ dim_promotion
# MAGIC           ├─ fact_returns, fact_web_session, fact_inventory_daily, fact_shipment
# MAGIC           └─ fact_finance_monthly  (GL — never add to fact_order_line revenue)
# MAGIC ```

# COMMAND ----------

dbutils.widgets.text("catalog", "retail_bootcamp", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql("USE SCHEMA gold")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0 · Drop in dependency order (facts first) so the notebook can be re-run
# MAGIC The data's as-of date is **2026-09-30**; customer age and segment use it so results stay reproducible.

# COMMAND ----------

for t in ["fact_order_line", "fact_web_session", "fact_inventory_daily", "fact_returns", "fact_shipment",
          "fact_finance_monthly", "dim_customer", "dim_product", "dim_store", "dim_date", "dim_promotion", "dim_supplier"]:
    spark.sql(f"DROP TABLE IF EXISTS gold.{t}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Dimensions

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE TABLE gold.dim_date (
# MAGIC   date_key    INT     NOT NULL COMMENT 'Surrogate key in yyyyMMdd format, e.g. 20251128',
# MAGIC   date        DATE    NOT NULL COMMENT 'Calendar date',
# MAGIC   day_name    STRING  COMMENT 'Day of week name, e.g. Friday',
# MAGIC   week        INT     COMMENT 'ISO week number of the year (1-53)',
# MAGIC   month       INT     COMMENT 'Month number (1-12)',
# MAGIC   month_name  STRING  COMMENT 'Month name, e.g. November',
# MAGIC   quarter     INT     COMMENT 'Calendar quarter (1-4)',
# MAGIC   year        INT     COMMENT 'Calendar year',
# MAGIC   season      STRING  COMMENT 'Retail season: Winter (Dec-Feb), Spring (Mar-May), Summer (Jun-Aug), Autumn (Sep-Nov)',
# MAGIC   is_weekend  BOOLEAN COMMENT 'True on Saturday and Sunday',
# MAGIC   is_holiday  BOOLEAN COMMENT 'True on a public holiday shared by Sweden, Norway and Denmark (incl. Christmas Eve and New Year''s Eve)',
# MAGIC   CONSTRAINT pk_dim_date PRIMARY KEY (date_key)
# MAGIC ) COMMENT 'Calendar dimension 2024-01-01 to 2026-12-31. Use it for all seasonality, weekday and holiday questions.';
# MAGIC
# MAGIC INSERT INTO gold.dim_date
# MAGIC WITH days AS (SELECT explode(sequence(DATE'2024-01-01', DATE'2026-12-31', INTERVAL 1 DAY)) AS d),
# MAGIC holidays AS (
# MAGIC   SELECT to_date(h) AS h FROM VALUES
# MAGIC   ('2024-01-01'),('2024-03-29'),('2024-04-01'),('2024-05-01'),('2024-05-09'),('2024-05-20'),('2024-12-24'),('2024-12-25'),('2024-12-26'),('2024-12-31'),
# MAGIC   ('2025-01-01'),('2025-04-18'),('2025-04-21'),('2025-05-01'),('2025-05-29'),('2025-06-09'),('2025-12-24'),('2025-12-25'),('2025-12-26'),('2025-12-31'),
# MAGIC   ('2026-01-01'),('2026-04-03'),('2026-04-06'),('2026-05-01'),('2026-05-14'),('2026-05-25'),('2026-12-24'),('2026-12-25'),('2026-12-26'),('2026-12-31')
# MAGIC   AS t(h)
# MAGIC )
# MAGIC SELECT CAST(date_format(d, 'yyyyMMdd') AS INT), d, date_format(d, 'EEEE'), weekofyear(d), month(d),
# MAGIC        date_format(d, 'MMMM'), quarter(d), year(d),
# MAGIC        CASE WHEN month(d) IN (12, 1, 2) THEN 'Winter' WHEN month(d) IN (3, 4, 5) THEN 'Spring'
# MAGIC             WHEN month(d) IN (6, 7, 8) THEN 'Summer' ELSE 'Autumn' END,
# MAGIC        dayofweek(d) IN (1, 7),
# MAGIC        h IS NOT NULL
# MAGIC FROM days LEFT JOIN holidays ON d = h;

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE TABLE gold.dim_supplier (
# MAGIC   supplier_id     STRING NOT NULL COMMENT 'Supplier business key, e.g. SUP01',
# MAGIC   supplier_name   STRING COMMENT 'Supplier legal name',
# MAGIC   country         STRING COMMENT 'Supplier home country',
# MAGIC   lead_time_days  INT    COMMENT 'Standard replenishment lead time in days',
# MAGIC   CONSTRAINT pk_dim_supplier PRIMARY KEY (supplier_id)
# MAGIC ) COMMENT 'Suppliers: one per brand (Electrolux, LEGO, Helly Hansen).';
# MAGIC INSERT INTO gold.dim_supplier SELECT supplier_id, supplier_name, country, lead_time_days FROM silver.suppliers;
# MAGIC
# MAGIC CREATE TABLE gold.dim_product (
# MAGIC   product_id    STRING NOT NULL COMMENT 'Product business key, e.g. P006',
# MAGIC   sku           STRING COMMENT 'Stock keeping unit code',
# MAGIC   product_name  STRING COMMENT 'Full product name including brand',
# MAGIC   brand         STRING COMMENT 'Brand: Electrolux, LEGO or Helly Hansen',
# MAGIC   category      STRING COMMENT 'Top-level category: Home Appliances, Toys, Outdoor Apparel',
# MAGIC   sub_category  STRING COMMENT 'Sub-category, e.g. Dishwashers, Shell Jackets',
# MAGIC   supplier_name STRING COMMENT 'Name of the supplying company',
# MAGIC   list_price    DECIMAL(10,2) COMMENT 'Current list price in EUR incl. VAT',
# MAGIC   unit_cost     DECIMAL(10,2) COMMENT 'Standard unit cost in EUR (used for COGS)',
# MAGIC   CONSTRAINT pk_dim_product PRIMARY KEY (product_id)
# MAGIC ) COMMENT 'Product catalogue: 15 products, 5 per brand.';
# MAGIC INSERT INTO gold.dim_product
# MAGIC SELECT p.product_id, p.sku, p.product_name, p.brand, p.category, p.sub_category, s.supplier_name, p.list_price, p.unit_cost
# MAGIC FROM silver.products p LEFT JOIN silver.suppliers s ON p.supplier_id = s.supplier_id;
# MAGIC
# MAGIC CREATE TABLE gold.dim_store (
# MAGIC   store_id   STRING NOT NULL COMMENT 'Store business key; ST01-ST10 are physical stores, ON01 is the online store',
# MAGIC   store_name STRING COMMENT 'Store name',
# MAGIC   channel    STRING COMMENT 'Sales channel: Store or Online',
# MAGIC   country    STRING COMMENT 'Country where the store is located (online store is run from Sweden)',
# MAGIC   city       STRING COMMENT 'City where the store is located',
# MAGIC   region     STRING COMMENT 'Store sales region (Scandinavia East/West/South). This is the STORE region, not the customer region',
# MAGIC   CONSTRAINT pk_dim_store PRIMARY KEY (store_id)
# MAGIC ) COMMENT '10 stores in Sweden, Norway and Denmark plus 1 online channel.';
# MAGIC INSERT INTO gold.dim_store SELECT store_id, store_name, channel, country, city, region FROM silver.stores;
# MAGIC
# MAGIC CREATE TABLE gold.dim_promotion (
# MAGIC   promotion_id   STRING NOT NULL COMMENT 'Promotion key; PR00 means no promotion applied',
# MAGIC   promotion_name STRING COMMENT 'Promotion name, e.g. Black Friday 2025',
# MAGIC   promotion_type STRING COMMENT 'Seasonal discount, Clearance, Category discount, Loyalty or None',
# MAGIC   discount_pct   DECIMAL(5,2) COMMENT 'Discount percentage applied to the line',
# MAGIC   start_date     DATE COMMENT 'First day the promotion is valid',
# MAGIC   end_date       DATE COMMENT 'Last day the promotion is valid',
# MAGIC   CONSTRAINT pk_dim_promotion PRIMARY KEY (promotion_id)
# MAGIC ) COMMENT 'Marketing promotions, including a PR00 "No promotion" member so every order line joins.';
# MAGIC INSERT INTO gold.dim_promotion
# MAGIC SELECT promotion_id, promotion_name, promotion_type, discount_pct, start_date, end_date FROM silver.promotions
# MAGIC UNION ALL SELECT 'PR00', 'No promotion', 'None', 0, NULL, NULL;

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE TABLE gold.dim_customer (
# MAGIC   customer_id      STRING NOT NULL COMMENT 'Customer business key, e.g. C0042',
# MAGIC   customer_name    STRING COMMENT 'First and last name (synthetic)',
# MAGIC   email            STRING COMMENT 'Email address (fake, example.com)',
# MAGIC   phone            STRING COMMENT 'Phone number (fake)',
# MAGIC   gender           STRING COMMENT 'Female, Male or Other',
# MAGIC   age_group        STRING COMMENT 'Age band at 2026-09-30: 18-24, 25-34, 35-44, 45-54, 55-64, 65+',
# MAGIC   country          STRING COMMENT 'Customer home country',
# MAGIC   city             STRING COMMENT 'Customer home city',
# MAGIC   region           STRING COMMENT 'CUSTOMER home region derived from country; Unassigned when the country has no mapping (Faroe Islands)',
# MAGIC   loyalty_tier     STRING COMMENT 'Loyalty tier: None, Bronze, Silver, Gold, Platinum',
# MAGIC   customer_segment STRING COMMENT 'VIP = lifetime net sales >= 2000 EUR or Platinum; New = signed up within 180 days of 2026-09-30 or at most 1 order; otherwise Regular',
# MAGIC   signup_date      DATE   COMMENT 'Date the customer registered',
# MAGIC   CONSTRAINT pk_dim_customer PRIMARY KEY (customer_id)
# MAGIC ) COMMENT 'Customers in Sweden, Norway, Denmark (plus a few Faroe Islands customers with region Unassigned).';
# MAGIC
# MAGIC INSERT INTO gold.dim_customer
# MAGIC WITH spend AS (
# MAGIC   SELECT o.customer_id, COUNT(DISTINCT o.order_id) AS order_count,
# MAGIC          SUM(i.quantity * i.unit_price - i.discount_amount) AS lifetime_net_sales
# MAGIC   FROM silver.orders o JOIN silver.order_items i ON o.order_id = i.order_id
# MAGIC   GROUP BY o.customer_id
# MAGIC )
# MAGIC SELECT c.customer_id, concat(c.first_name, ' ', c.last_name), c.email, c.phone, c.gender,
# MAGIC        CASE WHEN floor(months_between(DATE'2026-09-30', c.date_of_birth) / 12) < 25 THEN '18-24'
# MAGIC             WHEN floor(months_between(DATE'2026-09-30', c.date_of_birth) / 12) < 35 THEN '25-34'
# MAGIC             WHEN floor(months_between(DATE'2026-09-30', c.date_of_birth) / 12) < 45 THEN '35-44'
# MAGIC             WHEN floor(months_between(DATE'2026-09-30', c.date_of_birth) / 12) < 55 THEN '45-54'
# MAGIC             WHEN floor(months_between(DATE'2026-09-30', c.date_of_birth) / 12) < 65 THEN '55-64'
# MAGIC             ELSE '65+' END,
# MAGIC        c.country, c.city, c.region, c.loyalty_tier,
# MAGIC        CASE WHEN coalesce(s.lifetime_net_sales, 0) >= 2000 OR c.loyalty_tier = 'Platinum' THEN 'VIP'
# MAGIC             WHEN c.signup_date > DATE'2026-09-30' - INTERVAL 180 DAYS OR coalesce(s.order_count, 0) <= 1 THEN 'New'
# MAGIC             ELSE 'Regular' END,
# MAGIC        c.signup_date
# MAGIC FROM silver.customers c LEFT JOIN spend s ON c.customer_id = s.customer_id;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Facts

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE TABLE gold.fact_order_line (
# MAGIC   order_item_id   STRING NOT NULL COMMENT 'Order line key (WEBI-* online, POSI-* store)',
# MAGIC   order_id        STRING COMMENT 'Order key (WEB-* online, POS-* store); one order has 1-3 lines',
# MAGIC   date_key        INT    COMMENT 'Order date key (yyyyMMdd) -> dim_date',
# MAGIC   customer_id     STRING COMMENT 'Buying customer -> dim_customer',
# MAGIC   product_id      STRING COMMENT 'Product sold -> dim_product',
# MAGIC   store_id        STRING COMMENT 'Selling store; ON01 for online orders -> dim_store',
# MAGIC   promotion_id    STRING COMMENT 'Promotion applied; PR00 = none -> dim_promotion',
# MAGIC   quantity        INT    COMMENT 'Units sold on the line',
# MAGIC   gross_sales     DECIMAL(12,2) COMMENT 'quantity x unit_price, EUR, before discount',
# MAGIC   discount_amount DECIMAL(12,2) COMMENT 'Promotion discount on the line, EUR',
# MAGIC   net_sales       DECIMAL(12,2) COMMENT 'gross_sales - discount_amount, EUR. This is what "revenue" and "sales" mean',
# MAGIC   cogs            DECIMAL(12,2) COMMENT 'quantity x product unit_cost, EUR',
# MAGIC   gross_profit    DECIMAL(12,2) COMMENT 'net_sales - cogs, EUR',
# MAGIC   order_status    STRING COMMENT 'Completed or Processing (recent online orders)',
# MAGIC   payment_method  STRING COMMENT 'Card, Cash, Klarna, Swish, Vipps or MobilePay',
# MAGIC   CONSTRAINT pk_fact_order_line PRIMARY KEY (order_item_id),
# MAGIC   CONSTRAINT fk_fol_date      FOREIGN KEY (date_key)     REFERENCES gold.dim_date (date_key),
# MAGIC   CONSTRAINT fk_fol_customer  FOREIGN KEY (customer_id)  REFERENCES gold.dim_customer (customer_id),
# MAGIC   CONSTRAINT fk_fol_product   FOREIGN KEY (product_id)   REFERENCES gold.dim_product (product_id),
# MAGIC   CONSTRAINT fk_fol_store     FOREIGN KEY (store_id)     REFERENCES gold.dim_store (store_id),
# MAGIC   CONSTRAINT fk_fol_promotion FOREIGN KEY (promotion_id) REFERENCES gold.dim_promotion (promotion_id)
# MAGIC ) COMMENT 'Sales at order-line grain for stores and online, 2024-01 to 2026-09. Source of truth for revenue, margin and units.';
# MAGIC
# MAGIC INSERT INTO gold.fact_order_line
# MAGIC SELECT i.order_item_id, i.order_id, CAST(date_format(o.order_ts, 'yyyyMMdd') AS INT), o.customer_id, i.product_id,
# MAGIC        o.store_id, coalesce(o.promotion_id, 'PR00'), i.quantity,
# MAGIC        CAST(i.quantity * i.unit_price AS DECIMAL(12,2)),
# MAGIC        i.discount_amount,
# MAGIC        CAST(i.quantity * i.unit_price - i.discount_amount AS DECIMAL(12,2)),
# MAGIC        CAST(i.quantity * p.unit_cost AS DECIMAL(12,2)),
# MAGIC        CAST(i.quantity * i.unit_price - i.discount_amount - i.quantity * p.unit_cost AS DECIMAL(12,2)),
# MAGIC        o.order_status, o.payment_method
# MAGIC FROM silver.order_items i
# MAGIC JOIN silver.orders o   ON i.order_id = o.order_id
# MAGIC JOIN silver.products p ON i.product_id = p.product_id;

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE TABLE gold.fact_returns (
# MAGIC   return_id     STRING NOT NULL COMMENT 'Return key',
# MAGIC   order_item_id STRING COMMENT 'Returned order line -> fact_order_line',
# MAGIC   date_key      INT    COMMENT 'Return date key (yyyyMMdd) -> dim_date',
# MAGIC   customer_id   STRING COMMENT 'Customer who returned -> dim_customer',
# MAGIC   product_id    STRING COMMENT 'Returned product -> dim_product',
# MAGIC   store_id      STRING COMMENT 'Store of the original sale -> dim_store',
# MAGIC   return_qty    INT    COMMENT 'Units returned',
# MAGIC   refund_amount DECIMAL(12,2) COMMENT 'Amount refunded to the customer, EUR',
# MAGIC   return_reason STRING COMMENT 'Wrong size, Damaged on arrival, Changed mind, Not as described, Defective',
# MAGIC   CONSTRAINT pk_fact_returns PRIMARY KEY (return_id),
# MAGIC   CONSTRAINT fk_fr_line     FOREIGN KEY (order_item_id) REFERENCES gold.fact_order_line (order_item_id),
# MAGIC   CONSTRAINT fk_fr_date     FOREIGN KEY (date_key)      REFERENCES gold.dim_date (date_key),
# MAGIC   CONSTRAINT fk_fr_customer FOREIGN KEY (customer_id)   REFERENCES gold.dim_customer (customer_id),
# MAGIC   CONSTRAINT fk_fr_product  FOREIGN KEY (product_id)    REFERENCES gold.dim_product (product_id),
# MAGIC   CONSTRAINT fk_fr_store    FOREIGN KEY (store_id)      REFERENCES gold.dim_store (store_id)
# MAGIC ) COMMENT 'Product returns at line level, dated by return date. Subtract refund_amount from net_sales for Net Revenue.';
# MAGIC
# MAGIC INSERT INTO gold.fact_returns
# MAGIC SELECT r.return_id, r.order_item_id, CAST(date_format(r.return_date, 'yyyyMMdd') AS INT),
# MAGIC        f.customer_id, f.product_id, f.store_id, r.return_qty, r.refund_amount, r.return_reason
# MAGIC FROM silver.returns r JOIN gold.fact_order_line f ON r.order_item_id = f.order_item_id;
# MAGIC
# MAGIC CREATE TABLE gold.fact_web_session (
# MAGIC   session_id         STRING NOT NULL COMMENT 'Web session key',
# MAGIC   date_key           INT     COMMENT 'Session start date key (yyyyMMdd) -> dim_date',
# MAGIC   customer_id        STRING  COMMENT 'Logged-in customer -> dim_customer; NULL for anonymous visitors',
# MAGIC   device             STRING  COMMENT 'Mobile, Desktop or Tablet',
# MAGIC   traffic_source     STRING  COMMENT 'Organic, Paid Search, Email, Social or Direct',
# MAGIC   pages_viewed       INT     COMMENT 'Pages viewed in the session',
# MAGIC   added_to_cart_flag BOOLEAN COMMENT 'True if anything was added to cart',
# MAGIC   ordered_flag       BOOLEAN COMMENT 'True if the session ended in an online order (conversion)',
# MAGIC   CONSTRAINT pk_fact_web_session PRIMARY KEY (session_id),
# MAGIC   CONSTRAINT fk_fws_date     FOREIGN KEY (date_key)    REFERENCES gold.dim_date (date_key),
# MAGIC   CONSTRAINT fk_fws_customer FOREIGN KEY (customer_id) REFERENCES gold.dim_customer (customer_id)
# MAGIC ) COMMENT 'Web shop sessions (5,000) for funnel and conversion analysis. Online channel only.';
# MAGIC
# MAGIC INSERT INTO gold.fact_web_session
# MAGIC SELECT session_id, CAST(date_format(session_start_ts, 'yyyyMMdd') AS INT), customer_id, device, traffic_source,
# MAGIC        pages_viewed, added_to_cart_flag, ordered_flag
# MAGIC FROM silver.web_sessions;

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE TABLE gold.fact_inventory_daily (
# MAGIC   date_key      INT    NOT NULL COMMENT 'Snapshot date key (yyyyMMdd) -> dim_date',
# MAGIC   product_id    STRING NOT NULL COMMENT 'Product -> dim_product',
# MAGIC   store_id      STRING NOT NULL COMMENT 'Stock location; warehouse WH01 is reported as the online store ON01 -> dim_store',
# MAGIC   on_hand_qty   INT     COMMENT 'Units physically on hand at end of day',
# MAGIC   reserved_qty  INT     COMMENT 'Units reserved for open orders',
# MAGIC   available_qty INT     COMMENT 'on_hand_qty - reserved_qty',
# MAGIC   reorder_point INT     COMMENT 'Stock level that triggers replenishment',
# MAGIC   is_stock_out  BOOLEAN COMMENT 'True when available_qty <= 0',
# MAGIC   CONSTRAINT pk_fact_inventory_daily PRIMARY KEY (date_key, product_id, store_id),
# MAGIC   CONSTRAINT fk_fid_date    FOREIGN KEY (date_key)   REFERENCES gold.dim_date (date_key),
# MAGIC   CONSTRAINT fk_fid_product FOREIGN KEY (product_id) REFERENCES gold.dim_product (product_id),
# MAGIC   CONSTRAINT fk_fid_store   FOREIGN KEY (store_id)   REFERENCES gold.dim_store (store_id)
# MAGIC ) COMMENT 'Daily stock snapshot per product and location for the last 90 days (2026-07-03 to 2026-09-30). Semi-additive: do not sum quantities across dates.';
# MAGIC
# MAGIC INSERT INTO gold.fact_inventory_daily
# MAGIC SELECT CAST(date_format(snapshot_date, 'yyyyMMdd') AS INT), product_id,
# MAGIC        CASE location_id WHEN 'WH01' THEN 'ON01' ELSE location_id END,
# MAGIC        on_hand_qty, reserved_qty, on_hand_qty - reserved_qty, reorder_point, (on_hand_qty - reserved_qty) <= 0
# MAGIC FROM silver.inventory_snapshots;
# MAGIC
# MAGIC CREATE TABLE gold.fact_shipment (
# MAGIC   shipment_id       STRING NOT NULL COMMENT 'Shipment key',
# MAGIC   order_id          STRING  COMMENT 'Online order shipped (matches fact_order_line.order_id)',
# MAGIC   ship_date_key     INT     COMMENT 'Ship date key (yyyyMMdd) -> dim_date',
# MAGIC   delivery_date_key INT     COMMENT 'Delivery date key (yyyyMMdd) -> dim_date; NULL while in transit',
# MAGIC   carrier           STRING  COMMENT 'PostNord, Bring, DHL Express or Budbee',
# MAGIC   shipping_cost     DECIMAL(8,2) COMMENT 'Shipping cost charged, EUR',
# MAGIC   delivery_days     INT     COMMENT 'Days from ship date to delivery date',
# MAGIC   is_on_time        BOOLEAN COMMENT 'True when delivered within the 3-day promise; NULL if not delivered yet',
# MAGIC   CONSTRAINT pk_fact_shipment PRIMARY KEY (shipment_id),
# MAGIC   CONSTRAINT fk_fs_ship_date     FOREIGN KEY (ship_date_key)     REFERENCES gold.dim_date (date_key),
# MAGIC   CONSTRAINT fk_fs_delivery_date FOREIGN KEY (delivery_date_key) REFERENCES gold.dim_date (date_key)
# MAGIC ) COMMENT 'Deliveries of online orders from warehouse WH01. Delivery promise is 3 days.';
# MAGIC
# MAGIC INSERT INTO gold.fact_shipment
# MAGIC SELECT shipment_id, order_id, CAST(date_format(ship_date, 'yyyyMMdd') AS INT), CAST(date_format(delivery_date, 'yyyyMMdd') AS INT),
# MAGIC        carrier, shipping_cost, datediff(delivery_date, ship_date), datediff(delivery_date, ship_date) <= 3
# MAGIC FROM silver.shipments;

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE TABLE gold.fact_finance_monthly (
# MAGIC   month_date_key          INT    NOT NULL COMMENT 'First day of the month as yyyyMMdd, e.g. 20251101 -> dim_date',
# MAGIC   store_id                STRING NOT NULL COMMENT 'Store or online channel -> dim_store',
# MAGIC   revenue                 DECIMAL(14,2) COMMENT 'Booked GL revenue for the whole store, EUR. NOT comparable with or additive to fact_order_line.net_sales',
# MAGIC   cogs                    DECIMAL(14,2) COMMENT 'GL cost of goods sold, EUR',
# MAGIC   operating_expenses      DECIMAL(14,2) COMMENT 'GL staff, rent, marketing and utilities, EUR',
# MAGIC   operating_profit        DECIMAL(14,2) COMMENT 'revenue - cogs - operating_expenses, EUR',
# MAGIC   budget_revenue          DECIMAL(14,2) COMMENT 'Budgeted revenue, EUR',
# MAGIC   budget_operating_profit DECIMAL(14,2) COMMENT 'Budgeted revenue - budgeted COGS - budgeted operating expense, EUR',
# MAGIC   CONSTRAINT pk_fact_finance_monthly PRIMARY KEY (month_date_key, store_id),
# MAGIC   CONSTRAINT fk_ffm_date  FOREIGN KEY (month_date_key) REFERENCES gold.dim_date (date_key),
# MAGIC   CONSTRAINT fk_ffm_store FOREIGN KEY (store_id)       REFERENCES gold.dim_store (store_id)
# MAGIC ) COMMENT 'Monthly P&L actual vs budget per store from the general ledger. Use for profit and budget questions only.';
# MAGIC
# MAGIC INSERT INTO gold.fact_finance_monthly
# MAGIC WITH act AS (
# MAGIC   SELECT trunc(posting_date, 'MM') AS m, store_id,
# MAGIC          SUM(CASE WHEN account_type = 'Revenue' THEN amount END)           AS revenue,
# MAGIC          SUM(CASE WHEN account_type = 'COGS' THEN amount END)              AS cogs,
# MAGIC          SUM(CASE WHEN account_type = 'Operating Expense' THEN amount END) AS opex
# MAGIC   FROM silver.gl_entries GROUP BY 1, 2
# MAGIC ), bud AS (
# MAGIC   SELECT month AS m, store_id,
# MAGIC          SUM(CASE WHEN account_type = 'Revenue' THEN budget_amount END) AS b_rev,
# MAGIC          SUM(CASE WHEN account_type = 'Revenue' THEN budget_amount ELSE -budget_amount END) AS b_op
# MAGIC   FROM silver.budgets GROUP BY 1, 2
# MAGIC )
# MAGIC SELECT CAST(date_format(a.m, 'yyyyMMdd') AS INT), a.store_id, a.revenue, a.cogs, a.opex,
# MAGIC        a.revenue - a.cogs - a.opex, b.b_rev, b.b_op
# MAGIC FROM act a LEFT JOIN bud b ON a.m = b.m AND a.store_id = b.store_id;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Row counts and orphan check

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT 'dim_customer' AS table_name, COUNT(*) AS row_count FROM gold.dim_customer
# MAGIC UNION ALL SELECT 'dim_product', COUNT(*) FROM gold.dim_product
# MAGIC UNION ALL SELECT 'dim_store', COUNT(*) FROM gold.dim_store
# MAGIC UNION ALL SELECT 'dim_date', COUNT(*) FROM gold.dim_date
# MAGIC UNION ALL SELECT 'dim_promotion', COUNT(*) FROM gold.dim_promotion
# MAGIC UNION ALL SELECT 'dim_supplier', COUNT(*) FROM gold.dim_supplier
# MAGIC UNION ALL SELECT 'fact_order_line', COUNT(*) FROM gold.fact_order_line
# MAGIC UNION ALL SELECT 'fact_web_session', COUNT(*) FROM gold.fact_web_session
# MAGIC UNION ALL SELECT 'fact_inventory_daily', COUNT(*) FROM gold.fact_inventory_daily
# MAGIC UNION ALL SELECT 'fact_returns', COUNT(*) FROM gold.fact_returns
# MAGIC UNION ALL SELECT 'fact_shipment', COUNT(*) FROM gold.fact_shipment
# MAGIC UNION ALL SELECT 'fact_finance_monthly', COUNT(*) FROM gold.fact_finance_monthly
# MAGIC UNION ALL SELECT 'ORPHANS fact_order_line -> dim_customer', COUNT(*) FROM gold.fact_order_line f LEFT ANTI JOIN gold.dim_customer c ON f.customer_id = c.customer_id

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Validate the 5 bootcamp metrics
# MAGIC These numbers are recorded in the README. Genie answers should match them.

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TEMP VIEW v_metrics AS
# MAGIC WITH s AS (SELECT SUM(net_sales) AS net_sales, SUM(gross_profit) AS gross_profit, SUM(quantity) AS qty FROM gold.fact_order_line),
# MAGIC      r AS (SELECT SUM(refund_amount) AS refunds, SUM(return_qty) AS return_qty FROM gold.fact_returns),
# MAGIC      w AS (SELECT COUNT_IF(ordered_flag) AS converted, COUNT(*) AS sessions FROM gold.fact_web_session),
# MAGIC      i AS (SELECT COUNT_IF(is_stock_out) AS stock_out_rows, COUNT(*) AS inv_rows FROM gold.fact_inventory_daily)
# MAGIC SELECT 1 AS n, 'Net Revenue (EUR)' AS metric, ROUND(s.net_sales - r.refunds, 2) AS value FROM s, r
# MAGIC UNION ALL SELECT 2, 'Gross Margin %', ROUND(s.gross_profit / s.net_sales * 100, 2) FROM s
# MAGIC UNION ALL SELECT 3, 'Online Conversion Rate %', ROUND(w.converted / w.sessions * 100, 2) FROM w
# MAGIC UNION ALL SELECT 4, 'Return Rate %', ROUND(r.return_qty / s.qty * 100, 2) FROM s, r
# MAGIC UNION ALL SELECT 5, 'Stock-out Rate %', ROUND(i.stock_out_rows / i.inv_rows * 100, 2) FROM i;
# MAGIC
# MAGIC SELECT metric, value FROM v_metrics ORDER BY n

# COMMAND ----------

EXPECTED = {  # values recorded in README.md
    "Net Revenue (EUR)": 604798.15,
    "Gross Margin %": 40.84,
    "Online Conversion Rate %": 8.62,
    "Return Rate %": 7.19,
    "Stock-out Rate %": 2.44,
}
actual = {r.metric: float(r.value) for r in spark.table("v_metrics").collect()}
for k, v in EXPECTED.items():
    status = "OK " if abs(actual[k] - v) < 0.01 else "DIFF"
    print(f"{status}  {k:<26} actual={actual[k]:>14,.2f}   expected={v:>14,.2f}")
