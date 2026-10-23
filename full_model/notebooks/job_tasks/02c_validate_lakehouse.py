# Databricks notebook source
# MAGIC %md
# MAGIC # 02c · Validate the lakehouse
# MAGIC
# MAGIC The last task of `cpg_lakehouse_job`. Before anyone builds a Genie Agent on top of the data, we check
# MAGIC that the foundation is sound:
# MAGIC
# MAGIC | # | check | fails the task when |
# MAGIC |---|---|---|
# MAGIC | 1 | every gold table of the 10 domains **exists** and has a **primary key** constraint | a table or its PK is missing |
# MAGIC | 1b | all model **foreign keys** are registered | fewer foreign keys than the model defines |
# MAGIC | 2 | every table has **rows**, and the row counts match `data/manifest.json` | a table is empty / a count differs |
# MAGIC | 3 | **primary keys are unique and not null** | duplicates / NULL keys found |
# MAGIC | 4 | every **metric view** in the domain schemas is **queryable** (one measure is evaluated) | a view errors |
# MAGIC | 5 | the model **tags** are present | fewer tags than the model defines |
# MAGIC | 6 | *(information only)* what silver's **data-quality expectations** caught, from the pipeline event log | - |
# MAGIC
# MAGIC **Expected result:** `✅ Lakehouse validated` at the end. Otherwise the task fails with a list of problems.
# MAGIC The notebook only reads - running it again changes nothing.
# MAGIC
# MAGIC **Governance-proof.** The job runs as *you*. Once lab step 3 has attached row filters, a gold table such as
# MAGIC `finance.ar_invoice` shows you only your company codes, so its `count(*)` no longer equals the manifest.
# MAGIC Row counts and key checks therefore read the **ungoverned silver** table behind each gold table
# MAGIC (`silver.<domain>_<table>`, which gold copies 1:1). Gold is still counted: a gold table *without* a row
# MAGIC filter must equal its silver table; for a gold table *with* a row filter the visible rows are shown as
# MAGIC information only.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters and helpers

# COMMAND ----------

import json
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

dbutils.widgets.text("catalog", "", "Catalog (blank = automatic)")

DOMAINS = ["consumer", "distribution", "finance", "manufacturing", "procurement",
           "product", "promotion", "quality", "sales", "supply"]      # all 10 domains = gold schemas


def bundle_short_name(user_name: str) -> str:
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


def bundle_root() -> str:
    """The folder that holds databricks.yml (this notebook lives somewhere below it)."""
    try:
        nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        d = os.path.dirname(nb_path if nb_path.startswith("/Workspace") else "/Workspace" + nb_path)
    except Exception:
        d = os.getcwd()
    while d not in ("", "/"):
        if os.path.isfile(f"{d}/databricks.yml"):
            return d
        d = os.path.dirname(d)
    raise FileNotFoundError("databricks.yml not found above this notebook - run it from the full_model folder.")


def sql_str(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


user_name = spark.sql("SELECT current_user()").first()[0]
catalog = dbutils.widgets.get("catalog").strip() or f"cpg_full_{bundle_short_name(user_name)}"
domains = DOMAINS
BUNDLE_ROOT = bundle_root()
in_list = ", ".join(sql_str(d) for d in domains)
problems = []   # every failed check adds a line here; the task fails at the end if not empty
print(f"Catalog: {catalog} | domains: {', '.join(domains)}")

expected_tables, expected_tags, expected_fks = [], 0, 0
for d in domains:
    with open(f"{BUNDLE_ROOT}/src/model_tags/{d}.json", encoding="utf-8") as fh:
        doc = json.load(fh)
    expected_tables += [(d, t) for t in doc["tables"]]
    expected_tags += doc["tag_count"]
    expected_fks += doc.get("foreign_key_count", 0)   # FOREIGN KEYs the generated gold DDL declares
print(f"Expected gold tables: {len(expected_tables)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Gold tables exist and have a primary key
# MAGIC
# MAGIC `information_schema` also lists pipeline-internal helper tables (`__materialization_mat_*`,
# MAGIC `event_log_*`) - they are filtered out.

# COMMAND ----------

tables = spark.sql(f"""
    SELECT table_schema, table_name, table_type
    FROM `{catalog}`.information_schema.tables
    WHERE table_schema IN ({in_list})
      AND table_name NOT LIKE '\\_\\_%' AND table_name NOT LIKE 'event\\_log%'""").collect()
existing = {(r.table_schema, r.table_name): r.table_type for r in tables}

pk_rows = spark.sql(f"""
    SELECT tc.table_schema, tc.table_name, kcu.column_name
    FROM `{catalog}`.information_schema.table_constraints tc
    JOIN `{catalog}`.information_schema.key_column_usage kcu
      ON kcu.constraint_catalog = tc.constraint_catalog AND kcu.constraint_schema = tc.constraint_schema
     AND kcu.constraint_name = tc.constraint_name
    WHERE tc.table_schema IN ({in_list}) AND tc.constraint_type = 'PRIMARY KEY'""").collect()
pk = {(r.table_schema, r.table_name): r.column_name for r in pk_rows}
fk_count = {(r.table_schema, r.table_name): r.n for r in spark.sql(f"""
    SELECT table_schema, table_name, count(*) AS n FROM `{catalog}`.information_schema.table_constraints
    WHERE table_schema IN ({in_list}) AND constraint_type = 'FOREIGN KEY' GROUP BY ALL""").collect()}

missing = [f"{d}.{t}" for d, t in expected_tables if (d, t) not in existing]
no_pk = [f"{d}.{t}" for d, t in expected_tables if (d, t) in existing and (d, t) not in pk]
if missing:
    problems.append(f"{len(missing)} gold table(s) missing: {', '.join(missing[:10])}")
if no_pk:
    problems.append(f"{len(no_pk)} gold table(s) without PRIMARY KEY: {', '.join(no_pk[:10])}")
n_fks = sum(fk_count.values())
if n_fks < expected_fks:
    problems.append(f"only {n_fks} of {expected_fks} foreign keys registered - run the job again: on the first run the "
                    f"pipeline registers the keys in its automatic retry (Genie derives its joins from these keys)")
print(f"Gold tables found: {sum(1 for x in expected_tables if x in existing)}/{len(expected_tables)} | "
      f"with primary key: {sum(1 for x in expected_tables if x in pk)} | foreign keys: {n_fks} (model: {expected_fks})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Row counts and primary-key uniqueness
# MAGIC
# MAGIC One query per table on the **silver** table behind it: `count(*)` must be > 0, and `count(DISTINCT pk)`
# MAGIC must equal `count(*)` (no duplicates, no NULL keys - silver de-duplicated and dropped empty keys).
# MAGIC Silver is not governed, so the result is the same for every user. A second query counts the **gold** rows
# MAGIC you can see: without a row filter they must equal silver (gold is a 1:1 copy); with a row filter (lab step 3)
# MAGIC they are shown for information.

# COMMAND ----------

row_filtered = {(r.table_schema, r.table_name) for r in spark.sql(f"""
    SELECT table_schema, table_name FROM `{catalog}`.information_schema.row_filters
    WHERE table_schema IN ({in_list})""").collect()}


def profile(key):
    d, t = key
    col = pk[key]
    r = spark.sql(f"SELECT count(*) AS n, count(DISTINCT `{col}`) AS k, count_if(`{col}` IS NULL) AS z "
                  f"FROM `{catalog}`.silver.`{d}_{t}`").first()
    g = spark.sql(f"SELECT count(*) FROM `{catalog}`.`{d}`.`{t}`").first()[0]
    return (d, t, col, r.n, r.k, r.z, g, key in row_filtered, fk_count.get(key, 0))


t0 = time.time()
with ThreadPoolExecutor(max_workers=16) as pool:
    stats = list(pool.map(profile, [x for x in expected_tables if x in pk]))
stats.sort()
display(spark.createDataFrame(stats, "schema string, table string, primary_key string, silver_rows long, "
                                     "distinct_keys long, null_keys long, gold_rows_visible_to_you long, "
                                     "row_filter boolean, foreign_keys long"))
empty = [f"{d}.{t}" for d, t, c, n, k, z, g, rf, f in stats if n == 0]
dupes = [f"{d}.{t} ({n - k} dup)" for d, t, c, n, k, z, g, rf, f in stats if n != k or z > 0]
stale = [f"{d}.{t} (silver {n}, gold {g})" for d, t, c, n, k, z, g, rf, f in stats if not rf and g != n]
if empty:
    problems.append(f"{len(empty)} empty table(s): {', '.join(empty[:10])}")
if dupes:
    problems.append(f"{len(dupes)} table(s) with duplicate/NULL keys: {', '.join(dupes[:10])}")
if stale:
    problems.append(f"{len(stale)} gold table(s) differ from their silver table - run the job again: {', '.join(stale[:10])}")
governed = [f"{d}.{t}" for d, t, c, n, k, z, g, rf, f in stats if rf]
print(f"{len(stats)} tables profiled in {time.time() - t0:.1f}s, {sum(s[3] for s in stats):,} rows in total")
if governed:
    print(f"ℹ️ {len(governed)} gold table(s) carry a row filter (lab step 3) - you see only the rows of your company "
          f"codes there; their counts above come from silver: {', '.join(governed)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3b · Row counts match the data manifest
# MAGIC
# MAGIC `data/manifest.json` records for every table how many rows must remain after cleaning
# MAGIC (`clean_rows`: duplicates removed, empty keys and negative quantities dropped). The silver row count (= gold
# MAGIC for an admin, or before step 3) must match exactly - this proves that silver handled every injected
# MAGIC data-quality issue. Row filters cannot affect this check.

# COMMAND ----------

manifest_path = f"{BUNDLE_ROOT}/data/manifest.json"
manifest_result = "skipped (no data/manifest.json)"
if os.path.isfile(manifest_path):
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    expected_rows = {(d, t): meta.get("clean_rows") for d in domains for t, meta in manifest.get(d, {}).items()}
    compare = [(d, t, expected_rows.get((d, t)), n) for d, t, c, n, k, z, g, rf, f in stats]
    mismatch = [f"{d}.{t} (expected {e}, got {n})" for d, t, e, n in compare if e is not None and e != n]
    display(spark.createDataFrame(compare, "schema string, table string, expected_rows long, silver_rows long"))
    if mismatch:
        problems.append(f"{len(mismatch)} table(s) differ from data/manifest.json: {', '.join(mismatch[:10])}")
    manifest_result = f"{len(compare) - len(mismatch)}/{len(compare)} tables match"
    print(f"Row counts vs manifest: {manifest_result}")
else:
    print("ℹ️ data/manifest.json not found in the full_model folder - comparison skipped.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Every metric view answers a query
# MAGIC
# MAGIC For each metric view in the domain schemas the first measure is evaluated
# MAGIC (`SELECT MEASURE(<measure>) FROM <view>`). The industry views listed in
# MAGIC `src/metric_views/industry/` must all exist.

# COMMAND ----------

expected_mv = set()
for d in domains:
    with open(f"{BUNDLE_ROOT}/src/metric_views/industry/{d}.sql", encoding="utf-8") as fh:
        for m in re.finditer(r"CREATE OR REPLACE VIEW \$\{catalog\}\.(\w+)\.`?(\w+)`?", fh.read()):
            expected_mv.add((m.group(1), m.group(2)))
metric_views = sorted(k for k, v in existing.items() if v == "METRIC_VIEW")
missing_mv = sorted(f"{d}.{v}" for d, v in expected_mv - set(metric_views))
if missing_mv:
    problems.append(f"{len(missing_mv)} industry metric view(s) missing: {', '.join(missing_mv[:10])}")


def probe_metric_view(key):
    d, v = key
    fqn = f"`{catalog}`.`{d}`.`{v}`"
    try:
        desc = json.loads(spark.sql(f"DESCRIBE TABLE EXTENDED {fqn} AS JSON").first()[0])
        measures = [c["name"] for c in desc["columns"] if c.get("is_measure")]
        if not measures:
            return (d, v, None, None, "no measure defined")
        value = spark.sql(f"SELECT MEASURE(`{measures[0]}`) AS m FROM {fqn}").first()[0]
        return (d, v, measures[0], None if value is None else str(value), "OK")
    except Exception as e:
        return (d, v, None, None, "ERROR: " + str(e)[:400])


t0 = time.time()
with ThreadPoolExecutor(max_workers=8) as pool:
    mv_results = list(pool.map(probe_metric_view, metric_views))
display(spark.createDataFrame(mv_results, "schema string, metric_view string, measure string, value string, status string"))
bad_mv = [f"{d}.{v}: {s}" for d, v, m, val, s in mv_results if s != "OK"]
if bad_mv:
    problems.append(f"{len(bad_mv)} metric view(s) not queryable: " + " | ".join(bad_mv[:5]))
print(f"{len(metric_views)} metric views queried in {time.time() - t0:.1f}s "
      f"({len(expected_mv)} industry views expected)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Model tags present

# COMMAND ----------

n_tags = spark.sql(f"""
    SELECT (SELECT count(*) FROM `{catalog}`.information_schema.schema_tags WHERE schema_name IN ({in_list}))
         + (SELECT count(*) FROM `{catalog}`.information_schema.table_tags  WHERE schema_name IN ({in_list}))
         + (SELECT count(*) FROM `{catalog}`.information_schema.column_tags WHERE schema_name IN ({in_list}))""").first()[0]
print(f"Tags in the domain schemas: {n_tags:,} (model defines {expected_tags:,})")
if n_tags < expected_tags:
    problems.append(f"only {n_tags} of {expected_tags} model tags present - rerun task model_tags")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · What did silver clean up? (information only)
# MAGIC
# MAGIC The pipeline's event log records, per dataset and expectation, how many rows passed and failed in the
# MAGIC latest pipeline update. `*_not_null` (empty primary keys) and `quantity_ordered_not_negative` **drop** rows;
# MAGIC the other `*_not_negative` expectations only **warn**.

# COMMAND ----------

first = expected_tables[0]
try:
    dq = spark.sql(f"""
        WITH ev AS (
          SELECT origin.update_id, timestamp, details:flow_progress.data_quality.expectations AS e
          FROM event_log(TABLE(`{catalog}`.silver.`{first[0]}_{first[1]}`))
          WHERE event_type = 'flow_progress' AND details:flow_progress.data_quality.expectations IS NOT NULL),
        latest AS (SELECT update_id FROM ev ORDER BY timestamp DESC LIMIT 1),
        x AS (SELECT explode(from_json(e, 'array<struct<name string, dataset string, passed_records long, failed_records long>>')) AS x
              FROM ev WHERE update_id = (SELECT update_id FROM latest))
        SELECT x.dataset, x.name AS expectation, sum(x.passed_records) AS passed, sum(x.failed_records) AS failed
        FROM x GROUP BY ALL HAVING sum(x.failed_records) > 0 ORDER BY dataset, expectation""")
    display(dq)
except Exception as e:
    print("Event log not readable here (information only):", str(e)[:300])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Verdict

# COMMAND ----------

if problems:
    print("❌ Lakehouse validation FAILED:")
    for p in problems:
        print("  -", p)
    raise RuntimeError("Lakehouse validation failed: " + " || ".join(problems))
print(f"✅ Lakehouse validated: {len(stats)} gold tables ({sum(s[3] for s in stats):,} rows), {n_fks} foreign keys, "
      f"{len(metric_views)} metric views, {n_tags:,} tags in catalog `{catalog}`.")
dbutils.notebook.exit(json.dumps({
    "catalog": catalog, "gold_tables": len(stats), "rows": sum(s[3] for s in stats),
    "foreign_keys": n_fks, "expected_foreign_keys": expected_fks, "metric_views": len(metric_views), "tags": n_tags,
    "manifest_check": manifest_result, "row_filtered_gold_tables": governed,
    "row_counts": {f"{s[0]}.{s[1]}": s[3] for s in stats}}))
