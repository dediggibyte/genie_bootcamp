# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 02a · Create the metric views (semantic layer)
# MAGIC
# MAGIC A **metric view** defines business measures (e.g. *total net amount*, *on-time payment rate*) and the
# MAGIC dimensions you may slice them by - **once**, in YAML, governed by Unity Catalog. Genie, dashboards and
# MAGIC SQL users then all get the same numbers.
# MAGIC
# MAGIC This notebook runs as task **`metric_views`** of the job `cpg_lakehouse_job`, right after the pipeline.
# MAGIC It creates, in the gold schemas `consumer`, `finance` and `manufacturing`:
# MAGIC
# MAGIC 1. the **industry metric views** that ship with the Lakehouse Industry Data Model
# MAGIC    (`metric_views/industry/<domain>.sql`, 22 views) as `<catalog>.<domain>.<table>_metrics`, and
# MAGIC 2. the **curated bootcamp metric views** in `metric_views/curated/*.sql` (when there are any).
# MAGIC
# MAGIC Metric views cannot be defined inside a Lakeflow pipeline, which is why they are a separate job task.
# MAGIC
# MAGIC 🔁 **Only what is missing or changed:** a view that already exists with the same definition is left
# MAGIC alone (`unchanged`); only new views are created and changed ones replaced. A re-run of the job is
# MAGIC therefore a quick check.
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
from concurrent.futures import ThreadPoolExecutor

dbutils.widgets.text("catalog", "", "Catalog (blank = automatic)")

DOMAINS = ["consumer", "finance", "manufacturing"]   # the bootcamp domains = gold schemas


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}."""
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
    raise FileNotFoundError("databricks.yml not found above this notebook - run it from the bootcamp folder.")


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
catalog = dbutils.widgets.get("catalog").strip() or f"cpg_{bundle_short_name(user_name)}"
BUNDLE_ROOT = bundle_root()
print(f"Catalog: {catalog} | domains: {', '.join(DOMAINS)}")
print(f"Bootcamp folder: {BUNDLE_ROOT}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Collect the metric view definitions
# MAGIC
# MAGIC The SQL files use the placeholder `${catalog}`; it is replaced with your catalog name here.

# COMMAND ----------

NAME_RE = re.compile(r"CREATE\s+OR\s+REPLACE\s+VIEW\s+([^\s(]+)", re.I)
definitions = []  # (kind, file, view name, sql)


def read_definitions(kind: str, path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        for stmt in split_sql_statements(fh.read()):
            sql = stmt.replace("${catalog}", catalog)
            m = NAME_RE.search(sql)
            definitions.append((kind, os.path.relpath(path, BUNDLE_ROOT), m.group(1) if m else sql[:60], sql))


for d in DOMAINS:
    read_definitions("industry", f"{BUNDLE_ROOT}/metric_views/industry/{d}.sql")
for path in sorted(glob.glob(f"{BUNDLE_ROOT}/metric_views/curated/*.sql")):
    read_definitions("curated", path)

print(f"{len(definitions)} metric view statements "
      f"({sum(1 for x in definitions if x[0] == 'industry')} industry, "
      f"{sum(1 for x in definitions if x[0] == 'curated')} curated)")

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


def unquote(name: str) -> str:
    return name.replace("`", "")


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
    kind, file, name, sql = defn
    fqn = unquote(name)
    if fqn not in existing:
        return "create"
    want = desired_yaml(sql)
    return "unchanged" if (want is not None and want == current_yaml(fqn)) else "replace"


with ThreadPoolExecutor(max_workers=8) as pool:
    actions = list(pool.map(plan, definitions))
print({a: actions.count(a) for a in sorted(set(actions))})

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Create or replace what is missing or changed
# MAGIC
# MAGIC One `spark.sql()` call per view. Industry views first, then the curated views (which may build on them).

# COMMAND ----------

results = []
t_all = time.time()
for (kind, file, name, sql), action in zip(definitions, actions):
    t0 = time.time()
    if action == "unchanged":
        results.append((kind, unquote(name), file, "unchanged", 0.0, None))
        continue
    try:
        spark.sql(sql)
        results.append((kind, unquote(name), file, "created" if action == "create" else "replaced",
                        round(time.time() - t0, 1), None))
    except Exception as e:
        results.append((kind, unquote(name), file, "FAILED", round(time.time() - t0, 1), str(e)[:1000]))

display(spark.createDataFrame(results, "kind string, metric_view string, file string, status string, seconds double, error string"))
failed = [r for r in results if r[3] == "FAILED"]
counts = {s: sum(1 for r in results if r[3] == s) for s in ("created", "replaced", "unchanged", "FAILED")}
print(f"{len(results)} metric views: {counts} in {time.time() - t_all:.0f}s")
if failed:
    raise RuntimeError(f"{len(failed)} metric view(s) failed: " + "; ".join(f"{r[1]}: {r[5][:300]}" for r in failed[:5]))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Try one
# MAGIC
# MAGIC Metric views are queried with `MEASURE(<measure>)` and `GROUP BY` any of their dimensions, e.g.:
# MAGIC
# MAGIC ```sql
# MAGIC SELECT invoice_status, MEASURE(invoice_count) AS invoices, MEASURE(total_net_amount) AS net_amount
# MAGIC FROM <catalog>.finance.ar_invoice_metrics
# MAGIC GROUP BY ALL
# MAGIC ```
# MAGIC
# MAGIC ⚠️ `total_net_amount` here is summed across **company-code currencies** (SEK, NOK, DKK, EUR, PLN) - a
# MAGIC classic trap that the curated bootcamp metric views and the Genie instructions fix later.

# COMMAND ----------

display(spark.sql(f"""
    SELECT invoice_status, MEASURE(invoice_count) AS invoices, MEASURE(total_net_amount) AS net_amount
    FROM `{catalog}`.finance.ar_invoice_metrics
    GROUP BY ALL ORDER BY invoices DESC"""))

# COMMAND ----------

# Result for the job run page (and for automated checks)
dbutils.notebook.exit(json.dumps({
    "catalog": catalog, **counts,
    "industry": sum(1 for r in results if r[0] == "industry"), "curated": sum(1 for r in results if r[0] == "curated"),
    "seconds": round(time.time() - t_all, 1), "views": [r[1] for r in results]}))
