# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 02 · Silver — clean, type and conform (SQL + PySpark)
# MAGIC
# MAGIC | Fix | Where |
# MAGIC |---|---|
# MAGIC | Deduplicate on business keys | every table (`QUALIFY ROW_NUMBER()` / `dropDuplicates`) |
# MAGIC | Trim and standardise casing | names, cities, countries, tiers, statuses, payment methods |
# MAGIC | Parse the non-ISO date `dd.MM.yyyy` | `customers.signup_date` |
# MAGIC | Map native country names (Sverige, Norge, Danmark) | `customers` |
# MAGIC | Derive region from country (`Unassigned` when missing) | `customers`, `stores` |
# MAGIC | Merge online + store orders, add `channel` | `orders`, `order_items` (PySpark) |
# MAGIC | Quarantine invalid order lines with `reject_reason` | `order_items_quarantine` |

# COMMAND ----------

dbutils.widgets.text("catalog", "retail_bootcamp", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
spark.sql(f"USE CATALOG {CATALOG}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Customers (SQL)
# MAGIC Standardise country, derive region, parse both date formats, attach loyalty tier.

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE silver.customers
# MAGIC COMMENT 'Cleaned CRM customers, one row per customer_id' AS
# MAGIC WITH src AS (
# MAGIC   SELECT
# MAGIC     trim(customer_id)                                   AS customer_id,
# MAGIC     initcap(trim(first_name))                           AS first_name,
# MAGIC     initcap(trim(last_name))                            AS last_name,
# MAGIC     lower(trim(email))                                  AS email,
# MAGIC     trim(phone)                                         AS phone,
# MAGIC     CASE WHEN upper(trim(gender)) IN ('F', 'FEMALE') THEN 'Female'
# MAGIC          WHEN upper(trim(gender)) IN ('M', 'MALE')   THEN 'Male'
# MAGIC          ELSE 'Other' END                               AS gender,
# MAGIC     to_date(trim(date_of_birth))                        AS date_of_birth,
# MAGIC     CASE lower(trim(country))
# MAGIC          WHEN 'sverige' THEN 'Sweden'
# MAGIC          WHEN 'norge'   THEN 'Norway'
# MAGIC          WHEN 'danmark' THEN 'Denmark'
# MAGIC          ELSE initcap(trim(country)) END                AS country,
# MAGIC     initcap(trim(city))                                 AS city,
# MAGIC     coalesce(try_to_date(trim(signup_date), 'yyyy-MM-dd'),
# MAGIC              try_to_date(trim(signup_date), 'dd.MM.yyyy')) AS signup_date,
# MAGIC     upper(trim(is_active)) IN ('Y', 'YES', 'TRUE', '1') AS is_active,
# MAGIC     _ingest_ts
# MAGIC   FROM bronze.crm_customers_raw
# MAGIC   QUALIFY ROW_NUMBER() OVER (PARTITION BY trim(customer_id) ORDER BY _ingest_ts DESC) = 1
# MAGIC ),
# MAGIC loyalty AS (
# MAGIC   SELECT trim(customer_id) AS customer_id, initcap(trim(loyalty_tier)) AS loyalty_tier
# MAGIC   FROM bronze.crm_loyalty_members_raw
# MAGIC   QUALIFY ROW_NUMBER() OVER (PARTITION BY trim(customer_id) ORDER BY to_date(enrolled_date) DESC) = 1
# MAGIC )
# MAGIC SELECT s.customer_id, s.first_name, s.last_name, s.email, s.phone, s.gender, s.date_of_birth,
# MAGIC        s.country, s.city,
# MAGIC        coalesce(cr.region, 'Unassigned')  AS region,
# MAGIC        coalesce(l.loyalty_tier, 'None')   AS loyalty_tier,
# MAGIC        s.signup_date, s.is_active
# MAGIC FROM src s
# MAGIC LEFT JOIN bronze.mdm_country_region_raw cr ON s.country = trim(cr.country_name)
# MAGIC LEFT JOIN loyalty l ON s.customer_id = l.customer_id

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Products, suppliers, stores, promotions (SQL)

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE silver.products COMMENT 'ERP products with category hierarchy' AS
# MAGIC SELECT trim(p.product_id) AS product_id, upper(trim(p.sku)) AS sku, trim(p.product_name) AS product_name,
# MAGIC        trim(p.brand) AS brand, trim(c.category_name) AS category, trim(c.sub_category_name) AS sub_category,
# MAGIC        trim(p.supplier_id) AS supplier_id,
# MAGIC        CAST(p.list_price AS DECIMAL(10,2)) AS list_price, CAST(p.unit_cost AS DECIMAL(10,2)) AS unit_cost,
# MAGIC        to_date(p.launch_date) AS launch_date, upper(trim(p.is_active)) IN ('Y','TRUE','1') AS is_active
# MAGIC FROM bronze.erp_products_raw p
# MAGIC LEFT JOIN bronze.erp_product_categories_raw c ON trim(p.category_id) = trim(c.category_id)
# MAGIC QUALIFY ROW_NUMBER() OVER (PARTITION BY trim(p.product_id) ORDER BY p._ingest_ts DESC) = 1;
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.suppliers COMMENT 'ERP suppliers' AS
# MAGIC SELECT trim(supplier_id) AS supplier_id, trim(supplier_name) AS supplier_name, initcap(trim(country)) AS country,
# MAGIC        CAST(lead_time_days AS INT) AS lead_time_days, CAST(payment_terms_days AS INT) AS payment_terms_days
# MAGIC FROM bronze.erp_suppliers_raw
# MAGIC QUALIFY ROW_NUMBER() OVER (PARTITION BY trim(supplier_id) ORDER BY _ingest_ts DESC) = 1;
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.stores COMMENT 'Stores and the online channel with region' AS
# MAGIC SELECT trim(s.store_id) AS store_id, trim(s.store_name) AS store_name, trim(ch.channel_name) AS channel,
# MAGIC        initcap(trim(s.country)) AS country, initcap(trim(s.city)) AS city,
# MAGIC        coalesce(cr.region, 'Unassigned') AS region, to_date(s.opening_date) AS opening_date
# MAGIC FROM bronze.mdm_stores_raw s
# MAGIC LEFT JOIN bronze.mdm_channels_raw ch ON trim(s.channel_id) = trim(ch.channel_id)
# MAGIC LEFT JOIN bronze.mdm_country_region_raw cr ON initcap(trim(s.country)) = trim(cr.country_name)
# MAGIC QUALIFY ROW_NUMBER() OVER (PARTITION BY trim(s.store_id) ORDER BY s._ingest_ts DESC) = 1;
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.promotions COMMENT 'Marketing promotions' AS
# MAGIC SELECT trim(promotion_id) AS promotion_id, trim(promotion_name) AS promotion_name, trim(promotion_type) AS promotion_type,
# MAGIC        CAST(discount_pct AS DECIMAL(5,2)) AS discount_pct, to_date(start_date) AS start_date, to_date(end_date) AS end_date
# MAGIC FROM bronze.mkt_promotions_raw
# MAGIC QUALIFY ROW_NUMBER() OVER (PARTITION BY trim(promotion_id) ORDER BY _ingest_ts DESC) = 1;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Web sessions (PySpark)

# COMMAND ----------

from pyspark.sql import functions as F

web_sessions = (spark.table("bronze.ecom_web_sessions_raw")
    .select(F.trim("session_id").alias("session_id"),
            F.nullif(F.trim("customer_id"), F.lit("")).alias("customer_id"),
            F.to_timestamp("session_start_ts").alias("session_start_ts"),
            F.initcap(F.trim("device")).alias("device"),
            F.trim("traffic_source").alias("traffic_source"),
            F.col("pages_viewed").cast("int").alias("pages_viewed"),
            (F.col("added_to_cart_flag").cast("int") == 1).alias("added_to_cart_flag"),
            (F.col("ordered_flag").cast("int") == 1).alias("ordered_flag"))
    .dropDuplicates(["session_id"]))
web_sessions.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver.web_sessions")
print("silver.web_sessions:", spark.table("silver.web_sessions").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Orders — merge online and store into one model (PySpark)
# MAGIC Online orders get `store_id = 'ON01'` (the Online Store) and `channel = 'Online'`.

# COMMAND ----------

PAYMENT_MAP = {"card": "Card", "cash": "Cash", "klarna": "Klarna", "swish": "Swish", "vipps": "Vipps", "mobilepay": "MobilePay"}
pay_map = F.create_map([F.lit(x) for kv in PAYMENT_MAP.items() for x in kv])

def std_orders(df, channel, store_col):
    return df.select(
        F.trim("order_id").alias("order_id"),
        F.to_timestamp(F.trim("order_ts")).alias("order_ts"),
        F.trim("customer_id").alias("customer_id"),
        store_col.alias("store_id"),
        F.lit(channel).alias("channel"),
        F.nullif(F.trim("promotion_id"), F.lit("")).alias("promotion_id"),
        F.initcap(F.trim("order_status")).alias("order_status"),
        F.coalesce(pay_map[F.lower(F.trim("payment_method"))], F.lit("Other")).alias("payment_method"))

orders_all = (std_orders(spark.table("bronze.ecom_online_orders_raw"), "Online", F.lit("ON01"))
              .unionByName(std_orders(spark.table("bronze.pos_store_orders_raw"), "Store", F.trim("store_id")))
              .dropDuplicates(["order_id"]))

items_all = (spark.table("bronze.ecom_online_order_items_raw")
             .unionByName(spark.table("bronze.pos_store_order_items_raw"))
             .select(F.trim("order_item_id").alias("order_item_id"),
                     F.trim("order_id").alias("order_id"),
                     F.trim("product_id").alias("product_id"),
                     F.col("quantity").cast("int").alias("quantity"),
                     F.col("unit_price").cast("decimal(10,2)").alias("unit_price"),
                     F.col("discount_amount").cast("decimal(10,2)").alias("discount_amount"))
             .dropDuplicates(["order_item_id"]))
print("orders:", orders_all.count(), " order lines:", items_all.count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Validate order lines → valid vs quarantine

# COMMAND ----------

known_customers = spark.table("silver.customers").select("customer_id").withColumn("_cust_ok", F.lit(True))
known_products = spark.table("silver.products").select("product_id").withColumn("_prod_ok", F.lit(True))

checked = (items_all
    .join(orders_all.select("order_id", "customer_id").withColumn("_order_ok", F.lit(True)), "order_id", "left")
    .join(known_customers, "customer_id", "left")
    .join(known_products, "product_id", "left")
    .withColumn("reject_reason",
        F.when(F.col("quantity").isNull() | (F.col("quantity") <= 0), "QUANTITY_NOT_POSITIVE")
         .when(F.col("_order_ok").isNull(), "UNKNOWN_ORDER")
         .when(F.col("_cust_ok").isNull(), "UNKNOWN_CUSTOMER")
         .when(F.col("_prod_ok").isNull(), "UNKNOWN_PRODUCT")))

item_cols = ["order_item_id", "order_id", "product_id", "quantity", "unit_price", "discount_amount"]
valid = checked.filter("reject_reason IS NULL").select(*item_cols)
rejected = (checked.filter("reject_reason IS NOT NULL")
            .select(*item_cols, "customer_id", "reject_reason", F.current_timestamp().alias("_quarantined_ts")))

valid.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver.order_items")
rejected.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver.order_items_quarantine")

# keep only orders that still have at least one valid line
(orders_all.join(spark.table("silver.order_items").select("order_id").distinct(), "order_id", "left_semi")
    .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver.orders"))

display(spark.table("silver.order_items_quarantine").groupBy("reject_reason").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Payments, shipments, returns, inventory, purchasing, finance (SQL)

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE silver.payments COMMENT 'Payment gateway transactions' AS
# MAGIC SELECT trim(payment_id) AS payment_id, trim(order_id) AS order_id, to_timestamp(payment_ts) AS payment_ts,
# MAGIC        CAST(amount AS DECIMAL(12,2)) AS amount,
# MAGIC        CASE lower(trim(payment_method)) WHEN 'card' THEN 'Card' WHEN 'cash' THEN 'Cash' WHEN 'klarna' THEN 'Klarna'
# MAGIC             WHEN 'swish' THEN 'Swish' WHEN 'vipps' THEN 'Vipps' WHEN 'mobilepay' THEN 'MobilePay' ELSE 'Other' END AS payment_method,
# MAGIC        initcap(trim(payment_status)) AS payment_status
# MAGIC FROM bronze.pay_payments_raw
# MAGIC QUALIFY ROW_NUMBER() OVER (PARTITION BY trim(payment_id) ORDER BY _ingest_ts DESC) = 1;
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.shipments COMMENT 'WMS shipments for online orders' AS
# MAGIC SELECT trim(shipment_id) AS shipment_id, trim(order_id) AS order_id, trim(warehouse_id) AS warehouse_id,
# MAGIC        to_date(ship_date) AS ship_date, to_date(delivery_date) AS delivery_date, trim(carrier) AS carrier,
# MAGIC        CAST(shipping_cost AS DECIMAL(8,2)) AS shipping_cost, initcap(trim(delivery_status)) AS delivery_status
# MAGIC FROM bronze.wms_shipments_raw
# MAGIC QUALIFY ROW_NUMBER() OVER (PARTITION BY trim(shipment_id) ORDER BY _ingest_ts DESC) = 1;
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.returns COMMENT 'Returns portal records at order-line level' AS
# MAGIC SELECT trim(return_id) AS return_id, trim(order_item_id) AS order_item_id, to_date(return_date) AS return_date,
# MAGIC        CAST(return_qty AS INT) AS return_qty, CAST(refund_amount AS DECIMAL(10,2)) AS refund_amount,
# MAGIC        trim(return_reason) AS return_reason
# MAGIC FROM bronze.rtn_returns_raw
# MAGIC QUALIFY ROW_NUMBER() OVER (PARTITION BY trim(return_id) ORDER BY _ingest_ts DESC) = 1;
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.inventory_snapshots COMMENT 'Daily WMS stock per product and location' AS
# MAGIC SELECT to_date(snapshot_date) AS snapshot_date, trim(product_id) AS product_id, trim(location_id) AS location_id,
# MAGIC        CAST(on_hand_qty AS INT) AS on_hand_qty, CAST(reserved_qty AS INT) AS reserved_qty,
# MAGIC        CAST(reorder_point AS INT) AS reorder_point
# MAGIC FROM bronze.wms_inventory_snapshots_raw
# MAGIC QUALIFY ROW_NUMBER() OVER (PARTITION BY snapshot_date, trim(product_id), trim(location_id) ORDER BY _ingest_ts DESC) = 1;
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.purchase_orders COMMENT 'ERP purchase orders to suppliers' AS
# MAGIC SELECT trim(po_id) AS po_id, trim(supplier_id) AS supplier_id, trim(product_id) AS product_id,
# MAGIC        to_date(order_date) AS order_date, to_date(expected_date) AS expected_date, to_date(received_date) AS received_date,
# MAGIC        CAST(qty_ordered AS INT) AS qty_ordered, CAST(qty_received AS INT) AS qty_received,
# MAGIC        CAST(unit_cost AS DECIMAL(10,2)) AS unit_cost
# MAGIC FROM bronze.erp_purchase_orders_raw
# MAGIC QUALIFY ROW_NUMBER() OVER (PARTITION BY trim(po_id) ORDER BY _ingest_ts DESC) = 1;
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.gl_entries COMMENT 'Finance general ledger, monthly postings per store' AS
# MAGIC SELECT trim(entry_id) AS entry_id, to_date(posting_date) AS posting_date, trim(account_code) AS account_code,
# MAGIC        trim(account_type) AS account_type, trim(cost_centre) AS cost_centre, trim(store_id) AS store_id,
# MAGIC        CAST(amount AS DECIMAL(14,2)) AS amount
# MAGIC FROM bronze.fin_gl_entries_raw
# MAGIC QUALIFY ROW_NUMBER() OVER (PARTITION BY trim(entry_id) ORDER BY _ingest_ts DESC) = 1;
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.budgets COMMENT 'Monthly budget per store and account type' AS
# MAGIC SELECT to_date(month) AS month, trim(store_id) AS store_id, trim(account_type) AS account_type,
# MAGIC        CAST(budget_amount AS DECIMAL(14,2)) AS budget_amount
# MAGIC FROM bronze.fin_budgets_raw
# MAGIC QUALIFY ROW_NUMBER() OVER (PARTITION BY month, trim(store_id), trim(account_type) ORDER BY _ingest_ts DESC) = 1;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Data-quality summary

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT 'customers'   AS table_name, 'duplicate rows removed' AS dq_check, (SELECT COUNT(*) FROM bronze.crm_customers_raw) - (SELECT COUNT(*) FROM silver.customers) AS value
# MAGIC UNION ALL SELECT 'customers',   'non-ISO signup dates parsed', (SELECT COUNT(*) FROM bronze.crm_customers_raw WHERE signup_date LIKE '%.%.%')
# MAGIC UNION ALL SELECT 'customers',   'signup_date still NULL', (SELECT COUNT(*) FROM silver.customers WHERE signup_date IS NULL)
# MAGIC UNION ALL SELECT 'customers',   'native country names mapped', (SELECT COUNT(*) FROM bronze.crm_customers_raw WHERE lower(trim(country)) IN ('sverige','norge','danmark'))
# MAGIC UNION ALL SELECT 'customers',   'region Unassigned (no country mapping)', (SELECT COUNT(*) FROM silver.customers WHERE region = 'Unassigned')
# MAGIC UNION ALL SELECT 'products',    'duplicate rows removed', (SELECT COUNT(*) FROM bronze.erp_products_raw) - (SELECT COUNT(*) FROM silver.products)
# MAGIC UNION ALL SELECT 'web_sessions','duplicate rows removed', (SELECT COUNT(*) FROM bronze.ecom_web_sessions_raw) - (SELECT COUNT(*) FROM silver.web_sessions)
# MAGIC UNION ALL SELECT 'payments',    'duplicate rows removed', (SELECT COUNT(*) FROM bronze.pay_payments_raw) - (SELECT COUNT(*) FROM silver.payments)
# MAGIC UNION ALL SELECT 'order_items', 'duplicate rows removed', (SELECT COUNT(*) FROM bronze.ecom_online_order_items_raw) + (SELECT COUNT(*) FROM bronze.pos_store_order_items_raw)
# MAGIC                                                            - (SELECT COUNT(*) FROM silver.order_items) - (SELECT COUNT(*) FROM silver.order_items_quarantine)
# MAGIC UNION ALL SELECT 'order_items', 'valid lines', (SELECT COUNT(*) FROM silver.order_items)
# MAGIC UNION ALL SELECT 'order_items', concat('quarantined: ', reject_reason), COUNT(*) FROM silver.order_items_quarantine GROUP BY reject_reason
# MAGIC UNION ALL SELECT 'orders',      'orders kept', (SELECT COUNT(*) FROM silver.orders)