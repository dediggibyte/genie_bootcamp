---
title: Yield
domain: Manufacturing
subdomain: Batch Execution
synonyms:
  - production yield
  - first pass yield
  - yield %
  - output yield
  - material yield
  - utbyte
  - Ausbeute
description: "Yield = good output quantity ÷ input quantity of a production step, in percent; recorded per production order and batch in manufacturing.yield_record (actual_yield_percentage) with loss reasons. Fjällmark lines normally run at about 97 %."
owner: Head of Manufacturing Excellence (role)
related_assets:
  - <catalog>.manufacturing.production_performance_metrics
  - <catalog>.manufacturing.yield_record
  - <catalog>.manufacturing.production_order
  - <catalog>.manufacturing.batch_record
  - <catalog>.manufacturing.production_line
  - <catalog>.manufacturing.yield_record_metrics
sources:
  - Fjällmark Manufacturing Excellence playbook, "Yield and scrap" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: manufacturing.yield_record, manufacturing.production_order.yield_percentage"
---

# Yield

## Definition

> **Yield %** = good output ÷ input × 100
>
> At record level: `yield_record.actual_yield_percentage`
> (≈ `output_quantity` ÷ `input_quantity` × 100).
>
> **Aggregated yield** (plant, line, month) = Σ `output_quantity` ÷ Σ `input_quantity` × 100 over
> the yield records in scope (quantity-weighted).

Related columns: `theoretical_yield_percentage` (what the recipe allows),
`yield_variance_percentage` (actual − theoretical), `yield_loss_reason_code` and
`yield_loss_reason_description` (why), `yield_variance_cost_impact` (cost of the loss, in
`currency_code`). Production orders carry an order-level `yield_percentage` and batches a
`batch_record.yield_percentage`.

Normal level: about **97 %** on all mature lines (theoretical yield 97.1 %); Tampere was lower during
its 2025 ramp-up (loss reason `RAMPUP`).

## Business rules

1. Aggregate with quantities (Σ output ÷ Σ input), not by averaging percentages, unless the user asks
   for "average yield per order".
2. Period = month of `yield_record.measurement_timestamp`.
3. Yield, scrap and rework belong together: input = output + scrap + rework (+ process loss).
4. Loss reasons are codes, set when actual yield is clearly below the theoretical 97.1 %:
   `EQMALF` equipment malfunction, `RAMPUP` start-up losses (Tampere ramp-up), `CHGOVR` changeover
   losses, `MATSHT` material shortage, `LBLERR` label misalignment, `FILLWT` fill-weight adjustments,
   `CARTJM` carton feed jams. The description column tells the story behind the code.
5. The order-level `production_order.yield_percentage` = `confirmed_quantity` ÷ `order_quantity` × 100
   (planned quantity basis); `yield_record` uses the same quantities as input and output.
6. **Known event:** in **March 2026** line **PL-POZ-L2** (Poznań liquid filling) dropped from about
   97.2 % (February) to **86.8 %** yield because of worn filler nozzles (`EQMALF`); scrap 2.4 % → 7.3 %;
   back to 97.5 % in April after the repair on 4 April 2026.

## How to calculate (SQL)

```sql
-- Monthly yield by production line (quantity-weighted)
SELECT pl.line_code,
       date_trunc('MONTH', yr.measurement_timestamp)                       AS month,
       ROUND(100 * SUM(yr.output_quantity) / SUM(yr.input_quantity), 2)    AS yield_pct,
       ROUND(SUM(yr.scrap_quantity), 0)                                    AS scrap_qty
FROM manufacturing.yield_record yr
JOIN manufacturing.production_line pl ON pl.production_line_id = yr.production_line_id
WHERE yr.measurement_timestamp >= DATE'2026-01-01'
GROUP BY ALL
ORDER BY pl.line_code, month;
```

```sql
-- Main yield loss reasons in March 2026
SELECT yr.yield_loss_reason_code,
       any_value(yr.yield_loss_reason_description) AS description,
       COUNT(*)                                     AS records,
       ROUND(SUM(yr.input_quantity - yr.output_quantity), 0) AS lost_qty
FROM manufacturing.yield_record yr
WHERE yr.measurement_timestamp >= DATE'2026-03-01'
  AND yr.measurement_timestamp <  DATE'2026-04-01'
  AND yr.yield_loss_reason_code IS NOT NULL
GROUP BY yr.yield_loss_reason_code
ORDER BY lost_qty DESC;
```

Governed: `<catalog>.manufacturing.production_performance_metrics` (yield % measure).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `AVG(actual_yield_percentage)` across lines of different size | Unweighted; small batches count as much as big ones. |
| Mixing `production_order.yield_percentage` and `yield_record` in one figure | Different grains; pick one and say which. |
| Treating `theoretical_yield_percentage` as actual | It is the recipe target. |

## Example questions

* Which production line had the lowest yield in March 2026, and what was the reason?
* How did yield at the Poznań plant develop in 2026?
* What did the yield losses on PL-POZ-L2 cost?
