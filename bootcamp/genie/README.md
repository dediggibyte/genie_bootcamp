# Genie Agent template — "Fjällmark Business Analyst"

`fjallmark_business_analyst.json` is the complete definition of the bootcamp's one Genie Agent (formerly
*Genie space*): a serialized Genie space (version 2) with the placeholder `__CATALOG__` instead of a catalog
name. Notebook `../notebooks/04_genie_agent.py` replaces the placeholder with the participant's catalog and
creates the agent — or updates it in place — through the REST API `/api/2.0/genie/spaces`.

The file is **generated**: edit `../../tools/build_genie_template.py`, never the JSON. The agent is built on
tables of the Lakehouse Industry Data Model *Consumer Goods v2 MVM* (© Databricks, Inc., Databricks license —
see [`../LICENSE.md`](../LICENSE.md) and [`../NOTICE.md`](../NOTICE.md), copies of `tools/model/`); the agent content (descriptions,
instructions, examples, benchmarks) is written for the fictional company Fjällmark Consumer Goods AB.

| key in the JSON | meaning |
|---|---|
| `title`, `description` | notebook 04 appends ` (<catalog>)` to the title and `Catalog: <catalog>. [template <version>]` to the description |
| `template_version` | first 12 hex of the SHA-256 of `serialized_space`; notebook 04 only updates an agent whose description carries another version (so a re-run is a no-op and UI edits survive) |
| `tricky_benchmark_ids` | benchmarks marked ⚠ in notebook 04's score table |
| `serialized_space` | what the Genie API stores (sent as a JSON string) |
| `_license`, `_generated_by` | provenance; not sent to the API |

## What is in the agent

| surface | count | notes |
|---|---|---|
| data sources | 31 (10 metric views + 21 gold tables) | platform limit 50, bootcamp ceiling 45 — see the selection below |
| column settings | per source | synonyms, descriptions, entity matching on ~120 stable categorical columns, ~300 noisy / technical / personal columns hidden |
| text instruction | 1 | the ```` ```text ```` block of `../context/genie/agent_instructions.md` (business rules, owned by the context pages) + a short "HOW TO QUERY" block from the builder |
| example SQL | 19 | one per query *shape*, each with usage guidance; none repeats a benchmark |
| SQL snippets | 6 measures, 6 filters, 4 expressions | raw-table logic only — metric views already govern their measures |
| join specs | 1 | only joins that are **not** foreign keys (`journal_entry_line.plant_code = manufacturing_facility.plant_code`); FK joins are derived by Genie from the Unity Catalog constraints (authoring them creates duplicate `alias_2` joins) |
| sample questions | 9 | |
| benchmarks | 25 | checked SQL answers, all three domains and all storylines, 8 deliberately tricky |

### Data source selection

**Included — curated metric views (4).** They own the official KPI definitions, so Genie never re-derives a
formula: `finance.net_revenue_metrics` (Net Revenue, COGS, gross margin, production variances — the answer to
any "revenue" question), `consumer.dtc_sales_metrics` (webshop GMV / net sales / AOV / returns / active
shoppers, local *and* EUR), `finance.receivables_metrics` (open / overdue / disputed AR, DSO) and
`manufacturing.production_performance_metrics` (OEE, yield, scrap, downtime, on-time, cost variance).

**Included — industry metric views (6).** Only those whose measures are correct as they stand and that answer
questions the curated views do not: `consumer.loyalty_account_metrics` (points, redemption),
`consumer.shopper_metrics` (shopper base by segment), `consumer.consent_record_metrics` (GDPR consents),
`manufacturing.yield_record_metrics` (yield / scrap by loss reason and shift), `manufacturing.batch_record_metrics`
(quality release, GMP deviations), `manufacturing.equipment_metrics` (MTBF / MTTR, equipment OEE).

**Included — gold tables (21).** For row-level detail and attributes the metric views do not carry, and so Genie
can follow the FK graph:

| domain | tables | why |
|---|---|---|
| consumer | `shopper`, `dtc_order`, `dtc_order_line`, `loyalty_account`, `loyalty_tier`, `address`, `subscription` | order / line detail, the S1 "order total incl. VAT" trap, tiers, market (ship-to country), subscriptions; personal columns hidden |
| finance | `company_code`, `gl_account`, `journal_entry`, `journal_entry_line`, `profit_center`, `ar_invoice`, `ap_invoice`, `standard_cost` | entity / currency master, GL detail and the FX rate pattern, brands (profit centres), receivables and payables detail, cost estimates |
| manufacturing | `manufacturing_facility`, `production_line`, `production_order`, `yield_record`, `batch_record`, `equipment` | plant and line names (`FI-TMP`, `PL-POZ-L2`), order detail, yield loss reasons (S3 `EQMALF`, S4 `RAMPUP`), batches, equipment |

**Excluded on purpose.**

| object(s) | reason |
|---|---|
| industry `consumer.dtc_order_metrics`, `consumer.dtc_order_line_metrics` | sum order / line amounts across SEK, NOK, DKK and EUR and call the incl.-VAT order total "gross merchandise value" — exactly the S1 / S2 traps; `dtc_sales_metrics` replaces them |
| industry `finance.ar_invoice_metrics`, `finance.journal_entry_line_metrics`, `finance.journal_entry_metrics` | mix currencies / add debits and credits without sign; replaced by `receivables_metrics` and `net_revenue_metrics` |
| industry `consumer.subscription_metrics`, `finance.ap_invoice_metrics`, `finance.ap_payment_metrics`, `finance.ar_payment_metrics`, `finance.cogs_allocation_metrics`, `finance.standard_cost_metrics` | revenue / amount measures add different currencies (e.g. subscription revenue over EUR + SEK + NOK + DKK); the tables are included where detail is needed |
| industry `manufacturing.production_order_metrics` | `avg_yield_percentage` / `avg_oee_percentage` are averages of percentages; `production_performance_metrics` replaces it |
| industry `manufacturing.manufacturing_facility_metrics`, `production_line_metrics`, `consumer.household_metrics`, `consumer.loyalty_transaction_metrics` | master-data counts (4 plants, 16 lines) or outside the bootcamp storylines; fewer sources = better routing |
| gold `household`, `preference`, `consent_record`, `loyalty_program`, `loyalty_transaction`, `ap_payment`, `ar_payment`, `cogs_allocation`, `cost_center`, `ledger`, `manufacturing_bom`, `routing`, `work_center`, `planned_order`, `production_confirmation` | not needed by the agent's questions (a metric view covers it, or the table is technical); adding them dilutes Genie's table choice |
| bronze / silver / `governance` schema | never: not governed (silver) or not business data |

### Column settings (rules used)

* **Hidden (`exclude`)**: columns that are empty or constant in the data, technical columns (created / modified
  timestamps and users, source-system references, clearing documents, tokens), and personal data
  (`shopper` names, e-mail, phone, birth date, postal code; `address` street / postal code / coordinates;
  `dtc_order.ship_to_name`; employee names). Masks from notebook 03 protect them anyway; hiding keeps Genie from
  even trying.
* **Entity matching + format assistance** only on stable, low-cardinality strings that people type: company
  codes, plant codes / names, line tags, brands, tiers, markets, statuses, reason codes, product names (~90).
* **Synonyms / descriptions** where business words differ from model names (market = ship-to country, line =
  `mes_asset_tag`, "order value incl. VAT" = `order_total_amount`, local-currency measures "only per currency").

## Benchmarks (expected answers on the bootcamp data)

⚠ = deliberately tricky. Values from `zz_cpg_bc_e2e` (current data, 2026-10-23).

| # | question | expected (checked SQL) | storyline |
|---|---|---|---|
| 1 ⚠ | What was our total revenue in 2025? | Net Revenue 20,814,527 EUR (not the webshop) | S1 |
| 2 ⚠ | What is our gross margin percentage year to date? | 50.6 % (2026, Jan-Sep) | S1 |
| 3 | Which legal entity generated the most net revenue in 2025? | SE01, 5,977,382 EUR | |
| 4 | How much net revenue did Mjuk Care generate in 2025? | 5,384,234 EUR | |
| 5 | How much production variance did PL01 book in March 2026? | 4,647 EUR | S3 |
| 6 ⚠ | Compare webshop net sales with the DTC net revenue booked in finance for 2025, in EUR. | 103,893 vs 98,241 EUR | S1 |
| 7 ⚠ | What was total webshop GMV across all markets in September 2026? | 12,517 EUR (one EUR total, not per currency) | S2 |
| 8 ⚠ | What were webshop net sales in Sweden in 2025 in Swedish kronor? | 432,949 SEK | S2 |
| 9 | How many webshop orders did we receive in Q3 2026? | 860 (cancelled excluded) | |
| 10 ⚠ | How many active shoppers did we have in the 12 months to September 2026? | 1,668 (ordering shoppers, not `lifecycle_status`) | |
| 11 ⚠ | Compare the AOV of Gold and Platinum members with non-members over the last 12 months. | 59.64 vs 23.09 EUR | S5 |
| 12 | What share of webshop sales value was returned in 2025? | 5.44 % | |
| 13 | How many loyalty members are in each Fjällmark Friends tier? | Bronze 1,052, Silver 490, Gold 270, Platinum 123 | S5 |
| 14 | How many shoppers are in the at-risk CLTV segment? | 697 | S5 |
| 15 | Which company code has the highest DSO? | DE01, 65.7 days | S6 |
| 16 | What is the group DSO? | 39.2 days | S6 |
| 17 | How much of DE01's open receivables is overdue, in EUR? | 287,959 EUR | S6 |
| 18 | How many invoices are currently disputed and what is their open value in EUR? | 12, 305,149 EUR | S6 |
| 19 | What was the OEE of the Tampere plant in each quarter since it started? | 58.3 % (2025-Q2) … 78.9 % (2026-Q3) | S4 |
| 20 | Which plant had the lowest OEE in 2025? | Tampere Oat Drink Plant, 63.4 % | S4 |
| 21 | How did yield, scrap rate and downtime on line PL-POZ-L2 change from February to April 2026? | yield 97.2 → 86.8 → 97.5 %, downtime 240 → 724 → 126 min | S3 |
| 22 ⚠ | What was the yield loss reason on Poznań line 2 in March 2026? | EQMALF — worn filler nozzles (needs `yield_record` + `production_line`) | S3 |
| 23 | How many production orders finished late in 2026 at each plant? | per plant (FI-TMP 6, …) | S3 |
| 24 | In which month of 2026 did the Poznań plant have the most downtime? | March 2026, 1,455 min | S3 |
| 25 | What is the on-time completion rate of production orders per plant in 2026? | per plant (FI-TMP 94.5 %, …) | |

## Evaluation history (live, catalog `zz_cpg_bc_e2e`, agent "Fjällmark Business Analyst (zz_cpg_bc_e2e)")

| run (eval run id) | template | score | what changed before the run |
|---|---|---|---|
| 1 (`01f1cecc9d3111e397f5ae6963a54c6b`) | `7ee53fc514b5` | 23 / 25 GOOD (92 %) | first version. BAD: "total webshop GMV across all markets" (Genie listed `gmv_local` per currency — the S2 trap); "Gold and Platinum vs non-members" (listed every tier instead of the two groups) |
| 2 (`01f1cece505817ae9e38e680c266e58c`) | `e20929ab8a36` | 24 / 25 GOOD (96 %) | column descriptions on `gmv_local` / `dtc_net_sales_local` ("only per currency_code; totals use *_eur"), two HOW TO QUERY rules (a total across markets is one EUR number; build requested groups with CASE), new example SQL teaching CASE-grouping on Bronze/Silver vs Gold/Platinum *frequency* (not the benchmark's AOV). Both fixed. New BAD: yield-loss-reason question answered correctly (EQMALF) but with `scrap_quantity` instead of the benchmark's arbitrary `COUNT(*)` column |
| 3 (`01f1cecfc6f514f593736dccef79c3ab`) | `faedb37d43f0` | **25 / 25 GOOD (100 %)** | benchmark repair only: the yield-loss-reason answer SQL returns just the reason code and description (Genie's answer had been right) |

Genie is a language model: an individual question can flip between runs. Judge the agent on the whole
benchmark. In the UI, the **Benchmarks** tab → **Run benchmarks** starts a run; the **Evaluations** tab →
the run in the **Evaluation name** column shows each question as **Good**, **Bad** or **Manual review
needed** (API: `GOOD` / `BAD` / `NEEDS_REVIEW`), with Genie's **Model output** next to the **Ground truth**.

Expected values are for a user who sees every company code. A participant whose rows are filtered by
notebook 03 (default SE01) gets filtered results from Genie *and* from the answer SQL; benchmark runs under
a row filter have not been measured.

## Changing the agent

```bash
# 1. edit tools/build_genie_template.py (or the text block in bootcamp/context/genie/agent_instructions.md)
python3 -I tools/build_genie_template.py                     # rewrite the JSON (deterministic)
python3 -I tools/build_genie_template.py --run-sql \
    --catalog <loaded catalog> --warehouse <id> --profile <p>  # every example / benchmark / snippet runs
# 2. re-run notebooks/04_genie_agent.py: new template_version -> the agent is updated in place, then benchmarked
```

Limits verified on the platform: ≤ 50 data sources combined, exactly one text instruction item, 32-hex
lower-case IDs sorted by id (question IDs unique across sample questions and benchmarks), benchmark answer
format `SQL` only, `column_configs` sorted by column name. GET returns metric views folded into `tables`
(fine for round trips). MCP sources (GitHub) cannot be set through the API — the click path (agent →
**Sources** tab → **Add** → GitHub MCP service, then **Agent mode** and sign-in under **Configure**) is in
`../context/README.md`, step B, and in the participant guide `../README.md`, step 5b.
