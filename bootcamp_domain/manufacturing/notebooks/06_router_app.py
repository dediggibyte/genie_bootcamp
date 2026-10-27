# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # 06 · One entry point — the Fjällmark Manufacturing router app over your Manufacturing Analyst
# MAGIC
# MAGIC Step 4 gave you the *Fjällmark Manufacturing Analyst* Genie Agent. Business users also ask what a term **means**
# MAGIC ("How is OEE defined?") before they ask for the number. This notebook deploys a **custom agent as a
# MAGIC Databricks App** - built from the Databricks app template *Custom Agent (Advanced)* (`agent-openai-advanced`:
# MAGIC OpenAI Agents SDK, chat UI, conversation memory and long-running tasks in Lakebase) - that answers both:
# MAGIC
# MAGIC ```text
# MAGIC   you ──► Fjällmark Manufacturing router app ──┬──► lookup_glossary   (function tool)  ──► app/glossary/ (definitions, rules, SQL)
# MAGIC          (chat UI, memory)                     └──► Manufacturing Analyst   (Genie MCP)      ──► `manufacturing`, `finance` + metric views
# MAGIC ```
# MAGIC
# MAGIC The router never queries data itself. It looks the business term up in the official Manufacturing glossary (a copy
# MAGIC of the Manufacturing pages of `bootcamp/context/` in `app/glossary/`), then asks the analyst through its **managed
# MAGIC Genie MCP server** (`/api/2.0/mcp/genie/<space_id>`) with that definition, and names both in its answer.
# MAGIC Questions about other domains are declined with a pointer to the full bootcamp router (`bootcamp/`).
# MAGIC
# MAGIC 🔐 **Governance does not change.** The app calls the Genie Agent as its own **service principal**, and Unity
# MAGIC Catalog governs that principal like any user (step 5b): `SELECT` on the sample's gold schemas only, and a copy
# MAGIC of **your** rows in the step 3 mapping table (`governance.user_plant_access`: your plants), with no cost and no PII access: cost figures and personal data stay masked in the app. An unmapped
# MAGIC principal would see no governed rows at all.
# MAGIC
# MAGIC | step | what |
# MAGIC |---|---|
# MAGIC | 1 | parameters |
# MAGIC | 2 | find your Manufacturing Analyst (built by notebook 04) |
# MAGIC | 3 | the app's MLflow experiment (traces of every conversation) |
# MAGIC | 4 | the sample's Lakebase project and your branch of it (conversation memory) |
# MAGIC | 5 | create or update the app with its resources, and give its service principal access to your data |
# MAGIC | 6 | deploy the code in `bootcamp_domain/manufacturing/app/` and wait until it runs |
# MAGIC | 7 | try it |
# MAGIC
# MAGIC ▶ **How to run:** Serverless compute → **Run all** (most of the time is the app's first start).
# MAGIC
# MAGIC 🔁 **Re-running is safe.** Everything is found by name and only created when missing; a re-run deploys the
# MAGIC current code of `bootcamp_domain/manufacturing/app/` again (same app, same URL).

# COMMAND ----------

# DBTITLE 1,Parameters
# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | meaning |
# MAGIC |---|---|
# MAGIC | `catalog` | leave **blank** for `cpg_manufacturing_<your short user name>` (the catalog of your Manufacturing Analyst) |
# MAGIC | `app_name` | blank = `mfg-router-<short name>` (at most 30 characters: lower-case letters, digits, `-`) |
# MAGIC | `llm_endpoint` | the model that routes and writes the answer; blank = `databricks-claude-sonnet-5-5`, or the first Claude Sonnet endpoint you can use |
# MAGIC | `lakebase_project` | the Lakebase project for the app's memory; default `fjallmark-manufacturing-sample`. Created by this notebook when it does not exist (you own it), otherwise reused |

# COMMAND ----------

# DBTITLE 1,Setup and parameters
import hashlib
import json
import os
import re
import time
import unicodedata

import pandas as pd
import yaml
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

dbutils.widgets.text("catalog", "", "1 Catalog (blank = automatic)")
dbutils.widgets.text("app_name", "", "2 App name (blank = automatic)")
dbutils.widgets.text("llm_endpoint", "", "3 Router model endpoint (blank = automatic)")
dbutils.widgets.text("lakebase_project", "fjallmark-manufacturing-sample", "4 Lakebase project")

DOMAINS = ["manufacturing", "finance"]   # the gold schemas of this sample
MAIN_DOMAIN = "manufacturing"
PREFIX = "mfg"
TITLE = "Manufacturing"
# Row-filter mapping tables of notebook 03 whose rows of yours are copied to the app (a missing table is skipped).
# Never the *_readers tables: the app gets no PII (or cost) access.
MAPPING_TABLES = ["user_plant_access"]
PREFERRED_LLM = "databricks-claude-sonnet-5-5"
LAKEBASE_BRANCH = "production"
APP_DIR = "app"   # bootcamp_domain/manufacturing/app/ - the router app's code


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}: the part before '@',
    lower-cased, every character that is not a letter or digit replaced by '_'."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


def bundle_root() -> str:
    """The folder that holds databricks.yml (= bootcamp_domain/manufacturing/; this notebook lives below it)."""
    try:
        nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        d = os.path.dirname(nb_path if nb_path.startswith("/Workspace") else "/Workspace" + nb_path)
    except Exception:
        d = os.getcwd()
    while d not in ("", "/"):
        if os.path.isfile(f"{d}/databricks.yml"):
            return d
        d = os.path.dirname(d)
    raise FileNotFoundError("databricks.yml not found above this notebook - run it from the repository's Git folder.")


def resource_id(text: str, max_len: int) -> str:
    """Lower-case letters, digits and '-', at most max_len characters (a hash keeps long names unique)."""
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()).strip("-")
    if len(slug) <= max_len:
        return slug
    digest = hashlib.md5(slug.encode()).hexdigest()[:4]
    return f"{slug[:max_len - 5].rstrip('-')}-{digest}"


w = WorkspaceClient()
host = w.config.host.rstrip("/")
me = w.current_user.me()
user_name = me.user_name
short = bundle_short_name(user_name)
catalog = dbutils.widgets.get("catalog").strip() or f"cpg_{MAIN_DOMAIN}_{short}"
app_name = dbutils.widgets.get("app_name").strip() or resource_id(f"{PREFIX}-router-{short}", 30)
if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,29}", app_name):
    raise ValueError(f"app_name {app_name!r}: at most 30 lower-case letters, digits and '-'")
project = dbutils.widgets.get("lakebase_project").strip()
if not project:
    raise ValueError("lakebase_project is blank - enter a project name (default fjallmark-manufacturing-sample).")
branch = f"projects/{project}/branches/{LAKEBASE_BRANCH}"
BUNDLE_ROOT = bundle_root()
source_code_path = f"{BUNDLE_ROOT}/{APP_DIR}"
if not os.path.isfile(f"{source_code_path}/app.yaml"):
    raise FileNotFoundError(f"{source_code_path}/app.yaml not found - pull the latest Git folder.")


def pick_llm(wanted: str) -> str:
    names = [e.name for e in w.serving_endpoints.list()]
    if wanted:
        if wanted not in names:
            raise ValueError(f"Serving endpoint {wanted!r} not found (or not visible to you).")
        return wanted
    if PREFERRED_LLM in names:
        return PREFERRED_LLM
    sonnet = sorted((n for n in names if "claude-sonnet" in n), reverse=True)
    if not sonnet:
        raise ValueError("No Claude Sonnet serving endpoint visible - enter one in the 'llm_endpoint' widget.")
    return sonnet[0]


llm_endpoint = pick_llm(dbutils.widgets.get("llm_endpoint").strip())
print(f"You are          : {user_name}")
print(f"Catalog          : {catalog}")
print(f"App              : {app_name}")
print(f"Router model     : {llm_endpoint}")
print(f"Lakebase project : {project} (your branch is created from {LAKEBASE_BRANCH})")
print(f"App code         : {source_code_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Your Manufacturing Analyst
# MAGIC
# MAGIC Found by the title notebook 04 gives it: `Fjällmark Manufacturing Analyst (<catalog>)`. The app gets it as a
# MAGIC **resource** (`genie_space`, permission *Can run*); the router reads the space ID from its environment.

# COMMAND ----------

title = f"Fjällmark {TITLE} Analyst ({catalog})"
space_id, token = None, None
while space_id is None:
    resp = w.api_client.do("GET", "/api/2.0/genie/spaces", query={"page_size": 100, **({"page_token": token} if token else {})})
    space_id = next((s["space_id"] for s in resp.get("spaces", []) if s.get("title") == title), None)
    token = resp.get("next_page_token")
    if not token:
        break
display(pd.DataFrame([{"domain": MAIN_DOMAIN, "agent": title, "space_id": space_id or "MISSING"}]))
if not space_id:
    raise RuntimeError(f"Genie Agent not found: {title!r}. Run notebook 04 first (same catalog), then re-run this notebook.")
# The SQL warehouse the agent runs its SQL on.
warehouse_id = w.api_client.do("GET", f"/api/2.0/genie/spaces/{space_id}")["warehouse_id"]
print(f"SQL warehouse of the agent: {warehouse_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · MLflow experiment for the traces
# MAGIC
# MAGIC Every conversation with the router is traced with MLflow: the glossary look-ups, the question it sent to the
# MAGIC analyst, the Genie answer, the final reply. Open the experiment after you tried the app (*Traces* tab).

# COMMAND ----------

experiment_path = f"/Users/{user_name}/fjallmark_{MAIN_DOMAIN}_router_{catalog}"
try:
    experiment_id = w.api_client.do("GET", "/api/2.0/mlflow/experiments/get-by-name",
                                    query={"experiment_name": experiment_path})["experiment"]["experiment_id"]
    print(f"Experiment exists : {experiment_path} ({experiment_id})")
except NotFound:
    experiment_id = w.api_client.do("POST", "/api/2.0/mlflow/experiments/create",
                                    body={"name": experiment_path})["experiment_id"]
    print(f"Experiment created: {experiment_path} ({experiment_id})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · The Lakebase project and your branch of it
# MAGIC
# MAGIC The template keeps conversation memory (and long-running tasks, and the chat UI's history) in **Lakebase**
# MAGIC Postgres, in the branch's default database `databricks_postgres` and in fixed schema names.
# MAGIC
# MAGIC * **The project** (widget `lakebase_project`, default `fjallmark-manufacturing-sample`): when it does not exist, this
# MAGIC   notebook **creates** it (autoscaling 0.5-4 CU, suspends after 10 idle minutes) and **you own it** - share it
# MAGIC   (*Can use*) with colleagues who deploy their own router app from this sample, or let each one create their own.
# MAGIC   When it exists, it is reused.
# MAGIC * **Your branch** of it: a copy-on-write branch of `production` with its own database and its own compute
# MAGIC   endpoint (it suspends when idle), so the apps of different users never share tables. The app's service
# MAGIC   principal gets *Can connect and create* on the branch's database through the app resource and creates its
# MAGIC   tables at its first start.

# COMMAND ----------

pg = lambda method, path, **kw: w.api_client.do(method, f"/api/2.0/postgres/{path}", **kw)  # noqa: E731
my_branch = f"projects/{project}/branches/{resource_id(f'{PREFIX}-router-{short}', 63)}"
database_name = f"{my_branch}/databases/databricks-postgres"
LAKEBASE_SPEC = {"spec": {"display_name": f"Fjällmark {TITLE} sample - router app memory",
                          "default_endpoint_settings": {"autoscaling_limit_min_cu": 0.5, "autoscaling_limit_max_cu": 4,
                                                        "suspend_timeout_duration": "600s"}}}


def wait_operation(op: dict, what: str, timeout_s: int = 600) -> dict:
    deadline = time.time() + timeout_s
    while not op.get("done") and time.time() < deadline:
        time.sleep(5)
        op = pg("GET", op["name"])
    if op.get("error") or not op.get("done"):
        raise RuntimeError(f"{what} failed: {op.get('error') or f'not done after {timeout_s // 60} minutes'}")
    return op


try:
    proj = pg("GET", f"projects/{project}")
    print(f"Project exists : {project} (owner {(proj.get('status') or {}).get('owner')})")
except NotFound:
    wait_operation(pg("POST", "projects", query={"project_id": project}, body=LAKEBASE_SPEC),
                   f"Creating the Lakebase project {project}")
    print(f"Project created: {project} (autoscaling 0.5-4 CU, branch {LAKEBASE_BRANCH}) - you own it")

try:
    pg("GET", my_branch)
    print(f"Branch exists : {my_branch}")
except NotFound:
    wait_operation(pg("POST", f"projects/{project}/branches", query={"branch_id": my_branch.rsplit("/", 1)[1]},
                      body={"spec": {"source_branch": branch, "no_expiry": True}}),
                   "Creating your Lakebase branch")
    print(f"Branch created: {my_branch} (from {branch})")
endpoints = pg("GET", f"{my_branch}/endpoints").get("endpoints", [])
print(f"Database      : {database_name}")
print(f"Endpoints     : {[(e['name'].rsplit('/', 1)[1], (e.get('status') or {}).get('current_state')) for e in endpoints]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Create or update the app
# MAGIC
# MAGIC The app's **resources** are what it may use, granted to the app's service principal; `app.yaml` maps each
# MAGIC one to an environment variable (`valueFrom`):
# MAGIC
# MAGIC | resource | what | permission | env var |
# MAGIC |---|---|---|---|
# MAGIC | `genie-manufacturing` | your Manufacturing Analyst | Can run | `GENIE_SPACE_MANUFACTURING` |
# MAGIC | `sql-warehouse` | the SQL warehouse the agent runs its SQL on | Can use | - |
# MAGIC | `llm-endpoint` | the router's model | Can query | `LLM_ENDPOINT` |
# MAGIC | `experiment` | the MLflow experiment of step 3 | Can edit | `MLFLOW_EXPERIMENT_ID` |
# MAGIC | `postgres` | the database of your Lakebase branch (step 4) | Can connect and create | `LAKEBASE_AUTOSCALING_ENDPOINT` |
# MAGIC
# MAGIC The app gets **no** user authorization scopes: it never acts in the name of the person using it. Its data
# MAGIC access is granted to its service principal in Unity Catalog (step 5b).

# COMMAND ----------

resources = [
    {"name": f"genie-{MAIN_DOMAIN}", "description": title,
     "genie_space": {"name": title, "space_id": space_id, "permission": "CAN_RUN"}},
    {"name": "sql-warehouse", "description": "SQL warehouse of the Genie Agent",
     "sql_warehouse": {"id": warehouse_id, "permission": "CAN_USE"}},
    {"name": "llm-endpoint", "description": "Router model",
     "serving_endpoint": {"name": llm_endpoint, "permission": "CAN_QUERY"}},
    {"name": "experiment", "description": "Traces of the router",
     "experiment": {"experiment_id": experiment_id, "permission": "CAN_EDIT"}},
    {"name": "postgres", "description": "Conversation memory",
     "postgres": {"branch": my_branch, "database": database_name, "permission": "CAN_CONNECT_AND_CREATE"}},
]
spec = {"description": f"Fjällmark {TITLE} router - one chat entry point for the {TITLE} Analyst ({catalog})",
        "resources": resources, "user_api_scopes": []}


def wait_app(name: str, timeout_s: int = 900) -> dict:
    """Wait until the app's compute is ACTIVE (or STOPPED) and no update is pending."""
    deadline = time.time() + timeout_s
    while True:
        app = w.api_client.do("GET", f"/api/2.0/apps/{name}")
        compute = (app.get("compute_status") or {}).get("state")
        if compute in ("ACTIVE", "STOPPED", "ERROR") or time.time() > deadline:
            return app
        print(f"  compute {compute} ...")
        time.sleep(15)


try:
    w.api_client.do("GET", f"/api/2.0/apps/{app_name}")
    w.api_client.do("PATCH", f"/api/2.0/apps/{app_name}", body={"name": app_name, **spec})
    print(f"App exists - resources updated: {app_name}")
except NotFound:
    w.api_client.do("POST", "/api/2.0/apps", body={"name": app_name, **spec})
    print(f"App created: {app_name}")
app = wait_app(app_name)
if (app.get("compute_status") or {}).get("state") == "STOPPED":
    w.api_client.do("POST", f"/api/2.0/apps/{app_name}/start")
    app = wait_app(app_name)

# Resource grants reach the service principal asynchronously; the app reads its experiment at start-up, so wait
# until the grant is visible before deploying (an update of an existing app can otherwise start too early).
sp = app.get("service_principal_client_id")   # also what current_user() returns for the app (step 5b)
for _ in range(24):
    acl = w.api_client.do("GET", f"/api/2.0/permissions/experiments/{experiment_id}").get("access_control_list", [])
    if any(a.get("service_principal_name") == sp for a in acl):
        break
    time.sleep(5)
else:
    print("Warning: the app's experiment permission is not visible yet - if the app crashes at start, re-run step 6.")
print(f"Compute          : {(app.get('compute_status') or {}).get('state')} - {(app.get('compute_status') or {}).get('message', '')}")
print(f"Service principal: {app.get('service_principal_name')} ({sp})")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 5b · Give the app's service principal access to your data
# MAGIC
# MAGIC The resources above cover Genie, the warehouse, the model, the experiment and Lakebase. The **data** is granted
# MAGIC in Unity Catalog, by you as the catalog owner - the same least-privilege rules as for a colleague (notebook 03):
# MAGIC
# MAGIC | grant | why |
# MAGIC |---|---|
# MAGIC | `USE CATALOG` on your catalog | see the catalog |
# MAGIC | `USE SCHEMA`, `SELECT` on `manufacturing`, `finance` | the gold tables and metric views the agent queries - never `landing`, `bronze`, `silver` (ungoverned) or `governance` |
# MAGIC | your rows in `governance.user_plant_access`: your plants | the row filters let it see what you see (no row = no governed rows) |
# MAGIC
# MAGIC It gets **no** row in the `governance.*_readers` tables (no cost and no PII access: cost figures and personal data stay masked in the app); a row it may have from an
# MAGIC earlier run is removed. Re-run this cell after you change your own mapping in notebook 03.

# COMMAND ----------

grants = [f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{sp}`"] + [
    f"GRANT USE SCHEMA, SELECT ON SCHEMA `{catalog}`.`{d}` TO `{sp}`" for d in DOMAINS]
for g in grants:
    spark.sql(g)
    print(f"OK  {g}")

governance_tables = {r.tableName for r in spark.sql(f"SHOW TABLES IN `{catalog}`.governance").collect()}
sp_mapping = {}
for table in MAPPING_TABLES:
    mapping = f"`{catalog}`.governance.{table}"
    if table not in governance_tables:
        print(f"Skipped {mapping}: does not exist (did you run notebook 03?)")
        continue
    # Copy your rows column by column: the app gets exactly your mapping, whatever the mapping columns are.
    cols = [c for c in spark.table(mapping).columns if c != "user_email"]
    col_list = ", ".join(f"`{c}`" for c in cols)
    spark.sql(f"DELETE FROM {mapping} WHERE lower(user_email) = lower(:sp)", {"sp": sp})
    spark.sql(f"INSERT INTO {mapping} (user_email, {col_list}) "
              f"SELECT :sp, {col_list} FROM {mapping} WHERE lower(user_email) = lower(:me)", {"sp": sp, "me": user_name})
    rows = [tuple(r) for r in spark.sql(f"SELECT {col_list} FROM {mapping} WHERE lower(user_email) = lower(:sp)",
                                        {"sp": sp}).collect()]
    sp_mapping[table] = sorted(str(r[0] if len(r) == 1 else r) for r in rows)
    if not rows:
        print(f"Note: you have no row in {mapping} - the app will see no rows governed by it.")
    print(f"Row filter mapping of the app in {table}: {sp_mapping[table] or 'none'} (same as yours, {user_name})")

# No PII or cost access: remove any row of the app from the *_readers tables.
for table in sorted(t for t in governance_tables if t.endswith("_readers")):
    if "user_email" not in spark.table(f"`{catalog}`.governance.{table}").columns:
        continue
    spark.sql(f"DELETE FROM `{catalog}`.governance.{table} WHERE lower(user_email) = lower(:sp)", {"sp": sp})
    print(f"No access for the app in governance.{table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Deploy the code
# MAGIC
# MAGIC The code is the folder `bootcamp_domain/manufacturing/app/` of your Git folder: `agent_server/agent.py` is the router
# MAGIC (read its instructions and the `lookup_glossary` tool), `glossary/` the Manufacturing glossary it reads, the rest
# MAGIC comes from the template. The deployment passes the environment of `app.yaml` plus `CATALOG` (your catalog: the
# MAGIC glossary's SQL uses the placeholder `<catalog>`, which the tool replaces). At its first start the app installs
# MAGIC its Python packages, downloads the chat UI and creates its tables in your Lakebase branch - give it a few minutes.

# COMMAND ----------

with open(f"{source_code_path}/app.yaml", encoding="utf-8") as f:
    app_env = yaml.safe_load(f).get("env", [])
env_vars = [{"name": e["name"], **({"value_from": e["valueFrom"]} if "valueFrom" in e else {"value": str(e.get("value", ""))})}
            for e in app_env if e["name"] != "CATALOG"] + [{"name": "CATALOG", "value": catalog}]
deployment = w.api_client.do("POST", f"/api/2.0/apps/{app_name}/deployments",
                             body={"source_code_path": source_code_path, "mode": "SNAPSHOT", "env_vars": env_vars})
deployment_id = deployment["deployment_id"]
print(f"Deployment {deployment_id} started from {source_code_path} (CATALOG={catalog})")
deadline = time.time() + 1200
while True:
    d = w.api_client.do("GET", f"/api/2.0/apps/{app_name}/deployments/{deployment_id}")
    state = (d.get("status") or {}).get("state")
    if state in ("SUCCEEDED", "FAILED", "CANCELLED") or time.time() > deadline:
        break
    print(f"  {state}: {(d.get('status') or {}).get('message', '')}")
    time.sleep(20)
app = w.api_client.do("GET", f"/api/2.0/apps/{app_name}")
app_state = (app.get("app_status") or {}).get("state")
print(f"Deployment : {state} - {(d.get('status') or {}).get('message', '')}")
print(f"App status : {app_state} - {(app.get('app_status') or {}).get('message', '')}")
if state != "SUCCEEDED":
    raise RuntimeError(f"Deployment {state}. Open the app in Compute → Apps → {app_name} → Logs, fix, and re-run this cell.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Try it
# MAGIC
# MAGIC Open the app (link below). Ask:
# MAGIC
# MAGIC 1. *"According to our glossary, how is OEE calculated, and what was the average OEE per plant in 2025?"* — the glossary page *OEE* (Availability × Performance × Quality, average over completed orders), then the Manufacturing Analyst for the numbers.
# MAGIC 2. *"What does the glossary say about scrap rate, and which production line had the highest scrap rate in 2026?"* — definition first, then the analyst's ranking.
# MAGIC 3. A follow-up without context, e.g. *"And in 2024?"* — the router remembers the conversation (Lakebase).
# MAGIC 4. *"How many webshop orders did we have in 2025?"* — not manufacturing data: the router declines and points to the full bootcamp router.
# MAGIC
# MAGIC Check the **Sources** line of every answer: the glossary page and what the analyst answered. Then open the
# MAGIC MLflow experiment (*Traces*) and follow one conversation through the glossary tool and the Genie calls. Mapped
# MAGIC like you (step 3 and 5b), questions about rows outside your mapping come back empty — governance applies to the
# MAGIC app too.
# MAGIC
# MAGIC **Share the app** (app page → *Permissions* → *Can use*) with a colleague: they get their own conversations,
# MAGIC and the answers follow the **app's** mapping (yours) - give a shared app a mapping that suits everybody who
# MAGIC may use it.

# COMMAND ----------

app_url = app.get("url")
displayHTML(f'<p style="font-size:16px">👉 <a href="{app_url}" target="_blank">Open the Fjällmark {TITLE} router app</a> ({app_url})</p>'
            f'<p>Traces: <a href="{host}/ml/experiments/{experiment_id}" target="_blank">{experiment_path}</a></p>')
dbutils.notebook.exit(json.dumps({"app_name": app_name, "url": app_url, "app_status": app_state, "deployment": state,
                                  "service_principal": app.get("service_principal_name"),
                                  "sp_mapping": sp_mapping, "sql_warehouse": warehouse_id,
                                  "llm_endpoint": llm_endpoint, "genie_space": space_id, "experiment_id": experiment_id,
                                  "lakebase_project": project, "lakebase_branch": my_branch}))
