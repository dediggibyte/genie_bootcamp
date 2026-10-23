# Lakehouse pipeline (generated)

Every `.sql` file below `bootcamp/pipeline/`, `bootcamp/metric_views/industry/` and every `.json` file in
`bootcamp/model_tags/` is **generated** by [`tools/generate_lakehouse.py`](../../tools/generate_lakehouse.py)
(repository root) from the vendored industry model
[`tools/model/consumer_goods_v2_mvm.json`](../../tools/model/consumer_goods_v2_mvm.json)
(Lakehouse Industry Data Model *Consumer Goods v2 MVM*, © Databricks, Databricks license - see
[`../LICENSE.md`](../LICENSE.md) and [`../NOTICE.md`](../NOTICE.md), copies of `tools/model/`; modified for this
bootcamp).
Do not edit the generated files by hand - change the generator and run it again:

```bash
# from the repository root
python3 -I tools/generate_lakehouse.py           # rewrite all generated files (deterministic)
python3 -I tools/generate_lakehouse.py --check   # CI: exit 1 if anything is stale
```

## Layout

| file | layer | content |
|---|---|---|
| `<domain>/01_bronze.sql` | bronze | one **streaming table** per source table: `read_files` (Auto Loader) on `/Volumes/${catalog}/landing/raw_files/<domain>/<table>/`, all columns `STRING`, plus `_rescued_data`, `_source_file`, `_ingested_at` |
| `<domain>/02_silver.sql` | silver | one **materialized view** per table: typed and cleaned, one row per primary key, data-quality expectations |
| `<domain>/03_gold.sql` | gold | the **exact industry table** as materialized view `<domain>.<table>`: column names/order/types/comments, table comment, `NOT NULL` + `PRIMARY KEY`, foreign keys **between the bootcamp domains** (consumer, finance, manufacturing); keys into other domains (product, sales, ...) are left out and listed above each table |

Domains: `consumer` (12 tables), `finance` (13), `manufacturing` (11) = 36 gold tables. The complete
model (all 10 domains, all foreign keys) is built by `full_model/` at the repository root.

`${catalog}` is substituted by the pipeline from its configuration key `catalog` (set by the bundle).

## Silver cleaning rules (what the raw data needs, see `../data/README.md`)

| raw problem | silver rule |
|---|---|
| stray blanks, empty strings | `NULLIF(trim(x), '')` |
| enum values in the wrong case / with blanks (`' Gold'`, `ACTIVE`) | `CASE lower(trim(x)) WHEN 'gold' THEN 'gold' ...` - mapped to the model's exact value (`value_regex` list) |
| dates as `dd/MM/yyyy` | `COALESCE(try_to_date(x,'yyyy-MM-dd'), try_to_date(x,'dd/MM/yyyy'), TRY_CAST(x AS DATE))` |
| timestamps in different ISO-8601 shapes | `COALESCE(try_to_timestamp(x,'yyyy-MM-dd HH:mm:ss'), TRY_CAST(x AS TIMESTAMP))` |
| booleans as `Y`/`N`, `1`/`0`, `true`/`false` | `CASE WHEN lower(trim(x)) IN ('true','t','yes','y','1') THEN TRUE WHEN ... IN ('false','f','no','n','0') THEN FALSE END` |
| bad numbers | `TRY_CAST(NULLIF(trim(x), '') AS <type>)` (NULL instead of a failed pipeline) |
| exact duplicate rows / older versions of a record | `QUALIFY ROW_NUMBER() OVER (PARTITION BY pk ORDER BY <updated/modified ts> DESC, _ingested_at DESC) = 1` |
| empty primary key | expectation `<pk>_not_null` → **DROP ROW** (the dedup step keeps all NULL-key rows so every one is counted) |
| negative `consumer.dtc_order_line.quantity_ordered` | expectation `quantity_ordered_not_negative` → **DROP ROW** |
| negative amounts / quantities on the focus tables | expectations `<column>_not_negative` → **warn** (counted, rows kept) |

Expectation results: pipeline UI → *Data quality*, or SQL:
`SELECT * FROM event_log(TABLE(<catalog>.silver.consumer_shopper)) WHERE event_type = 'flow_progress'`
(notebook `02c_validate_lakehouse` shows a summary).

## Decisions verified on a live workspace (2026-10-22)

- Gold PK/FK constraints and comments must be declared in the pipeline DDL; they cannot be added later.
- A foreign key can only reference a table that exists when the key is registered: a table of the same
  pipeline, or one owned by another pipeline that has already run. The bootcamp builds only consumer,
  finance and manufacturing, so its gold files declare only the 123 foreign keys between those three
  domains; keys into product, sales and the other domains are listed in a comment above each table (the
  complete set is in `full_model/src/pipeline/`).
- **Self-referencing foreign keys are rejected** by pipelines
  (`TABLE_MATERIALIZATION_CYCLIC_FOREIGN_KEY_DEPENDENCY`) → the 23 self-references of the model are
  omitted (listed in a comment above each table). All other model FKs form no cycle.
- A pipeline orders tables only by the data they read, not by foreign keys. Each gold query therefore
  ends with `WHERE TRUE OR EXISTS (SELECT 1 FROM <FK target table>) ...` - it never filters a row but
  makes the pipeline build the referenced tables (and their primary keys) first.
- **Very first run of a fresh catalog:** the first pipeline update loads everything but ends with
  `FAILED unexpectedly` while registering the keys; the pipeline's automatic retry (cause
  `RETRY_ON_FAILURE`, same job run, job task stays green) reads no files and registers all keys. In the
  measured run (zz_cpg_bc_e2e) every materialized view of the retry was `NO_OP`. Evidence and the options
  that were tested: next section.
- **Governance makes 11 gold tables non-incremental.** The build-order hint (`OR EXISTS (SELECT 1 FROM
  <FK target>)`) reads the referenced *gold* table. Once lab step 3 attaches a column mask to
  `consumer.shopper` (and row filters to `consumer.dtc_order`, `finance.ar_invoice`), the 11 gold tables whose
  hint reads one of them cannot be maintained incrementally (event log: `PLAN_NOT_INCREMENTALIZABLE`, operator
  `SecureViewUnaryNode`) and are recomputed from silver on **every** update while the policies are attached:
  `consumer.address`, `consent_record`, `dtc_order`, `dtc_order_line`, `household`, `loyalty_account`,
  `loyalty_transaction`, `preference`, `subscription`, `finance.ar_invoice`, `ar_payment`. Same rows, no file
  read, bronze and silver stay `NO_OP`. Removing the hints would avoid it but they are what orders the key
  registration of the first run, so they stay (re-testing the first run without them was out of scope).
- Metric views cannot be defined in a pipeline → job task `metric_views` (notebook `02a`).
- Model tags are applied after the pipeline by job task `model_tags` (notebook `02b`); they survive refreshes.

## First run and re-runs - "load once" evidence (live, 2026-10-23)

User rule: *if the tables are loaded once, we don't need to run and load again.* Measured on a fresh
catalog `zz_cpg_bc_e2e`, set up exactly as a participant does it (notebook `01_setup_catalog` from a
workspace folder, `bundle deploy -t dev`, run `cpg_lakehouse_job`):

| | job run | result | job time | pipeline updates | data work |
|---|---|---|---|---|---|
| 1st run (fresh catalog) | 896080243101670 | SUCCESS (all 4 tasks, attempt 0) | 524 s | `c43d4606` FAILED unexpectedly after 212 s → `37afd3af` RETRY_ON_FAILURE COMPLETED in 154 s | update 1: bronze read the 36 CSV files (108,359 rows), silver 36 + gold 36 materialized views FULL_RECOMPUTE (= first build). Update 2: **0 files read, all 72 MVs `NO_OP`**, 36 PRIMARY KEY + 123 FOREIGN KEY registered |
| 2nd run (no change) | 26352436884186 | SUCCESS | 247 s | `f98610fb` COMPLETED in 154 s (single update) | 0 files read, 72/72 MVs `NO_OP`; metric views 26/26 `unchanged` (6 s); model tags 2,061/2,061 already correct, 0 statements (6 s); validate 36/36 row counts match `data/manifest.json` |

| 3rd run, after lab step 3 (policies attached) | 974355586975806 | SUCCESS (validate green: 36/36 silver counts match the manifest, 123/123 foreign keys, 4 row-filtered gold tables reported) | 276 s | `7ff60164` COMPLETED, pipeline task 174 s | 0 files read, silver 36/36 `NO_OP`, gold 25 `NO_OP` + **11 `FULL_RECOMPUTE`** from silver (see the governance bullet above) |
| 4th run, policies still attached | 954194445198464 | SUCCESS (validate green) | 283 s | `6d650729` COMPLETED, pipeline task 182 s | the same 11 gold tables recomputed again - it repeats on every run while the policies are attached |
Task times, 1st → 2nd run: pipeline 374 s → 163 s, metric_views 104 s → 39 s, model_tags 113 s → 35 s,
validate 35 s → 44 s. What remains in a no-op run is serverless start-up and the planning of 72 flows.
Bronze proof: all 108,359 bronze rows carry an `_ingested_at` between 09:40:37 and 09:41:07 UTC (update 1);
neither later update added a row. "Chosen technique" = `details:planning_information.incrementalization_status`
in the event log (`SELECT ... FROM event_log('<pipeline id>') WHERE event_type = 'planning_information'`).
Two traps when reading the event log: `technique_information` lists *every* technique the planner considered
(`MAINTENANCE_TYPE_ROW_BASED` with `PLAN_NOT_INCREMENTALIZABLE` is listed for every gold table because of the
`OR EXISTS` hint), so look at the entry with `is_chosen = true` or at `incrementalization_status`; and
`flow_progress.metrics.num_output_rows` reports the table's full row count even for a `NO_OP` update, so it is
not evidence of a recompute. The 3rd/4th-run rows were measured on 2026-10-23 after notebook 03 (run
149100240013522, defaults SE01); notebook 03 was rolled back afterwards (run 424082203759713).
A second fresh-catalog run (`zz_cpg_bc_fresh`, job run 1 SUCCESS in 482 s with the same failed-update +
retry pattern) was summarised with the first trap (35 gold tables "ROW_BASED" in the retry, 27 after lab
step 3); its pipeline has since been deleted, so the chosen techniques of that run can no longer be read. The
`zz_cpg_bc_e2e` numbers above are the ones read correctly.

### Why the very first update fails - and what was tried

The first update completes every flow (all data is loaded) and then fails while registering the
PRIMARY/FOREIGN KEY constraints of the brand-new tables; the event log has no exception text, only
`Update ... is FAILED unexpectedly`. Only the PK of `finance.company_code` (the one table without foreign
keys) is registered at that point. Throw-away gold-only pipelines (catalog `zz_cpg_bc_exp`, all deleted
afterwards) narrowed it down:

| experiment (fresh schemas, first update) | gold tables | foreign keys | result |
|---|---|---|---|
| finance / consumer subsets, FK depth 2-4 (e.g. company_code → gl_account → profit_center → cost_center, + ledger; loyalty_program → tier → shopper → household → address) | 2-5 | 1-8 | COMPLETED with all keys - 12 of 12 runs (incl. 3 repeats) |
| 5 finance tables + `journal_entry` | 6 | 13 | FAILED, 1 PK (2 of 2 runs) |
| finance subset / consumer only | 7 / 12 | 18 / 32 | FAILED, 1 PK |
| all 36, FKs only to `finance.company_code` (depth 1, no chains) | 36 | 13 | FAILED, 0 constraints |
| all 36 as generated / without build-order hints / built strictly one after the other | 36 | 123 | FAILED, 1 PK |
| all 36 without the 23 cross-schema FKs | 36 | 100 | FAILED, 3 PK |
| gold as STREAMING TABLES instead of materialized views | 7 / 36 | 18 / 123 | FAILED, 1 PK |

Conclusion: the first update of a new pipeline registers the keys of its brand-new tables only for
small sets - every run with up to 8 foreign keys succeeded, every run with 13 or more failed,
independent of FK depth, build order (hints, serial "chain"), table type (MV or streaming table) and
cross-schema keys. The bootcamp gold layer has 123 foreign keys, so a single successful first update is
not achievable for this model today. The one alternative that gives a successful first update per
pipeline - splitting gold into pipelines of at most ~8 foreign keys each (a foreign key to a table owned
by another, already-run pipeline does work) - would need 15+ pipelines and was rejected. Accepted
design: one job run; the pipeline retries itself once (the job task keeps `max_retries: 1` as a second
safety net); in the measured run the retry was a pure metadata step (0 files read, 72 `NO_OP`, ≈ 2.5 min);
every later run is a single update that loads nothing (no-op before lab step 3; 11 gold tables recomputed
from silver after it). Never use *Full refresh* to "fix" it - it would reload everything.
