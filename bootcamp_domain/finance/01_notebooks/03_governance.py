# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 03 · Governance — who may see which company, and who may see personal data
# MAGIC
# MAGIC Your finance gold tables are built. Right now **everybody who can read them sees everything**: every legal
# MAGIC entity's invoices and journal postings, the e-mail address of every profit-center manager and the bank
# MAGIC account of every vendor. In this notebook you put Unity Catalog **row filters** and **column masks** on the
# MAGIC gold tables, driven by **your e-mail address**. Because the policies live *on the tables*, every consumer
# MAGIC inherits them: SQL, dashboards, metric views and the **Genie Agent** you build in notebook 04.
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
# MAGIC | 14 | *(optional, advanced)* **ABAC**: tag-driven masking with `CREATE POLICY` | scale governance with governed tags |
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
# MAGIC **Expected result:** after step 7 you only see rows of the company code(s) you mapped yourself to
# MAGIC (default **SE01** = Fjällmark Consumer Goods AB, Sweden), the profit-center managers' e-mail addresses are
# MAGIC masked (`k***@example.com`) and vendor bank accounts are hidden (`NULL`).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | default | meaning |
# MAGIC |---|---|---|
# MAGIC | `catalog` | blank = `cpg_finance_<your short user name>` | the catalog your pipeline wrote to |
# MAGIC | `user_email` | your login (`current_user()`) | whose access you configure in the mapping tables |
# MAGIC | `company_code` | `SE01` | company code(s) that user may see: `SE01`, a list such as `SE01,NO01`, or `ALL` |
# MAGIC | `pii_access` | `false` | `true` = the user may read personal data (manager e-mail, vendor bank account) |
# MAGIC | `buddy_email` | blank | *(optional, step 13)* a colleague to share your governed gold tables with |
# MAGIC | `advanced_abac` | `false` | *(optional, step 14)* run the ABAC section |
# MAGIC | `ask_genie` | `false` | *(optional, step 11)* ask your Genie Agent a question (only after notebook 04) |
# MAGIC | `rollback` | `false` | `true` = remove **everything** this notebook created at the end (step 15) |
# MAGIC
# MAGIC Company codes of Fjällmark: `SE01` Sweden (parent) · `NO01` Norway · `DK01` Denmark · `FI01` Finland ·
# MAGIC `DE01` Germany · `PL01` Poland.

# COMMAND ----------

import hashlib
import json
import textwrap
import time
import unicodedata

current_user = spark.sql("SELECT current_user()").first()[0]

dbutils.widgets.text("catalog", "", "1 Catalog (blank = automatic)")
dbutils.widgets.text("user_email", current_user, "2 User e-mail to configure")
dbutils.widgets.text("company_code", "SE01", "3 Company code(s): SE01 | SE01,NO01 | ALL")
dbutils.widgets.dropdown("pii_access", "false", ["false", "true"], "4 May read personal data")
dbutils.widgets.text("buddy_email", "", "5 (optional) Buddy e-mail")
dbutils.widgets.dropdown("advanced_abac", "false", ["false", "true"], "6 (optional) Run ABAC section")
dbutils.widgets.dropdown("ask_genie", "false", ["false", "true"], "7 (optional) Ask the Genie Agent")
dbutils.widgets.dropdown("rollback", "false", ["false", "true"], "8 Roll back at the end")


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}: the part before '@',
    lower-cased, every character that is not a letter or digit replaced by '_'."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


CATALOG = dbutils.widgets.get("catalog").strip() or f"cpg_finance_{bundle_short_name(current_user)}"
C = f"`{CATALOG}`"   # back-quoted for SQL: catalog names with letters such as å/ä/ö need the quotes
USER_EMAIL = dbutils.widgets.get("user_email").strip() or current_user
COMPANY_CODES = sorted({c.strip().upper() for c in dbutils.widgets.get("company_code").split(",") if c.strip()})
PII_ACCESS = dbutils.widgets.get("pii_access") == "true"
BUDDY_EMAIL = dbutils.widgets.get("buddy_email").strip()
RUN_ABAC = dbutils.widgets.get("advanced_abac") == "true"
ASK_GENIE = dbutils.widgets.get("ask_genie") == "true"
RUN_ROLLBACK = dbutils.widgets.get("rollback") == "true"

DOMAINS = ["finance"]     # the gold schemas of this sample
MAIN_DOMAIN = "finance"

# Fixed names used across the bootcamp samples (an admin creates these account groups; the sample works without them).
ADMIN_GROUP = "cpg_bootcamp_admins"              # members bypass every policy (instructors)
PARTICIPANT_GROUP = "cpg_bootcamp_participants"  # used in the GRANT examples
BUDDY_SCHEMAS = tuple(DOMAINS)                   # gold schemas shared with the buddy (step 13)

# The gold tables that carry a company_code_id column and get the company row filter.
# In production you would protect every finance fact with company_code_id (ap_invoice, ar_payment,
# cogs_allocation, ...) - extending this list is all it takes.
ROW_FILTERED_TABLES = ["finance.ar_invoice", "finance.journal_entry_line"]
# Personal data in the finance model (columns tagged dbx_pii_* / dbx_confidential in 02_model_tags/finance.json)
# and the mask function each one gets. Chosen because they identify or pay a PERSON:
#   profit_center.responsible_person_email   - the e-mail of a named manager
#   ap_invoice.vendor_bank_account_code       - the vendor's bank account (sole traders are people too)
# The company's OWN bank accounts (ar_payment / ap_payment.bank_account_code) and the plant/office contact
# data of company_code and profit_center are business data, not personal data - they stay readable.
# profit_center.responsible_person_name is left unmasked on purpose: step 14 (ABAC) masks it through a tag.
MASKS = {
    ("finance.profit_center", "responsible_person_email"): "mask_email",
    ("finance.ap_invoice", "vendor_bank_account_code"): "mask_bank_account",
}

print(f"You are logged in as : {current_user}")
print(f"Catalog              : {CATALOG}")
print(f"Configure access for : {USER_EMAIL}")
print(f"  company code(s)    : {', '.join(COMPANY_CODES)}")
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
    """The silver table a gold table is built from: finance.ar_invoice -> silver.finance_ar_invoice."""
    return "silver." + table.replace(".", "_")


# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Pre-flight check
# MAGIC The notebook needs the gold tables from the pipeline (job `cpg_finance_job`) and their silver sources:
# MAGIC the self-checks use silver as the ungoverned reference of *which companies have data*. It also checks that
# MAGIC every column a policy goes on exists. If something is missing, run the pipeline job first.

# COMMAND ----------

ABAC_TABLE, ABAC_COLUMN, ABAC_TAG, ABAC_POLICY = ("finance.profit_center", "responsible_person_name", "class.name",
                                                  "mask_tagged_names")
masked_tables = sorted({t for t, _ in MASKS})
needed = ROW_FILTERED_TABLES + masked_tables + ["finance.company_code"] + [silver_of(t) for t in ROW_FILTERED_TABLES]
TABLE_TYPES.update({f"{r.table_schema}.{r.table_name}": r.table_type for r in run(f"""
    SELECT table_schema, table_name, table_type
    FROM {C}.information_schema.tables
    WHERE table_schema IN ('finance', 'silver')
""", echo=False).collect()})
missing = [t for t in needed if t not in TABLE_TYPES]
for t in needed:
    print(f"  {t:35s} {TABLE_TYPES.get(t, 'MISSING')}")
if missing:
    raise Exception(f"Missing in catalog {CATALOG}: {missing}. Run the pipeline job (cpg_finance_job) first, "
                    f"or set the 'catalog' widget to the catalog your pipeline wrote to.")
not_mv = [t for t in ROW_FILTERED_TABLES + masked_tables if TABLE_TYPES[t] != "MATERIALIZED_VIEW"]
if not_mv:
    print(f"NOTE: expected pipeline materialized views, found other types for {not_mv} - alter() adapts the keyword.")

# Every column a policy goes on must exist (one information_schema query for all of them).
needed_columns = [(t, "company_code_id") for t in ROW_FILTERED_TABLES] + list(MASKS) + [(ABAC_TABLE, ABAC_COLUMN)]
COLUMN_TYPES = {(f"{r.table_schema}.{r.table_name}", r.column_name): r.full_data_type for r in run(f"""
    SELECT table_schema, table_name, column_name, full_data_type
    FROM {C}.information_schema.columns
    WHERE table_schema = 'finance'
      AND table_name IN ({', '.join(sorted({f"'{t.split('.')[1]}'" for t, _ in needed_columns}))})
""", echo=False).collect()}
missing_columns = [f"{t}.{c}" for t, c in needed_columns if (t, c) not in COLUMN_TYPES]
if missing_columns:
    raise Exception(f"Columns missing in catalog {CATALOG}: {missing_columns}. Re-run the pipeline job.")

companies = {r.code: r.company_code_id for r in run(
    f"SELECT code, company_code_id FROM {C}.finance.company_code ORDER BY code", echo=False).collect()}
print(f"\nCompany codes in finance.company_code: {', '.join(companies)}")
unknown = [c for c in COMPANY_CODES if c != "ALL" and c not in companies]
if unknown:
    raise ValueError(f"Unknown company code(s) {unknown}. Use one of {list(companies)} or ALL.")

# Reference for the self-checks: which company codes HAVE rows in each governed table. Read from the
# ungoverned silver layer (one query), so it does not depend on the policies (or on a previous run of this notebook).
REFERENCE = {t: set() for t in ROW_FILTERED_TABLES}
for r in run("\nUNION ALL\n".join(f"""
    SELECT DISTINCT '{t}' AS governed_table, cc.code FROM {C}.{silver_of(t)} AS s
    JOIN {C}.finance.company_code AS cc ON cc.company_code_id = s.company_code_id""" for t in ROW_FILTERED_TABLES),
             echo=False).collect():
    REFERENCE[r.governed_table].add(r.code)
for t, codes in REFERENCE.items():
    print(f"  companies with data in {t:28s}: {', '.join(sorted(codes))}")

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
# MAGIC * **visibility** - for each governed table: how many rows you see and which company codes they belong to
# MAGIC * **personal-data sample** - the first profit centers with their manager, and the first vendor invoices with
# MAGIC   the vendor's bank account

# COMMAND ----------

def visibility() -> list:
    """Rows and company codes you can see in each governed table (runs as YOU). Displays and returns the rows."""
    parts = [f"""
      SELECT '{t}' AS governed_table, count(*) AS visible_rows,
             array_join(array_sort(collect_set(cc.code)), ', ') AS visible_company_codes
      FROM {C}.{t} AS t
      LEFT JOIN {C}.finance.company_code AS cc ON cc.company_code_id = t.company_code_id""" for t in ROW_FILTERED_TABLES]
    return display_rows(run("\nUNION ALL".join(parts) + "\nORDER BY governed_table", echo=False))


def pii_samples():
    """Display the personal-data samples; returns (profit-center rows, vendor-invoice rows) for the checks."""
    people = display_rows(run(f"""
        SELECT code, name, responsible_person_name, responsible_person_email
        FROM {C}.finance.profit_center
        ORDER BY code
        LIMIT 5
    """, echo=False))
    banks = display_rows(run(f"""
        SELECT ap_invoice_id, vendor_invoice_number, supplier_id, vendor_bank_account_code
        FROM {C}.finance.ap_invoice
        ORDER BY ap_invoice_id
        LIMIT 5
    """, echo=False))
    return people, banks


def check_pii(label: str, samples, pii: bool) -> None:
    """The e-mail is masked (a***@...) and the bank account NULL - or both readable for PII readers."""
    people, banks = samples
    email = next((r.responsible_person_email for r in people if r.responsible_person_email), None)
    if email:
        check(f"{label}finance.profit_center.responsible_person_email {'readable' if pii else 'masked'}",
              ("***@" in email) != pii, email)
    if banks:
        bank = banks[0].vendor_bank_account_code
        check(f"{label}finance.ap_invoice.vendor_bank_account_code {'readable' if pii else 'hidden'}",
              (bank is None) != pii, str(bank))


def as_dict(rows):
    return {r.governed_table: (r.visible_rows, r.visible_company_codes) for r in rows}


already = run(f"SELECT count(*) FROM {C}.information_schema.row_filters", echo=False).first()[0]
if already:
    print(f"NOTE: {already} row filter(s) are already attached (this is a re-run), so 'before' is already governed.")
BEFORE = as_dict(visibility())
pii_samples()

# COMMAND ----------

# MAGIC %md
# MAGIC **What you see:** all six company codes in the AR invoices and the journal lines, the e-mail address of
# MAGIC every profit-center manager and every vendor's bank account. Anyone with `SELECT` on these tables - and any
# MAGIC Genie Agent built on them - sees exactly the same.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Mapping tables: *who may see what* is data
# MAGIC
# MAGIC | table | columns | meaning |
# MAGIC |---|---|---|
# MAGIC | `governance.user_company_access` | `user_email`, `company_code` | the user may see rows of that company code (`ALL` = every company) |
# MAGIC | `governance.pii_readers` | `user_email` | the user may read personal data in clear text |
# MAGIC
# MAGIC Besides you, we seed three **fictional personas** so you can reason about typical access patterns.
# MAGIC Nobody can log in as them; in step 10 you will *become* them by copying their mapping to your e-mail.
# MAGIC
# MAGIC | persona | e-mail | company codes | PII | why |
# MAGIC |---|---|---|---|---|
# MAGIC | Anna Svensson, finance analyst Sweden | `anna.svensson@example.com` | SE01 | no | analyses the Swedish entity's revenue and receivables |
# MAGIC | Lukas Becker, financial controller Germany | `lukas.becker@example.com` | DE01 | **yes** | chases overdue German receivables and checks vendor bank details before the payment run |
# MAGIC | Group CFO | `cfo@example.com` | ALL | no | sees every entity - but **not** personal data |
# MAGIC
# MAGIC Row access and PII access are **independent** dimensions - the CFO sees all rows but masked personal
# MAGIC data, the German controller sees one entity but clear-text bank accounts.
# MAGIC
# MAGIC The notebook reads both mapping tables **once** and only writes a row that is missing or different.

# COMMAND ----------

G = f"{C}.governance"
run(f"CREATE SCHEMA IF NOT EXISTS {G} COMMENT 'Governance: access-mapping tables and policy functions (notebook 03)'")
run(f"""
    CREATE TABLE IF NOT EXISTS {G}.user_company_access (
      user_email   STRING NOT NULL COMMENT 'User e-mail exactly as current_user() returns it (compared case-insensitively)',
      company_code STRING NOT NULL COMMENT 'Company code the user may see (finance.company_code.code) or ALL'
    )
    COMMENT 'Row-level access: which company codes each user may see. Read by governance.has_company_access().'
""")
run(f"""
    CREATE TABLE IF NOT EXISTS {G}.pii_readers (
      user_email STRING NOT NULL COMMENT 'User e-mail exactly as current_user() returns it (compared case-insensitively)'
    )
    COMMENT 'Users who may read personal data in clear text. Read by governance.can_read_pii().'
""")


def read_mapping() -> dict:
    """Current mapping of every user in ONE query: lower(e-mail) -> [set of company codes, may read PII]."""
    mapping = {}
    for r in run(f"""
        SELECT lower(user_email) AS email, company_code FROM {G}.user_company_access
        UNION ALL
        SELECT lower(user_email) AS email, CAST(NULL AS STRING) AS company_code FROM {G}.pii_readers
    """, echo=False).collect():
        entry = mapping.setdefault(r.email, [set(), False])
        if r.company_code is None:
            entry[1] = True
        else:
            entry[0].add(r.company_code)
    return mapping


MAPPING = read_mapping()
PERSONA_ROWS = {   # e-mail -> (company codes, PII)
    "anna.svensson@example.com": (["SE01"], False),
    "lukas.becker@example.com": (["DE01"], True),
    "cfo@example.com": (["ALL"], False),
}

# Fictional personas (idempotent: only rows that are missing are inserted, nothing else is touched).
missing_codes = [(e, c) for e, (codes, _) in PERSONA_ROWS.items() for c in codes
                 if c not in MAPPING.get(e, [set(), False])[0]]
missing_pii = [e for e, (_, pii) in PERSONA_ROWS.items() if pii and not MAPPING.get(e, [set(), False])[1]]
if missing_codes:
    run(f"INSERT INTO {G}.user_company_access (user_email, company_code) VALUES "
        + ", ".join(f"('{e}', '{c}')" for e, c in missing_codes))
if missing_pii:
    run(f"INSERT INTO {G}.pii_readers (user_email) VALUES " + ", ".join(f"('{e}')" for e in missing_pii))
for e, c in missing_codes:
    MAPPING.setdefault(e, [set(), False])[0].add(c)
for e in missing_pii:
    MAPPING.setdefault(e, [set(), False])[1] = True
print("unchanged: persona rows" if not (missing_codes or missing_pii) else
      f"persona rows added: {len(missing_codes)} company row(s), {len(missing_pii)} PII row(s)")
changed("persona mapping rows", "created" if missing_codes or missing_pii else "unchanged")


def set_access(email: str, codes: list, pii: bool, echo: bool = True):
    """Make the mapping rows of one user equal to (company codes, PII flag). Only the table that differs is
    rewritten - a re-run changes nothing. Works on the mapping read once above (MAPPING) and keeps it current."""
    key = email.lower()
    have_codes, have_pii = MAPPING.get(key, [set(), False])
    if have_codes == set(codes) and have_pii == pii:
        print(f"unchanged: mapping of {email} (company codes {sorted(codes)}, PII {pii})")
        changed(f"mapping {email}", "unchanged")
        return
    changed(f"mapping {email}", "updated")
    if have_codes != set(codes):
        run(f"DELETE FROM {G}.user_company_access WHERE lower(user_email) = lower(:email)", {"email": email}, echo)
        if codes:
            values = ", ".join(f"(:email, :code{i})" for i in range(len(codes)))
            run(f"INSERT INTO {G}.user_company_access (user_email, company_code) VALUES {values}",
                {"email": email, **{f"code{i}": c for i, c in enumerate(codes)}}, echo)
    if have_pii != pii:
        if pii:
            run(f"INSERT INTO {G}.pii_readers (user_email) VALUES (:email)", {"email": email}, echo)
        else:
            run(f"DELETE FROM {G}.pii_readers WHERE lower(user_email) = lower(:email)", {"email": email}, echo)
    MAPPING[key] = [set(codes), pii]


# The user from the widgets.
set_access(USER_EMAIL, COMPANY_CODES, PII_ACCESS)

print("Mapping now (the rows read above plus the changes just written):")
display(spark.createDataFrame(
    [(e, ", ".join(sorted(codes)), pii) for e, (codes, pii) in sorted(MAPPING.items())],
    "user_email string, company_codes string, may_read_pii boolean"))

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
# MAGIC | `has_company_access(company_code)` | access | TRUE if you are mapped to that code (or to `ALL`) |
# MAGIC | `can_read_pii()` | access | TRUE if you are in `pii_readers` |
# MAGIC | `company_row_filter(company_code_id)` | **row filter** | translates the technical `company_code_id` to the business key `code` via `finance.company_code`, then asks `has_company_access` |
# MAGIC | `mask_email`, `mask_name` | **column masks** | the real value for PII readers, a masked value for everybody else (`mask_name` is used by the ABAC policy in step 14) |
# MAGIC | `mask_bank_account` | **column mask** | the real account for PII readers, `NULL` for everybody else (a BIGINT cannot carry `***`) |
# MAGIC
# MAGIC **The rule that keeps this working** (Unity Catalog does not support *nested* policies - a policy function
# MAGIC may not read a table that itself has a row filter or column mask, the query fails with
# MAGIC `UNSUPPORTED_NESTED_ROW_OR_COLUMN_ACCESS_POLICY`): `finance.company_code` and the mapping tables are
# MAGIC **never** governed themselves. You will *see* the nested-policy error in step 12.
# MAGIC
# MAGIC Masks keep **analytical value** where possible: the e-mail keeps its domain, so you can still count
# MAGIC managers per e-mail domain.

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


# --- access functions -------------------------------------------------------------------------------
ensure_function(
    "is_bootcamp_admin", "", "BOOLEAN",
    f"Access function: TRUE for members of the account group {ADMIN_GROUP} (instructors bypass all policies).",
    f"is_account_group_member('{ADMIN_GROUP}')")
ensure_function(
    "has_company_access", "company_code STRING", "BOOLEAN",
    "Access function: TRUE if the current user may see rows of this company code (governance.user_company_access, ALL = every company).",
    f"""
    {G}.is_bootcamp_admin()
    OR EXISTS (
         SELECT 1
         FROM {G}.user_company_access AS a
         WHERE lower(a.user_email) = lower(current_user())
           AND a.company_code IN ('ALL', has_company_access.company_code)
       )""")
ensure_function(
    "can_read_pii", "", "BOOLEAN",
    "Access function: TRUE if the current user may read personal data in clear text (governance.pii_readers).",
    f"""
    {G}.is_bootcamp_admin()
    OR EXISTS (SELECT 1 FROM {G}.pii_readers AS r WHERE lower(r.user_email) = lower(current_user()))""")

# --- row filter ------------------------------------------------------------------------------------
COMPANY_FILTER = dict(
    name="company_row_filter", params="row_company_code_id BIGINT", returns="BOOLEAN",
    comment="Row filter for tables with company_code_id: resolves the id to finance.company_code.code and checks has_company_access().",
    body=f"""
    EXISTS (
      SELECT 1
      FROM {C}.finance.company_code AS cc
      WHERE cc.company_code_id = row_company_code_id
        AND {G}.has_company_access(cc.code)
    )""")
ensure_function(**COMPANY_FILTER)

# --- column masks ----------------------------------------------------------------------------------
ensure_function(
    "mask_email", "email STRING", "STRING",
    "Column mask: clear text for PII readers, otherwise first letter + domain (a***@example.com).",
    f"""
    CASE WHEN {G}.can_read_pii() OR email IS NULL THEN email
         ELSE concat(left(email, 1), '***@', substring_index(email, '@', -1)) END""")
ensure_function(
    "mask_name", "name STRING", "STRING",
    "Column mask: clear text for PII readers, otherwise the first letter only (A****).",
    f"""
    CASE WHEN {G}.can_read_pii() OR name IS NULL THEN name
         ELSE concat(left(name, 1), '****') END""")
ensure_function(
    "mask_bank_account", "account BIGINT", "BIGINT",
    "Column mask: clear text for PII readers, otherwise NULL (a numeric account cannot be partly masked).",
    f"CASE WHEN {G}.can_read_pii() THEN account ELSE CAST(NULL AS BIGINT) END")

display(run(f"""
    SELECT company_code_id, code, name, {G}.has_company_access(code) AS i_may_see_it
    FROM {C}.finance.company_code
    ORDER BY code
"""))
display(run(f"SELECT {G}.can_read_pii() AS i_may_read_pii"))

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
# MAGIC policies on gold do not change what the pipeline writes. Silver stays ungoverned *and closed*: consumers
# MAGIC only get access to gold (step 12).
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


for t in ROW_FILTERED_TABLES:
    ensure_row_filter(t, "company_row_filter", "company_code_id")

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
after_pii = pii_samples()


def expected_codes(codes, table):
    """The company codes you should see in a table: the codes you are mapped to that have data there."""
    allowed = set(companies) if "ALL" in codes else set(codes)
    return allowed & REFERENCE[table]


def visible_codes(result, table):
    return {c.strip() for c in (result[table][1] or "").split(",") if c.strip()}


def visibility_report(result, codes, table):
    """(ok, text): EXACTLY the expected company codes are visible - not more (the filter works) and not
    fewer (it does not hide too much) - and there are rows whenever a company is expected."""
    expected, seen, rows = expected_codes(codes, table), visible_codes(result, table), result[table][0]
    ok = seen == expected and (rows > 0) == bool(expected)
    return ok, f"{table}: expected [{', '.join(sorted(expected))}] -> visible {rows} rows [{', '.join(sorted(seen))}]"


if IS_ADMIN:
    print("Admin: policies are bypassed, skipping the after-checks.")
elif USER_EMAIL.lower() == current_user.lower():
    for t in ROW_FILTERED_TABLES:
        ok, text = visibility_report(AFTER, COMPANY_CODES, t)
        check(f"{t}: exactly the expected company codes visible", ok, f"before {BEFORE[t][0]} rows; {text}")
    check_pii("", after_pii, PII_ACCESS)

# COMMAND ----------

# MAGIC %md
# MAGIC **What changed:** only the company code(s) you mapped yourself to are left in the AR invoices and the
# MAGIC journal lines, the managers' e-mail addresses are masked and the vendor bank accounts are `NULL` (unless
# MAGIC `pii_access = true`). Notice that you did **not** get an error - hidden rows simply do not exist for you.
# MAGIC
# MAGIC **Discussion:** `finance.ap_invoice` and `finance.profit_center` also carry a `company_code_id`, but have no
# MAGIC row filter here - every analyst still sees every entity's payables (with hidden bank accounts). Adding
# MAGIC them to `ROW_FILTERED_TABLES` is all it takes; the function is the same.

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
display(run(f"DESCRIBE TABLE EXTENDED {C}.finance.ar_invoice").filter("col_name IN ('Row Filter', 'Type', 'Owner')"))

check("row filters attached", n_filters >= len(ROW_FILTERED_TABLES), f"{n_filters} row filters")
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
    ("Lukas Becker - financial controller Germany, clear-text personal data", ["DE01"], True),
    ("Group CFO - every entity, no personal data", ["ALL"], False),
]
# Remember YOUR current mapping first: when user_email is a colleague, the rows you gave yourself in an earlier
# run (for example SE01) must come back exactly as they were - an unmapped user sees 0 governed rows.
my_mapping = MAPPING.get(current_user.lower(), [set(), False])
MY_CODES_BEFORE, MY_PII_BEFORE = sorted(my_mapping[0]), my_mapping[1]
IN_EXERCISE = True
try:
    for title, codes, pii in PERSONAS:
        print("=" * 100 + f"\nYou are now: {title}  (company codes {codes}, PII {pii})\n" + "=" * 100)
        set_access(current_user, codes, pii)
        got = as_dict(visibility())
        samples = pii_samples()
        if not IS_ADMIN:
            reports = [visibility_report(got, codes, t) for t in ROW_FILTERED_TABLES]
            check(f"persona '{title}': exactly the rows of {codes} visible",
                  all(ok for ok, _ in reports), "; ".join(text for _, text in reports))
            check_pii(f"persona '{title}': ", samples, pii)
finally:
    print("Restoring the mapping from the widgets ...")
    if USER_EMAIL.lower() != current_user.lower():
        # You configured a colleague: put YOUR rows back exactly as they were before section 10.
        set_access(current_user, MY_CODES_BEFORE, MY_PII_BEFORE)
        print(f"Your own mapping restored: company codes {MY_CODES_BEFORE or 'none'}, PII {MY_PII_BEFORE}")
    set_access(USER_EMAIL, COMPANY_CODES, PII_ACCESS)
    IN_EXERCISE = False

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11 · Metric views and Genie inherit the policies
# MAGIC
# MAGIC A metric view (or a plain view, a dashboard, a Genie Agent) reads the governed gold tables **as the
# MAGIC person asking**, so the row filters and masks apply automatically. We create a tiny demo metric view in
# MAGIC the `governance` schema and query it. The curated metric views of the sample (e.g.
# MAGIC `finance.receivables_metrics`, `finance.net_revenue_metrics`) behave the same way.

# COMMAND ----------

DEMO_MV = f"{G}.governance_demo_ar_metrics"
demo_yaml = textwrap.dedent(f"""
    version: 1.1
    comment: "Governance demo (notebook 03): AR invoices by company code. Inherits the row filter of finance.ar_invoice."
    source: "{C}.finance.ar_invoice"
    joins:
      - name: company
        source: "{C}.finance.company_code"
        on: source.company_code_id = company.company_code_id
    dimensions:
      - name: company_code
        expr: company.code
    measures:
      - name: invoice_count
        expr: COUNT(1)
      - name: open_balance_local_currency
        expr: SUM(outstanding_balance)
""").strip()
demo_fp = hashlib.sha1(demo_yaml.encode("utf-8")).hexdigest()[:10]
demo_yaml = demo_yaml.replace('finance.ar_invoice."', f'finance.ar_invoice. [def {demo_fp}]"', 1)
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
    SELECT company_code, MEASURE(invoice_count) AS invoices, MEASURE(open_balance_local_currency) AS open_balance
    FROM {DEMO_MV}
    GROUP BY company_code
    ORDER BY company_code
"""))
if not IS_ADMIN and USER_EMAIL.lower() == current_user.lower():
    mv_codes, mv_invoices = {r.company_code for r in mv_rows}, sum(r.invoices for r in mv_rows)
    check("metric view inherits the row filter (same codes and invoice count as the table)",
          mv_codes == expected_codes(COMPANY_CODES, "finance.ar_invoice") and mv_invoices == AFTER["finance.ar_invoice"][0],
          f"codes {sorted(mv_codes)}, {mv_invoices} invoices (table: {AFTER['finance.ar_invoice'][0]} visible rows)")

display(run(f"""
    SELECT table_schema, table_name
    FROM {C}.information_schema.tables
    WHERE table_type = 'METRIC_VIEW'
    ORDER BY table_schema, table_name
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Ask your Finance Analyst Genie Agent *(only when `ask_genie = true`)*
# MAGIC You build the agent **Fjällmark Finance Analyst** in notebook 04. When you come back here afterwards, set
# MAGIC the widget `ask_genie` to `true` and run this cell: it asks the agent a question through the Genie
# MAGIC Conversation API - the answer only contains your company codes. If the agent does not exist yet, the cell
# MAGIC just tells you so.

# COMMAND ----------

AGENT_TITLE = f"Fjällmark Finance Analyst ({CATALOG})"   # the title notebook 04 gives the agent


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
                                             "How many AR invoices are there per company code? Show the company code.")
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
                expected = expected_codes(COMPANY_CODES, "finance.ar_invoice")
                leaked = sorted(c for c in companies if c not in expected and c in answer_text)
                shown = sorted(c for c in expected if c in answer_text)
                check("Genie answer contains no company code you may not see", not leaked,
                      f"unexpected: {leaked}" if leaked else f"codes in the answer: {shown}")
                check("Genie answer shows your company codes", shown == sorted(expected),
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
# MAGIC | B | query **silver** instead of gold | you see **everything** | silver is not governed: consumers get `SELECT` on **gold only** |
# MAGIC | C | filter on a masked value / ask for another company directly | **0 rows**, no error | the mask is applied *before* your `WHERE`; hidden rows don't exist for you |
# MAGIC | D | (engineer) let a policy read another governed table | query **fails** with `UNSUPPORTED_NESTED_ROW_OR_COLUMN_ACCESS_POLICY` | keep lookup tables ungoverned - that is why `finance.company_code` has no policy |

# COMMAND ----------

# MAGIC %md
# MAGIC ### A · Copy the table

# COMMAND ----------

run(f"CREATE OR REPLACE TABLE {G}.break_copy_ar_invoice AS SELECT * FROM {C}.finance.ar_invoice")
run(f"CREATE OR REPLACE TABLE {G}.break_copy_profit_center AS SELECT * FROM {C}.finance.profit_center")
copy_rows = display_rows(run(f"""
    SELECT 'copy of finance.ar_invoice' AS what, count(*) AS rows_in_copy,
           array_join(array_sort(collect_set(cc.code)), ', ') AS company_codes_in_copy
    FROM {G}.break_copy_ar_invoice AS t
    LEFT JOIN {C}.finance.company_code AS cc ON cc.company_code_id = t.company_code_id
"""))[0]
display(run(f"SELECT code, responsible_person_name, responsible_person_email FROM {G}.break_copy_profit_center "
            "ORDER BY code LIMIT 3"))
copy_policies = run(f"""
    SELECT count(*) FROM {C}.information_schema.row_filters
    WHERE table_schema = 'governance' AND table_name = 'break_copy_ar_invoice'
""", echo=False).first()[0]
print(f"Row filters on the copy: {copy_policies}  <- the copy is NOT governed")
if not IS_ADMIN and USER_EMAIL.lower() == current_user.lower():
    copy_codes = {c.strip() for c in (copy_rows.company_codes_in_copy or "").split(",") if c.strip()}
    check("A: CTAS copies exactly the rows you can see",
          copy_codes == expected_codes(COMPANY_CODES, "finance.ar_invoice")
          and copy_rows.rows_in_copy == AFTER["finance.ar_invoice"][0],
          f"{copy_rows.rows_in_copy} rows {sorted(copy_codes)} (visible in the table: {AFTER['finance.ar_invoice'][0]} rows)")
    check("A: the copy carries no row filter", copy_policies == 0)
run(f"DROP TABLE IF EXISTS {G}.break_copy_ar_invoice")
run(f"DROP TABLE IF EXISTS {G}.break_copy_profit_center")
print("Copies dropped.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### B · Go around gold: query silver
# MAGIC You **own** this catalog, so you can read silver. A business user should not be able to.

# COMMAND ----------

silver = display_rows(run(f"""
    SELECT cc.code AS company_code, count(*) AS invoices_in_silver
    FROM {C}.silver.finance_ar_invoice AS s
    LEFT JOIN {C}.finance.company_code AS cc ON cc.company_code_id = s.company_code_id
    GROUP BY cc.code
    ORDER BY cc.code
"""))
check("B: silver is NOT governed (you see every company there)",
      {r.company_code for r in silver} >= REFERENCE["finance.ar_invoice"] or IS_ADMIN,
      f"{len(silver)} company codes in silver")

print("""
Lesson: grant business users access to the GOLD schemas only. For example (not executed here):

  GRANT USE CATALOG ON CATALOG {c} TO `{g}`;
  GRANT USE SCHEMA, SELECT ON SCHEMA {c}.finance TO `{g}`;
  -- nothing on landing, bronze, silver or governance.
  -- EXECUTE on the policy functions is NOT needed: Unity Catalog evaluates the policies for the reader,
  -- with the rights of the table owner.
  -- Use SHOW GRANTS ON SCHEMA {c}.silver to verify that no consumer group has access.
""".format(c=C, g=PARTICIPANT_GROUP))

# COMMAND ----------

# MAGIC %md
# MAGIC ### C · Probe a masked value, or ask for another company directly

# COMMAND ----------

real_email = run(f"SELECT responsible_person_email FROM {C}.silver.finance_profit_center "
                 "WHERE responsible_person_email IS NOT NULL LIMIT 1", echo=False).first()[0]
probe = display_rows(run(f"SELECT count(*) AS matches FROM {C}.finance.profit_center "
                         "WHERE responsible_person_email = :email", {"email": real_email}))
other = [c for c in companies if "ALL" not in COMPANY_CODES and c not in COMPANY_CODES][:1]
if other:
    direct = display_rows(run(f"SELECT count(*) AS rows_of_{other[0].lower()} FROM {C}.finance.ar_invoice "
                              "WHERE company_code_id = :id", {"id": companies[other[0]]}))
if not IS_ADMIN and USER_EMAIL.lower() == current_user.lower():
    if not PII_ACCESS:
        check("C: filtering on a masked column finds nothing", probe[0][0] == 0)
    if other:
        check(f"C: asking for {other[0]} directly returns 0 rows (no error)", direct[0][0] == 0)

# COMMAND ----------

# MAGIC %md
# MAGIC ### D · (engineer) Nested policies are not supported
# MAGIC Imagine an engineer "improves" the company filter to look the company up in the **governed**
# MAGIC `finance.ar_invoice` instead of the ungoverned `finance.company_code`. We do that for a moment, query the
# MAGIC journal lines, and restore the original filter - whatever happens.

# COMMAND ----------

try:
    run(f"""
        CREATE OR REPLACE FUNCTION {G}.company_row_filter(row_company_code_id BIGINT)
        RETURNS BOOLEAN
        RETURN EXISTS (SELECT 1 FROM {C}.finance.ar_invoice AS a WHERE a.company_code_id = row_company_code_id)
    """)
    try:
        run(f"SELECT count(*) FROM {C}.finance.journal_entry_line").collect()
        check("D: nested policy is rejected", False, "query unexpectedly succeeded")
    except Exception as e:
        msg = str(e).split("\n")[0]
        print(f"Expected error:\n  {msg[:400]}")
        check("D: nested policy is rejected", "UNSUPPORTED_NESTED_ROW_OR_COLUMN_ACCESS_POLICY" in str(e), msg[:120])
finally:
    IN_EXERCISE = True
    ensure_function(**COMPANY_FILTER, force=True)   # put the company_code-based filter from step 6 back
    IN_EXERCISE = False
    lines = run(f"SELECT count(*) FROM {C}.finance.journal_entry_line", echo=False).first()[0]
    print(f"Restored. Journal lines visible again: {lines}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 13 · *(optional)* Share with a buddy - test as a different user
# MAGIC
# MAGIC The real test of governance is a **second person**. Put a colleague's e-mail into the `buddy_email`
# MAGIC widget and re-run this cell. It grants your buddy `USE CATALOG` on your catalog and `USE SCHEMA` + `SELECT`
# MAGIC on your **gold** schema `finance` only (that covers the gold tables *and* the metric views in it), and maps
# MAGIC them to **DE01** without PII. Nothing on `silver` or `governance` is granted: the row filters and masks run
# MAGIC with the rights of the table owner (you), so the reader needs neither the mapping tables nor `EXECUTE` on the
# MAGIC functions. Then ask your buddy to run in the SQL editor (they also need **CAN USE** on a SQL warehouse):
# MAGIC
# MAGIC ```sql
# MAGIC SELECT * FROM <your catalog>.finance.ar_invoice LIMIT 10;                       -- expected: only DE01 rows
# MAGIC SELECT count(*) FROM <your catalog>.finance.journal_entry_line;                 -- expected: only DE01 lines
# MAGIC SELECT responsible_person_email FROM <your catalog>.finance.profit_center;      -- expected: masked
# MAGIC SELECT MEASURE(dso_days) FROM <your catalog>.finance.receivables_metrics;       -- expected: DE01 only
# MAGIC SELECT * FROM <your catalog>.silver.finance_ar_invoice LIMIT 10;                -- expected: PERMISSION_DENIED
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
    set_access(BUDDY_EMAIL, ["DE01"], False)
    display(run(f"SHOW GRANTS {principal} ON SCHEMA {C}.finance"))
    print("To undo:\n" + "".join(f"  REVOKE USE SCHEMA, SELECT ON SCHEMA {C}.{s} FROM {principal};\n"
                                 for s in BUDDY_SCHEMAS)
          + f"  REVOKE USE CATALOG ON CATALOG {C} FROM {principal};\n"
          + f"  DELETE FROM {G}.user_company_access WHERE user_email = '{BUDDY_EMAIL}';")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 14 · *(optional, advanced)* ABAC - tag-driven masking with `CREATE POLICY`
# MAGIC
# MAGIC Manual masks are attached column by column. **Attribute-based access control (ABAC)** attaches one
# MAGIC **policy** to a catalog, schema or table that masks *every column carrying a governed tag* - new tables
# MAGIC and columns are covered as soon as they are tagged.
# MAGIC
# MAGIC We use the system governed tag `class.name` on a column that is **not** masked yet:
# MAGIC `finance.profit_center.responsible_person_name` (the name of the profit-center manager - personal data).
# MAGIC The policy reuses our `mask_name` function, so PII readers still see clear text.
# MAGIC
# MAGIC **Never put a manual mask and an ABAC mask on the same column**: the column then has two masks, every
# MAGIC query fails with `MULTIPLE_MASKS` - and so does the next pipeline refresh. That is why the policy is
# MAGIC scoped to one table here, and **before** tagging anything the cell checks that no column of that table
# MAGIC the policy would cover (`responsible_person_name` itself, or a column already tagged `class.name`) has a
# MAGIC manual mask. If one does, the cell explains it and skips the exercise. (In production you would attach the
# MAGIC policy to the schema or catalog and use ABAC *instead of* manual masks.)
# MAGIC
# MAGIC Set the widget `advanced_abac` to `true` to run it. You need the **ASSIGN** permission on the governed
# MAGIC tag `class.name` (an account admin grants it).

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
    # The policy will mask responsible_person_name plus every column of this table tagged class.name.
    # None of them may already have a manual mask - check BEFORE tagging anything.
    collisions = run(f"""
        SELECT column_name, mask_name
        FROM {C}.information_schema.column_masks
        WHERE table_schema = '{ABAC_SCHEMA}' AND table_name = '{ABAC_TABLE_NAME}'
          AND (column_name = '{ABAC_COLUMN}'
               OR column_name IN (SELECT column_name FROM {C}.information_schema.column_tags
                                  WHERE schema_name = '{ABAC_SCHEMA}' AND table_name = '{ABAC_TABLE_NAME}'
                                    AND tag_name = '{ABAC_TAG}'))
    """).collect()
    check(f"ABAC: no manual mask on a column the policy would cover ({ABAC_TABLE})", not collisions,
          ", ".join(f"{r.column_name} has mask {r.mask_name}" for r in collisions) or "none")
    if collisions:
        print(f"Skipping the ABAC exercise: an ABAC mask on top of a manual mask would make every query on "
              f"{ABAC_TABLE} fail with MULTIPLE_MASKS. Remove the manual mask first, e.g.\n"
              + "\n".join(f"  {alter(ABAC_TABLE)} ALTER COLUMN {r.column_name} DROP MASK;" for r in collisions))

if RUN_ABAC and not collisions:
    try:
        already_tagged = run(f"""
            SELECT 1 FROM {C}.information_schema.column_tags
            WHERE schema_name = '{ABAC_SCHEMA}' AND table_name = '{ABAC_TABLE_NAME}'
              AND column_name = '{ABAC_COLUMN}' AND tag_name = '{ABAC_TAG}'""", echo=False).count() > 0
        if already_tagged:
            print(f"unchanged: tag {ABAC_TAG} on {ABAC_TABLE}.{ABAC_COLUMN}")
            changed("ABAC tag", "unchanged")
        else:
            run(f"{alter(ABAC_TABLE)} ALTER COLUMN {ABAC_COLUMN} SET TAGS ('{ABAC_TAG}')")
            changed("ABAC tag", "created")
        tagged_ok = True
    except Exception as e:
        check(f"ABAC: assign the governed tag {ABAC_TAG}", False,
              f"{str(e).splitlines()[0][:200]} - ask an account admin for the ASSIGN permission on this governed tag")

if tagged_ok and abac_policy_exists():
    print(f"unchanged: ABAC policy {ABAC_POLICY} on {ABAC_TABLE}")
    changed("ABAC policy", "unchanged")
elif tagged_ok:
    changed("ABAC policy", "created")
    run(f"""
        CREATE OR REPLACE POLICY {ABAC_POLICY}
        ON TABLE {C}.{ABAC_TABLE}
        COMMENT 'Sample ABAC demo: mask every column tagged {ABAC_TAG} with governance.mask_name'
        COLUMN MASK {G}.mask_name
        TO `account users`
        FOR TABLES
        MATCH COLUMNS has_tag('{ABAC_TAG}') AS c
        ON COLUMN c
    """)
if tagged_ok:
    display(run(f"SHOW POLICIES ON TABLE {C}.{ABAC_TABLE}"))
    display(run(f"DESCRIBE POLICY {ABAC_POLICY} ON TABLE {C}.{ABAC_TABLE}"))
    sample = display_rows(run(f"SELECT code, {ABAC_COLUMN}, name FROM {C}.{ABAC_TABLE} ORDER BY code LIMIT 5"))
    if sample and not IS_ADMIN:
        check("ABAC: responsible_person_name masked by the tag policy",
              (sample[0][1] or "").endswith("****") != PII_ACCESS, str(sample[0][1]))
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
    tagged = run(f"""
        SELECT 1 FROM {C}.information_schema.column_tags
        WHERE schema_name = '{ABAC_SCHEMA}' AND table_name = '{ABAC_TABLE_NAME}'
          AND column_name = '{ABAC_COLUMN}' AND tag_name = '{ABAC_TAG}'
    """, echo=False).count()
    if tagged:
        run(f"{alter(ABAC_TABLE)} ALTER COLUMN {ABAC_COLUMN} UNSET TAGS ('{ABAC_TAG}')")
    for t in ROW_FILTERED_TABLES:
        run(f"{alter(t)} DROP ROW FILTER")
    for t, column in MASKS:
        run(f"{alter(t)} ALTER COLUMN {column} DROP MASK")
    if BUDDY_EMAIL:
        for schema in BUDDY_SCHEMAS:
            run(f"REVOKE USE SCHEMA, SELECT ON SCHEMA {C}.{schema} FROM `{BUDDY_EMAIL}`")
        run(f"REVOKE USE CATALOG ON CATALOG {C} FROM `{BUDDY_EMAIL}`")
    # Drop exactly the objects of this notebook; the governance schema itself stays as notebook 01 created it.
    run(f"DROP VIEW IF EXISTS {DEMO_MV}")
    for table in ("user_company_access", "pii_readers", "break_copy_ar_invoice", "break_copy_profit_center"):
        run(f"DROP TABLE IF EXISTS {G}.{table}")
    for fn in reversed(OUR_FUNCTIONS):   # policy functions first, the access functions they call last
        run(f"DROP FUNCTION IF EXISTS {G}.{fn}")
    left_f = run(f"SELECT count(*) FROM {C}.information_schema.row_filters", echo=False).first()[0]
    left_m = run(f"SELECT count(*) FROM {C}.information_schema.column_masks", echo=False).first()[0]
    left_o = run(f"""
        SELECT (SELECT count(*) FROM {C}.information_schema.tables
                WHERE table_schema = 'governance'
                  AND table_name IN ('governance_demo_ar_metrics', 'user_company_access', 'pii_readers'))
             + (SELECT count(*) FROM {C}.information_schema.routines
                WHERE routine_schema = 'governance' AND routine_name IN ({', '.join(f"'{f}'" for f in OUR_FUNCTIONS)}))
    """, echo=False).first()[0]
    check("rollback: no row filters left", left_f == 0, str(left_f))
    check("rollback: no column masks left", left_m == 0, str(left_m))
    check("rollback: no ABAC policy left", not abac_policy_exists())
    check("rollback: no governance objects of this notebook left", left_o == 0, str(left_o))
    restored = as_dict(visibility())
    check("rollback: every company visible again", all(visible_codes(restored, t) == REFERENCE[t] for t in restored),
          "; ".join(f"{t}: {restored[t][0]} rows" for t in restored))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 16 · Summary
# MAGIC
# MAGIC * Policies live **on the gold tables** - every query path inherits them: SQL, views, metric views, Genie.
# MAGIC * **Who may see what** is a mapping table - changes are effective immediately.
# MAGIC * Govern the **serving layer**; give consumers access to gold only; copies leave governance.
# MAGIC * Keep lookup tables of policies **ungoverned** (no nested policies) and never stack two masks on a column.
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
    "company_codes": COMPANY_CODES,
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
