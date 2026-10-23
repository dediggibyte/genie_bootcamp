---
title: Schedule Adherence (On-time Completion)
domain: Manufacturing
subdomain: Batch Execution
synonyms:
  - on-time completion
  - on-time completion rate
  - schedule attainment
  - production on time
  - late production orders
  - leveransprecision produktion
  - Termintreue
description: "Share of finished production orders whose actual finish date is on or before the scheduled finish date (production_order.actual_finish_timestamp vs scheduled_finish_date), per plant, line and month."
owner: Head of Production Planning (role)
related_assets:
  - <catalog>.manufacturing.production_performance_metrics
  - <catalog>.manufacturing.production_order
  - <catalog>.manufacturing.production_line
  - <catalog>.manufacturing.manufacturing_facility
  - <catalog>.manufacturing.planned_order
sources:
  - Fjällmark S&OP process description, "Execution KPIs" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: manufacturing.production_order"
---

# Schedule Adherence (On-time Completion)

## Definition

> A production order is **on time** if `CAST(actual_finish_timestamp AS DATE)` ≤
> `scheduled_finish_date`.
>
> **On-time completion %** = on-time finished orders ÷ all finished orders × 100, where *finished*
> = `actual_finish_timestamp IS NOT NULL`, in the month of `actual_finish_timestamp`.
>
> **Days late** = `datediff(actual finish date, scheduled_finish_date)` for late orders.

## Business rules

1. Only finished orders are measured; open orders (no actual finish) are excluded — but orders that
   are open **past** their scheduled finish date are "overdue" and can be reported separately.
2. Compare dates, not timestamps (the schedule is a date).
3. Same-day finish counts as on time.
4. **Known event:** Poznań line PL-POZ-L2 finished many orders late in **March 2026** (equipment
   malfunction, repaired 4 April 2026).

## How to calculate (SQL)

```sql
-- On-time completion % by plant and month
SELECT f.erp_plant_code                                                AS plant,
       date_trunc('MONTH', po.actual_finish_timestamp)                 AS finish_month,
       COUNT(*)                                                        AS finished_orders,
       ROUND(100 * AVG(CASE WHEN CAST(po.actual_finish_timestamp AS DATE) <= po.scheduled_finish_date
                            THEN 1 ELSE 0 END), 1)                     AS on_time_pct,
       ROUND(AVG(CASE WHEN CAST(po.actual_finish_timestamp AS DATE) > po.scheduled_finish_date
                      THEN datediff(CAST(po.actual_finish_timestamp AS DATE), po.scheduled_finish_date) END), 1) AS avg_days_late
FROM manufacturing.production_order po
JOIN manufacturing.manufacturing_facility f
  ON f.manufacturing_facility_id = po.manufacturing_facility_id
WHERE po.actual_finish_timestamp IS NOT NULL
GROUP BY ALL
ORDER BY plant, finish_month;
```

Governed: `<catalog>.manufacturing.production_performance_metrics` (on-time completion % measure).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Comparing `actual_finish_timestamp` with `scheduled_finish_date` as timestamps | A 14:00 finish on the due date would count as late. |
| Counting open orders as late | They are not finished; report them as overdue open orders. |
| Using `actual_start_timestamp` vs `scheduled_start_date` | That is start adherence, a different KPI. |

## Example questions

* What share of production orders finished on time per plant in 2026?
* Which line had the most late orders in March 2026?
* How many days late were the Poznań orders on average?
