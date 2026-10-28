---
title: Active Subscription
domain: Telecommunications and Media
subdomain: Customers and Subscriptions
synonyms:
  - active lines
  - subscriptions
  - abonnemang
description: A subscription with status active (no end date).
related_assets:
  - <catalog>.telecom.billing_metrics
  - <catalog>.telecom.dim_customer
  - <catalog>.telecom.dim_subscription
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Active Subscription

## Definition

A subscription is **active** when `status = 'active'` (end date empty). Two subscriptions were cancelled on 2026-05-31: they have May invoices and usage but nothing for June. A customer can hold several subscriptions.

## How to calculate

Use the governed metric view `<catalog>.telecom.billing_metrics` (measure `billed_subscriptions`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT COUNT(*) AS active_subscriptions
FROM <catalog>.telecom.dim_subscription
WHERE status = 'active'
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**22** (active subscriptions today, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Counting customers instead of subscriptions.

## Related terms

* [ARPU](2026-10-27-arpu.md)
* [Customer Segment](2026-10-27-customer-segment.md)

## Example questions

* How many active subscriptions per plan type?
