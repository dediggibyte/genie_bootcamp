---
title: Return Rate
domain: Retail and Commerce
subdomain: Sales and Returns
synonyms:
  - returns %
  - return percentage
  - returrate
description: Returned units as a share of units sold, by the order date of the sale.
related_assets:
  - <catalog>.retail.fact_returns
  - <catalog>.retail.fact_sales
  - <catalog>.retail.return_metrics
  - <catalog>.retail.sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Return Rate

## Definition

**Return rate %** = returned units / units sold × 100. Returns are matched to the sold line (`fact_returns.order_line_id`) and counted in the month of the **order**, so a return in July of a June order belongs to June. **Refunds** = Σ `fact_returns.refund_sek`.

## How to calculate

Use the governed metric view `<catalog>.retail.sales_metrics` (measure `return_rate_pct`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(return_rate_pct) AS return_rate_pct
FROM <catalog>.retail.sales_metrics
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**22.45 %** (Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Counting returned orders instead of units.
* Using the return date month - the rate is by order month.

## Related terms

* [Net Revenue](2026-10-27-net-revenue.md)
* [Return Reason](2026-10-27-return-reason.md)

## Example questions

* What is the return rate by category?
* Which brands have the highest return rate?
