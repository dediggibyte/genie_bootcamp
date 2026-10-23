# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup — Maison Europa Group (Genie Bootcamp)
# MAGIC
# MAGIC Creates the Unity Catalog objects and loads the 8 raw CSV files into a volume.
# MAGIC
# MAGIC | Object | Name |
# MAGIC |---|---|
# MAGIC | Catalog | `fashion_bootcamp` |
# MAGIC | Schemas | `landing`, `bronze`, `silver`, `gold`, `governance` |
# MAGIC | Volume | `fashion_bootcamp.landing.raw_files` (one folder per entity) |
# MAGIC
# MAGIC **Where do the CSVs come from?** The CSVs are separate files in the `data/` folder next to this `notebooks/` folder.
# MAGIC 1. **Recommended:** import the whole project folder (`data/` + `notebooks/`) into your workspace or a Git folder. This notebook reads the CSVs from `../data` and writes them to the volume with `dbutils.fs.put`.
# MAGIC 2. **Alternative:** in Catalog Explorer, open the volume and upload each CSV into its entity folder, e.g. `2026-10-17-raw-sales.csv` → `/raw_files/sales/`. Then run only the "verify" cell.
# MAGIC
# MAGIC All data is synthetic. Customer PII uses `example.com` emails and fake phones and addresses.

# COMMAND ----------

dbutils.widgets.text("source_dir", "", "CSV source folder (blank = ../data)")
dbutils.widgets.dropdown("overwrite", "false", ["false", "true"], "Overwrite files in volume")

CATALOG = "fashion_bootcamp"
VOLUME_PATH = f"/Volumes/{CATALOG}/landing/raw_files"
FILE_PREFIX = "2026-10-17-raw-"
ENTITIES = ["country_region", "products", "customers", "stores",
            "sales", "returns", "production", "finance"]

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Catalog, schemas and volume
# MAGIC If your metastore has no default storage, add `MANAGED LOCATION '<your-external-location-path>'` to `CREATE CATALOG`.

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE CATALOG IF NOT EXISTS fashion_bootcamp
# MAGIC   COMMENT 'Genie bootcamp: Maison Europa Group, a fictional European fashion retailer (synthetic data, EUR).';
# MAGIC
# MAGIC CREATE SCHEMA IF NOT EXISTS fashion_bootcamp.landing    COMMENT 'Raw files landing zone (volume).';
# MAGIC CREATE SCHEMA IF NOT EXISTS fashion_bootcamp.bronze     COMMENT 'Raw tables, all columns as strings, plus ingestion metadata. Contains unmasked PII.';
# MAGIC CREATE SCHEMA IF NOT EXISTS fashion_bootcamp.silver     COMMENT 'Cleaned, typed, de-duplicated and validated tables.';
# MAGIC CREATE SCHEMA IF NOT EXISTS fashion_bootcamp.gold       COMMENT 'Star schema for analytics and the Genie space.';
# MAGIC CREATE SCHEMA IF NOT EXISTS fashion_bootcamp.governance COMMENT 'Access mapping tables, row filter and column mask functions.';
# MAGIC
# MAGIC CREATE VOLUME IF NOT EXISTS fashion_bootcamp.landing.raw_files
# MAGIC   COMMENT 'Raw CSV files, one folder per entity.';

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Entity folders

# COMMAND ----------

for entity in ENTITIES:
    dbutils.fs.mkdirs(f"{VOLUME_PATH}/{entity}")
display(dbutils.fs.ls(VOLUME_PATH))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Copy the CSV files into the volume
# MAGIC Reads each `2026-10-17-raw-<entity>.csv` from the source folder and writes it with `dbutils.fs.put`.
# MAGIC Existing files are skipped unless the `overwrite` widget is `true`.

# COMMAND ----------

import os

def default_source_dir():
    """../data relative to this notebook's folder."""
    try:
        nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        base = nb_path if nb_path.startswith("/Workspace") else "/Workspace" + nb_path
        return os.path.join(os.path.dirname(os.path.dirname(base)), "data")
    except Exception:
        return os.path.join(os.path.dirname(os.getcwd()), "data")

def path_exists(path):
    try:
        dbutils.fs.ls(path)
        return True
    except Exception:
        return False

source_dir = dbutils.widgets.get("source_dir").strip() or default_source_dir()
overwrite = dbutils.widgets.get("overwrite") == "true"
print(f"Source folder: {source_dir}\nOverwrite: {overwrite}\n")

for entity in ENTITIES:
    file_name = f"{FILE_PREFIX}{entity}.csv"
    src = os.path.join(source_dir, file_name)
    dst = f"{VOLUME_PATH}/{entity}/{file_name}"
    if not os.path.exists(src):
        print(f"MISSING  {src}  -> upload it manually to {VOLUME_PATH}/{entity}/")
        continue
    if path_exists(dst) and not overwrite:
        print(f"SKIPPED  {dst} (already exists)")
        continue
    with open(src, "r", encoding="utf-8") as f:
        dbutils.fs.put(dst, f.read(), overwrite=overwrite)
    print(f"WRITTEN  {dst}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Verify the files

# COMMAND ----------

rows = []
for entity in ENTITIES:
    try:
        for fi in dbutils.fs.ls(f"{VOLUME_PATH}/{entity}"):
            rows.append((entity, fi.name, fi.size, fi.path))
    except Exception as e:
        rows.append((entity, "<missing>", 0, str(e)[:80]))
display(spark.createDataFrame(rows, "entity string, file_name string, size_bytes long, path string"))

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Quick peek at one file straight from the volume
# MAGIC SELECT * FROM read_files('/Volumes/fashion_bootcamp/landing/raw_files/sales/', format => 'csv', header => true);
