---
title: Standard Cost
domain: Finance
subdomain: General Ledger
synonyms:
  - standard cost per unit
  - unit cost
  - cost estimate
  - product cost
  - standardkostnad
  - cost roll-up
description: "The planned (standard) manufacturing cost of one unit of a SKU, split into raw material, packaging, labour, overhead and freight-in components; used to value inventory and to post standard COGS."
owner: Head of Product Costing (role)
related_assets:
  - <catalog>.finance.standard_cost
  - <catalog>.finance.cogs_allocation
  - <catalog>.manufacturing.manufacturing_facility
  - <catalog>.finance.standard_cost_metrics
sources:
  - Fjällmark Costing Guideline, "Annual standard cost roll" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: finance.standard_cost, finance.cogs_allocation"
---

# Standard Cost

## Definition

The **standard cost** of a SKU is the cost Fjällmark *plans* to incur to make one unit of it at a
given plant. It is the sum of its cost components:

> `total_standard_cost` = `raw_material_cost` + `packaging_material_cost` + `direct_labor_cost`
> + `variable_overhead_cost` + `fixed_overhead_cost` + `machine_overhead_cost` + `freight_in_cost`

Standard cost is set by product costing, approved, **released**, and is valid for a period
(`valid_from_date` – `valid_to_date`). Standard COGS (GL account 4000) = units sold × standard cost;
differences between actual and standard production cost are booked as production variances
(account 4100).

## Business rules

1. The current standard of a SKU is the record with `costing_type = 'standard'`,
   `release_status = 'released'` (or `locked`) whose validity period contains the date of interest.
2. The SKU is `standard_cost.primary_standard_sku_id`; its readable SKU code is part of
   `cost_estimate_number` (`CE-<sku code>-<year>-<STA|ACT|PLA>`, e.g. `CE-BP-CRISP-RYE-250-2026-STA` →
   `BP-CRISP-RYE-250`) and its product name is on the webshop order lines (`consumer.dtc_order_line.sku_id`,
   `product_name`). The plant is `primary_standard_manufacturing_facility_id`. (The product master
   belongs to the full industry model, not to the bootcamp.)
3. `standard_cost.fiscal_year` and `fiscal_period` are **strings** (`'2026'`, `'03'`) in this table.
4. Currency is `standard_cost.currency_code` — the producing entity's currency; convert to EUR before
   comparing plants in different countries.
5. For "current standard cost" questions use the released `finance.standard_cost` record valid on the date
   and convert it to EUR with the GL rate (see *Group Currency & FX*); the 2026 released standards are about
   2 % higher than the 2025 ones (2025: about 3 % above 2024).
6. `previous_standard_cost` and `cost_variance_amount` / `cost_variance_percentage` describe the
   change versus the previous standard (cost inflation), **not** production variances.

## How to calculate (SQL)

```sql
-- Current released standard cost per SKU with its component split
WITH sku_names AS (   -- product names as sold in the webshop
  SELECT sku_id, MAX(product_name) AS product_name FROM consumer.dtc_order_line GROUP BY sku_id
)
SELECT regexp_extract(sc.cost_estimate_number, '^CE-(.+)-[0-9]{4}-[A-Z]+$', 1) AS sku_code,
       n.product_name,
       sc.currency_code,
       sc.valid_from_date,
       sc.valid_to_date,
       sc.raw_material_cost,
       sc.packaging_material_cost,
       sc.direct_labor_cost,
       sc.variable_overhead_cost + sc.fixed_overhead_cost + sc.machine_overhead_cost AS overhead_cost,
       sc.freight_in_cost,
       sc.total_standard_cost
FROM finance.standard_cost sc
LEFT JOIN sku_names n ON n.sku_id = sc.primary_standard_sku_id
WHERE sc.costing_type = 'standard'
  AND sc.release_status IN ('released', 'locked')
  AND DATE'2026-09-30' BETWEEN sc.valid_from_date AND coalesce(sc.valid_to_date, DATE'9999-12-31')
ORDER BY sku_code;
```

```sql
-- Current released standard cost per SKU in EUR (September 2026 finance rate of the costing currency)
WITH fx AS (   -- standard_cost has no company code: key the finance rate by currency
  SELECT jel.company_code_currency_code AS currency_code, AVG(jel.exchange_rate) AS eur_rate
  FROM finance.journal_entry_line jel
  JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
  WHERE je.posting_status = 'posted' AND je.fiscal_year = 2026 AND je.fiscal_period = 9
  GROUP BY ALL
)
SELECT regexp_extract(sc.cost_estimate_number, '^CE-(.+)-[0-9]{4}-[A-Z]+$', 1) AS sku_code,
       sc.currency_code,
       sc.total_standard_cost                         AS current_standard_local,
       ROUND(sc.total_standard_cost * fx.eur_rate, 4) AS current_standard_eur
FROM finance.standard_cost sc
JOIN fx ON fx.currency_code = sc.currency_code
WHERE sc.costing_type = 'standard'
  AND sc.release_status IN ('released', 'locked')
  AND DATE'2026-09-30' BETWEEN sc.valid_from_date AND coalesce(sc.valid_to_date, DATE'9999-12-31')
ORDER BY sku_code;
```

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Averaging all `standard_cost` rows of a SKU | Mixes draft, simulated and historical estimates; pick the released one valid on the date. |
| Comparing `total_standard_cost` across plants without FX | Poznań costs are in PLN, Lund/Norrköping in SEK. |
| Treating `cost_variance_amount` as production variance | It is the change against the previous standard. Production variances are GL account 4100 / `cogs_allocation.variance_amount`. |
| Filtering `fiscal_period = 3` | The column is a 2-character string: use `'03'`. |

## Example questions

* What is the standard cost of the Mjuk Care shampoo SKUs?
* Which cost component is largest for Kallkälla sparkling water?
* How much did standard costs increase versus the previous standard?
