# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 00 · Instructor setup - Manufacturing domain (admins only - run once before the event)
# MAGIC
# MAGIC Prepares the **Manufacturing domain** for the Manufacturing sample (`bootcamp_domain/manufacturing/`): the governed tags, the UC Semantics
# MAGIC domain **Manufacturing** with its subdomains, and the permission to *assign* those tags. Participants do **not** run
# MAGIC this notebook; their notebook 05 applies the tags.
# MAGIC
# MAGIC | step | what | needs |
# MAGIC |---|---|---|
# MAGIC | 2 | **who am I** - admin check, account id | workspace admin |
# MAGIC | 3 | **prerequisites** for domains: Domains API, Discover, tags on Genie Agents; **3.3** the SQL warehouse id (no permission check) | workspace admin |
# MAGIC | 4 | **governed tags + domain** `Manufacturing` with its subdomains, published | CREATE on governed tags |
# MAGIC | 5 | the participants group may **ASSIGN** the domain tags | MANAGE on the governed tags |
# MAGIC | 6 | **all tags** of the domain: definitions (API) and where they are applied (SQL on the warehouse) | the SQL warehouse |
# MAGIC | 7 | summary | |
# MAGIC | T | **teardown** *(after the event)*: `mode = teardown_domain` removes what this notebook created and stops | same as above |
# MAGIC
# MAGIC Not in this notebook (the bootcamp's [`00_instructor_setup`](../../../bootcamp/instructor/00_instructor_setup.py) does
# MAGIC them): account groups, catalogs, warehouse permissions, GitHub MCP, Pages. See [`00_INSTRUCTOR.md`](../00_INSTRUCTOR.md).
# MAGIC
# MAGIC ▶ **How to run:** attach to **Serverless** and **Run all**. `dry_run = false` is the default: the notebook makes
# MAGIC the changes. Set `dry_run = true` for a check-only run.
# MAGIC
# MAGIC 🔁 **Re-running is a no-op / diff:** existing tags and domains are reported as **OK** and reused as they are.
# MAGIC
# MAGIC **What does teardown remove?** Only what this notebook **created**: its governed tags and domains carry the
# MAGIC marker `[created by genie_bootcamp/bootcamp_domain/manufacturing/00_instructor_setup]` in their description. A `Manufacturing`
# MAGIC domain that already existed - for example created by the bootcamp's instructor notebook - is reused and kept.
# MAGIC
# MAGIC > Domains and governed tags are **account-level** objects visible to every workspace of the account. Testing?
# MAGIC > Use `tag_prefix = zz_test_` and finish with `mode = teardown_domain`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | default | meaning |
# MAGIC |---|---|---|
# MAGIC | `mode` | `setup` | `setup` = steps 3-7 · *after the event:* `teardown_domain` |
# MAGIC | `dry_run` | `false` | `false` = make the changes; `true` = only check and report |
# MAGIC | `confirm_teardown` | blank | teardown deletes only when this equals `teardown_domain` - otherwise it is a dry run |
# MAGIC | `apply_grants` | `true` | `false` = never change the tag ASSIGN permissions - report only |
# MAGIC | `participants_group` | `cpg_bootcamp_participants` | the account group that gets ASSIGN on the domain tags (not created here) |
# MAGIC | `warehouse_id` | blank = first serverless warehouse | the SQL warehouse step 6 runs its tag queries on |
# MAGIC | `tag_prefix` | blank | prefix for every tag key (use `zz_test_` when testing) |
# MAGIC | `create_subdomains` / `publish_domains` | `true` / `true` | subdomains from the industry model; publish (draft = false) so everybody sees them |

# COMMAND ----------

import json
import os
import re
import time
import urllib.parse

from databricks.sdk import WorkspaceClient

SAMPLE = "manufacturing"
DOMAIN = "Manufacturing"       # the one domain of this sample

dbutils.widgets.dropdown("mode", "setup", ["setup", "teardown_domain"], "00 Mode")
dbutils.widgets.dropdown("dry_run", "false", ["true", "false"], "01 Dry run")
dbutils.widgets.text("confirm_teardown", "", "02 Teardown: type teardown_domain to confirm")
dbutils.widgets.dropdown("apply_grants", "true", ["true", "false"], "03 Apply permission changes")
dbutils.widgets.text("participants_group", "cpg_bootcamp_participants", "04 Participants group")
dbutils.widgets.text("warehouse_id", "", "05 SQL warehouse id (blank = auto)")
dbutils.widgets.text("tag_prefix", "", "06 Tag prefix (zz_test_ when testing)")
dbutils.widgets.dropdown("create_subdomains", "true", ["true", "false"], "07 Create subdomains")
dbutils.widgets.dropdown("publish_domains", "true", ["true", "false"], "08 Publish domains")

MODE = dbutils.widgets.get("mode")
DRY_RUN = dbutils.widgets.get("dry_run") == "true"
if MODE != "setup" and not DRY_RUN and dbutils.widgets.get("confirm_teardown").strip() != MODE:
    DRY_RUN = True
    print(f"Teardown guard: confirm_teardown is not '{MODE}', so this run is a DRY RUN (nothing is deleted).\n")
APPLY_GRANTS = dbutils.widgets.get("apply_grants") == "true"
PARTICIPANTS_GROUP = dbutils.widgets.get("participants_group").strip()
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id").strip()
TAG_PREFIX = dbutils.widgets.get("tag_prefix")
CREATE_SUBDOMAINS = dbutils.widgets.get("create_subdomains") == "true"
PUBLISH_DOMAINS = dbutils.widgets.get("publish_domains") == "true"

w = WorkspaceClient()
me = spark.sql("SELECT current_user()").first()[0]
print(f"Instructor : {me}")
print(f"Mode       : {MODE.upper()} - {'DRY RUN (nothing is changed)' if DRY_RUN else 'APPLY CHANGES'}"
      f"{'' if APPLY_GRANTS or MODE != 'setup' else ' - permission changes disabled (apply_grants = false)'}")
print(f"Domain     : {TAG_PREFIX + DOMAIN} (sample {SAMPLE})")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Helpers
# MAGIC `record()` writes one line of the checklist printed at the end. `act()` performs a change only when
# MAGIC `dry_run = false` (and, for permission changes, `apply_grants = true`). In teardown mode `act()` refuses
# MAGIC every change that is not part of the teardown.
# MAGIC Status values: **OK** verified · **DONE** changed now · **DRY-RUN** would change · **ACTION** manual step
# MAGIC needed · **WARN** · **ERROR** · **SKIP** · **KEEP** (teardown: not created by this notebook, left alone).

# COMMAND ----------

CHECKLIST = []
MARKER = f"[created by genie_bootcamp/bootcamp_domain/{SAMPLE}/00_instructor_setup]"


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


def bundle_root() -> str:
    """The sample folder = the folder that holds databricks.yml (this notebook is in bootcamp_domain/<sample>/01_notebooks/)."""
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


BUNDLE_ROOT = bundle_root()                                  # <repo>/bootcamp_domain/<sample>
CONTEXT_DIR = f"{os.path.dirname(os.path.dirname(BUNDLE_ROOT))}/bootcamp/context/domains/{SAMPLE}"
print(f"Sample folder : {BUNDLE_ROOT}")
print(f"Domain context: {CONTEXT_DIR}")


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


# Governed tag key of the domain: tag_prefix + domain_tag of bootcamp/context/domains/<sample>/_domain.md.
ROOT_KEY = TAG_PREFIX + front_matter(f"{CONTEXT_DIR}/_domain.md").get("domain_tag", DOMAIN)


def in_scope(tag_key: str) -> bool:
    """The domain tag itself or one of its subdomain tags ('<domain>/<Subdomain>')."""
    return tag_key == ROOT_KEY or tag_key.startswith(ROOT_KEY + "/")

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
# MAGIC ## Teardown mode *(after the event - only when `mode = teardown_domain`)*
# MAGIC
# MAGIC Removes the subdomains, the domain and the governed tags of **Manufacturing** that carry this notebook's marker, then
# MAGIC **stops the notebook** (steps 3-7 do not run). Objects without the marker are reported as **KEEP**. A domain is
# MAGIC deleted only if all its subdomains are deleted too, and a governed tag only if no remaining domain uses it. The
# MAGIC run deletes only when `confirm_teardown = teardown_domain`; otherwise it prints the plan.
# MAGIC
# MAGIC Run it after the participants removed their tags with notebook 99 (a dropped catalog takes its tags with it).

# COMMAND ----------

if MODE == "setup":
    print("mode = setup - no teardown. Continue with step 3.")
else:
    # 1) domains and subdomains (step 4 writes the marker into the description)
    all_domains = list_all("/api/2.0/domains", "domains")
    ours = {d["tag_key"] for d in all_domains if in_scope(d["tag_key"]) and MARKER in (d.get("description") or "")}
    doomed = set()
    for d in sorted((d for d in all_domains if in_scope(d["tag_key"])), key=lambda d: d["tag_key"] == ROOT_KEY):
        key, kind = d["tag_key"], ("domain" if d["tag_key"] == ROOT_KEY else "subdomain")  # subdomains first
        children = {c["tag_key"] for c in all_domains
                    if c.get("parent_domain_id") == d["domain_id"] or c["tag_key"].startswith(key + "/")}
        if key not in ours:
            record("teardown", f"{kind} '{key}'", "KEEP", "not created by this notebook (no marker in the description)")
        elif children - ours:
            record("teardown", f"{kind} '{key}'", "KEEP", f"has subdomains this notebook did not create: {sorted(children - ours)}")
        else:
            doomed.add(key)
            act("teardown", f"delete {kind} '{key}'", lambda i=d["domain_id"]: api("DELETE", f"/api/2.0/domains/{i}"))

    # 2) governed tags (marker in the description, and no remaining domain uses the tag)
    still_used = {d["tag_key"] for d in all_domains} - doomed
    for t in sorted(list_all("/api/2.1/tag-policies", "tag_policies"), key=lambda t: t["tag_key"] == ROOT_KEY):
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

    rows = [list(c) for c in CHECKLIST if c[0] == "teardown"] or [["teardown", "nothing in scope", "-", ""]]
    display(spark.createDataFrame(rows, "area string, item string, status string, detail string"))
    counts = {}
    for c in CHECKLIST:
        counts[c[2]] = counts.get(c[2], 0) + 1
    print("  ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    if DRY_RUN:
        print("\nDry run - nothing was deleted. Review the DRY-RUN lines, then set confirm_teardown = teardown_domain "
              "(and dry_run = false) and run again.")
    print("\nTeardown finished - the setup steps below are not run in teardown mode.")
    dbutils.notebook.exit(json.dumps({"sample": SAMPLE, "mode": MODE, "dry_run": DRY_RUN, "counts": counts,
                                      "checklist": [dict(zip(("area", "item", "status", "detail"), c)) for c in CHECKLIST]}))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Prerequisites checklist
# MAGIC
# MAGIC ### 3.1 Domains API and the workspace previews for domains
# MAGIC Domains need the Domains API (Beta) and the **Discover** page; notebook 05 also tags the Genie Agent, which
# MAGIC needs *tags on Genie Agents*. The notebook reads the previews through the settings API and tells you which
# MAGIC ones to switch on - it does not change them.

# COMMAND ----------

domains_resp, err = api_try("GET", "/api/2.0/domains")
record("domains", "Domains API (/api/2.0/domains, Beta) reachable", "OK" if domains_resp is not None else "ERROR",
       f"{len((domains_resp or {}).get('domains', []))} domain(s) in the account" if domains_resp is not None else err)

SETTINGS = {
    "discover_page": "Discover page (Domains, Pages)",
    "enable_lakeview_tags": "tags on Genie Agents (domain tag on the agent)",
}
for name, why in SETTINGS.items():
    value, err = api_try("GET", f"/api/2.1/settings/{name}")
    enabled = bool(value and (value.get("effective_boolean_val") or value.get("boolean_val") or {}).get("value"))
    record("settings", f"{name} ({why})", "OK" if enabled else "ACTION",
           "enabled" if enabled else (err or "disabled - enable it in Admin settings > Previews"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.3 SQL warehouse
# MAGIC Step 6 runs its tag queries on a SQL warehouse. This step only resolves the warehouse **id**: the
# MAGIC `warehouse_id` widget, or else the first serverless warehouse (then any warehouse). It does **not** check or
# MAGIC change warehouse permissions - participants' warehouse access is not part of this notebook.

# COMMAND ----------

warehouses = list(w.warehouses.list())
wh = next((x for x in warehouses if x.id == WAREHOUSE_ID), None) if WAREHOUSE_ID else \
    next((x for x in warehouses if x.enable_serverless_compute), None) or next(iter(warehouses), None)
if WAREHOUSE_ID and not wh:
    record("warehouse", f"SQL warehouse {WAREHOUSE_ID}", "ERROR", "no warehouse with this id - fix the warehouse_id widget")
elif not wh:
    record("warehouse", "SQL warehouse", "ACTION", "no warehouse found - create one (Small, serverless)")
else:
    record("warehouse", f"{wh.name} ({wh.id})", "OK",
           f"{'serverless' if wh.enable_serverless_compute else 'classic/pro'}, state {wh.state.value if wh.state else '?'}")
WAREHOUSE_ID = wh.id if wh else None

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · UC Semantics: governed tags and the Manufacturing domain
# MAGIC
# MAGIC A **domain** (Discover → Domains) *is* a governed tag: an asset belongs to the domain when it carries
# MAGIC the tag (schema tags are inherited by tables). Rules verified against the Domains API (Beta):
# MAGIC
# MAGIC 1. create the **governed tag** first (tag policy **without values**),
# MAGIC 2. create the domain with `tag_key` = that tag (`POST /api/2.0/domains`, created as draft),
# MAGIC 3. a **subdomain** needs its own governed tag named `<domain tag>/<Subdomain>` and `parent_domain_id`,
# MAGIC 4. **publish** with `PATCH /api/2.0/domains/<id>?update_mask=draft` (`draft = false`).
# MAGIC
# MAGIC Names, subtitles and descriptions come from `bootcamp/context/domains/manufacturing/**/_domain.md` and `_subdomain.md`
# MAGIC front matter; the subdomains and their order from this sample's `02_model_tags/manufacturing.json`. Participants later
# MAGIC apply the value-less tags in notebook 05: `ALTER SCHEMA <catalog>.manufacturing SET TAGS ('Manufacturing')`.

# COMMAND ----------


def title_case(snake: str) -> str:
    return " ".join(p.capitalize() for p in snake.split("_"))


ICON, COLOR = {"Consumer": ("ADDRESS_BOOK", "#1565C0"), "Finance": ("COINS", "#2E7D32"),
               "Manufacturing": ("SPEEDOMETER", "#EF6C00")}.get(DOMAIN, ("PACKAGE", "#455A64"))

# The industry model's domain description and subdomains (in model order), from this sample's 02_model_tags/.
doc = json.load(open(f"{BUNDLE_ROOT}/02_model_tags/{SAMPLE}.json", encoding="utf-8"))
SUBDOMAINS = []
for t in doc["tables"].values():
    sd = t["table_tags"].get("dbx_subdomain")
    if sd and sd not in SUBDOMAINS:
        SUBDOMAINS.append(sd)

fm = front_matter(f"{CONTEXT_DIR}/_domain.md")
PLAN = [(ROOT_KEY, None, fm.get("subtitle", f"Fjällmark {DOMAIN}"),       # (tag_key, parent, subtitle, description)
         fm.get("description", doc.get("schema_comment") or f"{DOMAIN} domain of Fjällmark Consumer Goods"))]
if CREATE_SUBDOMAINS:
    for sub in SUBDOMAINS:
        sfm = front_matter(f"{CONTEXT_DIR}/{sub}/_subdomain.md")
        sub_title = sfm.get("subdomain", title_case(sub))
        PLAN.append((f"{ROOT_KEY}/{sub_title}", ROOT_KEY, f"{DOMAIN} - {sub_title}",
                     sfm.get("description", f"Subdomain {sub_title} of {DOMAIN}")))
for p in PLAN:
    print(("    " if p[1] else "") + p[0])

# COMMAND ----------


def origin(obj: dict) -> str:
    return "created by this notebook" if MARKER in (obj.get("description") or "") else "reused - teardown keeps it"


tag_policies = {t["tag_key"]: t for t in list_all("/api/2.1/tag-policies", "tag_policies")}
domains = {d["tag_key"]: d for d in list_all("/api/2.0/domains", "domains")}

for key, parent, subtitle, description in PLAN:
    # 1) governed tag (tag policy without values)
    if key in tag_policies:
        record("tags", f"governed tag '{key}'", "OK", f"exists ({origin(tag_policies[key])})")
    else:
        created = act("tags", f"create governed tag '{key}'",
                      lambda k=key, d=description: api("POST", "/api/2.1/tag-policies",
                                                       body={"tag_key": k, "description": f"{d[:170]} {MARKER}"}))
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
                "icon": {"name": ICON, "color": COLOR}, **({"parent_domain_id": parent_id} if parent_id else {})}
        created = act("domains", f"create {'subdomain' if parent else 'domain'} '{key}'",
                      lambda b=body: api("POST", "/api/2.0/domains", body=b))
        if created:
            domains[key] = created
            if (created.get("icon") or {}).get("name") != ICON:
                record("domains", f"icon {ICON} for '{key}'", "WARN", "icon name not accepted - edit it in Discover")
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
# MAGIC ## 5 · Let participants ASSIGN the domain tags
# MAGIC
# MAGIC Applying a governed tag needs **two** permissions: `APPLY TAG` on the object (participants own their
# MAGIC catalog, so they have it) **and** `ASSIGN` on the governed tag. Governed-tag permissions are managed with
# MAGIC the **Account Access Control Proxy** API (UI: Catalog → Govern → Governed tags → *tag* → Permissions):
# MAGIC resource `accounts/<account_id>/tagPolicies/<tag_policy_id>`, rule set `.../ruleSets/default`, role
# MAGIC `roles/tagPolicy.assigner` (= ASSIGN). The group itself is not created here.

# COMMAND ----------

ASSIGN_STATE = {}   # tag_key -> "yes" / "no" / reason, shown in step 6
principal = f"groups/{PARTICIPANTS_GROUP}"
group = find_group(PARTICIPANTS_GROUP) if PARTICIPANTS_GROUP else None
if not group:
    record("tag-perms", f"group {PARTICIPANTS_GROUP or '(blank)'}", "ACTION",
           "group not found - create it (or run the bootcamp instructor notebook), then re-run this notebook")
for key, *_ in PLAN:
    policy = tag_policies.get(key)
    if not group or not policy or not account_id:
        ASSIGN_STATE[key] = "no group" if not group else ("no tag yet" if not policy else "no account id")
        if group and not policy:
            record("tag-perms", f"ASSIGN on '{key}' for {PARTICIPANTS_GROUP}", "DRY-RUN" if DRY_RUN else "WARN",
                   "governed tag does not exist yet")
        continue
    name = f"accounts/{account_id}/tagPolicies/{policy['id']}/ruleSets/default"
    rule_set, err = api_try("GET", "/api/2.0/preview/accounts/access-control/rule-sets", query={"name": name, "etag": ""})
    if not rule_set:
        ASSIGN_STATE[key] = "unknown"
        record("tag-perms", f"read permissions of '{key}'", "ERROR", err)
        continue
    rules = rule_set.get("grant_rules", [])
    if any(r.get("role") == "roles/tagPolicy.assigner" and principal in r.get("principals", []) for r in rules):
        ASSIGN_STATE[key] = "yes"
        record("tag-perms", f"ASSIGN on '{key}' for {PARTICIPANTS_GROUP}", "OK", "already granted")
        continue
    new_rules = [dict(r) for r in rules]
    assigner = next((r for r in new_rules if r.get("role") == "roles/tagPolicy.assigner"), None)
    if assigner:
        assigner["principals"] = sorted(set(assigner.get("principals", [])) | {principal})
    else:
        new_rules.append({"role": "roles/tagPolicy.assigner", "principals": [principal]})
    done = act("tag-perms", f"grant ASSIGN on '{key}' to {PARTICIPANTS_GROUP}",
               lambda n=name, e=rule_set.get("etag"), r=new_rules: api(
                   "PUT", "/api/2.0/preview/accounts/access-control/rule-sets",
                   body={"name": n, "rule_set": {"name": n, "etag": e, "grant_rules": r}}),
               grant=True)
    ASSIGN_STATE[key] = "yes" if done else "no"

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · All tags of the Manufacturing domain
# MAGIC
# MAGIC **6a - definitions** (APIs): every governed tag of the domain, its domain or subdomain, and whether the
# MAGIC participants may assign it. **6b - usage** (SQL on the warehouse of step 3.3): where the tags are applied,
# MAGIC from `system.information_schema.schema_tags` and `table_tags`. Before the participants run notebook 05 the
# MAGIC usage list is empty. It shows only the catalogs **you** can see: participants own their catalogs, so ask for
# MAGIC `USE CATALOG` + `BROWSE` on them if you want to follow their progress here.

# COMMAND ----------

tag_policies = {t["tag_key"]: t for t in list_all("/api/2.1/tag-policies", "tag_policies")}
domains = {d["tag_key"]: d for d in list_all("/api/2.0/domains", "domains")}
rows = []
for key, parent, *_ in PLAN:
    t, d = tag_policies.get(key), domains.get(key)
    rows.append([key, "subdomain" if parent else "domain", parent or "",
                 "yes" if t else "missing",
                 "missing" if not d else ("draft" if d.get("effective_draft", d.get("draft")) else "published"),
                 origin(t or d) if (t or d) else "-", ASSIGN_STATE.get(key, "-")])
display(spark.createDataFrame(rows, "tag_key string, kind string, parent string, governed_tag string, "
                                    "domain_state string, origin string, participants_assign string"))
missing = [r[0] for r in rows if r[3] == "missing" or r[4] == "missing"]
record("tags", f"{len(rows) - len(missing)} of {len(rows)} domain tags exist with their domain",
       "OK" if not missing else ("DRY-RUN" if DRY_RUN else "ERROR"), ", ".join(missing))

# COMMAND ----------


def run_sql(statement: str, parameters: list) -> tuple:
    """Run one statement on the SQL warehouse (Statement Execution API); returns (column names, rows)."""
    resp = api("POST", "/api/2.0/sql/statements", body={
        "warehouse_id": WAREHOUSE_ID, "statement": statement, "parameters": parameters,
        "wait_timeout": "30s", "on_wait_timeout": "CONTINUE", "disposition": "INLINE", "format": "JSON_ARRAY"})
    deadline = time.time() + 600
    while resp["status"]["state"] in ("PENDING", "RUNNING"):   # a stopped warehouse starts first
        if time.time() > deadline:
            raise TimeoutError(f"statement {resp['statement_id']} still {resp['status']['state']} after 10 minutes")
        time.sleep(5)
        resp = api("GET", f"/api/2.0/sql/statements/{resp['statement_id']}")
    if resp["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(f"{resp['status']['state']}: {(resp['status'].get('error') or {}).get('message', '')}")
    columns = [c["name"] for c in resp["manifest"]["schema"]["columns"]]
    result = resp.get("result") or {}
    data = list(result.get("data_array") or [])
    while result.get("next_chunk_internal_link"):
        result = api("GET", result["next_chunk_internal_link"])
        data += result.get("data_array") or []
    return columns, data


TAG_USAGE_SQL = """
SELECT 'schema' AS level, catalog_name, schema_name, CAST(NULL AS STRING) AS table_name, tag_name
FROM system.information_schema.schema_tags
WHERE tag_name = :root OR startswith(tag_name, concat(:root, '/'))
UNION ALL
SELECT 'table', catalog_name, schema_name, table_name, tag_name
FROM system.information_schema.table_tags
WHERE tag_name = :root OR startswith(tag_name, concat(:root, '/'))
ORDER BY catalog_name, level, schema_name, table_name
"""
if not WAREHOUSE_ID:
    record("usage", "where the domain tags are applied", "SKIP", "no SQL warehouse (step 3.3)")
else:
    try:
        columns, data = run_sql(TAG_USAGE_SQL, [{"name": "root", "value": ROOT_KEY, "type": "STRING"}])
        if data:
            display(spark.createDataFrame(data, ", ".join(f"{c} string" for c in columns)))
        catalogs = sorted({r[1] for r in data})
        record("usage", f"domain tags applied on {len(data)} schema(s) / table(s) in {len(catalogs)} catalog(s)", "OK",
               ", ".join(catalogs) or "none yet - participants apply them with notebook 05")
    except Exception as e:
        record("usage", f"tag query on warehouse {WAREHOUSE_ID}", "ERROR", str(e).splitlines()[0][:300])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Summary

# COMMAND ----------

summary = spark.createDataFrame([list(c) for c in CHECKLIST], "area string, item string, status string, detail string")
display(summary)
counts = {}
for c in CHECKLIST:
    counts[c[2]] = counts.get(c[2], 0) + 1
print("  ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
if DRY_RUN:
    print("\nDry run - nothing was changed. Review the DRY-RUN lines, then set dry_run = false and run again.")
print("\nAfter the event: run again with mode = teardown_domain and confirm_teardown = teardown_domain.")

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"sample": SAMPLE, "mode": MODE, "dry_run": DRY_RUN, "warehouse_id": WAREHOUSE_ID,
                                  "counts": counts,
                                  "checklist": [dict(zip(("area", "item", "status", "detail"), c)) for c in CHECKLIST]}))
