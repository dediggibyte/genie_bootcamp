# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 00 · Instructor setup - Finance sample (admins only - run once before the event)
# MAGIC
# MAGIC Prepares the event workspace for the **Finance sample** (`bootcamp_domain/finance/`). It does not copy the
# MAGIC bootcamp's instructor notebook: it **runs** [`bootcamp/instructor/00_instructor_setup.py`](../../../bootcamp/instructor/00_instructor_setup.py)
# MAGIC with the values of this sample, so both stay one tested notebook. Participants do **not** run this notebook.
# MAGIC
# MAGIC | widget | Finance sample | bootcamp default |
# MAGIC |---|---|---|
# MAGIC | `catalog_prefix` | `cpg_finance_` (the sample's catalogs are `cpg_finance_<short name>`) | `cpg_` |
# MAGIC | `domain_names` | `Finance` (one domain and its subdomains) | `Consumer,Finance,Manufacturing` |
# MAGIC | `lakebase_project` | `fjallmark-finance-sample` (notebook 06 of the sample uses it) | `fjallmark-genie-bootcamp` |
# MAGIC | `dry_run` | **`false`**: Run all makes the changes | `true` |
# MAGIC
# MAGIC Every other widget means exactly what it means in the bootcamp notebook (groups, warehouse, catalog strategy,
# MAGIC GitHub repository, ...); see [`INSTRUCTOR.md`](../INSTRUCTOR.md).
# MAGIC
# MAGIC **Teardown is guarded.** With `mode = teardown_...` the run stays a dry run until `confirm_teardown` equals
# MAGIC the mode name, even though `dry_run = false`. Read section 7 of `INSTRUCTOR.md` first: domains, governed tags and
# MAGIC groups are shared with the bootcamp and the other samples.
# MAGIC
# MAGIC ▶ **How to run:** attach to **Serverless**, fill in `participants` (and `instructors`), **Run all**. The table at
# MAGIC the end is the bootcamp notebook's checklist; its full output is in the linked run.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Parameters

# COMMAND ----------

import json
import os

SAMPLE = "finance"
TITLE = "Finance"
MODES = ["setup", "teardown_domains_and_tags", "teardown_everything"]

dbutils.widgets.dropdown("mode", "setup", MODES, "00 Mode")
dbutils.widgets.dropdown("dry_run", "false", ["true", "false"], "01 Dry run")
dbutils.widgets.text("confirm_teardown", "", "01b Teardown: type the mode name to confirm")
dbutils.widgets.dropdown("apply_grants", "true", ["true", "false"], "02 Apply permission changes")
dbutils.widgets.text("participants", "", "03 Participant e-mails")
dbutils.widgets.text("instructors", "", "04 Instructor e-mails")
dbutils.widgets.text("participants_group", "cpg_bootcamp_participants", "05 Participants group")
dbutils.widgets.text("admins_group", "cpg_bootcamp_admins", "06 Admins group")
dbutils.widgets.text("warehouse_id", "", "07 SQL warehouse id (blank = auto)")
dbutils.widgets.dropdown("catalog_strategy", "precreate", ["precreate", "grant_create_catalog", "none"], "08 Catalog strategy")
dbutils.widgets.text("catalog_prefix", f"cpg_{SAMPLE}_", "09 Catalog prefix")
dbutils.widgets.text("managed_location", "", "10 Managed location for new catalogs")
dbutils.widgets.text("domain_names", TITLE, "11 Domains")
dbutils.widgets.text("tag_prefix", "", "12 Tag prefix (zz_test_ when testing)")
dbutils.widgets.dropdown("create_subdomains", "true", ["true", "false"], "13 Create subdomains")
dbutils.widgets.dropdown("publish_domains", "true", ["true", "false"], "14 Publish domains")
dbutils.widgets.text("github_repo", "dediggibyte/genie_bootcamp", "15 GitHub repository")
dbutils.widgets.dropdown("create_groups", "true", ["true", "false"], "16 Create missing account groups")
dbutils.widgets.text("lakebase_project", f"fjallmark-{SAMPLE}-sample", "17 Lakebase project (router app)")

# The widgets of the bootcamp notebook, passed through unchanged (everything except confirm_teardown).
PASS_THROUGH = ["mode", "dry_run", "apply_grants", "participants", "instructors", "participants_group",
                "admins_group", "warehouse_id", "catalog_strategy", "catalog_prefix", "managed_location",
                "domain_names", "tag_prefix", "create_subdomains", "publish_domains", "github_repo",
                "create_groups", "lakebase_project"]
args = {k: dbutils.widgets.get(k).strip() for k in PASS_THROUGH}

MODE = args["mode"]
if MODE != "setup" and args["dry_run"] == "false" and dbutils.widgets.get("confirm_teardown").strip() != MODE:
    args["dry_run"] = "true"
    print(f"Teardown guard: confirm_teardown is not {MODE!r}, so this run is a DRY RUN (nothing is deleted).\n"
          f"Review the result, then type {MODE} into confirm_teardown and run again.\n")
if not args["catalog_prefix"].startswith(f"cpg_{SAMPLE}_"):
    print(f"⚠️ catalog_prefix {args['catalog_prefix']!r} differs from cpg_{SAMPLE}_: the sample's notebooks default to "
          f"cpg_{SAMPLE}_<short name>, so participants must then type their catalog into every catalog widget.")

for k in PASS_THROUGH:
    print(f"  {k:20s} = {args[k]!r}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Run the bootcamp instructor notebook
# MAGIC
# MAGIC The notebook is found next to this sample in the same Git folder: `<repo>/bootcamp/instructor/00_instructor_setup`.
# MAGIC It runs as a child run of this notebook; open the link it prints (or the cell's *Notebook job* link) for its
# MAGIC full, section-by-section output.

# COMMAND ----------

def bundle_root() -> str:
    """The folder holding databricks.yml above this notebook (= bootcamp_domain/<sample> in the Git folder)."""
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


BUNDLE_ROOT = bundle_root()                        # <repo>/bootcamp_domain/<sample>
REPO_ROOT = os.path.dirname(os.path.dirname(BUNDLE_ROOT))
SETUP = f"{REPO_ROOT}/bootcamp/instructor/00_instructor_setup"
if not os.path.isfile(SETUP + ".py") and not os.path.exists(SETUP):
    raise FileNotFoundError(f"{SETUP} not found - the whole repository must be in the Git folder.")
SETUP_NOTEBOOK = SETUP.removeprefix("/Workspace")  # dbutils.notebook.run takes the workspace path
print(f"Running {SETUP_NOTEBOOK} (mode = {MODE}, dry_run = {args['dry_run']}) ...")

result = json.loads(dbutils.notebook.run(SETUP_NOTEBOOK, 3600, args))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Summary

# COMMAND ----------

rows = [[c["area"], c["item"], c["status"], c["detail"]] for c in result.get("checklist", [])]
if rows:
    display(spark.createDataFrame(rows, "area string, item string, status string, detail string"))
print("  ".join(f"{k}: {v}" for k, v in sorted(result.get("counts", {}).items())))
if result.get("dry_run"):
    print("\nDry run - nothing was changed. Review the DRY-RUN lines, then run again"
          + (" with confirm_teardown set." if MODE != "setup" else " with dry_run = false."))
elif MODE == "setup":
    print(f"\nNext: participants open bootcamp_domain/{SAMPLE}/README.md and start with notebook 01.")
dbutils.notebook.exit(json.dumps({"sample": SAMPLE, **result}))
