# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # 04 · Your Genie Agent — the Finance Analyst
# MAGIC
# MAGIC Steps 1-3 gave you **governed data**: the finance gold tables of the Lakehouse Industry Data Model, metric views
# MAGIC with the official KPI definitions, and row filters / column masks. Now you put a **Genie Agent** (formerly
# MAGIC *Genie space*) on top of it, so the business can ask questions in plain language — and you can **prove**
# MAGIC that the answers are right.
# MAGIC
# MAGIC This sample has **one** agent, owned by "its" part of the business and curated on **its own datasets** only:
# MAGIC
# MAGIC | agent | template | data sources | benchmarks |
# MAGIC |---|---|---|---|
# MAGIC | **Fjällmark Finance Analyst** | `bootcamp_domain/finance/genie/fjallmark_finance_analyst.json` | 2 finance metric views, 8 finance tables | 9 |
# MAGIC
# MAGIC An agent is not "a chatbot with tables". It is a curated, versioned asset. The template carries:
# MAGIC
# MAGIC | building block | what it does |
# MAGIC |---|---|
# MAGIC | **Data sources** | what Genie may query |
# MAGIC | **Column settings** | synonyms, *entity matching* (Genie knows the real values, e.g. `DE01`), hidden noisy / personal columns |
# MAGIC | **Text instruction** | shared rules (company, calendar, currency, privacy, *who answers what*) + the domain's business rules, from `bootcamp/context/genie/agent_instructions.md` |
# MAGIC | **Example SQL** | trusted query patterns with usage guidance |
# MAGIC | **SQL snippets** | reusable measures, filters, expressions |
# MAGIC | **Sample questions** | the starter questions users see |
# MAGIC | **Benchmarks** | questions with a checked SQL answer — the agent's *test suite* |
# MAGIC
# MAGIC ℹ️ **One agent of three.** The template is the bootcamp's Finance Analyst, unchanged. Its text instruction
# MAGIC still lists **who answers what** across the three bootcamp agents (Consumer, Finance and Manufacturing
# MAGIC Analyst) and the full bootcamp's router app (not part of this sample) for questions that need two domains. Only the Finance Analyst exists in this
# MAGIC sample, so a question about webshop orders and shoppers (the Consumer Analyst's), plants and lines (the Manufacturing Analyst's) or one that needs two domains (the full bootcamp router's) is **declined by design**: the agent names the agent that would answer it
# MAGIC instead of guessing. That is the intended behaviour, not a bug — a single-domain agent must not invent
# MAGIC another domain's numbers.
# MAGIC
# MAGIC | step | what |
# MAGIC |---|---|
# MAGIC | 1 | parameters: catalog, SQL warehouse |
# MAGIC | 2 | check that your catalog has every table and metric view the agent needs |
# MAGIC | 3 | build the agent definition for **your** catalog from the template |
# MAGIC | 4 | create the agent — or update it if it already exists |
# MAGIC | 5 | ask test questions through the **Conversation API** and look at the SQL |
# MAGIC | 6 | run the **benchmarks** with the built-in **evaluation API** and read the score |
# MAGIC | 7 | share the agent — answers respect each viewer's row filters and masks |
# MAGIC | 8 | (UI) attach the business glossary from GitHub with the **GitHub MCP** in Agent mode |
# MAGIC
# MAGIC ▶ **How to run:** Serverless compute → **Run all** (most of the run time is the benchmark run in step 6).
# MAGIC
# MAGIC 🔁 **Re-running is safe.** The agent is found by its title. If it already matches its template (the template
# MAGIC version is stored in the agent's description), nothing is changed — your own edits in the Genie UI survive.
# MAGIC If the template changed, the agent is updated in place (same ID and link). Steps 5 and 6 only *read*: they ask
# MAGIC questions and evaluate, they never change the agent.

# COMMAND ----------

# DBTITLE 1,Parameters
# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | meaning |
# MAGIC |---|---|
# MAGIC | `catalog` | leave **blank** for `cpg_finance_<your short user name>` (same rule as the bundle) |
# MAGIC | `warehouse` | SQL warehouse ID or name; **blank** = the first serverless warehouse you can use (preferably *Serverless Starter Warehouse*) |
# MAGIC | `ask_test_questions` | step 5 on / off |
# MAGIC | `run_benchmarks` | step 6 on / off |
# MAGIC | `force_update` | `true` overwrites the agent with the template even if the template version did not change (discards your UI edits) |

# COMMAND ----------

# DBTITLE 1,Setup and parameters
import json
import os
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError

MAIN_DOMAIN = "finance"
DOMAINS = ["finance"]   # the gold schemas of this sample
dbutils.widgets.text("catalog", "", "1 Catalog (blank = automatic)")
dbutils.widgets.text("warehouse", "", "2 SQL warehouse id or name (blank = automatic)")
dbutils.widgets.dropdown("ask_test_questions", "true", ["true", "false"], "3 Ask test questions")
dbutils.widgets.dropdown("run_benchmarks", "true", ["true", "false"], "4 Run the benchmarks")
dbutils.widgets.dropdown("force_update", "false", ["false", "true"], "5 Force update from template")

TEMPLATE_FILE = f"04_genie/fjallmark_{MAIN_DOMAIN}_analyst.json"
PLACEHOLDER = "__CATALOG__"


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}: the part before '@',
    lower-cased, every character that is not a letter or digit replaced by '_'."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


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


w = WorkspaceClient()
host = w.config.host.rstrip("/")
user_name = w.current_user.me().user_name
catalog = dbutils.widgets.get("catalog").strip() or f"cpg_{MAIN_DOMAIN}_{bundle_short_name(user_name)}"
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
        raise ValueError("No serverless SQL warehouse visible to you - ask a workspace admin for CAN USE on one, "
                         "or enter a warehouse id in the 'warehouse' widget.")
    return serverless[0]


warehouse = pick_warehouse(dbutils.widgets.get("warehouse").strip())

print(f"You are     : {user_name}")
print(f"Catalog     : {catalog}")
print(f"Warehouse   : {warehouse['name']} ({warehouse['id']}, {warehouse.get('state')})")
print(f"Template    : {BUNDLE_ROOT}/{TEMPLATE_FILE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Does your catalog have everything the agent needs?
# MAGIC
# MAGIC The template lists its data sources as `__CATALOG__.<schema>.<table>`. Genie refuses to create an agent on a
# MAGIC table that does not exist, so we check first in `information_schema.tables` (gold tables are
# MAGIC `MATERIALIZED_VIEW`s written by the pipeline, metric views are `METRIC_VIEW`s written by job task
# MAGIC `metric_views`). If something is missing: run the bundle job `cpg_finance_job` (step 2) first.

# COMMAND ----------

with open(f"{BUNDLE_ROOT}/{TEMPLATE_FILE}", encoding="utf-8") as fh:
    template = json.load(fh)

schema_list = ", ".join(f"'{s}'" for s in DOMAINS)
existing = {
    f"{r.table_schema}.{r.table_name}": r.table_type
    for r in spark.sql(f"""
        SELECT table_schema, table_name, table_type
        FROM `{catalog}`.information_schema.tables
        WHERE table_schema IN ({schema_list})
    """).collect()
}
rows, missing = [], []
sources = template["serialized_space"]["data_sources"]
for kind, key in (("table", "tables"), ("metric view", "metric_views")):
    for s in sources.get(key, []):
        short = s["identifier"].replace(f"{PLACEHOLDER}.", "")
        found = existing.get(short)
        rows.append((kind, f"{catalog}.{short}", found or "MISSING"))
        if not found:
            missing.append(short)
display(pd.DataFrame(rows, columns=["kind", "object", "found as"]))
if missing:
    raise RuntimeError(f"{len(missing)} data source(s) missing in {catalog}: {sorted(set(missing))}. Run the bundle job "
                       "cpg_finance_job (pipeline + metric_views) first, then re-run this notebook.")
print(f"OK - all {len(rows)} data sources of the agent exist in {catalog}.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Build the agent definition for your catalog
# MAGIC
# MAGIC The Genie API takes the whole agent as one JSON document, the **serialized space** (version 2). The template
# MAGIC is exactly that, with `__CATALOG__` instead of a catalog name - so the same file works for every
# MAGIC participant, and the agent can be reviewed in a pull request like any other code.
# MAGIC
# MAGIC Have a look at the text instruction and at one benchmark below. Notice that the benchmark questions are
# MAGIC **not** among the example SQLs: benchmarks test an agent, they must not teach it the answers.

# COMMAND ----------

space_json = json.dumps(template["serialized_space"], ensure_ascii=False).replace(PLACEHOLDER, catalog)
space = json.loads(space_json)
version_tag = f"[template {template['template_version']}]"
agent = {   # everything the next steps need
    "title": f"{template['title']} ({catalog})",
    "description": f"{template['description']} Catalog: {catalog}. {version_tag}",
    "template_version": template["template_version"],
    "version_tag": version_tag,
    "space_json": space_json,
    "space": space,
    "benchmark_ids": [q["id"] for q in space.get("benchmarks", {}).get("questions", [])],
    "tricky_ids": set(template.get("tricky_benchmark_ids", [])),
}

display(pd.DataFrame([{
    "agent": agent["title"],
    "template version": agent["template_version"],
    "tables": len(space["data_sources"]["tables"]),
    "metric views": len(space["data_sources"]["metric_views"]),
    "example SQLs": len(space["instructions"]["example_question_sqls"]),
    "SQL snippets": sum(len(v) for v in space["instructions"]["sql_snippets"].values()),
    "sample questions": len(space["config"]["sample_questions"]),
    "benchmarks": f"{len(agent['benchmark_ids'])} ({len(agent['tricky_ids'])} tricky)",
}]))

instruction_text = "".join(space["instructions"]["text_instructions"][0]["content"])
print(f"----- text instruction of {agent['title']} (first 30 lines) -----")
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


matches = [s for s in list_spaces() if s.get("title") == agent["title"]]
if len(matches) > 1:
    print(f"Note: {len(matches)} agents are titled '{agent['title']}' - using the first one ({matches[0]['space_id']}).")
if not matches:
    created = w.api_client.do("POST", "/api/2.0/genie/spaces", body={
        "warehouse_id": warehouse["id"],
        "title": agent["title"],
        "description": agent["description"],
        "parent_path": f"/Workspace/Users/{user_name}",
        "serialized_space": agent["space_json"],
    })
    agent["space_id"], agent["action"] = created["space_id"], "created"
else:
    agent["space_id"] = matches[0]["space_id"]
    detail = w.api_client.do("GET", f"/api/2.0/genie/spaces/{agent['space_id']}")
    same_version = agent["version_tag"] in (detail.get("description") or "")
    same_warehouse = detail.get("warehouse_id") == warehouse["id"]
    if same_version and same_warehouse and not force_update:
        agent["action"] = "unchanged (template version and warehouse already match)"
    else:
        w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{agent['space_id']}", body={
            "warehouse_id": warehouse["id"],
            "title": agent["title"],
            "description": agent["description"],
            "serialized_space": agent["space_json"],
        })
        agent["action"] = "updated" + ("" if same_version else " (new template version)") + (
            "" if same_warehouse else " (warehouse changed)")
agent["url"] = f"{host}/genie/rooms/{agent['space_id']}"

display(pd.DataFrame([{"agent": agent["title"], "space_id": agent["space_id"], "action": agent["action"],
                       "link": agent["url"]}]))
displayHTML(f'<p style="font-size:16px">👉 <a href="{agent["url"]}" target="_blank">Open "{agent["title"]}" in Genie</a></p>')

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Ask test questions (Conversation API)
# MAGIC
# MAGIC Everything you can do in the Genie UI can be done through the **Conversation API** — that is how you embed
# MAGIC an agent in an app, in Teams / Slack, or test it automatically:
# MAGIC
# MAGIC 1. `POST .../spaces/<id>/start-conversation` with the question,
# MAGIC 2. poll `GET .../conversations/<c>/messages/<m>` until the status is `COMPLETED`,
# MAGIC 3. read the generated SQL from the attachment and fetch the rows with `GET .../attachments/<a>/query-result`.
# MAGIC
# MAGIC Read the SQL! Does the Finance Analyst use `finance.net_revenue_metrics` for revenue? EUR for totals across
# MAGIC company codes? Quarters from the fiscal periods of posted journal entries?

# COMMAND ----------

TEST_QUESTIONS = [
    "What were net revenue and gross margin by quarter in 2026?",
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
        status, text, sql, df = ask_genie(agent["space_id"], q)
        print("=" * 100)
        print(f"{agent['title']}\nQ: {q}\nstatus: {status}")
        if text:
            print(f"Genie: {text}")
        if sql:
            print(f"SQL:\n{sql}")
        if df is not None:
            display(df)

# COMMAND ----------

# DBTITLE 1,Step 6 description
# MAGIC %md
# MAGIC ## 6 · Run the benchmarks — built-in evaluation API
# MAGIC
# MAGIC Benchmarks are the agent's **test suite**: every question has a SQL answer that a human checked. This step uses
# MAGIC Genie's own **benchmark evaluation API** — the same engine as **Benchmarks → Run benchmarks** in the UI. Genie
# MAGIC answers every benchmark question, runs its SQL and the checked SQL, and grades the result itself (no judge model
# MAGIC of your own needed). The run shows up in the agent's **Benchmarks → Evaluations** tab, where you can review
# MAGIC each question, override an assessment or update the ground truth.
# MAGIC
# MAGIC | assessment | meaning |
# MAGIC |---|---|
# MAGIC | `GOOD` | Genie's result matches the result of the checked SQL |
# MAGIC | `BAD` | the result differs (wrong table, filter, currency, period ...) — `reasons` says why |
# MAGIC | `NEEDS_REVIEW` | could not be decided automatically — review it in the *Evaluations* tab |
# MAGIC
# MAGIC A few benchmarks are **deliberately tricky** (marked ⚠): "total revenue" must be the GL Net Revenue as one EUR
# MAGIC number (not a list per currency), and "year to date" means January-September 2026 with the margin % as a
# MAGIC ratio of sums.
# MAGIC When one fails, that is your lab exercise: compare `genie_sql` with `expected_sql` in the table (or open the
# MAGIC run in the *Evaluations* tab), fix the agent (instruction, example SQL, synonym) - then run this step again.
# MAGIC
# MAGIC API: `POST /api/2.0/genie/spaces/<id>/eval-runs` starts a run, `GET .../eval-runs/<run>` reports progress,
# MAGIC `GET .../eval-runs/<run>/results` and `.../results/<result>` return the per-question assessment.
# MAGIC Note: the evaluation API tests **Chat mode** (SQL comparison). Agent-mode benchmarks, graded by Genie's built-in
# MAGIC LLM judge, can currently be started only from the UI (**Benchmarks → Run benchmarks** with the Agent toggle on).

# COMMAND ----------

# DBTITLE 1,Run benchmarks via evaluation API
FINAL_STATES = {"DONE", "EVALUATION_FAILED", "EVALUATION_CANCELLED", "EVALUATION_TIMEOUT"}
PARALLEL_DETAILS = 8
EVAL_TIMEOUT_S = 1800


def eval_api(space_id: str) -> str:
    return f"/api/2.0/genie/spaces/{space_id}/eval-runs"


def list_eval_results(space_id: str, eval_run_id: str) -> list:
    out, token = [], None
    while True:
        query = {"page_size": 100, **({"page_token": token} if token else {})}
        resp = w.api_client.do("GET", f"{eval_api(space_id)}/{eval_run_id}/results", query=query)
        out += resp.get("eval_results", [])
        token = resp.get("next_page_token")
        if not token:
            return out


def _sql_of(responses) -> str:
    return "\n;\n".join(r.get("response", "") for r in (responses or []) if r.get("response_type") == "SQL")


def result_row(a: dict, res: dict) -> dict:
    qid = res.get("benchmark_question_id", "")
    row = {"question": ("⚠ " if qid in a["tricky_ids"] else "") + (res.get("question") or ""),
           "benchmark_question_id": qid, "status": res.get("status")}
    try:
        d = w.api_client.do("GET", f"{eval_api(a['space_id'])}/{a['eval_run_id']}/results/{res['result_id']}")
    except DatabricksError as e:
        return {**row, "assessment": "NEEDS_REVIEW", "reasons": f"details failed: {str(e)[:150]}",
                "genie_sql": "", "expected_sql": res.get("benchmark_answer") or ""}
    return {**row,
            "assessment": d.get("assessment") or "NEEDS_REVIEW",
            "reasons": ", ".join(d.get("assessment_reasons") or []),
            "genie_sql": _sql_of(d.get("actual_response")),
            "expected_sql": _sql_of(d.get("expected_response")) or res.get("benchmark_answer") or ""}


agent["score"] = None
if not run_benchmarks:
    print("Skipped (run_benchmarks = false).")
elif not agent["benchmark_ids"]:
    print("The template has no benchmarks - nothing to evaluate.")
else:
    started = time.time()
    run = w.api_client.do("POST", eval_api(agent["space_id"]), body={})   # no benchmark_question_ids = all benchmarks
    agent["eval_run_id"] = run["eval_run_id"]
    print(f"Evaluation run {agent['eval_run_id']} started for {agent['title']} ({len(agent['benchmark_ids'])} benchmarks)")
    while run.get("eval_run_status") not in FINAL_STATES and time.time() - started < EVAL_TIMEOUT_S:
        time.sleep(15)
        run = w.api_client.do("GET", f"{eval_api(agent['space_id'])}/{agent['eval_run_id']}")
        print(f"  {run.get('eval_run_status')} {run.get('num_done', 0)}/{run.get('num_questions', '?')}")

    status = run.get("eval_run_status")
    if status not in FINAL_STATES:
        print(f"Still {status} after {EVAL_TIMEOUT_S}s - results so far are shown; the run continues.")
    results = list_eval_results(agent["space_id"], agent["eval_run_id"])
    with ThreadPoolExecutor(max_workers=PARALLEL_DETAILS) as pool:
        bench = pd.DataFrame(list(pool.map(lambda r: result_row(agent, r), results)))
    total = int(run.get("num_questions") or len(bench))
    good = int((bench["assessment"] == "GOOD").sum()) if len(bench) else 0
    review = int((bench["assessment"] == "NEEDS_REVIEW").sum()) if len(bench) else 0
    agent["score"] = {"mode": "chat (eval-runs API)", "eval_run_id": agent["eval_run_id"], "status": status,
                      "good": good, "needs_review": review, "total": total,
                      "api_num_correct": run.get("num_correct"), "seconds": round(time.time() - started),
                      "results": bench[["benchmark_question_id", "assessment", "reasons"]].to_dict("records") if len(bench) else []}

    display(pd.DataFrame([{"agent": agent["title"], "run status": status,
                           "score": f"{good}/{total} GOOD ({100 * good / max(total, 1):.0f} %)",
                           "need review": review, "eval run": agent["eval_run_id"]}]))
    if len(bench):
        display(bench.sort_values(["assessment", "question"])[
            ["question", "assessment", "reasons", "genie_sql", "expected_sql", "status", "benchmark_question_id"]])
    displayHTML(f'<p>Review in Genie: <a href="{agent["url"]}" target="_blank">{agent["title"]}</a> '
                f'→ <b>Benchmarks → Evaluations</b> (run {agent["eval_run_id"]})</p>')

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
# MAGIC filters and column masks from step 3 therefore apply inside Genie too: a viewer mapped to one company code
# MAGIC sees only that company code's rows, and masked columns stay masked in Genie's answers. The agent's instruction
# MAGIC tells it to answer about people only in aggregate. You do not configure security in the agent — you
# MAGIC configure it **once**, in Unity Catalog.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8 · (UI) Give the agent the business glossary — GitHub MCP in Agent mode
# MAGIC
# MAGIC The definitions behind the instructions live in the repository folder **`bootcamp/context/`** (one page per
# MAGIC business term; this domain's pages are in `bootcamp/context/domains/finance/pages/`, e.g. `bootcamp/context/domains/finance/pages/dso.md`). In
# MAGIC **Agent mode** an agent can read them live through the managed **GitHub MCP** (`system.ai.github`). There is
# MAGIC no API for this yet, so it is a few clicks:
# MAGIC
# MAGIC 1. Open the agent (link from step 4) and switch the mode toggle to **Agent**.
# MAGIC 2. **Configure** → **Sources** (or the *+ Add* next to the data sources) → **Add** → **MCP services**.
# MAGIC 3. Pick **`system.ai.github`** → *Add*. The first time, sign in to GitHub when asked (each user authorises
# MAGIC    with their own GitHub account — the agent only sees what *you* may see on GitHub).
# MAGIC 4. Description of the source (Genie uses it to decide when to call the tool):
# MAGIC    > Fjällmark business glossary in the GitHub repository `dediggibyte/genie_bootcamp`, folder
# MAGIC    > `bootcamp/context/domains/finance/pages/` (index `bootcamp/context/glossary.csv`). Read the relevant page
# MAGIC    > before answering questions about KPI definitions, revenue, currency, fiscal calendar or known business events.
# MAGIC 5. Ask the Finance Analyst in Agent mode: *"According to our glossary, how is DSO defined - and what is DE01's DSO?"* — the agent reads `bootcamp/context/domains/finance/pages/dso.md` (it asks you to
# MAGIC    **approve** the tool call) and then queries `finance.receivables_metrics`.
# MAGIC
# MAGIC Notes: MCP sources work in **Agent mode** only (Beta) and need the workspace setting *MCP tools in Genie
# MAGIC Agents* (a workspace admin turns it on). A private repository additionally needs the Databricks GitHub
# MAGIC connector app installed by a GitHub organisation admin.
# MAGIC
# MAGIC ✅ **Done.** Next: notebook `05_business_context` files your finance schema, its tables and this agent into the
# MAGIC *Finance* domain (it finds the agent by its title).

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"catalog": catalog, "agent": {
    "space_id": agent["space_id"], "title": agent["title"], "action": agent["action"], "url": agent["url"],
    "template_version": agent["template_version"], "benchmarks": agent["score"]}}))
