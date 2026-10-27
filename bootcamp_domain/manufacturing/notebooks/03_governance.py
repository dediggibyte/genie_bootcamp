# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 03 · Governance — who may see which plant, its costs and its people
# MAGIC
# MAGIC Your manufacturing gold tables are built. Right now **everybody who can read them sees everything**: the
# MAGIC production orders, batches and yields of all four plants, every planned and actual production cost, and
# MAGIC the names and user ids of the people on the shop floor. In this notebook you put Unity Catalog **row
# MAGIC filters** and **column masks** on the gold tables, driven by **your e-mail address**. Because the policies
# MAGIC live *on the tables*, every consumer inherits them: SQL, dashboards, metric views and the **Genie Agent**
# MAGIC you build in notebook 04.
# MAGIC
# MAGIC Three independent access dimensions:
# MAGIC
# MAGIC | dimension | policy | mapping table |
# MAGIC |---|---|---|
# MAGIC | **plant** - which plants' rows you see | row filter | `governance.user_plant_access` |
# MAGIC | **cost** - planned / actual / standard production cost | column mask (`NULL` unless allowed) | `governance.cost_readers` |
# MAGIC | **people** - supervisor and approver names, user ids | column mask (`K****`, masked user id) | `governance.pii_readers` |
# MAGIC
# MAGIC | step | what | why |
# MAGIC |---|---|---|
# MAGIC | 1-2 | parameters, pre-flight check | find your catalog and make sure the pipeline has run |
# MAGIC | 3 | **who am I?** | policies are evaluated for the *person running the query* |
# MAGIC | 4 | **before**: look at the data without policies | a baseline to compare with |
# MAGIC | 5 | **mapping tables** in schema `governance` | *who may see what* is data, not code |
# MAGIC | 6 | **access functions** and **policy functions** | the rules, written once in SQL |
# MAGIC | 7 | **attach** row filters and column masks to the gold tables | `ALTER MATERIALIZED VIEW ... SET ROW FILTER / SET MASK` |
# MAGIC | 8 | **after**: same queries again | see the effect |
# MAGIC | 9 | **inspect** the policies | `information_schema.row_filters` / `column_masks` |
# MAGIC | 10 | **switch persona** by editing the mapping | the effect is immediate - no pipeline run |
# MAGIC | 11 | **metric views and Genie inherit** the policies | govern once, use everywhere |
# MAGIC | 12 | **try to break it** | learn where the boundaries are |
# MAGIC | 13 | *(optional)* share with a buddy | test as a *different* user |
# MAGIC | 14 | *(optional, advanced)* **ABAC**: tag-driven cost masking with `CREATE POLICY` | scale governance with governed tags |
# MAGIC | 15 | *(optional)* rollback | remove everything this notebook created |
# MAGIC | 16 | summary | every check of this run, including the rollback checks |
# MAGIC
# MAGIC ▶ **How to run:** attach to **Serverless** compute and click **Run all**. Every SQL statement the notebook
# MAGIC runs is printed above its result, so you can copy it into the SQL editor.
# MAGIC
# MAGIC 🔁 **Run it as often as you like - it only changes what is missing or different.** The mapping rows,
# MAGIC functions, policies and the demo metric view are compared with what is already in your catalog: things
# MAGIC that are already in place are reported as `unchanged` and are **not** touched again, so a second
# MAGIC *Run all* is a no-op (apart from the exercises in steps 10 and 12, which change something on purpose and
# MAGIC put it back right away). Nothing here re-runs the pipeline or reloads data - the policies sit on top of the
# MAGIC tables you loaded once.
# MAGIC
# MAGIC **Expected result:** after step 7 you only see rows of the plant(s) you mapped yourself to (default
# MAGIC **SE-LUN** = Lund Food Plant), every cost column is `NULL` and supervisor names are masked (`K****`).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | default | meaning |
# MAGIC |---|---|---|
# MAGIC | `catalog` | blank = `cpg_manufacturing_<your short user name>` | the catalog your pipeline wrote to |
# MAGIC | `user_email` | your login (`current_user()`) | whose access you configure in the mapping tables |
# MAGIC | `plant_code` | `SE-LUN` | plant(s) that user may see: `SE-LUN`, a list such as `SE-LUN,PL-POZ`, or `ALL` |
# MAGIC | `cost_access` | `false` | `true` = the user may read production costs |
# MAGIC | `pii_access` | `false` | `true` = the user may read people data (supervisor and approver names, user ids) |
# MAGIC | `buddy_email` | blank | *(optional, step 13)* a colleague to share your governed gold tables with |
# MAGIC | `advanced_abac` | `false` | *(optional, step 14)* run the ABAC section |
# MAGIC | `abac_tag` | `cost_confidential` | *(step 14)* the **governed tag** the ABAC policy matches (an account admin creates it) |
# MAGIC | `ask_genie` | `false` | *(optional, step 11)* ask your Genie Agent a question (only after notebook 04) |
# MAGIC | `rollback` | `false` | `true` = remove **everything** this notebook created at the end (step 15) |
# MAGIC
# MAGIC Plants of Fjällmark - the business names them by `manufacturing_facility.erp_plant_code` (also the prefix of
# MAGIC every line tag such as `PL-POZ-L2`), so that is the code the mapping uses:
# MAGIC
# MAGIC | plant code | SAP plant (`plant_code` on orders) | plant |
# MAGIC |---|---|---|
# MAGIC | `SE-LUN` | `LUND` | Lund Food Plant |
# MAGIC | `SE-NKP` | `NKPG` | Norrköping Beverage Plant |
# MAGIC | `FI-TMP` | `TMPR` | Tampere Oat Drink Plant (from April 2025) |
# MAGIC | `PL-POZ` | `POZN` | Poznań Personal Care Plant |
# MAGIC
# MAGIC The widget also accepts the 4-character SAP code (`LUND`) and translates it.

# COMMAND ----------

import hashlib
import json
import re
import textwrap
import time
import unicodedata

current_user = spark.sql("SELECT current_user()").first()[0]

dbutils.widgets.text("catalog", "", "01 Catalog (blank = automatic)")
dbutils.widgets.text("user_email", current_user, "02 User e-mail to configure")
dbutils.widgets.text("plant_code", "SE-LUN", "03 Plant(s): SE-LUN | SE-LUN,PL-POZ | ALL")
dbutils.widgets.dropdown("cost_access", "false", ["false", "true"], "04 May read production costs")
dbutils.widgets.dropdown("pii_access", "false", ["false", "true"], "05 May read people data")
dbutils.widgets.text("buddy_email", "", "06 (optional) Buddy e-mail")
dbutils.widgets.dropdown("advanced_abac", "false", ["false", "true"], "07 (optional) Run ABAC section")
dbutils.widgets.text("abac_tag", "cost_confidential", "08 (ABAC) Governed tag for costs")
dbutils.widgets.dropdown("ask_genie", "false", ["false", "true"], "09 (optional) Ask the Genie Agent")
dbutils.widgets.dropdown("rollback", "false", ["false", "true"], "10 Roll back at the end")


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}: the part before '@',
    lower-cased, every character that is not a letter or digit replaced by '_'."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


CATALOG = dbutils.widgets.get("catalog").strip() or f"cpg_manufacturing_{bundle_short_name(current_user)}"
C = f"`{CATALOG}`"   # back-quoted for SQL: catalog names with letters such as å/ä/ö need the quotes
USER_EMAIL = dbutils.widgets.get("user_email").strip() or current_user
PLANT_INPUT = sorted({c.strip().upper() for c in dbutils.widgets.get("plant_code").split(",") if c.strip()})
COST_ACCESS = dbutils.widgets.get("cost_access") == "true"
PII_ACCESS = dbutils.widgets.get("pii_access") == "true"
BUDDY_EMAIL = dbutils.widgets.get("buddy_email").strip()
RUN_ABAC = dbutils.widgets.get("advanced_abac") == "true"
ABAC_TAG = dbutils.widgets.get("abac_tag").strip() or "cost_confidential"
ASK_GENIE = dbutils.widgets.get("ask_genie") == "true"
RUN_ROLLBACK = dbutils.widgets.get("rollback") == "true"

DOMAINS = ["manufacturing", "finance"]   # the gold schemas of this sample (finance = reference tables only)
MAIN_DOMAIN = "manufacturing"

# Fixed names used across the bootcamp samples (an admin creates these account groups; the sample works without them).
ADMIN_GROUP = "cpg_bootcamp_admins"              # members bypass every policy (instructors)
PARTICIPANT_GROUP = "cpg_bootcamp_participants"  # used in the GRANT examples
BUDDY_SCHEMAS = tuple(DOMAINS)                   # gold schemas shared with the buddy (step 13)

FACILITY = "manufacturing.manufacturing_facility"
# The plant row filter, per governed table: (filter function, column it is attached to).
# production_order carries the SAP plant code; the other facts only the plant's manufacturing_facility_id.
# Master data (facility, lines, work centers, equipment, BOMs, routings) stays visible to everybody - Genie
# needs it to name plants and lines - but its people and cost columns are masked.
ROW_FILTERS = {
    "manufacturing.production_order": ("plant_code_row_filter", "plant_code"),
    "manufacturing.batch_record": ("plant_row_filter", "manufacturing_facility_id"),
    "manufacturing.yield_record": ("plant_row_filter", "manufacturing_facility_id"),
    "manufacturing.production_confirmation": ("plant_row_filter", "manufacturing_facility_id"),
    "manufacturing.planned_order": ("plant_row_filter", "manufacturing_facility_id"),
}
GOVERNED_TABLES = list(ROW_FILTERS)
# Production cost: the columns tagged dbx_confidential in model_tags/manufacturing.json. Masked to NULL unless
# you are a cost reader. The mask function is chosen per data type in step 2 (a mask returns the column's type).
COST_COLUMNS = [
    ("manufacturing.production_order", "planned_cost"),
    ("manufacturing.production_order", "actual_cost"),
    ("manufacturing.batch_record", "actual_cost_amount"),
    ("manufacturing.batch_record", "standard_cost_amount"),
    ("manufacturing.yield_record", "standard_cost_per_unit"),
    ("manufacturing.yield_record", "yield_variance_cost_impact"),
    ("manufacturing.routing", "standard_cost_amount"),
]
# People data: names and user ids, and the mask function each one gets. (The plant e-mail address in
# manufacturing_facility is a functional mailbox such as plant.lund@example.com, not personal data: not masked.)
PII_MASKS = {
    ("manufacturing.production_order", "production_supervisor"): "mask_name",
    ("manufacturing.production_order", "released_by"): "mask_user_id",
    ("manufacturing.production_order", "created_by"): "mask_user_id",
    ("manufacturing.manufacturing_bom", "approved_by"): "mask_name",
    ("manufacturing.production_line", "modified_by_user"): "mask_user_id",
    ("manufacturing.planned_order", "created_by_user"): "mask_user_id",
    ("manufacturing.planned_order", "last_modified_by_user"): "mask_user_id",
}
# ABAC (step 14): a cost column that is NOT masked manually - the purchase price of each machine.
ABAC_TABLE, ABAC_COLUMN, ABAC_POLICY = "manufacturing.equipment", "acquisition_cost", "mask_tagged_costs"

print(f"You are logged in as : {current_user}")
print(f"Catalog              : {CATALOG}")
print(f"Configure access for : {USER_EMAIL}")
print(f"  plant(s)           : {', '.join(PLANT_INPUT)}")
print(f"  may read costs     : {COST_ACCESS}")
print(f"  may read PII       : {PII_ACCESS}")
if USER_EMAIL.lower() != current_user.lower():
    print("\nNOTE: user_email is not you. The before/after queries below run as YOU, so you will only see rows "
          "if you are mapped as well (e.g. through a persona switch in step 10).")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Small helpers
# MAGIC `run()` prints a SQL statement and executes it - nothing is hidden. `check()` records a PASS / FAIL
# MAGIC (or WARN, for things outside your control such as a Genie answer) line that is summarised at the end of
# MAGIC the notebook. `display_rows()` runs a query **once**, shows the result and returns the rows for the checks
# MAGIC (`display(df)` followed by `df.collect()` would run the same query twice).

# COMMAND ----------

CHECKS = []
CHANGES = []   # (object, created | replaced | attached | updated | unchanged) - a re-run shows only 'unchanged'


IN_EXERCISE = False   # steps 10 and 12 change things on purpose and restore them; recorded as 'exercise'


def changed(obj: str, state: str) -> None:
    CHANGES.append((obj, "exercise" if IN_EXERCISE and state != "unchanged" else state))


def run(statement: str, args: dict | None = None, echo: bool = True):
    """Print the SQL statement, then run it. Returns a Spark DataFrame."""
    statement = textwrap.dedent(statement).strip()
    if echo:
        print(statement + ("" if statement.endswith(";") else ";"))
        if args:
            print(f"-- parameters: {args}")
        print()
    return spark.sql(statement, args) if args else spark.sql(statement)


def check(name: str, ok: bool, detail: str = "", level: str = "FAIL") -> None:
    """Record a check. A check that does not hold is reported as `level` (FAIL, or WARN)."""
    result = "PASS" if ok else level
    CHECKS.append({"check": name, "result": result, "detail": detail})
    print(f"{result}  {name}" + (f"  -- {detail}" if detail else ""))


def display_rows(df) -> list:
    """Run the query once: collect the rows, display them and return them."""
    rows = df.collect()
    display(spark.createDataFrame(rows, df.schema))
    return rows


TABLE_TYPES = {}   # 'schema.table' -> table_type, filled once by the pre-flight check (step 2)


def table_type(table: str) -> str:
    if table in TABLE_TYPES:
        return TABLE_TYPES[table]
    schema, name = table.split(".")
    rows = spark.sql(
        f"SELECT table_type FROM {C}.information_schema.tables WHERE table_schema = :s AND table_name = :t",
        {"s": schema, "t": name}).collect()
    TABLE_TYPES[table] = rows[0][0] if rows else None
    return TABLE_TYPES[table]


def alter(table: str) -> str:
    """Pipeline gold tables are MATERIALIZED VIEWs: 'ALTER TABLE' fails on them (EXPECT_TABLE_NOT_VIEW),
    you must say 'ALTER MATERIALIZED VIEW'. This helper picks the right keyword from the table type
    (read once in the pre-flight check)."""
    kind = table_type(table)
    keyword = {"MATERIALIZED_VIEW": "MATERIALIZED VIEW", "STREAMING_TABLE": "STREAMING TABLE"}.get(kind, "TABLE")
    return f"ALTER {keyword} {C}.{table}"


def silver_of(table: str) -> str:
    """The silver table a gold table is built from: manufacturing.production_order -> silver.manufacturing_production_order."""
    return "silver." + table.replace(".", "_")


def cost_mask_for(data_type: str) -> tuple:
    """'decimal(15,2)' -> ('mask_cost_15_2', 'DECIMAL(15,2)'): one cost mask per decimal type, because a
    column mask must return exactly the type of the column it masks."""
    m = re.fullmatch(r"decimal\((\d+),(\d+)\)", data_type.lower().replace(" ", ""))
    if not m:
        raise ValueError(f"cost column of type {data_type}: expected a DECIMAL")
    return f"mask_cost_{m.group(1)}_{m.group(2)}", f"DECIMAL({m.group(1)},{m.group(2)})"


# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Pre-flight check
# MAGIC The notebook needs the gold tables from the pipeline (job `cpg_manufacturing_job`) and their silver
# MAGIC sources: `silver.manufacturing_manufacturing_facility` is the security lookup of the row filters (explained
# MAGIC in step 6), and the self-checks use silver as the ungoverned reference of *which plants have data*. It also
# MAGIC checks that every column a policy goes on exists and reads its data type (for the cost masks). If something
# MAGIC is missing, run the pipeline job first.

# COMMAND ----------

masked_tables = sorted({t for t, _ in COST_COLUMNS} | {t for t, _ in PII_MASKS})
needed = (GOVERNED_TABLES + [t for t in masked_tables if t not in GOVERNED_TABLES] + [ABAC_TABLE]
          + [silver_of(t) for t in GOVERNED_TABLES + [FACILITY]])
TABLE_TYPES.update({f"{r.table_schema}.{r.table_name}": r.table_type for r in run(f"""
    SELECT table_schema, table_name, table_type
    FROM {C}.information_schema.tables
    WHERE table_schema IN ('manufacturing', 'silver')
""", echo=False).collect()})
missing = [t for t in needed if t not in TABLE_TYPES]
for t in needed:
    print(f"  {t:45s} {TABLE_TYPES.get(t, 'MISSING')}")
if missing:
    raise Exception(f"Missing in catalog {CATALOG}: {missing}. Run the pipeline job (cpg_manufacturing_job) first, "
                    f"or set the 'catalog' widget to the catalog your pipeline wrote to.")
not_mv = [t for t in GOVERNED_TABLES + masked_tables if TABLE_TYPES[t] != "MATERIALIZED_VIEW"]
if not_mv:
    print(f"NOTE: expected pipeline materialized views, found other types for {not_mv} - alter() adapts the keyword.")

# Every column a policy goes on must exist (one information_schema query for all of them).
needed_columns = ([(t, col) for t, (_, col) in ROW_FILTERS.items()] + COST_COLUMNS + list(PII_MASKS)
                  + [(ABAC_TABLE, ABAC_COLUMN)])
COLUMN_TYPES = {(f"{r.table_schema}.{r.table_name}", r.column_name): r.full_data_type for r in run(f"""
    SELECT table_schema, table_name, column_name, full_data_type
    FROM {C}.information_schema.columns
    WHERE table_schema = 'manufacturing'
      AND table_name IN ({', '.join(sorted({f"'{t.split('.')[1]}'" for t, _ in needed_columns}))})
""", echo=False).collect()}
missing_columns = [f"{t}.{c}" for t, c in needed_columns if (t, c) not in COLUMN_TYPES]
if missing_columns:
    raise Exception(f"Columns missing in catalog {CATALOG}: {missing_columns}. Re-run the pipeline job.")

# All masks: people masks by name, cost masks by the column's decimal type.
COST_MASK_TYPES = {}   # mask function -> SQL type
MASKS = dict(PII_MASKS)
for t, col in COST_COLUMNS + [(ABAC_TABLE, ABAC_COLUMN)]:
    fn, sql_type = cost_mask_for(COLUMN_TYPES[(t, col)])
    COST_MASK_TYPES[fn] = sql_type
    if (t, col) != (ABAC_TABLE, ABAC_COLUMN):   # the ABAC column is masked by the tag policy (step 14), not by hand
        MASKS[(t, col)] = fn
ABAC_MASK = cost_mask_for(COLUMN_TYPES[(ABAC_TABLE, ABAC_COLUMN)])[0]

# The plants (gold manufacturing_facility is master data: never row-filtered, so you always see all four).
plants = {r.erp_plant_code: (r.manufacturing_facility_id, r.plant_code, r.facility_name) for r in run(
    f"SELECT erp_plant_code, manufacturing_facility_id, plant_code, facility_name FROM {C}.{FACILITY} "
    "ORDER BY erp_plant_code", echo=False).collect()}
sap_to_plant = {sap: code for code, (_, sap, _) in plants.items()}
print(f"\nPlants in {FACILITY}: " + ", ".join(f"{c} ({sap})" for c, (_, sap, _) in plants.items()))
PLANT_CODES = sorted({sap_to_plant.get(c, c) for c in PLANT_INPUT})   # LUND -> SE-LUN
unknown = [c for c in PLANT_CODES if c != "ALL" and c not in plants]
if unknown:
    raise ValueError(f"Unknown plant code(s) {unknown}. Use one of {list(plants)} (or the SAP codes "
                     f"{list(sap_to_plant)}) or ALL.")
if PLANT_CODES != PLANT_INPUT:
    print(f"Plant code(s) {PLANT_INPUT} -> {PLANT_CODES}")


def plant_join(table_alias: str, table: str, facility_alias: str = "f") -> str:
    """Join condition from a governed table to a facility table, on the column the table's row filter uses."""
    column = ROW_FILTERS[table][1]
    return f"{facility_alias}.{column} = {table_alias}.{column}"


# Reference for the self-checks: which plants HAVE rows in each governed table. Read from the ungoverned
# silver layer (one query), so it does not depend on the policies (or on a previous run of this notebook).
REFERENCE = {t: set() for t in GOVERNED_TABLES}
for r in run("\nUNION ALL\n".join(f"""
    SELECT DISTINCT '{t}' AS governed_table, f.erp_plant_code AS plant FROM {C}.{silver_of(t)} AS s
    JOIN {C}.{silver_of(FACILITY)} AS f ON {plant_join('s', t)}""" for t in GOVERNED_TABLES), echo=False).collect():
    REFERENCE[r.governed_table].add(r.plant)
for t, codes in REFERENCE.items():
    print(f"  plants with data in {t:40s}: {', '.join(sorted(codes))}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Who am I?
# MAGIC Row filters and column masks are evaluated **for the person (or service principal) running the query**:
# MAGIC `current_user()` returns your e-mail, `is_account_group_member()` checks *account* group membership.
# MAGIC Members of the account group `cpg_bootcamp_admins` (the instructors) bypass every policy in this sample.

# COMMAND ----------

me = display_rows(run(f"""
    SELECT current_user()                                  AS me,
           is_account_group_member('{ADMIN_GROUP}')        AS in_admin_group,
           is_account_group_member('{PARTICIPANT_GROUP}')  AS in_participant_group
"""))
IS_ADMIN = me[0].in_admin_group
if IS_ADMIN:
    print(f"NOTE: you are in {ADMIN_GROUP} and bypass every policy - before and after will look the same. "
          "Use another login (or the buddy test in step 13) to see the effect.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Before: what can I see without policies?
# MAGIC Two views on the data that we will repeat after every change:
# MAGIC * **visibility** - for each governed table: how many rows you see and which plants they belong to
# MAGIC * **sensitive sample** - the first production orders with supervisor, user ids and costs, and the plant
# MAGIC   directory with its e-mail addresses

# COMMAND ----------

def visibility() -> list:
    """Rows and plants you can see in each governed table (runs as YOU). Displays and returns the rows."""
    parts = [f"""
      SELECT '{t}' AS governed_table, count(*) AS visible_rows,
             array_join(array_sort(collect_set(f.erp_plant_code)), ', ') AS visible_plants
      FROM {C}.{t} AS t
      LEFT JOIN {C}.{FACILITY} AS f ON {plant_join('t', t)}""" for t in GOVERNED_TABLES]
    return display_rows(run("\nUNION ALL".join(parts) + "\nORDER BY governed_table", echo=False))


def sensitive_samples():
    """Display the cost and people samples; returns (production-order rows, facility rows) for the checks."""
    orders = display_rows(run(f"""
        SELECT production_order_id, plant_code, production_supervisor, released_by, created_by,
               planned_cost, actual_cost, currency_code
        FROM {C}.manufacturing.production_order
        ORDER BY production_order_id
        LIMIT 5
    """, echo=False))
    facilities = display_rows(run(f"""
        SELECT erp_plant_code, plant_code, facility_name
        FROM {C}.{FACILITY}
        ORDER BY erp_plant_code
    """, echo=False))
    return orders, facilities


def check_sensitive(label: str, samples, cost: bool, pii: bool) -> None:
    """Costs are NULL unless cost reader; names and user ids masked unless PII reader."""
    orders, _ = samples
    if orders:   # only when you see production orders at all
        first = orders[0]
        check(f"{label}production_order.planned_cost {'readable' if cost else 'hidden (NULL)'}",
              (first.planned_cost is not None) == cost, str(first.planned_cost))
        check(f"{label}production_order.production_supervisor {'readable' if pii else 'masked'}",
              (first.production_supervisor or "").endswith("****") != pii, str(first.production_supervisor))


def as_dict(rows):
    return {r.governed_table: (r.visible_rows, r.visible_plants) for r in rows}


already = run(f"SELECT count(*) FROM {C}.information_schema.row_filters", echo=False).first()[0]
if already:
    print(f"NOTE: {already} row filter(s) are already attached (this is a re-run), so 'before' is already governed.")
BEFORE = as_dict(visibility())
sensitive_samples()

# COMMAND ----------

# MAGIC %md
# MAGIC **What you see:** all four plants in every governed table, the planned and actual cost of every order,
# MAGIC and the names and user ids of supervisors and planners. Anyone with `SELECT` on these tables - and any
# MAGIC Genie Agent built on them - sees exactly the same.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Mapping tables: *who may see what* is data
# MAGIC
# MAGIC | table | columns | meaning |
# MAGIC |---|---|---|
# MAGIC | `governance.user_plant_access` | `user_email`, `plant_code` | the user may see rows of that plant (`erp_plant_code`, `ALL` = every plant) |
# MAGIC | `governance.cost_readers` | `user_email` | the user may read production costs |
# MAGIC | `governance.pii_readers` | `user_email` | the user may read people data in clear text |
# MAGIC
# MAGIC Besides you, we seed three **fictional personas** so you can reason about typical access patterns.
# MAGIC Nobody can log in as them; in step 10 you will *become* them by copying their mapping to your e-mail.
# MAGIC
# MAGIC | persona | e-mail | plants | costs | PII | why |
# MAGIC |---|---|---|---|---|---|
# MAGIC | Johan Lindgren, plant manager Lund | `johan.lindgren@example.com` | SE-LUN | no | **yes** | runs the Lund plant and knows its people - but cost is the controller's business |
# MAGIC | Marta Kowalczyk, plant controller Poznań | `marta.kowalczyk@example.com` | PL-POZ | **yes** | no | explains Poznań's cost variances |
# MAGIC | COO | `coo@example.com` | ALL | **yes** | no | compares every plant's performance and cost - not individual people |
# MAGIC
# MAGIC Plant, cost and people access are **independent** dimensions - three mapping tables, three questions.
# MAGIC
# MAGIC The notebook reads the mapping tables **once** and only writes a row that is missing or different.

# COMMAND ----------

G = f"{C}.governance"
run(f"CREATE SCHEMA IF NOT EXISTS {G} COMMENT 'Governance: access-mapping tables and policy functions (notebook 03)'")
run(f"""
    CREATE TABLE IF NOT EXISTS {G}.user_plant_access (
      user_email STRING NOT NULL COMMENT 'User e-mail exactly as current_user() returns it (compared case-insensitively)',
      plant_code STRING NOT NULL COMMENT 'Plant the user may see (manufacturing_facility.erp_plant_code, e.g. SE-LUN) or ALL'
    )
    COMMENT 'Row-level access: which plants each user may see. Read by governance.has_plant_access().'
""")
run(f"""
    CREATE TABLE IF NOT EXISTS {G}.cost_readers (
      user_email STRING NOT NULL COMMENT 'User e-mail exactly as current_user() returns it (compared case-insensitively)'
    )
    COMMENT 'Users who may read production costs. Read by governance.can_read_cost().'
""")
run(f"""
    CREATE TABLE IF NOT EXISTS {G}.pii_readers (
      user_email STRING NOT NULL COMMENT 'User e-mail exactly as current_user() returns it (compared case-insensitively)'
    )
    COMMENT 'Users who may read people data (names, user ids, e-mail) in clear text. Read by governance.can_read_pii().'
""")


def read_mapping() -> dict:
    """Current mapping of every user in ONE query: lower(e-mail) -> [set of plants, may read cost, may read PII]."""
    mapping = {}
    for r in run(f"""
        SELECT lower(user_email) AS email, 'plant' AS kind, plant_code FROM {G}.user_plant_access
        UNION ALL
        SELECT lower(user_email) AS email, 'cost' AS kind, CAST(NULL AS STRING) AS plant_code FROM {G}.cost_readers
        UNION ALL
        SELECT lower(user_email) AS email, 'pii' AS kind, CAST(NULL AS STRING) AS plant_code FROM {G}.pii_readers
    """, echo=False).collect():
        entry = mapping.setdefault(r.email, [set(), False, False])
        if r.kind == "plant":
            entry[0].add(r.plant_code)
        elif r.kind == "cost":
            entry[1] = True
        else:
            entry[2] = True
    return mapping


MAPPING = read_mapping()
PERSONA_ROWS = {   # e-mail -> (plants, cost, PII)
    "johan.lindgren@example.com": (["SE-LUN"], False, True),
    "marta.kowalczyk@example.com": (["PL-POZ"], True, False),
    "coo@example.com": (["ALL"], True, False),
}

# Fictional personas (idempotent: only rows that are missing are inserted, nothing else is touched).
NO_MAPPING = [set(), False, False]
missing_plants = [(e, p) for e, (codes, _, _) in PERSONA_ROWS.items() for p in codes
                  if p not in MAPPING.get(e, NO_MAPPING)[0]]
missing_cost = [e for e, (_, cost, _) in PERSONA_ROWS.items() if cost and not MAPPING.get(e, NO_MAPPING)[1]]
missing_pii = [e for e, (_, _, pii) in PERSONA_ROWS.items() if pii and not MAPPING.get(e, NO_MAPPING)[2]]
if missing_plants:
    run(f"INSERT INTO {G}.user_plant_access (user_email, plant_code) VALUES "
        + ", ".join(f"('{e}', '{p}')" for e, p in missing_plants))
if missing_cost:
    run(f"INSERT INTO {G}.cost_readers (user_email) VALUES " + ", ".join(f"('{e}')" for e in missing_cost))
if missing_pii:
    run(f"INSERT INTO {G}.pii_readers (user_email) VALUES " + ", ".join(f"('{e}')" for e in missing_pii))
for e, p in missing_plants:
    MAPPING.setdefault(e, [set(), False, False])[0].add(p)
for e in missing_cost:
    MAPPING.setdefault(e, [set(), False, False])[1] = True
for e in missing_pii:
    MAPPING.setdefault(e, [set(), False, False])[2] = True
persona_changes = len(missing_plants) + len(missing_cost) + len(missing_pii)
print("unchanged: persona rows" if not persona_changes else f"persona rows added: {persona_changes}")
changed("persona mapping rows", "created" if persona_changes else "unchanged")


def set_flag(table: str, email: str, have: bool, want: bool, echo: bool) -> None:
    """Add or remove one user in a one-column reader table (cost_readers, pii_readers) - only if it differs."""
    if have == want:
        return
    if want:
        run(f"INSERT INTO {G}.{table} (user_email) VALUES (:email)", {"email": email}, echo)
    else:
        run(f"DELETE FROM {G}.{table} WHERE lower(user_email) = lower(:email)", {"email": email}, echo)


def set_access(email: str, codes: list, cost: bool, pii: bool, echo: bool = True):
    """Make the mapping rows of one user equal to (plants, cost flag, PII flag). Only the table that differs is
    rewritten - a re-run changes nothing. Works on the mapping read once above (MAPPING) and keeps it current."""
    key = email.lower()
    have_codes, have_cost, have_pii = MAPPING.get(key, NO_MAPPING)
    if have_codes == set(codes) and have_cost == cost and have_pii == pii:
        print(f"unchanged: mapping of {email} (plants {sorted(codes)}, cost {cost}, PII {pii})")
        changed(f"mapping {email}", "unchanged")
        return
    changed(f"mapping {email}", "updated")
    if have_codes != set(codes):
        run(f"DELETE FROM {G}.user_plant_access WHERE lower(user_email) = lower(:email)", {"email": email}, echo)
        if codes:
            values = ", ".join(f"(:email, :plant{i})" for i in range(len(codes)))
            run(f"INSERT INTO {G}.user_plant_access (user_email, plant_code) VALUES {values}",
                {"email": email, **{f"plant{i}": c for i, c in enumerate(codes)}}, echo)
    set_flag("cost_readers", email, have_cost, cost, echo)
    set_flag("pii_readers", email, have_pii, pii, echo)
    MAPPING[key] = [set(codes), cost, pii]


# The user from the widgets.
set_access(USER_EMAIL, PLANT_CODES, COST_ACCESS, PII_ACCESS)

print("Mapping now (the rows read above plus the changes just written):")
display(spark.createDataFrame(
    [(e, ", ".join(sorted(codes)), cost, pii) for e, (codes, cost, pii) in sorted(MAPPING.items())],
    "user_email string, plants string, may_read_cost boolean, may_read_pii boolean"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Access functions and policy functions
# MAGIC
# MAGIC We separate **"who is allowed"** (access functions) from **"what happens to a row or value"** (policy
# MAGIC functions). All of them are ordinary SQL UDFs in schema `governance`.
# MAGIC
# MAGIC | function | kind | returns |
# MAGIC |---|---|---|
# MAGIC | `is_bootcamp_admin()` | access | TRUE for members of the account group `cpg_bootcamp_admins` |
# MAGIC | `has_plant_access(plant_code)` | access | TRUE if you are mapped to that plant (or to `ALL`) |
# MAGIC | `can_read_cost()` | access | TRUE if you are in `cost_readers` |
# MAGIC | `can_read_pii()` | access | TRUE if you are in `pii_readers` |
# MAGIC | `plant_code_row_filter(plant_code)` | **row filter** | production orders carry the SAP plant code (`LUND`): translated to the plant code (`SE-LUN`), then `has_plant_access` |
# MAGIC | `plant_row_filter(manufacturing_facility_id)` | **row filter** | batches, yields, confirmations and planned orders only carry the plant's id: translated to the plant code, then `has_plant_access` |
# MAGIC | `mask_cost_<precision>_<scale>` | **column masks** | the cost for cost readers, `NULL` for everybody else - one per decimal type |
# MAGIC | `mask_name`, `mask_user_id` | **column masks** | the real value for PII readers, a masked value for everybody else |
# MAGIC
# MAGIC **The rule that keeps this working** (Unity Catalog does not support *nested* policies - a policy function
# MAGIC may not read a table that itself has a row filter or column mask, the query fails with
# MAGIC `UNSUPPORTED_NESTED_ROW_OR_COLUMN_ACCESS_POLICY`): both row filters need the plant directory to translate
# MAGIC an id or SAP code into a plant code. The gold `manufacturing.manufacturing_facility` carries no policy
# MAGIC today, but a filter that reads a gold table breaks the day someone governs it (ABAC in step 14 can add a
# MAGIC mask to any tagged column). So they read the **silver** copy `silver.manufacturing_manufacturing_facility`
# MAGIC (consumers never get access to silver - see step 12). The mapping tables are never governed either. You will
# MAGIC *see* the nested-policy error in step 12.
# MAGIC
# MAGIC Why `NULL` for costs and not `0`? A zero would silently turn every cost total, variance and average into a
# MAGIC wrong number; `NULL` makes `SUM`, `AVG` and the metric views return *no value* - visibly "not for you".
# MAGIC `mask_user_id` keeps service accounts (`SVC_MRP`, `SVC_PLM`) readable: they are systems, not people, and
# MAGIC "created by the MRP run vs. by a planner" stays analysable.

# COMMAND ----------

FUNCTIONS_IN_CATALOG = {r.routine_name: (r.comment or "") for r in run(
    f"SELECT routine_name, comment FROM {C}.information_schema.routines WHERE routine_schema = 'governance'",
    echo=False).collect()}
OUR_FUNCTIONS = []   # every function this notebook manages (the rollback drops exactly these)


def ensure_function(name: str, params: str, returns: str, comment: str, body: str, force: bool = False) -> str:
    """CREATE OR REPLACE the function only if it is missing or its definition changed.
    A short fingerprint of the definition is stored at the end of the function COMMENT, so a re-run can
    tell 'unchanged' from 'changed' without parsing SQL."""
    if name not in OUR_FUNCTIONS:
        OUR_FUNCTIONS.append(name)
    body = textwrap.dedent(body).strip()
    fingerprint = hashlib.sha1("|".join((params, returns, comment, body)).encode("utf-8")).hexdigest()[:10]
    full_comment = f"{comment} [def {fingerprint}]"
    if not force and FUNCTIONS_IN_CATALOG.get(name, "").endswith(f"[def {fingerprint}]"):
        print(f"unchanged: function governance.{name}")
        changed(f"function {name}", "unchanged")
        return "unchanged"
    state = "replaced" if name in FUNCTIONS_IN_CATALOG else "created"
    sql_comment = full_comment.replace("\\", "\\\\").replace("'", "\\'")
    run(f"CREATE OR REPLACE FUNCTION {G}.{name}({params})\nRETURNS {returns}\nCOMMENT '{sql_comment}'\n"
        f"RETURN {textwrap.indent(body, '  ').strip()}")
    FUNCTIONS_IN_CATALOG[name] = full_comment
    changed(f"function {name}", state)
    return state


SILVER_FACILITY = f"{C}.{silver_of(FACILITY)}"

# --- access functions -------------------------------------------------------------------------------
ensure_function(
    "is_bootcamp_admin", "", "BOOLEAN",
    f"Access function: TRUE for members of the account group {ADMIN_GROUP} (instructors bypass all policies).",
    f"is_account_group_member('{ADMIN_GROUP}')")
ensure_function(
    "has_plant_access", "plant_code STRING", "BOOLEAN",
    "Access function: TRUE if the current user may see rows of this plant (governance.user_plant_access, ALL = every plant).",
    f"""
    {G}.is_bootcamp_admin()
    OR EXISTS (
         SELECT 1
         FROM {G}.user_plant_access AS a
         WHERE lower(a.user_email) = lower(current_user())
           AND a.plant_code IN ('ALL', has_plant_access.plant_code)
       )""")
ensure_function(
    "can_read_cost", "", "BOOLEAN",
    "Access function: TRUE if the current user may read production costs (governance.cost_readers).",
    f"""
    {G}.is_bootcamp_admin()
    OR EXISTS (SELECT 1 FROM {G}.cost_readers AS r WHERE lower(r.user_email) = lower(current_user()))""")
ensure_function(
    "can_read_pii", "", "BOOLEAN",
    "Access function: TRUE if the current user may read people data in clear text (governance.pii_readers).",
    f"""
    {G}.is_bootcamp_admin()
    OR EXISTS (SELECT 1 FROM {G}.pii_readers AS r WHERE lower(r.user_email) = lower(current_user()))""")

# --- row filters -----------------------------------------------------------------------------------
ensure_function(
    "plant_code_row_filter", "row_plant_code STRING", "BOOLEAN",
    "Row filter for tables with the SAP plant_code (LUND): translates it to erp_plant_code (SE-LUN) and checks "
    "has_plant_access(). Looks the plant up in SILVER because a policy may not read a governed table.",
    f"""
    EXISTS (
      SELECT 1
      FROM {SILVER_FACILITY} AS f
      WHERE f.plant_code = row_plant_code
        AND {G}.has_plant_access(f.erp_plant_code)
    )""")
PLANT_FILTER = dict(
    name="plant_row_filter", params="row_manufacturing_facility_id BIGINT", returns="BOOLEAN",
    comment="Row filter for tables with manufacturing_facility_id: translates it to erp_plant_code and checks "
            "has_plant_access(). Looks the plant up in SILVER because a policy may not read a governed table.",
    body=f"""
    EXISTS (
      SELECT 1
      FROM {SILVER_FACILITY} AS f
      WHERE f.manufacturing_facility_id = row_manufacturing_facility_id
        AND {G}.has_plant_access(f.erp_plant_code)
    )""")
ensure_function(**PLANT_FILTER)

# --- column masks: cost ----------------------------------------------------------------------------
for fn, sql_type in sorted(COST_MASK_TYPES.items()):
    ensure_function(
        fn, f"amount {sql_type}", sql_type,
        f"Column mask for {sql_type} cost columns: the value for cost readers, otherwise NULL.",
        f"CASE WHEN {G}.can_read_cost() THEN amount ELSE CAST(NULL AS {sql_type}) END")

# --- column masks: people --------------------------------------------------------------------------
ensure_function(
    "mask_name", "name STRING", "STRING",
    "Column mask: clear text for PII readers, otherwise the first letter only (A****).",
    f"""
    CASE WHEN {G}.can_read_pii() OR name IS NULL THEN name
         ELSE concat(left(name, 1), '****') END""")
ensure_function(
    "mask_user_id", "user_id STRING", "STRING",
    "Column mask: clear text for PII readers and for service accounts (SVC_...), otherwise the first letter only (K****).",
    f"""
    CASE WHEN {G}.can_read_pii() OR user_id IS NULL OR left(user_id, 4) = 'SVC_' THEN user_id
         ELSE concat(left(user_id, 1), '****') END""")

display(run(f"""
    SELECT erp_plant_code, plant_code, facility_name, {G}.has_plant_access(erp_plant_code) AS i_may_see_it
    FROM {SILVER_FACILITY}
    ORDER BY erp_plant_code
"""))
display(run(f"SELECT {G}.can_read_cost() AS i_may_read_cost, {G}.can_read_pii() AS i_may_read_pii"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Attach the policies to the gold tables
# MAGIC
# MAGIC The gold tables are **materialized views owned by the pipeline**, so the statement is
# MAGIC `ALTER MATERIALIZED VIEW` - `ALTER TABLE` fails on them. Policies attached this way **survive pipeline
# MAGIC refreshes**, and changing a function or a mapping row takes effect **immediately**.
# MAGIC
# MAGIC Why only gold? Gold is the **serving layer** - the tables people, dashboards and Genie query. The pipeline
# MAGIC takes the *data* for every gold table from **silver**, which carries no policies. If you open the pipeline
# MAGIC SQL you will also see gold queries that mention another gold table in
# MAGIC `WHERE TRUE OR EXISTS (SELECT 1 FROM <gold table>)`: that clause only tells the pipeline the **build order**
# MAGIC (the table it references must exist first) and never filters a row - `TRUE OR ...` is always true. So the
# MAGIC policies on gold do not change what the pipeline writes. (They do cost the pipeline something: a gold table
# MAGIC whose build-order clause reads a governed table - most of them read `manufacturing_facility` - is recomputed
# MAGIC from silver on every update instead of incrementally; see the header of `pipeline/manufacturing/03_gold.sql`.)
# MAGIC Silver stays ungoverned *and closed*: consumers only get access to gold (step 12).
# MAGIC
# MAGIC The cell first reads `information_schema.row_filters` / `column_masks` and only attaches what is
# MAGIC missing (or replaces a policy that points to a different function) - on a re-run every line says
# MAGIC `unchanged`.

# COMMAND ----------

def short_fn(name: str) -> str:
    """'cat.governance.mask_email' -> 'mask_email' (information_schema returns full or short names)."""
    return (name or "").split(".")[-1].strip("`").lower()


# What is attached right now? (A re-run finds everything in place and changes nothing.)
def column_list(value) -> str:
    """target_columns comes back as a string or an array, depending on the runtime."""
    items = value if isinstance(value, (list, tuple)) else str(value or "").strip("[]").split(",")
    return ",".join(str(x).strip(" '\"`").lower() for x in items if str(x).strip())


FILTERS_NOW = {f"{r.table_schema}.{r.table_name}": (short_fn(r.filter_name), column_list(r.target_columns))
               for r in run(f"SELECT table_schema, table_name, filter_name, target_columns "
                            f"FROM {C}.information_schema.row_filters", echo=False).collect()}
MASKS_NOW = {(f"{r.table_schema}.{r.table_name}", r.column_name): short_fn(r.mask_name)
             for r in run(f"SELECT table_schema, table_name, column_name, mask_name "
                          f"FROM {C}.information_schema.column_masks", echo=False).collect()}
ATTACH_RESULT = []


def ensure_row_filter(table: str, fn: str, column: str) -> None:
    current = FILTERS_NOW.get(table)
    if current == (fn, column):
        print(f"unchanged: row filter {fn}({column}) on {table}")
        ATTACH_RESULT.append((table, "", f"row filter {fn}", "unchanged"))
        return
    if current:   # a different filter is attached: drop it first
        run(f"{alter(table)} DROP ROW FILTER")
    run(f"{alter(table)} SET ROW FILTER {G}.{fn} ON ({column})")
    ATTACH_RESULT.append((table, "", f"row filter {fn}", "replaced" if current else "attached"))


def ensure_mask(table: str, column: str, fn: str) -> None:
    current = MASKS_NOW.get((table, column))
    if current == fn:
        print(f"unchanged: mask {fn} on {table}.{column}")
        ATTACH_RESULT.append((table, column, f"mask {fn}", "unchanged"))
        return
    if current:
        run(f"{alter(table)} ALTER COLUMN {column} DROP MASK")
    run(f"{alter(table)} ALTER COLUMN {column} SET MASK {G}.{fn}")
    ATTACH_RESULT.append((table, column, f"mask {fn}", "replaced" if current else "attached"))


for t, (fn, column) in ROW_FILTERS.items():
    ensure_row_filter(t, fn, column)

for (t, column), fn in MASKS.items():
    ensure_mask(t, column, fn)

for t, col, pol, res in ATTACH_RESULT:
    changed(f"{pol} on {t}{'.' + col if col else ''}", res)
display(spark.createDataFrame(ATTACH_RESULT, "governed_table string, column string, policy string, result string"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8 · After: the same queries again

# COMMAND ----------

AFTER = as_dict(visibility())
after_samples = sensitive_samples()


def expected_codes(codes, table):
    """The plants you should see in a table: the plants you are mapped to that have data there."""
    allowed = set(plants) if "ALL" in codes else set(codes)
    return allowed & REFERENCE[table]


def visible_codes(result, table):
    return {c.strip() for c in (result[table][1] or "").split(",") if c.strip()}


def visibility_report(result, codes, table):
    """(ok, text): EXACTLY the expected plants are visible - not more (the filter works) and not
    fewer (it does not hide too much) - and there are rows whenever a plant is expected."""
    expected, seen, rows = expected_codes(codes, table), visible_codes(result, table), result[table][0]
    ok = seen == expected and (rows > 0) == bool(expected)
    return ok, f"{table}: expected [{', '.join(sorted(expected))}] -> visible {rows} rows [{', '.join(sorted(seen))}]"


if IS_ADMIN:
    print("Admin: policies are bypassed, skipping the after-checks.")
elif USER_EMAIL.lower() == current_user.lower():
    for t in GOVERNED_TABLES:
        ok, text = visibility_report(AFTER, PLANT_CODES, t)
        check(f"{t}: exactly the expected plants visible", ok, f"before {BEFORE[t][0]} rows; {text}")
    check_sensitive("", after_samples, COST_ACCESS, PII_ACCESS)

# COMMAND ----------

# MAGIC %md
# MAGIC **What changed:** only the plant(s) you mapped yourself to are left in the orders, batches, yields,
# MAGIC confirmations and planned orders; costs are `NULL` (unless `cost_access = true`) and supervisor names,
# MAGIC user ids are masked (unless `pii_access = true`). Notice that you did **not** get an
# MAGIC error - hidden rows simply do not exist for you, and hidden costs are simply empty.
# MAGIC
# MAGIC **Discussion:** the plant directory, production lines, work centers and equipment are still visible for
# MAGIC all plants - Genie needs them to name plants and lines. Is that right for equipment, which also carries
# MAGIC acquisition and maintenance costs? Step 14 masks such a cost column with a tag instead of by hand; a row
# MAGIC filter on `equipment.manufacturing_facility_id` would be one more line in `ROW_FILTERS`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9 · Inspect the policies
# MAGIC Unity Catalog records every attached policy. `information_schema` is the auditable list; `DESCRIBE TABLE
# MAGIC EXTENDED` shows them per table (and Catalog Explorer shows a shield icon on governed columns).

# COMMAND ----------

n_filters = len(display_rows(run(f"""
    SELECT table_schema, table_name, filter_name, target_columns
    FROM {C}.information_schema.row_filters
    ORDER BY table_schema, table_name
""")))
n_masks = len(display_rows(run(f"""
    SELECT table_schema, table_name, column_name, mask_name
    FROM {C}.information_schema.column_masks
    ORDER BY table_schema, table_name, column_name
""")))
display(run(f"DESCRIBE TABLE EXTENDED {C}.manufacturing.production_order")
        .filter("col_name IN ('Row Filter', 'Type', 'Owner')"))

check("row filters attached", n_filters >= len(ROW_FILTERS), f"{n_filters} row filters")
check("column masks attached", n_masks >= len(MASKS), f"{n_masks} column masks")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10 · Switch persona: change the mapping, not the code
# MAGIC
# MAGIC Access is *data*. Updating a mapping row changes what you see **in the very next query** - no pipeline
# MAGIC run, no re-deploy, no new function. We temporarily give **your** e-mail the mapping of each persona,
# MAGIC look at the result and restore your widget settings at the end. If `user_email` is a colleague, your
# MAGIC own mapping from earlier runs is saved first and put back exactly as it was.

# COMMAND ----------

PERSONAS = [
    ("Johan Lindgren - plant manager Lund: his plant and its people, no costs", ["SE-LUN"], False, True),
    ("Marta Kowalczyk - plant controller Poznan: her plant with costs, no people data", ["PL-POZ"], True, False),
    ("COO - every plant with costs, no people data", ["ALL"], True, False),
]
# Remember YOUR current mapping first: when user_email is a colleague, the rows you gave yourself in an earlier
# run (for example SE-LUN) must come back exactly as they were - an unmapped user sees 0 governed rows.
my_mapping = MAPPING.get(current_user.lower(), NO_MAPPING)
MY_PLANTS_BEFORE, MY_COST_BEFORE, MY_PII_BEFORE = sorted(my_mapping[0]), my_mapping[1], my_mapping[2]
IN_EXERCISE = True
try:
    for title, codes, cost, pii in PERSONAS:
        print("=" * 100 + f"\nYou are now: {title}  (plants {codes}, cost {cost}, PII {pii})\n" + "=" * 100)
        set_access(current_user, codes, cost, pii)
        got = as_dict(visibility())
        samples = sensitive_samples()
        if not IS_ADMIN:
            reports = [visibility_report(got, codes, t) for t in GOVERNED_TABLES]
            check(f"persona '{title}': exactly the rows of {codes} visible",
                  all(ok for ok, _ in reports), "; ".join(text for _, text in reports))
            check_sensitive(f"persona '{title}': ", samples, cost, pii)
finally:
    print("Restoring the mapping from the widgets ...")
    if USER_EMAIL.lower() != current_user.lower():
        # You configured a colleague: put YOUR rows back exactly as they were before section 10.
        set_access(current_user, MY_PLANTS_BEFORE, MY_COST_BEFORE, MY_PII_BEFORE)
        print(f"Your own mapping restored: plants {MY_PLANTS_BEFORE or 'none'}, cost {MY_COST_BEFORE}, "
              f"PII {MY_PII_BEFORE}")
    set_access(USER_EMAIL, PLANT_CODES, COST_ACCESS, PII_ACCESS)
    IN_EXERCISE = False

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11 · Metric views and Genie inherit the policies
# MAGIC
# MAGIC A metric view (or a plain view, a dashboard, a Genie Agent) reads the governed gold tables **as the
# MAGIC person asking**, so the row filters and masks apply automatically. We create a tiny demo metric view in
# MAGIC the `governance` schema and query it. The curated metric view of the sample
# MAGIC (`manufacturing.production_performance_metrics`) behaves the same way: its OEE, yield and on-time
# MAGIC measures follow your plants, and its cost measures are empty unless you may read costs.

# COMMAND ----------

DEMO_MV = f"{G}.governance_demo_production_order_metrics"
demo_yaml = textwrap.dedent(f"""
    version: 1.1
    comment: "Governance demo (notebook 03): production orders by plant. Inherits the row filter and cost masks of manufacturing.production_order."
    source: "{C}.manufacturing.production_order"
    joins:
      - name: plant
        source: "{C}.{FACILITY}"
        on: source.manufacturing_facility_id = plant.manufacturing_facility_id
    dimensions:
      - name: plant_code
        expr: plant.erp_plant_code
    measures:
      - name: order_count
        expr: COUNT(1)
      - name: planned_cost_local_currency
        expr: SUM(planned_cost)
""").strip()
demo_fp = hashlib.sha1(demo_yaml.encode("utf-8")).hexdigest()[:10]
demo_yaml = demo_yaml.replace('manufacturing.production_order."', f'manufacturing.production_order. [def {demo_fp}]"', 1)
try:
    current_text = json.loads(spark.sql(f"DESCRIBE TABLE EXTENDED {DEMO_MV} AS JSON").first()[0]).get("view_text") or ""
except Exception:
    current_text = ""   # does not exist yet
if f"[def {demo_fp}]" in current_text:
    print(f"unchanged: metric view {DEMO_MV}")
    changed("demo metric view", "unchanged")
else:
    run(f"CREATE OR REPLACE VIEW {DEMO_MV}\nWITH METRICS\nLANGUAGE YAML\nAS $$\n{demo_yaml}\n$$")
    changed("demo metric view", "replaced" if current_text else "created")
mv_rows = display_rows(run(f"""
    SELECT plant_code, MEASURE(order_count) AS orders, MEASURE(planned_cost_local_currency) AS planned_cost
    FROM {DEMO_MV}
    GROUP BY plant_code
    ORDER BY plant_code
"""))
if not IS_ADMIN and USER_EMAIL.lower() == current_user.lower():
    mv_codes, mv_orders = {r.plant_code for r in mv_rows}, sum(r.orders for r in mv_rows)
    check("metric view inherits the row filter (same plants and order count as the table)",
          mv_codes == expected_codes(PLANT_CODES, "manufacturing.production_order")
          and mv_orders == AFTER["manufacturing.production_order"][0],
          f"plants {sorted(mv_codes)}, {mv_orders} orders (table: {AFTER['manufacturing.production_order'][0]} visible rows)")
    if mv_rows:
        check(f"metric view inherits the cost mask (planned cost {'shown' if COST_ACCESS else 'empty'})",
              all((r.planned_cost is not None) == COST_ACCESS for r in mv_rows),
              ", ".join(f"{r.plant_code}: {r.planned_cost}" for r in mv_rows))

display(run(f"""
    SELECT table_schema, table_name
    FROM {C}.information_schema.tables
    WHERE table_type = 'METRIC_VIEW'
    ORDER BY table_schema, table_name
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Ask your Manufacturing Analyst Genie Agent *(only when `ask_genie = true`)*
# MAGIC You build the agent **Fjällmark Manufacturing Analyst** in notebook 04. When you come back here afterwards,
# MAGIC set the widget `ask_genie` to `true` and run this cell: it asks the agent a question through the Genie
# MAGIC Conversation API - the answer only contains your plants. If the agent does not exist yet, the cell just
# MAGIC tells you so.

# COMMAND ----------

AGENT_TITLE = f"Fjällmark Manufacturing Analyst ({CATALOG})"   # the title notebook 04 gives the agent


def my_agents(w):
    """Genie Agents with exactly the title notebook 04 gives the agent of this catalog."""
    found, token = [], None
    while True:
        query = {"page_size": 100, **({"page_token": token} if token else {})}
        resp = w.api_client.do("GET", "/api/2.0/genie/spaces", query=query)
        found += [s for s in resp.get("spaces", []) if s.get("title") == AGENT_TITLE]
        token = resp.get("next_page_token")
        if not token:
            return found


def ask_genie_agent(w, space_id: str, question: str, timeout_s: int = 240):
    start = w.api_client.do("POST", f"/api/2.0/genie/spaces/{space_id}/start-conversation", body={"content": question})
    conv, msg = start["conversation_id"], start["message_id"]
    base = f"/api/2.0/genie/spaces/{space_id}/conversations/{conv}/messages/{msg}"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        m = w.api_client.do("GET", base)
        if m.get("status") in ("COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"):
            break
        time.sleep(5)
    status = m.get("status")
    print(f"Genie status: {status}")
    for a in m.get("attachments") or []:
        if a.get("text"):
            print("Genie says:", a["text"].get("content", ""))
        if a.get("query"):
            print("Genie SQL:\n" + a["query"].get("query", ""))
            res = w.api_client.do("GET", f"{base}/attachments/{a['attachment_id']}/query-result")
            sr = res.get("statement_response", {})
            cols = [c["name"] for c in sr.get("manifest", {}).get("schema", {}).get("columns", [])]
            rows = sr.get("result", {}).get("data_array", []) or []
            return status, cols, rows
    return status, [], []


if not ASK_GENIE:
    print("ask_genie = false - skipping the Genie question. (Set it to true after notebook 04.)")
else:
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    agents = my_agents(w)
    if not agents:
        print(f"No Genie Agent titled '{AGENT_TITLE}' yet - come back after notebook 04.")
    else:
        agent = agents[0]
        print(f"Asking '{agent['title']}' ({agent['space_id']}) ...")
        status, cols, rows = ask_genie_agent(w, agent["space_id"],
                                             "How many production orders are there per plant? Show the plant code.")
        if rows:
            display(spark.createDataFrame([[str(v) for v in r] for r in rows], cols))
        if not IS_ADMIN and USER_EMAIL.lower() == current_user.lower():
            if status != "COMPLETED" or not rows:
                # Genie is a language model: an empty or failed answer says nothing about the policies.
                check("Genie answered with a result table", False,
                      f"status {status}, {len(rows)} rows - re-run this cell or ask the question in the Genie UI",
                      level="WARN")
            else:
                answer_text = " ".join(str(v) for r in rows for v in r)
                expected = expected_codes(PLANT_CODES, "manufacturing.production_order")
                # A plant may appear as SE-LUN or as its SAP code LUND (whole word, so 'Lund' in a name does not count).
                in_answer = {p for p, (_, sap, _) in plants.items()
                             if p in answer_text or re.search(rf"\b{sap}\b", answer_text)}
                leaked, shown = sorted(in_answer - expected), sorted(in_answer & expected)
                check("Genie answer contains no plant you may not see", not leaked,
                      f"unexpected: {leaked}" if leaked else f"plants in the answer: {shown}")
                check("Genie answer shows your plants", shown == sorted(expected),
                      f"expected {sorted(expected)}, found {shown} (Genie may have shown ids instead of codes)",
                      level="WARN")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 12 · Try to break it
# MAGIC
# MAGIC Four attempts to get around the policies - with the expected outcome and the lesson.
# MAGIC
# MAGIC | # | attempt | expected outcome | lesson |
# MAGIC |---|---|---|---|
# MAGIC | A | copy the table (`CREATE TABLE ... AS SELECT`) | the copy only contains what **you** can see (masked values stay masked) - but the copy has **no** policy | copies leave governance: only give consumers `SELECT`, never `CREATE` on gold schemas; lineage shows every copy |
# MAGIC | B | query **silver** instead of gold | you see **everything**, costs included | silver is not governed: consumers get `SELECT` on **gold only** |
# MAGIC | C | filter on a masked cost / ask for another plant directly | **0 rows**, no error | the mask is applied *before* your `WHERE`; hidden rows don't exist for you |
# MAGIC | D | (engineer) let a policy read another governed table | query **fails** with `UNSUPPORTED_NESTED_ROW_OR_COLUMN_ACCESS_POLICY` | keep lookup tables ungoverned - that is why the plant filters read silver |

# COMMAND ----------

# MAGIC %md
# MAGIC ### A · Copy the table

# COMMAND ----------

run(f"CREATE OR REPLACE TABLE {G}.break_copy_production_order AS SELECT * FROM {C}.manufacturing.production_order")
copy_rows = display_rows(run(f"""
    SELECT 'copy of manufacturing.production_order' AS what, count(*) AS rows_in_copy,
           array_join(array_sort(collect_set(f.erp_plant_code)), ', ') AS plants_in_copy,
           count(planned_cost) AS rows_with_a_planned_cost
    FROM {G}.break_copy_production_order AS t
    LEFT JOIN {C}.{FACILITY} AS f ON f.plant_code = t.plant_code
"""))[0]
display(run(f"SELECT production_order_id, plant_code, production_supervisor, planned_cost "
            f"FROM {G}.break_copy_production_order ORDER BY production_order_id LIMIT 3"))
copy_policies = run(f"""
    SELECT (SELECT count(*) FROM {C}.information_schema.row_filters
            WHERE table_schema = 'governance' AND table_name = 'break_copy_production_order')
         + (SELECT count(*) FROM {C}.information_schema.column_masks
            WHERE table_schema = 'governance' AND table_name = 'break_copy_production_order')
""", echo=False).first()[0]
print(f"Row filters and masks on the copy: {copy_policies}  <- the copy is NOT governed")
if not IS_ADMIN and USER_EMAIL.lower() == current_user.lower():
    copy_codes = {c.strip() for c in (copy_rows.plants_in_copy or "").split(",") if c.strip()}
    check("A: CTAS copies exactly the rows you can see",
          copy_codes == expected_codes(PLANT_CODES, "manufacturing.production_order")
          and copy_rows.rows_in_copy == AFTER["manufacturing.production_order"][0],
          f"{copy_rows.rows_in_copy} rows {sorted(copy_codes)} "
          f"(visible in the table: {AFTER['manufacturing.production_order'][0]} rows)")
    if not COST_ACCESS:
        check("A: masked costs stay masked in the copy (no planned cost copied)",
              copy_rows.rows_with_a_planned_cost == 0, f"{copy_rows.rows_with_a_planned_cost} rows with a cost")
    check("A: the copy carries no policy", copy_policies == 0)
run(f"DROP TABLE IF EXISTS {G}.break_copy_production_order")
print("Copy dropped.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### B · Go around gold: query silver
# MAGIC You **own** this catalog, so you can read silver. A business user should not be able to.

# COMMAND ----------

silver = display_rows(run(f"""
    SELECT f.erp_plant_code AS plant_code, count(*) AS orders_in_silver, sum(s.planned_cost) AS planned_cost
    FROM {C}.silver.manufacturing_production_order AS s
    LEFT JOIN {SILVER_FACILITY} AS f ON f.plant_code = s.plant_code
    GROUP BY f.erp_plant_code
    ORDER BY f.erp_plant_code
"""))
check("B: silver is NOT governed (you see every plant and its costs there)",
      ({r.plant_code for r in silver} >= REFERENCE["manufacturing.production_order"]
       and all(r.planned_cost is not None for r in silver)) or IS_ADMIN,
      f"{len(silver)} plants in silver")

print("""
Lesson: grant business users access to the GOLD schemas only. For example (not executed here):

  GRANT USE CATALOG ON CATALOG {c} TO `{g}`;
  GRANT USE SCHEMA, SELECT ON SCHEMA {c}.manufacturing TO `{g}`;
  GRANT USE SCHEMA, SELECT ON SCHEMA {c}.finance       TO `{g}`;
  -- nothing on landing, bronze, silver or governance.
  -- EXECUTE on the policy functions is NOT needed: Unity Catalog evaluates the policies for the reader,
  -- with the rights of the table owner.
  -- Use SHOW GRANTS ON SCHEMA {c}.silver to verify that no consumer group has access.
""".format(c=C, g=PARTICIPANT_GROUP))

# COMMAND ----------

# MAGIC %md
# MAGIC ### C · Probe a masked cost, or ask for another plant directly

# COMMAND ----------

probe = display_rows(run(f"SELECT count(*) AS orders_with_a_planned_cost_above_zero "
                         f"FROM {C}.manufacturing.production_order WHERE planned_cost > 0"))
other = [p for p in plants if "ALL" not in PLANT_CODES and p not in PLANT_CODES][:1]
if other:
    direct = display_rows(run(f"SELECT count(*) AS orders_of_{other[0].lower().replace('-', '_')} "
                              f"FROM {C}.manufacturing.production_order WHERE plant_code = :sap",
                              {"sap": plants[other[0]][1]}))
if not IS_ADMIN and USER_EMAIL.lower() == current_user.lower():
    if not COST_ACCESS:
        check("C: filtering on a masked cost finds nothing", probe[0][0] == 0)
    if other:
        check(f"C: asking for {other[0]} directly returns 0 rows (no error)", direct[0][0] == 0)

# COMMAND ----------

# MAGIC %md
# MAGIC ### D · (engineer) Nested policies are not supported
# MAGIC Imagine an engineer "simplifies" the facility-id filter: a batch is visible when the **governed**
# MAGIC `manufacturing.production_order` has a visible order of that plant. We do that for a moment, query the
# MAGIC batches, and restore the silver-based filter - whatever happens.

# COMMAND ----------

try:
    run(f"""
        CREATE OR REPLACE FUNCTION {G}.plant_row_filter(row_manufacturing_facility_id BIGINT)
        RETURNS BOOLEAN
        RETURN EXISTS (SELECT 1 FROM {C}.manufacturing.production_order AS o
                       WHERE o.manufacturing_facility_id = row_manufacturing_facility_id)
    """)
    try:
        run(f"SELECT count(*) FROM {C}.manufacturing.batch_record").collect()
        check("D: nested policy is rejected", False, "query unexpectedly succeeded")
    except Exception as e:
        msg = str(e).split("\n")[0]
        print(f"Expected error:\n  {msg[:400]}")
        check("D: nested policy is rejected", "UNSUPPORTED_NESTED_ROW_OR_COLUMN_ACCESS_POLICY" in str(e), msg[:120])
finally:
    IN_EXERCISE = True
    ensure_function(**PLANT_FILTER, force=True)   # put the silver-based filter from step 6 back
    IN_EXERCISE = False
    batches = run(f"SELECT count(*) FROM {C}.manufacturing.batch_record", echo=False).first()[0]
    print(f"Restored. Batch records visible again: {batches}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 13 · *(optional)* Share with a buddy - test as a different user
# MAGIC
# MAGIC The real test of governance is a **second person**. Put a colleague's e-mail into the `buddy_email`
# MAGIC widget and re-run this cell. It grants your buddy `USE CATALOG` on your catalog and `USE SCHEMA` + `SELECT`
# MAGIC on your **gold** schemas `manufacturing` and `finance` (the reference tables) only (that covers the gold
# MAGIC tables *and* the metric views in them), and maps them to **PL-POZ** without costs and without PII. Nothing on
# MAGIC `silver` or `governance` is granted: the row filters and masks run with the rights of the table owner (you),
# MAGIC so the reader needs neither the mapping tables nor `EXECUTE` on the functions. Then ask your buddy to run in
# MAGIC the SQL editor (they also need **CAN USE** on a SQL warehouse):
# MAGIC
# MAGIC ```sql
# MAGIC SELECT * FROM <your catalog>.manufacturing.production_order LIMIT 10;      -- expected: only POZN rows, planned_cost NULL
# MAGIC SELECT count(*) FROM <your catalog>.manufacturing.batch_record;            -- expected: only Poznań batches
# MAGIC SELECT plant, MEASURE(oee_pct) FROM <your catalog>.manufacturing.production_performance_metrics
# MAGIC GROUP BY plant;                                                             -- expected: PL-POZ only
# MAGIC SELECT * FROM <your catalog>.silver.manufacturing_production_order LIMIT 10;  -- expected: PERMISSION_DENIED
# MAGIC ```
# MAGIC To let the buddy use your Genie Agent as well, share it with them as **CAN RUN**.
# MAGIC
# MAGIC > These are instructions, not a recorded result: this section has not been run with a second, non-admin
# MAGIC > user. If your buddy gets a permission error instead of filtered rows, note which statement failed.
# MAGIC
# MAGIC Revoke afterwards with the `REVOKE` statements printed below (or run the rollback).

# COMMAND ----------

if not BUDDY_EMAIL:
    print("buddy_email is empty - skipping. (Optional exercise.)")
else:
    principal = f"`{BUDDY_EMAIL}`"
    run(f"GRANT USE CATALOG ON CATALOG {C} TO {principal}")
    for schema in BUDDY_SCHEMAS:
        run(f"GRANT USE SCHEMA, SELECT ON SCHEMA {C}.{schema} TO {principal}")
    set_access(BUDDY_EMAIL, ["PL-POZ"], False, False)
    display(run(f"SHOW GRANTS {principal} ON SCHEMA {C}.manufacturing"))
    print("To undo:\n" + "".join(f"  REVOKE USE SCHEMA, SELECT ON SCHEMA {C}.{s} FROM {principal};\n"
                                 for s in BUDDY_SCHEMAS)
          + f"  REVOKE USE CATALOG ON CATALOG {C} FROM {principal};\n"
          + f"  DELETE FROM {G}.user_plant_access WHERE user_email = '{BUDDY_EMAIL}';")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 14 · *(optional, advanced)* ABAC - tag-driven cost masking with `CREATE POLICY`
# MAGIC
# MAGIC Manual masks are attached column by column. **Attribute-based access control (ABAC)** attaches one
# MAGIC **policy** to a catalog, schema or table that masks *every column carrying a governed tag* - new tables
# MAGIC and columns are covered as soon as they are tagged.
# MAGIC
# MAGIC We tag a cost column that is **not** masked yet - `manufacturing.equipment.acquisition_cost`, the purchase
# MAGIC price of each machine - with the governed tag from the widget `abac_tag` (default `cost_confidential`).
# MAGIC The policy reuses the cost mask of step 6 for that column's type, so cost readers still see the amount.
# MAGIC
# MAGIC **Before you start:** unlike `class.name`, a cost tag is not a system tag. An **account admin** creates it
# MAGIC once (Catalog Explorer → *Govern* → *Governed tags*, key `cost_confidential`, no values) and gives you
# MAGIC **ASSIGN** on it. Without it the cell explains the error and skips the rest.
# MAGIC
# MAGIC **Never put a manual mask and an ABAC mask on the same column**: the column then has two masks, every
# MAGIC query fails with `MULTIPLE_MASKS` - and so does the next pipeline refresh. That is why the policy is
# MAGIC scoped to one table here, and **before** tagging anything the cell checks that no column of that table
# MAGIC the policy would cover (`acquisition_cost` itself, or a column already carrying the tag) has a manual mask.
# MAGIC The mask function returns one decimal type, so only tag columns of that type (`maintenance_cost` has the
# MAGIC same type). (In production you would attach the policy to the schema or catalog and use ABAC *instead of*
# MAGIC manual masks.)
# MAGIC
# MAGIC Set the widget `advanced_abac` to `true` to run it.

# COMMAND ----------

ABAC_SCHEMA, ABAC_TABLE_NAME = ABAC_TABLE.split(".")


def abac_policy_exists() -> bool:
    try:
        return any(r[0] == ABAC_POLICY for r in spark.sql(f"SHOW POLICIES ON TABLE {C}.{ABAC_TABLE}").collect())
    except Exception:
        return False


collisions, tagged_ok = [], False
if not RUN_ABAC:
    print("advanced_abac = false - skipping the ABAC section.")
else:
    # The policy will mask acquisition_cost plus every column of this table carrying the tag.
    # None of them may already have a manual mask - check BEFORE tagging anything.
    collisions = run(f"""
        SELECT column_name, mask_name
        FROM {C}.information_schema.column_masks
        WHERE table_schema = '{ABAC_SCHEMA}' AND table_name = '{ABAC_TABLE_NAME}'
          AND (column_name = '{ABAC_COLUMN}'
               OR column_name IN (SELECT column_name FROM {C}.information_schema.column_tags
                                  WHERE schema_name = '{ABAC_SCHEMA}' AND table_name = '{ABAC_TABLE_NAME}'
                                    AND tag_name = :tag))
    """, {"tag": ABAC_TAG}).collect()
    check(f"ABAC: no manual mask on a column the policy would cover ({ABAC_TABLE})", not collisions,
          ", ".join(f"{r.column_name} has mask {r.mask_name}" for r in collisions) or "none")
    if collisions:
        print(f"Skipping the ABAC exercise: an ABAC mask on top of a manual mask would make every query on "
              f"{ABAC_TABLE} fail with MULTIPLE_MASKS. Remove the manual mask first, e.g.\n"
              + "\n".join(f"  {alter(ABAC_TABLE)} ALTER COLUMN {r.column_name} DROP MASK;" for r in collisions))


def abac_tagged() -> bool:
    return run(f"""
        SELECT 1 FROM {C}.information_schema.column_tags
        WHERE schema_name = '{ABAC_SCHEMA}' AND table_name = '{ABAC_TABLE_NAME}'
          AND column_name = '{ABAC_COLUMN}' AND tag_name = :tag""", {"tag": ABAC_TAG}, echo=False).count() > 0


if RUN_ABAC and not collisions:
    try:
        if abac_tagged():
            print(f"unchanged: tag {ABAC_TAG} on {ABAC_TABLE}.{ABAC_COLUMN}")
            changed("ABAC tag", "unchanged")
        else:
            run(f"{alter(ABAC_TABLE)} ALTER COLUMN {ABAC_COLUMN} SET TAGS ('{ABAC_TAG}')")
            changed("ABAC tag", "created")
        tagged_ok = True
    except Exception as e:
        check(f"ABAC: assign the governed tag {ABAC_TAG}", False,
              f"{str(e).splitlines()[0][:200]} - the governed tag must exist and you need ASSIGN on it "
              "(ask an account admin)")

if tagged_ok and abac_policy_exists():
    print(f"unchanged: ABAC policy {ABAC_POLICY} on {ABAC_TABLE}")
    changed("ABAC policy", "unchanged")
elif tagged_ok:
    changed("ABAC policy", "created")
    run(f"""
        CREATE OR REPLACE POLICY {ABAC_POLICY}
        ON TABLE {C}.{ABAC_TABLE}
        COMMENT 'Sample ABAC demo: mask every column tagged {ABAC_TAG} with governance.{ABAC_MASK}'
        COLUMN MASK {G}.{ABAC_MASK}
        TO `account users`
        FOR TABLES
        MATCH COLUMNS has_tag('{ABAC_TAG}') AS c
        ON COLUMN c
    """)
if tagged_ok:
    display(run(f"SHOW POLICIES ON TABLE {C}.{ABAC_TABLE}"))
    display(run(f"DESCRIBE POLICY {ABAC_POLICY} ON TABLE {C}.{ABAC_TABLE}"))
    sample = display_rows(run(f"SELECT equipment_id, name, {ABAC_COLUMN}, maintenance_cost FROM {C}.{ABAC_TABLE} "
                              "ORDER BY equipment_id LIMIT 5"))
    if sample and not IS_ADMIN:
        check("ABAC: acquisition_cost masked by the tag policy", (sample[0][2] is not None) == COST_ACCESS,
              str(sample[0][2]))
    print("Note: ABAC masks are listed by SHOW POLICIES, not in information_schema.column_masks (manual masks only).")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 15 · *(optional)* Rollback - only when `rollback = true`
# MAGIC Removes **everything** this notebook created: the ABAC policy and tag, all row filters and column masks
# MAGIC on the gold tables, the buddy grants and the objects in the `governance` schema (mapping tables,
# MAGIC functions, demo metric view - the empty schema stays, as notebook 01 created it). Your gold data is
# MAGIC untouched. Re-run the notebook with `rollback = false` to govern again. The rollback checks are part of
# MAGIC the summary in step 16.

# COMMAND ----------

if not RUN_ROLLBACK:
    print("rollback = false - keeping the policies.")
else:
    if abac_policy_exists():
        run(f"DROP POLICY {ABAC_POLICY} ON TABLE {C}.{ABAC_TABLE}")
    try:
        if abac_tagged():
            run(f"{alter(ABAC_TABLE)} ALTER COLUMN {ABAC_COLUMN} UNSET TAGS ('{ABAC_TAG}')")
    except Exception as e:
        print(f"Could not remove the tag {ABAC_TAG}: {str(e).splitlines()[0][:200]}")
    for t in ROW_FILTERS:
        run(f"{alter(t)} DROP ROW FILTER")
    for t, column in MASKS:
        run(f"{alter(t)} ALTER COLUMN {column} DROP MASK")
    if BUDDY_EMAIL:
        for schema in BUDDY_SCHEMAS:
            run(f"REVOKE USE SCHEMA, SELECT ON SCHEMA {C}.{schema} FROM `{BUDDY_EMAIL}`")
        run(f"REVOKE USE CATALOG ON CATALOG {C} FROM `{BUDDY_EMAIL}`")
    # Drop exactly the objects of this notebook; the governance schema itself stays as notebook 01 created it.
    run(f"DROP VIEW IF EXISTS {DEMO_MV}")
    for table in ("user_plant_access", "cost_readers", "pii_readers", "break_copy_production_order"):
        run(f"DROP TABLE IF EXISTS {G}.{table}")
    for fn in reversed(OUR_FUNCTIONS):   # policy functions first, the access functions they call last
        run(f"DROP FUNCTION IF EXISTS {G}.{fn}")
    left_f = run(f"SELECT count(*) FROM {C}.information_schema.row_filters", echo=False).first()[0]
    left_m = run(f"SELECT count(*) FROM {C}.information_schema.column_masks", echo=False).first()[0]
    left_o = run(f"""
        SELECT (SELECT count(*) FROM {C}.information_schema.tables
                WHERE table_schema = 'governance'
                  AND table_name IN ('governance_demo_production_order_metrics', 'user_plant_access',
                                     'cost_readers', 'pii_readers'))
             + (SELECT count(*) FROM {C}.information_schema.routines
                WHERE routine_schema = 'governance' AND routine_name IN ({', '.join(f"'{f}'" for f in OUR_FUNCTIONS)}))
    """, echo=False).first()[0]
    check("rollback: no row filters left", left_f == 0, str(left_f))
    check("rollback: no column masks left", left_m == 0, str(left_m))
    check("rollback: no ABAC policy left", not abac_policy_exists())
    check("rollback: no governance objects of this notebook left", left_o == 0, str(left_o))
    restored = as_dict(visibility())
    check("rollback: every plant visible again", all(visible_codes(restored, t) == REFERENCE[t] for t in restored),
          "; ".join(f"{t}: {restored[t][0]} rows" for t in restored))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 16 · Summary
# MAGIC
# MAGIC * Policies live **on the gold tables** - every query path inherits them: SQL, views, metric views, Genie.
# MAGIC * **Who may see what** is a mapping table per dimension (plant, cost, people) - changes are effective
# MAGIC   immediately.
# MAGIC * Govern the **serving layer**; give consumers access to gold only; copies leave governance.
# MAGIC * Keep lookup tables of policies **ungoverned** (no nested policies) - the plant filters read silver - and
# MAGIC   never stack two masks on a column.
# MAGIC
# MAGIC **Next:** notebook 04 - build the Genie Agent. Then come back to step 11 with `ask_genie = true`.

# COMMAND ----------

display(spark.createDataFrame([(c["check"], c["result"], c["detail"]) for c in CHECKS] or [("no checks", "-", "")],
                              "check string, result string, detail string"))
failed = [c for c in CHECKS if c["result"] == "FAIL"]
warned = [c for c in CHECKS if c["result"] == "WARN"]
print(f"{len(CHECKS) - len(failed) - len(warned)} of {len(CHECKS)} checks passed"
      + (f", {len(warned)} warning(s)" if warned else "") + (f", {len(failed)} FAILED" if failed else "") + ".")

# COMMAND ----------

dbutils.notebook.exit(json.dumps({
    "catalog": CATALOG,
    "user_email": USER_EMAIL,
    "plant_codes": PLANT_CODES,
    "cost_access": COST_ACCESS,
    "pii_access": PII_ACCESS,
    "rollback": RUN_ROLLBACK,
    "checks_passed": len([c for c in CHECKS if c["result"] == "PASS"]),
    "checks_total": len(CHECKS),
    "failed": failed,
    "warnings": warned,
    "checks": CHECKS,
    "changes": {state: sum(1 for _, s in CHANGES if s == state) for state in sorted({s for _, s in CHANGES})},
    "changed_objects": [f"{o}: {s}" for o, s in CHANGES if s not in ("unchanged", "exercise")],
    "before": {k: list(v) for k, v in BEFORE.items()},
    "after": {k: list(v) for k, v in AFTER.items()},
}))
