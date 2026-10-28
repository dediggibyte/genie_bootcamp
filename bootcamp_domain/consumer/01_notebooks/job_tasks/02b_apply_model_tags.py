# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 02b · Apply the industry model's tags
# MAGIC
# MAGIC The Lakehouse Industry Data Model ships **governance metadata as Unity Catalog tags**:
# MAGIC
# MAGIC | level | example tags |
# MAGIC |---|---|
# MAGIC | schema (domain) | `dbx_domain = consumer`, `dbx_division = business` |
# MAGIC | table | `dbx_data_type = master_data`, `dbx_subdomain = customer_identity` |
# MAGIC | column | `dbx_business_glossary_term = Primary Email Address`, `dbx_pii_email = true`, `dbx_restricted = true` |
# MAGIC
# MAGIC Tags make the data **discoverable** (search, Catalog Explorer), give **Genie business vocabulary** and
# MAGIC drive **governance** (e.g. find every PII column with `information_schema.column_tags`).
# MAGIC
# MAGIC This notebook runs as task **`model_tags`** of `cpg_consumer_job`. It is fast and idempotent:
# MAGIC
# MAGIC 1. reads the wanted tags from `02_model_tags/<domain>.json` (generated from the model) for the sample's gold
# MAGIC    schemas (`consumer` and `finance`),
# MAGIC 2. reads the tags that already exist (3 queries on `information_schema`),
# MAGIC 3. applies **only what is missing or different** - one `SET TAGS` statement per object with all its
# MAGIC    tag pairs, many tables in parallel.
# MAGIC
# MAGIC 🔁 **Only what is missing or changed** is applied, so a re-run of the job only checks.
# MAGIC
# MAGIC **Expected result:** the first run applies the model's 967 tags of this sample; a re-run only checks and
# MAGIC applies nothing. Tags survive pipeline refreshes.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters and helpers

# COMMAND ----------

import json
import os
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

dbutils.widgets.text("catalog", "", "Catalog (blank = automatic)")
dbutils.widgets.text("parallelism", "16", "Parallel threads")

SAMPLE = "consumer"
DOMAINS = ["consumer", "finance"]   # the sample's gold schemas (main domain first)


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
    raise FileNotFoundError("databricks.yml not found above this notebook - run it from the sample folder.")


def sql_str(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


user_name = spark.sql("SELECT current_user()").first()[0]
catalog = dbutils.widgets.get("catalog").strip() or f"cpg_{SAMPLE}_{bundle_short_name(user_name)}"
parallelism = int(dbutils.widgets.get("parallelism") or 16)
BUNDLE_ROOT = bundle_root()
print(f"Catalog: {catalog} | domains: {', '.join(DOMAINS)} | threads: {parallelism}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Wanted tags (from the model) vs. existing tags (from Unity Catalog)

# COMMAND ----------

t_start = time.time()
wanted = {}  # (schema, table|None, column|None) -> {tag: value}
for d in DOMAINS:
    with open(f"{BUNDLE_ROOT}/02_model_tags/{d}.json", encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc["schema_tags"]:
        wanted[(d, None, None)] = doc["schema_tags"]
    for table, t in doc["tables"].items():
        if t["table_tags"]:
            wanted[(d, table, None)] = t["table_tags"]
        for column, tags in t["column_tags"].items():
            wanted[(d, table, column)] = tags
n_wanted = sum(len(v) for v in wanted.values())

in_list = ", ".join(sql_str(d) for d in DOMAINS)
existing = {}
for row in spark.sql(f"SELECT schema_name, tag_name, tag_value FROM `{catalog}`.information_schema.schema_tags "
                     f"WHERE schema_name IN ({in_list})").collect():
    existing.setdefault((row.schema_name, None, None), {})[row.tag_name] = row.tag_value
for row in spark.sql(f"SELECT schema_name, table_name, tag_name, tag_value FROM `{catalog}`.information_schema.table_tags "
                     f"WHERE schema_name IN ({in_list})").collect():
    existing.setdefault((row.schema_name, row.table_name, None), {})[row.tag_name] = row.tag_value
for row in spark.sql(f"SELECT schema_name, table_name, column_name, tag_name, tag_value "
                     f"FROM `{catalog}`.information_schema.column_tags WHERE schema_name IN ({in_list})").collect():
    existing.setdefault((row.schema_name, row.table_name, row.column_name), {})[row.tag_name] = row.tag_value

# Only the tag pairs that are missing or have a different value.
todo = {}
for obj, tags in wanted.items():
    have = existing.get(obj, {})
    diff = {k: v for k, v in tags.items() if have.get(k) != v}
    if diff:
        todo[obj] = diff
n_todo = sum(len(v) for v in todo.values())
print(f"Wanted tags: {n_wanted:,} on {len(wanted):,} objects | already correct: {n_wanted - n_todo:,} | "
      f"to apply: {n_todo:,} on {len(todo):,} objects ({time.time() - t_start:.1f}s)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Apply the missing tags
# MAGIC
# MAGIC One statement per object carries all of its tag pairs, e.g.
# MAGIC
# MAGIC ```sql
# MAGIC ALTER TABLE <catalog>.consumer.shopper ALTER COLUMN primary_email
# MAGIC   SET TAGS ('dbx_business_glossary_term' = 'Primary Email Address', 'dbx_pii_email' = 'true', ...)
# MAGIC ```
# MAGIC
# MAGIC Statements of the same table run one after the other; different tables run in parallel threads.
# MAGIC (`ALTER TABLE ... SET TAGS` works on the pipeline's materialized views.)

# COMMAND ----------


def statement(obj, tags):
    schema, table, column = obj
    pairs = ", ".join(f"{sql_str(k)} = {sql_str(v)}" for k, v in sorted(tags.items()))
    if table is None:
        return f"ALTER SCHEMA {ident(catalog)}.{ident(schema)} SET TAGS ({pairs})"
    target = f"{ident(catalog)}.{ident(schema)}.{ident(table)}"
    if column is None:
        return f"ALTER TABLE {target} SET TAGS ({pairs})"
    return f"ALTER TABLE {target} ALTER COLUMN {ident(column)} SET TAGS ({pairs})"


groups = {}  # one group per table (schema-level statements form their own group)
for obj, tags in todo.items():
    groups.setdefault((obj[0], obj[1]), []).append(statement(obj, tags))


def run_group(key, stmts):
    errors = []
    for stmt in stmts:
        for attempt in range(4):
            try:
                spark.sql(stmt)
                break
            except Exception as e:   # transient concurrency errors are retried
                if attempt == 3:
                    errors.append((stmt[:200], str(e)[:500]))
                else:
                    time.sleep(2 * (attempt + 1))
    return key, len(stmts), errors


t0 = time.time()
failures = []
done_statements = 0
if groups:
    # biggest tables first, so the long ones do not end up last
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    with ThreadPoolExecutor(max_workers=parallelism) as pool:
        futures = [pool.submit(run_group, k, v) for k, v in ordered]
        for f in as_completed(futures):
            key, n, errors = f.result()
            done_statements += n
            failures.extend(errors)
elapsed = time.time() - t0
total_seconds = time.time() - t_start
print(f"Applied {n_todo:,} tag values with {done_statements:,} statements on {len(groups)} tables/schemas "
      f"in {elapsed:.1f}s ({parallelism} threads). Total runtime {time.time() - t_start:.1f}s.")
if failures:
    for stmt, err in failures[:10]:
        print("FAILED:", stmt, "\n   ", err)
    raise RuntimeError(f"{len(failures)} SET TAGS statement(s) failed (first errors printed above)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Look at the result
# MAGIC
# MAGIC Example: every column the model classifies as personal data (PII) - the starting point for the
# MAGIC governance notebook.

# COMMAND ----------

display(spark.sql(f"""
    SELECT schema_name, table_name, column_name, tag_name
    FROM `{catalog}`.information_schema.column_tags
    WHERE schema_name IN ({in_list}) AND tag_name LIKE 'dbx_pii%'
    ORDER BY ALL"""))

# COMMAND ----------

# Result for the job run page (and for automated checks)
dbutils.notebook.exit(json.dumps({
    "catalog": catalog, "tags_wanted": n_wanted, "tags_already_correct": n_wanted - n_todo,
    "tags_applied": n_todo, "statements": done_statements, "threads": parallelism,
    "apply_seconds": round(elapsed, 1), "total_seconds": round(total_seconds, 1)}))
