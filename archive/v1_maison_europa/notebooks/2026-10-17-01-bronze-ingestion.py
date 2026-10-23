# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Bronze ingestion (PySpark)
# MAGIC
# MAGIC Loads every CSV folder in the volume into `fashion_bootcamp.bronze.<entity>_raw`.
# MAGIC
# MAGIC - `header = true`, `inferSchema = false` → **every column is a string**. Bronze keeps the data exactly as received, including the data-quality issues.
# MAGIC - Adds `_source_file` (from `_metadata.file_path`) and `_ingest_ts` for lineage.
# MAGIC - Full overwrite on each run, so the notebook is safe to re-run.

# COMMAND ----------

from pyspark.sql import functions as F

CATALOG = "fashion_bootcamp"
VOLUME_PATH = f"/Volumes/{CATALOG}/landing/raw_files"
ENTITIES = ["country_region", "products", "customers", "stores",
            "sales", "returns", "production", "finance"]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Preview a raw file with `read_files()` (SQL)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT *, _metadata.file_path AS source_file
# MAGIC FROM read_files('/Volumes/fashion_bootcamp/landing/raw_files/customers/',
# MAGIC                 format => 'csv', header => true, inferSchema => false);

# COMMAND ----------

# MAGIC %md
# MAGIC ## Ingest all entities

# COMMAND ----------

def ingest_entity(entity: str):
    df = (
        spark.read.format("csv")
        .option("header", "true")
        .option("inferSchema", "false")
        .load(f"{VOLUME_PATH}/{entity}/")
        .select("*", F.col("_metadata.file_path").alias("_source_file"))
        .withColumn("_ingest_ts", F.current_timestamp())
    )
    target = f"{CATALOG}.bronze.{entity}_raw"
    (df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(target))
    spark.sql(f"COMMENT ON TABLE {target} IS 'Bronze raw copy of {entity} CSV files. All columns are strings, as received.'")
    return target, spark.table(target).count()

results = [ingest_entity(e) for e in ENTITIES]
display(spark.createDataFrame(results, "table_name string, row_count long"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Look at the data-quality issues Silver must fix

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Exact duplicate sales line (SL003) and the invalid line (SL011: quantity 0, unknown customer C999)
# MAGIC SELECT sales_line_id, count(*) AS copies, max(quantity) AS quantity, max(customer_id) AS customer_id
# MAGIC FROM fashion_bootcamp.bronze.sales_raw
# MAGIC GROUP BY sales_line_id
# MAGIC HAVING count(*) > 1 OR max(quantity) = '0' OR max(customer_id) = 'C999';

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Customer C005 appears twice: older row has an uppercase email, ' Madrid ' and 'spain'
# MAGIC SELECT customer_id, email, concat('[', city, ']') AS city_with_spaces, country, gender,
# MAGIC        first_purchase_date, last_updated
# MAGIC FROM fashion_bootcamp.bronze.customers_raw
# MAGIC WHERE customer_id IN (SELECT customer_id FROM fashion_bootcamp.bronze.customers_raw
# MAGIC                       GROUP BY customer_id HAVING count(*) > 1)
# MAGIC ORDER BY last_updated;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Inconsistent text in products: ' Zara ' with spaces, lowercase categories
# MAGIC SELECT product_id, concat('[', brand, ']') AS brand_with_spaces, category
# MAGIC FROM fashion_bootcamp.bronze.products_raw
# MAGIC WHERE brand <> trim(brand) OR category <> initcap(category);
