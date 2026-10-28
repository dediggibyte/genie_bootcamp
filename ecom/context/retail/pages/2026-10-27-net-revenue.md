---
title: Net Revenue
domain: Retail and Commerce
subdomain: Sales and Returns
synonyms:
  - revenue
  - sales
  - net sales
  - turnover
  - omsättning
description: Sales value of completed orders after line discounts, in SEK excl. VAT.
related_assets:
  - <catalog>.retail.fact_returns
  - <catalog>.retail.fact_sales
  - <catalog>.retail.return_metrics
  - <catalog>.retail.sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Net Revenue

## Definition

**Net revenue** = Σ (`quantity` × `unit_price_sek` − `discount_sek`) over the lines of **completed** orders (`retail.fact_sales.net_revenue_sek`). Cancelled orders are not sales and are not in `fact_sales`. Returns are reported separately (refunds), not netted.

## How to calculate

Use the governed metric view `<catalog>.retail.sales_metrics` (measure `net_revenue_sek`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(net_revenue_sek) AS net_revenue_sek
FROM <catalog>.retail.sales_metrics
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**248 606.20 SEK** (Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Adding cancelled orders - they are not in fact_sales and are not revenue.
* Subtracting refunds from net revenue - Nordvik reports returns separately (return rate, refunds).

## Related terms

* [Gross Margin](2026-10-27-gross-margin.md)
* [Average Order Value](2026-10-27-average-order-value.md)
* [Return Rate](2026-10-27-return-rate.md)

## Example questions

* What was net revenue by month?
* Which store region has the highest net revenue?
