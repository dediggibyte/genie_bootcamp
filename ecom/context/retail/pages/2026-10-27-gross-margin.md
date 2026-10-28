---
title: Gross Margin
domain: Retail and Commerce
subdomain: Sales and Returns
synonyms:
  - margin
  - gross profit
  - GM%
  - bruttomarginal
description: Net revenue minus purchase cost of the goods sold, in SEK and as % of net revenue.
related_assets:
  - <catalog>.retail.fact_returns
  - <catalog>.retail.fact_sales
  - <catalog>.retail.return_metrics
  - <catalog>.retail.sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Gross Margin

## Definition

**Gross margin (SEK)** = net revenue − Σ (`quantity` × `dim_product.unit_cost_sek`). **Gross margin %** = gross margin / net revenue × 100. Purchase cost is **confidential**: users who are not cost readers see NULL (column mask), so the margin is NULL for them.

## How to calculate

Use the governed metric view `<catalog>.retail.sales_metrics` (measure `gross_margin_pct`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(gross_margin_pct) AS gross_margin_pct
FROM <catalog>.retail.sales_metrics
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**27.35 %** (Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Averaging the margin % of categories - always divide total margin by total revenue.
* Reporting a NULL margin as 0 - NULL means the purchase cost is masked for you.

## Related terms

* [Net Revenue](2026-10-27-net-revenue.md)
* [Product Category and Brand](2026-10-27-product-category.md)

## Example questions

* What is the gross margin % by category?
* Which brand has the lowest gross margin?
