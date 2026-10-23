# Full industry model (optional, instructor)

The **complete** Databricks *Lakehouse Industry Data Model, Consumer Goods v2 (MVM)* for the fictional company
Fjällmark Consumer Goods AB: **10 domains, 116 gold tables, 733 foreign keys, 79 industry metric views and
6,291 model tags**. All data is synthetic.

The hands-on lab does **not** need this folder: participants work in [`../bootcamp/`](../bootcamp/README.md)
(3 domains, one Genie Agent). Use the full model to show the whole industry model, for instructor demos, or as
the base for further Genie Agents (for example over sales, supply or quality).

| domain | gold tables | CSVs stored in |
|---|---|---|
| consumer, finance, manufacturing | 12 + 13 + 11 = 36 | [`../bootcamp/data/<domain>/`](../bootcamp/data/README.md) (stored once, shared with the bootcamp) |
| distribution, procurement, product, promotion, quality, sales, supply | 80 | [`data/<domain>/`](data/README.md) |

Compared with the bootcamp, the full model adds the product master (brands, categories, 89 SKUs and their
specifications), B2B sales (`sales.trade_account` with customers such as "Alpina Drogerie"), distribution,
procurement, promotion, quality and supply. Its gold layer has **all** model foreign keys except the 23
self-references, including the keys from the bootcamp domains into product and sales.

## Contents

| path | what |
|---|---|
| [`databricks.yml`](databricks.yml), [`resources/`](resources/) | bundle `genie_bootcamp`, target `full` (default): pipeline `cpg_lakehouse_pipeline` (30 SQL files) and job `cpg_lakehouse_job` |
| [`notebooks/01_setup_catalog.py`](notebooks/01_setup_catalog.py) | catalog `cpg_full_<short name>`, schemas (`landing`, `bronze`, `silver`, `governance`, the 10 domain schemas), landing volume; copies all 116 CSVs from `../bootcamp/data` and `data/` |
| [`notebooks/job_tasks/`](notebooks/job_tasks/) | job tasks: 79 industry metric views (`02a`), model tags (`02b`), validation (`02c`) |
| [`notebooks/99_cleanup.py`](notebooks/99_cleanup.py) | drop the full-model catalog (dry run first) |
| [`src/pipeline/<domain>/`](src/pipeline/README.md) | bronze, silver and gold SQL for all 10 domains (generated) |
| [`src/metric_views/industry/`](src/metric_views/industry/), [`src/model_tags/`](src/model_tags/) | the 79 industry metric views and the `dbx_*` tags (generated) |
| [`data/`](data/README.md) | CSVs of the 7 non-bootcamp domains, `manifest.json` (all 116 tables, paths relative to the repository root), data dictionary |

Not included: the bootcamp's 4 curated metric views, governance notebook, Genie Agent template and business
context. They are written for the 3-domain bootcamp and live in [`../bootcamp/`](../bootcamp/README.md).

## Deploy

1. **Set up the catalog.** From the repository's **Git folder**, run
   [`notebooks/01_setup_catalog.py`](notebooks/01_setup_catalog.py) on Serverless. Leave the `catalog` widget blank
   for `cpg_full_<your short name>`, and set `managed_location` if your metastore uses Default Storage (see the
   bootcamp's [INSTRUCTOR.md](../bootcamp/INSTRUCTOR.md), section 1.4). It must run from the Git folder: it reads
   the bootcamp CSVs from the sibling folder `../bootcamp/data`, and a bundle deployment contains no CSV files.
2. **Deploy and run the job:**
   * workspace UI: open `full_model/databricks.yml` > deployments icon > target **`full`** > **Deploy**, then run
     `cpg_lakehouse_job` from the **Bundle resources** pane;
   * CLI, from `full_model/`: `databricks bundle deploy -t full [--var catalog=<name>]`, then
     `databricks bundle run cpg_lakehouse_job -t full`.
3. **Re-runs are no-ops:** setup skips existing files, the pipeline only ingests new files (never use *Full
   refresh*), and metric views and tags are applied only when missing or changed.

The default catalog `cpg_full_<short name>` is separate from the bootcamp's `cpg_<short name>`, so the two
pipelines never compete for the same tables.

**Bundle name and deployment state.** The bundle is called `genie_bootcamp`, like the bootcamp bundle, and keeps
the deployment root `~/.bundle/genie_bootcamp/full/<catalog>` of earlier full-model deployments. A redeploy
therefore updates the pipeline that already owns a catalog's tables instead of creating a competing one. Do not
deploy the *bootcamp* bundle into a catalog that was built with the earlier 4-domain development version: it
would remove that pipeline's product tables.

## Runtime and size

| item | value |
|---|---|
| CSV data | 116 files, 113,516 rows, 38.1 MB of CSV; the two data folders incl. manifests and READMEs: 36.1 MB (bootcamp) + 2.3 MB (full_model) = 38.3 MB of the 40 MB budget |
| `01_setup_catalog`, fresh catalog | 116 files copied in a one-time serverless run (83 s); re-run copies 0 |
| pipeline update, all 116 tables | about 11 minutes per update (688 s for the first update, 649 s for the follow-up that registers the keys), measured on an earlier data generation |
| metric views and tags | 79 views created, 6,291 tags applied; re-runs: 79 unchanged, 0 tags |

**First run of a fresh catalog.** As in the bootcamp, the first pipeline update loads all data and then ends
"FAILED unexpectedly" while registering the keys; a second update (the pipeline's automatic retry, the job
task's retry or the next job run) registers them without reading any file. Never use *Full refresh*. The full model has 733 foreign keys; see
[`src/pipeline/README.md`](src/pipeline/README.md) and the bootcamp's
[`pipeline/README.md`](../bootcamp/pipeline/README.md) for the evidence.

**Validation status (read this before relying on the full model).**

* **Built live, on the pre-restructure layout:** catalog `zz_cpg_test_b1_full` was built by the earlier
  root-level bundle (target `full`, pipeline SQL from an earlier run of the same generator, older data
  generation). It holds 116 gold
  tables, 116 primary keys, 733 foreign keys, 79 metric views and 6,291 model tags (re-checked read-only on
  2026-10-23). Because its CSVs are an older data generation, 02c's row-count check against the current
  `manifest.json` reports differences there.
* **Restructured bundle in this folder: statically validated only.** `python3 -I tools/generate_lakehouse.py
  --check` passes and `databricks bundle validate -t full` passes from a private copy. This folder layout
  (`src/pipeline`, `notebooks/job_tasks/`) has **not** been deployed and run end to end on a fresh catalog with
  the current data; notebooks 01, 02a and 02b ran as one-time runs on copies of a loaded catalog, including
  no-op re-runs. Treat the first deployment as a test, and allow for a first update of about 11 minutes plus
  the key-registering retry.

## Regenerate

```bash
# from the repository root
python3 -I tools/generate_lakehouse.py --check   # pipeline SQL, metric views, tags (bootcamp/ and full_model/)
python3 -I tools/generate_data.py                # CSVs, manifests and data READMEs (deterministic)
python3 -I tools/verify_data.py                  # data checks + storyline KPIs
```

## License

Generated files come from `../tools/model/consumer_goods_v2_mvm.json`, the Databricks *Lakehouse Industry Data
Model, Consumer Goods v2 (MVM)* (© Databricks, Inc.), licensed under the Databricks license. See
[`LICENSE.md`](LICENSE.md) and [`NOTICE.md`](NOTICE.md) in this folder (verbatim copies of `tools/model/`, written
by the generator so that the folder and every bundle deployment carry them). The generated SQL and JSON files are
modified for this bootcamp and say so in their headers or `_notice` keys; the CSV data is documented in
[`data/README.md`](data/README.md).
