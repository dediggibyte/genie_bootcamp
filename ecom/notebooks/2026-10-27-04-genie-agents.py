# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 04 · Genie Agents - one per domain
# MAGIC
# MAGIC Each domain of Nordvik Group gets **its own Genie Agent**, built on that domain's gold tables and metric views:
# MAGIC
# MAGIC | agent | domain | data | answers questions about |
# MAGIC |---|---|---|---|
# MAGIC | **Nordvik Retail Analyst** | Retail and Commerce | `retail.*` (5 tables, 2 metric views) | net revenue, orders, AOV, gross margin, return rate, stores, webshop, brands |
# MAGIC | **Nordvik Mobility Analyst** | Mobility and Automotive | `mobility.*` (5 tables, 2 metric views) | vehicles sold, vehicle revenue, EV share, dealers, workshop visits, warranty |
# MAGIC | **Nordvik Connect Analyst** | Telecommunications and Media | `telecom.*` (5 tables, 2 metric views) | billed revenue, ARPU, overdue invoices, subscriptions, data and streaming usage |
# MAGIC
# MAGIC The agents are **code**: `genie/2026-10-27-<domain>-agent.json`, generated from one spec by
# MAGIC `tools/2026-10-27-build-semantics.py` (which also writes the business glossary in `context/`). Each template holds
# MAGIC the data sources, one text instruction (definitions, region codes, who answers what), example SQL on the metric
# MAGIC views, SQL snippets, sample questions and **benchmarks** whose answers equal `data/2026-10-27-expected-answers.json`.
# MAGIC
# MAGIC | step | what |
# MAGIC |---|---|
# MAGIC | 1 | parameters: catalog, SQL warehouse, which agents |
# MAGIC | 2 | check that every data source exists in your catalog |
# MAGIC | 3 | build the agent definitions for your catalog |
# MAGIC | 4 | **create or update** the agents (`/api/2.0/genie/spaces`) and tag them `ecom_project` |
# MAGIC | 5 | ask test questions (Conversation API) |
# MAGIC | 6 | run the **benchmarks** (Genie evaluation API) |
# MAGIC | 7 | share the agents - governance travels with the data |
# MAGIC
# MAGIC ▶ **Before:** notebook 01 and the job `ecom_job` (gold tables + metric views). Notebook 03 (governance) is
# MAGIC optional before this one - the agents follow your row filters and masks whenever they exist.
# MAGIC
# MAGIC 🔁 **Re-running is safe:** an agent with the same title and template version is left as it is; a changed
# MAGIC template updates the agent in place (same link).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | meaning |
# MAGIC |---|---|
# MAGIC | `catalog` | blank = `ecom_<your short user name>` (same rule as the bundle) |
# MAGIC | `warehouse` | SQL warehouse id or name; blank = the first serverless warehouse you may use |
# MAGIC | `domains` | which agents to build: `retail,mobility,telecom` |
# MAGIC | `ask_test_questions`, `run_benchmarks` | steps 5 and 6 |
# MAGIC | `force_update` | `true` = push the template even if the agent is already up to date |

# COMMAND ----------

import json
import os
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError

ALL_DOMAINS = ["retail", "mobility", "telecom"]
dbutils.widgets.text("catalog", "", "1 Catalog (blank = automatic)")
dbutils.widgets.text("warehouse", "", "2 SQL warehouse id or name (blank = automatic)")
dbutils.widgets.text("domains", ",".join(ALL_DOMAINS), "3 Agents to build")
dbutils.widgets.dropdown("ask_test_questions", "true", ["true", "false"], "4 Ask test questions")
dbutils.widgets.dropdown("run_benchmarks", "true", ["true", "false"], "5 Run the benchmarks")
dbutils.widgets.dropdown("force_update", "false", ["false", "true"], "6 Force update from template")

TEMPLATE_FILE = "genie/2026-10-27-{domain}-agent.json"
PLACEHOLDER = "__CATALOG__"


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}: the part before '@',
    lower-cased, every character that is not a letter or digit replaced by '_'."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


def bundle_root() -> str:
    """The folder that holds databricks.yml (= ecom/; this notebook lives below it)."""
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


w = WorkspaceClient()
host = w.config.host.rstrip("/")
user_name = w.current_user.me().user_name
catalog = dbutils.widgets.get("catalog").strip() or f"ecom_{bundle_short_name(user_name)}"
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
        raise ValueError("No serverless SQL warehouse visible to you - ask an admin for CAN USE on one, "
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
# MAGIC Each template lists its data sources as `__CATALOG__.<schema>.<object>`. Genie refuses to create an agent on a
# MAGIC table that does not exist, so we check first (gold tables are `MATERIALIZED_VIEW`s written by the pipelines,
# MAGIC metric views are `METRIC_VIEW`s written by job task `metric_views`). If something is missing: run `ecom_job`.

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
        WHERE table_schema IN ({", ".join(repr(d) for d in ALL_DOMAINS)})
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
                       "ecom_job (pipelines + metric_views) first, then re-run this notebook.")
print(f"OK - all {len(rows)} data sources of {len(templates)} agent(s) exist in {catalog}.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Build the agent definitions for your catalog
# MAGIC
# MAGIC The Genie API takes the whole agent as one JSON document, the **serialized space** (version 2). Each template is
# MAGIC exactly that with `__CATALOG__` instead of a catalog name - so the same files work for every participant and can
# MAGIC be reviewed in a pull request. Notice that the benchmark questions are **not** among the example SQLs:
# MAGIC benchmarks test an agent, they must not teach it the answers.

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
print(f"----- text instruction of {agents[domains[0]]['title']} (first 25 lines) -----")
print("\n".join(instruction_text.split("\n")[:25]) + "\n...")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Create or update the agents
# MAGIC
# MAGIC | situation | call |
# MAGIC |---|---|
# MAGIC | no agent with this title yet | `POST /api/2.0/genie/spaces` (in your home folder) |
# MAGIC | agent exists, description carries the same template version | nothing to do |
# MAGIC | agent exists, template changed (or `force_update = true`) | `PATCH /api/2.0/genie/spaces/<id>` - same ID, same link |
# MAGIC
# MAGIC Every agent also gets the workspace tag `ecom_project = ecom_bootcamp` (`POST /api/2.0/entity-tag-assignments`,
# MAGIC best effort). Its **domain** tag is added by the business-context notebooks 05a-c.

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


def tag_space(space_id: str) -> str:
    try:
        have = {t.get("tag_key"): t.get("tag_value") for t in w.api_client.do(
            "GET", f"/api/2.0/entity-tag-assignments/geniespaces/{space_id}/tags").get("tag_assignments", [])}
        if have.get("ecom_project") == "ecom_bootcamp":
            return "already tagged"
        w.api_client.do("POST", "/api/2.0/entity-tag-assignments", body={
            "entity_type": "geniespaces", "entity_id": space_id, "tag_key": "ecom_project", "tag_value": "ecom_bootcamp"})
        return "tagged"
    except Exception as e:
        return f"not tagged ({str(e)[:120]})"


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
    a["tag"] = tag_space(a["space_id"])

display(pd.DataFrame([{"agent": a["title"], "space_id": a["space_id"], "action": a["action"], "ecom_project tag": a["tag"],
                       "link": a["url"]} for a in agents.values()]))
displayHTML("".join(f'<p style="font-size:16px">👉 <a href="{a["url"]}" target="_blank">Open "{a["title"]}" in Genie</a></p>'
                    for a in agents.values()))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Ask test questions (Conversation API)
# MAGIC
# MAGIC Everything you can do in the Genie UI can be done through the **Conversation API** - that is how you embed an
# MAGIC agent in an app or test it automatically: `start-conversation`, poll the message until `COMPLETED`, read the SQL
# MAGIC from the attachment and fetch the rows with `query-result`.
# MAGIC
# MAGIC Read the SQL! Does the Retail Analyst exclude cancelled orders and compute AOV as a ratio? Does the Connect
# MAGIC Analyst group ARPU by month? The last question goes to the **wrong** agent on purpose: the Retail Analyst should
# MAGIC say that vehicles are the Mobility Analyst's, not guess.

# COMMAND ----------

TEST_QUESTIONS = [   # (agent, question)
    ("retail", "What was net revenue and average order value by region?"),
    ("mobility", "What is the EV share per vehicle type, and which dealer sold the most EVs?"),
    ("telecom", "How did ARPU develop from May to June per customer segment?"),
    ("retail", "How many electric cars did we sell?"),   # belongs to the Mobility Analyst
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

# MAGIC %md
# MAGIC ## 6 · Run the benchmarks - built-in evaluation API
# MAGIC
# MAGIC Benchmarks are each agent's **test suite**: every question has a checked SQL answer (6 per agent; their values
# MAGIC are in `data/2026-10-27-expected-answers.json`). Genie answers every question, runs its SQL and the checked SQL,
# MAGIC and grades the result itself: `GOOD`, `BAD` (with reasons) or `NEEDS_REVIEW`. Runs show up in each agent's
# MAGIC **Benchmarks → Evaluations** tab.
# MAGIC
# MAGIC Questions marked ⚠ are **tricky** on purpose: "Göteborg" means region GOT, the return rate counts units, webshop
# MAGIC orders exclude cancelled ones, truck EV share excludes hybrids, ARPU is per month. When one fails, compare
# MAGIC `genie_sql` with `expected_sql`, improve the agent (instruction, example SQL, synonym) - in the spec
# MAGIC `tools/2026-10-27-build-semantics.py`, so the change is reviewed as code - regenerate, and run this notebook again.
# MAGIC
# MAGIC Results are for **your** scope: benchmark answers assume a user who sees every row. If notebook 03 limited you
# MAGIC to one region or segment, switch your mapping to `ALL` first (notebook 03 explains how).

# COMMAND ----------

FINAL_STATES = {"DONE", "EVALUATION_FAILED", "EVALUATION_CANCELLED", "EVALUATION_TIMEOUT"}
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
        with ThreadPoolExecutor(max_workers=8) as pool:
            bench = pd.DataFrame(list(pool.map(lambda r, a=a: result_row(a, r), results)))
        total = int(a["run"].get("num_questions") or len(bench))
        good = int((bench["assessment"] == "GOOD").sum()) if len(bench) else 0
        a["score"] = {"eval_run_id": a["eval_run_id"], "status": status, "good": good, "total": total}
        frames.append(bench)

    display(pd.DataFrame([{"agent": a["title"], "run status": a["score"]["status"],
                           "score": f"{a['score']['good']}/{a['score']['total']} GOOD "
                                    f"({100 * a['score']['good'] / max(a['score']['total'], 1):.0f} %)",
                           "eval run": a["eval_run_id"]} for a in running]))
    if frames and sum(len(f) for f in frames):
        display(pd.concat(frames).sort_values(["agent", "assessment", "question"])[
            ["agent", "question", "assessment", "reasons", "genie_sql", "expected_sql", "status"]])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Share the agents - governance travels with the data
# MAGIC
# MAGIC **Share:** open an agent → **Share** → add a user or group → **Can run** → *Save*. The viewer also needs
# MAGIC `CAN USE` on the SQL warehouse and `USE CATALOG` / `USE SCHEMA` / `SELECT` on the gold schema of the domain
# MAGIC (never on bronze / silver). As code (not executed here):
# MAGIC
# MAGIC ```python
# MAGIC w.api_client.do("PATCH", f"/api/2.0/permissions/genie/{space_id}",
# MAGIC                 body={"access_control_list": [{"group_name": "<group>", "permission_level": "CAN_RUN"}]})
# MAGIC ```
# MAGIC
# MAGIC 🔐 Genie runs every query **as the person who asks**, so the row filters and column masks of notebook 03 apply
# MAGIC inside Genie too: the Göteborg store manager asking the Retail Analyst "net revenue by region" gets one row
# MAGIC (GOT); masked columns stay masked. Security is configured **once**, in Unity Catalog - not in the agents.
# MAGIC
# MAGIC ✅ **Next:** the business-context notebooks **05a (retail), 05b (mobility), 05c (telecom)** create the domains and
# MAGIC subdomains, file your schemas, tables and these agents into them, and write the business glossary tables.

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"catalog": catalog, "agents": {
    d: {"space_id": a["space_id"], "title": a["title"], "action": a["action"], "url": a["url"],
        "template_version": a["template_version"], "benchmarks": a["score"]} for d, a in agents.items()}}))
