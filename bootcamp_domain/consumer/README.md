# Genie, Governed: Consumer sample

A standalone version of the [bootcamp lab](../../bootcamp/README.md) for **e-commerce, CRM and loyalty teams**: one catalog, one
governed lakehouse, **one Genie Agent** (the *Fjällmark Consumer Analyst*), the business context of the Consumer domain. The company is the fictional Fjällmark Consumer Goods AB; all data is synthetic.

* **The data:** the `consumer` domain of the Databricks *Lakehouse Industry Data Model, Consumer Goods v2 (MVM)*:
  the webshop (direct-to-consumer orders in EUR, SEK, NOK and DKK), shoppers and households, the *Fjällmark Friends* loyalty programme, subscriptions and GDPR consent plus four **finance reference tables** (`company_code`, `profit_center`, `journal_entry`, `journal_entry_line`) that the curated `dtc_sales_metrics` and the company-code row filter need.
  16 gold tables (12 consumer, 4 finance), 42 foreign keys, 8 industry metric views plus the curated `dtc_sales_metrics`. Data runs from January 2024 to September 2026.
* **What you build:** your catalog `cpg_consumer_<short name>`, the bronze/silver/gold pipeline, row filters and
  column masks for the Consumer domain, the Consumer Analyst with 8 benchmarks, domain tags and Pages.

> **Not yet run on a workspace.** This sample is built from the tested bootcamp code, but it has not been
> deployed end to end yet: no run times are given, and the first run may surface problems the bootcamp never had.
> Overview of all samples: [`../README.md`](../README.md). Running it as a workshop: [`00_INSTRUCTOR.md`](00_INSTRUCTOR.md).

---

## Contents

* [Prerequisites](#prerequisites)
* [Architecture](#architecture)
* [Step 1: Set up your catalog](#step-1-set-up-your-catalog)
* [Step 2: Deploy and run the bundle](#step-2-deploy-and-run-the-bundle)
* [Step 3: Governance](#step-3-governance)
* [Step 4: The Genie Agent](#step-4-the-genie-agent)
* [Step 5: Business context](#step-5-business-context)
* [Troubleshooting](#troubleshooting)
* [Cleanup](#cleanup)
* [What is in this folder](#what-is-in-this-folder)

---

## Prerequisites

| you need | why |
|---|---|
| the repository as a **Git folder** in your workspace (bootcamp README, step 0) | the notebooks read the CSV files from `bootcamp/data/` in the same Git folder |
| **Serverless** compute for notebooks, jobs and pipelines | every notebook, the pipeline and the job run on serverless |
| **CAN USE** on a SQL warehouse | the Genie Agent runs its SQL there |
| your own catalog `cpg_consumer_<short name>`, or the right to create it | your sandbox |
| the governed tag (domain) **Consumer** and `ASSIGN` on it | step 5 only; the instructor's [`00_instructor_setup.py`](01_notebooks/00_instructor_setup.py) creates it |
| a GitHub account | step 5: the GitHub MCP signs in with *your* account |

Your **short user name** is the part of your login before `@`, in lower case, with every character that is not a
letter or digit replaced by `_`: `jane.doe@example.com` becomes `jane_doe`, and the catalog is `cpg_consumer_jane_doe`.
Every notebook and the bundle compute it the same way.

---

## Architecture

```mermaid
flowchart LR
    CSV["bootcamp/data/<br/>CSV files of this sample"] -->|"notebook 01"| VOL["landing.raw_files volume"]
    VOL -->|"job cpg_consumer_job"| BR["bronze"] --> SI["silver"] --> GO["gold: consumer and finance (reference)<br/>16 tables, 42 foreign keys"]
    GO --> MV["metric views"]
    GOV["notebook 03<br/>row filters, column masks"] -.-> GO
    GO --> AG["Fjällmark Consumer Analyst<br/>notebook 04"]
    MV --> AG
    CTX["bootcamp/context/<br/>consumer glossary"] --> PAG["domain tags, Pages, GitHub MCP<br/>notebook 05"]
    PAG --> AG
```

| layer | built by | where it lives |
|---|---|---|
| landing | [`01_notebooks/01_setup_catalog.py`](01_notebooks/01_setup_catalog.py) | `/Volumes/<catalog>/landing/raw_files/<domain>/<table>/<table>.csv` |
| bronze, silver, gold | pipeline `cpg_consumer_pipeline` ([`02_pipeline/`](02_pipeline/)) | schemas `bronze`, `silver`, `consumer` and `finance` (reference) |
| metric views, model tags | job tasks [`02a`](01_notebooks/job_tasks/02a_create_metric_views.py), [`02b`](01_notebooks/job_tasks/02b_apply_model_tags.py) | in the gold schema; `dbx_*` tags |
| governance | [`01_notebooks/03_governance.py`](01_notebooks/03_governance.py) | functions and mapping tables in schema `governance`, policies on gold |
| Genie Agent | [`01_notebooks/04_genie_agent.py`](01_notebooks/04_genie_agent.py) | your workspace home folder |
| context | [`01_notebooks/05_business_context.py`](01_notebooks/05_business_context.py) + UI | domain tags, Pages, GitHub MCP source |

---

## Step 1: Set up your catalog

Open [`01_notebooks/01_setup_catalog.py`](01_notebooks/01_setup_catalog.py) **in your Git folder**, attach **Serverless** and
click **Run all**.

| widget | default | meaning |
|---|---|---|
| `catalog` | blank = `cpg_consumer_<your short user name>` | the catalog for everything in this sample |
| `managed_location` | blank | storage path for a *new* catalog, only if your metastore needs one |
| `overwrite` | `false` | repairs only |

It creates the catalog (or reuses it), the schemas `landing`, `bronze`, `silver`, `consumer` and `finance` and
`governance`, the volume `landing.raw_files`, and copies the sample's 16 CSV files (77,175 rows) from
`bootcamp/data/` into the volume. A volume file that differs from the Git folder is kept and reported as `WARN`.

🔁 A second *Run all* copies nothing.

---

## Step 2: Deploy and run the bundle

1. In your Git folder, open `bootcamp_domain/consumer/databricks.yml`.
2. Click the **deployments** icon (the rocket), choose the target **`dev`** and click **Deploy**.
3. In **Bundle resources**, run the job **`cpg_consumer_job`**.

CLI alternative (Web Terminal or laptop), from `bootcamp_domain/consumer/`:

```bash
databricks bundle deploy -t dev        # add --var catalog=<name> if you used another catalog in step 1
databricks bundle run cpg_consumer_job -t dev
```

The job runs `pipeline` (bronze, silver, gold), then `metric_views` and `model_tags` in parallel, then
`validate`. It is set to **performance optimized** serverless, so tasks start in seconds instead of minutes.

**The first run of a fresh catalog** loads all data, and the pipeline update may then end *"FAILED
unexpectedly"* while it registers the 42 foreign keys: Lakeflow registers the keys of brand-new tables only for
small sets. The automatic retry reads no files and registers the keys; the job stays green. **Never click
*Full refresh*.** See the bootcamp's [`02_pipeline/README.md`](../../bootcamp/pipeline/README.md) for the evidence.

---

## Step 3: Governance

Everyone who can read your gold tables sees the orders of **every** market and every shopper's name, e-mail, phone number and birth date. You change that once, in Unity Catalog, and every consumer inherits it: SQL, metric views and the
Genie Agent.

Open [`01_notebooks/03_governance.py`](01_notebooks/03_governance.py), keep the defaults and click **Run all**.

| widget | default | meaning |
|---|---|---|
| `catalog` | blank = `cpg_consumer_<short name>` | your catalog |
| `user_email` | your login | whose access you configure |
| `company_code` | `SE01` | the company codes you may see: `SE01`, `SE01,NO01` or `ALL` |
| `pii_access` | `false` | `true` = you may read shopper PII in clear text |
| `buddy_email` | blank | optional: a colleague who tests as a different user |
| `advanced_abac` | `false` | optional: tag-driven masking with `CREATE POLICY` |
| `ask_genie` | `false` | `true` = also ask your Genie Agent a governed question (after step 4) |
| `rollback` | `false` | **leave it `false`**, or your policies are removed again |

| policy | on | rule |
|---|---|---|
| row filter | `consumer.dtc_order` | only the company codes mapped to you in `governance.user_company_access` (`ALL` = every market) |
| row filter | `consumer.dtc_order_line` | follows its order: a line is visible when its order is (lookup on the ungoverned silver orders) |
| column masks | six `consumer.shopper` columns: `given_name`, `family_name`, `display_name`, `primary_email`, `primary_phone`, `birth_date` | masked unless you are in `governance.pii_readers`; the e-mail keeps its domain, the birth date becomes 1 January |

The policies are attached with `ALTER MATERIALIZED VIEW ... SET ROW FILTER / SET MASK`, because the gold tables
are materialized views owned by the pipeline. *Who may see what* is data in the `governance` mapping tables, not
code.

**Personas.** In the personas step you *become* each one by copying its mapping to your e-mail; the next query
shows the effect, with no pipeline run.

| persona | company codes | PII |
|---|---|---|
| Anna Svensson, sales analyst Sweden | SE01 | no |
| Head of e-commerce, all markets | ALL | no |
| CRM manager Nordics | SE01, NO01, DK01 | yes |

**Try to break it:** copy a table with `CREATE TABLE ... AS SELECT`, query silver instead of gold, filter on a
hidden value, and let a policy read a governed table. Each attempt shows a lesson the notebook explains.

**Expected result:** all checks PASS. 🔁 Re-running reports `unchanged`.

> Members of the account group `cpg_bootcamp_admins` bypass the policies. Test as a non-admin.

---

## Step 4: The Genie Agent

Open [`01_notebooks/04_genie_agent.py`](01_notebooks/04_genie_agent.py) and click **Run all**. It creates the
**Fjällmark Consumer Analyst (\<catalog\>)** in your home folder from the template
[`04_genie/fjallmark_consumer_analyst.json`](04_genie/fjallmark_consumer_analyst.json) (the bootcamp's agent, unchanged), asks a
test question through the Conversation API and runs the 8 benchmarks.

| widget | default | meaning |
|---|---|---|
| `catalog` | blank | your catalog |
| `warehouse` | blank = the first serverless warehouse you can use | the agent's SQL warehouse |
| `ask_test_questions` | `true` | ask the test questions |
| `run_benchmarks` | `true` | run the benchmarks |
| `force_update` | `false` | `true` overwrites your UI edits with the template |

**One agent of three.** The template's instructions know that the bootcamp has two more analysts. Questions that
belong to another domain are declined by design in this sample: that is the agent staying in its lane.

**Your answers are governed.** Genie runs every query as the person who asks, so with the step 3 defaults some
benchmarks return only your rows. The expected values in [`bootcamp/genie/README.md`](../../bootcamp/genie/README.md)
are for a user who sees everything.

Then test, benchmark and improve the agent in the UI exactly as in the bootcamp (step 4b).

---

## Step 5: Business context

The glossary of the Consumer domain lives in [`bootcamp/context/domains/consumer/`](../../bootcamp/context/domains/consumer/): one
Markdown page per business term.

1. **Tags (notebook).** [`01_notebooks/05_business_context.py`](01_notebooks/05_business_context.py) tags the
   `consumer` schema with the domain **Consumer**, every table and metric view with its subdomain, and your Genie Agent.
   It needs the governed tag **Consumer**: the instructor creates it with
   [`00_instructor_setup.py`](01_notebooks/00_instructor_setup.py) ([`00_INSTRUCTOR.md`](00_INSTRUCTOR.md)), or an
   admin creates it under **Discover** > **Domains**. Without it, the notebook skips the tags and carries
   on. `tag_reference_tables = true` also tags the finance reference tables (when the domain *Finance* exists).
2. **Pages (UI).** There is no API that creates Pages, so the notebook prints a **Bulk import prompt** and a
   checklist of the expected pages. Open **Discover** > **Pages** > **Create page**, open the Genie Code pane,
   choose **Bulk import pages**, attach the two workspace paths the notebook prints and paste the prompt.
3. **GitHub MCP (UI).** On the agent's **Sources** tab, add `system.ai.github`, point it at
   `bootcamp/context/domains/consumer/pages/`, turn on **Agent mode** and ask about *Active Shopper*.

---

## Troubleshooting

| symptom | cause and fix |
|---|---|
| Notebook 01: "databricks.yml not found" or `bootcamp/data` missing | Open the notebook from the Git folder, with the whole repository cloned. |
| Notebook 01: the catalog cannot be created | Create it in **Catalog** > **+** > **Create a catalog** (name `cpg_consumer_<short name>`), or set `managed_location`. |
| The pipeline shows "FAILED unexpectedly" on the first run | Expected (step 2): the retry registers the keys. Never use *Full refresh*. |
| `validate` fails on row counts or foreign keys | Run the job again; it loads nothing twice. |
| Notebook 03 or 04: tables missing | The job has not finished. Wait until `cpg_consumer_job` is green. |
| You still see everything after notebook 03 | You are in `cpg_bootcamp_admins`, you mapped yourself to `ALL`, or `rollback = true`. |
| Notebook 05: governed tags missing | The domain **Consumer** does not exist yet (step 5). Pages and MCP still work. |

---

## Cleanup

1. Run [`01_notebooks/99_cleanup.py`](01_notebooks/99_cleanup.py) once **without** confirmation: it lists what it would
   delete (your Genie Agent, the policies and your catalog).
2. Type your catalog name into `confirm` and **Run all** again.
3. Delete the job and the pipeline in **Jobs & Pipelines**, or run `databricks bundle destroy -t dev` from
   `bootcamp_domain/consumer/`.

Account-level objects (the domain, governed tags, published Pages) are never touched.

---

## What is in this folder

| path | what | written by |
|---|---|---|
| [`00_instructor_setup.py`](01_notebooks/00_instructor_setup.py), [`00_INSTRUCTOR.md`](00_INSTRUCTOR.md) | admins, once per workshop: the domain's governed tags, domain, subdomains and ASSIGN, and a list of all its tags | hand |
| [`01_notebooks/`](01_notebooks/) | step 0 (instructor setup), steps 1 and 3-5, cleanup, and the job tasks (`job_tasks/`) | hand |
| [`01_data/manifest.json`](01_data/manifest.json) | row counts of this sample's tables; the CSV files stay in `bootcamp/data/` | generated |
| [`databricks.yml`](databricks.yml), [`resources/`](resources/) | the bundle: pipeline `cpg_consumer_pipeline`, job `cpg_consumer_job` | hand |
| [`02_pipeline/`](02_pipeline/), [`02_metric_views/`](02_metric_views/), [`02_model_tags/`](02_model_tags/) | bronze, silver and gold SQL, metric views, `dbx_*` tags | [`../tools/build_domain_samples.py`](../tools/build_domain_samples.py) |
| [`04_genie/`](04_genie/) | the Genie Agent template (copy of the bootcamp's) | generated |
| [`LICENSE.md`](LICENSE.md), [`NOTICE.md`](NOTICE.md) | the industry model's license | generated |

The numbers in the folder names follow the lab: `00` instructor setup, `01` notebooks and source data, `02` the pipeline content
the bundle deploys, `04` the Genie Agent template. `databricks.yml` and `resources/` keep their names: the Databricks CLI and the
**Deployments** button look for a file called `databricks.yml`, which includes `resources/*.yml`.

**License.** The tables, columns, keys, tags and industry metric views come from the Databricks *Lakehouse Industry
Data Model, Consumer Goods v2 (MVM)* (© Databricks, Inc.), licensed under the Databricks license; see
[`LICENSE.md`](LICENSE.md) and [`NOTICE.md`](NOTICE.md).
