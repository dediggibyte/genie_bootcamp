# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Your Genie Agent — "Fjällmark Business Analyst"
# MAGIC
# MAGIC Steps 1-3 gave you **governed data**: gold tables of the Lakehouse Industry Data Model (consumer, finance,
# MAGIC manufacturing), metric views with the official KPI definitions, and row filters / column masks. Now you
# MAGIC put a **Genie Agent** (formerly *Genie space*) on top of it, so the business can ask questions in plain
# MAGIC language — and you can **prove** that the answers are right.
# MAGIC
# MAGIC The agent is not "a chatbot with tables". It is a curated, versioned asset. Everything below comes from the
# MAGIC template `bootcamp/genie/fjallmark_business_analyst.json` in your Git folder:
# MAGIC
# MAGIC | building block | what it does | in the template |
# MAGIC |---|---|---|
# MAGIC | **Data sources** | what Genie may query | 4 curated metric views, 6 industry metric views, 21 gold tables |
# MAGIC | **Column settings** | synonyms, *entity matching* (Genie knows the real values, e.g. `PL-POZ-L2`), hidden noisy / personal columns | per table / metric view |
# MAGIC | **Text instruction** | business rules: which revenue is official, group currency EUR, fiscal calendar, status filters, privacy | 1 instruction (from `bootcamp/context/genie/agent_instructions.md`) |
# MAGIC | **Example SQL** | trusted query patterns with usage guidance | 19 |
# MAGIC | **SQL snippets** | reusable measures, filters, expressions | 16 |
# MAGIC | **Joins** | relationships that are *not* foreign keys (FK joins come from Unity Catalog automatically) | 1 |
# MAGIC | **Sample questions** | the starter questions users see | 9 |
# MAGIC | **Benchmarks** | questions with a checked SQL answer — the agent's *test suite* | 25 |
# MAGIC
# MAGIC | step | what |
# MAGIC |---|---|
# MAGIC | 1 | parameters: catalog, SQL warehouse, title |
# MAGIC | 2 | check that your catalog has every table and metric view the agent needs |
# MAGIC | 3 | build the agent definition for **your** catalog from the template |
# MAGIC | 4 | create the agent — or update it if it already exists |
# MAGIC | 5 | ask three test questions through the **Conversation API** and look at the SQL |
# MAGIC | 6 | run the **benchmarks** and read the score |
# MAGIC | 7 | share the agent — answers respect each viewer's row filters and masks |
# MAGIC | 8 | (UI) attach the business glossary from GitHub with the **GitHub MCP** in Agent mode |
# MAGIC
# MAGIC ▶ **How to run:** Serverless compute → **Run all** (about 10 minutes, most of it the benchmark run in step 6).
# MAGIC
# MAGIC 🔁 **Re-running is safe.** The agent is found by its title. If it already matches the template (the template
# MAGIC version is stored in the agent's description), nothing is changed — your own edits in the Genie UI survive.
# MAGIC If the template changed, the agent is updated in place (same ID and link). Steps 5 and 6 only *read*: they ask
# MAGIC questions and evaluate, they never change the agent.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | meaning |
# MAGIC |---|---|
# MAGIC | `catalog` | leave **blank** for `cpg_<your short user name>` (same rule as the bundle) |
# MAGIC | `warehouse` | SQL warehouse ID or name; **blank** = the first serverless warehouse you can use (preferably *Serverless Starter Warehouse*) |
# MAGIC | `title` | blank = `Fjällmark Business Analyst (<catalog>)` |
# MAGIC | `ask_test_questions` | step 5 on / off |
# MAGIC | `run_benchmarks` | step 6 on / off |
# MAGIC | `force_update` | `true` overwrites the agent with the template even if the template version did not change (discards your UI edits) |

# COMMAND ----------

import hashlib
import json
import os
import time
import unicodedata

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError

dbutils.widgets.text("catalog", "", "1 Catalog (blank = automatic)")
dbutils.widgets.text("warehouse", "", "2 SQL warehouse id or name (blank = automatic)")
dbutils.widgets.text("title", "", "3 Agent title (blank = automatic)")
dbutils.widgets.dropdown("ask_test_questions", "true", ["true", "false"], "4 Ask 3 test questions")
dbutils.widgets.dropdown("run_benchmarks", "true", ["true", "false"], "5 Run the benchmarks")
dbutils.widgets.dropdown("force_update", "false", ["false", "true"], "6 Force update from template")

TEMPLATE_FILE = "genie/fjallmark_business_analyst.json"
PLACEHOLDER = "__CATALOG__"


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}: the part before '@',
    lower-cased, every character that is not a letter or digit replaced by '_'."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


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


w = WorkspaceClient()
host = w.config.host.rstrip("/")
user_name = w.current_user.me().user_name
catalog = dbutils.widgets.get("catalog").strip() or f"cpg_{bundle_short_name(user_name)}"
title = dbutils.widgets.get("title").strip() or f"Fjällmark Business Analyst ({catalog})"
ask_questions = dbutils.widgets.get("ask_test_questions") == "true"
run_benchmarks = dbutils.widgets.get("run_benchmarks") == "true"
force_update = dbutils.widgets.get("force_update") == "true"
BUNDLE_ROOT = bundle_root()


def pick_warehouse(wanted: str):
    """Warehouse by id or name; blank = first serverless warehouse this user can use."""
    whs = w.api_client.do("GET", "/api/2.0/sql/warehouses").get("warehouses", [])
    if wanted:
        for wh in whs:
            if wanted in (wh["id"], wh["name"]):
                return wh
        raise ValueError(f"SQL warehouse '{wanted}' not found (or you have no permission on it).")
    serverless = [wh for wh in whs if wh.get("enable_serverless_compute")]
    serverless.sort(key=lambda wh: (wh["name"] != "Serverless Starter Warehouse", wh.get("state") != "RUNNING", wh["name"]))
    if not serverless:
        raise ValueError("No serverless SQL warehouse visible to you - ask the instructor for CAN USE on one, "
                         "or enter a warehouse id in the 'warehouse' widget.")
    return serverless[0]


warehouse = pick_warehouse(dbutils.widgets.get("warehouse").strip())

print(f"You are     : {user_name}")
print(f"Catalog     : {catalog}")
print(f"Warehouse   : {warehouse['name']} ({warehouse['id']}, {warehouse.get('state')})")
print(f"Agent title : {title}")
print(f"Template    : {BUNDLE_ROOT}/{TEMPLATE_FILE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Does your catalog have everything the agent needs?
# MAGIC
# MAGIC The template lists its data sources as `__CATALOG__.<schema>.<table>`. Genie refuses to create an agent on a
# MAGIC table that does not exist, so we check first in `information_schema.tables` (gold tables are
# MAGIC `MATERIALIZED_VIEW`s written by the pipeline, metric views are `METRIC_VIEW`s written by job task
# MAGIC `metric_views`). If something is missing: run the bundle job `cpg_lakehouse_job` (step 2) first.

# COMMAND ----------

with open(f"{BUNDLE_ROOT}/{TEMPLATE_FILE}", encoding="utf-8") as fh:
    template = json.load(fh)

space_template = template["serialized_space"]
sources = ([("table", s["identifier"]) for s in space_template["data_sources"].get("tables", [])]
           + [("metric view", s["identifier"]) for s in space_template["data_sources"].get("metric_views", [])])

existing = {
    f"{r.table_schema}.{r.table_name}": r.table_type
    for r in spark.sql(f"""
        SELECT table_schema, table_name, table_type
        FROM `{catalog}`.information_schema.tables
        WHERE table_schema IN ('consumer', 'finance', 'manufacturing')
    """).collect()
}
rows, missing = [], []
for kind, ident in sources:
    short = ident.replace(f"{PLACEHOLDER}.", "")
    found = existing.get(short)
    rows.append((kind, f"{catalog}.{short}", found or "MISSING"))
    if not found:
        missing.append(short)
display(pd.DataFrame(rows, columns=["kind", "object", "found as"]))
if missing:
    raise RuntimeError(f"{len(missing)} data source(s) missing in {catalog}: {missing}. Run the bundle job "
                       "cpg_lakehouse_job (pipeline + metric_views) first, then re-run this notebook.")
print(f"OK - all {len(sources)} data sources exist in {catalog}.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Build the agent definition for your catalog
# MAGIC
# MAGIC The Genie API takes the whole agent as one JSON document, the **serialized space** (version 2). The template
# MAGIC is exactly that, with `__CATALOG__` instead of a catalog name - so the same file works for every
# MAGIC participant, and the agent can be reviewed in a pull request like any other code.
# MAGIC
# MAGIC Have a look at the text instruction and at one benchmark below. Notice that the benchmark questions are
# MAGIC **not** among the example SQLs: benchmarks test the agent, they must not teach it the answers.

# COMMAND ----------

space_json = json.dumps(space_template, ensure_ascii=False).replace(PLACEHOLDER, catalog)
TEMPLATE_VERSION = template["template_version"]
VERSION_TAG = f"[template {TEMPLATE_VERSION}]"
description = f"{template['description']} Catalog: {catalog}. {VERSION_TAG}"
space = json.loads(space_json)
benchmark_ids = [q["id"] for q in space.get("benchmarks", {}).get("questions", [])]
tricky_ids = set(template.get("tricky_benchmark_ids", []))

print(f"Template version : {TEMPLATE_VERSION}")
print(f"Data sources     : {len(space['data_sources']['tables'])} tables, {len(space['data_sources']['metric_views'])} metric views")
print(f"Example SQLs     : {len(space['instructions']['example_question_sqls'])}")
print(f"SQL snippets     : {sum(len(v) for v in space['instructions']['sql_snippets'].values())}")
print(f"Benchmarks       : {len(benchmark_ids)} ({len(tricky_ids)} deliberately tricky)")
instruction_text = "".join(space["instructions"]["text_instructions"][0]["content"])
print("\n----- text instruction (first 30 lines) -----")
print("\n".join(instruction_text.split("\n")[:30]) + "\n...")
print("\n----- one benchmark -----")
b0 = space["benchmarks"]["questions"][0]
print("Q:", b0["question"][0])
print("A:", "".join(b0["answer"][0]["content"]))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Create or update the agent
# MAGIC
# MAGIC REST API `/api/2.0/genie/spaces`:
# MAGIC
# MAGIC | situation | call |
# MAGIC |---|---|
# MAGIC | no agent with this title yet | `POST /api/2.0/genie/spaces` (in your home folder) |
# MAGIC | agent exists, description carries the same template version | nothing to do |
# MAGIC | agent exists, template changed (or `force_update = true`) | `PATCH /api/2.0/genie/spaces/<id>` — same ID, same link |
# MAGIC
# MAGIC Genie stores which **warehouse** runs the SQL. Each user's questions run with **their own** permissions on
# MAGIC that warehouse and on the tables — that is why the row filters from step 3 also apply in Genie.

# COMMAND ----------


def list_spaces():
    out, token = [], None
    while True:
        query = {"page_size": 100, **({"page_token": token} if token else {})}
        resp = w.api_client.do("GET", "/api/2.0/genie/spaces", query=query)
        out += resp.get("spaces", [])
        token = resp.get("next_page_token")
        if not token:
            return out


matches = [s for s in list_spaces() if s.get("title") == title]
if len(matches) > 1:
    print(f"Note: {len(matches)} agents are titled '{title}' - using the first one ({matches[0]['space_id']}).")

if not matches:
    created = w.api_client.do("POST", "/api/2.0/genie/spaces", body={
        "warehouse_id": warehouse["id"],
        "title": title,
        "description": description,
        "parent_path": f"/Workspace/Users/{user_name}",
        "serialized_space": space_json,
    })
    space_id, action = created["space_id"], "created"
else:
    current = matches[0]
    space_id = current["space_id"]
    detail = w.api_client.do("GET", f"/api/2.0/genie/spaces/{space_id}")
    same_version = VERSION_TAG in (detail.get("description") or "")
    same_warehouse = detail.get("warehouse_id") == warehouse["id"]
    if same_version and same_warehouse and not force_update:
        action = "unchanged (template version and warehouse already match)"
    else:
        w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{space_id}", body={
            "warehouse_id": warehouse["id"],
            "title": title,
            "description": description,
            "serialized_space": space_json,
        })
        action = "updated" + ("" if same_version else " (new template version)") + (
            "" if same_warehouse else " (warehouse changed)")

agent_url = f"{host}/genie/rooms/{space_id}"
print(f"Agent    : {title}")
print(f"Space ID : {space_id}")
print(f"Action   : {action}")
print(f"Open it  : {agent_url}")
displayHTML(f'<p style="font-size:16px">👉 <a href="{agent_url}" target="_blank">Open "{title}" in Genie</a></p>')

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Ask three test questions (Conversation API)
# MAGIC
# MAGIC Everything you can do in the Genie UI can be done through the **Conversation API** — that is how you embed
# MAGIC the agent in an app, in Teams / Slack, or test it automatically:
# MAGIC
# MAGIC 1. `POST .../spaces/<id>/start-conversation` with the question,
# MAGIC 2. poll `GET .../conversations/<c>/messages/<m>` until the status is `COMPLETED`,
# MAGIC 3. read the generated SQL from the attachment and fetch the rows with `GET .../attachments/<a>/query-result`.
# MAGIC
# MAGIC Read the SQL! Does it use `finance.net_revenue_metrics` for revenue? EUR for totals across companies? The
# MAGIC Tampere plant code `FI-TMP`? This is where you build trust — or find the next thing to fix.

# COMMAND ----------

TEST_QUESTIONS = [
    "What were net revenue and gross margin by quarter in 2026?",
    "How did the Tampere plant's OEE develop since start-up?",
    "Which company has the most overdue receivables?",
]


def ask_genie(space_id: str, question: str, timeout_s: int = 300):
    """Ask one question; return (status, text, sql, DataFrame)."""
    start = w.api_client.do("POST", f"/api/2.0/genie/spaces/{space_id}/start-conversation", body={"content": question})
    base = f"/api/2.0/genie/spaces/{space_id}/conversations/{start['conversation_id']}/messages/{start['message_id']}"
    deadline, m = time.time() + timeout_s, {}
    while time.time() < deadline:
        m = w.api_client.do("GET", base)
        if m.get("status") in ("COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"):
            break
        time.sleep(4)
    text, sql, df = [], None, None
    for a in m.get("attachments") or []:
        if a.get("text"):
            text.append(a["text"].get("content", ""))
        if a.get("query"):
            sql = a["query"].get("query", "")
            if a["query"].get("description"):
                text.append(a["query"]["description"])
            res = w.api_client.do("GET", f"{base}/attachments/{a['attachment_id']}/query-result")
            sr = res.get("statement_response", {})
            cols = [c["name"] for c in sr.get("manifest", {}).get("schema", {}).get("columns", [])]
            df = pd.DataFrame(sr.get("result", {}).get("data_array", []) or [], columns=cols)
    if m.get("status") == "FAILED" and m.get("error"):
        text.append(f"ERROR: {m['error']}")
    return m.get("status", "TIMEOUT"), "\n".join(text), sql, df


if not ask_questions:
    print("Skipped (ask_test_questions = false).")
else:
    for q in TEST_QUESTIONS:
        status, text, sql, df = ask_genie(space_id, q)
        print("=" * 100)
        print(f"Q: {q}\nstatus: {status}")
        if text:
            print(f"Genie: {text}")
        if sql:
            print(f"SQL:\n{sql}")
        if df is not None:
            display(df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Run the benchmarks
# MAGIC
# MAGIC Benchmarks are the agent's **test suite**: each question has a SQL answer that a human checked. The benchmark
# MAGIC run asks Genie every question and compares Genie's result with the expected result:
# MAGIC
# MAGIC | assessment | meaning |
# MAGIC |---|---|
# MAGIC | `GOOD` | same result as the checked answer |
# MAGIC | `BAD` | different result (wrong table, filter, currency, period ...) |
# MAGIC | `NEEDS_REVIEW` | Genie could not decide automatically — open it in the UI (*Benchmarks* tab) and judge yourself |
# MAGIC
# MAGIC A few benchmarks are **deliberately tricky** (marked ⚠): "revenue" must be the finance Net Revenue and not the
# MAGIC webshop order value, a total across markets must be in EUR, "active shoppers" are not `lifecycle_status`.
# MAGIC When one fails, that is your lab exercise: open the question in the *Benchmarks* tab, read Genie's SQL, and
# MAGIC fix the agent (instruction, example SQL, synonym) - then run the benchmark again.
# MAGIC
# MAGIC API (Beta): `POST .../spaces/<id>/eval-runs` with the question IDs, poll `GET .../eval-runs/<run>`, then
# MAGIC `GET .../eval-runs/<run>/results` and `.../results/<result>` for the details.

# COMMAND ----------


def run_eval(space_id: str, question_ids, timeout_s: int = 1800):
    run = w.api_client.do("POST", f"/api/2.0/genie/spaces/{space_id}/eval-runs",
                          body={"benchmark_question_ids": list(question_ids)})
    run_id = run["eval_run_id"]
    print(f"Benchmark run {run_id} started for {len(question_ids)} questions ...")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        run = w.api_client.do("GET", f"/api/2.0/genie/spaces/{space_id}/eval-runs/{run_id}")
        if run.get("eval_run_status") not in ("RUNNING", "PENDING", "QUEUED", "IN_PROGRESS", None):
            break
        print(f"  ... {run.get('num_done', 0)}/{run.get('num_questions', len(question_ids))} done")
        time.sleep(30)
    results, token = [], None
    while True:   # the results endpoint is paged (20 per page by default)
        query = {"page_size": 100, **({"page_token": token} if token else {})}
        page = w.api_client.do("GET", f"/api/2.0/genie/spaces/{space_id}/eval-runs/{run_id}/results", query=query)
        results += page.get("eval_results", [])
        token = page.get("next_page_token")
        if not token:
            break
    rows = []
    for r in results:
        d = w.api_client.do("GET", f"/api/2.0/genie/spaces/{space_id}/eval-runs/{run_id}/results/{r['result_id']}")
        actual = (d.get("actual_response") or [{}])[0].get("response", "")
        rows.append({
            "question": ("⚠ " if r["benchmark_question_id"] in tricky_ids else "") + r.get("question", ""),
            "assessment": d.get("assessment", r.get("status")),
            "genie_sql": actual,
            "benchmark_question_id": r["benchmark_question_id"],
        })
    return run, pd.DataFrame(rows)


score = None
if not run_benchmarks:
    print("Skipped (run_benchmarks = false).")
elif not benchmark_ids:
    print("The template has no benchmarks.")
else:
    run, bench = run_eval(space_id, benchmark_ids)
    good = int((bench["assessment"] == "GOOD").sum())
    review = int((bench["assessment"] == "NEEDS_REVIEW").sum())
    total = len(bench)
    print(f"\nBenchmark run {run['eval_run_id']}: status {run.get('eval_run_status')}")
    score = {"eval_run_id": run["eval_run_id"], "good": good, "needs_review": review, "total": total,
             "results": bench[["benchmark_question_id", "assessment"]].to_dict("records")}
    print(f"Score: {good}/{total} GOOD = {100 * good / max(total, 1):.0f} %   ({review} need review)")
    display(bench.sort_values(["assessment", "question"]))
    print(f"Details in the UI: {agent_url} → Benchmarks")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Share the agent — governance travels with the data
# MAGIC
# MAGIC **Share:** open the agent → **Share** (top right) → add a user or group → permission **Can run** → *Save*.
# MAGIC
# MAGIC | permission | can |
# MAGIC |---|---|
# MAGIC | Can view | see the agent and its conversations |
# MAGIC | **Can run** | ask questions — what a business user needs |
# MAGIC | Can edit | change instructions, examples, benchmarks |
# MAGIC | Can manage | everything, incl. permissions |
# MAGIC
# MAGIC The viewer also needs `CAN USE` on the SQL warehouse and `USE CATALOG` / `USE SCHEMA` / `SELECT` on the gold
# MAGIC schemas (never on bronze / silver). Same thing as code (not executed here):
# MAGIC
# MAGIC ```python
# MAGIC w.api_client.do("PATCH", f"/api/2.0/permissions/genie/{space_id}",
# MAGIC                 body={"access_control_list": [{"group_name": "<group>", "permission_level": "CAN_RUN"}]})
# MAGIC ```
# MAGIC
# MAGIC 🔐 **Answers respect each viewer's governance.** Genie runs every query **as the person who asks**. The row
# MAGIC filters and column masks from step 3 therefore apply inside Genie too: Anna (mapped to `SE01`) asking "net
# MAGIC revenue by company code" gets one row, SE01; the CFO (`ALL`) gets six. Masked columns stay masked in Genie's
# MAGIC answers, and the agent's instruction tells it to answer about people only in aggregate. You do not configure
# MAGIC security in the agent — you configure it **once**, in Unity Catalog. (Notebook 03, section 11 asks your agent
# MAGIC a question and checks exactly this.)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8 · (UI) Give the agent the business glossary — GitHub MCP in Agent mode
# MAGIC
# MAGIC The definitions behind the instruction live in the repository folder **`bootcamp/context/`** (one page per
# MAGIC business term, e.g. `bootcamp/context/domains/finance/pages/net_revenue.md`). In **Agent mode** the agent can
# MAGIC read them live through the managed **GitHub MCP** (`system.ai.github`). There is no API for this yet, so it is
# MAGIC a few clicks:
# MAGIC
# MAGIC 1. Open the agent (link from step 4) and switch the mode toggle to **Agent**.
# MAGIC 2. **Configure** → **Sources** (or the *+ Add* next to the data sources) → **Add** → **MCP services**.
# MAGIC 3. Pick **`system.ai.github`** → *Add*. The first time, sign in to GitHub when asked (each user authorises
# MAGIC    with their own GitHub account — the agent only sees what *you* may see on GitHub).
# MAGIC 4. Description of the source (Genie uses it to decide when to call the tool):
# MAGIC    > Fjällmark business glossary in the GitHub repository `dediggibyte/genie_bootcamp`, folder
# MAGIC    > `bootcamp/context/` (pages per domain under `bootcamp/context/domains/<domain>/pages/`, index
# MAGIC    > `bootcamp/context/glossary.csv`). Read the relevant page before answering questions about KPI definitions,
# MAGIC    > revenue, currency, fiscal calendar or known business events.
# MAGIC 5. Ask in Agent mode: *"According to our glossary, how is DSO defined - and what is DE01's DSO?"* — the agent
# MAGIC    reads `bootcamp/context/domains/finance/pages/dso.md` (it asks you to **approve** the tool call) and then
# MAGIC    queries `finance.receivables_metrics`.
# MAGIC
# MAGIC Notes: MCP sources work in **Agent mode** only (Beta) and need the workspace setting *MCP tools in Genie
# MAGIC Agents* (the instructor checked it). A private repository additionally needs the Databricks GitHub connector
# MAGIC app installed by a GitHub organisation admin.
# MAGIC
# MAGIC ✅ **Done.** Next: notebook `05_business_context` files your schemas, tables and this agent into the
# MAGIC Finance / Consumer / Manufacturing domains (paste the Space ID printed in step 4 into its `genie_space_id` widget).

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"space_id": space_id, "title": title, "action": action, "url": agent_url,
                                  "template_version": TEMPLATE_VERSION, "benchmarks": score}))
