# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 02b · Apply the ecom tags to tables, columns and metric views
# MAGIC
# MAGIC Every gold table, metric view and sensitive column of the three domains carries **plain Unity Catalog
# MAGIC tags** with the prefix `ecom_`:
# MAGIC
# MAGIC | level | tags | example |
# MAGIC |---|---|---|
# MAGIC | table / metric view | `ecom_project`, `ecom_domain`, `ecom_subdomain`, `ecom_layer`, `ecom_table_type` | `retail.fact_sales`: retail_commerce / sales_returns / gold / fact |
# MAGIC | column | `ecom_pii` (name, email, phone), `ecom_classification` (confidential) | `retail.dim_customer.email`: email / confidential |
# MAGIC
# MAGIC Tags make the data **discoverable** (search, Catalog Explorer), document **which domain owns what**, and
# MAGIC drive **governance** (find every PII column with `information_schema.column_tags`).
# MAGIC
# MAGIC This notebook runs as task **`tags`** of `ecom_job`, after `metric_views`. It
# MAGIC
# MAGIC 1. reads the wanted tags from `config/2026-10-27-tags.json` (the single source for all ecom tags),
# MAGIC 2. reads the tags that already exist (`information_schema.table_tags` / `column_tags`),
# MAGIC 3. applies **only what is missing or different** - one `SET TAGS` statement per object, with the keyword
# MAGIC    the object type needs (`ALTER MATERIALIZED VIEW` for gold tables, `ALTER VIEW` for metric views).
# MAGIC
# MAGIC 🔁 A re-run only checks. Catalog, schemas and volume are tagged by notebook 01; job and pipelines carry
# MAGIC their tags in `resources/*.yml`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters and helpers

# COMMAND ----------

import json
import os
import time
import unicodedata

dbutils.widgets.text("catalog", "", "Catalog (blank = automatic)")

DOMAINS = ["retail", "mobility", "telecom"]   # the three domains = gold schemas
KEYWORD = {"MATERIALIZED_VIEW": "MATERIALIZED VIEW", "STREAMING_TABLE": "STREAMING TABLE",
           "METRIC_VIEW": "VIEW", "VIEW": "VIEW"}   # anything else: TABLE


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
    raise FileNotFoundError("databricks.yml not found above this notebook - run it from the ecom folder.")


def sql_str(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


user_name = spark.sql("SELECT current_user()").first()[0]
catalog = dbutils.widgets.get("catalog").strip() or f"ecom_{bundle_short_name(user_name)}"
BUNDLE_ROOT = bundle_root()
in_list = ", ".join(sql_str(d) for d in DOMAINS)
print(f"Catalog: {catalog} | domains: {', '.join(DOMAINS)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Wanted tags (config) vs. existing tags (Unity Catalog)
# MAGIC
# MAGIC The config must list every gold table and metric view the domains have - an object that exists but has no
# MAGIC entry (or an entry without an object) fails the task, so new tables never go untagged unnoticed.

# COMMAND ----------

t_start = time.time()
with open(f"{BUNDLE_ROOT}/config/2026-10-27-tags.json", encoding="utf-8") as fh:
    config = json.load(fh)["tables"]

types = {f"{r.table_schema}.{r.table_name}": r.table_type for r in spark.sql(f"""
    SELECT table_schema, table_name, table_type FROM `{catalog}`.information_schema.tables
    WHERE table_schema IN ({in_list})
      AND table_name NOT LIKE '\\_\\_%' AND table_name NOT LIKE 'event\\_log%'""").collect()}
missing = sorted(set(config) - set(types))
unlisted = sorted(set(types) - set(config))
if missing:
    raise RuntimeError(f"{len(missing)} object(s) of config/2026-10-27-tags.json do not exist - did the pipelines and "
                       f"task metric_views run? {missing}")
if unlisted:
    raise RuntimeError(f"{len(unlisted)} object(s) in the domain schemas are missing in config/2026-10-27-tags.json: {unlisted}")

wanted = {}  # (schema.table, column|None) -> {tag: value}
for table, entry in config.items():
    wanted[(table, None)] = entry["tags"]
    for column, tags in entry["columns"].items():
        wanted[(table, column)] = tags

existing = {}
for r in spark.sql(f"SELECT schema_name, table_name, tag_name, tag_value FROM `{catalog}`.information_schema.table_tags "
                   f"WHERE schema_name IN ({in_list})").collect():
    existing.setdefault((f"{r.schema_name}.{r.table_name}", None), {})[r.tag_name] = r.tag_value
for r in spark.sql(f"SELECT schema_name, table_name, column_name, tag_name, tag_value "
                   f"FROM `{catalog}`.information_schema.column_tags WHERE schema_name IN ({in_list})").collect():
    existing.setdefault((f"{r.schema_name}.{r.table_name}", r.column_name), {})[r.tag_name] = r.tag_value

todo = {}
for obj, tags in wanted.items():
    diff = {k: v for k, v in tags.items() if existing.get(obj, {}).get(k) != v}
    if diff:
        todo[obj] = diff
n_wanted = sum(len(v) for v in wanted.values())
n_todo = sum(len(v) for v in todo.values())
print(f"Wanted tags: {n_wanted} on {len(wanted)} objects | already correct: {n_wanted - n_todo} | "
      f"to apply: {n_todo} on {len(todo)} objects")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Apply the missing tags
# MAGIC
# MAGIC ```sql
# MAGIC ALTER MATERIALIZED VIEW <catalog>.retail.dim_customer ALTER COLUMN email
# MAGIC   SET TAGS ('ecom_classification' = 'confidential', 'ecom_pii' = 'email')
# MAGIC ALTER VIEW <catalog>.retail.sales_metrics SET TAGS ('ecom_domain' = 'retail_commerce', ...)
# MAGIC ```

# COMMAND ----------


def statement(obj, tags):
    table, column = obj
    schema, name = table.split(".")
    target = f"ALTER {KEYWORD.get(types[table], 'TABLE')} {ident(catalog)}.{ident(schema)}.{ident(name)}"
    pairs = ", ".join(f"{sql_str(k)} = {sql_str(v)}" for k, v in sorted(tags.items()))
    return f"{target} SET TAGS ({pairs})" if column is None else f"{target} ALTER COLUMN {ident(column)} SET TAGS ({pairs})"


results, failures = [], []
for obj, tags in sorted(todo.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
    stmt = statement(obj, tags)
    for attempt in range(3):
        try:
            spark.sql(stmt)
            results.append((obj[0], obj[1], types[obj[0]], len(tags), "applied", None))
            break
        except Exception as e:   # transient concurrency errors are retried
            if attempt == 2:
                failures.append(stmt)
                results.append((obj[0], obj[1], types[obj[0]], len(tags), "FAILED", str(e)[:400]))
            else:
                time.sleep(2 * (attempt + 1))
if results:
    display(spark.createDataFrame(results, "object string, column string, object_type string, tags long, "
                                           "status string, error string"))
print(f"Applied {n_todo - sum(r[3] for r in results if r[4] == 'FAILED')} tag values in "
      f"{time.time() - t_start:.1f}s; {len(failures)} statement(s) failed.")
if failures:
    raise RuntimeError(f"{len(failures)} SET TAGS statement(s) failed (see the table above)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Review the tags
# MAGIC
# MAGIC Every personal-data column of the three domains - the starting point for the governance notebook (03):

# COMMAND ----------

display(spark.sql(f"""
    SELECT schema_name, table_name, column_name, tag_name, tag_value
    FROM `{catalog}`.information_schema.column_tags
    WHERE schema_name IN ({in_list}) AND tag_name IN ('ecom_pii', 'ecom_classification')
    ORDER BY ALL"""))

# COMMAND ----------

# Which objects belong to which domain and subdomain:
display(spark.sql(f"""
    SELECT t.schema_name, t.table_name,
           max_by(t.tag_value, t.tag_name = 'ecom_subdomain') AS ecom_subdomain,
           max_by(t.tag_value, t.tag_name = 'ecom_table_type') AS ecom_table_type
    FROM `{catalog}`.information_schema.table_tags t
    WHERE t.schema_name IN ({in_list}) AND t.tag_name IN ('ecom_subdomain', 'ecom_table_type')
    GROUP BY ALL ORDER BY ALL"""))

# COMMAND ----------

# Result for the job run page (and for automated checks)
dbutils.notebook.exit(json.dumps({"catalog": catalog, "tags_wanted": n_wanted, "tags_already_correct": n_wanted - n_todo,
                                  "tags_applied": n_todo, "objects": len(config),
                                  "seconds": round(time.time() - t_start, 1)}))
