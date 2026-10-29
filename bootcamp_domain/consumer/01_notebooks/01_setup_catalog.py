# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 01 · Set up your catalog and land the raw data
# MAGIC
# MAGIC **Genie domain sample Consumer.** **Fjällmark Consumer Goods AB** keeps its data in one Unity Catalog
# MAGIC *catalog* per participant. This notebook prepares everything the sample's data pipeline needs:
# MAGIC
# MAGIC | step | what | why |
# MAGIC |---|---|---|
# MAGIC | 1 | work out **your catalog name** (`cpg_consumer_<your short user name>`) | the bundle uses the same default, so nothing needs to be typed twice |
# MAGIC | 2 | find the **sample folder** this notebook lives in and the repository root | the CSV files ship with the repository, **once**, in `bootcamp/data/...` |
# MAGIC | 3 | create (or reuse) the **catalog** | your own sandbox - nobody else writes into it |
# MAGIC | 4 | create the **schemas** `landing`, `bronze`, `silver`, `governance` and the gold schemas `consumer` and `finance` | medallion layers + the industry data model's domains |
# MAGIC | 5 | create the **volume** `landing.raw_files` | the landing zone the pipeline's Auto Loader reads from |
# MAGIC | 6 | **copy the sample's CSV files** from the Git folder into the volume | one folder per table: `/Volumes/<catalog>/landing/raw_files/<domain>/<table>/` |
# MAGIC | 7 | **verify** the files | catch problems now, not in the middle of the pipeline |
# MAGIC
# MAGIC ▶ **How to run:** open this notebook **in the Git folder** (a bundle deployment does not contain the CSV
# MAGIC files), attach to **Serverless** compute and click **Run all**.
# MAGIC
# MAGIC 🔁 **Load once:** re-running is safe and fast - existing catalog, schemas, volume and CSV files are
# MAGIC kept as they are (nothing is copied twice), so the pipeline never has to load the data again.
# MAGIC
# MAGIC **Expected result:** a green summary at the end and instructions for deploying the pipeline bundle.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC The widgets at the top of the notebook control the run. The defaults are right for the sample - just run.
# MAGIC
# MAGIC | widget | meaning |
# MAGIC |---|---|
# MAGIC | `catalog` | leave **blank** to use `cpg_consumer_<your short user name>` |
# MAGIC | `managed_location` | optional cloud storage path for a **new** catalog (ask your instructor; usually blank) |
# MAGIC | `overwrite` | `true` re-copies the CSV files even if they are already in the volume (repairs only - see step 6) |
# MAGIC
# MAGIC The sample covers the **consumer** domain of the industry data model (12 tables) plus
# MAGIC 4 reference tables of **finance** (`profit_center`, `journal_entry`, `journal_entry_line`, `company_code`)
# MAGIC that the curated metric view (entity, brand, EUR rate) and the governance step (company codes) need - 16 tables.

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

SAMPLE = "consumer"
DOMAINS = ["consumer", "finance"]   # the sample's gold schemas (main domain first)
MAIN_DOMAIN = "consumer"


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}: the part before '@',
    lower-cased, every character that is not a letter or digit replaced by '_'."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


user_name = spark.sql("SELECT current_user()").first()[0]
short_name = bundle_short_name(user_name)
catalog = dbutils.widgets.get("catalog").strip() or f"cpg_{SAMPLE}_{short_name}"
if not re.fullmatch(r"[A-Za-z0-9_]+", catalog):
    # The pipeline SQL and the metric views use the catalog name without back-quotes, so it may only contain
    # ASCII letters, digits and '_' (a user name such as "björn" would give the default catalog "cpg_consumer_björn").
    raise ValueError(
        f"Catalog name {catalog!r} contains characters other than ASCII letters, digits and '_'. Type a catalog "
        f"name such as 'cpg_{SAMPLE}_bjorn' into the 'catalog' widget, and set the same name as "
        f"variables.catalog.default in bootcamp_domain/{SAMPLE}/databricks.yml before you deploy the bundle "
        f"(CLI: --var catalog=<name>).")
managed_location = dbutils.widgets.get("managed_location").strip()
overwrite = dbutils.widgets.get("overwrite") == "true"

print(f"You are            : {user_name}")
print(f"Bundle short name  : {short_name}")
print(f"Catalog            : {catalog}")
print(f"Domains            : {', '.join(DOMAINS)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Find the sample folder and the bootcamp data
# MAGIC
# MAGIC The notebook walks up from its own path to the folder that holds `databricks.yml`
# MAGIC (= `bootcamp_domain/consumer/`). The repository root is two levels above it. The sample does **not** copy
# MAGIC the CSV files - `01_data/manifest.json` lists the sample's tables and, for each one, the file in the
# MAGIC repository (`bootcamp/data/<domain>/<table>.csv`).
# MAGIC
# MAGIC Run this notebook from the **Git folder** (a bundle deployment of the sample does not contain the CSVs).

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


BUNDLE_ROOT = bundle_root()                                 # <repo>/bootcamp_domain/consumer
REPO_ROOT = os.path.dirname(os.path.dirname(BUNDLE_ROOT))   # <repo>
DATA_DIR = f"{BUNDLE_ROOT}/01_data"                            # manifest.json of the sample's tables
TAGS_DIR = f"{BUNDLE_ROOT}/02_model_tags"
BOOTCAMP_DATA_DIR = f"{REPO_ROOT}/bootcamp/data"            # the CSV files (stored once in the repository)
print(f"Sample folder : {BUNDLE_ROOT}")
print(f"Bootcamp data : {BOOTCAMP_DATA_DIR}")
for p in (DATA_DIR, TAGS_DIR, BOOTCAMP_DATA_DIR):
    if not os.path.isdir(p):
        raise FileNotFoundError(
            f"{p} not found. Run this notebook from the repository's Git folder (Workspace -> Create -> Git folder "
            f"-> paste the repository URL), so that bootcamp/data and bootcamp_domain/{SAMPLE} are both present.")

# The sample's tables (01_data/manifest.json: domain -> table -> rows, clean_rows, file, ...) and the industry
# model's domain descriptions (02_model_tags/<domain>.json; they become schema comments).
with open(f"{DATA_DIR}/manifest.json", encoding="utf-8") as fh:
    manifest = json.load(fh)
model = {}
for d in DOMAINS:
    with open(f"{TAGS_DIR}/{d}.json", encoding="utf-8") as fh:
        model[d] = json.load(fh)
    if not isinstance(manifest.get(d), dict) or not manifest[d]:
        raise ValueError(f"01_data/manifest.json has no tables for domain {d!r}")
print("Tables in scope :", sum(len(manifest[d]) for d in DOMAINS),
      "(" + ", ".join(f"{d}: {len(manifest[d])}" for d in DOMAINS) + ")")

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
    stmt += f" COMMENT {sql_str('Genie domain sample Consumer - Fjällmark Consumer Goods lakehouse of ' + user_name)}"
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
# MAGIC # MAGIC | `consumer` | **gold** - the exact industry tables of the domain plus metric views |
# MAGIC | `finance` | **gold** - the 4 finance reference tables (exact industry tables) |
# MAGIC | `governance` | row-filter / column-mask functions and access-mapping tables (notebook 03) |
# MAGIC
# MAGIC The gold schemas get the industry model's domain description as comment - Genie reads it.

# COMMAND ----------

LAYER_SCHEMAS = {
    "landing": "Landing zone: volume raw_files holds the CSV extracts (one folder per table) read by the pipeline.",
    "bronze": "Bronze layer: raw rows exactly as delivered (all columns STRING) + lineage columns. Written by cpg_consumer_pipeline.",
    "silver": "Silver layer: typed, cleaned and de-duplicated rows with data-quality expectations. Written by cpg_consumer_pipeline.",
    "governance": "Governance: row-filter and column-mask functions plus the access-mapping tables that drive them.",
}
for schema, comment in LAYER_SCHEMAS.items():
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}` COMMENT {sql_str(comment)}")
for d in DOMAINS:
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
# MAGIC Only the tables of this sample (`01_data/manifest.json`) are copied, each one from the file the manifest
# MAGIC names (`<repo>/bootcamp/data/<domain>/<table>.csv`). Each table gets its **own folder** - Auto Loader in
# MAGIC the bronze layer watches one folder per table. Files that are already in the volume are **skipped** - the
# MAGIC data is loaded once.
# MAGIC
# MAGIC > ℹ️ Auto Loader ingests each file **once**, and the pipeline never needs a full refresh. `overwrite = true`
# MAGIC > is only for repairing a damaged volume file *before* the first pipeline run - a file replaced after the
# MAGIC > pipeline has run is not read again. With `overwrite = false` a volume file whose size differs from the
# MAGIC > Git folder copy is **kept** and reported as `WARN` in step 7 (the run does not stop).

# COMMAND ----------

jobs = []
missing = []
for d in DOMAINS:
    for table, meta in manifest[d].items():
        src = f"{REPO_ROOT}/{meta['file']}"
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
        return (d, table, "skipped (already there)" if same else "DIFFERENT - kept (overwrite=false)", size)
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
    print("⚠️ These volume files differ from the Git folder and are kept as they are (step 7 reports them as WARN; "
          "to replace them before the first pipeline run, set overwrite=true):",
          [f"{r[0]}.{r[1]}" for r in different][:10])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Verify the landed files
# MAGIC
# MAGIC Every table must have exactly one non-empty CSV in its folder. Its size should equal the Git folder copy:
# MAGIC
# MAGIC | status | meaning | stops the notebook |
# MAGIC |---|---|---|
# MAGIC | `OK` | one non-empty file, same size as in the Git folder | no |
# MAGIC | `WARN` | the file was already in the volume with a different size and kept (`overwrite = false`, step 6) | no |
# MAGIC | `PROBLEM` | no file / extra files / empty file, or a freshly copied file whose size differs | yes |
# MAGIC
# MAGIC `01_data/manifest.json` adds the number of rows in each CSV and how many rows remain after the silver layer
# MAGIC has removed duplicates and broken records (`rows_after_cleaning`).

# COMMAND ----------

manifest_rows = {}   # "<domain>.<table>" -> (rows in the CSV, rows expected after silver cleaning)
for d in DOMAINS:
    for table, meta in manifest[d].items():
        if isinstance(meta, dict) and "rows" in meta:
            manifest_rows[f"{d}.{table}"] = (meta.get("rows"), meta.get("clean_rows"))

kept_different = {(r[0], r[1]) for r in different}   # differing files that step 6 kept on purpose
problems = []
warnings = []
summary = []
for d, table, src, dst_dir, dst in jobs:
    files = [f for f in os.listdir(dst_dir) if not f.startswith(".")] if os.path.isdir(dst_dir) else []
    size = os.path.getsize(dst) if os.path.exists(dst) else 0
    present = files == [f"{table}.csv"] and size > 0
    if not present:
        status = "PROBLEM"
        problems.append(f"{d}.{table}: files={files}, bytes={size}")
    elif size == os.path.getsize(src):
        status = "OK"
    elif (d, table) in kept_different:
        status = "WARN"
        warnings.append(f"{d}.{table}: {size} bytes in the volume, {os.path.getsize(src)} in the Git folder")
    else:
        status = "PROBLEM"
        problems.append(f"{d}.{table}: copied file has {size} bytes, the Git folder copy {os.path.getsize(src)}")
    rows, clean_rows = manifest_rows.get(f"{d}.{table}", (None, None))
    summary.append((d, table, size, rows, clean_rows, status))

display(spark.createDataFrame(summary, "domain string, table string, bytes long, csv_rows long, "
                                       "rows_after_cleaning long, status string")
        .orderBy("domain", "table"))
if problems:
    raise RuntimeError(f"{len(problems)} table folder(s) are not as expected: {problems[:5]}")
if warnings:
    print(f"⚠️ {len(warnings)} volume file(s) differ in size from the Git folder and were kept (overwrite=false). "
          f"If the pipeline has not run yet and the files are damaged, re-run with overwrite=true: {warnings[:5]}")
print(f"✅ {len(summary) - len(warnings)} CSV files verified in {VOLUME_ROOT}"
      + (f" ({len(warnings)} kept with a different size)" if warnings else ""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8 · Next step: deploy and run the pipeline bundle
# MAGIC
# MAGIC The pipeline (bronze → silver → gold) and the job that builds the metric views are defined as code in
# MAGIC **`bootcamp_domain/consumer/databricks.yml`** (a *Declarative Automation Bundle*), next to this `01_notebooks/` folder.
# MAGIC
# MAGIC 1. In the workspace file browser open the Git folder → `bootcamp_domain` → `consumer` and click **`databricks.yml`**.
# MAGIC 2. Click the **Deployments** icon (🚀 rocket) in the left pane of the editor.
# MAGIC 3. Select target **`dev`** → **Deploy**.
# MAGIC 4. Under *Bundle resources* find the job **`cpg_consumer_job`** → click **Run** (▶).
# MAGIC 5. Open the job run: `pipeline` → `metric_views` + `model_tags` → `validate` should all turn green.
# MAGIC
# MAGIC > ℹ️ **First run only:** the pipeline page may show one update *"FAILED unexpectedly"* followed by an
# MAGIC > automatic retry (*Retry on failure*) that completes - both inside the same job run, and the job task stays
# MAGIC > green. The first update **loads all the data**; Lakeflow registers the keys of brand-new tables only for small
# MAGIC > sets of foreign keys, and this sample's gold tables declare 16 primary keys and 42 foreign keys.
# MAGIC > The retry reads **no** files and loads nothing; it only registers the keys. Never use *Full refresh*.
# MAGIC > Details: the header of `02_pipeline/consumer/03_gold.sql`.
# MAGIC
# MAGIC The bundle's default catalog is `cpg_consumer_<your short user name>` - the same as this notebook's default.
# MAGIC If you typed a **different catalog** above, change `variables.catalog.default` in `databricks.yml`
# MAGIC (or deploy with the CLI from the `bootcamp_domain/consumer` folder:
# MAGIC `databricks bundle deploy -t dev --var catalog=<name>`).
# MAGIC
# MAGIC 🔁 Running the job again later loads nothing: the pipeline reads no new files and leaves bronze and silver
# MAGIC untouched, and the metric-view and tag tasks only apply what is missing or changed. Once step 3 (governance)
# MAGIC has attached its row filters and masks, every run recomputes the gold tables whose build-order hint reads a
# MAGIC governed table (Lakeflow cannot refresh those incrementally) - the same rows, no file read, no reload.

# COMMAND ----------

print(f"""
✅ Setup complete for catalog `{catalog}` ({len(DOMAINS)} domain(s), {len(results)} tables).

NEXT: open bootcamp_domain/{SAMPLE}/databricks.yml in this Git folder -> Deployments (rocket icon)
      -> target 'dev' -> Deploy -> run the job 'cpg_{SAMPLE}_job'.
""")
dbutils.notebook.exit(json.dumps({"catalog": catalog, "files": len(results), "copied": copied,
                                  "already_present": skipped, "different": len(different),
                                  "verified": len(summary) - len(warnings), "warned": len(warnings)}))
