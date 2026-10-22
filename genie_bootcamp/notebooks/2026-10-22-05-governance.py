# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 05 · Governance — region + category access for Genie (SQL + Python)
# MAGIC
# MAGIC Unity Catalog **row filters** and **column masks** on the gold tables. Genie runs every question as the
# MAGIC signed-in user, so each user's answers only cover the data they are entitled to.
# MAGIC
# MAGIC | User | Regions | Product categories | Customer PII | Finance, web sessions, shipments |
# MAGIC |---|---|---|---|---|
# MAGIC | 👑 **Admin** | all | all | visible | visible |
# MAGIC | 👤 **User** | only the regions granted | only the categories granted **+ 🎁 Services & Gifts** | `***` | hidden |
# MAGIC | 🚫 **Not listed** | none | none | `***` | hidden |
# MAGIC
# MAGIC * Rows a user is not entitled to are **removed**, not masked.
# MAGIC * 🎁 **Services & Gifts** is the common category: Nordhem's house brand, 2 products sold with every brand in
# MAGIC   every region. Everyone sees it in their own regions. It is created **only by this notebook**.
# MAGIC * Entitlements live in `governance.user_entitlements` and are granted **only through this notebook** (widgets below).
# MAGIC
# MAGIC > ⚠️ Run **after `03-gold`**. Re-running `03-gold` drops the gold tables, which removes the filters, masks and
# MAGIC > common category. Run this notebook again afterwards.
# MAGIC >
# MAGIC > ⚠️ Row filters need a SQL warehouse, serverless compute or DBR 15.4+ to read the tables.

# COMMAND ----------

dbutils.widgets.text("catalog", "retail_bootcamp", "Catalog")
dbutils.widgets.dropdown("action", "apply", ["apply", "remove"], "Action")
dbutils.widgets.text("grant_user", "", "Grant: user email (blank = skip)")
dbutils.widgets.multiselect("grant_regions", "ALL", ["ALL", "Scandinavia East", "Scandinavia West", "Scandinavia South"], "Grant: regions")
dbutils.widgets.multiselect("grant_categories", "ALL", ["ALL", "Home Appliances", "Toys", "Outdoor Apparel"], "Grant: categories")
dbutils.widgets.dropdown("grant_admin", "false", ["false", "true"], "Grant: admin")

CATALOG = dbutils.widgets.get("catalog")
ACTION = dbutils.widgets.get("action")
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql("CREATE SCHEMA IF NOT EXISTS governance COMMENT 'Access control for the gold layer: entitlements, lookups, filter and mask functions. Not for Genie.'")

COMMON_CATEGORY = "Services & Gifts"
G = f"{CATALOG}.governance"

# table -> (row filter function, columns it is applied on)
ROW_FILTERS = {
    "gold.fact_order_line":      ("rf_store_product", "store_id, product_id"),
    "gold.fact_returns":         ("rf_store_product", "store_id, product_id"),
    "gold.fact_inventory_daily": ("rf_store_product", "store_id, product_id"),
    "gold.dim_store":            ("rf_store", "store_id"),
    "gold.dim_product":          ("rf_product", "product_id"),
    "gold.fact_finance_monthly": ("rf_admin_only", "store_id"),
    "gold.fact_web_session":     ("rf_admin_only", "session_id"),
    "gold.fact_shipment":        ("rf_admin_only", "shipment_id"),
}
PII_MASKS = {"gold.dim_customer": ["customer_name", "email", "phone"]}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Drop existing filters and masks
# MAGIC Done first on every run, so the data changes below see the full tables and the notebook can be re-run.

# COMMAND ----------

def try_sql(stmt):
    try:
        spark.sql(stmt)
    except Exception as e:  # nothing to drop yet
        print(f"skip: {stmt.split(' DROP')[0]} ({type(e).__name__})")

for table in ROW_FILTERS:
    try_sql(f"ALTER TABLE {table} DROP ROW FILTER")
for table, cols in PII_MASKS.items():
    for c in cols:
        try_sql(f"ALTER TABLE {table} ALTER COLUMN {c} DROP MASK")

if ACTION == "remove":
    spark.sql("DELETE FROM gold.fact_order_line WHERE product_id IN ('P016', 'P017')")
    spark.sql("DELETE FROM gold.dim_product WHERE product_id IN ('P016', 'P017')")
    print("Governance removed: no filters, no masks, common category deleted. Entitlements are kept.")
    dbutils.notebook.exit("removed")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · 🎁 Common category — Services & Gifts
# MAGIC
# MAGIC | Product | Name | List price | Unit cost |
# MAGIC |---|---|---|---|
# MAGIC | P016 | Nordhem Gift Card | 50.00 EUR | 45.00 EUR |
# MAGIC | P017 | Nordhem Care & Protection Plan | 39.00 EUR | 12.00 EUR |
# MAGIC
# MAGIC One unit is added as an extra line to existing orders: the gift card to every order whose number ends in
# MAGIC `% 8 = 0`, the protection plan to `% 8 = 4`. That spreads them over every store, region, brand and promotion.
# MAGIC The line takes the order's promotion, like every other line (promotions apply to the whole order).
# MAGIC
# MAGIC > ℹ️ This adds sales, so the full-data KPIs move away from the README values. `dim_customer.customer_segment`
# MAGIC > is not recalculated.

# COMMAND ----------

# MAGIC %sql
# MAGIC MERGE INTO gold.dim_product t
# MAGIC USING (
# MAGIC   SELECT * FROM VALUES
# MAGIC     ('P016', 'NRD-GC50', 'Nordhem Gift Card',              'Nordhem', 'Services & Gifts', 'Gift Cards',       'Nordhem Retail Group', 50.00, 45.00),
# MAGIC     ('P017', 'NRD-CPP',  'Nordhem Care & Protection Plan', 'Nordhem', 'Services & Gifts', 'Protection Plans', 'Nordhem Retail Group', 39.00, 12.00)
# MAGIC   AS s(product_id, sku, product_name, brand, category, sub_category, supplier_name, list_price, unit_cost)
# MAGIC ) s ON t.product_id = s.product_id
# MAGIC WHEN MATCHED THEN UPDATE SET *
# MAGIC WHEN NOT MATCHED THEN INSERT *;
# MAGIC
# MAGIC DELETE FROM gold.fact_order_line WHERE product_id IN ('P016', 'P017');
# MAGIC
# MAGIC INSERT INTO gold.fact_order_line
# MAGIC WITH orders AS (
# MAGIC   SELECT DISTINCT order_id, date_key, customer_id, store_id, promotion_id, order_status, payment_method,
# MAGIC          CAST(substring_index(order_id, '-', -1) AS INT) % 8 AS bucket
# MAGIC   FROM gold.fact_order_line
# MAGIC ),
# MAGIC lines AS (
# MAGIC   SELECT o.*, CASE o.bucket WHEN 0 THEN 'P016' ELSE 'P017' END AS product_id
# MAGIC   FROM orders o WHERE o.bucket IN (0, 4)
# MAGIC )
# MAGIC SELECT concat('NRDI-', l.order_id), l.order_id, l.date_key, l.customer_id, l.product_id, l.store_id, l.promotion_id, 1,
# MAGIC        p.list_price,
# MAGIC        CAST(p.list_price * pr.discount_pct / 100 AS DECIMAL(12,2)),
# MAGIC        CAST(p.list_price - p.list_price * pr.discount_pct / 100 AS DECIMAL(12,2)),
# MAGIC        p.unit_cost,
# MAGIC        CAST(p.list_price - p.list_price * pr.discount_pct / 100 - p.unit_cost AS DECIMAL(12,2)),
# MAGIC        l.order_status, l.payment_method
# MAGIC FROM lines l
# MAGIC JOIN gold.dim_product p    ON l.product_id = p.product_id
# MAGIC JOIN gold.dim_promotion pr ON l.promotion_id = pr.promotion_id;
# MAGIC
# MAGIC -- the common category reaches every region and is sold alongside every brand
# MAGIC SELECT s.region, p.product_name, COUNT(*) AS lines, ROUND(SUM(f.net_sales), 2) AS net_sales_eur
# MAGIC FROM gold.fact_order_line f
# MAGIC JOIN gold.dim_store s   USING (store_id)
# MAGIC JOIN gold.dim_product p USING (product_id)
# MAGIC WHERE p.category = 'Services & Gifts'
# MAGIC GROUP BY ALL ORDER BY ALL

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Lookup tables and entitlements
# MAGIC
# MAGIC The filter functions read small lookup copies in `governance`, not the gold dimensions. The gold dimensions
# MAGIC have their own row filters, and a filter must not read a filtered table.
# MAGIC
# MAGIC `user_entitlements` has **one row per user × region × category**. `ALL` is a wildcard.
# MAGIC The person running this notebook is always made admin, so they keep full access.

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE governance.store_region COMMENT 'Lookup store_id -> region for the row filters' AS
# MAGIC SELECT store_id, region FROM gold.dim_store;
# MAGIC
# MAGIC CREATE OR REPLACE TABLE governance.product_category COMMENT 'Lookup product_id -> category for the row filters' AS
# MAGIC SELECT product_id, category FROM gold.dim_product;
# MAGIC
# MAGIC CREATE TABLE IF NOT EXISTS governance.user_entitlements (
# MAGIC   user_email STRING  NOT NULL COMMENT 'Databricks user name (email), compared case-insensitively with current_user()',
# MAGIC   region     STRING  NOT NULL COMMENT 'Scandinavia East / West / South, or ALL',
# MAGIC   category   STRING  NOT NULL COMMENT 'Home Appliances / Toys / Outdoor Apparel, or ALL. Services & Gifts is always visible',
# MAGIC   is_admin   BOOLEAN NOT NULL COMMENT 'True = no filters and no masks',
# MAGIC   granted_by STRING  COMMENT 'Who ran the grant',
# MAGIC   granted_ts TIMESTAMP COMMENT 'When the grant was made'
# MAGIC ) COMMENT 'Who may see which region and product category. Edit only through notebook 05.';

# COMMAND ----------

def grant(user, regions, categories, is_admin):
    """Replace all entitlement rows of one user with regions x categories."""
    user = user.strip().lower()
    spark.sql("DELETE FROM governance.user_entitlements WHERE lower(user_email) = :u", args={"u": user})
    rows = [(user, r, c, is_admin) for r in regions for c in categories]
    (spark.createDataFrame(rows, "user_email STRING, region STRING, category STRING, is_admin BOOLEAN")
        .selectExpr("*", "current_user() AS granted_by", "current_timestamp() AS granted_ts")
        .write.mode("append").saveAsTable("governance.user_entitlements"))
    print(f"granted  {user:<28} admin={is_admin!s:<5} regions={regions} categories={categories}")

me = spark.sql("SELECT current_user()").first()[0]
grant(me, ["ALL"], ["ALL"], True)

# demo users for the simulation in step 5 (fake addresses, they cannot sign in)
grant("anna.west@example.com", ["Scandinavia West"], ["Toys"], False)
grant("erik.east@example.com", ["Scandinavia East"], ["Home Appliances", "Outdoor Apparel"], False)

# the user picked in the widgets
if dbutils.widgets.get("grant_user").strip():
    grant(dbutils.widgets.get("grant_user"),
          dbutils.widgets.get("grant_regions").split(","),
          dbutils.widgets.get("grant_categories").split(","),
          dbutils.widgets.get("grant_admin") == "true")

display(spark.table("governance.user_entitlements").orderBy("user_email", "region", "category"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Filter and mask functions
# MAGIC
# MAGIC | Function | Logic | Used on |
# MAGIC |---|---|---|
# MAGIC | `user_sees_row(u, store, product)` | admin, or an entitlement row matching the store's region **and** the product's category (or Services & Gifts) | simulation + `rf_store_product` |
# MAGIC | `rf_store_product(store_id, product_id)` | `user_sees_row(current_user(), …)` | fact_order_line, fact_returns, fact_inventory_daily |
# MAGIC | `rf_store(store_id)` | admin, or a region match | dim_store |
# MAGIC | `rf_product(product_id)` | admin, Services & Gifts, or a category match | dim_product |
# MAGIC | `rf_admin_only(any)` | admin only | fact_finance_monthly, fact_web_session, fact_shipment |
# MAGIC | `mask_pii(value)` | value for admins, `***` for everyone else | dim_customer name, email, phone |
# MAGIC
# MAGIC Region and category are matched **on the same entitlement row**, so a user with *West × Toys* and
# MAGIC *East × Home Appliances* never sees *West × Home Appliances*.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE FUNCTION {G}.user_is_admin(u STRING)
RETURNS BOOLEAN
COMMENT 'True when the user has an admin entitlement'
RETURN EXISTS (SELECT 1 FROM {G}.user_entitlements e WHERE lower(e.user_email) = lower(u) AND e.is_admin)
""")

spark.sql(f"""
CREATE OR REPLACE FUNCTION {G}.user_sees_row(u STRING, p_store_id STRING, p_product_id STRING)
RETURNS BOOLEAN
COMMENT 'True when the user may see a row for this store and product'
RETURN {G}.user_is_admin(u) OR EXISTS (
  SELECT 1
  FROM {G}.user_entitlements e, {G}.store_region s, {G}.product_category pc
  WHERE lower(e.user_email) = lower(u)
    AND s.store_id = p_store_id
    AND pc.product_id = p_product_id
    AND (e.region = 'ALL' OR e.region = s.region)
    AND (e.category = 'ALL' OR e.category = pc.category OR pc.category = '{COMMON_CATEGORY}')
)
""")

spark.sql(f"""
CREATE OR REPLACE FUNCTION {G}.rf_store_product(p_store_id STRING, p_product_id STRING)
RETURNS BOOLEAN
COMMENT 'Row filter: region and category of the signed-in user'
RETURN {G}.user_sees_row(current_user(), p_store_id, p_product_id)
""")

spark.sql(f"""
CREATE OR REPLACE FUNCTION {G}.rf_store(p_store_id STRING)
RETURNS BOOLEAN
COMMENT 'Row filter: stores in the regions of the signed-in user'
RETURN {G}.user_is_admin(current_user()) OR EXISTS (
  SELECT 1 FROM {G}.user_entitlements e, {G}.store_region s
  WHERE lower(e.user_email) = lower(current_user())
    AND s.store_id = p_store_id
    AND (e.region = 'ALL' OR e.region = s.region)
)
""")

spark.sql(f"""
CREATE OR REPLACE FUNCTION {G}.rf_product(p_product_id STRING)
RETURNS BOOLEAN
COMMENT 'Row filter: products in the categories of the signed-in user, plus Services & Gifts'
RETURN {G}.user_is_admin(current_user()) OR EXISTS (
  SELECT 1 FROM {G}.user_entitlements e, {G}.product_category pc
  WHERE lower(e.user_email) = lower(current_user())
    AND pc.product_id = p_product_id
    AND (e.category = 'ALL' OR e.category = pc.category OR pc.category = '{COMMON_CATEGORY}')
)
""")

spark.sql(f"""
CREATE OR REPLACE FUNCTION {G}.rf_admin_only(p_any STRING)
RETURNS BOOLEAN
COMMENT 'Row filter: admins only (tables without a product column)'
RETURN {G}.user_is_admin(current_user())
""")

spark.sql(f"""
CREATE OR REPLACE FUNCTION {G}.mask_pii(p_value STRING)
RETURNS STRING
COMMENT 'Column mask: personal data visible to admins only'
RETURN CASE WHEN {G}.user_is_admin(current_user()) THEN p_value ELSE '***' END
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Simulate what each user sees
# MAGIC You are admin, so the filters let you see everything. `user_sees_row` is called with each user's email to
# MAGIC show what Genie will return to them.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT e.user_email,
# MAGIC        s.region,
# MAGIC        p.category,
# MAGIC        COUNT(*)                     AS order_lines,
# MAGIC        ROUND(SUM(f.net_sales), 2)   AS net_sales_eur
# MAGIC FROM (SELECT DISTINCT user_email FROM governance.user_entitlements WHERE NOT is_admin) e
# MAGIC CROSS JOIN gold.fact_order_line f
# MAGIC JOIN gold.dim_store s   ON f.store_id = s.store_id
# MAGIC JOIN gold.dim_product p ON f.product_id = p.product_id
# MAGIC WHERE governance.user_sees_row(e.user_email, f.store_id, f.product_id)
# MAGIC GROUP BY ALL
# MAGIC ORDER BY ALL

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Attach the filters and masks

# COMMAND ----------

for table, (fn, cols) in ROW_FILTERS.items():
    spark.sql(f"ALTER TABLE {table} SET ROW FILTER {G}.{fn} ON ({cols})")
    print(f"row filter  {table:<26} {fn}({cols})")
for table, cols in PII_MASKS.items():
    for c in cols:
        spark.sql(f"ALTER TABLE {table} ALTER COLUMN {c} SET MASK {G}.mask_pii")
        print(f"mask        {table}.{c}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Admin check — full data, including Services & Gifts
# MAGIC You are admin, so this is the whole company. Compare with the README values (base data, without Services & Gifts).

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT CASE WHEN p.category = 'Services & Gifts' THEN 'Services & Gifts (added by 05)' ELSE 'Base data (README values)' END AS scope,
# MAGIC        COUNT(*)                                             AS order_lines,
# MAGIC        ROUND(SUM(f.net_sales), 2)                           AS net_sales_eur,
# MAGIC        ROUND(SUM(f.gross_profit) / SUM(f.net_sales) * 100, 2) AS gross_margin_pct
# MAGIC FROM gold.fact_order_line f
# MAGIC JOIN gold.dim_product p USING (product_id)
# MAGIC GROUP BY ALL
# MAGIC ORDER BY scope
