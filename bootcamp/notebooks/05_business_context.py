# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Business context — domains, Pages and the GitHub MCP
# MAGIC
# MAGIC Your Genie Agent already knows **what the data is** (table and column comments, primary/foreign keys,
# MAGIC metric views) and **who may see what** (row filters and masks from notebook 03). What it still lacks is
# MAGIC **what the business means**: which revenue is the official one, why you never add SEK to EUR, which
# MAGIC production order statuses count as "completed".
# MAGIC
# MAGIC Fjällmark keeps that knowledge **as code** in the repository folder `bootcamp/context/` (one Markdown file per
# MAGIC business term) and brings it into Databricks in three ways:
# MAGIC
# MAGIC | # | Where | How | Who |
# MAGIC |---|---|---|---|
# MAGIC | A | **UC Semantics → Pages** (Discover) | Genie Code *Bulk import pages* from GitHub | instructor, once |
# MAGIC | B | **Your Genie Agent** | GitHub MCP (`system.ai.github`) as an agent source, Agent mode | you (UI, step 8) |
# MAGIC | C | **Your own draft Page** | Discover → Pages → Create page | you (UI, step 9) |
# MAGIC
# MAGIC Pages live in **domains**. A domain *is* a governed tag: an asset belongs to the domain `Finance` when it
# MAGIC carries the tag `Finance`, and to the subdomain `Finance/General Ledger` when it carries that tag. The
# MAGIC instructor created the domains (notebook `00_instructor_setup`); **this notebook files your own data
# MAGIC into them**:
# MAGIC
# MAGIC | step | what |
# MAGIC |---|---|
# MAGIC | 1 | parameters, your catalog |
# MAGIC | 2 | read the industry model's tags: which gold table belongs to which domain / subdomain |
# MAGIC | 3 | check that the instructor's governed tags exist (otherwise stop with a clear message) |
# MAGIC | 4 | tag your **gold schemas** with the domain tags (`ALTER SCHEMA ... SET TAGS ('Finance')`) |
# MAGIC | 5 | tag your **gold tables and metric views** with the subdomain tags |
# MAGIC | 6 | optionally tag your **Genie Agent** with its domains |
# MAGIC | 7 | **verify** in `information_schema` |
# MAGIC | 8 | the **business glossary** in `bootcamp/context/` and how to attach it to your agent (GitHub MCP) |
# MAGIC | 9 | your turn: **draft a Page** for your own business question |
# MAGIC
# MAGIC ▶ **How to run:** Serverless compute → **Run all**. Set `action = remove` to take all tags off again.
# MAGIC
# MAGIC 🔁 **Re-running is a no-op.** The notebook first reads which domain / subdomain tags your schemas, tables,
# MAGIC metric views and agent already carry (`information_schema.schema_tags` / `table_tags`, the entity tag
# MAGIC API) and only sets the missing ones - everything else is reported as `already tagged`. It never touches
# MAGIC your data or the pipeline, and it never creates account-level objects (domains and governed tags are the
# MAGIC instructor's job).
# MAGIC
# MAGIC **Expected result:** every gold schema shows its domain, every gold table its subdomain
# MAGIC (Catalog Explorer → table → *Tags*; Discover → *Domains* → e.g. Finance → your tables), and a printed
# MAGIC click-path for the GitHub MCP.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | meaning |
# MAGIC |---|---|
# MAGIC | `catalog` | leave **blank** for `cpg_<your short user name>` (same rule as the bundle) |
# MAGIC | `genie_space_id` | optional: the ID of your Genie Agent (from notebook 04 or the URL `.../genie/rooms/<id>`) |
# MAGIC | `tag_consumer`, `tag_finance`, `tag_manufacturing` | the domain tags the instructor created — keep the defaults unless told otherwise |
# MAGIC | `subdomain_tag_pattern` | how subdomain tags are named; default `{domain_tag}/{subdomain}`, e.g. `Finance/General Ledger` |
# MAGIC | `action` | `apply` (default) or `remove` |

# COMMAND ----------

import csv
import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError, NotFound, PermissionDenied

dbutils.widgets.text("catalog", "", "Catalog (blank = automatic)")
dbutils.widgets.text("genie_space_id", "", "Genie Agent ID (optional)")
dbutils.widgets.text("tag_consumer", "Consumer", "Domain tag: consumer")
dbutils.widgets.text("tag_finance", "Finance", "Domain tag: finance")
dbutils.widgets.text("tag_manufacturing", "Manufacturing", "Domain tag: manufacturing")
dbutils.widgets.text("subdomain_tag_pattern", "{domain_tag}/{subdomain}", "Subdomain tag pattern")
dbutils.widgets.dropdown("action", "apply", ["apply", "remove"], "Action")

GOLD_SCHEMAS = ["consumer", "finance", "manufacturing"]   # the bootcamp domains
GITHUB_REPO = "dediggibyte/genie_bootcamp"


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}: the part before '@',
    lower-cased, every character that is not a letter or digit replaced by '_'."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


user_name = spark.sql("SELECT current_user()").first()[0]
catalog = dbutils.widgets.get("catalog").strip() or f"cpg_{bundle_short_name(user_name)}"
genie_space_id = dbutils.widgets.get("genie_space_id").strip()
action = dbutils.widgets.get("action")
pattern = dbutils.widgets.get("subdomain_tag_pattern").strip()
DOMAIN_TAG = {d: dbutils.widgets.get(f"tag_{d}").strip() for d in GOLD_SCHEMAS}

w = WorkspaceClient()
host = w.config.host.rstrip("/")

print(f"You are        : {user_name}")
print(f"Catalog        : {catalog}")
print(f"Action         : {action}")
print(f"Domain tags    : {DOMAIN_TAG}")
print(f"Subdomain tags : {pattern}")
print(f"Genie Agent    : {genie_space_id or '(not given - step 6 is skipped)'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Which table belongs to which domain and subdomain?
# MAGIC
# MAGIC The answer comes from the **Lakehouse Industry Data Model** that the pipeline was generated from - its
# MAGIC tags ship in `bootcamp/model_tags/<domain>.json` (table tag `dbx_subdomain`): every domain (= gold schema)
# MAGIC has 2-3 subdomains, and every table belongs to exactly one subdomain. Subdomain tag = pattern applied to the domain tag and the
# MAGIC subdomain's title, e.g. `general_ledger` → `Finance/General Ledger`.
# MAGIC
# MAGIC Metric views are filed too: the industry views `<table>_metrics` go to their table's subdomain, the
# MAGIC curated bootcamp views to the subdomain of the KPI they serve.

# COMMAND ----------


def bundle_root() -> str:
    """The folder that holds databricks.yml (= bootcamp/; this notebook lives below it)."""
    try:
        nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        d = os.path.dirname(nb_path if nb_path.startswith("/Workspace") else "/Workspace" + nb_path)
    except Exception:
        d = os.getcwd()
    while d not in ("", "/"):
        if os.path.isfile(f"{d}/databricks.yml"):
            return d
        d = os.path.dirname(d)
    raise FileNotFoundError("databricks.yml not found above this notebook - run it from the bootcamp Git folder.")


BUNDLE_ROOT = bundle_root()
CONTEXT_DIR = f"{BUNDLE_ROOT}/context"
model = {}   # domain -> model_tags document (generated from the industry model)
for d in GOLD_SCHEMAS:
    with open(f"{BUNDLE_ROOT}/model_tags/{d}.json", encoding="utf-8") as fh:
        model[d] = json.load(fh)


def title(name: str) -> str:
    return name.replace("_", " ").title()          # general_ledger -> General Ledger


def subdomain_tag(domain: str, subdomain: str) -> str:
    return pattern.format(domain_tag=DOMAIN_TAG[domain], subdomain=title(subdomain), subdomain_key=subdomain)


# (schema, table) -> subdomain tag, for every gold table of the bootcamp domains
TABLE_TAG = {}
SUBDOMAINS = {}
for d in GOLD_SCHEMAS:
    SUBDOMAINS[d] = []
    for table, t in model[d]["tables"].items():
        sd = t["table_tags"]["dbx_subdomain"]
        if sd not in SUBDOMAINS[d]:
            SUBDOMAINS[d].append(sd)
        TABLE_TAG[(d, table)] = subdomain_tag(d, sd)

# metric views: industry <table>_metrics follow their table; curated views follow their KPI
METRIC_VIEW_TAG = {(s, f"{t}_metrics"): tag for (s, t), tag in TABLE_TAG.items()}
METRIC_VIEW_TAG.update({
    ("consumer", "dtc_sales_metrics"): subdomain_tag("consumer", "direct_sales"),
    ("finance", "net_revenue_metrics"): subdomain_tag("finance", "general_ledger"),
    ("finance", "receivables_metrics"): subdomain_tag("finance", "receivables_payables"),
    ("manufacturing", "production_performance_metrics"): subdomain_tag("manufacturing", "batch_execution"),
})

ALL_TAGS = list(DOMAIN_TAG.values()) + sorted({subdomain_tag(d, s) for d in SUBDOMAINS for s in SUBDOMAINS[d]})

plan = []
for s in GOLD_SCHEMAS:
    for sd in SUBDOMAINS[s]:
        tag = subdomain_tag(s, sd)
        tables = sorted(t for (ss, t), tg in TABLE_TAG.items() if ss == s and tg == tag)
        plan.append((s, DOMAIN_TAG[s], title(sd), tag, ", ".join(tables)))
display(spark.createDataFrame(plan, "gold_schema string, domain_tag string, subdomain string, subdomain_tag string, tables string"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Do the governed tags exist?
# MAGIC
# MAGIC A **governed tag** has a *tag policy* (account level). Only governed tags define domains — and, careful:
# MAGIC Unity Catalog happily accepts a tag key that has **no** policy and stores it as an ordinary tag, which
# MAGIC would then **not** show up in Discover. So we check first (REST `GET /api/2.1/tag-policies/<key>`) and
# MAGIC stop with a clear message if the instructor has not run `00_instructor_setup` yet.
# MAGIC
# MAGIC We also list the **domains** that use these tags (`GET /api/2.0/domains`, Beta) — purely informative.

# COMMAND ----------


def rest(method: str, path: str, body: dict = None, query: dict = None):
    """Small wrapper around the workspace REST API (authenticated as you)."""
    return w.api_client.do(method, path, body=body, query=query)


missing, unknown = [], []
for key in ALL_TAGS:
    try:
        rest("GET", f"/api/2.1/tag-policies/{quote(key, safe='')}")
    except NotFound:
        missing.append(key)
    except (PermissionDenied, DatabricksError) as e:
        if "not found" in str(e).lower():
            missing.append(key)
        else:
            unknown.append((key, str(e)[:120]))

print(f"Governed tags expected : {len(ALL_TAGS)}")
print(f"  found                : {len(ALL_TAGS) - len(missing) - len(unknown)}")
if unknown:
    print("  could not verify (no permission to read tag policies?) - continuing:")
    for k, e in unknown:
        print(f"     {k}: {e}")

try:
    domains = rest("GET", "/api/2.0/domains").get("domains", [])
    by_tag = {d["tag_key"]: d for d in domains}
    for key in ALL_TAGS:
        d = by_tag.get(key)
        state = "-" if d is None else ("draft" if d.get("effective_draft") else "published")
        print(f"  domain for tag {key!r:45} : {state}")
except DatabricksError as e:
    print(f"(Domains API not readable for you: {str(e)[:100]} - fine, continuing)")

if missing and action == "apply":
    msg = (
        "\n" + "=" * 100 +
        "\nSTOP: these governed tags do not exist (no tag policy):\n   " + "\n   ".join(missing) +
        "\n\nThe domains and their governed tags are created ONCE per account by the instructor in"
        "\nbootcamp/instructor/00_instructor_setup. Ask your instructor to run it (or check the tag names in the widgets"
        "\nat the top of this notebook), then run this notebook again.\n" + "=" * 100)
    print(msg)
    dbutils.notebook.exit(json.dumps({"status": "STOPPED", "reason": "governed tags missing", "missing": missing}))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Tag your gold schemas with their domain
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
            msg += "  -> you need the ASSIGN permission on this governed tag (instructor: 00_instructor_setup)"
        return msg


existing_schemas = {r[0] for r in spark.sql(f"SHOW SCHEMAS IN {q(catalog)}").collect()}
gold_list = ", ".join(lit(s) for s in GOLD_SCHEMAS)
have_schema_tags = {(r.schema_name, r.tag_name) for r in spark.sql(
    f"SELECT schema_name, tag_name FROM {q(catalog)}.information_schema.schema_tags WHERE schema_name IN ({gold_list})").collect()}
have_table_tags = {(r.schema_name, r.table_name, r.tag_name) for r in spark.sql(
    f"SELECT schema_name, table_name, tag_name FROM {q(catalog)}.information_schema.table_tags WHERE schema_name IN ({gold_list})").collect()}
verb = "SET" if action == "apply" else "UNSET"
schema_results = []
for s in GOLD_SCHEMAS:
    if s not in existing_schemas:
        schema_results.append((s, DOMAIN_TAG[s], "SKIPPED - schema does not exist (run 01 and the pipeline first)"))
        continue
    if ((s, DOMAIN_TAG[s]) in have_schema_tags) == (action == "apply"):   # nothing to do
        schema_results.append((s, DOMAIN_TAG[s], "already tagged" if action == "apply" else "not tagged"))
        continue
    err = run(f"ALTER SCHEMA {q(catalog, s)} {verb} TAGS ({lit(DOMAIN_TAG[s])})")
    schema_results.append((s, DOMAIN_TAG[s], err or f"{verb} OK"))
display(spark.createDataFrame(schema_results, "gold_schema string, domain_tag string, result string"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Tag your gold tables and metric views with their subdomain
# MAGIC
# MAGIC A subdomain tag is **not** inherited upwards and the parent tag is **not** applied automatically — that is
# MAGIC why step 4 tagged the schemas and this step tags each table. Gold tables are pipeline materialized views
# MAGIC (`ALTER TABLE ... SET TAGS` works on them and survives pipeline refreshes); metric views use `ALTER VIEW`.
# MAGIC About 80 statements, run in parallel threads (≈ 1 s each).

# COMMAND ----------

objects = spark.sql(f"""
    SELECT table_schema, table_name, table_type
    FROM {q(catalog)}.information_schema.tables
    WHERE table_schema IN ({', '.join(lit(s) for s in GOLD_SCHEMAS)})
      AND table_name NOT LIKE '\\_\\_%'          -- hide pipeline-internal tables
      AND table_name NOT LIKE 'event_log%'
""").collect()

todo, not_in_model, unchanged = [], [], []
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
missing_tables = sorted(f"{s}.{t}" for (s, t) in TABLE_TAG if (s, t) not in found)

print(f"Tagged objects : {sum(1 for e in errors if e is None)} of {len(todo)} to change "
      f"({len(unchanged)} already as wanted)")
print(f"Failed         : {sum(1 for e in errors if e is not None)}")
if missing_tables:
    print(f"Model tables not (yet) in your catalog: {len(missing_tables)} -> e.g. {missing_tables[:5]}"
          f"  (has the pipeline run?)")
if not_in_model:
    print(f"Objects without a subdomain (left untouched): {not_in_model[:10]}")
display(spark.createDataFrame(table_results, "gold_schema string, object string, type string, subdomain_tag string, result string")
        .orderBy("gold_schema", "object"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · (Optional) Tag your Genie Agent with its domains
# MAGIC
# MAGIC Genie Agents are workspace objects, so they are tagged with the **workspace entity tag assignments** API
# MAGIC (`POST /api/2.0/entity-tag-assignments`, Beta). The agent gets the domain tag of every gold schema it uses
# MAGIC (read from the agent's own data sources), so it shows up under *Consumer*, *Finance* and *Manufacturing*
# MAGIC in Discover. Subdomain tags (with `/`) cannot be assigned to workspace objects.

# COMMAND ----------

genie_result = []
if not genie_space_id:
    print("No genie_space_id given - skipped. (Find it in notebook 04's output or in the agent URL .../genie/rooms/<id>.)")
else:
    try:
        space = rest("GET", f"/api/2.0/genie/spaces/{genie_space_id}", query={"include_serialized_space": "true"})
        sources = json.loads(space.get("serialized_space") or "{}").get("data_sources", {})
        idents = [t["identifier"] for k in ("tables", "metric_views") for t in sources.get(k, [])]
        schemas = sorted({i.split(".")[1] for i in idents if i.split(".")[1] in DOMAIN_TAG})
        print(f"Agent '{space.get('title')}' uses {len(idents)} data sources in schemas {schemas}")
    except DatabricksError as e:
        schemas = ["consumer", "finance", "manufacturing"]
        print(f"Could not read the agent's sources ({str(e)[:100]}); using {schemas}")
    try:
        have = {t["tag_key"] for t in rest("GET", f"/api/2.0/entity-tag-assignments/geniespaces/{genie_space_id}/tags")
                .get("tag_assignments", [])}
    except DatabricksError:
        have = set()
    for s in schemas:
        key = DOMAIN_TAG[s]
        if (key in have) == (action == "apply"):
            genie_result.append((key, "already tagged" if action == "apply" else "not tagged"))
            continue
        try:
            if action == "apply":
                rest("POST", "/api/2.0/entity-tag-assignments",
                     {"entity_type": "geniespaces", "entity_id": genie_space_id, "tag_key": key})
            else:
                rest("DELETE", f"/api/2.0/entity-tag-assignments/geniespaces/{genie_space_id}/tags/{quote(key, safe='')}")
            genie_result.append((key, f"{verb} OK"))
        except DatabricksError as e:
            txt = str(e)
            ok = ("already exists" in txt.lower() and action == "apply") or ("not found" in txt.lower() and action == "remove")
            genie_result.append((key, f"{verb} OK (nothing to do)" if ok else f"FAILED: {txt[:200]}"))
    for k, r in genie_result:
        print(f"  {k:20} {r}")
    print(f"\nYour agent: {host}/genie/rooms/{genie_space_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Verify
# MAGIC
# MAGIC Tags are visible in `information_schema` (`schema_tags`, `table_tags`) — value-less tags have an empty
# MAGIC `tag_value`. Expected after `apply`: the 3 gold schemas (`consumer`, `finance`, `manufacturing`) with their
# MAGIC domain tag, every gold table (and metric view) with exactly one subdomain tag - on the first run and on
# MAGIC every re-run. After `remove`: zero rows.

# COMMAND ----------

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
expected_schemas = sum(1 for s in GOLD_SCHEMAS if s in existing_schemas)
expected_tables = len(todo) + len(unchanged)   # newly tagged now + already tagged before (re-run)
if action == "apply":
    ok = n_schema == expected_schemas and n_tables == expected_tables and not any(errors)
else:
    ok = n_schema == 0 and n_tables == 0
print(f"Schemas with a domain tag    : {n_schema} (expected {expected_schemas if action == 'apply' else 0})")
print(f"Objects with a subdomain tag : {n_tables} (expected {expected_tables if action == 'apply' else 0})")
if genie_space_id:
    try:
        tags = rest("GET", f"/api/2.0/entity-tag-assignments/geniespaces/{genie_space_id}/tags")
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
# MAGIC and example questions. The instructor imported these files as **Pages** (Discover → Pages, step A in
# MAGIC `bootcamp/context/README.md`) — Genie One now cites them. Below is the index (`bootcamp/context/glossary.csv`).

# COMMAND ----------

glossary_path = f"{CONTEXT_DIR}/glossary.csv"
if os.path.isfile(glossary_path):
    with open(glossary_path, encoding="utf-8", newline="") as fh:
        rows = [(r["domain"], r["subdomain"], r["term"], r["short_definition"], r["page_path"]) for r in csv.DictReader(fh)]
    display(spark.createDataFrame(rows, "domain string, subdomain string, term string, definition string, page string"))
else:
    print(f"{glossary_path} not found (is this the bootcamp Git folder?)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Attach the GitHub MCP to your Genie Agent (UI, 3 minutes)
# MAGIC
# MAGIC There is no API for MCP sources yet, so this is a UI step. Run the next cell for your personal click-path.
# MAGIC
# MAGIC Good to know:
# MAGIC * MCP tools work **only in Agent mode** (not in Chat mode).
# MAGIC * Every tool call runs with **your** GitHub account (OAuth sign-in in the *Configure* panel).
# MAGIC * The GitHub MCP reads **public** repositories by default. A private repository needs the
# MAGIC   [Databricks GitHub connector app](https://github.com/apps/databricks-github-connector) installed by a
# MAGIC   GitHub organisation admin. The instructor makes the bootcamp repository readable (public, or the
# MAGIC   connector app installed) before the event — if the agent cannot read `bootcamp/context/`, tell the instructor.
# MAGIC * Read tools (search, get file) run automatically; write tools would pause for **your approval**.

# COMMAND ----------

agent_url = f"{host}/genie/rooms/{genie_space_id}" if genie_space_id else "(open your agent from the Genie page)"
description = (
    "Business glossary of Fjällmark Consumer Goods. Before you answer a question that uses a business term "
    "(revenue, net revenue, GMV, margin, COGS, DSO, overdue, OEE, yield, scrap, active shopper, AOV, loyalty tier, "
    "CLTV segment, consent, subscription, return rate, plant, fiscal period, company code ...), read the matching "
    f"file in the GitHub repository {GITHUB_REPO}, folder bootcamp/context/domains/<domain>/pages/ (index: "
    "bootcamp/context/glossary.csv), and follow its business rules and calculation. Company facts (entities, "
    "currencies, plants, fiscal calendar) are in bootcamp/context/company_profile.md. Read only; never create "
    "issues, branches or pull requests."
)
print(f"""
1. Open your agent: {agent_url}
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
# MAGIC 1. **Discover → Pages → Create page** (or open a domain, e.g. *Consumer*, and create it there).
# MAGIC 2. Pick a concept that is **not** defined yet, for example *Subscription churn rate*, *Gold-member share of
# MAGIC    DTC sales*, *Line changeover loss* or *Revenue per active shopper*.
# MAGIC 3. Fill **Synonyms**, **Description** and the **Page body** — copy the structure of any file in
# MAGIC    `bootcamp/context/domains/*/pages/` (definition → business rules → calculation SQL → pitfalls → example
# MAGIC    questions), or let **Genie Code** draft it from `bootcamp/context/` (GitHub connection), your gold tables and the
# MAGIC    metric view.
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
    "schemas_with_domain_tag": n_schema,
    "objects_with_subdomain_tag": n_tables,
    "statements_run": len(todo) + sum(1 for r in schema_results if r[2].endswith(" OK")),   # 0 on a re-run
    "already_as_wanted": len(unchanged),
    "failed_statements": sum(1 for e in errors if e is not None),
    "model_tables_missing_in_catalog": len(missing_tables),
    "genie_agent": genie_space_id or None,
    "genie_agent_tags": [f"{k}: {r}" for k, r in genie_result],
    "ok": ok,
}
print(json.dumps(summary, indent=2))
dbutils.notebook.exit(json.dumps(summary))   # visible as the run output when this notebook runs as a job task
