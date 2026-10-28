---
title: Service Revenue
domain: Mobility and Automotive
subdomain: Aftersales Service
synonyms:
  - aftersales revenue
  - workshop revenue
description: Amount billed to customers for workshop visits (warranty work is 0), SEK excl. VAT.
related_assets:
  - <catalog>.mobility.fact_service_visits
  - <catalog>.mobility.service_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Service Revenue

## Definition

**Service revenue** = Σ `billed_amount_sek` of the workshop visits = labour + parts, except **warranty work**, which the manufacturer pays (billed 0 to the customer). Labour is 1 150 SEK per hour for cars and vans, 1 450 SEK for trucks.

## How to calculate

Use the governed metric view `<catalog>.mobility.service_metrics` (measure `service_revenue_sek`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(service_revenue_sek) AS service_revenue_sek
FROM <catalog>.mobility.service_metrics
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**149 725 SEK** (Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Adding labour + parts of warranty visits to revenue.

## Related terms

* [Vehicle Revenue](2026-10-27-vehicle-revenue.md)
* [Warranty Share](2026-10-27-warranty-share.md)

## Example questions

* Service revenue by service type
* Which workshop earns the most?
