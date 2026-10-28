---
title: Data Usage
domain: Telecommunications and Media
subdomain: Usage
synonyms:
  - data
  - traffic
  - GB
description: Data used in GB per subscription and month, mobile and fixed.
related_assets:
  - <catalog>.telecom.fact_usage
  - <catalog>.telecom.usage_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Data Usage

## Definition

**Data used** = Σ `data_gb` of `telecom.fact_usage` (one row per subscription and month). **Data per subscription** = data used / subscriptions with usage, per month. Broadband and bundles dominate the totals - compare within a plan type.

## How to calculate

Use the governed metric view `<catalog>.telecom.usage_metrics` (measure `avg_data_gb_per_subscription`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(avg_data_gb_per_subscription) AS avg_data_gb_per_subscription
FROM <catalog>.telecom.usage_metrics
WHERE usage_month = DATE'2026-06-01'
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**242.20 GB** (per subscription, June 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Averaging over both months without grouping by month.

## Related terms

* [Streaming Hours and Add-ons](2026-10-27-streaming-hours.md)

## Example questions

* Data usage by plan type
* Average data per mobile subscription
