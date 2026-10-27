# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 05 · Business context — the Finance domain, Pages and the GitHub MCP
# MAGIC
# MAGIC Your Genie Agent already knows **what the data is** (table and column comments, primary/foreign keys,
# MAGIC metric views) and **who may see what** (row filters and masks from notebook 03). What it still lacks is
# MAGIC **what the business means**: which revenue is the official one, why you never add SEK to EUR, when a receivable counts as overdue.
# MAGIC
# MAGIC Fjällmark keeps that knowledge **as code** in the repository folder `bootcamp/context/` (one Markdown file per
# MAGIC business term; this domain's pages are in `bootcamp/context/domains/finance/pages/`) and brings it into
# MAGIC Databricks in three ways:
# MAGIC
# MAGIC | # | Where | How | Who |
# MAGIC |---|---|---|---|
# MAGIC | A | **UC Semantics → Pages** (Discover) | Genie Code *Bulk import pages* in the Page editor, with the prompt this notebook writes (step 8) | you (UI) |
# MAGIC | B | **Your Genie Agent** | GitHub MCP (`system.ai.github`) as an agent source, Agent mode | you (UI, step 8) |
# MAGIC | C | **Your own draft Page** | Discover → Pages → Create page | you (UI, step 9) |
# MAGIC
# MAGIC Pages live in **domains**. A domain *is* a governed tag: an asset belongs to the domain `Finance` when it
# MAGIC carries the tag `Finance`, and to the subdomain `Finance/General Ledger` when it carries that tag. The
# MAGIC domain and its governed tags are created once per account (by an admin, see step 3); **this notebook files
# MAGIC your own data into them**:
# MAGIC
# MAGIC | step | what |
# MAGIC |---|---|
# MAGIC | 1 | parameters, your catalog |
# MAGIC | 2 | read the industry model's tags: which gold table belongs to which subdomain |
# MAGIC | 3 | check that the governed tags exist (otherwise skip steps 4-7 with a clear message - steps 8-9 still run) |
# MAGIC | 4 | tag your **`finance` schema** with the domain tag (`ALTER SCHEMA ... SET TAGS ('Finance')`) |
# MAGIC | 5 | tag its **gold tables and metric views** with the subdomain tags |
# MAGIC | 6 | tag your **Genie Agent** (the Finance Analyst) with the domain |
# MAGIC | 7 | **verify** in `information_schema` |
# MAGIC | 8 | the **business glossary** in `bootcamp/context/`: **import it as Pages** under the domain and its subdomains (Genie Code *Bulk import pages*, prompt written by the notebook) and attach it to your agent (GitHub MCP) |
# MAGIC | 9 | your turn: **draft a Page** for your own business question |
# MAGIC
# MAGIC ▶ **How to run:** Serverless compute → **Run all**. Set `action = remove` to take all tags off again.
# MAGIC
# MAGIC 🔁 **Re-running is a no-op.** The notebook first reads which domain / subdomain tags your schema, tables,
# MAGIC metric views and agent already carry (`information_schema.schema_tags` / `table_tags`, the entity tag
# MAGIC API) and only sets the missing ones - everything else is reported as `already tagged`. It never touches
# MAGIC your data or the pipeline, and it never creates domains or governed tags (an account admin's job). The Pages
# MAGIC import of step 8 is a UI step: the notebook only writes the prompt (`import_pages = false` skips it).
# MAGIC
# MAGIC **Expected result:** the `finance` schema shows the *Finance* domain, every finance gold table and metric view its
# MAGIC subdomain (Catalog Explorer → table → *Tags*; Discover → *Domains* → Finance → your tables), a Bulk import
# MAGIC prompt with a checklist of the expected Pages, and a printed click-path for the GitHub MCP.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | meaning |
# MAGIC |---|---|
# MAGIC | `catalog` | leave **blank** for `cpg_finance_<your short user name>` (same rule as the bundle) |
# MAGIC | `tag_finance` | the domain tag (= governed tag) of this sample; keep the default `Finance` unless your admin named it differently |
# MAGIC | `subdomain_tag_pattern` | how subdomain tags are named; default `{domain_tag}/{subdomain}`, e.g. `Finance/General Ledger` |
# MAGIC | `action` | `apply` (default) or `remove` |
# MAGIC | `import_pages` | `true` (default) = step 8 writes the *Bulk import pages* prompt; `false` = skip |

# COMMAND ----------

import csv
import html
import json
import os
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError, NotFound

MAIN_DOMAIN = "finance"
DOMAINS = ["finance"]   # the gold schemas of this sample
REFERENCE_DOMAINS = [d for d in DOMAINS if d != MAIN_DOMAIN]   # reference tables only, not this sample's domain

dbutils.widgets.text("catalog", "", "Catalog (blank = automatic)")
for d in DOMAINS:
    dbutils.widgets.text(f"tag_{d}", d.title(), f"Domain tag: {d}")
if REFERENCE_DOMAINS:
    dbutils.widgets.dropdown("tag_reference_tables", "false", ["false", "true"], "Tag the reference tables")
dbutils.widgets.text("subdomain_tag_pattern", "{domain_tag}/{subdomain}", "Subdomain tag pattern")
dbutils.widgets.dropdown("action", "apply", ["apply", "remove"], "Action")
dbutils.widgets.dropdown("import_pages", "true", ["true", "false"], "Import glossary Pages")

GITHUB_REPO = "dediggibyte/genie_bootcamp"


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}: the part before '@',
    lower-cased, every character that is not a letter or digit replaced by '_'."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


user_name = spark.sql("SELECT current_user()").first()[0]
catalog = dbutils.widgets.get("catalog").strip() or f"cpg_{MAIN_DOMAIN}_{bundle_short_name(user_name)}"
action = dbutils.widgets.get("action")
import_pages = dbutils.widgets.get("import_pages") == "true"
tag_reference = bool(REFERENCE_DOMAINS) and dbutils.widgets.get("tag_reference_tables") == "true"
pattern = dbutils.widgets.get("subdomain_tag_pattern").strip()
DOMAIN_TAG = {d: dbutils.widgets.get(f"tag_{d}").strip() for d in DOMAINS}

w = WorkspaceClient()
host = w.config.host.rstrip("/")

print(f"You are          : {user_name}")
print(f"Catalog          : {catalog}")
print(f"Action           : {action}")
print(f"Import Pages     : {import_pages}")
print(f"Domain tags      : {DOMAIN_TAG}")
print(f"Subdomain tags   : {pattern}")
if REFERENCE_DOMAINS:
    print(f"Reference tables : {'tagged' if tag_reference else 'left untagged'} ({', '.join(REFERENCE_DOMAINS)})")
print("Genie Agent      : found by title in step 6 (built by notebook 04)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Which table belongs to which subdomain?
# MAGIC
# MAGIC The answer comes from the **Lakehouse Industry Data Model** that the pipeline was generated from - its
# MAGIC tags ship in `bootcamp_domain/finance/model_tags/<domain>.json` (table tag `dbx_subdomain`): the finance domain
# MAGIC (= gold schema) has 3 subdomains, and every table belongs to exactly one subdomain. Subdomain tag =
# MAGIC pattern applied to the domain tag and the subdomain's title, e.g. `general_ledger` →
# MAGIC `Finance/General Ledger`.
# MAGIC
# MAGIC Metric views are filed too: the industry views `<table>_metrics` go to their table's subdomain, the
# MAGIC curated views to the subdomain of the KPI they serve.

# COMMAND ----------


def bundle_root() -> str:
    """The folder that holds databricks.yml (= bootcamp_domain/finance/; this notebook lives below it)."""
    try:
        nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        d = os.path.dirname(nb_path if nb_path.startswith("/Workspace") else "/Workspace" + nb_path)
    except Exception:
        d = os.getcwd()
    while d not in ("", "/"):
        if os.path.isfile(f"{d}/databricks.yml"):
            return d
        d = os.path.dirname(d)
    raise FileNotFoundError("databricks.yml not found above this notebook - run it from the Git folder "
                            "(bootcamp_domain/finance/notebooks).")


BUNDLE_ROOT = bundle_root()
REPO_ROOT = os.path.dirname(os.path.dirname(BUNDLE_ROOT))   # the Git folder: bootcamp/ and bootcamp_domain/ below it
CONTEXT_DIR = f"{REPO_ROOT}/bootcamp/context"
model = {}   # domain -> model_tags document (generated from the industry model)
for d in DOMAINS:
    with open(f"{BUNDLE_ROOT}/model_tags/{d}.json", encoding="utf-8") as fh:
        model[d] = json.load(fh)


def title(name: str) -> str:
    return name.replace("_", " ").title()          # general_ledger -> General Ledger


def subdomain_tag(domain: str, subdomain: str) -> str:
    return pattern.format(domain_tag=DOMAIN_TAG[domain], subdomain=title(subdomain), subdomain_key=subdomain)


# (schema, table) -> subdomain tag, for every gold table of this sample
TABLE_TAG = {}
SUBDOMAINS = {}
for d in DOMAINS:
    SUBDOMAINS[d] = []
    for table, t in model[d]["tables"].items():
        sd = t["table_tags"]["dbx_subdomain"]
        if sd not in SUBDOMAINS[d]:
            SUBDOMAINS[d].append(sd)
        TABLE_TAG[(d, table)] = subdomain_tag(d, sd)

# metric views: industry <table>_metrics follow their table; curated views follow their KPI
METRIC_VIEW_TAG = {(s, f"{t}_metrics"): tag for (s, t), tag in TABLE_TAG.items()}
METRIC_VIEW_TAG.update({
    ("finance", "net_revenue_metrics"): subdomain_tag("finance", "general_ledger"),
    ("finance", "receivables_metrics"): subdomain_tag("finance", "receivables_payables"),
})

plan = []
for s in DOMAINS:
    role = "domain of this sample" if s == MAIN_DOMAIN else (
        "reference tables (tagged)" if tag_reference else "reference tables (left untagged)")
    for sd in SUBDOMAINS[s]:
        tag = subdomain_tag(s, sd)
        tables = sorted(t for (ss, t), tg in TABLE_TAG.items() if ss == s and tg == tag)
        plan.append((s, role, DOMAIN_TAG[s], title(sd), tag, ", ".join(tables)))
display(spark.createDataFrame(plan, "gold_schema string, role string, domain_tag string, subdomain string, "
                                    "subdomain_tag string, tables string"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Do the governed tags exist?
# MAGIC
# MAGIC A **governed tag** has a *tag policy* (account level). Only governed tags define domains — and, careful:
# MAGIC Unity Catalog happily accepts a tag key that has **no** policy and stores it as an ordinary tag, which
# MAGIC would then **not** show up in Discover. So we check first (REST `GET /api/2.1/tag-policies/<key>`).
# MAGIC
# MAGIC In a workspace of its own (no bootcamp instructor) the *Finance* domain may not exist yet. Then steps 4-7
# MAGIC are skipped with a clear message, and steps 8-9 (Pages, GitHub MCP) still run. To create the domain once
# MAGIC per account - you need to be an account admin, or ask one:
# MAGIC
# MAGIC * run `bootcamp/instructor/00_instructor_setup.py` from the same Git folder with widget
# MAGIC   `domain_names = Finance` (it creates the governed tags, the domain and its subdomains), **or**
# MAGIC * create the domain in the UI under **Discover → Domains** (name `Finance`, subdomains `Organizational Accounting`, `General Ledger`, `Receivables Payables`)
# MAGIC   and grant yourself `ASSIGN` on its governed tags.
# MAGIC
# MAGIC Then run this notebook again.
# MAGIC
# MAGIC We also list the **domains** that use these tags (`GET /api/2.0/domains`, Beta) — purely informative.

# COMMAND ----------


def rest(method: str, path: str, body: dict = None, query: dict = None):
    """Small wrapper around the workspace REST API (authenticated as you)."""
    return w.api_client.do(method, path, body=body, query=query)


def check_tag_policies(keys: list):
    """-> (missing, unknown): tag keys without a tag policy, and keys that could not be verified."""
    missing, unknown = [], []
    for key in keys:
        try:
            rest("GET", f"/api/2.1/tag-policies/{quote(key, safe='')}")
        except NotFound:
            missing.append(key)
        except DatabricksError as e:
            if "not found" in str(e).lower():
                missing.append(key)
            else:
                unknown.append((key, str(e)[:120]))
    return missing, unknown


MAIN_TAGS = [DOMAIN_TAG[MAIN_DOMAIN]] + sorted({subdomain_tag(MAIN_DOMAIN, s) for s in SUBDOMAINS[MAIN_DOMAIN]})
REF_TAGS = sorted({DOMAIN_TAG[d] for d in REFERENCE_DOMAINS}
                  | {subdomain_tag(d, s) for d in REFERENCE_DOMAINS for s in SUBDOMAINS[d]}) if tag_reference else []

missing, unknown = check_tag_policies(MAIN_TAGS)
ref_missing, ref_unknown = check_tag_policies(REF_TAGS)

print(f"Governed tags expected : {len(MAIN_TAGS)}" + (f" (+ {len(REF_TAGS)} for the reference tables)" if REF_TAGS else ""))
print(f"  found                : {len(MAIN_TAGS) - len(missing) - len(unknown)}"
      + (f" (+ {len(REF_TAGS) - len(ref_missing) - len(ref_unknown)})" if REF_TAGS else ""))
if unknown or ref_unknown:
    print("  could not verify (no permission to read tag policies?) - continuing:")
    for k, e in unknown + ref_unknown:
        print(f"     {k}: {e}")

try:
    domains = rest("GET", "/api/2.0/domains").get("domains", [])
    by_tag = {d["tag_key"]: d for d in domains}
    for key in MAIN_TAGS + REF_TAGS:
        d = by_tag.get(key)
        state = "-" if d is None else ("draft" if d.get("effective_draft") else "published")
        print(f"  domain for tag {key!r:45} : {state}")
except DatabricksError as e:
    print(f"(Domains API not readable for you: {str(e)[:100]} - fine, continuing)")

# tags_ready = steps 4-7 run; on `remove` nothing new is assigned, so missing policies do not matter
tags_ready = not (missing and action == "apply")
if not tags_ready:
    msg = (
        "\n" + "=" * 100 +
        "\nSTOP (steps 4-7 skipped): these governed tags do not exist (no tag policy):\n   " + "\n   ".join(missing) +
        "\n\nThe domain and its governed tags are created ONCE per account by an account admin, either with"
        f"\n  bootcamp/instructor/00_instructor_setup.py  (widget domain_names = {DOMAIN_TAG[MAIN_DOMAIN]})"
        f"\nor in the UI under Discover > Domains (domain {DOMAIN_TAG[MAIN_DOMAIN]} with its subdomains)."
        "\nCheck the tag names in the widgets at the top of this notebook, then run this notebook again."
        "\nSteps 8 and 9 (glossary Pages, GitHub MCP) continue below.\n" + "=" * 100)
    print(msg)

# reference tables are tagged only when asked AND their governed tags exist
tag_reference = tag_reference and (action == "remove" or not ref_missing)
if REF_TAGS and ref_missing and action == "apply":
    print(f"Note: the reference tables stay untagged - governed tag(s) missing: {ref_missing}")
TAG_DOMAINS = [MAIN_DOMAIN] + (REFERENCE_DOMAINS if tag_reference else [])   # schemas whose tables get tags
ALL_TAGS = MAIN_TAGS + (REF_TAGS if tag_reference else [])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Tag your `finance` schema with its domain
# MAGIC
# MAGIC Domain tags are **value-less** governed tags: `ALTER SCHEMA ... SET TAGS ('Finance')` (a `key = value` form
# MAGIC would be rejected — the tag policy allows no values). A tag on a schema is **inherited** by every table,
# MAGIC view and metric view in it, so your whole `finance` schema now appears under the *Finance* domain.
# COMMAND ----------


def q(*parts: str) -> str:
    """Back-tick quote a (multi-part) identifier."""
    return ".".join("`" + p.replace("`", "``") + "`" for p in parts)


def lit(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def run(stmt: str):
    try:
        spark.sql(stmt)
        return None
    except Exception as e:                                   # noqa: BLE001 - shown to the participant
        msg = str(e).split("\n")[0]
        if "PERMISSION_DENIED" in msg or "ASSIGN" in msg.upper():
            msg += "  -> you need the ASSIGN permission on this governed tag (see step 3)"
        return msg


verb = "SET" if action == "apply" else "UNSET"
existing_schemas = {r[0] for r in spark.sql(f"SHOW SCHEMAS IN {q(catalog)}").collect()}
schema_results = []
if not tags_ready:
    print("Skipped - governed tags missing (step 3).")
else:
    tag_schema_list = ", ".join(lit(s) for s in TAG_DOMAINS)
    have_schema_tags = {(r.schema_name, r.tag_name) for r in spark.sql(
        f"SELECT schema_name, tag_name FROM {q(catalog)}.information_schema.schema_tags "
        f"WHERE schema_name = {lit(MAIN_DOMAIN)}").collect()}
    have_table_tags = {(r.schema_name, r.table_name, r.tag_name) for r in spark.sql(
        f"SELECT schema_name, table_name, tag_name FROM {q(catalog)}.information_schema.table_tags "
        f"WHERE schema_name IN ({tag_schema_list})").collect()}
    s = MAIN_DOMAIN
    if s not in existing_schemas:
        schema_results.append((s, DOMAIN_TAG[s], "SKIPPED - schema does not exist (run 01 and the pipeline first)"))
    elif ((s, DOMAIN_TAG[s]) in have_schema_tags) == (action == "apply"):   # nothing to do
        schema_results.append((s, DOMAIN_TAG[s], "already tagged" if action == "apply" else "not tagged"))
    else:
        err = run(f"ALTER SCHEMA {q(catalog, s)} {verb} TAGS ({lit(DOMAIN_TAG[s])})")
        schema_results.append((s, DOMAIN_TAG[s], err or f"{verb} OK"))
    display(spark.createDataFrame(schema_results, "gold_schema string, domain_tag string, result string"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Tag your gold tables and metric views with their subdomain
# MAGIC
# MAGIC A subdomain tag is **not** inherited upwards and the parent tag is **not** applied automatically — that is
# MAGIC why step 4 tagged the schema and this step tags each table. Gold tables are pipeline materialized views
# MAGIC (`ALTER TABLE ... SET TAGS` works on them and survives pipeline refreshes); metric views use `ALTER VIEW`.
# MAGIC The statements run in parallel threads (≈ 1 s each).
# COMMAND ----------

todo, not_in_model, unchanged, errors, missing_tables = [], [], [], [], []
if not tags_ready:
    print("Skipped - governed tags missing (step 3).")
else:
    objects = spark.sql(f"""
        SELECT table_schema, table_name, table_type
        FROM {q(catalog)}.information_schema.tables
        WHERE table_schema IN ({', '.join(lit(s) for s in TAG_DOMAINS)})
          AND table_name NOT LIKE '\\_\\_%'          -- hide pipeline-internal tables
          AND table_name NOT LIKE 'event_log%'
    """).collect()

    for r in objects:
        key = (r.table_schema, r.table_name)
        tag = TABLE_TAG.get(key) or METRIC_VIEW_TAG.get(key)
        if tag is None:
            not_in_model.append(f"{r.table_schema}.{r.table_name}")
            continue
        if ((r.table_schema, r.table_name, tag) in have_table_tags) == (action == "apply"):   # nothing to do
            unchanged.append(key)
            continue
        kind = "VIEW" if r.table_type in ("VIEW", "METRIC_VIEW") else "TABLE"
        todo.append((r.table_schema, r.table_name, r.table_type, tag,
                     f"ALTER {kind} {q(catalog, r.table_schema, r.table_name)} {verb} TAGS ({lit(tag)})"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        errors = list(pool.map(lambda t: run(t[4]), todo))

    table_results = [(t[0], t[1], t[2], t[3], e or f"{verb} OK") for t, e in zip(todo, errors)]
    table_results += [(s, t, "", TABLE_TAG.get((s, t)) or METRIC_VIEW_TAG.get((s, t)),
                       "already tagged" if action == "apply" else "not tagged") for s, t in unchanged]
    found = {(t[0], t[1]) for t in todo} | set(unchanged)
    missing_tables = sorted(f"{s}.{t}" for (s, t) in TABLE_TAG if s in TAG_DOMAINS and (s, t) not in found)

    print(f"Tagged objects : {sum(1 for e in errors if e is None)} of {len(todo)} to change "
          f"({len(unchanged)} already as wanted)")
    print(f"Failed         : {sum(1 for e in errors if e is not None)}")
    if missing_tables:
        print(f"Model tables not (yet) in your catalog: {len(missing_tables)} -> e.g. {missing_tables[:5]}"
              f"  (has the pipeline run?)")
    if not_in_model:
        print(f"Objects without a subdomain (left untouched): {not_in_model[:10]}")
    if table_results:
        display(spark.createDataFrame(table_results, "gold_schema string, object string, type string, "
                                                     "subdomain_tag string, result string").orderBy("gold_schema", "object"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Tag your Genie Agent with its domain
# MAGIC
# MAGIC Genie Agents are workspace objects, so they are tagged with the **workspace entity tag assignments** API
# MAGIC (`POST /api/2.0/entity-tag-assignments`, Beta). Notebook 04 built the Finance Analyst; it gets the
# MAGIC *Finance* domain tag, so it shows up under *Finance* in Discover. The agent is found by its title
# MAGIC `Fjällmark Finance Analyst (<catalog>)`. Subdomain tags (with `/`) cannot be assigned to workspace objects.

# COMMAND ----------

AGENT_TITLE = f"Fjällmark {MAIN_DOMAIN.capitalize()} Analyst ({catalog})"


def find_agent():
    """Space id of the agent notebook 04 built on this catalog (matched by title), or None."""
    token = None
    while True:
        query = {"page_size": 100, **({"page_token": token} if token else {})}
        resp = rest("GET", "/api/2.0/genie/spaces", query=query)
        for s in resp.get("spaces", []):
            if s.get("title") == AGENT_TITLE:
                return s["space_id"]
        token = resp.get("next_page_token")
        if not token:
            return None


genie_agent = find_agent()
genie_result = []   # (agent, tag, result)
key = DOMAIN_TAG[MAIN_DOMAIN]
if not genie_agent:
    print(f"No agent titled '{AGENT_TITLE}' yet - run notebook 04 first, then re-run this cell.")
elif not tags_ready:
    print("Skipped - governed tags missing (step 3).")
else:
    try:
        have = {t["tag_key"] for t in rest("GET", f"/api/2.0/entity-tag-assignments/geniespaces/{genie_agent}/tags")
                .get("tag_assignments", [])}
    except DatabricksError:
        have = set()
    if (key in have) == (action == "apply"):
        genie_result.append((AGENT_TITLE, key, "already tagged" if action == "apply" else "not tagged"))
    else:
        try:
            if action == "apply":
                rest("POST", "/api/2.0/entity-tag-assignments",
                     {"entity_type": "geniespaces", "entity_id": genie_agent, "tag_key": key})
            else:
                rest("DELETE", f"/api/2.0/entity-tag-assignments/geniespaces/{genie_agent}/tags/{quote(key, safe='')}")
            genie_result.append((AGENT_TITLE, key, f"{verb} OK"))
        except DatabricksError as e:
            txt = str(e)
            ok = ("already exists" in txt.lower() and action == "apply") or ("not found" in txt.lower() and action == "remove")
            genie_result.append((AGENT_TITLE, key, f"{verb} OK (nothing to do)" if ok else f"FAILED: {txt[:200]}"))
for agent_title, k, r in genie_result:   # not `title`: that would shadow the title() helper used in step 8
    print(f"  {agent_title:60} {k:15} {r}")
if genie_agent:
    print(f"  {AGENT_TITLE}: {host}/genie/rooms/{genie_agent}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Verify
# MAGIC
# MAGIC Tags are visible in `information_schema` (`schema_tags`, `table_tags`) — value-less tags have an empty
# MAGIC `tag_value`. Expected after `apply`: the `finance` schema with its domain tag, every finance gold table (and metric
# MAGIC view) with exactly one subdomain tag - on the first run and on every re-run. After `remove`: zero rows.

# COMMAND ----------

n_schema, n_tables, ok = 0, 0, False
if not tags_ready:
    print("Skipped - governed tags missing (step 3).")
else:
    tag_list = ", ".join(lit(t) for t in ALL_TAGS)
    schema_tags = spark.sql(f"""
        SELECT schema_name, tag_name, tag_value
        FROM {q(catalog)}.information_schema.schema_tags
        WHERE tag_name IN ({tag_list})
        ORDER BY schema_name""")
    display(schema_tags)

    table_tags = spark.sql(f"""
        SELECT tag_name AS subdomain_tag, schema_name, COUNT(*) AS tagged_objects,
               array_join(sort_array(collect_list(table_name)), ', ') AS objects
        FROM {q(catalog)}.information_schema.table_tags
        WHERE tag_name IN ({tag_list})
        GROUP BY tag_name, schema_name
        ORDER BY schema_name, subdomain_tag""")
    display(table_tags)

    n_schema = schema_tags.count()
    n_tables = spark.sql(f"""SELECT COUNT(*) FROM {q(catalog)}.information_schema.table_tags
                              WHERE tag_name IN ({tag_list})""").first()[0]
    expected_schemas = 1 if MAIN_DOMAIN in existing_schemas else 0
    expected_tables = len(todo) + len(unchanged)   # newly tagged now + already tagged before (re-run)
    if action == "apply":
        ok = n_schema == expected_schemas and n_tables == expected_tables and not any(errors)
    else:
        ok = n_schema == 0 and n_tables == 0
    print(f"Schemas with a domain tag    : {n_schema} (expected {expected_schemas if action == 'apply' else 0})")
    print(f"Objects with a subdomain tag : {n_tables} (expected {expected_tables if action == 'apply' else 0})")
    if genie_agent:
        try:
            tags = rest("GET", f"/api/2.0/entity-tag-assignments/geniespaces/{genie_agent}/tags")
            print(f"Genie Agent tags             : {[t['tag_key'] for t in tags.get('tag_assignments', [])]}")
        except DatabricksError as e:
            print(f"Genie Agent tags             : could not read ({str(e)[:100]})")
    print("\n✅ All good." if ok else "\n⚠️  Something is missing - check the result tables above.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8 · The business glossary — and how your agent reads it (GitHub MCP)
# MAGIC
# MAGIC The folder `bootcamp/context/` of this repository is Fjällmark's business glossary: one page per term, with
# MAGIC definition, business rules, calculation SQL against your gold tables, pitfalls ("common wrong answers")
# MAGIC and example questions. Below are the *Finance* rows of the index (`bootcamp/context/glossary.csv`); the next
# MAGIC cell writes the prompt that imports them as **Pages** under the domain and subdomains you just filed your
# MAGIC data into, so Genie One cites them. The files are read from the Git folder (`bootcamp/` next to
# MAGIC `bootcamp_domain/`), not copied into this sample.

# COMMAND ----------

glossary_path = f"{CONTEXT_DIR}/glossary.csv"
pages_dir = f"{CONTEXT_DIR}/domains/{MAIN_DOMAIN}/pages"
terms = []   # the glossary rows of this domain
if os.path.isfile(glossary_path):
    with open(glossary_path, encoding="utf-8", newline="") as fh:
        terms = [r for r in csv.DictReader(fh) if r["domain"] == title(MAIN_DOMAIN)]
    display(spark.createDataFrame([(r["domain"], r["subdomain"], r["term"], r["short_definition"], r["page_path"])
                                   for r in terms],
                                  "domain string, subdomain string, term string, definition string, page string"))
else:
    print(f"{glossary_path} not found (is this the repository's Git folder, with bootcamp/ next to bootcamp_domain/?)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Import the glossary as Pages (Genie Code *Bulk import pages*, UI)
# MAGIC
# MAGIC Pages have **no API**, and a Genie Code task in a job has **no tool to create them**: only the **Bulk import
# MAGIC pages** mode of the Genie Code pane in the Page editor creates Pages (it reads the sources you attach,
# MAGIC proposes one Page per term, flags duplicates and conflicts, and creates them all as drafts). So this is a
# MAGIC UI step - the cell below writes the exact prompt, with your catalog and the workspace paths of the glossary
# MAGIC files filled in, and a checklist of the Pages you should end up with:
# MAGIC
# MAGIC 1. **Discover → Pages → Create page**. If the Genie Code pane is not open, click the Genie Code icon (top
# MAGIC    right), then **Bulk import pages**.
# MAGIC 2. In the chat box click **+ → Add context** and add the `pages` folder and `glossary.csv` (paths below).
# MAGIC 3. Copy the prompt (click into the grey box, select all, copy), paste it, send, review the proposed Pages
# MAGIC    (resolve duplicate / low-confidence flags, check each Page's subdomain) and let Genie Code create them.
# MAGIC    They are created as **drafts**.
# MAGIC 4. Check the result in **Discover → Pages** (filter *Draft*) and tick the Pages off in the checklist.
# MAGIC
# MAGIC Drafts are visible only to you (and curators), and Genie One uses them in your own conversations, the same
# MAGIC rule as step 9. Filing the Pages under subdomains needs the domain of step 3 - if step 3 stopped, create the
# MAGIC domain first. `import_pages = false` skips the cell.

# COMMAND ----------

pages_result = []   # (domain_tag, number of terms)
if action != "apply" or not import_pages:
    print(f"Skipped (action = {action}, import_pages = {import_pages}).")
elif not terms:
    print(f"Skipped: no {title(MAIN_DOMAIN)} rows in {glossary_path} (file missing?).")
else:
    d = MAIN_DOMAIN
    subdomains = sorted({r["subdomain"] for r in terms})
    filing = "; ".join(f"subdomain '{r}' -> '{subdomain_tag(d, r.lower().replace(' ', '_'))}'" for r in subdomains)
    prompt = (
        f"Bulk import the Fjällmark business glossary for the domain '{DOMAIN_TAG[d]}'. Use only the attached "
        f"workspace files as sources: the index {glossary_path} and the term pages in the folder {pages_dir}. "
        f"Create exactly one Page per index row whose domain column is '{title(d)}' ({len(terms)} terms: "
        f"{', '.join(r['term'] for r in terms)}) - no other terms, do not merge or split terms. For each row read "
        f"the Markdown file named in page_path and fill the Page from its YAML front matter and body: Page name = "
        f"title; Synonyms = synonyms; Description = description; Page body = the Markdown after the front matter "
        f"(definition, business rules, calculation SQL, pitfalls, example questions) word for word, except that "
        f"every '<catalog>' - in the body as well - becomes '{catalog}', followed by a 'Sources' list with the "
        f"front matter sources; Related assets = related_assets with '<catalog>' replaced by '{catalog}', keeping "
        f"only assets in the schemas {', '.join(DOMAINS)} (this catalog has no other gold schemas); "
        f"Sources (links only, must be https URLs) = the single link "
        f"https://github.com/{GITHUB_REPO}/blob/main/<page_path> of the row. File each Page under its subdomain "
        f"from the subdomain column: {filing}. The index rows are distinct terms: similarity or overlap warnings "
        f"between them (e.g. CLTV Segment and Active Shopper) are expected - create every term anyway. If a Page "
        f"with the same name already exists, flag it as a duplicate instead of creating a second one. Create all "
        f"Pages as drafts; do not publish."
    )
    pages_result.append((DOMAIN_TAG[d], len(terms)))
    checklist = "".join(
        f"<tr><td><input type='checkbox'></td><td>{html.escape(r['term'])}</td><td>{html.escape(r['subdomain'])}</td>"
        f"<td><code>{html.escape(subdomain_tag(d, r['subdomain'].lower().replace(' ', '_')))}</code></td>"
        f"<td><code>{html.escape(os.path.basename(r['page_path']))}</code></td></tr>"
        for r in sorted(terms, key=lambda r: (r["subdomain"], r["term"])))
    displayHTML(f"""
<div style="font-family:sans-serif;font-size:14px">
  <p>Domain <b>{html.escape(DOMAIN_TAG[d])}</b> - {len(terms)} terms in {len(subdomains)} subdomains.
     Open <a href="{host}/discover/pages" target="_blank">Discover → Pages</a> → Create page → Genie Code →
     <b>Bulk import pages</b>.</p>
  <p><b>Add context</b> (both):<br><code>{html.escape(pages_dir)}</code><br><code>{html.escape(glossary_path)}</code></p>
  <p><b>Prompt</b> (click into the box, select all, copy):</p>
  <pre style="white-space:pre-wrap;user-select:all;background:#f4f4f4;border:1px solid #ccc;padding:10px;
              max-width:1100px">{html.escape(prompt)}</pre>
  <p><b>Expected Pages</b> (drafts) - tick them off in Discover → Pages:</p>
  <table style="border-collapse:collapse" border="1" cellpadding="4">
    <tr><th>✓</th><th>Page (title)</th><th>subdomain</th><th>subdomain tag</th><th>source file</th></tr>
    {checklist}
  </table>
</div>""")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Attach the GitHub MCP to your Finance Analyst (UI, 3 minutes)
# MAGIC
# MAGIC There is no API for MCP sources yet, so this is a UI step. Run the next cell for your personal click-path.
# MAGIC
# MAGIC Good to know:
# MAGIC * MCP tools work **only in Agent mode** (not in Chat mode).
# MAGIC * Every tool call runs with **your** GitHub account (OAuth sign-in in the *Configure* panel).
# MAGIC * The GitHub MCP reads **public** repositories by default. A private repository needs the
# MAGIC   [Databricks GitHub connector app](https://github.com/apps/databricks-github-connector) installed by a
# MAGIC   GitHub organisation admin. If the agent cannot read `bootcamp/context/`, check that the repository is
# MAGIC   public or the connector app is installed.
# MAGIC * Read tools (search, get file) run automatically; write tools would pause for **your approval**.

# COMMAND ----------

agent_url = (f"{host}/genie/rooms/{genie_agent}" if genie_agent
             else "(open your Finance Analyst from the Genie page)")
term_names = ", ".join(r["term"] for r in terms) or "net revenue, COGS, gross margin, DSO, overdue receivable, fiscal period, company code"
description = (
    f"Business glossary of Fjällmark Consumer Goods, domain {title(MAIN_DOMAIN)}. Before you answer a question that "
    f"uses a business term ({term_names} ...), read the matching file in the GitHub repository {GITHUB_REPO}, "
    f"folder bootcamp/context/domains/{MAIN_DOMAIN}/pages/ (index: bootcamp/context/glossary.csv), and follow its "
    "business rules and calculation. Company facts (entities, currencies, plants, fiscal calendar) are in "
    "bootcamp/context/company_profile.md. Read only; never create issues, branches or pull requests."
)
print(f"""
1. Open your Finance Analyst: {agent_url}
2. Tab  Sources  ->  Add  ->  MCP services  ->  select  system.ai.github  (GitHub)
3. Paste this as the source Description:

{description}

4. Switch OFF the connector's write tools (keep search / get file contents).
5. In the chat box switch ON  Agent mode, open  Configure  and  Sign in  to GitHub.
6. Ask:  "What was net revenue in Q2 2026 by company code? Use the official definition."
   -> watch the agent open bootcamp/context/domains/finance/pages/net_revenue.md before it writes SQL.
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9 · Your turn — draft a Page for *your* business question
# MAGIC
# MAGIC 1. **Discover → Pages → Create page** (or open the *Finance* domain and create it there).
# MAGIC 2. Pick a concept that is **not** defined yet, for example *Overdue payables rate*, *Brand contribution margin* or *Revenue per company code employee*.
# MAGIC 3. Fill **Synonyms**, **Description** and the **Page body** — copy the structure of any file in
# MAGIC    `bootcamp/context/domains/finance/pages/` (definition → business rules → calculation SQL → pitfalls → example
# MAGIC    questions), or let **Genie Code** draft it from `bootcamp/context/` (GitHub connection), your gold tables and the
# MAGIC    metric views.
# MAGIC 4. Add your tables / metric views under **Related assets** and this repository under **Sources**.
# MAGIC 5. **Save as draft.** A draft is visible only to you (and curators) and Genie One uses it **only in your
# MAGIC    own conversations** — the safe way to test a definition before the domain owner publishes it.
# MAGIC 6. Ask Genie One your question and check that the answer **cites your Page**.
# MAGIC
# MAGIC **Never put personal data in a Page** — Pages are account-level and may be replicated globally.

# COMMAND ----------

summary = {
    "catalog": catalog,
    "action": action,
    "governed_tags_missing": missing,
    "reference_tables_tagged": tag_reference,
    "schemas_with_domain_tag": n_schema,
    "objects_with_subdomain_tag": n_tables,
    "statements_run": len(todo) + sum(1 for r in schema_results if r[2].endswith(" OK")),   # 0 on a re-run
    "already_as_wanted": len(unchanged),
    "failed_statements": sum(1 for e in errors if e is not None),
    "model_tables_missing_in_catalog": len(missing_tables),
    "genie_agent": genie_agent,
    "genie_agent_tags": [f"{agent_title} - {k}: {r}" for agent_title, k, r in genie_result],
    "glossary_pages": [f"{tag}: {n} terms (prompt written; import in the Page editor)" for tag, n in pages_result],
    "ok": ok,
}
if not tags_ready:
    summary["status"] = "STOPPED"
    summary["reason"] = "governed tags missing - tagging skipped, Pages / MCP steps written"
print(json.dumps(summary, indent=2))
dbutils.notebook.exit(json.dumps(summary))   # visible as the run output when this notebook runs as a job task
