# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup — Genie Bootcamp (Scandinavian Retail)
# MAGIC
# MAGIC Creates the Unity Catalog objects and copies the raw CSV extracts from this Git folder into the landing volume.
# MAGIC
# MAGIC | Object | Purpose |
# MAGIC |---|---|
# MAGIC | `retail_bootcamp` | Catalog for the bootcamp |
# MAGIC | `landing` / `bronze` / `silver` / `gold` | Medallion schemas |
# MAGIC | `landing.raw_files` | Managed volume holding the CSV extracts |
# MAGIC
# MAGIC **Run this notebook from the repo cloned as a Databricks Git folder.**

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters

# COMMAND ----------

dbutils.widgets.text("catalog", "retail_bootcamp", "Catalog")
dbutils.widgets.text("repo_root", "", "Repo root (leave empty to auto-detect)")

CATALOG = dbutils.widgets.get("catalog")
VOLUME_PATH = f"/Volumes/{CATALOG}/landing/raw_files"
print(f"Catalog: {CATALOG}\nVolume : {VOLUME_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Catalog, schemas and volume
# MAGIC If your metastore requires a managed location, create the catalog first with
# MAGIC `CREATE CATALOG retail_bootcamp MANAGED LOCATION '<path>'`, or ask your workspace admin.

# COMMAND ----------

spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG} COMMENT 'Databricks Genie bootcamp - Scandinavian retail demo'")
spark.sql(f"USE CATALOG {CATALOG}")

for schema, comment in [
    ("landing", "Raw file landing zone (volumes)"),
    ("bronze", "Raw tables, one per source extract, all STRING columns"),
    ("silver", "Cleaned, typed and conformed tables"),
    ("gold", "Star schema used by the Genie space"),
]:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{schema} COMMENT '{comment}'")

spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.landing.raw_files COMMENT 'Source system CSV extracts'")
display(spark.sql(f"SHOW SCHEMAS IN {CATALOG}"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Copy CSV extracts from the repo into the volume
# MAGIC Layout is preserved: `data/raw/<entity>/<date>-raw-<entity>.csv` → `/Volumes/.../raw_files/<entity>/...`

# COMMAND ----------

import os, shutil

repo_root = dbutils.widgets.get("repo_root")
if not repo_root:
    nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    repo_root = "/Workspace" + os.path.dirname(os.path.dirname(nb_path))   # notebooks/ -> repo root

src = os.path.join(repo_root, "data", "raw")
assert os.path.isdir(src), f"Source folder not found: {src}. Set the repo_root widget."

copied = 0
for entity in sorted(os.listdir(src)):
    os.makedirs(f"{VOLUME_PATH}/{entity}", exist_ok=True)
    for f in os.listdir(os.path.join(src, entity)):
        if f.endswith(".csv"):
            shutil.copy(os.path.join(src, entity, f), f"{VOLUME_PATH}/{entity}/{f}")
            copied += 1
print(f"Copied {copied} files from {src}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Check what landed

# COMMAND ----------

rows = [(e, f.name, f.size) for e in sorted(os.listdir(VOLUME_PATH)) for f in dbutils.fs.ls(f"{VOLUME_PATH}/{e}")]
display(spark.createDataFrame(rows, "entity STRING, file_name STRING, size_bytes LONG"))
print(f"{len(rows)} files in {VOLUME_PATH} (expected 27)")
