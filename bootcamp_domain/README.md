# Genie, Governed: domain samples

The hands-on lab in [`../bootcamp/`](../bootcamp/README.md) builds **three** domain Genie Agents and a router in one
catalog. This folder cuts that lab into **three standalone samples, one per business domain**. Each one is a
complete, self-contained copy of the lab for a single team: its own catalog, pipeline, governance, Genie Agent,
business context and router app.

| sample | for whom | gold tables | metric views | Genie Agent | governance key |
|---|---|---|---|---|---|
| [`finance/`](finance/README.md) | finance and controlling | 13 finance | 8 industry + 2 curated | Fjällmark Finance Analyst, 9 benchmarks | company code |
| [`consumer/`](consumer/README.md) | e-commerce, CRM, loyalty | 12 consumer + 4 finance reference | 8 industry + 1 curated | Fjällmark Consumer Analyst, 8 benchmarks | company code + shopper PII |
| [`manufacturing/`](manufacturing/README.md) | plants, operations, production controlling | 11 manufacturing + 3 finance reference | 6 industry + 1 curated | Fjällmark Manufacturing Analyst, 7 benchmarks | plant + production cost |

The company (Fjällmark Consumer Goods AB), the Databricks *Lakehouse Industry Data Model, Consumer Goods v2 (MVM)*
and the synthetic data are the same as in the bootcamp. Read the bootcamp README for the story behind the data.

> **Status: not yet run on a workspace.** The samples are built from the tested bootcamp code and generators,
> but no sample has been deployed end to end yet. The READMEs give no measured run times until one has.

---

## What each sample contains

Every sample folder has the same layout and the same steps as the bootcamp:

| step | file | what it does |
|---|---|---|
| 1 | `notebooks/01_setup_catalog.py` | catalog `cpg_<sample>_<short name>`, schemas, volume; copies the sample's CSV files from `../../bootcamp/data` |
| 2 | `databricks.yml`, `resources/` | bundle `genie_domain_<sample>`: pipeline `cpg_<sample>_pipeline` and job `cpg_<sample>_job` (performance optimized) |
| 2 | `notebooks/job_tasks/02a-02c` | metric views, model tags, validation (tasks of the job) |
| 3 | `notebooks/03_governance.py` | mapping tables, row filters and column masks for this domain, personas, try to break it |
| 4 | `notebooks/04_genie_agent.py` | creates or updates the sample's one Genie Agent, test questions, benchmarks |
| 5 | `notebooks/05_business_context.py` | domain and subdomain tags, Bulk import prompt for the domain's Pages, GitHub MCP |
| 6 | `notebooks/06_router_app.py`, `app/` | router app: the Genie Agent for numbers plus a glossary tool for definitions; memory in Lakebase |
| - | `notebooks/99_cleanup.py` | removes everything the sample created (dry run first) |

### Why a single-domain router?

In the bootcamp, the router chooses between three analysts. A sample has one, so its router combines two
sources instead: the **glossary tool** answers *what a term means* from the domain's business glossary, and the
**Genie Agent** answers *what the number is*. A question such as *"How is DSO defined, and what is SE01's DSO?"*
uses both. A question for another domain is declined with a pointer to the full bootcamp router.

### Reference tables

A domain rarely stands alone. The consumer and manufacturing samples also build a few **finance reference
tables** in a `finance` schema, because their curated metric views and governance need them:

| sample | reference tables | used for |
|---|---|---|
| consumer | `company_code`, `profit_center`, `journal_entry`, `journal_entry_line` | entity names, brands, EUR rates in `dtc_sales_metrics`; company-code row filters |
| manufacturing | `company_code`, `journal_entry`, `journal_entry_line` | EUR rate of each plant currency in `production_performance_metrics` |

Foreign keys into tables a sample does not build are left out of its gold DDL, and each gold file lists what
was omitted.

---

## How to choose and run a sample

1. Add the repository as a **Git folder** (bootcamp README, step 0). The samples read the CSV files from
   `bootcamp/data/` in the same Git folder, so the whole repository must be there.
2. Open `bootcamp_domain/<sample>/README.md` and follow steps 1 to 6.
3. The samples use their own catalogs (`cpg_finance_<short>`, `cpg_consumer_<short>`,
   `cpg_manufacturing_<short>`), so you can run any of them next to each other and next to the bootcamp.

**Workspace prerequisites** are the bootcamp's, with one difference: a sample has no instructor notebook.
Notebook 06 creates the sample's Lakebase project itself when it does not exist (you need the right to create
a Lakebase project), and notebook 05 needs the domain's governed tag. A workspace admin creates the tag with
[`../bootcamp/instructor/00_instructor_setup.py`](../bootcamp/instructor/00_instructor_setup.py)
(`domain_names` = the sample's domain), or in **Discover** > **Domains**.

---

## For maintainers: how the samples are built

The generated parts of every sample come from one script. It reuses the bootcamp generator's own functions, so
a sample's pipeline is exactly the bootcamp pipeline, cut down to the sample's tables. Nothing in `bootcamp/`
or `tools/` is written.

```bash
python3 -I bootcamp_domain/tools/build_domain_samples.py           # write the generated files
python3 -I bootcamp_domain/tools/build_domain_samples.py --check   # exit 1 if one is missing or stale
```

| generated file | source |
|---|---|
| `pipeline/<domain>/01_bronze.sql`, `02_silver.sql`, `03_gold.sql` | the industry model (`tools/model/`), via `tools/generate_lakehouse.py` |
| `metric_views/industry/<domain>.sql`, `model_tags/<domain>.json` | the industry model |
| `metric_views/curated/*.sql` | copies of `bootcamp/metric_views/curated/<domain>_*.sql` |
| `genie/fjallmark_<domain>_analyst.json` | copy of the bootcamp Genie Agent template |
| `data/manifest.json` | subset of `bootcamp/data/manifest.json` (the CSV files themselves are not copied) |
| `app/glossary/` | the domain's rows of `bootcamp/context/glossary.csv` and its pages |
| `LICENSE.md`, `NOTICE.md` | copies of `tools/model/` |

The script stops when a curated metric view or the Genie Agent template reads a table the sample does not
build. Run it, with `--check`, after every change to the bootcamp's generated files, curated views, agent
templates or glossary. The notebooks and the app are written by hand and are not generated.

**Data budget.** The CSV files are not copied: the repository keeps its data under 40 MB, and
`tools/verify_data.py` rejects a table that is stored twice.

**License.** The tables, columns, keys, tags and industry metric views come from the Databricks *Lakehouse
Industry Data Model, Consumer Goods v2 (MVM)* (© Databricks, Inc.), licensed under the Databricks license. Each
sample folder carries [`LICENSE.md`](finance/LICENSE.md) and [`NOTICE.md`](finance/NOTICE.md).
