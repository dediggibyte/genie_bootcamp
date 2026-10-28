---
title: Average Order Value
domain: Retail and Commerce
subdomain: Sales and Returns
synonyms:
  - AOV
  - basket size
  - average basket
  - average ticket
description: Net revenue divided by the number of completed orders.
related_assets:
  - <catalog>.retail.fact_returns
  - <catalog>.retail.fact_sales
  - <catalog>.retail.return_metrics
  - <catalog>.retail.sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Average Order Value

## Definition

**AOV** = net revenue / number of distinct completed orders (`order_id`). It is a ratio of sums, so it is computed per group from the totals - never as an average of line values.

## How to calculate

Use the governed metric view `<catalog>.retail.sales_metrics` (measure `average_order_value_sek`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(average_order_value_sek) AS average_order_value_sek
FROM <catalog>.retail.sales_metrics
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**6 719.09 SEK** (Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* AVG(net_revenue_sek) over order lines - that is the average line value, not the order value.

## Related terms

* [Net Revenue](2026-10-27-net-revenue.md)
* [Sales Region and Channel](2026-10-27-sales-region-channel.md)

## Example questions

* What is the average order value per channel?
* How did AOV develop by month?
