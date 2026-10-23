---
title: Downtime
domain: Manufacturing
subdomain: Batch Execution
synonyms:
  - downtime minutes
  - line stops
  - unplanned downtime
  - stoppage
  - breakdown time
  - stillestånd
  - Stillstandszeit
description: "Minutes a production line did not produce during planned production time, recorded per production order (production_order.downtime_minutes); reported per line, plant and month. Changeover time is tracked separately."
owner: Head of Manufacturing Excellence (role)
related_assets:
  - <catalog>.manufacturing.production_performance_metrics
  - <catalog>.manufacturing.production_order
  - <catalog>.manufacturing.production_confirmation
  - <catalog>.manufacturing.batch_record
  - <catalog>.manufacturing.production_line
sources:
  - Fjällmark Manufacturing Excellence playbook, "Loss tree" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: downtime_minutes on production_order, production_confirmation, batch_record"
---

# Downtime

## Definition

> **Downtime (minutes)** = Σ `production_order.downtime_minutes` of production orders in scope
> (plant, line, month of `actual_finish_timestamp`).

Downtime is unplanned or planned stop time *during* a production order (breakdowns, material
shortages, quality holds). **Changeovers** between orders are tracked separately in
`production_order.changeover_time_minutes` (standard: `production_line.changeover_time_standard_minutes`).
Downtime reduces OEE **availability**.

## Business rules

1. **One grain only.** Downtime is recorded at three grains — `production_order.downtime_minutes`
   (order total), `production_confirmation.downtime_minutes` (per operation confirmation) and
   `batch_record.downtime_minutes` (per batch). They describe the **same** stops; never add them up.
   Default: production order.
2. Do not include changeover minutes unless the user asks for "total lost time".
3. Normalise when comparing lines: downtime minutes per order, or per 1,000 units confirmed.
4. **Known event:** downtime on **PL-POZ-L2** spiked in **March 2026** (worn filler nozzles; repaired
   4 April 2026).

## How to calculate (SQL)

```sql
-- Downtime by line and month, with minutes per order
SELECT pl.line_code,
       date_trunc('MONTH', po.actual_finish_timestamp)      AS finish_month,
       COUNT(*)                                             AS orders,
       SUM(po.downtime_minutes)                             AS downtime_minutes,
       ROUND(SUM(po.downtime_minutes) / COUNT(*), 1)        AS downtime_min_per_order,
       SUM(po.changeover_time_minutes)                      AS changeover_minutes
FROM manufacturing.production_order po
JOIN manufacturing.production_line pl ON pl.production_line_id = po.production_line_id
WHERE po.actual_finish_timestamp >= DATE'2026-01-01'
GROUP BY ALL
ORDER BY pl.line_code, finish_month;
```

Governed: `<catalog>.manufacturing.production_performance_metrics` (downtime minutes measure).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Joining orders, confirmations and batches and summing all `downtime_minutes` | Triple counting (and join fan-out). |
| Adding changeover time to downtime by default | Different loss category. |
| Comparing total minutes of a 3-line plant with a 5-line plant | Normalise per order, per line or per volume. |

## Example questions

* Which line had the most downtime in March 2026?
* How much downtime did the Poznań plant have per month this year?
* Is downtime or changeover the bigger loss on the Lund lines?
