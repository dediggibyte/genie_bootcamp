# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 05 · Business context of one domain - domains, subdomains, business terms
# MAGIC
# MAGIC **Run it through 05a (retail), 05b (mobility) or 05c (telecom)** - they call this notebook with their domain.
# MAGIC (Run directly, it uses the `domain` widget.)
# MAGIC
# MAGIC The data already says **what it is** (comments, keys, metric views, `ecom_*` tags) and **who may see what**
# MAGIC (notebook 03). This notebook adds **what the business means and who owns it**:
# MAGIC
# MAGIC | step | what | how |
# MAGIC |---|---|---|
# MAGIC | 1 | parameters | widgets |
# MAGIC | 2 | read the domain, its subdomains and business terms | `context/<domain>/_domain.md`, `<subdomain>/_subdomain.md`, `pages/*.md`, `context/2026-10-27-glossary.csv` |
# MAGIC | 3 | document them as **tables** Genie and SQL users can query | `context.domain_map`, `context.business_terms` |
# MAGIC | 4 | create (or check) the **domain and subdomains** in Unity Catalog | governed tags + Domains API (`create_domains = true`, needs permission) |
# MAGIC | 5 | file the **gold schema** into the domain and each **table / metric view** into its subdomain | value-less governed tags |
# MAGIC | 6 | file the domain's **Genie Agent** into the domain | workspace tag assignment |
# MAGIC | 7 | verify | `information_schema` |
# MAGIC | 8 | import the business terms as **Pages** and attach them to the agent | UI (prompt written here), GitHub MCP |
# MAGIC
# MAGIC A **domain** in Unity Catalog (Discover → Domains) *is* a governed tag: an asset belongs to the domain
# MAGIC `Nordvik Retail and Commerce` when it carries that tag, and to the subdomain
# MAGIC `Nordvik Retail and Commerce/Sales and Returns` when it carries that one.
# MAGIC
# MAGIC 🔁 **Re-running is a no-op**: existing tables rows, governed tags, domains and tag assignments are reported as
# MAGIC `unchanged` / `already tagged`. `action = remove` takes this domain's tags off again (the domains themselves are
# MAGIC removed by notebook 99).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | meaning |
# MAGIC |---|---|
# MAGIC | `domain` | `retail`, `mobility` or `telecom` (set by 05a / 05b / 05c) |
# MAGIC | `catalog` | blank = `ecom_<your short user name>` |
# MAGIC | `create_domains` | `true` = create the missing governed tags, domain and subdomains (needs permission to create tag policies and domains - an account / metastore admin). `false` = only check them |
# MAGIC | `publish_domains` | `true` = publish new domains (otherwise they stay drafts, visible to curators only) |
# MAGIC | `action` | `apply` (default) or `remove` this domain's tags from your schema, tables and agent |

# COMMAND ----------

import csv
import json
import os
import re
import unicodedata
from urllib.parse import quote

from databricks.sdk import WorkspaceClient

ALL_DOMAINS = ["retail", "mobility", "telecom"]
dbutils.widgets.dropdown("domain", "retail", ALL_DOMAINS, "1 Domain")
dbutils.widgets.text("catalog", "", "2 Catalog (blank = automatic)")
dbutils.widgets.dropdown("create_domains", "false", ["false", "true"], "3 Create domains (needs permission)")
dbutils.widgets.dropdown("publish_domains", "true", ["true", "false"], "4 Publish new domains")
dbutils.widgets.dropdown("action", "apply", ["apply", "remove"], "5 Action")

DATE = "2026-10-27"
MARKER = "[created by ecom bootcamp]"        # notebook 99 deletes only governed tags / domains with this marker
GITHUB_REPO = "dediggibyte/genie_bootcamp"
AGENTS = {"retail": "Nordvik Retail Analyst", "mobility": "Nordvik Mobility Analyst", "telecom": "Nordvik Connect Analyst"}
ICONS = {"retail": ("PACKAGE", "#1565C0"), "mobility": ("SPEEDOMETER", "#EF6C00"), "telecom": ("ADDRESS_BOOK", "#2E7D32")}
KEYWORD = {"MATERIALIZED_VIEW": "MATERIALIZED VIEW", "METRIC_VIEW": "VIEW", "VIEW": "VIEW"}   # anything else: TABLE


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
    raise FileNotFoundError("databricks.yml not found above this notebook - run it from the ecom Git folder.")


def api(method: str, path: str, query: dict = None, body: dict = None):
    return w.api_client.do(method, path, query=query, body=body)


def api_try(method: str, path: str, query: dict = None, body: dict = None):
    try:
        return api(method, path, query, body), None
    except Exception as e:
        return None, str(e).splitlines()[0][:300]


def list_all(path: str, key: str) -> list:
    """GET every page of a paginated list API."""
    items, token = [], None
    while True:
        resp = api("GET", path, query={"page_size": 100, **({"page_token": token} if token else {})})
        items += resp.get(key, [])
        token = resp.get("next_page_token")
        if not token:
            return items


def front_matter(path: str) -> dict:
    """YAML front matter of a context file: 'key: value' lines and '  - item' lists."""
    with open(path, encoding="utf-8") as fh:
        m = re.match(r"^---\n(.*?)\n---", fh.read(), re.S)
    out, key = {}, None
    for line in (m.group(1).splitlines() if m else []):
        if line.startswith("  - ") and key:
            out.setdefault(key, []).append(unquote(line[4:]))
            continue
        key, sep, value = line.partition(":")
        key = key.strip()
        if sep and value.strip():
            out[key] = unquote(value.strip())
    return out


def unquote(text: str) -> str:
    return json.loads(text) if text.startswith('"') else text


def q(*parts: str) -> str:
    return ".".join("`" + p.replace("`", "``") + "`" for p in parts)


def lit(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


w = WorkspaceClient()
host = w.config.host.rstrip("/")
user_name = spark.sql("SELECT current_user()").first()[0]
domain = dbutils.widgets.get("domain")
catalog = dbutils.widgets.get("catalog").strip() or f"ecom_{bundle_short_name(user_name)}"
create_domains = dbutils.widgets.get("create_domains") == "true"
publish_domains = dbutils.widgets.get("publish_domains") == "true"
action = dbutils.widgets.get("action")
BUNDLE_ROOT = bundle_root()
CONTEXT_DIR = f"{BUNDLE_ROOT}/context"
print(f"Domain: {domain} | catalog: {catalog} | create_domains: {create_domains} | action: {action}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · The domain, its subdomains and business terms (from `context/`)
# MAGIC
# MAGIC The context folder is the **single source**: it is generated, together with the Genie Agents, by
# MAGIC `tools/2026-10-27-build-semantics.py`. Which table belongs to which subdomain comes from the `ecom_subdomain`
# MAGIC tags of `config/2026-10-27-tags.json` - the same assignment job task `tags` applied as plain tags.

# COMMAND ----------

dom = front_matter(f"{CONTEXT_DIR}/{domain}/_domain.md")
DOMAIN_TAG = dom["domain_tag"]
subdomains = []
for key in sorted(os.listdir(f"{CONTEXT_DIR}/{domain}")):
    path = f"{CONTEXT_DIR}/{domain}/{key}/_subdomain.md"
    if os.path.isfile(path):
        fm = front_matter(path)
        fm["objects"] = [o.replace("<catalog>", catalog) for o in fm.get("objects", [])]
        subdomains.append(fm)
with open(f"{CONTEXT_DIR}/{DATE}-glossary.csv", encoding="utf-8", newline="") as fh:
    terms = [r for r in csv.DictReader(fh) if r["domain_key"] == domain]

print(f"Domain    : {dom['domain']} ({dom['business_unit']})  ->  governed tag '{DOMAIN_TAG}'")
print(f"Owner     : {dom['business_owner']} | {dom['technical_owner']}")
for s in subdomains:
    print(f"  Subdomain {s['subdomain']:<28} -> '{s['subdomain_tag']}'  ({len(s['objects'])} objects, "
          f"{sum(1 for t in terms if t['subdomain_key'] == s['subdomain_key'])} terms)")
display(spark.createDataFrame([(t["subdomain"], t["term"], t["short_definition"], f"{t['metric_view']}.{t['measure']}")
                               for t in terms], "subdomain string, term string, definition string, measure string"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Document the domain as tables: `context.domain_map` and `context.business_terms`
# MAGIC
# MAGIC Two small Delta tables in your schema `context` (one set of rows per domain, replaced only when the context
# MAGIC files changed). Anyone can now ask in SQL *"which subdomain owns `retail.fact_returns`?"* or *"how is ARPU
# MAGIC defined?"* - and they are a data source you can add to a Genie Agent.

# COMMAND ----------

spark.sql(f"""CREATE TABLE IF NOT EXISTS {q(catalog, 'context', 'domain_map')} (
  domain STRING COMMENT 'Business domain, e.g. Retail and Commerce',
  domain_tag STRING COMMENT 'Governed tag = Unity Catalog domain, e.g. Nordvik Retail and Commerce',
  business_owner STRING COMMENT 'Role that owns the domain',
  subdomain STRING COMMENT 'Subdomain, e.g. Sales and Returns',
  subdomain_tag STRING COMMENT 'Governed tag = Unity Catalog subdomain, e.g. Nordvik Retail and Commerce/Sales and Returns',
  object_name STRING COMMENT 'Fully qualified gold table or metric view of the subdomain',
  description STRING COMMENT 'What the subdomain holds')
COMMENT 'Nordvik Group domain map: which domain and subdomain owns which gold table and metric view (ecom bootcamp, notebooks 05a-c).'""")
spark.sql(f"""CREATE TABLE IF NOT EXISTS {q(catalog, 'context', 'business_terms')} (
  domain STRING COMMENT 'Business domain',
  subdomain STRING COMMENT 'Subdomain the term belongs to',
  term STRING COMMENT 'Business term, e.g. Net Revenue, ARPU',
  definition STRING COMMENT 'Short definition',
  metric_view STRING COMMENT 'Metric view that implements the term',
  measure STRING COMMENT 'Measure of the metric view',
  synonyms STRING COMMENT 'Other words users use, separated by ;',
  related_terms STRING COMMENT 'Related business terms, separated by ;',
  page_path STRING COMMENT 'Glossary page in the repository (full definition, SQL, reference value)')
COMMENT 'Nordvik Group business glossary: definitions of the business terms and the metric-view measure that implements each (ecom bootcamp, notebooks 05a-c).'""")

wanted = {
    "domain_map": sorted((dom["domain"], DOMAIN_TAG, dom["business_owner"], s["subdomain"], s["subdomain_tag"], o,
                          s["description"]) for s in subdomains for o in s["objects"]),
    "business_terms": sorted((t["domain"], t["subdomain"], t["term"], t["short_definition"], f"{catalog}.{t['metric_view']}",
                              t["measure"], t["synonyms"], t["related_terms"], t["page_path"]) for t in terms),
}
for table, rows in wanted.items():
    target = q(catalog, "context", table)
    have = sorted(tuple(r) for r in spark.sql(f"SELECT * FROM {target} WHERE domain = :d", {"d": dom["domain"]}).collect())
    if action == "remove":
        spark.sql(f"DELETE FROM {target} WHERE domain = :d", {"d": dom["domain"]})
        print(f"context.{table}: rows of {dom['domain']} removed")
    elif have == rows:
        print(f"context.{table}: unchanged ({len(rows)} rows)")
    else:
        spark.sql(f"DELETE FROM {target} WHERE domain = :d", {"d": dom["domain"]})
        spark.createDataFrame(rows, spark.table(target).schema).write.mode("append").saveAsTable(f"{catalog}.context.{table}")
        print(f"context.{table}: {len(rows)} rows written for {dom['domain']}")
display(spark.sql(f"SELECT subdomain, object_name FROM {q(catalog, 'context', 'domain_map')} "
                  f"WHERE domain = :d ORDER BY ALL", {"d": dom["domain"]}))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Create (or check) the domain and subdomains in Unity Catalog
# MAGIC
# MAGIC Rules of the Domains API (Beta), the same as in `bootcamp/instructor/00_instructor_setup.py`:
# MAGIC
# MAGIC 1. create the **governed tag** first - a tag policy **without values** (`POST /api/2.1/tag-policies`),
# MAGIC 2. create the **domain** with `tag_key` = that tag (`POST /api/2.0/domains`, created as a draft),
# MAGIC 3. each **subdomain** gets its own governed tag `<domain tag>/<Subdomain>` and `parent_domain_id`,
# MAGIC 4. **publish** with `PATCH /api/2.0/domains/<id>?update_mask=draft` (`draft = false`).
# MAGIC
# MAGIC Governed tags and domains live at **account / metastore level** and are shared by everyone. Creating them needs
# MAGIC permission (an account or metastore admin), so the default `create_domains = false` only **checks** them. Ask an
# MAGIC admin to run this notebook once with `create_domains = true` - or create them in Discover → Domains with the
# MAGIC names printed below. Existing ones (also from another participant) are **reused** as they are; what this notebook
# MAGIC creates carries the marker `[created by ecom bootcamp]` so notebook 99 removes only those.

# COMMAND ----------

PLAN = [(DOMAIN_TAG, None, dom["subtitle"], dom["description"])]
PLAN += [(s["subdomain_tag"], DOMAIN_TAG, f"{dom['domain']} - {s['subdomain']}", s["description"]) for s in subdomains]
icon, color = ICONS[domain]

policies, err_p = api_try("GET", "/api/2.1/tag-policies")
policies = {t["tag_key"]: t for t in list_all("/api/2.1/tag-policies", "tag_policies")} if err_p is None else {}
domains_api, err_d = api_try("GET", "/api/2.0/domains")
uc_domains = {d["tag_key"]: d for d in list_all("/api/2.0/domains", "domains")} if err_d is None else {}
if err_p or err_d:
    print(f"ℹ️ Tag-policy API: {err_p or 'OK'} | Domains API: {err_d or 'OK'}")

results = []
for key, parent, subtitle, description in PLAN:
    kind = "subdomain" if parent else "domain"
    # 1) governed tag (tag policy without values)
    if key in policies:
        results.append((kind, key, "governed tag", "exists"))
    elif create_domains and action == "apply":
        created, err = api_try("POST", "/api/2.1/tag-policies", body={"tag_key": key, "description": f"{description[:190]} {MARKER}"})
        results.append((kind, key, "governed tag", "created" if created else f"FAILED: {err}"))
        if created:
            policies[key] = created
    else:
        results.append((kind, key, "governed tag", "MISSING - needs create_domains = true (admin)"))
    # 2) domain / subdomain
    if key in uc_domains:
        d = uc_domains[key]
        results.append((kind, key, kind, "exists (" + ("draft" if d.get("effective_draft", d.get("draft")) else "published") + ")"))
    elif create_domains and action == "apply" and key in policies:
        parent_id = uc_domains.get(parent, {}).get("domain_id") if parent else None
        if parent and not parent_id:
            results.append((kind, key, kind, "SKIPPED - parent domain missing"))
            continue
        body = {"tag_key": key, "draft": True, "subtitle": subtitle[:120], "description": f"{description} {MARKER}",
                "icon": {"name": icon, "color": color}, **({"parent_domain_id": parent_id} if parent_id else {})}
        created, err = api_try("POST", "/api/2.0/domains", body=body)
        results.append((kind, key, kind, "created (draft)" if created else f"FAILED: {err}"))
        if created:
            uc_domains[key] = created
    else:
        results.append((kind, key, kind, "MISSING" + ("" if create_domains else " - needs create_domains = true (admin)")))
    # 3) publish
    d = uc_domains.get(key)
    if d and publish_domains and action == "apply" and d.get("effective_draft", d.get("draft", False)) \
            and MARKER in (d.get("description") or ""):
        updated, err = api_try("PATCH", f"/api/2.0/domains/{d['domain_id']}", query={"update_mask": "draft"},
                               body={"draft": False})
        results.append((kind, key, "publish", "published" if updated else f"FAILED: {err}"))
        if updated:
            uc_domains[key] = updated
display(spark.createDataFrame(results, "level string, governed_tag string, object string, result string"))
tags_ready = {key for key, *_ in PLAN if key in policies}
if DOMAIN_TAG not in tags_ready:
    print(f"⚠️ The governed tag '{DOMAIN_TAG}' does not exist yet: steps 5 and 6 are skipped. Run this notebook with "
          f"create_domains = true as an admin (or ask one), then run it again.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · File the gold schema into the domain and each object into its subdomain
# MAGIC
# MAGIC Domain tags are **value-less** governed tags: `ALTER SCHEMA <catalog>.retail SET TAGS ('Nordvik Retail and
# MAGIC Commerce')`. A schema tag is **inherited** by every table and metric view in it, so the whole schema appears under
# MAGIC the domain. A subdomain tag is not inherited, so each object gets its own:
# MAGIC `ALTER MATERIALIZED VIEW <catalog>.retail.fact_sales SET TAGS ('Nordvik Retail and Commerce/Sales and Returns')`.
# MAGIC You need the **ASSIGN** permission on the governed tags (the admin who created them grants it).

# COMMAND ----------


def run(stmt: str):
    try:
        spark.sql(stmt)
        return None
    except Exception as e:
        msg = str(e).split("\n")[0][:300]
        if "PERMISSION_DENIED" in msg or "ASSIGN" in msg.upper():
            msg += "  -> you need the ASSIGN permission on this governed tag (ask the admin who created it)"
        return msg


verb = "SET" if action == "apply" else "UNSET"
types = {f"{catalog}.{r.table_schema}.{r.table_name}": r.table_type for r in spark.sql(
    f"SELECT table_schema, table_name, table_type FROM {q(catalog)}.information_schema.tables "
    f"WHERE table_schema = :s", {"s": domain}).collect()}
have_schema = {r.tag_name for r in spark.sql(
    f"SELECT tag_name FROM {q(catalog)}.information_schema.schema_tags WHERE schema_name = :s", {"s": domain}).collect()}
have_table = {(f"{catalog}.{r.schema_name}.{r.table_name}", r.tag_name) for r in spark.sql(
    f"SELECT schema_name, table_name, tag_name FROM {q(catalog)}.information_schema.table_tags WHERE schema_name = :s",
    {"s": domain}).collect()}

tag_results = []
if DOMAIN_TAG in tags_ready:
    if (DOMAIN_TAG in have_schema) == (action == "apply"):
        tag_results.append((f"{catalog}.{domain}", "SCHEMA", DOMAIN_TAG, "already tagged" if action == "apply" else "not tagged"))
    else:
        err = run(f"ALTER SCHEMA {q(catalog, domain)} {verb} TAGS ({lit(DOMAIN_TAG)})")
        tag_results.append((f"{catalog}.{domain}", "SCHEMA", DOMAIN_TAG, err or f"{verb} OK"))
    for s in subdomains:
        for obj in s["objects"]:
            if obj not in types:
                tag_results.append((obj, "-", s["subdomain_tag"], "SKIPPED - object missing (run ecom_job)"))
            elif s["subdomain_tag"] not in tags_ready:
                tag_results.append((obj, types[obj], s["subdomain_tag"], "SKIPPED - governed tag missing"))
            elif ((obj, s["subdomain_tag"]) in have_table) == (action == "apply"):
                tag_results.append((obj, types[obj], s["subdomain_tag"], "already tagged" if action == "apply" else "not tagged"))
            else:
                err = run(f"ALTER {KEYWORD.get(types[obj], 'TABLE')} {q(*obj.split('.'))} {verb} TAGS ({lit(s['subdomain_tag'])})")
                tag_results.append((obj, types[obj], s["subdomain_tag"], err or f"{verb} OK"))
if tag_results:
    display(spark.createDataFrame(tag_results, "object string, type string, governed_tag string, result string"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · File the Genie Agent into the domain
# MAGIC
# MAGIC Notebook 04 built one agent per domain. It gets the domain's governed tag as a **workspace tag assignment**
# MAGIC (`POST /api/2.0/entity-tag-assignments`, entity type `geniespaces`), so Discover lists it under the domain.

# COMMAND ----------

agent_title = f"{AGENTS[domain]} ({catalog})"
agent_result = "skipped - governed tag missing"
spaces = [s for s in list_all("/api/2.0/genie/spaces", "spaces") if s.get("title") == agent_title]
if not spaces:
    agent_result = f"agent '{agent_title}' not found - run notebook 04 first"
elif DOMAIN_TAG in tags_ready:
    space_id = spaces[0]["space_id"]
    tags, err = api_try("GET", f"/api/2.0/entity-tag-assignments/geniespaces/{space_id}/tags")
    have = {t["tag_key"] for t in (tags or {}).get("tag_assignments", [])}
    if err:
        agent_result = f"FAILED: {err}"
    elif (DOMAIN_TAG in have) == (action == "apply"):
        agent_result = "already tagged" if action == "apply" else "not tagged"
    elif action == "apply":
        _, err = api_try("POST", "/api/2.0/entity-tag-assignments",
                         body={"entity_type": "geniespaces", "entity_id": space_id, "tag_key": DOMAIN_TAG})
        agent_result = err and f"FAILED: {err}" or "tagged"
    else:
        _, err = api_try("DELETE", f"/api/2.0/entity-tag-assignments/geniespaces/{space_id}/tags/{quote(DOMAIN_TAG, safe='')}")
        agent_result = err and f"FAILED: {err}" or "untagged"
print(f"{agent_title}: {agent_result}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Verify
# MAGIC
# MAGIC Every object of the domain with its plain `ecom_subdomain` tag (job task `tags`) next to its governed subdomain
# MAGIC tag (this notebook). In the UI: **Discover → Domains → Nordvik ...** lists your schema, tables, metric views and
# MAGIC agent; Catalog Explorer → a table → *Tags* shows the tags.

# COMMAND ----------

display(spark.sql(f"""
    SELECT m.subdomain, m.object_name,
           max(CASE WHEN t.tag_name = 'ecom_subdomain' THEN t.tag_value END) AS ecom_subdomain,
           max(CASE WHEN t.tag_name = m.subdomain_tag THEN t.tag_name END) AS governed_subdomain_tag
    FROM {q(catalog, 'context', 'domain_map')} m
    LEFT JOIN {q(catalog)}.information_schema.table_tags t
      ON concat_ws('.', t.catalog_name, t.schema_name, t.table_name) = m.object_name
    WHERE m.domain = :d
    GROUP BY ALL ORDER BY ALL""", {"d": dom["domain"]}))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8 · The business terms as Pages - and in your Genie Agent
# MAGIC
# MAGIC **Pages** (Discover → Pages) have no API: only **Genie Code → Bulk import pages** in the Page editor creates
# MAGIC them. The cell below writes the exact prompt for this domain:
# MAGIC
# MAGIC 1. **Discover → Pages → Create page** → Genie Code icon → **Bulk import pages**.
# MAGIC 2. **+ → Add context**: add the `pages` folder and the glossary file (paths below).
# MAGIC 3. Paste the prompt, review the proposed Pages and let Genie Code create them (as **drafts**).
# MAGIC
# MAGIC **Agent mode + GitHub MCP:** open the agent → switch to **Agent** → *Configure* → *Sources* → *Add* →
# MAGIC **MCP services** → `system.ai.github`, with the description printed below. The agent then reads the term pages
# MAGIC live before it answers definition questions. (MCP sources work in Agent mode only and need the workspace setting
# MAGIC *MCP tools in Genie Agents*; the page links point to the `main` branch, so merge this project first.)

# COMMAND ----------

pages_dir = f"{CONTEXT_DIR}/{domain}/pages"
glossary_path = f"{CONTEXT_DIR}/{DATE}-glossary.csv"
filing = "; ".join(f"subdomain '{s['subdomain']}' -> '{s['subdomain_tag']}'" for s in subdomains)
prompt = (
    f"Bulk import the Nordvik Group business glossary for the domain '{DOMAIN_TAG}'. Use only the attached workspace "
    f"files as sources: the index {glossary_path} and the term pages in the folder {pages_dir}. Create exactly one Page "
    f"per index row whose domain_key column is '{domain}' ({len(terms)} terms: {', '.join(t['term'] for t in terms)}) - "
    f"no other terms, do not merge or split terms. For each row read the Markdown file named in page_path and fill the "
    f"Page from its YAML front matter and body: Page name = title; Synonyms = synonyms; Description = description; Page "
    f"body = the Markdown after the front matter word for word, except that every '<catalog>' becomes '{catalog}'; "
    f"Related assets = related_assets with '<catalog>' replaced by '{catalog}'; Sources (links only, https) = the single "
    f"link https://github.com/{GITHUB_REPO}/blob/main/<page_path> of the row. File each Page under its subdomain: "
    f"{filing}. If a Page with the same name already exists, flag it as a duplicate instead of creating a second one. "
    f"Create all Pages as drafts; do not publish.")
mcp_description = (
    f"Nordvik Group business glossary in the GitHub repository `{GITHUB_REPO}`, folder `ecom/context/{domain}/` (term "
    f"pages under `pages/`, index `ecom/context/{DATE}-glossary.csv`). Read the relevant page before answering questions "
    f"about KPI definitions, regions, segments or reference values.")
if action == "apply":
    print(f"Open: {host}/discover/pages  ->  Create page  ->  Genie Code  ->  Bulk import pages\n")
    print(f"Add context:  {pages_dir}   and   {glossary_path}\n")
    print(f"Prompt:\n{prompt}\n")
    print(f"GitHub MCP source description for '{agent_title}':\n{mcp_description}")

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"domain": domain, "catalog": catalog, "domain_tag": DOMAIN_TAG,
                                  "subdomains": [s["subdomain"] for s in subdomains], "terms": len(terms),
                                  "uc_domains": [r for r in results], "tags": len(tag_results), "agent": agent_result}))
