# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 01 · Bronze — raw ingestion (PySpark)
# MAGIC
# MAGIC One table per source extract: `bronze.<system>_<entity>_raw`
# MAGIC * every column kept as **STRING**, no cleaning
# MAGIC * lineage columns: `_source_system`, `_source_file` (from `_metadata.file_path`), `_ingest_ts`

# COMMAND ----------

dbutils.widgets.text("catalog", "retail_bootcamp", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
VOLUME_PATH = f"/Volumes/{CATALOG}/landing/raw_files"
spark.sql(f"USE CATALOG {CATALOG}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Source system → extract mapping

# COMMAND ----------

SOURCES = {
    ("crm",  "CRM"):              ["customers", "customer_addresses", "loyalty_members"],
    ("ecom", "E-commerce"):       ["web_sessions", "cart_events", "online_orders", "online_order_items"],
    ("pos",  "POS"):              ["store_orders", "store_order_items"],
    ("erp",  "ERP"):              ["products", "product_categories", "suppliers", "purchase_orders"],
    ("wms",  "WMS"):              ["inventory_snapshots", "inventory_movements", "shipments"],
    ("pay",  "Payment gateway"):  ["payments", "refunds"],
    ("rtn",  "Returns portal"):   ["returns"],
    ("mkt",  "Marketing"):        ["promotions", "campaigns"],
    ("fin",  "Finance GL"):       ["gl_entries", "budgets", "cost_centres"],
    ("mdm",  "Master data"):      ["stores", "channels", "country_region"],
}
print(sum(len(v) for v in SOURCES.values()), "extracts")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Ingest every extract
# MAGIC `inferSchema=false` keeps every column as STRING; Silver does the typing.

# COMMAND ----------

from pyspark.sql import functions as F

results = []
for (code, system), entities in SOURCES.items():
    for entity in entities:
        table = f"{CATALOG}.bronze.{code}_{entity}_raw"
        df = (spark.read.format("csv")
              .option("header", "true")
              .option("inferSchema", "false")
              .load(f"{VOLUME_PATH}/{entity}/")
              .select("*",
                      F.lit(system).alias("_source_system"),
                      F.col("_metadata.file_path").alias("_source_file"),
                      F.current_timestamp().alias("_ingest_ts")))
        (df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table))
        spark.sql(f"COMMENT ON TABLE {table} IS 'Raw {system} extract: {entity}. All columns STRING, uncleaned.'")
        results.append((table, system, spark.table(table).count()))

display(spark.createDataFrame(results, "table STRING, source_system STRING, row_count LONG"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Look at the raw data — spot the quality issues
# MAGIC Notice the spaces, casing, native country names (Sverige/Norge/Danmark) and the `dd.MM.yyyy` dates.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT customer_id, first_name, last_name, country, city, gender, signup_date, is_active, _source_file
# MAGIC FROM bronze.crm_customers_raw
# MAGIC WHERE country RLIKE '^ |[A-Z]{3}| $' OR signup_date LIKE '%.%' OR lower(trim(country)) IN ('sverige','norge','danmark','faroe islands')
# MAGIC LIMIT 20

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Duplicate rows per extract (exact duplicates on business key)
# MAGIC SELECT 'customers' AS extract, COUNT(*) - COUNT(DISTINCT customer_id) AS duplicate_rows FROM bronze.crm_customers_raw
# MAGIC UNION ALL SELECT 'products', COUNT(*) - COUNT(DISTINCT product_id) FROM bronze.erp_products_raw
# MAGIC UNION ALL SELECT 'store_order_items', COUNT(*) - COUNT(DISTINCT order_item_id) FROM bronze.pos_store_order_items_raw
# MAGIC UNION ALL SELECT 'payments', COUNT(*) - COUNT(DISTINCT payment_id) FROM bronze.pay_payments_raw
# MAGIC UNION ALL SELECT 'web_sessions', COUNT(*) - COUNT(DISTINCT session_id) FROM bronze.ecom_web_sessions_raw