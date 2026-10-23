---
title: OEE (Overall Equipment Effectiveness)
domain: Manufacturing
subdomain: Batch Execution
synonyms:
  - OEE
  - overall equipment effectiveness
  - line efficiency
  - equipment effectiveness
  - availability performance quality
  - utnyttjandegrad
  - Gesamtanlageneffektivität
description: "OEE = Availability × Performance × Quality of a production line, in percent (0–100). Fjällmark reports OEE per production order (production_order.oee_percentage) and aggregates it as the average over completed orders by plant, line and month."
owner: Head of Manufacturing Excellence (role)
related_assets:
  - <catalog>.manufacturing.production_performance_metrics
  - <catalog>.manufacturing.production_order
  - <catalog>.manufacturing.production_confirmation
  - <catalog>.manufacturing.production_line
  - <catalog>.manufacturing.manufacturing_facility
  - <catalog>.manufacturing.production_order_metrics
sources:
  - Fjällmark Manufacturing Excellence playbook, "OEE standard" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: manufacturing.production_order.oee_percentage, manufacturing.production_confirmation"
---

# OEE — Overall Equipment Effectiveness

## Definition

> **OEE** = **Availability** × **Performance** × **Quality**
>
> * Availability = run time ÷ planned production time (losses: breakdowns, changeovers)
> * Performance = actual output rate ÷ design speed (losses: slow running, small stops)
> * Quality = good units ÷ total units (losses: scrap, rework)

At Fjällmark the MES calculates OEE per production order and stores it in
**`production_order.oee_percentage`** (0–100). The components are recorded per shop-floor
confirmation in `production_confirmation.oee_availability_percent`, `oee_performance_percent`,
`oee_quality_percent`.

> **OEE of a plant / line / month** = average of `oee_percentage` over production orders that
> **finished** in that period (`actual_finish_timestamp`), excluding orders without an OEE value.

World-class OEE is ≥ 85 %. Fjällmark's mature plants run at about 76–79 % against line targets of
80–83 % (`production_line.nominal_oee_target_percent`); the new Tampere plant's target is 78 %.

## Business rules

1. OEE is stored as **percent 0–100** — do not multiply by 100 again.
2. Attribute an order to the month of `actual_finish_timestamp` (fallback `scheduled_finish_date`
   for orders not finished yet — but those usually have no OEE).
3. Default aggregation is the **simple average** of order OEE. If the user asks for a
   volume-weighted OEE, weight by `confirmed_quantity` and say so.
4. **Tampere (FI-TMP)** started production in **April 2025**; its OEE ramps up from about 55 %
   (Q2 2025 58 %) and reaches the 78 % target in June 2026 (quarterly average Q2 2026 78.4 %, Q3 2026 78.9 %).
   Do not rank Tampere against mature plants over the ramp-up period without
   saying so.
5. **Poznań line PL-POZ-L2** lost OEE in **March 2026** (equipment malfunction: worn filler nozzles;
   lower quality and availability), recovered after the repair on 4 April 2026.

## How to calculate (SQL)

```sql
-- Monthly OEE by plant (average of production-order OEE, by finish month)
SELECT f.erp_plant_code                                 AS plant,
       date_trunc('MONTH', po.actual_finish_timestamp)  AS finish_month,
       COUNT(*)                                         AS orders,
       ROUND(AVG(po.oee_percentage), 1)                 AS avg_oee_pct
FROM manufacturing.production_order po
JOIN manufacturing.manufacturing_facility f
  ON f.manufacturing_facility_id = po.manufacturing_facility_id
WHERE po.actual_finish_timestamp IS NOT NULL
  AND po.oee_percentage IS NOT NULL
GROUP BY ALL
ORDER BY plant, finish_month;
```

```sql
-- OEE components by line for March 2026 (from shop-floor confirmations)
SELECT pl.line_code,
       ROUND(AVG(pc.oee_availability_percent), 1) AS availability_pct,
       ROUND(AVG(pc.oee_performance_percent), 1)  AS performance_pct,
       ROUND(AVG(pc.oee_quality_percent), 1)      AS quality_pct
FROM manufacturing.production_confirmation pc
JOIN manufacturing.production_order po ON po.production_order_id = pc.production_order_id
JOIN manufacturing.production_line  pl ON pl.production_line_id  = po.production_line_id
WHERE pc.posting_date >= DATE'2026-03-01' AND pc.posting_date < DATE'2026-04-01'
GROUP BY pl.line_code
ORDER BY quality_pct;
```

Governed: `<catalog>.manufacturing.production_performance_metrics` (OEE measure; plant, line, month
dimensions).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `AVG(oee_percentage) * 100` | Already a percentage. |
| Multiplying the averages of availability, performance and quality across many orders | Product of averages ≠ average of products; use the stored order OEE. |
| Using `equipment.oee_actual` | Equipment master snapshot, not production performance over time. |
| Ranking Tampere last in 2025 without context | It was ramping up after commissioning in April 2025. |

## Example questions

* What was OEE by plant per month in 2026?
* How did the Tampere plant's OEE develop since it opened?
* Which line had the lowest OEE in March 2026, and why?
