# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # 04 · Your three Genie Agents — Consumer, Finance and Manufacturing Analyst
# MAGIC
# MAGIC Steps 1-3 gave you **governed data**: gold tables of the Lakehouse Industry Data Model (consumer, finance,
# MAGIC manufacturing), metric views with the official KPI definitions, and row filters / column masks. Now you
# MAGIC put **Genie Agents** (formerly *Genie spaces*) on top of it, so the business can ask questions in plain
# MAGIC language — and you can **prove** that the answers are right.
# MAGIC
# MAGIC One agent per domain, each owned by "its" part of the business and curated on **its own datasets** only:
# MAGIC
# MAGIC | agent | template | data sources | benchmarks |
# MAGIC |---|---|---|---|
# MAGIC | **Fjällmark Consumer Analyst** | `bootcamp/genie/fjallmark_consumer_analyst.json` | 4 consumer metric views, 7 consumer tables + `finance.company_code` (entity reference) | 8 |
# MAGIC | **Fjällmark Finance Analyst** | `bootcamp/genie/fjallmark_finance_analyst.json` | 2 finance metric views, 8 finance tables | 9 |
# MAGIC | **Fjällmark Manufacturing Analyst** | `bootcamp/genie/fjallmark_manufacturing_analyst.json` | 4 manufacturing metric views, 6 manufacturing tables | 7 |
# MAGIC
# MAGIC A question that needs two domains ("webshop sales vs the revenue finance reports") is not answered by any single
# MAGIC agent: that is the job of the **router app** in step 6, which asks the right agents and combines their answers.
# MAGIC
# MAGIC An agent is not "a chatbot with tables". It is a curated, versioned asset. Each template carries:
# MAGIC
# MAGIC | building block | what it does |
# MAGIC |---|---|
# MAGIC | **Data sources** | what Genie may query |
# MAGIC | **Column settings** | synonyms, *entity matching* (Genie knows the real values, e.g. `PL-POZ-L2`), hidden noisy / personal columns |
# MAGIC | **Text instruction** | shared rules (company, calendar, currency, privacy, *who answers what*) + the domain's business rules, from `bootcamp/context/genie/agent_instructions.md` |
# MAGIC | **Example SQL** | trusted query patterns with usage guidance |
# MAGIC | **SQL snippets** | reusable measures, filters, expressions |
# MAGIC | **Sample questions** | the starter questions users see |
# MAGIC | **Benchmarks** | questions with a checked SQL answer — the agent's *test suite* |
# MAGIC
# MAGIC | step | what |
# MAGIC |---|---|
# MAGIC | 1 | parameters: catalog, SQL warehouse, which agents |
# MAGIC | 2 | check that your catalog has every table and metric view the agents need |
# MAGIC | 3 | build the agent definitions for **your** catalog from the templates |
# MAGIC | 4 | create the agents — or update them if they already exist |
# MAGIC | 5 | ask test questions through the **Conversation API** and look at the SQL |
# MAGIC | 6 | run the **benchmarks** of all three agents with the built-in **evaluation API** and read the scores |
# MAGIC | 7 | share the agents — answers respect each viewer's row filters and masks |
# MAGIC | 8 | (UI) attach the business glossary from GitHub with the **GitHub MCP** in Agent mode |
# MAGIC
# MAGIC ▶ **How to run:** Serverless compute → **Run all** (about 10 minutes, most of it the benchmark runs in step 6,
# MAGIC which run for the three agents at the same time).
# MAGIC
# MAGIC 🔁 **Re-running is safe.** Each agent is found by its title. If it already matches its template (the template
# MAGIC version is stored in the agent's description), nothing is changed — your own edits in the Genie UI survive.
# MAGIC If a template changed, that agent is updated in place (same ID and link). Steps 5 and 6 only *read*: they ask
# MAGIC questions and evaluate, they never change an agent.

# COMMAND ----------

# DBTITLE 1,Parameters
# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | meaning |
# MAGIC |---|---|
# MAGIC | `catalog` | leave **blank** for `cpg_<your short user name>` (same rule as the bundle) |
# MAGIC | `warehouse` | SQL warehouse ID or name; **blank** = the first serverless warehouse you can use (preferably *Serverless Starter Warehouse*) |
# MAGIC | `domains` | which agents to build: `consumer,finance,manufacturing` (default) or a subset, e.g. `finance` |
# MAGIC | `ask_test_questions` | step 5 on / off |
# MAGIC | `run_benchmarks` | step 6 on / off |
# MAGIC | `force_update` | `true` overwrites the agents with the templates even if the template version did not change (discards your UI edits) |

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

ALL_DOMAINS = ["consumer", "finance", "manufacturing"]
dbutils.widgets.text("catalog", "", "1 Catalog (blank = automatic)")
dbutils.widgets.text("warehouse", "", "2 SQL warehouse id or name (blank = automatic)")
dbutils.widgets.text("domains", ",".join(ALL_DOMAINS), "3 Agents to build")
dbutils.widgets.dropdown("ask_test_questions", "true", ["true", "false"], "4 Ask test questions")
dbutils.widgets.dropdown("run_benchmarks", "true", ["true", "false"], "5 Run the benchmarks")
dbutils.widgets.dropdown("force_update", "false", ["false", "true"], "6 Force update from template")

TEMPLATE_FILE = "genie/fjallmark_{domain}_analyst.json"
LEGACY_TITLE = "Fjällmark Business Analyst"   # the one all-domains agent of earlier bootcamp versions
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
domains = [d.strip().lower() for d in dbutils.widgets.get("domains").split(",") if d.strip()]
unknown = sorted(set(domains) - set(ALL_DOMAINS))
if unknown or not domains:
    raise ValueError(f"domains must be a subset of {ALL_DOMAINS}, got {domains}")
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
print(f"Agents      : {', '.join(domains)}")
print(f"Templates   : {BUNDLE_ROOT}/{TEMPLATE_FILE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Does your catalog have everything the agents need?
# MAGIC
# MAGIC Each template lists its data sources as `__CATALOG__.<schema>.<table>`. Genie refuses to create an agent on a
# MAGIC table that does not exist, so we check first in `information_schema.tables` (gold tables are
# MAGIC `MATERIALIZED_VIEW`s written by the pipeline, metric views are `METRIC_VIEW`s written by job task
# MAGIC `metric_views`). If something is missing: run the bundle job `cpg_lakehouse_job` (step 2) first.

# COMMAND ----------

templates = {}
for d in domains:
    with open(f"{BUNDLE_ROOT}/{TEMPLATE_FILE.format(domain=d)}", encoding="utf-8") as fh:
        templates[d] = json.load(fh)

existing = {
    f"{r.table_schema}.{r.table_name}": r.table_type
    for r in spark.sql(f"""
        SELECT table_schema, table_name, table_type
        FROM `{catalog}`.information_schema.tables
        WHERE table_schema IN ('consumer', 'finance', 'manufacturing')
    """).collect()
}
rows, missing = [], []
for d, template in templates.items():
    sources = template["serialized_space"]["data_sources"]
    for kind, key in (("table", "tables"), ("metric view", "metric_views")):
        for s in sources.get(key, []):
            short = s["identifier"].replace(f"{PLACEHOLDER}.", "")
            found = existing.get(short)
            rows.append((d, kind, f"{catalog}.{short}", found or "MISSING"))
            if not found:
                missing.append(short)
display(pd.DataFrame(rows, columns=["agent", "kind", "object", "found as"]))
if missing:
    raise RuntimeError(f"{len(missing)} data source(s) missing in {catalog}: {sorted(set(missing))}. Run the bundle job "
                       "cpg_lakehouse_job (pipeline + metric_views) first, then re-run this notebook.")
print(f"OK - all {len(rows)} data sources of {len(templates)} agent(s) exist in {catalog}.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Build the agent definitions for your catalog
# MAGIC
# MAGIC The Genie API takes the whole agent as one JSON document, the **serialized space** (version 2). Each template
# MAGIC is exactly that, with `__CATALOG__` instead of a catalog name - so the same files work for every
# MAGIC participant, and the agents can be reviewed in a pull request like any other code.
# MAGIC
# MAGIC Have a look at one text instruction and at one benchmark below. Notice that the benchmark questions are
# MAGIC **not** among the example SQLs: benchmarks test an agent, they must not teach it the answers.

# COMMAND ----------

agents = {}   # domain -> everything the next steps need
for d, template in templates.items():
    space_json = json.dumps(template["serialized_space"], ensure_ascii=False).replace(PLACEHOLDER, catalog)
    space = json.loads(space_json)
    version_tag = f"[template {template['template_version']}]"
    agents[d] = {
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
    "agent": a["title"],
    "template version": a["template_version"],
    "tables": len(a["space"]["data_sources"]["tables"]),
    "metric views": len(a["space"]["data_sources"]["metric_views"]),
    "example SQLs": len(a["space"]["instructions"]["example_question_sqls"]),
    "SQL snippets": sum(len(v) for v in a["space"]["instructions"]["sql_snippets"].values()),
    "sample questions": len(a["space"]["config"]["sample_questions"]),
    "benchmarks": f"{len(a['benchmark_ids'])} ({len(a['tricky_ids'])} tricky)",
} for a in agents.values()]))

first = agents[domains[0]]["space"]
instruction_text = "".join(first["instructions"]["text_instructions"][0]["content"])
print(f"----- text instruction of {agents[domains[0]]['title']} (first 30 lines) -----")
print("\n".join(instruction_text.split("\n")[:30]) + "\n...")
print("\n----- one benchmark -----")
b0 = first["benchmarks"]["questions"][0]
print("Q:", b0["question"][0])
print("A:", "".join(b0["answer"][0]["content"]))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Create or update the agents
# MAGIC
# MAGIC REST API `/api/2.0/genie/spaces`, once per agent:
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


all_spaces = list_spaces()
for d, a in agents.items():
    matches = [s for s in all_spaces if s.get("title") == a["title"]]
    if len(matches) > 1:
        print(f"Note: {len(matches)} agents are titled '{a['title']}' - using the first one ({matches[0]['space_id']}).")
    if not matches:
        created = w.api_client.do("POST", "/api/2.0/genie/spaces", body={
            "warehouse_id": warehouse["id"],
            "title": a["title"],
            "description": a["description"],
            "parent_path": f"/Workspace/Users/{user_name}",
            "serialized_space": a["space_json"],
        })
        a["space_id"], a["action"] = created["space_id"], "created"
    else:
        a["space_id"] = matches[0]["space_id"]
        detail = w.api_client.do("GET", f"/api/2.0/genie/spaces/{a['space_id']}")
        same_version = a["version_tag"] in (detail.get("description") or "")
        same_warehouse = detail.get("warehouse_id") == warehouse["id"]
        if same_version and same_warehouse and not force_update:
            a["action"] = "unchanged (template version and warehouse already match)"
        else:
            w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{a['space_id']}", body={
                "warehouse_id": warehouse["id"],
                "title": a["title"],
                "description": a["description"],
                "serialized_space": a["space_json"],
            })
            a["action"] = "updated" + ("" if same_version else " (new template version)") + (
                "" if same_warehouse else " (warehouse changed)")
    a["url"] = f"{host}/genie/rooms/{a['space_id']}"

display(pd.DataFrame([{"agent": a["title"], "space_id": a["space_id"], "action": a["action"], "link": a["url"]}
                      for a in agents.values()]))
displayHTML("".join(f'<p style="font-size:16px">👉 <a href="{a["url"]}" target="_blank">Open "{a["title"]}" in Genie</a></p>'
                    for a in agents.values()))

legacy = [s for s in all_spaces if s.get("title") == f"{LEGACY_TITLE} ({catalog})"]
for s in legacy:
    print(f"Note: the earlier all-domains agent '{s['title']}' ({s['space_id']}) still exists. The three domain agents "
          "replace it - trash it in the Genie UI, or run notebook 99 (cleanup) after the event.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Ask test questions (Conversation API)
# MAGIC
# MAGIC Everything you can do in the Genie UI can be done through the **Conversation API** — that is how you embed
# MAGIC an agent in an app (step 6 does exactly that), in Teams / Slack, or test it automatically:
# MAGIC
# MAGIC 1. `POST .../spaces/<id>/start-conversation` with the question,
# MAGIC 2. poll `GET .../conversations/<c>/messages/<m>` until the status is `COMPLETED`,
# MAGIC 3. read the generated SQL from the attachment and fetch the rows with `GET .../attachments/<a>/query-result`.
# MAGIC
# MAGIC Read the SQL! Does the Finance Analyst use `finance.net_revenue_metrics` for revenue? EUR for totals across
# MAGIC companies? Does the Manufacturing Analyst use the Tampere plant code `FI-TMP`? The last question goes to the
# MAGIC **wrong** agent on purpose: the Consumer Analyst should say that revenue is the Finance Analyst's, not present
# MAGIC webshop order values as revenue.

# COMMAND ----------

TEST_QUESTIONS = [   # (agent, question)
    ("finance", "What were net revenue and gross margin by quarter in 2026?"),
    ("manufacturing", "How did the Tampere plant's OEE develop since start-up?"),
    ("consumer", "How do Gold and Platinum members shop compared with non-members?"),
    ("consumer", "What was our total revenue in 2025?"),   # belongs to the Finance Analyst
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
    for d, q in TEST_QUESTIONS:
        if d not in agents:
            continue
        status, text, sql, df = ask_genie(agents[d]["space_id"], q)
        print("=" * 100)
        print(f"{agents[d]['title']}\nQ: {q}\nstatus: {status}")
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
# MAGIC Benchmarks are each agent's **test suite**: every question has a SQL answer that a human checked. This step uses
# MAGIC Genie's own **benchmark evaluation API** — the same engine as **Benchmarks → Run benchmarks** in the UI. Genie
# MAGIC answers every benchmark question, runs its SQL and the checked SQL, and grades the result itself (no judge model
# MAGIC of your own needed). The runs of the three agents start together; each run shows up in its agent's
# MAGIC **Benchmarks → Evaluations** tab, where you can review each question, override an assessment or update the
# MAGIC ground truth.
# MAGIC
# MAGIC | assessment | meaning |
# MAGIC |---|---|
# MAGIC | `GOOD` | Genie's result matches the result of the checked SQL |
# MAGIC | `BAD` | the result differs (wrong table, filter, currency, period ...) — `reasons` says why |
# MAGIC | `NEEDS_REVIEW` | could not be decided automatically — review it in the *Evaluations* tab |
# MAGIC
# MAGIC A few benchmarks are **deliberately tricky** (marked ⚠): "revenue" must be the finance Net Revenue and not the
# MAGIC webshop order value, a total across markets must be in EUR, "active shoppers" are not `lifecycle_status`.
# MAGIC When one fails, that is your lab exercise: compare `genie_sql` with `expected_sql` in the table (or open the
# MAGIC run in the *Evaluations* tab), fix the agent (instruction, example SQL, synonym) - then run this step again.
# MAGIC
# MAGIC API: `POST /api/2.0/genie/spaces/<id>/eval-runs` starts a run, `GET .../eval-runs/<run>` reports progress,
# MAGIC `GET .../eval-runs/<run>/results` and `.../results/<result>` return the per-question assessment.
# MAGIC Note: the evaluation API tests **Chat mode** (SQL comparison). Agent-mode benchmarks, graded by Genie's built-in
# MAGIC LLM judge, can currently be started only from the UI (**Benchmarks → Run benchmarks** with the Agent toggle on).
# MAGIC The cross-domain questions (`bootcamp/genie/cross_domain_benchmarks.json`) are evaluated on the router app.

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
    row = {"agent": a["title"], "question": ("⚠ " if qid in a["tricky_ids"] else "") + (res.get("question") or ""),
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


for a in agents.values():
    a["score"] = None
if not run_benchmarks:
    print("Skipped (run_benchmarks = false).")
else:
    started = time.time()
    running = [a for a in agents.values() if a["benchmark_ids"]]
    for a in running:
        run = w.api_client.do("POST", eval_api(a["space_id"]), body={})   # no benchmark_question_ids = all benchmarks
        a["eval_run_id"], a["run"] = run["eval_run_id"], run
        print(f"Evaluation run {a['eval_run_id']} started for {a['title']} ({len(a['benchmark_ids'])} benchmarks)")
    while any(a["run"].get("eval_run_status") not in FINAL_STATES for a in running) \
            and time.time() - started < EVAL_TIMEOUT_S:
        time.sleep(15)
        for a in running:
            if a["run"].get("eval_run_status") not in FINAL_STATES:
                a["run"] = w.api_client.do("GET", f"{eval_api(a['space_id'])}/{a['eval_run_id']}")
        print("  " + " | ".join(f"{d}: {a['run'].get('eval_run_status')} {a['run'].get('num_done', 0)}/"
                                f"{a['run'].get('num_questions', '?')}" for d, a in agents.items() if a in running))

    frames = []
    for a in running:
        status = a["run"].get("eval_run_status")
        if status not in FINAL_STATES:
            print(f"{a['title']}: still {status} after {EVAL_TIMEOUT_S}s - results so far are shown; the run continues.")
        results = list_eval_results(a["space_id"], a["eval_run_id"])
        with ThreadPoolExecutor(max_workers=PARALLEL_DETAILS) as pool:
            bench = pd.DataFrame(list(pool.map(lambda r, a=a: result_row(a, r), results)))
        total = int(a["run"].get("num_questions") or len(bench))
        good = int((bench["assessment"] == "GOOD").sum()) if len(bench) else 0
        review = int((bench["assessment"] == "NEEDS_REVIEW").sum()) if len(bench) else 0
        a["score"] = {"mode": "chat (eval-runs API)", "eval_run_id": a["eval_run_id"], "status": status,
                      "good": good, "needs_review": review, "total": total,
                      "api_num_correct": a["run"].get("num_correct"), "seconds": round(time.time() - started),
                      "results": bench[["benchmark_question_id", "assessment", "reasons"]].to_dict("records") if len(bench) else []}
        frames.append(bench)

    display(pd.DataFrame([{"agent": a["title"], "run status": a["score"]["status"],
                           "score": f"{a['score']['good']}/{a['score']['total']} GOOD "
                                    f"({100 * a['score']['good'] / max(a['score']['total'], 1):.0f} %)",
                           "need review": a["score"]["needs_review"], "eval run": a["eval_run_id"]} for a in running]))
    if frames and sum(len(f) for f in frames):
        display(pd.concat(frames).sort_values(["agent", "assessment", "question"])[
            ["agent", "question", "assessment", "reasons", "genie_sql", "expected_sql", "status", "benchmark_question_id"]])
    displayHTML("".join(f'<p>Review in Genie: <a href="{a["url"]}" target="_blank">{a["title"]}</a> '
                        f'→ <b>Benchmarks → Evaluations</b> (run {a["eval_run_id"]})</p>' for a in running))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Share the agents — governance travels with the data
# MAGIC
# MAGIC **Share:** open an agent → **Share** (top right) → add a user or group → permission **Can run** → *Save*.
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
# MAGIC filters and column masks from step 3 therefore apply inside Genie too: Anna (mapped to `SE01`) asking the Finance
# MAGIC Analyst "net revenue by company code" gets one row, SE01; the CFO (`ALL`) gets six. Masked columns stay masked
# MAGIC in Genie's answers, and the agents' instruction tells them to answer about people only in aggregate. You do not
# MAGIC configure security in the agents — you configure it **once**, in Unity Catalog. (Notebook 03, section 11 asks
# MAGIC your Finance Analyst a question and checks exactly this.) The router app of step 6 keeps it that way: it calls
# MAGIC the agents **on behalf of the signed-in user**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8 · (UI) Give the agents the business glossary — GitHub MCP in Agent mode
# MAGIC
# MAGIC The definitions behind the instructions live in the repository folder **`bootcamp/context/`** (one page per
# MAGIC business term, e.g. `bootcamp/context/domains/finance/pages/net_revenue.md`). In **Agent mode** an agent can
# MAGIC read them live through the managed **GitHub MCP** (`system.ai.github`). There is no API for this yet, so it is
# MAGIC a few clicks — do it for the **Finance Analyst** first (and the other two if you have time):
# MAGIC
# MAGIC 1. Open the agent (link from step 4) and switch the mode toggle to **Agent**.
# MAGIC 2. **Configure** → **Sources** (or the *+ Add* next to the data sources) → **Add** → **MCP services**.
# MAGIC 3. Pick **`system.ai.github`** → *Add*. The first time, sign in to GitHub when asked (each user authorises
# MAGIC    with their own GitHub account — the agent only sees what *you* may see on GitHub).
# MAGIC 4. Description of the source (Genie uses it to decide when to call the tool; use the agent's own domain folder):
# MAGIC    > Fjällmark business glossary in the GitHub repository `dediggibyte/genie_bootcamp`, folder
# MAGIC    > `bootcamp/context/` (pages of this agent's domain under `bootcamp/context/domains/<domain>/pages/`, index
# MAGIC    > `bootcamp/context/glossary.csv`). Read the relevant page before answering questions about KPI definitions,
# MAGIC    > revenue, currency, fiscal calendar or known business events.
# MAGIC 5. Ask the Finance Analyst in Agent mode: *"According to our glossary, how is DSO defined - and what is DE01's
# MAGIC    DSO?"* — the agent reads `bootcamp/context/domains/finance/pages/dso.md` (it asks you to **approve** the tool
# MAGIC    call) and then queries `finance.receivables_metrics`.
# MAGIC
# MAGIC Notes: MCP sources work in **Agent mode** only (Beta) and need the workspace setting *MCP tools in Genie
# MAGIC Agents* (the instructor checked it). A private repository additionally needs the Databricks GitHub connector
# MAGIC app installed by a GitHub organisation admin.
# MAGIC
# MAGIC ✅ **Done.** Next: notebook `05_business_context` files your schemas, tables and the three agents into the
# MAGIC Consumer / Finance / Manufacturing domains (it finds the agents by their titles), and notebook
# MAGIC `06_router_app` puts one chat entry point in front of all three.

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"catalog": catalog, "agents": {
    d: {"space_id": a["space_id"], "title": a["title"], "action": a["action"], "url": a["url"],
        "template_version": a["template_version"], "benchmarks": a["score"]} for d, a in agents.items()}}))
