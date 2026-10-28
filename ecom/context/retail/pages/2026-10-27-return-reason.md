---
title: Return Reason
domain: Retail and Commerce
subdomain: Sales and Returns
synonyms:
  - why returned
  - return cause
description: "Why a customer returned goods: wrong_size, changed_mind, defect or damaged."
related_assets:
  - <catalog>.retail.fact_returns
  - <catalog>.retail.fact_sales
  - <catalog>.retail.return_metrics
  - <catalog>.retail.sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Return Reason

## Definition

Every return carries one **reason**: `wrong_size`, `changed_mind`, `defect`, `damaged`. `defect` and `damaged` are quality returns; `wrong_size` and `changed_mind` are customer returns.

## How to calculate

Use the governed metric view `<catalog>.retail.return_metrics` (measure `return_count`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(return_count) AS return_count
FROM <catalog>.retail.return_metrics
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**10** (returns Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Mixing return counts (lines) with returned units.

## Related terms

* [Return Rate](2026-10-27-return-rate.md)

## Example questions

* What are the most common return reasons?
* How much was refunded for defects?
