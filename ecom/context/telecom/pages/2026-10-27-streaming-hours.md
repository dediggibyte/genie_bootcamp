---
title: Streaming Hours and Add-ons
domain: Telecommunications and Media
subdomain: Plans and Products
synonyms:
  - viewing hours
  - watch time
  - streaming add-on
  - Netflix
  - Spotify
  - Disney+
  - Max
description: Hours streamed; plans can include Netflix, Spotify, Disney+ or Max.
related_assets:
  - <catalog>.telecom.dim_plan
  - <catalog>.telecom.usage_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Streaming Hours and Add-ons

## Definition

**Streaming hours** = Σ `streaming_hours` in the TV app and the included services. A plan **includes streaming** when `dim_plan.included_streaming` lists a service (Netflix Standard, Spotify Premium, Disney+ Standard, Max) - flag `has_streaming`.

## How to calculate

Use the governed metric view `<catalog>.telecom.usage_metrics` (measure `streaming_hours`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(streaming_hours) AS streaming_hours
FROM <catalog>.telecom.usage_metrics
WHERE usage_month = DATE'2026-06-01'
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**324.40** (hours, June 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Assuming every TV plan includes Netflix - check included_streaming.

## Related terms

* [Data Usage](2026-10-27-data-usage.md)

## Example questions

* Streaming hours by plan
* Do customers with streaming add-ons use more data?
