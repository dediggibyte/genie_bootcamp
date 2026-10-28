---
title: Customer Segment
domain: Telecommunications and Media
subdomain: Customers and Subscriptions
synonyms:
  - segment
  - consumer vs business
  - B2B vs B2C
description: consumer or business; the scope of the governance row filter.
related_assets:
  - <catalog>.telecom.billing_metrics
  - <catalog>.telecom.dim_customer
  - <catalog>.telecom.dim_subscription
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Customer Segment

## Definition

Every customer is `consumer` or `business` (`dim_customer.customer_segment`, copied to subscriptions, invoices and usage). Business customers buy the Företag plans. The segment is the scope of the governance row filter.

## How to calculate

Use the governed metric view `<catalog>.telecom.billing_metrics` (measure `billed_revenue_sek`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(billed_revenue_sek) AS billed_revenue_sek
FROM <catalog>.telecom.billing_metrics
WHERE billing_month = DATE'2026-06-01' AND customer_segment = 'business'
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**3 492 SEK** (business billed revenue June 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Mixing the plan's target segment with the customer's segment - use customer_segment.

## Related terms

* [ARPU](2026-10-27-arpu.md)
* [Active Subscription](2026-10-27-active-subscription.md)

## Example questions

* Billed revenue by segment
