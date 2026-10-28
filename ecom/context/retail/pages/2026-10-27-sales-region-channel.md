---
title: Sales Region and Channel
domain: Retail and Commerce
subdomain: Stores and Channels
synonyms:
  - region
  - channel
  - online vs store
  - webshop
description: Regions STO, GOT, MAL and ONLINE (webshop); channels store and online.
related_assets:
  - <catalog>.retail.dim_store
  - <catalog>.retail.sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Sales Region and Channel

## Definition

Each order belongs to the **store** that sold it. Stores roll up to a **region**: `STO` (Stockholm City, Kista), `GOT` (Göteborg Nordstan, Frölunda), `MAL` (Malmö Triangeln) and `ONLINE` (the webshop). **Channel** = `store` or `online`. The region is the scope of the governance row filter: a store manager sees only their region.

## How to calculate

Use the governed metric view `<catalog>.retail.sales_metrics` (measure `order_count`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(order_count) AS order_count
FROM <catalog>.retail.sales_metrics
WHERE channel = 'online'
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**6** (webshop orders Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Filtering on the city 'Göteborg' instead of region GOT (the webshop is also registered in Stockholm).

## Related terms

* [Net Revenue](2026-10-27-net-revenue.md)
* [Average Order Value](2026-10-27-average-order-value.md)

## Example questions

* Compare webshop and store revenue.
* Which region had the most orders?
