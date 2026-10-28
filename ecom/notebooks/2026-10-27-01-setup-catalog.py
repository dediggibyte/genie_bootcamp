# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 01 · Set up your catalog and land the raw data
# MAGIC
# MAGIC **Nordvik Group** (fictional) runs three business units - *Nordvik Retail*, *Nordvik Mobility* and
# MAGIC *Nordvik Connect* - and keeps their data in one Unity Catalog *catalog* per participant. This notebook
# MAGIC prepares everything the pipelines need:
# MAGIC
# MAGIC | step | what | why |
# MAGIC |---|---|---|
# MAGIC | 1 | work out **your catalog name** (`ecom_<your short user name>`) | the bundle uses the same default, so nothing needs to be typed twice |
# MAGIC | 2 | find the **ecom folder** this notebook lives in | the CSV files and the tag configuration ship with the repository |
# MAGIC | 3 | check that the **`ecom_*` tag keys are free** | a governed tag with the same key would block the tags |
# MAGIC | 4 | create (or reuse) the **catalog** | your own sandbox - nobody else writes into it |
# MAGIC | 5 | create the **schemas** and the **volume** `landing.raw_files` | medallion layers, the three domain schemas, governance and context |
# MAGIC | 6 | **copy the CSV files** from the Git folder into the volume | one folder per table: `/Volumes/<catalog>/landing/raw_files/<domain>/<table>/` |
# MAGIC | 7 | **verify** the files against the manifest | catch problems now, not in the middle of the pipeline |
# MAGIC | 8 | **tag** the catalog, schemas, volume and the ecom notebooks | `ecom_project`, `ecom_domain`, `ecom_layer` - from `config/2026-10-27-tags.json` |
# MAGIC
# MAGIC ▶ **How to run:** attach to **Serverless** compute and click **Run all**.
# MAGIC
# MAGIC 🔁 **Load once:** re-running is safe and fast - existing catalog, schemas, volume, files and tags are kept
# MAGIC as they are (nothing is copied or tagged twice).
# MAGIC
# MAGIC **Expected result:** a green summary at the end and instructions for deploying the bundle.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | meaning |
# MAGIC |---|---|
# MAGIC | `catalog` | leave **blank** to use `ecom_<your short user name>` |
# MAGIC | `managed_location` | optional cloud storage path for a **new** catalog (ask your instructor; usually blank) |
# MAGIC | `overwrite` | `true` re-copies the CSV files even if they are already in the volume (repairs only - see step 6) |

# COMMAND ----------

import json
import os
import re
import shutil
import time
import unicodedata

from databricks.sdk import WorkspaceClient

dbutils.widgets.text("catalog", "", "Catalog (blank = automatic)")
dbutils.widgets.text("managed_location", "", "Managed location (optional)")
dbutils.widgets.dropdown("overwrite", "false", ["false", "true"], "Overwrite CSV files")

DOMAINS = ["retail", "mobility", "telecom"]          # the three domains = gold schemas
CATALOG_MARKER = "[created by ecom bootcamp]"        # notebook 99 drops only a catalog with this marker
DATE = "2026-10-27"                                  # file-name prefix of the data and config files


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}: the part before '@',
    lower-cased, every character that is not a letter or digit replaced by '_'."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


w = WorkspaceClient()
user_name = spark.sql("SELECT current_user()").first()[0]
short_name = bundle_short_name(user_name)
catalog = dbutils.widgets.get("catalog").strip() or f"ecom_{short_name}"
if not re.fullmatch(r"[A-Za-z0-9_]+", catalog):
    # The pipeline SQL and the metric views use the catalog name without back-quotes, so it may only contain
    # ASCII letters, digits and '_' (a user name such as "björn" would give the default catalog "ecom_björn").
    raise ValueError(
        f"Catalog name {catalog!r} contains characters other than ASCII letters, digits and '_'. Type a catalog "
        f"name such as 'ecom_bjorn' into the 'catalog' widget, and set the same name as variables.catalog.default "
        f"in ecom/databricks.yml before you deploy the bundle (CLI: --var catalog=<name>).")
managed_location = dbutils.widgets.get("managed_location").strip()
overwrite = dbutils.widgets.get("overwrite") == "true"

print(f"You are            : {user_name}")
print(f"Bundle short name  : {short_name}")
print(f"Catalog            : {catalog}")
print(f"Domains            : {', '.join(DOMAINS)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Find the ecom folder
# MAGIC
# MAGIC Everything this project needs sits in the folder `ecom/` of the repository - the folder that holds
# MAGIC `databricks.yml`. The notebook walks up from its own path until it finds that file, so this works in a
# MAGIC Git folder, in a copied folder and in a bundle deployment.

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
    raise FileNotFoundError("databricks.yml not found above this notebook - run it from the ecom Git folder.")


BUNDLE_ROOT = bundle_root()
DATA_DIR = f"{BUNDLE_ROOT}/data"
print(f"ecom folder : {BUNDLE_ROOT}")
for p in (DATA_DIR, f"{BUNDLE_ROOT}/config"):
    if not os.path.isdir(p):
        raise FileNotFoundError(
            f"{p} not found. Run this notebook from the repository's Git folder (Workspace -> Create -> Git folder "
            f"-> paste the repository URL), so that data/ and config/ sit next to notebooks/.")

with open(f"{DATA_DIR}/{DATE}-manifest.json", encoding="utf-8") as fh:
    manifest = {d: t for d, t in json.load(fh).items() if isinstance(t, dict)}   # skips the _notice string
with open(f"{BUNDLE_ROOT}/config/{DATE}-tags.json", encoding="utf-8") as fh:
    tag_config = json.load(fh)
print("Source tables :", sum(len(manifest[d]) for d in DOMAINS))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Are the `ecom_*` tag keys free?
# MAGIC
# MAGIC The project uses **plain tags** with the prefix `ecom_`. If an account admin has made one of these keys a
# MAGIC **governed tag** (tag policy), only its allowed values may be set and the tag tasks would fail - so we check
# MAGIC first. If the tag-policy API is not available to you, the check is skipped (information only).

# COMMAND ----------


def all_tag_keys(cfg) -> set:
    keys = set(cfg["catalog"])
    for group in ("schemas", "volumes"):
        for tags in cfg[group].values():
            keys |= set(tags)
    for t in cfg["tables"].values():
        keys |= set(t["tags"])
        for col_tags in t["columns"].values():
            keys |= set(col_tags)
    return keys


our_keys = all_tag_keys(tag_config)
try:
    governed, token = set(), None
    while True:
        resp = w.api_client.do("GET", "/api/2.1/tag-policies", query={"page_token": token} if token else None)
        governed |= {p.get("tag_key") for p in resp.get("tag_policies", [])}
        token = resp.get("next_page_token")
        if not token:
            break
    clash = sorted(our_keys & governed)
    if clash:
        raise RuntimeError(f"These tag keys are governed tags in your account: {clash}. Ask an account admin, or "
                           f"rename the keys in config/{DATE}-tags.json and resources/*.yml.")
    print(f"✅ {len(our_keys)} ecom_* tag keys, none of them governed ({len(governed)} governed tags in the account).")
except RuntimeError:
    raise
except Exception as e:
    print(f"ℹ️ Tag-policy check skipped ({str(e)[:200]}).")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Create (or reuse) your catalog
# MAGIC
# MAGIC * If the catalog already exists (for example created by your instructor) it is simply reused.
# MAGIC * Otherwise the notebook tries `CREATE CATALOG`. On workspaces whose metastore uses **Default Storage**,
# MAGIC   creating a catalog with SQL needs a `managed_location`; without one, the notebook stops and tells you
# MAGIC   how to create the catalog in the UI (it takes 30 seconds), then you simply run the notebook again.
# MAGIC * A catalog created here carries the marker `[created by ecom bootcamp]` in its comment. The cleanup
# MAGIC   notebook (99) drops a catalog only when it carries this marker - otherwise it drops only the project schemas.

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
     Comment (optional, lets notebook 99 drop the whole catalog): {CATALOG_MARKER}
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
    stmt += f" COMMENT {sql_str(f'ecom bootcamp - Nordvik Group lakehouse of {user_name} {CATALOG_MARKER}')}"
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
# MAGIC ## 5 · Create the schemas and the landing volume
# MAGIC
# MAGIC | schema | holds |
# MAGIC |---|---|
# MAGIC | `landing` | the volume `raw_files` with the CSV extracts |
# MAGIC | `bronze` | raw rows, all columns as text (`bronze.<domain>_<table>`) |
# MAGIC | `silver` | typed, cleaned, de-duplicated rows (`silver.<domain>_<table>`) - not governed, not for consumers |
# MAGIC | `retail`, `mobility`, `telecom` | **gold** - one star schema per domain plus its metric views |
# MAGIC | `governance` | row-filter / column-mask functions and the access-mapping tables (notebook 03) |
# MAGIC | `context` | business terms and the domain map (notebooks 05a-c) |
# MAGIC
# MAGIC The gold schemas get a description of their domain as comment - Genie reads it.

# COMMAND ----------

SCHEMAS = {
    "landing": "Landing zone: volume raw_files holds the CSV extracts (one folder per table) read by the pipelines.",
    "bronze": "Bronze layer: raw rows exactly as delivered (all columns STRING) + lineage columns. Written by the ecom_*_pipeline pipelines.",
    "silver": "Silver layer: typed, cleaned and de-duplicated rows with data-quality expectations. Not governed - give consumers the gold schemas only.",
    "retail": "Retail and Commerce (Nordvik Retail): 5 stores and a webshop selling electronics, fashion and beauty. "
              "Subdomains Product Catalog, Stores & Channels, Customers, Sales & Returns. Gold star schema + metric views.",
    "mobility": "Mobility and Automotive (Nordvik Mobility): car dealers with workshops and a truck centre. "
                "Subdomains Vehicle Catalog, Dealer Network, Vehicle Sales, Aftersales Service. Gold star schema + metric views.",
    "telecom": "Telecommunications and Media (Nordvik Connect): mobile, fibre and TV / streaming operator. "
               "Subdomains Plans & Products, Customers & Subscriptions, Billing, Usage. Gold star schema + metric views.",
    "governance": "Governance: row-filter and column-mask functions plus the access-mapping tables that drive them.",
    "context": "Business context: business terms, definitions and the domain / subdomain map of Nordvik Group.",
}
for schema, comment in SCHEMAS.items():
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}` COMMENT {sql_str(comment)}")
    current = spark.sql(f"SELECT comment FROM `{catalog}`.information_schema.schemata WHERE schema_name = :s",
                        {"s": schema}).first()
    if current is None or current.comment != comment:                          # only when changed
        spark.sql(f"COMMENT ON SCHEMA `{catalog}`.`{schema}` IS {sql_str(comment)}")

spark.sql(f"""CREATE VOLUME IF NOT EXISTS `{catalog}`.`landing`.`raw_files`
COMMENT 'CSV extracts of the Nordvik Group source systems: <domain>/<table>/<file>.csv'""")
VOLUME_ROOT = f"/Volumes/{catalog}/landing/raw_files"
display(spark.sql(f"SHOW SCHEMAS IN `{catalog}`"))
print(f"✅ Volume ready: {VOLUME_ROOT}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Copy the CSV files into the volume
# MAGIC
# MAGIC Each table gets its **own folder** - `read_files` in the bronze layer watches one folder per table.
# MAGIC Files that are already in the volume are **skipped** - the data is loaded once.
# MAGIC
# MAGIC > ℹ️ The bronze streaming tables ingest each file **once**. `overwrite = true` is only for repairing a damaged
# MAGIC > volume file *before* the first pipeline run - a file replaced after the pipeline has run is not read again.

# COMMAND ----------

jobs, missing = [], []
for d in DOMAINS:
    for table in manifest[d]:
        name = f"{DATE}-{table}.csv"
        src = f"{DATA_DIR}/{d}/{name}"
        if not os.path.isfile(src):
            missing.append(src)
            continue
        jobs.append((d, table, src, f"{VOLUME_ROOT}/{d}/{table}", f"{VOLUME_ROOT}/{d}/{table}/{name}"))
if missing:
    raise FileNotFoundError(f"{len(missing)} CSV file(s) missing in the Git folder, e.g. {missing[:3]}")

results = []
t0 = time.time()
for d, table, src, dst_dir, dst in jobs:
    size = os.path.getsize(src)
    if os.path.exists(dst) and not overwrite:
        same = os.path.getsize(dst) == size
        results.append((d, table, "skipped (already there)" if same else "DIFFERENT - set overwrite=true", size))
        continue
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copyfile(src, dst)
    results.append((d, table, "copied", size))
copied = sum(1 for r in results if r[2] == "copied")
skipped = sum(1 for r in results if r[2].startswith("skipped"))
different = [r for r in results if r[2].startswith("DIFFERENT")]
print(f"{len(results)} files: {copied} copied, {skipped} already present, {len(different)} different "
      f"in {time.time() - t0:.1f}s")
if different:
    print("⚠️ These volume files differ from the Git folder (kept as they are):", [f"{r[0]}.{r[1]}" for r in different])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Verify the landed files ("prepare source data")
# MAGIC
# MAGIC Every table must have exactly one non-empty CSV in its folder, identical in size to the Git folder copy,
# MAGIC with the header and the number of rows that `data/2026-10-27-manifest.json` records. `clean_rows` is how many
# MAGIC rows remain after the silver layer has repaired the deliberate data-quality issues (see `data/README.md`).

# COMMAND ----------

problems, summary = [], []
for d, table, src, dst_dir, dst in jobs:
    meta = manifest[d][table]
    files = [f for f in os.listdir(dst_dir) if not f.startswith(".")] if os.path.isdir(dst_dir) else []
    with open(dst, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    header_ok = lines[0].split(",") == meta["columns"] if lines else False
    rows = len(lines) - 1
    ok = (files == [os.path.basename(dst)] and os.path.getsize(dst) == os.path.getsize(src)
          and header_ok and rows == meta["rows"] and rows < 50)
    if not ok:
        problems.append(f"{d}.{table}: files={files}, rows={rows} (manifest {meta['rows']}), header ok={header_ok}")
    summary.append((d, table, rows, meta["clean_rows"], len(meta["dq_issues"]), "OK" if ok else "PROBLEM"))

display(spark.createDataFrame(summary, "domain string, table string, csv_rows long, rows_after_cleaning long, "
                                       "dq_issues long, status string").orderBy("domain", "table"))
if problems:
    raise RuntimeError(f"{len(problems)} table folder(s) are not as expected: {problems[:5]}")
print(f"✅ {len(summary)} CSV files verified in {VOLUME_ROOT}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8 · Tag the catalog, schemas, volume and notebooks
# MAGIC
# MAGIC The wanted tags come from `config/2026-10-27-tags.json`; only missing or different values are applied, e.g.
# MAGIC
# MAGIC ```sql
# MAGIC ALTER SCHEMA <catalog>.retail SET TAGS ('ecom_project' = 'ecom_bootcamp', 'ecom_domain' = 'retail_commerce', 'ecom_layer' = 'gold')
# MAGIC ```
# MAGIC
# MAGIC Tables, columns and metric views are tagged by job task `tags` once the pipelines have built them. The CSV
# MAGIC files inside the volume are not Unity Catalog objects and cannot carry tags - the volume carries them.
# MAGIC The ecom **notebooks** get `ecom_project` through the workspace tag-assignment API (skipped with a note
# MAGIC if the API is not available).

# COMMAND ----------


def ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def pairs(tags: dict) -> str:
    return ", ".join(f"{sql_str(k)} = {sql_str(v)}" for k, v in sorted(tags.items()))


have_catalog = {r.tag_name: r.tag_value for r in spark.sql(
    f"SELECT tag_name, tag_value FROM `{catalog}`.information_schema.catalog_tags WHERE catalog_name = :c",
    {"c": catalog}).collect()}
have_schema, have_volume = {}, {}
for r in spark.sql(f"SELECT schema_name, tag_name, tag_value FROM `{catalog}`.information_schema.schema_tags").collect():
    have_schema.setdefault(r.schema_name, {})[r.tag_name] = r.tag_value
for r in spark.sql(f"SELECT schema_name, volume_name, tag_name, tag_value "
                   f"FROM `{catalog}`.information_schema.volume_tags").collect():
    have_volume.setdefault(f"{r.schema_name}.{r.volume_name}", {})[r.tag_name] = r.tag_value

statements = []
diff = {k: v for k, v in tag_config["catalog"].items() if have_catalog.get(k) != v}
if diff:
    statements.append(f"ALTER CATALOG {ident(catalog)} SET TAGS ({pairs(diff)})")
for schema, tags in tag_config["schemas"].items():
    diff = {k: v for k, v in tags.items() if have_schema.get(schema, {}).get(k) != v}
    if diff:
        statements.append(f"ALTER SCHEMA {ident(catalog)}.{ident(schema)} SET TAGS ({pairs(diff)})")
for volume, tags in tag_config["volumes"].items():
    diff = {k: v for k, v in tags.items() if have_volume.get(volume, {}).get(k) != v}
    if diff:
        schema, name = volume.split(".")
        statements.append(f"ALTER VOLUME {ident(catalog)}.{ident(schema)}.{ident(name)} SET TAGS ({pairs(diff)})")
for stmt in statements:
    spark.sql(stmt)
print(f"✅ Unity Catalog tags: {len(statements)} statement(s) applied "
      f"({1 + len(tag_config['schemas']) + len(tag_config['volumes'])} objects in config).")

# Notebooks: workspace tag assignments (best effort - never fails the setup).
nb_tagged, nb_note = 0, None
try:
    nb_dir = f"{BUNDLE_ROOT}/notebooks".replace("/Workspace", "", 1)
    pending = [nb_dir]
    while pending:
        folder = pending.pop()
        for obj in w.api_client.do("GET", "/api/2.0/workspace/list", query={"path": folder}).get("objects", []):
            if obj["object_type"] == "DIRECTORY":
                pending.append(obj["path"])
            elif obj["object_type"] == "NOTEBOOK":
                entity_id = str(obj["object_id"])
                have = {t.get("tag_key"): t.get("tag_value") for t in w.api_client.do(
                    "GET", f"/api/2.0/entity-tag-assignments/notebooks/{entity_id}/tags").get("tag_assignments", [])}
                if have.get("ecom_project") != "ecom_bootcamp":
                    w.api_client.do("POST", "/api/2.0/entity-tag-assignments", body={
                        "entity_type": "notebooks", "entity_id": entity_id,
                        "tag_key": "ecom_project", "tag_value": "ecom_bootcamp"})
                nb_tagged += 1
except Exception as e:
    nb_note = str(e)[:200]
print(f"Notebook tags: {nb_tagged} notebook(s) carry ecom_project" + (f" (stopped: {nb_note})" if nb_note else ""))

display(spark.sql(f"""
    SELECT 'catalog' AS object_type, catalog_name AS object, tag_name, tag_value FROM `{catalog}`.information_schema.catalog_tags
    WHERE tag_name LIKE 'ecom\\_%'
    UNION ALL
    SELECT 'schema', schema_name, tag_name, tag_value FROM `{catalog}`.information_schema.schema_tags WHERE tag_name LIKE 'ecom\\_%'
    UNION ALL
    SELECT 'volume', concat(schema_name, '.', volume_name), tag_name, tag_value FROM `{catalog}`.information_schema.volume_tags
    WHERE tag_name LIKE 'ecom\\_%'
    ORDER BY ALL"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9 · Next step: deploy and run the bundle
# MAGIC
# MAGIC The three pipelines (bronze → silver → gold) and the job that builds the metric views, applies the tags and
# MAGIC validates the result are defined as code in **`ecom/databricks.yml`** (a *Declarative Automation Bundle*).
# MAGIC
# MAGIC 1. In the workspace file browser open the Git folder → `ecom` and click **`databricks.yml`**.
# MAGIC 2. Click the **Deployments** icon (🚀 rocket) in the left pane of the editor.
# MAGIC 3. Select target **`dev`** → **Deploy**.
# MAGIC 4. Under *Bundle resources* find the job **`ecom_job`** → click **Run** (▶).
# MAGIC 5. The three pipeline tasks run in parallel, then `metric_views` → `tags` → `validate` should all turn green.
# MAGIC
# MAGIC The bundle's default catalog is `ecom_<your short user name>` - the same as this notebook's default.
# MAGIC If you typed a **different catalog** above, change `variables.catalog.default` in `databricks.yml`
# MAGIC (or deploy with the CLI from the `ecom` folder: `databricks bundle deploy -t dev --var catalog=<name>`).

# COMMAND ----------

print(f"""
✅ Setup complete for catalog `{catalog}` ({len(DOMAINS)} domains, {len(results)} source files).

NEXT: open ecom/databricks.yml in this Git folder -> Deployments (rocket icon) -> target 'dev'
      -> Deploy -> run the job 'ecom_job'.
""")
dbutils.notebook.exit(json.dumps({"catalog": catalog, "files": len(results), "copied": copied,
                                  "already_present": skipped, "different": len(different), "verified": len(summary),
                                  "tag_statements": len(statements), "notebooks_tagged": nb_tagged}))
