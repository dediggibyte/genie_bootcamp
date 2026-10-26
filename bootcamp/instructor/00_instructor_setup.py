# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 00 · Instructor setup (admins only - run once before the event)
# MAGIC
# MAGIC Prepares the **event workspace** so every participant can run the lab without waiting for an admin.
# MAGIC Participants do **not** run this notebook.
# MAGIC
# MAGIC | step | what | needs |
# MAGIC |---|---|---|
# MAGIC | 2 | **who am I** - admin check | workspace admin |
# MAGIC | 3 | **prerequisites checklist**, verified by code: serverless, workspace previews (MCP tools in Genie Agents, managed MCP, Discover, tags on Genie Agents, Agent-mode API), Domains API, `system.ai.github` MCP + grants, SQL warehouse + `CAN USE` | workspace admin |
# MAGIC | 4 | **account groups** `cpg_bootcamp_participants` and `cpg_bootcamp_admins` + members | workspace admin (account groups are created through the workspace proxy API) |
# MAGIC | 5 | **catalog strategy** - pre-create one catalog per participant, or grant `CREATE CATALOG` | metastore admin / owner of the storage location |
# MAGIC | 6 | **UC Semantics domains**: governed tags + domains `Consumer`, `Finance`, `Manufacturing` with their subdomains, published | workspace admin (CREATE on governed tags) |
# MAGIC | 7 | participants may **ASSIGN** the domain tags (and `class.name` for the optional ABAC exercise) | MANAGE on the governed tags |
# MAGIC | 8 | **GitHub MCP checklist** - repository visibility, connector app, Git folders | GitHub org admin |
# MAGIC | 9 | **Pages** bulk import (UI, Genie Code) | instructor |
# MAGIC | 10 | summary | |
# MAGIC | T | **teardown mode** *(after the event)*: with `mode = teardown_...` the notebook removes what it created right after step 2 and **stops** - steps 3-10 do not run | same as above |
# MAGIC
# MAGIC ▶ **How to run:** attach to **Serverless** and **Run all** with `mode = setup` and `dry_run = true`
# MAGIC (defaults): the notebook only *checks* and prints what it *would* change. Review the summary, then set
# MAGIC `dry_run = false` and run again.
# MAGIC
# MAGIC 🔁 **Re-running is a no-op / diff.** Every step first reads what exists (groups, members, grants, catalogs,
# MAGIC governed tags, domains, tag permissions) and only creates or changes what is missing - existing objects
# MAGIC are reported as **OK** and reused as they are. Run it again the morning of the event as a checklist.
# MAGIC
# MAGIC **What does teardown remove?** Only what this notebook **created**. It marks its objects at creation time:
# MAGIC catalogs, governed tags and domains carry the marker `[created by genie_bootcamp/00_instructor_setup]` in
# MAGIC their comment / description, and the account groups it created are remembered in a small ledger file in
# MAGIC your home folder (groups have no comment field). Objects that already existed and were only *reused* are
# MAGIC reported as **KEEP** and left alone.
# MAGIC
# MAGIC > **Testing this notebook?** Use throw-away names (`tag_prefix = zz_test_`, group names `zz_test_...`,
# MAGIC > `catalog_prefix = zz_test_`), `create_groups = false`, `apply_grants = false`, `catalog_strategy = none`,
# MAGIC > and finish with `mode = teardown_domains_and_tags` (or `teardown_everything`). Domains, governed tags and
# MAGIC > groups are **account-level** objects visible to every workspace of the account.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | default | meaning |
# MAGIC |---|---|---|
# MAGIC | `mode` | `setup` | `setup` = steps 3-10 · *after the event:* `teardown_domains_and_tags` or `teardown_everything` (see *Teardown mode*) |
# MAGIC | `dry_run` | `true` | `true` = only check and report; `false` = make the changes (setup **and** teardown) |
# MAGIC | `apply_grants` | `true` | `false` = never change permissions (warehouse ACL, UC grants, catalog owner, tag ASSIGN) - report only |
# MAGIC | `participants` | blank | participant e-mails, separated by comma, semicolon or new line |
# MAGIC | `instructors` | blank | instructor e-mails (members of the admin group bypass all lab policies) |
# MAGIC | `participants_group` / `admins_group` | `cpg_bootcamp_participants` / `cpg_bootcamp_admins` | account group names (notebook 03 uses these exact names) |
# MAGIC | `create_groups` | `true` | `false` = never create account groups (e.g. they come from your IdP via SCIM) - missing groups are reported as ACTION |
# MAGIC | `warehouse_id` | blank = first serverless warehouse | SQL warehouse for Genie Agents and the SQL editor |
# MAGIC | `catalog_strategy` | `precreate` | `precreate` = one catalog per participant · `grant_create_catalog` · `none` (participants create it in the UI) |
# MAGIC | `catalog_prefix` | `cpg_` | catalog = prefix + participant short name (same rule as the bundle) |
# MAGIC | `managed_location` | blank | storage root for new catalogs (needed on Default-Storage metastores, e.g. `s3://.../unity-catalog/<workspace id>`) |
# MAGIC | `domain_names` | `Consumer,Finance,Manufacturing` | UC Semantics domains (= governed tag keys) - the three bootcamp domains |
# MAGIC | `tag_prefix` | blank | prefix for every domain tag key (use `zz_test_` when testing) |
# MAGIC | `create_subdomains` / `publish_domains` | `true` / `true` | subdomains from the industry model; publish (draft = false) so everybody sees them |
# MAGIC | `github_repo` | `dediggibyte/genie_bootcamp` | repository the participants clone and the GitHub MCP reads |
# MAGIC | `lakebase_project` | `fjallmark-genie-bootcamp` | Lakebase project for the router app of lab step 6 (one branch per participant, created by notebook 06) |

# COMMAND ----------

import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request

from databricks.sdk import WorkspaceClient

dbutils.widgets.dropdown("mode", "setup", ["setup", "teardown_domains_and_tags", "teardown_everything"], "00 Mode")
dbutils.widgets.dropdown("dry_run", "true", ["true", "false"], "01 Dry run")
dbutils.widgets.dropdown("apply_grants", "true", ["true", "false"], "02 Apply permission changes")
dbutils.widgets.text("participants", "", "03 Participant e-mails")
dbutils.widgets.text("instructors", "", "04 Instructor e-mails")
dbutils.widgets.text("participants_group", "cpg_bootcamp_participants", "05 Participants group")
dbutils.widgets.text("admins_group", "cpg_bootcamp_admins", "06 Admins group")
dbutils.widgets.text("warehouse_id", "", "07 SQL warehouse id (blank = auto)")
dbutils.widgets.dropdown("catalog_strategy", "precreate", ["precreate", "grant_create_catalog", "none"], "08 Catalog strategy")
dbutils.widgets.text("catalog_prefix", "cpg_", "09 Catalog prefix")
dbutils.widgets.text("managed_location", "", "10 Managed location for new catalogs")
dbutils.widgets.text("domain_names", "Consumer,Finance,Manufacturing", "11 Domains")
dbutils.widgets.text("tag_prefix", "", "12 Tag prefix (zz_test_ when testing)")
dbutils.widgets.dropdown("create_subdomains", "true", ["true", "false"], "13 Create subdomains")
dbutils.widgets.dropdown("publish_domains", "true", ["true", "false"], "14 Publish domains")
dbutils.widgets.text("github_repo", "dediggibyte/genie_bootcamp", "15 GitHub repository")
dbutils.widgets.dropdown("create_groups", "true", ["true", "false"], "16 Create missing account groups")
dbutils.widgets.text("lakebase_project", "fjallmark-genie-bootcamp", "17 Lakebase project (router app)")


def split_list(value: str) -> list:
    return [x.strip() for x in re.split(r"[,;\n]", value or "") if x.strip()]


MODE = dbutils.widgets.get("mode")
DRY_RUN = dbutils.widgets.get("dry_run") == "true"
APPLY_GRANTS = dbutils.widgets.get("apply_grants") == "true"
PARTICIPANTS = split_list(dbutils.widgets.get("participants"))
INSTRUCTORS = split_list(dbutils.widgets.get("instructors"))
PARTICIPANTS_GROUP = dbutils.widgets.get("participants_group").strip()
ADMINS_GROUP = dbutils.widgets.get("admins_group").strip()
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id").strip()
CATALOG_STRATEGY = dbutils.widgets.get("catalog_strategy")
CATALOG_PREFIX = dbutils.widgets.get("catalog_prefix").strip()
MANAGED_LOCATION = dbutils.widgets.get("managed_location").strip()
DOMAIN_NAMES = split_list(dbutils.widgets.get("domain_names"))
TAG_PREFIX = dbutils.widgets.get("tag_prefix")
CREATE_SUBDOMAINS = dbutils.widgets.get("create_subdomains") == "true"
PUBLISH_DOMAINS = dbutils.widgets.get("publish_domains") == "true"
GITHUB_REPO = dbutils.widgets.get("github_repo").strip()
CREATE_GROUPS = dbutils.widgets.get("create_groups") == "true"
LAKEBASE_PROJECT = dbutils.widgets.get("lakebase_project").strip()

w = WorkspaceClient()
me = spark.sql("SELECT current_user()").first()[0]
print(f"Instructor : {me}")
print(f"Mode       : {MODE.upper()} - {'DRY RUN (nothing is changed)' if DRY_RUN else 'APPLY CHANGES'}"
      f"{'' if APPLY_GRANTS or MODE != 'setup' else ' - permission changes disabled (apply_grants = false)'}")
print(f"Participants ({len(PARTICIPANTS)}): {', '.join(PARTICIPANTS) or '-'}")
print(f"Instructors  ({len(INSTRUCTORS)}): {', '.join(INSTRUCTORS) or '-'}")
print(f"Domains      : {', '.join(TAG_PREFIX + d for d in DOMAIN_NAMES)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Helpers
# MAGIC `record()` writes one line of the checklist printed at the end. `act()` performs a change only when
# MAGIC `dry_run = false` (and, for permission changes, `apply_grants = true`). In teardown mode `act()` refuses
# MAGIC every change that is not part of the teardown - even if you run a setup cell by hand.
# MAGIC Status values: **OK** verified · **DONE** changed now · **DRY-RUN** would change · **ACTION** manual step
# MAGIC needed · **WARN** · **ERROR** · **SKIP** · **KEEP** (teardown: not created by this notebook, left alone).
# MAGIC
# MAGIC `MARKER` is written into the comment / description of every catalog, governed tag and domain this
# MAGIC notebook creates; the ledger file remembers the account groups it creates. Teardown relies on both.

# COMMAND ----------

CHECKLIST = []
MARKER = "[created by genie_bootcamp/00_instructor_setup]"
LEDGER_PATH = f"/Workspace/Users/{me}/genie_bootcamp_instructor_ledger.json"


def record(area: str, item: str, status: str, detail: str = "") -> None:
    CHECKLIST.append((area, item, status, detail))
    print(f"[{status:7s}] {area:10s} | {item}" + (f"  -- {detail}" if detail else ""))


def act(area: str, item: str, fn, detail: str = "", grant: bool = False):
    """Run fn() unless this is a dry run, a permission change while apply_grants = false,
    or a setup change while the notebook runs in teardown mode."""
    if MODE != "setup" and area != "teardown":
        record(area, item, "SKIP", f"mode = {MODE}: setup changes are disabled")
        return None
    if DRY_RUN:
        record(area, item, "DRY-RUN", detail or "would be changed")
        return None
    if grant and not APPLY_GRANTS:
        record(area, item, "SKIP", "apply_grants = false - " + (detail or "permission change not applied"))
        return None
    try:
        result = fn()
        record(area, item, "DONE", detail)
        return result
    except Exception as e:
        record(area, item, "ERROR", str(e).splitlines()[0][:300])
        return None


def api(method: str, path: str, query: dict | None = None, body: dict | None = None):
    return w.api_client.do(method, path, query=query, body=body)


def api_try(method: str, path: str, query: dict | None = None, body: dict | None = None):
    try:
        return api(method, path, query, body), None
    except Exception as e:
        return None, str(e).splitlines()[0]


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


def list_all(path: str, key: str) -> list:
    """GET every page of a paginated list API."""
    items, token = [], None
    while True:
        resp = api("GET", path, query={"page_size": 100, **({"page_token": token} if token else {})})
        items += resp.get(key, [])
        token = resp.get("next_page_token")
        if not token:
            return items


def find_group(name: str):
    resp = api("GET", "/api/2.0/identity/groups", query={"filter": f'group_name eq "{name}"'})
    return next((g for g in resp.get("groups", []) if g.get("group_name") == name), None)


def read_ledger() -> dict:
    """Account groups created by this notebook, as {"groups": {group_id: group_name}}."""
    try:
        with open(LEDGER_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"groups": {}}


def write_ledger(ledger: dict) -> None:
    with open(LEDGER_PATH, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2)


def bundle_root() -> str:
    """The bootcamp folder = the folder that holds databricks.yml (this notebook is in bootcamp/instructor/)."""
    nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    d = os.path.dirname(nb_path if nb_path.startswith("/Workspace") else "/Workspace" + nb_path)
    while d not in ("", "/"):
        if os.path.isfile(f"{d}/databricks.yml"):
            return d
        d = os.path.dirname(d)
    raise FileNotFoundError("databricks.yml not found above this notebook - run it from the bootcamp Git folder.")


BUNDLE_ROOT = bundle_root()
print(f"Bootcamp folder: {BUNDLE_ROOT}")


def front_matter(path: str) -> dict:
    """Tiny YAML front-matter reader (key: value lines only)."""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return {}
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        k, sep, v = line.partition(":")
        if sep and not line.startswith(" ") and v.strip():
            out[k.strip()] = v.strip().strip('"')
    return out


def domain_tag_key(name: str) -> str:
    """Governed tag key of a domain: tag_prefix + domain_tag of context/domains/<name>/_domain.md (default: name)."""
    return TAG_PREFIX + front_matter(f"{BUNDLE_ROOT}/context/domains/{name.lower()}/_domain.md").get("domain_tag", name)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Who am I?

# COMMAND ----------

is_ws_admin = spark.sql("SELECT is_member('admins')").first()[0]
record("identity", f"{me} is a workspace admin", "OK" if is_ws_admin else "ERROR",
       "" if is_ws_admin else "run this notebook as a workspace admin")
# The account id (needed for governed-tag permissions) is part of every group the identity proxy returns.
account_id = None
groups_resp, err = api_try("GET", "/api/2.0/identity/groups", query={"page_size": 1})
if groups_resp and groups_resp.get("groups"):
    account_id = groups_resp["groups"][0]["account_id"]
record("identity", "account id resolved via the workspace identity proxy", "OK" if account_id else "WARN",
       account_id or (err or "unknown"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Teardown mode *(after the event - only when `mode` is not `setup`)*
# MAGIC
# MAGIC | `mode` | removes |
# MAGIC |---|---|
# MAGIC | `teardown_domains_and_tags` | domains, subdomains and governed tags of `domain_names` (with `tag_prefix`) that carry the marker |
# MAGIC | `teardown_everything` | the above + catalogs whose name starts with `catalog_prefix` **and** whose comment carries the marker (`DROP CATALOG ... CASCADE`) + the two account groups, if the ledger says this notebook created them |
# MAGIC
# MAGIC Safety rules:
# MAGIC * **Nothing is created or changed** in teardown mode: this cell removes objects and then **stops the notebook**
# MAGIC   (steps 3-10 do not run). The `participants` list is not used, so a catalog a participant already dropped
# MAGIC   with notebook 99 is never re-created.
# MAGIC * Objects **without the marker** - for example a `Finance` domain that existed before and was only reused - are
# MAGIC   reported as **KEEP**.
# MAGIC * A domain is deleted only if all its subdomains are deleted too (deleting a domain deletes its subdomains),
# MAGIC   and a governed tag only if no remaining domain uses it.
# MAGIC * `dry_run = true` prints the plan without deleting anything.
# MAGIC
# MAGIC Participants clean up their own Genie Agents and catalogs with notebook 99. Pages are deleted in
# MAGIC Discover → Pages.

# COMMAND ----------


def delete_group(group_id: str) -> None:
    api("DELETE", f"/api/2.0/identity/groups/{group_id}")
    ledger = read_ledger()
    ledger.get("groups", {}).pop(str(group_id), None)
    write_ledger(ledger)


if MODE == "setup":
    print("mode = setup - no teardown. Continue with step 3.")
else:
    everything = MODE == "teardown_everything"
    roots = {domain_tag_key(n) for n in DOMAIN_NAMES}

    def in_scope(tag_key: str) -> bool:
        """The domain tag itself or one of its subdomain tags ('<domain>/<Subdomain>')."""
        return any(tag_key == r or tag_key.startswith(r + "/") for r in roots)

    # 1) catalogs this notebook pre-created (step 5 writes the marker into the comment)
    if everything:
        for r in spark.sql("SELECT catalog_name, comment FROM system.information_schema.catalogs "
                           "ORDER BY catalog_name").collect():
            if not r.catalog_name.startswith(CATALOG_PREFIX):
                continue
            if MARKER in (r.comment or ""):
                stmt = f"DROP CATALOG IF EXISTS {r.catalog_name} CASCADE"
                act("teardown", stmt, lambda s=stmt: spark.sql(s))
            else:
                record("teardown", f"catalog {r.catalog_name}", "KEEP", "not created by this notebook (no marker in the comment)")

    # 2) domains and subdomains (step 6 writes the marker into the description)
    all_domains = list_all("/api/2.0/domains", "domains")
    ours = {d["tag_key"] for d in all_domains if in_scope(d["tag_key"]) and MARKER in (d.get("description") or "")}
    doomed = set()
    for d in sorted((d for d in all_domains if in_scope(d["tag_key"])), key=lambda d: d["tag_key"] in roots):
        key, kind = d["tag_key"], ("domain" if d["tag_key"] in roots else "subdomain")  # subdomains first
        children = {c["tag_key"] for c in all_domains
                    if c.get("parent_domain_id") == d["domain_id"] or c["tag_key"].startswith(key + "/")}
        if key not in ours:
            record("teardown", f"{kind} '{key}'", "KEEP", "not created by this notebook (no marker in the description)")
        elif children - ours:
            record("teardown", f"{kind} '{key}'", "KEEP", f"has subdomains this notebook did not create: {sorted(children - ours)}")
        else:
            doomed.add(key)
            act("teardown", f"delete {kind} '{key}'", lambda i=d["domain_id"]: api("DELETE", f"/api/2.0/domains/{i}"))

    # 3) governed tags (marker in the description, and no remaining domain uses the tag)
    still_used = {d["tag_key"] for d in all_domains} - doomed
    for t in sorted(list_all("/api/2.1/tag-policies", "tag_policies"), key=lambda t: t["tag_key"] in roots):
        key = t["tag_key"]
        if not in_scope(key):
            continue
        if MARKER not in (t.get("description") or ""):
            record("teardown", f"governed tag '{key}'", "KEEP", "not created by this notebook (no marker in the description)")
        elif key in still_used:
            record("teardown", f"governed tag '{key}'", "KEEP", "a domain that is kept still uses this tag")
        else:
            # encode the '/' of subdomain tags as %2F - a raw '/' is not routed for DELETE
            act("teardown", f"delete governed tag '{key}'",
                lambda k=key: api("DELETE", f"/api/2.1/tag-policies/{urllib.parse.quote(k, safe='')}"))

    # 4) account groups - only those this notebook created (ledger written in step 4)
    if everything:
        created_groups = read_ledger().get("groups", {})
        for gname in (PARTICIPANTS_GROUP, ADMINS_GROUP):
            g = find_group(gname)
            if not g:
                record("teardown", f"account group {gname}", "OK", "does not exist")
            elif str(g["group_id"]) not in created_groups:
                record("teardown", f"account group {gname}", "KEEP", f"not created by this notebook (not in {LEDGER_PATH})")
            else:
                act("teardown", f"delete account group {gname}", lambda i=g["group_id"]: delete_group(i))

    # 5) the router app's Lakebase project - only if the ledger says this notebook created it. Deleting it deletes
    #    the participants' branches in it (their apps stop remembering; notebook 99 deletes the apps).
    if everything and LAKEBASE_PROJECT:
        proj, _ = api_try("GET", f"/api/2.0/postgres/projects/{LAKEBASE_PROJECT}")
        if not proj:
            record("teardown", f"Lakebase project {LAKEBASE_PROJECT}", "OK", "does not exist")
        elif LAKEBASE_PROJECT not in read_ledger().get("lakebase_projects", {}):
            record("teardown", f"Lakebase project {LAKEBASE_PROJECT}", "KEEP", f"not created by this notebook (not in {LEDGER_PATH})")
        else:
            def delete_project():
                api("DELETE", f"/api/2.0/postgres/projects/{LAKEBASE_PROJECT}")
                ledger = read_ledger()
                ledger.get("lakebase_projects", {}).pop(LAKEBASE_PROJECT, None)
                write_ledger(ledger)
            act("teardown", f"delete Lakebase project {LAKEBASE_PROJECT} (and every participant branch in it)", delete_project)

    rows = [list(c) for c in CHECKLIST if c[0] == "teardown"] or [["teardown", "nothing in scope", "-", ""]]
    display(spark.createDataFrame(rows, "area string, item string, status string, detail string"))
    counts = {}
    for c in CHECKLIST:
        counts[c[2]] = counts.get(c[2], 0) + 1
    print("  ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    if DRY_RUN:
        print("\nDry run - nothing was deleted. Review the DRY-RUN lines, then set dry_run = false and run again.")
    print("\nTeardown finished - the setup steps below are not run in teardown mode.")
    dbutils.notebook.exit(json.dumps({"mode": MODE, "dry_run": DRY_RUN, "counts": counts,
                                      "checklist": [dict(zip(("area", "item", "status", "detail"), c)) for c in CHECKLIST]}))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Prerequisites checklist
# MAGIC
# MAGIC ### 3.1 Serverless and workspace previews
# MAGIC The lab runs on **serverless** notebooks, jobs and pipelines. The Genie Agent part needs a few workspace
# MAGIC previews (Admin settings → **Previews**). The notebook reads them through the settings API
# MAGIC (`/api/2.1/settings/<name>`) and tells you which ones to switch on - it does not change them.

# COMMAND ----------

serverless_runtime = os.environ.get("IS_SERVERLESS", "").upper() == "TRUE" or \
    spark.conf.get("spark.databricks.serverless.environmentVersion", None) is not None
record("compute", "this notebook runs on serverless compute", "OK" if serverless_runtime else "WARN",
       "" if serverless_runtime else "attach the notebook to Serverless to be sure participants can too")

SETTINGS = {
    "serverless_compute": "serverless notebooks, jobs and pipelines",
    "managed_mcp_servers": "Databricks managed MCP servers (system.ai.*)",
    "mcp_tools_in_genie_agents": "MCP tools (GitHub) in Genie Agents - Agent mode",
    "genie_spaces_agentic_api": "Agent mode API for Genie Agents",
    "discover_page": "Discover page (Domains, Pages)",
    "enable_lakeview_tags": "tags on Genie Agents (domain tag on the agent)",
}
for name, why in SETTINGS.items():
    value, err = api_try("GET", f"/api/2.1/settings/{name}")
    enabled = bool(value and (value.get("effective_boolean_val") or value.get("boolean_val") or {}).get("value"))
    record("settings", f"{name} ({why})", "OK" if enabled else "ACTION",
           "enabled" if enabled else (err or "disabled - enable it in Admin settings > Previews"))
record("settings", "Pages preview (account level, Beta)", "ACTION",
       "verify in the account console > Previews: 'Pages' must be on (no public API to check)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.2 Domains API and the GitHub managed MCP

# COMMAND ----------

domains_resp, err = api_try("GET", "/api/2.0/domains")
record("domains", "Domains API (/api/2.0/domains, Beta) reachable", "OK" if domains_resp is not None else "ERROR",
       f"{len((domains_resp or {}).get('domains', []))} domain(s) in the account" if domains_resp is not None else err)

mcp, err = api_try("GET", "/api/2.1/unity-catalog/mcp-services", query={"parent": "schemas/system.ai"})
services = [s.get("name", "") for s in (mcp or {}).get("mcp_services", [])]
has_github = "mcp-services/system.ai.github" in services
record("mcp", "managed MCP service system.ai.github exists", "OK" if has_github else "ACTION",
       f"{len(services)} system.ai services" if mcp else (err or "not found - enable 'Managed MCP servers'"))


def principals_with(securable: str, privilege: str) -> set:
    rows = spark.sql(f"SHOW GRANTS ON {securable}").collect()
    return {r["Principal"] for r in rows if r["ActionType"] == privilege}


expected = {"account users", PARTICIPANTS_GROUP}
use_cat = principals_with("CATALOG system", "USE CATALOG")
schema_exec = principals_with("SCHEMA system.ai", "EXECUTE")
schema_use = principals_with("SCHEMA system.ai", "USE SCHEMA")
ok_mcp = bool(use_cat & expected) and bool(schema_exec & expected) and bool(schema_use & expected)
record("mcp", "participants can EXECUTE system.ai.* (USE CATALOG system, USE SCHEMA + EXECUTE system.ai)",
       "OK" if ok_mcp else "ACTION",
       f"via {sorted((schema_exec & expected))}" if ok_mcp else "missing grants")
if not ok_mcp:
    for stmt in (f"GRANT USE CATALOG ON CATALOG system TO `{PARTICIPANTS_GROUP}`",
                 f"GRANT USE SCHEMA, EXECUTE ON SCHEMA system.ai TO `{PARTICIPANTS_GROUP}`"):
        act("mcp", stmt, lambda s=stmt: spark.sql(s), grant=True)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.3 SQL warehouse
# MAGIC Genie Agents run their SQL on a SQL warehouse; participants need **CAN USE** on it (notebook 04 picks the
# MAGIC warehouse automatically). A **serverless** warehouse starts in seconds - recommended for the event.

# COMMAND ----------

warehouses = list(w.warehouses.list())
wh = next((x for x in warehouses if x.id == WAREHOUSE_ID), None) if WAREHOUSE_ID else \
    next((x for x in warehouses if x.enable_serverless_compute), None)
if not wh:
    record("warehouse", "SQL warehouse", "ACTION", "no (serverless) warehouse found - create one (Small, serverless)")
else:
    record("warehouse", f"{wh.name} ({wh.id})", "OK" if wh.enable_serverless_compute else "WARN",
           f"serverless={wh.enable_serverless_compute}, size={wh.cluster_size}, state={wh.state}")
    acl = api("GET", f"/api/2.0/permissions/warehouses/{wh.id}").get("access_control_list", [])
    can_use = {a.get("group_name") or a.get("user_name") or a.get("service_principal_name")
               for a in acl if any(p.get("permission_level") in ("CAN_USE", "CAN_MONITOR", "CAN_MANAGE", "IS_OWNER")
                                   for p in a.get("all_permissions", []))}
    if PARTICIPANTS_GROUP in can_use or "users" in can_use:
        record("warehouse", f"CAN USE for {PARTICIPANTS_GROUP}", "OK",
               "granted to " + (PARTICIPANTS_GROUP if PARTICIPANTS_GROUP in can_use else "'users' (all workspace users)"))
    else:
        act("warehouse", f"grant CAN USE on {wh.name} to {PARTICIPANTS_GROUP}",
            lambda: api("PATCH", f"/api/2.0/permissions/warehouses/{wh.id}",
                        body={"access_control_list": [{"group_name": PARTICIPANTS_GROUP, "permission_level": "CAN_USE"}]}),
            grant=True)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Account groups
# MAGIC
# MAGIC **Account groups vs workspace-local groups.** Unity Catalog grants, row filters and column masks
# MAGIC (`is_account_group_member()`) only understand **account** groups. Groups created in the old workspace
# MAGIC admin page of a non-identity-federated workspace are *workspace-local* and do **not** work for UC.
# MAGIC This notebook creates account groups through the workspace **identity proxy API**
# MAGIC (`/api/2.0/identity/groups`, Beta) - a workspace admin can do that without account-console access -
# MAGIC assigns them to this workspace and adds the members. If your participants come from an IdP (SCIM),
# MAGIC you can create the groups there instead; just keep the names.
# MAGIC
# MAGIC | group | members | used for |
# MAGIC |---|---|---|
# MAGIC | `cpg_bootcamp_participants` | every participant | warehouse CAN USE, MCP EXECUTE, tag ASSIGN, catalog grants |
# MAGIC | `cpg_bootcamp_admins` | instructors | bypass every row filter / mask of the lab (notebook 03) |
# MAGIC
# MAGIC Participants must already be **users of the account** (invited to the workspace). Unknown e-mails are
# MAGIC reported as ACTION. Groups this notebook creates are written to the ledger file, so that
# MAGIC `teardown_everything` deletes them - and only them - after the event.

# COMMAND ----------


def find_user(email: str):
    resp = api("GET", "/api/2.0/identity/users", query={"filter": f'username eq "{email}"'})
    return next((u for u in resp.get("users", []) if u.get("username", "").lower() == email.lower()), None)


def create_group(name: str) -> dict:
    group = api("POST", "/api/2.0/identity/groups", body={"group_name": name})
    ledger = read_ledger()
    ledger.setdefault("groups", {})[str(group["group_id"])] = name
    write_ledger(ledger)
    return group


def assign_to_workspace(group_id: str) -> None:
    # Right after creating a group the GET below can 404 although the assignment exists -> "already assigned" is fine.
    _, err = api_try("POST", "/api/2.0/identity/workspace-assignments",
                     body={"principal_id": int(group_id), "entitlements": ["WORKSPACE_ACCESS"]})
    if err and "already assigned" not in err:
        raise RuntimeError(err)


def ensure_group(name: str):
    group = find_group(name)
    if group:
        created_here = str(group["group_id"]) in read_ledger().get("groups", {})
        record("groups", f"account group {name}", "OK", f"exists (id {group['group_id']}, "
               + ("created by this notebook)" if created_here else "not created by this notebook - teardown keeps it)"))
    elif not CREATE_GROUPS:
        record("groups", f"account group {name}", "ACTION", "does not exist and create_groups = false - "
               "create it (IdP / account console) with exactly this name")
    else:
        group = act("groups", f"create account group {name}", lambda: create_group(name))
    if not group:
        return None
    assignment, _ = api_try("GET", f"/api/2.0/identity/workspace-assignments/{group['group_id']}")
    if assignment:
        record("groups", f"{name} assigned to this workspace", "OK", ", ".join(assignment.get("entitlements", [])))
    else:
        act("groups", f"assign {name} to this workspace (WORKSPACE_ACCESS)",
            lambda: assign_to_workspace(group["group_id"]))
    return group


def ensure_members(group, group_name: str, emails: list):
    member_ids = set()
    if group:
        members = api("GET", f"/api/2.0/identity/groups/{group['group_id']}/direct-members").get("direct_group_members", [])
        member_ids = {str(m["principal_id"]) for m in members}
    for e in emails:
        user = find_user(e)
        if not user:
            record("groups", f"{e} -> {group_name}", "ACTION", "not a user of the account yet - invite first")
        elif str(user["user_id"]) in member_ids:
            record("groups", f"{e} -> {group_name}", "OK", "already a member")
        elif not group:
            record("groups", f"add {e} to {group_name}", "DRY-RUN" if DRY_RUN else "SKIP", "group does not exist yet")
        else:
            act("groups", f"add {e} to {group_name}",
                lambda u=user: api("POST", f"/api/2.0/identity/groups/{group['group_id']}/direct-members",
                                   body={"principal_id": int(u["user_id"])}))


participants_group = ensure_group(PARTICIPANTS_GROUP)
admins_group = ensure_group(ADMINS_GROUP)
ensure_members(participants_group, PARTICIPANTS_GROUP, PARTICIPANTS)
ensure_members(admins_group, ADMINS_GROUP, INSTRUCTORS)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Catalog strategy
# MAGIC
# MAGIC Every participant works in **their own catalog** `cpg_<short name>` (the bundle computes the same name).
# MAGIC On a **Default-Storage** metastore `CREATE CATALOG` without a location fails for SQL/API callers
# MAGIC ("Metastore storage root URL does not exist") - so pick one of:
# MAGIC
# MAGIC | strategy | what this notebook does | participant experience |
# MAGIC |---|---|---|
# MAGIC | `precreate` *(recommended)* | `CREATE CATALOG cpg_<short> MANAGED LOCATION '<managed_location>'`, then makes the participant the **owner** | notebook 01 finds the catalog and just continues |
# MAGIC | `grant_create_catalog` | `GRANT CREATE CATALOG ON METASTORE TO cpg_bootcamp_participants` | notebook 01 creates it (needs `managed_location` + `CREATE MANAGED STORAGE` on that external location, or Default Storage via the UI) |
# MAGIC | `none` | nothing | participants create the catalog in Catalog Explorer (Create catalog → default storage) before notebook 01 |
# MAGIC
# MAGIC Ownership matters: the owner can create schemas, functions, row filters, masks and ABAC policies in the
# MAGIC catalog and can drop it again in notebook 99. Catalogs created here carry the marker in their comment;
# MAGIC `teardown_everything` drops only those.

# COMMAND ----------

if CATALOG_STRATEGY == "precreate":
    if not PARTICIPANTS:
        record("catalogs", "pre-create participant catalogs", "ACTION", "participants widget is empty")
    if PARTICIPANTS and not MANAGED_LOCATION:
        record("catalogs", "managed_location", "WARN", "empty - CREATE CATALOG may fail on a Default-Storage metastore")
    existing = {r.catalog_name: r.comment or "" for r in spark.sql(
        "SELECT catalog_name, comment FROM system.information_schema.catalogs").collect()}
    for email in PARTICIPANTS:
        name = CATALOG_PREFIX + bundle_short_name(email)
        if name in existing:
            record("catalogs", f"catalog {name}", "OK", "exists (" + (
                "created by this notebook)" if MARKER in existing[name] else "not created by this notebook - teardown keeps it)"))
        else:
            location = f" MANAGED LOCATION '{MANAGED_LOCATION}'" if MANAGED_LOCATION else ""
            stmt = f"CREATE CATALOG IF NOT EXISTS {name}{location} COMMENT 'Genie bootcamp catalog of {email} {MARKER}'"
            act("catalogs", stmt, lambda s=stmt: spark.sql(s))
        owner = None
        try:
            owner = w.catalogs.get(name).owner
        except Exception:
            pass
        if owner and owner.lower() == email.lower():
            record("catalogs", f"{name} owned by {email}", "OK")
        else:
            stmt = f"ALTER CATALOG {name} OWNER TO `{email}`"
            act("catalogs", stmt, lambda s=stmt: spark.sql(s), grant=True)
elif CATALOG_STRATEGY == "grant_create_catalog":
    stmt = f"GRANT CREATE CATALOG ON METASTORE TO `{PARTICIPANTS_GROUP}`"
    act("catalogs", stmt, lambda: spark.sql(stmt), grant=True)
    record("catalogs", "managed storage for participant catalogs", "ACTION",
           "grant CREATE MANAGED STORAGE on the external location participants pass as managed_location, "
           "or let them create the catalog in the UI (default storage)")
else:
    record("catalogs", "participants create their catalog in Catalog Explorer", "ACTION",
           "Catalog Explorer > + > Create catalog > name cpg_<short name>, default storage")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · UC Semantics: governed tags and domains
# MAGIC
# MAGIC A **domain** (Discover → Domains) *is* a governed tag: an asset belongs to the domain when it carries
# MAGIC the tag (schema tags are inherited by tables). Rules verified against the Domains API (Beta):
# MAGIC
# MAGIC 1. create the **governed tag** first (tag policy **without values**),
# MAGIC 2. create the domain with `tag_key` = that tag (`POST /api/2.0/domains`, created as draft),
# MAGIC 3. a **subdomain** needs its own governed tag named `<domain tag>/<Subdomain>` and `parent_domain_id`,
# MAGIC 4. **publish** with `PATCH /api/2.0/domains/<id>?update_mask=draft` (`draft = false`).
# MAGIC
# MAGIC Names, subtitles and descriptions come from `bootcamp/context/domains/**/_domain.md` and
# MAGIC `_subdomain.md` front matter (fallback: the industry model's tags in `bootcamp/model_tags/`). Participants later apply
# MAGIC the value-less tags in notebook 05: `ALTER SCHEMA <catalog>.finance SET TAGS ('Finance')`.
# MAGIC
# MAGIC Every governed tag and domain created here gets the marker at the end of its description (teardown
# MAGIC deletes only those). Existing ones with the same name are reused as they are.

# COMMAND ----------


def title_case(snake: str) -> str:
    return " ".join(p.capitalize() for p in snake.split("_"))


ICONS = {"Consumer": "ADDRESS_BOOK", "Finance": "COINS", "Manufacturing": "SPEEDOMETER"}
COLORS = {"Consumer": "#1565C0", "Finance": "#2E7D32", "Manufacturing": "#EF6C00"}

# The industry model's domain description and subdomains (in model order), from bootcamp/model_tags/.
model = {}
for name in DOMAIN_NAMES:
    try:
        doc = json.load(open(f"{BUNDLE_ROOT}/model_tags/{name.lower()}.json", encoding="utf-8"))
    except OSError:
        print(f"(model_tags/{name.lower()}.json not found - using context/ only)")
        continue
    subs = []
    for t in doc["tables"].values():
        sd = t["table_tags"].get("dbx_subdomain")
        if sd and sd not in subs:
            subs.append(sd)
    model[name.lower()] = {"description": doc.get("schema_comment", ""), "subdomains": [{"name": x} for x in subs]}

PLAN = []  # (tag_key, parent_tag_key, subtitle, description, icon, color)
for name in DOMAIN_NAMES:
    folder = name.lower()
    fm = front_matter(f"{BUNDLE_ROOT}/context/domains/{folder}/_domain.md")
    md = model.get(folder, {})
    key = domain_tag_key(name)
    PLAN.append((key, None, fm.get("subtitle", f"Fjällmark {name}"),
                 fm.get("description", md.get("description", f"{name} domain of Fjällmark Consumer Goods (bootcamp)")),
                 ICONS.get(name, "PACKAGE"), COLORS.get(name, "#455A64")))
    if CREATE_SUBDOMAINS:
        subs = [s["name"] for s in md.get("subdomains", [])]
        ctx_dir = f"{BUNDLE_ROOT}/context/domains/{folder}"
        if not subs and os.path.isdir(ctx_dir):
            subs = sorted(d for d in os.listdir(ctx_dir) if os.path.isdir(f"{ctx_dir}/{d}") and d != "pages")
        for sub in subs:
            sfm = front_matter(f"{ctx_dir}/{sub}/_subdomain.md")
            sub_title = sfm.get("subdomain", title_case(sub))
            PLAN.append((f"{key}/{sub_title}", key, f"{name} - {sub_title}",
                         sfm.get("description", f"Subdomain {sub_title} of {name}"),
                         ICONS.get(name, "PACKAGE"), COLORS.get(name, "#455A64")))
for p in PLAN:
    print(("    " if p[1] else "") + p[0])

# COMMAND ----------


def origin(obj: dict) -> str:
    return "created by this notebook" if MARKER in (obj.get("description") or "") else "reused - teardown keeps it"


tag_policies = {t["tag_key"]: t for t in list_all("/api/2.1/tag-policies", "tag_policies")}
domains = {d["tag_key"]: d for d in list_all("/api/2.0/domains", "domains")}

for key, parent, subtitle, description, icon, color in PLAN:
    # 1) governed tag (tag policy without values)
    if key in tag_policies:
        record("tags", f"governed tag '{key}'", "OK", f"exists ({origin(tag_policies[key])})")
    else:
        created = act("tags", f"create governed tag '{key}'",
                      lambda k=key, d=description: api("POST", "/api/2.1/tag-policies",
                                                       body={"tag_key": k, "description": f"{d[:190]} {MARKER}"}))
        if created:
            tag_policies[key] = created
    # 2) domain / subdomain
    if key in domains:
        record("domains", f"{'subdomain' if parent else 'domain'} '{key}'", "OK",
               f"exists ({'draft' if domains[key].get('effective_draft') else 'published'}, {origin(domains[key])})")
    else:
        parent_id = domains.get(parent, {}).get("domain_id") if parent else None
        if parent and not parent_id:
            record("domains", f"subdomain '{key}'", "DRY-RUN" if DRY_RUN else "ERROR", "parent domain not created")
            continue
        body = {"tag_key": key, "draft": True, "subtitle": subtitle[:120], "description": f"{description} {MARKER}",
                "icon": {"name": icon, "color": color}, **({"parent_domain_id": parent_id} if parent_id else {})}
        created = act("domains", f"create {'subdomain' if parent else 'domain'} '{key}'",
                      lambda b=body: api("POST", "/api/2.0/domains", body=b))
        if created:
            domains[key] = created
            if (created.get("icon") or {}).get("name") != icon:
                record("domains", f"icon {icon} for '{key}'", "WARN", "icon name not accepted - edit it in Discover")
    # 3) publish
    d = domains.get(key)
    if d and PUBLISH_DOMAINS and d.get("effective_draft", d.get("draft", True)):
        updated = act("domains", f"publish '{key}' (draft = false)",
                      lambda i=d["domain_id"]: api("PATCH", f"/api/2.0/domains/{i}",
                                                   query={"update_mask": "draft"}, body={"draft": False}))
        if updated:
            domains[key] = updated

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Let participants ASSIGN the governed tags
# MAGIC
# MAGIC Applying a governed tag needs **two** permissions: `APPLY TAG` on the object (participants own their
# MAGIC catalog, so they have it) **and** `ASSIGN` on the governed tag. Governed-tag permissions are managed
# MAGIC with the **Account Access Control Proxy** API (also in the UI: Catalog → Govern → Governed tags →
# MAGIC *tag* → Permissions):
# MAGIC
# MAGIC * resource `accounts/<account_id>/tagPolicies/<tag_policy_id>`, rule set `.../ruleSets/default`
# MAGIC * roles: `roles/tagPolicy.assigner` (= ASSIGN) and `roles/tagPolicy.manager` (= MANAGE)
# MAGIC * `GET /api/2.0/preview/accounts/access-control/rule-sets?name=<rule set>&etag=` then
# MAGIC   `PUT /api/2.0/preview/accounts/access-control/rule-sets` with the full rule list and the etag
# MAGIC
# MAGIC Besides the domain tags we grant `class.name` (system governed tag) for the optional ABAC exercise in
# MAGIC notebook 03. Account-wide ASSIGN on *all* governed tags would be the `accounts/<account_id>` rule set -
# MAGIC deliberately not used here (least privilege).

# COMMAND ----------

ASSIGN_TAGS = [p[0] for p in PLAN] + ["class.name"]
all_policies = {t["tag_key"]: t for t in list_all("/api/2.1/tag-policies", "tag_policies")}
principal = f"groups/{PARTICIPANTS_GROUP}"
for key in ASSIGN_TAGS:
    policy = all_policies.get(key)
    if not policy:
        record("tag-perms", f"ASSIGN on '{key}' for {PARTICIPANTS_GROUP}", "DRY-RUN" if DRY_RUN else "WARN",
               "governed tag does not exist yet")
        continue
    name = f"accounts/{account_id}/tagPolicies/{policy['id']}/ruleSets/default"
    rule_set, err = api_try("GET", "/api/2.0/preview/accounts/access-control/rule-sets", query={"name": name, "etag": ""})
    if not rule_set:
        record("tag-perms", f"read permissions of '{key}'", "ERROR", err)
        continue
    rules = rule_set.get("grant_rules", [])
    if any(r.get("role") == "roles/tagPolicy.assigner" and principal in r.get("principals", []) for r in rules):
        record("tag-perms", f"ASSIGN on '{key}' for {PARTICIPANTS_GROUP}", "OK", "already granted")
        continue
    new_rules = [dict(r) for r in rules]
    assigner = next((r for r in new_rules if r.get("role") == "roles/tagPolicy.assigner"), None)
    if assigner:
        assigner["principals"] = sorted(set(assigner.get("principals", [])) | {principal})
    else:
        new_rules.append({"role": "roles/tagPolicy.assigner", "principals": [principal]})
    act("tag-perms", f"grant ASSIGN on '{key}' to {PARTICIPANTS_GROUP}",
        lambda n=name, e=rule_set.get("etag"), r=new_rules: api(
            "PUT", "/api/2.0/preview/accounts/access-control/rule-sets",
            body={"name": n, "rule_set": {"name": n, "etag": e, "grant_rules": r}}),
        grant=True)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8 · GitHub: Git folders and the GitHub MCP
# MAGIC
# MAGIC Two different things read the repository:
# MAGIC
# MAGIC | who | how | private repository needs |
# MAGIC |---|---|---|
# MAGIC | participants' **Git folder** (clone into the workspace) | Workspace → Create → Git folder → URL | every participant has read access on GitHub **and** a Git credential (GitHub PAT or the Databricks GitHub App) in User settings → Linked accounts |
# MAGIC | **GitHub MCP** (`system.ai.github`) in Genie Code / Agent mode | per-user GitHub OAuth | a GitHub org admin installs the [Databricks GitHub connector app](https://github.com/apps/databricks-github-connector) on the org and grants it this repository |
# MAGIC
# MAGIC The simplest event setup is a **public** repository (no credentials, no app). The cell below checks the
# MAGIC repository visibility anonymously through the GitHub REST API.

# COMMAND ----------

visibility, detail = "unknown", ""
try:
    req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "genie-bootcamp-setup"})
    with urllib.request.urlopen(req, timeout=10) as r:
        info = json.load(r)
    visibility = "private" if info.get("private") else "public"
    detail = f"default branch {info.get('default_branch')}"
except urllib.error.HTTPError as e:
    visibility, detail = ("private or missing", "GitHub returns 404 to anonymous callers") if e.code == 404 \
        else ("unknown", f"HTTP {e.code}")
except Exception as e:
    detail = f"could not reach api.github.com from serverless ({str(e)[:80]}) - check manually"
if visibility == "public":
    record("github", f"https://github.com/{GITHUB_REPO} is public", "OK", detail)
else:
    record("github", f"https://github.com/{GITHUB_REPO} is {visibility}", "ACTION",
           f"{detail}. Before the event EITHER make the repository public, OR install "
           "https://github.com/apps/databricks-github-connector on the org for this repository AND make sure every "
           "participant can read it (GitHub account added to the repo/org + Git credential in Databricks)")
record("github", "each participant has a GitHub account (needed for the GitHub MCP OAuth sign-in)", "ACTION",
       "announce in the event invitation")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8b · Lakebase project for the router app (lab step 6)
# MAGIC
# MAGIC Notebook 06 deploys each participant's **router app** (Databricks App from the template *Custom Agent
# MAGIC (Advanced)*), which keeps conversation memory in Lakebase Postgres. One Lakebase project serves the whole
# MAGIC bootcamp; notebook 06 gives every participant **their own branch** of it (copy-on-write, own `databricks_postgres`
# MAGIC database and own compute that suspends when idle), because the template's tables live in the default database
# MAGIC under fixed schema names and two apps must never share them.
# MAGIC
# MAGIC This step creates the project (autoscaling 0.5-4 CU, suspends after 10 idle minutes) and grants the
# MAGIC participants group **CAN USE** on it. The project goes into the ledger, so `teardown_everything` deletes it.

# COMMAND ----------

LAKEBASE_SPEC = {"spec": {"display_name": "Fjällmark Genie bootcamp - router app memory",
                          "default_endpoint_settings": {"autoscaling_limit_min_cu": 0.5, "autoscaling_limit_max_cu": 4,
                                                        "suspend_timeout_duration": "600s"}}}


def create_lakebase_project():
    op = api("POST", "/api/2.0/postgres/projects", query={"project_id": LAKEBASE_PROJECT}, body=LAKEBASE_SPEC)
    for _ in range(120):
        if op.get("done"):
            break
        time.sleep(5)
        op = api("GET", f"/api/2.0/postgres/{op['name']}")
    if op.get("error") or not op.get("done"):
        raise RuntimeError(f"project creation: {op.get('error') or 'not done after 10 minutes'}")
    ledger = read_ledger()
    ledger.setdefault("lakebase_projects", {})[LAKEBASE_PROJECT] = MARKER
    write_ledger(ledger)


if not LAKEBASE_PROJECT:
    record("lakebase", "Lakebase project", "SKIP", "lakebase_project is blank - lab step 6 (router app) is not prepared")
else:
    proj, err = api_try("GET", f"/api/2.0/postgres/projects/{LAKEBASE_PROJECT}")
    if proj:
        record("lakebase", f"project {LAKEBASE_PROJECT}", "OK", f"exists (owner {(proj.get('status') or {}).get('owner')})")
    elif err and "not found" not in err.lower() and "does not exist" not in err.lower():
        record("lakebase", f"project {LAKEBASE_PROJECT}", "ERROR", f"cannot read it: {err[:200]}")
    else:
        act("lakebase", f"create project {LAKEBASE_PROJECT}", create_lakebase_project, "autoscaling 0.5-4 CU, branch production")
    perms, err = api_try("GET", f"/api/2.0/permissions/database-projects/{LAKEBASE_PROJECT}")
    has_use = any(a.get("group_name") == PARTICIPANTS_GROUP
                  and any(p.get("permission_level") in ("CAN_USE", "CAN_MANAGE") for p in a.get("all_permissions", []))
                  for a in (perms or {}).get("access_control_list", []))
    if has_use:
        record("lakebase", f"CAN USE on {LAKEBASE_PROJECT} for {PARTICIPANTS_GROUP}", "OK")
    else:
        act("lakebase", f"grant CAN USE on {LAKEBASE_PROJECT} to {PARTICIPANTS_GROUP}",
            lambda: api("PATCH", f"/api/2.0/permissions/database-projects/{LAKEBASE_PROJECT}",
                        body={"access_control_list": [{"group_name": PARTICIPANTS_GROUP, "permission_level": "CAN_USE"}]}),
            grant=True)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9 · Pages: bulk-import the official business glossary (UI, once per event)
# MAGIC
# MAGIC There is no Pages API, so this is a UI step. Full instructions: `bootcamp/context/README.md` (step A).
# MAGIC
# MAGIC 1. Prerequisites: the domains from step 6 are **published**, the account preview **Pages** is on, the
# MAGIC    GitHub MCP can read the repository (step 8).
# MAGIC 2. **Discover → Pages → Create page**, open the **Genie Code** pane, click **Bulk import pages**.
# MAGIC 3. In the chat box click **+ → Connections → GitHub** (`system.ai.github`), sign in to GitHub.
# MAGIC 4. Ask Genie Code to import every file in `bootcamp/context/domains/*/pages/` of the repository (branch `main`),
# MAGIC    using the YAML front matter (`title`, `domain`/`subdomain`, `synonyms`, `description`, body,
# MAGIC    `related_assets` with `<catalog>` replaced by your instructor catalog, `sources`).
# MAGIC 5. Review the proposed list, fix the (sub)domain of each page, create them (drafts), review and **publish**.
# MAGIC
# MAGIC Pages are account-level and shared: participants only create **draft** pages of their own.

# COMMAND ----------

pages_dir = f"{BUNDLE_ROOT}/context/domains"
page_files = []
if os.path.isdir(pages_dir):
    for dom in sorted(os.listdir(pages_dir)):
        pdir = f"{pages_dir}/{dom}/pages"
        if os.path.isdir(pdir):
            page_files += [f"{dom}/pages/{f}" for f in sorted(os.listdir(pdir)) if f.endswith(".md")]
record("pages", "page files in bootcamp/context/domains/*/pages", "OK" if page_files else "WARN",
       f"{len(page_files)} files to import" if page_files else f"{pages_dir} not found (run from the Git folder)")
record("pages", "bulk-import the Pages with Genie Code (UI) and publish them", "ACTION", "see step 9")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10 · Summary

# COMMAND ----------

summary = spark.createDataFrame([list(c) for c in CHECKLIST], "area string, item string, status string, detail string")
display(summary)
counts = {}
for c in CHECKLIST:
    counts[c[2]] = counts.get(c[2], 0) + 1
print("  ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
if DRY_RUN:
    print("\nDry run - nothing was changed. Review the DRY-RUN lines, then set dry_run = false and run again.")
print("\nAfter the event: run again with mode = teardown_domains_and_tags or teardown_everything.")

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"mode": MODE, "dry_run": DRY_RUN, "counts": counts,
                                  "checklist": [dict(zip(("area", "item", "status", "detail"), c)) for c in CHECKLIST]}))
