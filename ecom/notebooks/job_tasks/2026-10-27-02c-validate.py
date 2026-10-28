# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 02c · Validate the lakehouse
# MAGIC
# MAGIC The last task of `ecom_job`. Before anyone builds a Genie Agent on top of the data, we check that the
# MAGIC foundation is sound:
# MAGIC
# MAGIC | # | check | fails the task when |
# MAGIC |---|---|---|
# MAGIC | 1 | the 15 gold tables exist, each with its **primary key**; all **17 foreign keys** are registered | a table, PK or FK is missing |
# MAGIC | 2 | silver row counts equal `clean_rows` in `data/2026-10-27-manifest.json`; gold keys are unique and not null | a count differs / duplicate keys |
# MAGIC | 3 | gold row counts equal the expected counts (dimensions = silver, `fact_sales` = completed order lines) | a table is stale |
# MAGIC | 4 | the 6 **metric views** answer, and their totals equal `data/2026-10-27-expected-answers.json` | a view errors / a total differs |
# MAGIC | 5 | the **ecom tags** of `config/2026-10-27-tags.json` are present | a tag is missing |
# MAGIC
# MAGIC **Governance-proof.** The job runs as *you*. Once notebook 03 has attached row filters, a gold table shows you
# MAGIC only your scope, so its `count(*)` no longer equals the expected count. Row counts therefore come from the
# MAGIC **ungoverned silver** tables; gold counts and metric-view totals of a table *with* a row filter (or a view on
# MAGIC one) are shown as information only. The notebook only reads - running it again changes nothing.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters and helpers

# COMMAND ----------

import json
import os
import re
import unicodedata

dbutils.widgets.text("catalog", "", "Catalog (blank = automatic)")

DOMAINS = ["retail", "mobility", "telecom"]   # the three domains = gold schemas
DATE = "2026-10-27"


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


user_name = spark.sql("SELECT current_user()").first()[0]
catalog = dbutils.widgets.get("catalog").strip() or f"ecom_{bundle_short_name(user_name)}"
BUNDLE_ROOT = bundle_root()
in_list = ", ".join(sql_str(d) for d in DOMAINS)
problems = []   # every failed check adds a line here; the task fails at the end if not empty
print(f"Catalog: {catalog} | domains: {', '.join(DOMAINS)}")

with open(f"{BUNDLE_ROOT}/data/{DATE}-manifest.json", encoding="utf-8") as fh:
    manifest = {d: t for d, t in json.load(fh).items() if isinstance(t, dict)}
with open(f"{BUNDLE_ROOT}/data/{DATE}-expected-answers.json", encoding="utf-8") as fh:
    answers = json.load(fh)
with open(f"{BUNDLE_ROOT}/config/{DATE}-tags.json", encoding="utf-8") as fh:
    tag_config = json.load(fh)["tables"]

# Gold tables and their declared keys, read from the pipeline SQL (the single source).
gold = {}   # "retail.dim_product" -> {"pk": col, "fks": n}
for d in DOMAINS:
    with open(f"{BUNDLE_ROOT}/pipeline/{d}/{DATE}-03-gold.sql", encoding="utf-8") as fh:
        for block in fh.read().split("CREATE OR REFRESH MATERIALIZED VIEW ")[1:]:
            name = re.match(r"\$\{catalog\}\.(\w+\.\w+)", block).group(1)
            gold[name] = {"pk": re.search(r"PRIMARY KEY \((\w+)\)", block).group(1),
                          "fks": len(re.findall(r"CONSTRAINT fk_\w+ FOREIGN KEY", block))}
print(f"Expected: {len(gold)} gold tables, {sum(g['fks'] for g in gold.values())} foreign keys")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Gold tables, primary and foreign keys

# COMMAND ----------

existing = {f"{r.table_schema}.{r.table_name}": r.table_type for r in spark.sql(f"""
    SELECT table_schema, table_name, table_type FROM `{catalog}`.information_schema.tables
    WHERE table_schema IN ({in_list})
      AND table_name NOT LIKE '\\_\\_%' AND table_name NOT LIKE 'event\\_log%'""").collect()}
constraints = {}
for r in spark.sql(f"""
    SELECT table_schema, table_name, constraint_type, count(*) AS n
    FROM `{catalog}`.information_schema.table_constraints
    WHERE table_schema IN ({in_list}) GROUP BY ALL""").collect():
    constraints[(f"{r.table_schema}.{r.table_name}", r.constraint_type)] = r.n

missing = sorted(t for t in gold if t not in existing)
no_pk = sorted(t for t in gold if t in existing and not constraints.get((t, "PRIMARY KEY")))
fk_short = sorted(f"{t} ({constraints.get((t, 'FOREIGN KEY'), 0)}/{g['fks']})" for t, g in gold.items()
                  if t in existing and constraints.get((t, "FOREIGN KEY"), 0) < g["fks"])
if missing:
    problems.append(f"{len(missing)} gold table(s) missing: {', '.join(missing)}")
if no_pk:
    problems.append(f"{len(no_pk)} gold table(s) without PRIMARY KEY: {', '.join(no_pk)}")
if fk_short:
    problems.append(f"foreign keys missing on {', '.join(fk_short)} - run the job again (Genie derives joins from them)")
print(f"Gold tables: {len(gold) - len(missing)}/{len(gold)} | without PK: {len(no_pk)} | "
      f"tables with missing FKs: {len(fk_short)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Row counts (silver vs manifest, gold vs expected) and key uniqueness

# COMMAND ----------

row_filtered = {f"{r.table_schema}.{r.table_name}" for r in spark.sql(f"""
    SELECT table_schema, table_name FROM `{catalog}`.information_schema.row_filters
    WHERE table_schema IN ({in_list})""").collect()}

silver_rows = {}
for d in DOMAINS:
    for t, meta in manifest[d].items():
        n = spark.sql(f"SELECT count(*) FROM `{catalog}`.silver.`{d}_{t}`").first()[0]
        silver_rows[f"{d}.{t}"] = n
        if n != meta["clean_rows"]:
            problems.append(f"silver.{d}_{t}: {n} rows, manifest clean_rows {meta['clean_rows']}")

# What each gold table must contain: dimensions and most facts are 1:1 with a silver table.
expected_gold = {
    "retail.dim_product": silver_rows["retail.products"], "retail.dim_store": silver_rows["retail.stores"],
    "retail.dim_customer": silver_rows["retail.customers"], "retail.fact_sales": answers["retail"]["fact_sales_rows"],
    "retail.fact_returns": silver_rows["retail.returns"],
    "mobility.dim_vehicle_model": silver_rows["mobility.vehicle_models"], "mobility.dim_dealer": silver_rows["mobility.dealers"],
    "mobility.dim_customer": silver_rows["mobility.customers"],
    "mobility.fact_vehicle_sales": silver_rows["mobility.vehicle_sales"],
    "mobility.fact_service_visits": silver_rows["mobility.service_visits"],
    "telecom.dim_plan": silver_rows["telecom.plans"], "telecom.dim_customer": silver_rows["telecom.customers"],
    "telecom.dim_subscription": silver_rows["telecom.subscriptions"], "telecom.fact_billing": silver_rows["telecom.invoices"],
    "telecom.fact_usage": silver_rows["telecom.usage"],
}
stats = []
for t, g in sorted(gold.items()):
    if t in missing:
        continue
    r = spark.sql(f"SELECT count(*) AS n, count(DISTINCT `{g['pk']}`) AS k, count_if(`{g['pk']}` IS NULL) AS z "
                  f"FROM `{catalog}`.{t}").first()
    governed = t in row_filtered
    stats.append((t, g["pk"], expected_gold[t], r.n, governed))
    if r.n != r.k or r.z:
        problems.append(f"{t}: primary key {g['pk']} not unique / NULL")
    if not governed and r.n != expected_gold[t]:
        problems.append(f"{t}: {r.n} rows, expected {expected_gold[t]} - run the job again")
display(spark.createDataFrame(stats, "gold_table string, primary_key string, expected_rows long, "
                                     "rows_visible_to_you long, row_filter boolean"))
if row_filtered:
    print(f"ℹ️ {len(row_filtered)} gold table(s) carry a row filter (notebook 03) - you see only your scope there; "
          f"their counts are information only: {', '.join(sorted(row_filtered))}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Metric views answer - and agree with the expected answers
# MAGIC
# MAGIC Each total below is computed by the generator from the clean data (`data/2026-10-27-expected-answers.json`).
# MAGIC The same numbers are quoted by the Genie benchmarks and the README, so a match here means they all agree.

# COMMAND ----------

CHECKS = [   # (metric view, measure, expected value, gold table its rows come from)
    ("retail.sales_metrics", "net_revenue_sek", answers["retail"]["total"]["net_revenue_sek"], "retail.fact_sales"),
    ("retail.sales_metrics", "order_count", answers["retail"]["total"]["orders"], "retail.fact_sales"),
    ("retail.sales_metrics", "return_rate_pct", answers["retail"]["total"]["return_rate_pct"], "retail.fact_sales"),
    ("retail.return_metrics", "refund_amount_sek", answers["retail"]["total"]["refund_amount_sek"], "retail.fact_returns"),
    ("mobility.vehicle_sales_metrics", "vehicle_revenue_sek", answers["mobility"]["sales_total"]["vehicle_revenue_sek"],
     "mobility.fact_vehicle_sales"),
    ("mobility.vehicle_sales_metrics", "ev_share_pct", answers["mobility"]["sales_total"]["ev_share_pct"], "mobility.fact_vehicle_sales"),
    ("mobility.service_metrics", "service_revenue_sek", answers["mobility"]["service_total"]["service_revenue_sek"],
     "mobility.fact_service_visits"),
    ("telecom.billing_metrics", "billed_revenue_sek",
     sum(v["billed_revenue_sek"] for v in answers["telecom"]["billing_by_month"].values()), "telecom.fact_billing"),
    ("telecom.usage_metrics", "voice_minutes",
     sum(v["voice_minutes"] for v in answers["telecom"]["usage_by_month"].values()), "telecom.fact_usage"),
]
expected_views = {t for t, x in tag_config.items() if x["type"] == "METRIC_VIEW"}
missing_mv = sorted(expected_views - {t for t, k in existing.items() if k == "METRIC_VIEW"})
if missing_mv:
    problems.append(f"metric view(s) missing: {', '.join(missing_mv)} - rerun task metric_views")
mv_results = []
for view, measure, want, base in CHECKS:
    if view in missing_mv:
        continue
    try:
        got = spark.sql(f"SELECT MEASURE(`{measure}`) FROM `{catalog}`.{view}").first()[0]
        ok = got is not None and abs(float(got) - float(want)) < 0.006
        status = "OK" if ok else ("info only (row filter)" if base in row_filtered else "DIFFERENT")
        if status == "DIFFERENT":
            problems.append(f"{view}.{measure} = {got}, expected {want}")
    except Exception as e:
        got, status = None, "ERROR: " + str(e)[:300]
        problems.append(f"{view}.{measure} not queryable: {str(e)[:200]}")
    mv_results.append((view, measure, None if got is None else str(got), str(want), status))
display(spark.createDataFrame(mv_results, "metric_view string, measure string, value string, expected string, status string"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · ecom tags present

# COMMAND ----------

have = {(f"{r.schema_name}.{r.table_name}", r.tag_name) for r in spark.sql(
    f"SELECT schema_name, table_name, tag_name FROM `{catalog}`.information_schema.table_tags "
    f"WHERE schema_name IN ({in_list}) AND tag_name LIKE 'ecom\\_%'").collect()}
have_cols = {(f"{r.schema_name}.{r.table_name}", r.column_name, r.tag_name) for r in spark.sql(
    f"SELECT schema_name, table_name, column_name, tag_name FROM `{catalog}`.information_schema.column_tags "
    f"WHERE schema_name IN ({in_list}) AND tag_name LIKE 'ecom\\_%'").collect()}
want = {(t, k) for t, x in tag_config.items() for k in x["tags"]}
want_cols = {(t, c, k) for t, x in tag_config.items() for c, tags in x["columns"].items() for k in tags}
n_missing = len(want - have) + len(want_cols - have_cols)
print(f"ecom tags: {len(want) + len(want_cols) - n_missing}/{len(want) + len(want_cols)} present")
if n_missing:
    problems.append(f"{n_missing} ecom tag(s) missing - rerun task tags")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Verdict

# COMMAND ----------

if problems:
    print("❌ Lakehouse validation FAILED:")
    for p in problems:
        print("  -", p)
    raise RuntimeError("Lakehouse validation failed: " + " || ".join(problems))
print(f"✅ Lakehouse validated: {len(stats)} gold tables, {sum(g['fks'] for g in gold.values())} foreign keys, "
      f"{len(expected_views)} metric views, totals match the expected answers, tags present in `{catalog}`.")
dbutils.notebook.exit(json.dumps({"catalog": catalog, "gold_tables": len(stats), "metric_views": len(expected_views),
                                  "row_filtered_gold_tables": sorted(row_filtered),
                                  "silver_rows": silver_rows}))
