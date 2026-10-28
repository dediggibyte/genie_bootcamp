# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 02a · Create the metric views (semantic layer)
# MAGIC
# MAGIC A **metric view** defines business measures (e.g. *net revenue*, *EV share*, *ARPU*) and the dimensions
# MAGIC you may slice them by - **once**, in YAML, governed by Unity Catalog. Genie, dashboards and SQL users then
# MAGIC all get the same numbers.
# MAGIC
# MAGIC This notebook runs as task **`metric_views`** of the job `ecom_job`, after the three pipelines. It creates
# MAGIC the six views of `metric_views/2026-10-27-<domain>-metrics.sql`:
# MAGIC
# MAGIC | domain | metric views |
# MAGIC |---|---|
# MAGIC | Retail and Commerce | `retail.sales_metrics`, `retail.return_metrics` |
# MAGIC | Mobility and Automotive | `mobility.vehicle_sales_metrics`, `mobility.service_metrics` |
# MAGIC | Telecommunications and Media | `telecom.billing_metrics`, `telecom.usage_metrics` |
# MAGIC
# MAGIC Metric views cannot be defined inside a Lakeflow pipeline, which is why they are a separate job task.
# MAGIC
# MAGIC 🔁 **Only what is missing or changed:** a view that already exists with the same definition is left
# MAGIC alone (`unchanged`); only new views are created and changed ones replaced.
# MAGIC
# MAGIC **Expected result:** a table listing every metric view with status `created`, `replaced` or
# MAGIC `unchanged`; the task fails if any view could not be created.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters and helpers

# COMMAND ----------

import glob
import json
import os
import re
import time
import unicodedata

dbutils.widgets.text("catalog", "", "Catalog (blank = automatic)")

DOMAINS = ["retail", "mobility", "telecom"]   # the three domains = gold schemas


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


def split_sql_statements(text: str) -> list:
    """Split a SQL file on ';' that are outside quotes, back-quotes, $$...$$ blocks and -- comments.
    Comment lines are dropped."""
    stmts, buf, i, n, state = [], [], 0, len(text), None
    while i < n:
        ch, two = text[i], text[i:i + 2]
        if state is None:
            if two == "--":
                state = "--"; i += 2; continue
            if two == "$$":
                state = "$$"; buf.append(two); i += 2; continue
            if ch in ("'", '"', "`"):
                state = ch
            elif ch == ";":
                if "".join(buf).strip():
                    stmts.append("".join(buf).strip())
                buf = []; i += 1; continue
            buf.append(ch); i += 1; continue
        if state == "--":
            if ch == "\n":
                state = None; buf.append(ch)
            i += 1; continue
        if state == "$$":
            if two == "$$":
                state = None; buf.append(two); i += 2; continue
            buf.append(ch); i += 1; continue
        if ch == "\\" and state != "`" and i + 1 < n:
            buf.append(text[i:i + 2]); i += 2; continue
        if ch == state:
            state = None
        buf.append(ch); i += 1
    if "".join(buf).strip():
        stmts.append("".join(buf).strip())
    return stmts


user_name = spark.sql("SELECT current_user()").first()[0]
catalog = dbutils.widgets.get("catalog").strip() or f"ecom_{bundle_short_name(user_name)}"
BUNDLE_ROOT = bundle_root()
print(f"Catalog: {catalog} | domains: {', '.join(DOMAINS)}")
print(f"ecom folder: {BUNDLE_ROOT}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Collect the metric view definitions
# MAGIC
# MAGIC The SQL files use the placeholder `${catalog}`; it is replaced with your catalog name here.

# COMMAND ----------

NAME_RE = re.compile(r"CREATE\s+OR\s+REPLACE\s+VIEW\s+([^\s(]+)", re.I)
definitions = []  # (file, view name, sql)
for path in sorted(glob.glob(f"{BUNDLE_ROOT}/metric_views/*.sql")):
    with open(path, encoding="utf-8") as fh:
        for stmt in split_sql_statements(fh.read()):
            sql = stmt.replace("${catalog}", catalog)
            m = NAME_RE.search(sql)
            definitions.append((os.path.relpath(path, BUNDLE_ROOT), m.group(1) if m else sql[:60], sql))
print(f"{len(definitions)} metric view statements in {len(glob.glob(f'{BUNDLE_ROOT}/metric_views/*.sql'))} files")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Which views are missing or changed?
# MAGIC
# MAGIC Unity Catalog stores a metric view's YAML (`DESCRIBE TABLE EXTENDED ... AS JSON` → `view_text`), in its
# MAGIC own formatting. Both YAML texts are parsed and compared as data, so formatting differences do not count
# MAGIC as a change.

# COMMAND ----------

try:
    import yaml
except ImportError:          # without PyYAML every existing view is simply replaced (still correct)
    yaml = None


def desired_yaml(sql: str):
    m = re.search(r"\$\$(.*)\$\$", sql, re.S)
    return yaml.safe_load(m.group(1)) if (m and yaml) else None


existing = {f"{catalog}.{r.table_schema}.{r.table_name}" for r in spark.sql(f"""
    SELECT table_schema, table_name FROM `{catalog}`.information_schema.tables
    WHERE table_type = 'METRIC_VIEW' AND table_schema IN ({", ".join(repr(d) for d in DOMAINS)})""").collect()}


def current_yaml(fqn: str):
    try:
        cat, sch, name = fqn.split(".")
        desc = json.loads(spark.sql(f"DESCRIBE TABLE EXTENDED `{cat}`.`{sch}`.`{name}` AS JSON").first()[0])
        return yaml.safe_load(desc.get("view_text") or "") if yaml else None
    except Exception:
        return None


def plan(defn):
    file, name, sql = defn
    fqn = name.replace("`", "")
    if fqn not in existing:
        return "create"
    want = desired_yaml(sql)
    return "unchanged" if (want is not None and want == current_yaml(fqn)) else "replace"


actions = [plan(x) for x in definitions]
print({a: actions.count(a) for a in sorted(set(actions))})

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Create or replace what is missing or changed

# COMMAND ----------

results = []
t_all = time.time()
for (file, name, sql), action in zip(definitions, actions):
    t0 = time.time()
    fqn = name.replace("`", "")
    if action == "unchanged":
        results.append((fqn, file, "unchanged", 0.0, None))
        continue
    try:
        spark.sql(sql)
        results.append((fqn, file, "created" if action == "create" else "replaced", round(time.time() - t0, 1), None))
    except Exception as e:
        results.append((fqn, file, "FAILED", round(time.time() - t0, 1), str(e)[:1000]))

display(spark.createDataFrame(results, "metric_view string, file string, status string, seconds double, error string"))
failed = [r for r in results if r[2] == "FAILED"]
counts = {s: sum(1 for r in results if r[2] == s) for s in ("created", "replaced", "unchanged", "FAILED")}
print(f"{len(results)} metric views: {counts} in {time.time() - t_all:.0f}s")
if failed:
    raise RuntimeError(f"{len(failed)} metric view(s) failed: " + "; ".join(f"{r[0]}: {r[4][:300]}" for r in failed[:5]))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Try one
# MAGIC
# MAGIC Metric views are queried with `MEASURE(<measure>)` and `GROUP BY` any of their dimensions, e.g.:
# MAGIC
# MAGIC ```sql
# MAGIC SELECT category, MEASURE(net_revenue_sek) AS net_revenue, MEASURE(gross_margin_pct) AS margin_pct
# MAGIC FROM <catalog>.retail.sales_metrics
# MAGIC GROUP BY ALL
# MAGIC ```

# COMMAND ----------

display(spark.sql(f"""
    SELECT category, MEASURE(net_revenue_sek) AS net_revenue_sek, MEASURE(order_count) AS orders,
           MEASURE(gross_margin_pct) AS gross_margin_pct, MEASURE(return_rate_pct) AS return_rate_pct
    FROM `{catalog}`.retail.sales_metrics
    GROUP BY ALL ORDER BY net_revenue_sek DESC"""))

# COMMAND ----------

# Result for the job run page (and for automated checks)
dbutils.notebook.exit(json.dumps({"catalog": catalog, **counts, "seconds": round(time.time() - t_all, 1),
                                  "views": [r[0] for r in results]}))
