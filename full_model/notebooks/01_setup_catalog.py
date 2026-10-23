# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Full industry model - set up the catalog and land the raw data
# MAGIC
# MAGIC The **full model** builds all 10 domains / 116 tables of the Lakehouse Industry Data Model *Consumer
# MAGIC Goods v2 MVM* for Fjällmark in its own catalog (default `cpg_full_<your short user name>`, separate from
# MAGIC the bootcamp catalog). This notebook prepares everything the full-model pipeline needs:
# MAGIC
# MAGIC | step | what | why |
# MAGIC |---|---|---|
# MAGIC | 1 | work out **the catalog name** (`cpg_full_<your short user name>`) | the bundle uses the same default, so nothing needs to be typed twice |
# MAGIC | 2 | find the **full_model folder** and the repository root | the CSV files ship with the repository: the 3 bootcamp domains in `bootcamp/data/`, the other 7 in `full_model/data/` (every file is stored once) |
# MAGIC | 3 | create (or reuse) the **catalog** | your own sandbox - nobody else writes into it |
# MAGIC | 4 | create the **schemas** `landing`, `bronze`, `silver`, `governance` and one gold schema per domain (10) | medallion layers + the industry data model's domains |
# MAGIC | 5 | create the **volume** `landing.raw_files` | the landing zone the pipeline's Auto Loader reads from |
# MAGIC | 6 | **copy the CSV files** from the Git folder into the volume | one folder per table: `/Volumes/<catalog>/landing/raw_files/<domain>/<table>/` |
# MAGIC | 7 | **verify** the files | catch problems now, not in the middle of the pipeline |
# MAGIC
# MAGIC ▶ **How to run:** attach to **Serverless** compute and click **Run all**.
# MAGIC
# MAGIC 🔁 **Load once:** re-running is safe and fast - existing catalog, schemas, volume and CSV files are
# MAGIC kept as they are (nothing is copied twice), so the pipeline never has to load the data again.
# MAGIC
# MAGIC **Expected result:** a green summary at the end and instructions for deploying the pipeline bundle.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC The widgets at the top of the notebook control the run. The defaults are right for the lab - just run.
# MAGIC
# MAGIC | widget | meaning |
# MAGIC |---|---|
# MAGIC | `catalog` | leave **blank** to use `cpg_full_<your short user name>` |
# MAGIC | `managed_location` | optional cloud storage path for a **new** catalog (ask your instructor; usually blank) |
# MAGIC | `overwrite` | `true` re-copies the CSV files even if they are already in the volume (repairs only - see step 6) |
# MAGIC
# MAGIC All 10 domains of the industry data model: consumer, distribution, finance, manufacturing, procurement,
# MAGIC product, promotion, quality, sales, supply (116 tables).

# COMMAND ----------

import json
import os
import re
import shutil
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

dbutils.widgets.text("catalog", "", "Catalog (blank = automatic)")
dbutils.widgets.text("managed_location", "", "Managed location (optional)")
dbutils.widgets.dropdown("overwrite", "false", ["false", "true"], "Overwrite CSV files")

DOMAINS = ["consumer", "distribution", "finance", "manufacturing", "procurement",
           "product", "promotion", "quality", "sales", "supply"]      # = gold schemas
BOOTCAMP_DOMAINS = ["consumer", "finance", "manufacturing"]           # CSVs live in bootcamp/data


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}: the part before '@',
    lower-cased, every character that is not a letter or digit replaced by '_'."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


user_name = spark.sql("SELECT current_user()").first()[0]
short_name = bundle_short_name(user_name)
catalog = dbutils.widgets.get("catalog").strip() or f"cpg_full_{short_name}"
if not re.fullmatch(r"[A-Za-z0-9_]+", catalog):
    # The pipeline SQL and the metric views use the catalog name without back-quotes, so it may only contain
    # ASCII letters, digits and '_' (a user name such as "björn" would give the default catalog "cpg_björn").
    raise ValueError(
        f"Catalog name {catalog!r} contains characters other than ASCII letters, digits and '_'. Type a catalog "
        f"name such as 'cpg_bjorn' into the 'catalog' widget, and set the same name as variables.catalog.default "
        f"in full_model/databricks.yml before you deploy the bundle (CLI: --var catalog=<name>).")
managed_location = dbutils.widgets.get("managed_location").strip()
overwrite = dbutils.widgets.get("overwrite") == "true"
domains = DOMAINS

print(f"You are            : {user_name}")
print(f"Bundle short name  : {short_name}")
print(f"Catalog            : {catalog}")
print(f"Domains            : {', '.join(domains)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Find the full_model folder and the bootcamp data
# MAGIC
# MAGIC The notebook walks up from its own path to the folder that holds `databricks.yml` (= `full_model/`).
# MAGIC The repository root is its parent. CSV files are stored **once** in the repository:
# MAGIC
# MAGIC | domains | CSV folder |
# MAGIC |---|---|
# MAGIC | consumer, finance, manufacturing | `<repo>/bootcamp/data/<domain>/<table>.csv` |
# MAGIC | the other 7 | `<repo>/full_model/data/<domain>/<table>.csv` |
# MAGIC
# MAGIC Run this notebook from the **Git folder** (a bundle deployment of `full_model/` does not contain the CSVs).

# COMMAND ----------


def bundle_root() -> str:
    """The folder that holds databricks.yml (this notebook lives somewhere below it)."""
    try:
        nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        d = os.path.dirname(nb_path if nb_path.startswith("/Workspace") else "/Workspace" + nb_path)
    except Exception:  # fallback: notebooks run with the notebook folder as working directory
        d = os.getcwd()
    while d not in ("", "/"):
        if os.path.isfile(f"{d}/databricks.yml"):
            return d
        d = os.path.dirname(d)
    raise FileNotFoundError("databricks.yml not found above this notebook - run it from the Git folder.")


BUNDLE_ROOT = bundle_root()                      # <repo>/full_model
REPO_ROOT = os.path.dirname(BUNDLE_ROOT)         # <repo>
DATA_DIR = f"{BUNDLE_ROOT}/data"                 # the 7 non-bootcamp domains + manifest of all 116 tables
BOOTCAMP_DATA_DIR = f"{REPO_ROOT}/bootcamp/data" # consumer, finance, manufacturing
TAGS_DIR = f"{BUNDLE_ROOT}/src/model_tags"
print(f"full_model folder : {BUNDLE_ROOT}")
print(f"bootcamp data     : {BOOTCAMP_DATA_DIR}")
for p in (DATA_DIR, BOOTCAMP_DATA_DIR, TAGS_DIR):
    if not os.path.isdir(p):
        raise FileNotFoundError(
            f"{p} not found. Run this notebook from the repository's Git folder (Workspace -> Create -> Git folder "
            f"-> paste the repository URL), so that bootcamp/data and full_model/data are both present.")


def csv_dir(domain: str) -> str:
    return BOOTCAMP_DATA_DIR if domain in BOOTCAMP_DOMAINS else DATA_DIR

# The industry model's domain descriptions (become schema comments) and table lists.
model = {}
for d in domains:
    with open(f"{TAGS_DIR}/{d}.json", encoding="utf-8") as fh:
        model[d] = json.load(fh)
print("Tables in scope :", sum(len(model[d]["tables"]) for d in domains))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Create (or reuse) your catalog
# MAGIC
# MAGIC * If the catalog already exists (for example created by your instructor) it is simply reused.
# MAGIC * Otherwise the notebook tries `CREATE CATALOG`. On workspaces whose metastore uses **Default Storage**,
# MAGIC   creating a catalog with SQL needs a `managed_location`; without one, the notebook stops and tells you
# MAGIC   how to create the catalog in the UI (it takes 30 seconds), then you simply run the notebook again.

# COMMAND ----------


def sql_str(text: str) -> str:
    """Quote a Python string as a SQL string literal."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def catalog_exists(name: str) -> bool:
    return spark.sql(f"SHOW CATALOGS LIKE {sql_str(name)}").count() > 0


UI_HELP = f"""
------------------------------------------------------------------------------------------
The catalog `{catalog}` could not be created with SQL on this workspace.
Please create it in the UI (30 seconds), then run this notebook again:

  1. Left sidebar -> Catalog  (Catalog Explorer)
  2. Click  "+"  (top of the catalog list) -> "Create a catalog"
  3. Catalog name: {catalog}
     Type: Standard   |   Storage location: leave the default (Default Storage)
  4. Click "Create"  (you do not need to change the permissions)

Alternative: ask the instructor for a managed storage location and enter it in the
`managed_location` widget.
------------------------------------------------------------------------------------------
"""

if catalog_exists(catalog):
    print(f"✅ Catalog `{catalog}` already exists - reusing it.")
else:
    stmt = f"CREATE CATALOG IF NOT EXISTS `{catalog}`"
    if managed_location:
        stmt += f" MANAGED LOCATION {sql_str(managed_location)}"
    stmt += f" COMMENT {sql_str('Genie bootcamp - Fjällmark Consumer Goods full industry model of ' + user_name)}"
    try:
        spark.sql(stmt)
        print(f"✅ Catalog `{catalog}` created.")
    except Exception as e:
        msg = str(e)
        print(UI_HELP)
        if "storage root" in msg.lower() or "default storage" in msg.lower() or "managed location" in msg.lower():
            raise RuntimeError(f"Create the catalog `{catalog}` in the UI (see instructions above), then re-run.") from None
        raise

spark.sql(f"USE CATALOG `{catalog}`")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Create the schemas
# MAGIC
# MAGIC | schema | holds |
# MAGIC |---|---|
# MAGIC | `landing` | the volume `raw_files` with the CSV extracts |
# MAGIC | `bronze` | raw rows, all columns as text (`bronze.<domain>_<table>`) |
# MAGIC | `silver` | typed, cleaned, de-duplicated rows (`silver.<domain>_<table>`) |
# MAGIC | `consumer`, `distribution`, `finance`, `manufacturing`, `procurement`, `product`, `promotion`, `quality`, `sales`, `supply` | **gold** - the exact industry tables plus metric views |
# MAGIC | `governance` | row-filter / column-mask functions and access-mapping tables (notebook 03) |
# MAGIC
# MAGIC The gold schemas get the industry model's domain description as comment - Genie reads it.

# COMMAND ----------

LAYER_SCHEMAS = {
    "landing": "Landing zone: volume raw_files holds the CSV extracts (one folder per table) read by the pipeline.",
    "bronze": "Bronze layer: raw rows exactly as delivered (all columns STRING) + lineage columns. Written by cpg_lakehouse_pipeline.",
    "silver": "Silver layer: typed, cleaned and de-duplicated rows with data-quality expectations. Written by cpg_lakehouse_pipeline.",
    "governance": "Governance: row-filter and column-mask functions plus the access-mapping tables that drive them.",
}
for schema, comment in LAYER_SCHEMAS.items():
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}` COMMENT {sql_str(comment)}")
for d in domains:
    comment = model[d]["schema_comment"]
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{d}` COMMENT {sql_str(comment)}")
    current = spark.sql(f"SELECT comment FROM `{catalog}`.information_schema.schemata WHERE schema_name = :s",
                        {"s": d}).first()
    if current is None or current.comment != comment:                          # only when changed
        spark.sql(f"COMMENT ON SCHEMA `{catalog}`.`{d}` IS {sql_str(comment)}")

display(spark.sql(f"SHOW SCHEMAS IN `{catalog}`"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Create the landing volume

# COMMAND ----------

spark.sql(f"""CREATE VOLUME IF NOT EXISTS `{catalog}`.`landing`.`raw_files`
COMMENT 'CSV extracts of the Fjällmark source systems: <domain>/<table>/<table>.csv'""")
VOLUME_ROOT = f"/Volumes/{catalog}/landing/raw_files"
print(f"✅ Volume ready: {VOLUME_ROOT}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Copy the CSV files into the volume
# MAGIC
# MAGIC Each table gets its **own folder** - Auto Loader in the bronze layer watches one folder per table.
# MAGIC Files that are already in the volume are **skipped** - the data is loaded once.
# MAGIC
# MAGIC > ℹ️ Auto Loader ingests each file **once**, and the pipeline never needs a full refresh. `overwrite = true`
# MAGIC > is only for repairing a damaged volume file *before* the first pipeline run - a file replaced after the
# MAGIC > pipeline has run is not read again.

# COMMAND ----------

jobs = []
missing = []
for d in domains:
    for table in model[d]["tables"]:
        src = f"{csv_dir(d)}/{d}/{table}.csv"
        dst_dir = f"{VOLUME_ROOT}/{d}/{table}"
        if not os.path.isfile(src):
            missing.append(src)
            continue
        jobs.append((d, table, src, dst_dir, f"{dst_dir}/{table}.csv"))
if missing:
    raise FileNotFoundError(f"{len(missing)} CSV file(s) missing in the Git folder, e.g. {missing[:3]}")


def copy_one(job):
    d, table, src, dst_dir, dst = job
    size = os.path.getsize(src)
    if os.path.exists(dst) and not overwrite:
        same = os.path.getsize(dst) == size
        return (d, table, "skipped (already there)" if same else "DIFFERENT - set overwrite=true", size)
    os.makedirs(dst_dir, exist_ok=True)
    for attempt in range(3):
        try:
            shutil.copyfile(src, dst)
            return (d, table, "copied", size)
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


t0 = time.time()
with ThreadPoolExecutor(max_workers=16) as pool:
    results = list(pool.map(copy_one, jobs))
copied = sum(1 for r in results if r[2] == "copied")
skipped = sum(1 for r in results if r[2].startswith("skipped"))
different = [r for r in results if r[2].startswith("DIFFERENT")]
print(f"{len(results)} files: {copied} copied, {skipped} already present, {len(different)} different "
      f"in {time.time() - t0:.1f}s ({sum(r[3] for r in results) / 1e6:.1f} MB in scope)")
if different:
    print("⚠️ These volume files differ from the Git folder (kept as they are):",
          [f"{r[0]}.{r[1]}" for r in different][:10])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Verify the landed files
# MAGIC
# MAGIC Every table must have exactly one non-empty CSV in its folder, identical in size to the
# MAGIC Git folder copy. `full_model/data/manifest.json` (all 116 tables) adds the number of rows in each CSV and how many rows remain
# MAGIC after the silver layer has removed duplicates and broken records (`rows_after_cleaning`).

# COMMAND ----------

manifest_rows = {}   # "<domain>.<table>" -> (rows in the CSV, rows expected after silver cleaning)
manifest_path = f"{DATA_DIR}/manifest.json"
if os.path.isfile(manifest_path):
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)        # {domain: {table: {"rows": .., "clean_rows": .., ...}}}
    for d, tables_meta in manifest.items():
        if isinstance(tables_meta, dict):
            for table, meta in tables_meta.items():
                if isinstance(meta, dict) and "rows" in meta:
                    manifest_rows[f"{d}.{table}"] = (meta.get("rows"), meta.get("clean_rows"))

problems = []
summary = []
for d, table, src, dst_dir, dst in jobs:
    files = [f for f in os.listdir(dst_dir) if not f.startswith(".")] if os.path.isdir(dst_dir) else []
    ok = files == [f"{table}.csv"] and os.path.getsize(dst) == os.path.getsize(src) and os.path.getsize(dst) > 0
    if not ok:
        problems.append(f"{d}.{table}: files={files}")
    rows, clean_rows = manifest_rows.get(f"{d}.{table}", (None, None))
    summary.append((d, table, os.path.getsize(dst) if os.path.exists(dst) else 0, rows, clean_rows,
                    "OK" if ok else "PROBLEM"))

display(spark.createDataFrame(summary, "domain string, table string, bytes long, csv_rows long, "
                                       "rows_after_cleaning long, status string")
        .orderBy("domain", "table"))
if problems:
    raise RuntimeError(f"{len(problems)} table folder(s) are not as expected: {problems[:5]}")
print(f"✅ {len(summary)} CSV files verified in {VOLUME_ROOT}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8 · Next step: deploy and run the pipeline bundle
# MAGIC
# MAGIC The pipeline (bronze → silver → gold) and the job that builds the metric views are defined as code in
# MAGIC **`full_model/databricks.yml`** (a *Declarative Automation Bundle*), next to this `notebooks/` folder.
# MAGIC
# MAGIC 1. In the workspace file browser open the Git folder → `full_model` and click **`databricks.yml`**.
# MAGIC 2. Click the **Deployments** icon (🚀 rocket) in the left pane of the editor.
# MAGIC 3. Select target **`full`** → **Deploy**. (First deployment: ~1 minute.)
# MAGIC 4. Under *Bundle resources* find the job **`cpg_lakehouse_job`** → click **Run** (▶).
# MAGIC 5. Open the job run: `pipeline` → `metric_views` + `model_tags` → `validate` should all turn green
# MAGIC    (see `full_model/README.md` for run times).
# MAGIC
# MAGIC > ℹ️ **First run only:** the pipeline's event log may show one update *"FAILED unexpectedly"* followed by an
# MAGIC > automatic retry (both inside the same job run). The first update loads all data; Lakeflow registers the keys of
# MAGIC > brand-new tables only for small sets of foreign keys (up to 8 worked, 13 or more failed), so it fails while
# MAGIC > registering them. The retry reads no files and registers the keys (on the bootcamp: all materialized views
# MAGIC > `NO_OP`). Never use *Full refresh*. On the earlier test catalog the automatic retry was cancelled and the next
# MAGIC > job run registered all 116 primary and 733 foreign keys with every materialized view `NO_OP`.
# MAGIC
# MAGIC The bundle's default catalog is `cpg_full_<your short user name>` - the same as this notebook's default.
# MAGIC If you typed a **different catalog** above, change `variables.catalog.default` in `databricks.yml`
# MAGIC (or deploy with the CLI from the `full_model` folder: `databricks bundle deploy -t full --var catalog=<name>`).
# MAGIC
# MAGIC 🔁 Running the job again later loads nothing: the pipeline finds no new files (every materialized view `NO_OP`)
# MAGIC and the metric-view and tag tasks only apply what is missing or changed.

# COMMAND ----------

print(f"""
✅ Setup complete for catalog `{catalog}` ({len(domains)} domains, {len(results)} tables).

NEXT: open full_model/databricks.yml in this Git folder -> Deployments (rocket icon) -> target 'full'
      -> Deploy -> run the job 'cpg_lakehouse_job'.
""")
dbutils.notebook.exit(json.dumps({"catalog": catalog, "files": len(results), "copied": copied,
                                  "already_present": skipped, "different": len(different), "verified": len(summary)}))
