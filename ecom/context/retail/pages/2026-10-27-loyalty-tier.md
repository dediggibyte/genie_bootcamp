---
title: Loyalty Tier
domain: Retail and Commerce
subdomain: Customers
synonyms:
  - tier
  - membership level
  - Nordvik Club
description: "Tier of the Nordvik Club loyalty programme: none, silver or gold."
related_assets:
  - <catalog>.retail.dim_customer
  - <catalog>.retail.sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Loyalty Tier

## Definition

Every customer has a **loyalty tier** of the Nordvik Club: `none`, `silver`, `gold`. The tier is the customer's current tier (no history). Customer names, e-mail and phone are personal data - analyse customers only in aggregate.

## How to calculate

Use the governed metric view `<catalog>.retail.sales_metrics` (measure `order_count`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(order_count) AS order_count
FROM <catalog>.retail.sales_metrics
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**37** (completed orders Jan-Jun 2026, all tiers, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Listing individual customers - answer with counts and shares.

## Related terms

* [Average Order Value](2026-10-27-average-order-value.md)

## Example questions

* How do gold members' orders compare with non-members?
