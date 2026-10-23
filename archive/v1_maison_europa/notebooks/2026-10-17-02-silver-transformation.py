# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Silver transformation (SQL + PySpark)
# MAGIC
# MAGIC Cleans, types, de-duplicates and validates the Bronze tables.
# MAGIC
# MAGIC | Entity | Language | Main fixes |
# MAGIC |---|---|---|
# MAGIC | country_region | SQL | trim + initcap |
# MAGIC | products | SQL | trim brand, initcap category, cast decimals, dedupe on `last_updated` |
# MAGIC | stores | SQL | cast types, join region |
# MAGIC | customers | PySpark | trim, lowercase email, gender F/M → Female/Male, parse `dd/MM/yyyy`, keep latest row, region, age_group |
# MAGIC | sales | PySpark | cast, drop exact duplicates, validate → `sales` + `sales_quarantine` |
# MAGIC | returns | SQL | cast, Y/N → boolean, enrich from `silver.sales` |
# MAGIC | production, finance | SQL | `yyyy-MM` → first-of-month date, cast types |
# MAGIC
# MAGIC Note: `silver.customers` keeps PII columns. Notebook 04 masks them. Before re-running this notebook after Notebook 04, run the rollback cell in Notebook 04 (section 8). Then run 02 → 03 → 04 again.

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

CATALOG = "fashion_bootcamp"
BRONZE = f"{CATALOG}.bronze"
SILVER = f"{CATALOG}.silver"

# COMMAND ----------

# MAGIC %md
# MAGIC ## country_region (SQL)

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE fashion_bootcamp.silver.country_region
# MAGIC COMMENT 'Reference: country to European region.'
# MAGIC AS
# MAGIC SELECT DISTINCT
# MAGIC   initcap(trim(country)) AS country,
# MAGIC   initcap(trim(region))  AS region
# MAGIC FROM fashion_bootcamp.bronze.country_region_raw
# MAGIC WHERE country IS NOT NULL;
# MAGIC
# MAGIC SELECT * FROM fashion_bootcamp.silver.country_region ORDER BY region, country;

# COMMAND ----------

# MAGIC %md
# MAGIC ## products (SQL)

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE fashion_bootcamp.silver.products
# MAGIC COMMENT 'Cleaned product master with prices, costs and the discount policy cap.'
# MAGIC AS
# MAGIC SELECT
# MAGIC   trim(product_id)                         AS product_id,
# MAGIC   trim(product_name)                       AS product_name,
# MAGIC   trim(brand)                              AS brand,
# MAGIC   trim(brand_tier)                         AS brand_tier,
# MAGIC   initcap(trim(category))                  AS category,
# MAGIC   trim(collection)                         AS collection,
# MAGIC   trim(material)                           AS material,
# MAGIC   CAST(list_price_eur   AS DECIMAL(12,2))  AS list_price_eur,
# MAGIC   CAST(unit_cost_eur    AS DECIMAL(12,2))  AS unit_cost_eur,
# MAGIC   CAST(max_discount_pct AS DECIMAL(5,2))   AS max_discount_pct,
# MAGIC   to_timestamp(trim(last_updated))         AS last_updated
# MAGIC FROM fashion_bootcamp.bronze.products_raw
# MAGIC QUALIFY row_number() OVER (PARTITION BY trim(product_id)
# MAGIC                            ORDER BY to_timestamp(trim(last_updated)) DESC) = 1;
# MAGIC
# MAGIC SELECT * FROM fashion_bootcamp.silver.products ORDER BY product_id;

# COMMAND ----------

# MAGIC %md
# MAGIC ## stores (SQL)

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE fashion_bootcamp.silver.stores
# MAGIC COMMENT 'Cleaned store master with region from the country reference.'
# MAGIC AS
# MAGIC SELECT
# MAGIC   trim(s.store_id)                     AS store_id,
# MAGIC   trim(s.store_name)                   AS store_name,
# MAGIC   trim(s.channel)                      AS channel,
# MAGIC   initcap(trim(s.country))             AS country,
# MAGIC   initcap(trim(s.city))                AS city,
# MAGIC   cr.region                            AS region,
# MAGIC   CAST(s.store_size_sqm AS INT)        AS store_size_sqm,
# MAGIC   to_date(trim(s.opening_date))        AS opening_date
# MAGIC FROM fashion_bootcamp.bronze.stores_raw s
# MAGIC LEFT JOIN fashion_bootcamp.silver.country_region cr
# MAGIC   ON initcap(trim(s.country)) = cr.country;
# MAGIC
# MAGIC SELECT * FROM fashion_bootcamp.silver.stores ORDER BY store_id;

# COMMAND ----------

# MAGIC %md
# MAGIC ## customers (PySpark)

# COMMAND ----------

raw = spark.table(f"{BRONZE}.customers_raw")
country_region = spark.table(f"{SILVER}.country_region")

gender_raw = F.upper(F.trim("gender"))

customers = raw.select(
    F.trim("customer_id").alias("customer_id"),
    F.initcap(F.trim("first_name")).alias("first_name"),
    F.initcap(F.trim("last_name")).alias("last_name"),
    F.lower(F.trim("email")).alias("email"),
    F.trim("phone").alias("phone"),
    F.when(gender_raw == "F", "Female").when(gender_raw == "M", "Male").otherwise("Unknown").alias("gender"),
    F.to_date(F.trim("date_of_birth"), "yyyy-MM-dd").alias("date_of_birth"),
    F.trim("street_address").alias("street_address"),
    F.initcap(F.trim("city")).alias("city"),
    F.trim("postal_code").alias("postal_code"),
    F.initcap(F.trim("country")).alias("country"),
    F.trim("customer_segment").alias("customer_segment"),
    F.trim("loyalty_tier").alias("loyalty_tier"),
    F.to_date(F.trim("first_purchase_date"), "dd/MM/yyyy").alias("first_purchase_date"),
    F.to_timestamp(F.trim("last_updated")).alias("last_updated"),
)

# Keep only the latest version of each customer
latest = Window.partitionBy("customer_id").orderBy(F.col("last_updated").desc())
customers = customers.withColumn("_rn", F.row_number().over(latest)).filter("_rn = 1").drop("_rn")

# Region from the country reference
customers = customers.join(country_region, "country", "left")

# Age group from date of birth
age = F.floor(F.months_between(F.current_date(), F.col("date_of_birth")) / 12)
customers = customers.withColumn(
    "age_group",
    F.when(age < 18, "Under 18")
     .when(age < 25, "18-24")
     .when(age < 35, "25-34")
     .when(age < 45, "35-44")
     .when(age < 55, "45-54")
     .otherwise("55+"),
)

customers = customers.select(
    "customer_id", "first_name", "last_name", "email", "phone", "gender", "date_of_birth",
    "age_group", "street_address", "city", "postal_code", "country", "region",
    "customer_segment", "loyalty_tier", "first_purchase_date", "last_updated",
)

(customers.write.mode("overwrite").option("overwriteSchema", "true")
    .saveAsTable(f"{SILVER}.customers"))
spark.sql(f"COMMENT ON TABLE {SILVER}.customers IS 'Cleaned customers, latest row per customer_id. Contains PII (masked by governance policies).'")
display(spark.table(f"{SILVER}.customers").orderBy("customer_id"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## sales (PySpark): cast, de-duplicate, validate, quarantine

# COMMAND ----------

sales_raw = spark.table(f"{BRONZE}.sales_raw").drop("_source_file", "_ingest_ts")

sales = (
    sales_raw.dropDuplicates()  # removes the exact duplicate SL003
    .select(
        F.trim("sales_line_id").alias("sales_line_id"),
        F.trim("order_id").alias("order_id"),
        F.to_date(F.trim("order_date"), "yyyy-MM-dd").alias("order_date"),
        F.trim("customer_id").alias("customer_id"),
        F.trim("product_id").alias("product_id"),
        F.trim("store_id").alias("store_id"),
        F.col("quantity").cast("int").alias("quantity"),
        F.col("unit_list_price_eur").cast("decimal(12,2)").alias("unit_list_price_eur"),
        F.col("discount_pct").cast("decimal(5,2)").alias("discount_pct"),
        F.trim("promotion_type").alias("promotion_type"),
        F.trim("payment_method").alias("payment_method"),
        F.trim("order_status").alias("order_status"),
    )
)

known_customers = spark.table(f"{SILVER}.customers").select(F.col("customer_id").alias("_known_customer"))
known_products = spark.table(f"{SILVER}.products").select(F.col("product_id").alias("_known_product"))
known_stores = spark.table(f"{SILVER}.stores").select(F.col("store_id").alias("_known_store"))

checked = (
    sales
    .join(known_customers, sales.customer_id == known_customers._known_customer, "left")
    .join(known_products, sales.product_id == known_products._known_product, "left")
    .join(known_stores, sales.store_id == known_stores._known_store, "left")
    .withColumn(
        "reject_reason",
        F.concat_ws(
            "; ",
            F.when(F.col("quantity").isNull() | (F.col("quantity") <= 0), F.lit("quantity must be > 0")),
            F.when(F.col("_known_customer").isNull(), F.lit("unknown customer_id")),
            F.when(F.col("_known_product").isNull(), F.lit("unknown product_id")),
            F.when(F.col("_known_store").isNull(), F.lit("unknown store_id")),
            F.when(F.col("order_date").isNull(), F.lit("invalid order_date")),
            F.when(F.col("discount_pct").isNull() | ~F.col("discount_pct").between(0, 100),
                   F.lit("discount_pct outside 0-100")),
        ),
    )
    .drop("_known_customer", "_known_product", "_known_store")
)

valid = checked.filter(F.col("reject_reason") == "").drop("reject_reason")
quarantine = checked.filter(F.col("reject_reason") != "").withColumn("_quarantined_ts", F.current_timestamp())

valid.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{SILVER}.sales")
quarantine.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{SILVER}.sales_quarantine")
spark.sql(f"COMMENT ON TABLE {SILVER}.sales IS 'Valid, de-duplicated sales lines (order-line grain).'")
spark.sql(f"COMMENT ON TABLE {SILVER}.sales_quarantine IS 'Sales lines that failed validation, with reject_reason.'")

print(f"valid: {spark.table(f'{SILVER}.sales').count()}  quarantined: {spark.table(f'{SILVER}.sales_quarantine').count()}")
display(spark.table(f"{SILVER}.sales_quarantine"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## returns (SQL)

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE fashion_bootcamp.silver.returns
# MAGIC COMMENT 'Cleaned returns enriched with order, customer, product and store from silver.sales.'
# MAGIC AS
# MAGIC SELECT
# MAGIC   trim(r.return_id)                                 AS return_id,
# MAGIC   trim(r.sales_line_id)                             AS sales_line_id,
# MAGIC   s.order_id,
# MAGIC   to_date(trim(r.return_date))                      AS return_date,
# MAGIC   s.customer_id,
# MAGIC   s.product_id,
# MAGIC   s.store_id,
# MAGIC   CAST(r.return_qty AS INT)                         AS return_qty,
# MAGIC   CAST(r.refund_amount_eur AS DECIMAL(12,2))        AS refund_amount_eur,
# MAGIC   trim(r.return_reason)                             AS return_reason,
# MAGIC   trim(r.return_channel)                            AS return_channel,
# MAGIC   CASE upper(trim(r.is_restockable)) WHEN 'Y' THEN true WHEN 'N' THEN false END AS is_restockable,
# MAGIC   CAST(r.return_handling_cost_eur AS DECIMAL(12,2)) AS return_handling_cost_eur
# MAGIC FROM fashion_bootcamp.bronze.returns_raw r
# MAGIC LEFT JOIN fashion_bootcamp.silver.sales s
# MAGIC   ON trim(r.sales_line_id) = s.sales_line_id;
# MAGIC
# MAGIC SELECT * FROM fashion_bootcamp.silver.returns ORDER BY return_id;

# COMMAND ----------

# MAGIC %md
# MAGIC ## production and finance (SQL)

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE fashion_bootcamp.silver.production
# MAGIC COMMENT 'Production batches by product and month.'
# MAGIC AS
# MAGIC SELECT
# MAGIC   trim(production_batch_id)                         AS production_batch_id,
# MAGIC   trim(product_id)                                  AS product_id,
# MAGIC   to_date(trim(production_month), 'yyyy-MM')        AS production_month,
# MAGIC   initcap(trim(factory_country))                    AS factory_country,
# MAGIC   trim(factory_city)                                AS factory_city,
# MAGIC   CAST(units_planned   AS INT)                      AS units_planned,
# MAGIC   CAST(units_produced  AS INT)                      AS units_produced,
# MAGIC   CAST(units_defective AS INT)                      AS units_defective,
# MAGIC   CAST(unit_production_cost_eur AS DECIMAL(12,2))   AS unit_production_cost_eur,
# MAGIC   CAST(lead_time_days AS INT)                       AS lead_time_days,
# MAGIC   CASE upper(trim(on_time_flag)) WHEN 'Y' THEN true WHEN 'N' THEN false END AS is_on_time
# MAGIC FROM fashion_bootcamp.bronze.production_raw;
# MAGIC
# MAGIC CREATE OR REPLACE TABLE fashion_bootcamp.silver.finance
# MAGIC COMMENT 'Monthly store P&L with budget.'
# MAGIC AS
# MAGIC SELECT
# MAGIC   trim(finance_id)                                  AS finance_id,
# MAGIC   to_date(trim(month), 'yyyy-MM')                   AS month_date,
# MAGIC   trim(store_id)                                    AS store_id,
# MAGIC   CAST(revenue_eur        AS DECIMAL(14,2))         AS revenue_eur,
# MAGIC   CAST(cogs_eur           AS DECIMAL(14,2))         AS cogs_eur,
# MAGIC   CAST(marketing_cost_eur AS DECIMAL(14,2))         AS marketing_cost_eur,
# MAGIC   CAST(staff_cost_eur     AS DECIMAL(14,2))         AS staff_cost_eur,
# MAGIC   CAST(rent_cost_eur      AS DECIMAL(14,2))         AS rent_cost_eur,
# MAGIC   CAST(logistics_cost_eur AS DECIMAL(14,2))         AS logistics_cost_eur,
# MAGIC   CAST(budget_revenue_eur AS DECIMAL(14,2))         AS budget_revenue_eur,
# MAGIC   CAST(budget_operating_profit_eur AS DECIMAL(14,2)) AS budget_operating_profit_eur
# MAGIC FROM fashion_bootcamp.bronze.finance_raw;
# MAGIC
# MAGIC SELECT * FROM fashion_bootcamp.silver.finance ORDER BY store_id;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Data-quality summary
# MAGIC Expected: customers 11 → 10, sales 12 → 10 with 1 quarantined (SL011), 0 stores without a region.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT 'customers' AS entity,
# MAGIC        (SELECT count(*) FROM fashion_bootcamp.bronze.customers_raw) AS bronze_rows,
# MAGIC        (SELECT count(*) FROM fashion_bootcamp.silver.customers)     AS silver_rows,
# MAGIC        NULL AS quarantined, '11 -> 10 (C005 deduped)' AS expected
# MAGIC UNION ALL
# MAGIC SELECT 'sales',
# MAGIC        (SELECT count(*) FROM fashion_bootcamp.bronze.sales_raw),
# MAGIC        (SELECT count(*) FROM fashion_bootcamp.silver.sales),
# MAGIC        (SELECT count(*) FROM fashion_bootcamp.silver.sales_quarantine),
# MAGIC        '12 -> 10, 1 quarantined (SL011)'
# MAGIC UNION ALL
# MAGIC SELECT 'products',
# MAGIC        (SELECT count(*) FROM fashion_bootcamp.bronze.products_raw),
# MAGIC        (SELECT count(*) FROM fashion_bootcamp.silver.products), NULL, '10 -> 10'
# MAGIC UNION ALL
# MAGIC SELECT 'stores without region',
# MAGIC        NULL,
# MAGIC        (SELECT count(*) FROM fashion_bootcamp.silver.stores WHERE region IS NULL), NULL, '0'
# MAGIC UNION ALL
# MAGIC SELECT 'customers without region',
# MAGIC        NULL,
# MAGIC        (SELECT count(*) FROM fashion_bootcamp.silver.customers WHERE region IS NULL), NULL, '0'
# MAGIC UNION ALL
# MAGIC SELECT 'returns not matched to a sale',
# MAGIC        NULL,
# MAGIC        (SELECT count(*) FROM fashion_bootcamp.silver.returns WHERE order_id IS NULL), NULL, '0';
