# Curated bootcamp metric views

Hand-written Unity Catalog **metric views** (YAML version 1.1) for the bootcamp's Genie Agent. They encode
the business definitions of the glossary (`../../context/domains/*/pages/*.md`) once, so that Genie,
dashboards and SQL users all get the same numbers. They sit next to the 22 generated industry views
(`../industry/`) in the gold schemas and are built on tables of the Lakehouse Industry Data Model
*Consumer Goods v2 MVM* (© Databricks, Databricks license - see [`../../LICENSE.md`](../../LICENSE.md) and
[`../../NOTICE.md`](../../NOTICE.md), copies of `tools/model/`).

| file | view | grain (source) | joins (all many-to-one) | what it answers |
|---|---|---|---|---|
| `consumer_dtc_sales_metrics.sql` | `consumer.dtc_sales_metrics` | order line (`dtc_order_line`) | order header → shopper → loyalty tier, ship-to address, company code, monthly FX; brand profit centre | webshop GMV, DTC net sales, discounts, units, orders, AOV, return rate, active shoppers, orders per shopper, merchandise margin - local currency **and** EUR |
| `finance_net_revenue_metrics.sql` | `finance.net_revenue_metrics` | GL line (`journal_entry_line`) | journal entry, GL account, company code, profit centre → brand | **official Net Revenue**, COGS, Gross Margin (EUR, %), DTC / B2B revenue, trade discounts, returns, standard COGS, production variances |
| `finance_receivables_metrics.sql` | `finance.receivables_metrics` | AR invoice (`ar_invoice`) | company code, September-2026 FX | open / overdue / disputed AR (local and EUR), overdue share, aging bucket, billing, collection rate, **DSO**, days past due - snapshot as of 2026-09-30 |
| `manufacturing_production_performance_metrics.sql` | `manufacturing.production_performance_metrics` | production order (`production_order`) | plant, production line, monthly FX by currency | OEE (simple and volume-weighted, vs target), yield %, scrap rate %, on-time completion %, late orders, downtime, changeovers, planned vs actual cost variance (plant currency and EUR) |

Design rules used in every view:

* **Measures at the fact grain.** Every measure is a sum / count / distinct count over the source rows
  (order lines, GL lines, invoices, production orders); joined tables only add dimensions. Ratios are
  ratios of sums (`MEASURE(a) / MEASURE(b)`), never averages of percentages - so no header fan-out and no
  double counting. Grand totals equal the source table totals (checked).
* **Currency safety (storyline S2).** Amounts that can mix currencies are suffixed `_local` and documented
  "group by currency_code"; the EUR measures (`_eur`) convert with the finance monthly rate from
  `journal_entry_line.exchange_rate` (company code or currency + month; balances at the September 2026
  closing rate). `net_revenue_metrics` has no local amounts at all.
* **Business filters are built in:** cancelled webshop orders are excluded, the GL view only uses posted
  documents of account groups REVENUE and COGS, the production view only finished orders (cost measures
  only completed statuses CNF / DLV / TECO / CLSD).
* Percent measures are named `*_pct` and return 0-100. Every field has a `comment`, a `display_name` and,
  where users have other words for it, `synonyms` (Genie matches them); measures carry a `format`.

## How they are deployed

Job task `metric_views` (`../../notebooks/job_tasks/02a_create_metric_views.py`) reads every `*.sql` file
here (alphabetical, after the industry views), replaces `${catalog}` and **only creates missing views or
replaces changed ones** (the YAML is compared with the stored `view_text`). After editing a file here, run
just that task - no pipeline run needed:

```bash
# from the bootcamp/ folder: deploy the changed files, then run only the metric_views task
databricks bundle deploy -t dev --var catalog=<catalog>
databricks jobs run-now --json '{"job_id": <cpg_lakehouse_job id>, "only": ["metric_views"]}'
```

(or in the UI: redeploy from `bootcamp/databricks.yml` → *Deployments*, then run the job; the pipeline
task is a no-op and task `metric_views` replaces only the changed views).
Task `validate` (02c) checks that all industry **and** curated views exist and answer a query.

## Querying

```sql
SELECT fiscal_year, company_code,
       MEASURE(net_revenue_eur) AS net_revenue_eur, MEASURE(gross_margin_pct) AS gm_pct
FROM <catalog>.finance.net_revenue_metrics
GROUP BY ALL ORDER BY ALL;

SELECT loyalty_tier, MEASURE(avg_order_value_eur) AS aov_eur, MEASURE(orders_per_active_shopper) AS frequency
FROM <catalog>.consumer.dtc_sales_metrics GROUP BY ALL;

SELECT finish_month, MEASURE(yield_pct), MEASURE(scrap_rate_pct), MEASURE(downtime_minutes)
FROM <catalog>.manufacturing.production_performance_metrics
WHERE production_line = 'PL-POZ-L2' AND finish_year = 2026 GROUP BY ALL ORDER BY 1;

SELECT company_code, MEASURE(dso_days), MEASURE(overdue_ar_eur), MEASURE(disputed_ar_eur)
FROM <catalog>.finance.receivables_metrics GROUP BY ALL ORDER BY 2 DESC;
```

Caveats: `receivables_metrics.dso_days` is defined for the reporting date 2026-09-30 - slice it by company
code, customer or currency, not by billing / due month. `dtc_sales_metrics.active_shoppers` counts the
shoppers active in whatever period you filter (the glossary's default is the 12 months to 2026-09-30).

## Verification (live, catalog `zz_cpg_bc_e2e`, 2026-10-23)

All measures were compared with hand-written SQL taken from the glossary pages - 26 checks, every one
an exact match (max difference 0.0001 from rounding), including fan-out guards (view grand totals =
source table totals). Headline values: Net Revenue EUR 56,416,937 and gross margin 51.8 % (2024 - 2026-09);
DSO DE01 65.7 days (group 39.2); Tampere OEE 58.3 % (2025-Q2) → 78.9 % (2026-Q3); PL-POZ-L2 yield
97.2 % → 86.8 % → 97.5 % (Feb-Apr 2026), scrap 2.42 % → 7.34 %, downtime 240 → 724 min; webshop return
rate 5.78 %; AOV EUR Gold 56.65 / Platinum 58.88 vs Non-member 22.72.
