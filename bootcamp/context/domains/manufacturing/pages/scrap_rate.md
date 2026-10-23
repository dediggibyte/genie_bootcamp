---
title: Scrap Rate
domain: Manufacturing
subdomain: Batch Execution
synonyms:
  - scrap
  - scrap %
  - waste rate
  - reject rate
  - kassation
  - Ausschussquote
  - spoilage
description: "Scrap rate = scrapped quantity ÷ input quantity, in percent, from manufacturing.yield_record; compared with the line target production_line.scrap_rate_target_percent."
owner: Head of Manufacturing Excellence (role)
related_assets:
  - <catalog>.manufacturing.production_performance_metrics
  - <catalog>.manufacturing.yield_record
  - <catalog>.manufacturing.production_order
  - <catalog>.manufacturing.production_line
  - <catalog>.manufacturing.batch_record
sources:
  - Fjällmark Manufacturing Excellence playbook, "Yield and scrap" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: manufacturing.yield_record.scrap_quantity, manufacturing.production_line.scrap_rate_target_percent"
---

# Scrap Rate

## Definition

> **Scrap rate %** = Σ `yield_record.scrap_quantity` ÷ Σ `yield_record.input_quantity` × 100
> (same records, same period).

Scrap is material or product that cannot be used or reworked and is destroyed. **Rework**
(`rework_quantity`) is *not* scrap. Each line has a target in
`production_line.scrap_rate_target_percent` (2.5 % on all Fjällmark lines); normal scrap is about
2–2.5 %.

## Business rules

1. Use the yield records as the default source; `production_order.scrap_quantity` ÷
   `production_order.order_quantity` gives an order-level view (planned-quantity basis) — label it.
2. Period = month of `yield_record.measurement_timestamp`.
3. Ratio of sums, not average of percentages.
4. **Known event:** scrap on **PL-POZ-L2** roughly **tripled in March 2026** (filler nozzle wear,
   reason code `EQMALF`), back to normal after the repair on 4 April 2026.

## How to calculate (SQL)

```sql
-- Scrap rate vs. target by line, March 2026
SELECT pl.line_code,
       pl.scrap_rate_target_percent                                          AS target_pct,
       ROUND(100 * SUM(yr.scrap_quantity) / SUM(yr.input_quantity), 2)       AS scrap_rate_pct
FROM manufacturing.yield_record yr
JOIN manufacturing.production_line pl ON pl.production_line_id = yr.production_line_id
WHERE yr.measurement_timestamp >= DATE'2026-03-01'
  AND yr.measurement_timestamp <  DATE'2026-04-01'
GROUP BY pl.line_code, pl.scrap_rate_target_percent
ORDER BY scrap_rate_pct DESC;
```

Governed: `<catalog>.manufacturing.production_performance_metrics` (scrap rate measure).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Adding `rework_quantity` to scrap | Reworked units become good product. |
| Summing `scrap_quantity` from `production_order`, `batch_record` **and** `yield_record` | The same scrap is recorded at several grains — double counting. |
| Comparing scrap quantities of lines with different units of measure | Use the rate, or filter one `unit_of_measure`. |

## Example questions

* Which lines exceeded their scrap target in 2026?
* How much did scrap increase on PL-POZ-L2 in March 2026?
* What is the scrap rate per plant this year?
