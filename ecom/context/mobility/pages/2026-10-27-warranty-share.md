---
title: Warranty Share
domain: Mobility and Automotive
subdomain: Aftersales Service
synonyms:
  - warranty rate
  - warranty work
description: Warranty visits as a share of all workshop visits.
related_assets:
  - <catalog>.mobility.fact_service_visits
  - <catalog>.mobility.service_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Warranty Share

## Definition

**Warranty share %** = visits with `is_warranty = true` / visits × 100. Warranty visits use workshop hours but bring no service revenue.

## How to calculate

Use the governed metric view `<catalog>.mobility.service_metrics` (measure `warranty_share_pct`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(warranty_share_pct) AS warranty_share_pct
FROM <catalog>.mobility.service_metrics
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**13.64 %** (Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Computing the share of service revenue instead of visits.

## Related terms

* [Service Revenue](2026-10-27-service-revenue.md)

## Example questions

* What is the warranty share by brand?
