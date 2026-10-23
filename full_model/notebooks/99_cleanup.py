# Databricks notebook source
# MAGIC %md
# MAGIC # 99 · Clean up the full-model catalog
# MAGIC
# MAGIC Removes what **you** created with the full industry model bundle (`full_model/`) - and nothing else:
# MAGIC
# MAGIC | step | what is removed | how we make sure it is yours |
# MAGIC |---|---|---|
# MAGIC | 3 | Genie Agents you built on this catalog (e.g. with the bootcamp's notebook 04) | title starts with **Fjällmark Business Analyst**, stored in **your** home folder, uses **this** catalog |
# MAGIC | 4 | governance policies: ABAC policies, row filters, column masks | only inside **this** catalog, and you must **own** it |
# MAGIC | 5 | the catalog itself (`DROP CATALOG ... CASCADE`: schemas, tables, metric views, volume, files) | you must **own** the catalog |
# MAGIC
# MAGIC If somebody else owns the catalog (for example an instructor runs this notebook to help a participant),
# MAGIC steps 4 and 5 change **nothing** - the policies stay on the participant's tables.
# MAGIC | 6 | the bundle's job and pipeline | `bundle destroy` - explained at the end (not done by this notebook) |
# MAGIC
# MAGIC Account-level objects (domains, governed tags, groups, Pages) belong to the instructor and are **not**
# MAGIC touched. Draft Pages you created yourself can be deleted from **Discover → Pages**.
# MAGIC
# MAGIC ▶ **How to run:** Run all once **without** confirmation - the notebook only lists what it *would* delete.
# MAGIC Then type your catalog name into the `confirm` widget and run all again.
# MAGIC
# MAGIC **Expected result:** an inventory, then (after confirmation) "deleted" lines and a final check that the
# MAGIC catalog and your agents are gone.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters
# MAGIC
# MAGIC | widget | default | meaning |
# MAGIC |---|---|---|
# MAGIC | `catalog` | blank = `cpg_full_<your short user name>` | the catalog to clean up |
# MAGIC | `confirm` | blank | type the **catalog name** here to actually delete; blank = inventory only (dry run) |
# MAGIC | `delete_genie_agents` | `true` | move your bootcamp Genie Agents on this catalog to the trash |
# MAGIC | `drop_catalog` | `true` | `false` = only remove the governance policies and keep the data |

# COMMAND ----------

import json
import unicodedata

from databricks.sdk import WorkspaceClient

dbutils.widgets.text("catalog", "", "1 Catalog (blank = automatic)")
dbutils.widgets.text("confirm", "", "2 Type the catalog name to confirm")
dbutils.widgets.dropdown("delete_genie_agents", "true", ["true", "false"], "3 Delete my Genie Agents")
dbutils.widgets.dropdown("drop_catalog", "true", ["true", "false"], "4 Drop the catalog")


def bundle_short_name(user_name: str) -> str:
    """Same rule as the bundle's ${workspace.current_user.short_name}."""
    local = user_name.split("@")[0].lower()
    return "".join(c if unicodedata.category(c).startswith("L") or unicodedata.category(c) == "Nd" else "_"
                   for c in local)


w = WorkspaceClient()
me = spark.sql("SELECT current_user()").first()[0]
C = dbutils.widgets.get("catalog").strip() or f"cpg_full_{bundle_short_name(me)}"
CONFIRMED = dbutils.widgets.get("confirm").strip() == C
Q = f"`{C}`"   # the catalog name back-quoted for SQL (names with letters such as å/ä/ö need the quotes)


def qname(full_name: str) -> str:
    """catalog.schema.table -> `catalog`.`schema`.`table`"""
    return ".".join(f"`{part}`" for part in full_name.split("."))
DELETE_AGENTS = dbutils.widgets.get("delete_genie_agents") == "true"
DROP_CATALOG = dbutils.widgets.get("drop_catalog") == "true"
AGENT_TITLE_PREFIX = "Fjällmark Business Analyst"
MY_HOME = f"/Users/{me}"

print(f"You are   : {me}")
print(f"Catalog   : {C}")
print(f"Mode      : {'DELETE (confirmed)' if CONFIRMED else 'DRY RUN - inventory only (type the catalog name into confirm to delete)'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Inventory - what belongs to you?

# COMMAND ----------

# --- the catalog ----------------------------------------------------------------------------------
try:
    cat = w.catalogs.get(C)
    catalog_exists, catalog_owner = True, cat.owner
except Exception:
    catalog_exists, catalog_owner = False, None
i_own_catalog = catalog_exists and (catalog_owner or "").lower() == me.lower()
print(f"Catalog {C}: {'exists, owner ' + str(catalog_owner) if catalog_exists else 'does not exist'}")
if catalog_exists and not i_own_catalog:
    print(f"  You are not the owner of {C} - this notebook will not remove its policies or drop it "
          "(ask the owner / instructor).")

# --- governance policies inside the catalog --------------------------------------------------------
row_filters, column_masks, abac_policies = [], [], []
if catalog_exists:
    row_filters = [(r.table_schema, r.table_name) for r in spark.sql(
        f"SELECT table_schema, table_name FROM {Q}.information_schema.row_filters").collect()]
    column_masks = [(r.table_schema, r.table_name, r.column_name) for r in spark.sql(
        f"SELECT table_schema, table_name, column_name FROM {Q}.information_schema.column_masks").collect()]
    # ABAC policies can sit on the catalog, a schema or a table, and SHOW POLICIES only lists the policies
    # defined on that exact securable -> ask the catalog, every schema and every gold/governance table.
    securables = [("CATALOG", C)]
    securables += [("SCHEMA", f"{C}.{r.schema_name}") for r in spark.sql(
        f"SELECT schema_name FROM {Q}.information_schema.schemata WHERE schema_name <> 'information_schema'").collect()]
    securables += [("TABLE", f"{C}.{r.table_schema}.{r.table_name}") for r in spark.sql(f"""
        SELECT table_schema, table_name FROM {Q}.information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'landing', 'bronze', 'silver')
          AND table_name NOT LIKE '\\_\\_%' AND table_name NOT LIKE 'event_log%'""").collect()]
    seen = set()
    for kind, name in securables:
        try:
            for p in spark.sql(f"SHOW POLICIES ON {kind} {qname(name)}").collect():
                key = (p["on_securable_type"], p["on_securable_fullname"], p["Policy Name"])
                if key not in seen and p["on_securable_fullname"] == name:
                    seen.add(key)
                    abac_policies.append(key)
        except Exception:
            pass  # securable types without policy support
print(f"Row filters : {len(row_filters)}   Column masks: {len(column_masks)}   ABAC policies: {len(abac_policies)}")
for p in abac_policies:
    print(f"  ABAC policy {p[2]} on {p[0]} {p[1]}")

# --- Genie Agents -------------------------------------------------------------------------------------
agents, token = [], None
while True:
    query = {"page_size": 100, **({"page_token": token} if token else {})}
    resp = w.api_client.do("GET", "/api/2.0/genie/spaces", query=query)
    for s in resp.get("spaces", []):
        if not s.get("title", "").startswith(AGENT_TITLE_PREFIX):
            continue
        detail = w.api_client.do("GET", f"/api/2.0/genie/spaces/{s['space_id']}",
                                 query={"include_serialized_space": "true"})
        parent = (detail.get("parent_path") or "").removeprefix("/Workspace")
        mine = parent == MY_HOME or parent.startswith(MY_HOME + "/")
        uses_catalog = f"{C}." in detail.get("serialized_space", "")
        if mine and uses_catalog:
            agents.append({"space_id": s["space_id"], "title": s["title"], "parent_path": parent})
    token = resp.get("next_page_token")
    if not token:
        break
print(f"Genie Agents to trash: {len(agents)}")
for a in agents:
    print(f"  {a['space_id']}  {a['title']}  ({a['parent_path']})")

# --- pipelines writing to the catalog (informational) -----------------------------------------------
my_pipelines = []
for p in w.pipelines.list_pipelines():
    if (p.creator_user_name or "").lower() != me.lower():
        continue
    try:
        spec = w.pipelines.get(p.pipeline_id).spec
        if spec and spec.catalog == C:
            my_pipelines.append((p.pipeline_id, p.name))
    except Exception:
        pass
print(f"Your pipelines that write to {C}: {len(my_pipelines)}")
for pid, name in my_pipelines:
    print(f"  {pid}  {name}")

# COMMAND ----------

if not CONFIRMED:
    dbutils.notebook.exit(json.dumps({"mode": "dry_run", "catalog": C, "catalog_exists": catalog_exists,
                                      "i_own_catalog": i_own_catalog, "agents": len(agents), "row_filters": len(row_filters),
                                      "column_masks": len(column_masks), "abac_policies": len(abac_policies)}))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Trash the Genie Agents
# MAGIC Trashed agents can be restored from the workspace **Trash** for 30 days.

# COMMAND ----------

deleted_agents = []
if DELETE_AGENTS:
    for a in agents:
        w.api_client.do("DELETE", f"/api/2.0/genie/spaces/{a['space_id']}")
        deleted_agents.append(a["space_id"])
        print(f"trashed  {a['space_id']}  {a['title']}")
print(f"{len(deleted_agents)} Genie Agent(s) trashed.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Remove the governance policies
# MAGIC Dropping the catalog removes them anyway; this step matters when you keep the data
# MAGIC (`drop_catalog = false`) and only want the tables back without policies. Only the catalog **owner**
# MAGIC removes policies - anybody else (even an admin) gets a message and nothing changes.

# COMMAND ----------


def alter(schema: str, table: str) -> str:
    kind = spark.sql(f"SELECT table_type FROM {Q}.information_schema.tables WHERE table_schema = :s AND table_name = :t",
                     {"s": schema, "t": table}).first()[0]
    keyword = {"MATERIALIZED_VIEW": "MATERIALIZED VIEW", "STREAMING_TABLE": "STREAMING TABLE"}.get(kind, "TABLE")
    return f"ALTER {keyword} {Q}.`{schema}`.`{table}`"


policies_removed = False
if catalog_exists and not i_own_catalog:
    print(f"Not your catalog: {C} is owned by {catalog_owner}. Policies kept "
          f"({len(abac_policies)} ABAC, {len(row_filters)} row filters, {len(column_masks)} column masks).")
elif catalog_exists:
    for on_type, on_name, policy in abac_policies:
        stmt = f"DROP POLICY `{policy}` ON {on_type} {qname(on_name)}"
        print(stmt + ";")
        spark.sql(stmt)
    for schema, table in row_filters:
        stmt = f"{alter(schema, table)} DROP ROW FILTER"
        print(stmt + ";")
        spark.sql(stmt)
    for schema, table, column in column_masks:
        stmt = f"{alter(schema, table)} ALTER COLUMN `{column}` DROP MASK"
        print(stmt + ";")
        spark.sql(stmt)
    policies_removed = True
    print("Policies removed.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Drop the catalog
# MAGIC `DROP CATALOG ... CASCADE` removes every schema, table, materialized view, metric view, function and the
# MAGIC landing volume (with the CSV files) of your catalog. There is no undo.

# COMMAND ----------

dropped = False
if DROP_CATALOG and catalog_exists:
    if not i_own_catalog:
        print(f"Skipping: {C} is owned by {catalog_owner}, not by you.")
    else:
        stmt = f"DROP CATALOG IF EXISTS {Q} CASCADE"
        print(stmt + ";")
        spark.sql(stmt)
        dropped = True
        print(f"Catalog {C} dropped.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Remove the bundle deployment (job + pipeline)
# MAGIC
# MAGIC The job `cpg_lakehouse_job` and the pipeline `cpg_lakehouse_pipeline` were deployed by the bundle.
# MAGIC Remove them with the bundle itself, so its deployment state stays consistent:
# MAGIC
# MAGIC **Workspace UI** (bundle deployed from the Git folder): open the Git folder, click `full_model/databricks.yml`,
# MAGIC open the **Deployments** pane, select the target you deployed (`full`) and choose **Destroy** (the
# MAGIC wording of the menu entry can differ between releases). Only the bundle's resources are deleted; the
# MAGIC files in your Git folder stay.
# MAGIC
# MAGIC **CLI** (your laptop or the workspace **Web Terminal**), from the `full_model` folder of the repository:
# MAGIC ```bash
# MAGIC databricks bundle destroy -t full --var catalog=<your catalog> --auto-approve
# MAGIC ```
# MAGIC Without a bundle you can also delete the job and the pipeline from **Jobs & Pipelines**: they are named
# MAGIC `[dev <your short name>] cpg_lakehouse_job (<catalog>)` and `... cpg_lakehouse_pipeline ...`.
# MAGIC
# MAGIC Finally, delete the Git folder from your workspace home if you no longer need it.

# COMMAND ----------

left_agents = [a for a in agents if a["space_id"] not in deleted_agents]
catalog_left = spark.sql("SELECT count(*) FROM system.information_schema.catalogs WHERE catalog_name = :c",
                         {"c": C}).first()[0] > 0
print(f"Genie Agents remaining      : {len(left_agents)}")
print(f"Catalog {C} still exists : {catalog_left}")
if my_pipelines:
    print("Pipelines still deployed    : " + ", ".join(n for _, n in my_pipelines) + "  -> run bundle destroy (above)")
dbutils.notebook.exit(json.dumps({"mode": "deleted", "catalog": C, "catalog_owner": catalog_owner,
                                  "catalog_dropped": dropped,
                                  "catalog_still_exists": catalog_left, "agents_trashed": deleted_agents,
                                  "policies_removed": policies_removed,
                                  "policies_found": {"abac": len(abac_policies), "row_filters": len(row_filters),
                                                     "column_masks": len(column_masks)},
                                  "pipelines_left": [pid for pid, _ in my_pipelines]}))
