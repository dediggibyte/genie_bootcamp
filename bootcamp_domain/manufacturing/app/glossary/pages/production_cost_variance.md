---
title: Production Cost Variance
domain: Manufacturing
subdomain: Batch Execution
synonyms:
  - cost variance
  - production variance
  - actual vs planned cost
  - cost overrun
  - manufacturing variance
  - Kostenabweichung
description: "Actual minus planned cost of production orders (production_order.actual_cost − planned_cost), in the plant's local currency; positive = overrun. Posted to finance as production variances (GL account 4100)."
owner: Head of Product Costing (role)
related_assets:
  - <catalog>.manufacturing.production_performance_metrics
  - <catalog>.manufacturing.production_order
  - <catalog>.manufacturing.yield_record
  - <catalog>.finance.cogs_allocation
  - <catalog>.finance.journal_entry_line
  - <catalog>.manufacturing.manufacturing_facility
sources:
  - Fjällmark Costing Guideline, "Variance analysis" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: manufacturing.production_order.planned_cost / actual_cost"
---

# Production Cost Variance

## Definition

> **Cost variance** = Σ `production_order.actual_cost` − Σ `production_order.planned_cost`
> (completed orders, in `production_order.currency_code`).
>
> **Cost variance %** = variance ÷ Σ `planned_cost` × 100. Positive = more expensive than planned.

`planned_cost` = order quantity × standard cost; `actual_cost` includes extra material, labour and
machine time caused by scrap, rework and downtime. Yield-related cost is also visible per record in
`yield_record.yield_variance_cost_impact`. Finance posts the variances to GL account **4100
Production variances** (part of COGS).

## Business rules

1. Currency = plant currency (`currency_code`: SEK for Lund/Norrköping, EUR for Tampere, PLN for
   Poznań). Convert to EUR before comparing plants. Production orders carry **no company code**, so
   take the finance rate **by currency and month**: an FX table from `journal_entry_line` grouped by
   `company_code_currency_code`, `fiscal_year`, `fiscal_period`, joined on `production_order.currency_code`
   + year/month of `actual_finish_timestamp` (second query below). The plant's company code, if needed,
   is `manufacturing_facility.profit_center_id` → `finance.profit_center.company_code_id` (Lund and
   Norrköping SE01, Tampere FI01, Poznań PL01).
2. Use completed orders (`order_status IN ('CNF','DLV','TECO','CLSD')`), period = month of
   `actual_finish_timestamp`.
3. **Known event:** the March 2026 PL-POZ-L2 incident (yield loss, scrap, downtime) created a variance
   spike at Poznań that also shows in PL01's COGS for March 2026.

## How to calculate (SQL)

```sql
-- Cost variance by plant and month (local currency)
SELECT f.erp_plant_code                                AS plant,
       po.currency_code,
       date_trunc('MONTH', po.actual_finish_timestamp) AS finish_month,
       ROUND(SUM(po.planned_cost), 2)                  AS planned_cost,
       ROUND(SUM(po.actual_cost), 2)                   AS actual_cost,
       ROUND(SUM(po.actual_cost - po.planned_cost), 2) AS cost_variance,
       ROUND(100 * SUM(po.actual_cost - po.planned_cost) / SUM(po.planned_cost), 2) AS cost_variance_pct
FROM manufacturing.production_order po
JOIN manufacturing.manufacturing_facility f
  ON f.manufacturing_facility_id = po.manufacturing_facility_id
WHERE upper(po.order_status) IN ('CNF', 'DLV', 'TECO', 'CLSD')
  AND po.actual_finish_timestamp IS NOT NULL
GROUP BY ALL
ORDER BY plant, finish_month;
```

```sql
-- Cost variance by plant in EUR, 2026 (finance monthly rate of the plant currency)
WITH fx AS (
  SELECT jel.company_code_currency_code AS currency_code,
         je.fiscal_year,
         je.fiscal_period,
         AVG(jel.exchange_rate)          AS eur_rate
  FROM finance.journal_entry_line jel
  JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
  WHERE je.posting_status = 'posted'
  GROUP BY ALL
)
SELECT f.erp_plant_code                                                AS plant,
       ROUND(SUM(po.planned_cost * fx.eur_rate), 2)                    AS planned_cost_eur,
       ROUND(SUM(po.actual_cost * fx.eur_rate), 2)                     AS actual_cost_eur,
       ROUND(SUM((po.actual_cost - po.planned_cost) * fx.eur_rate), 2) AS cost_variance_eur,
       ROUND(100 * SUM(po.actual_cost - po.planned_cost) / SUM(po.planned_cost), 2) AS cost_variance_pct
FROM manufacturing.production_order po
JOIN manufacturing.manufacturing_facility f
  ON f.manufacturing_facility_id = po.manufacturing_facility_id
JOIN fx ON fx.currency_code = po.currency_code
       AND fx.fiscal_year   = year(po.actual_finish_timestamp)
       AND fx.fiscal_period = month(po.actual_finish_timestamp)
WHERE upper(po.order_status) IN ('CNF', 'DLV', 'TECO', 'CLSD')
  AND year(po.actual_finish_timestamp) = 2026
GROUP BY f.erp_plant_code
ORDER BY cost_variance_eur DESC;
```

Governed: `<catalog>.manufacturing.production_performance_metrics` (planned vs. actual cost variance).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Summing variances of all plants in local currency | Adds SEK, EUR and PLN. |
| Joining the FX table on company code | `production_order` has no `company_code_id`; key the rate by currency (or go plant → profit centre → company code). |
| Including open orders | Their actual cost is still accumulating. |
| Comparing `production_order.actual_cost` with finance COGS | COGS is cost of goods **sold** (EUR, by selling period); production cost is cost of goods **made**. |

## Example questions

* Which plant had the largest cost overrun in 2026?
* What did the March 2026 problems on PL-POZ-L2 cost?
* How does the production cost variance trend per month?
