# Full-model lakehouse pipeline (generated)

Every `.sql` file below `full_model/src/pipeline/`, `full_model/src/metric_views/industry/` and every
`.json` file in `full_model/src/model_tags/` is **generated** by
[`tools/generate_lakehouse.py`](../../../tools/generate_lakehouse.py) (repository root) from the vendored industry model
[`tools/model/consumer_goods_v2_mvm.json`](../../../tools/model/consumer_goods_v2_mvm.json)
(Lakehouse Industry Data Model *Consumer Goods v2 MVM*, © Databricks, Databricks license - see
[`../../LICENSE.md`](../../LICENSE.md) and [`../../NOTICE.md`](../../NOTICE.md), copies of `tools/model/`;
modified for this bootcamp).
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
| `<domain>/03_gold.sql` | gold | the **exact industry table** as materialized view `<domain>.<table>`: column names/order/types/comments, table comment, `NOT NULL` + `PRIMARY KEY`, **all** model foreign keys (except self-references) |

All 10 domains, 116 gold tables. The bootcamp variant (3 domains, foreign keys only between them) is in
`bootcamp/pipeline/`.

`${catalog}` is substituted by the pipeline from its configuration key `catalog` (set by the bundle).

## Silver cleaning rules (what the raw data needs, see `full_model/data/README.md`)

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
  pipeline, or one owned by another pipeline that has already run. The full model builds all 10 domains
  in one pipeline; the bootcamp variant omits keys into domains it does not build.
- **Self-referencing foreign keys are rejected** by pipelines
  (`TABLE_MATERIALIZATION_CYCLIC_FOREIGN_KEY_DEPENDENCY`) → the 23 self-references of the model are
  omitted (listed in a comment above each table). All other model FKs form no cycle.
- A pipeline orders tables only by the data they read, not by foreign keys. Each gold query therefore
  ends with `WHERE TRUE OR EXISTS (SELECT 1 FROM <FK target table>) ...` - it never filters a row but
  makes the pipeline build the referenced tables (and their primary keys) first.
- **Very first run of a fresh catalog:** the first update loads all data, then ends with `FAILED
  unexpectedly` while registering the keys. The cause is the number of keys on brand-new tables, not FKs
  between tables of the same update: first updates with up to 8 foreign keys always registered them, 13 or
  more always failed (evidence: `bootcamp/pipeline/README.md`). A second update registers the keys without
  reading files: the pipeline's automatic retry, or the job's pipeline task retry (`max_retries: 1`), or the
  next job run. On the earlier full-model test catalog `zz_cpg_test_b1_full` the automatic retry was
  cancelled and the next job run (update `ab9b64b1`) registered all 116 primary and 733 foreign keys with all
  232 silver and gold materialized views `NO_OP`. **Never use a full refresh**: it would reload everything.
- Metric views cannot be defined in a pipeline → job task `metric_views` (notebook `02a`).
- Model tags are applied after the pipeline by job task `model_tags` (notebook `02b`); they survive refreshes.
