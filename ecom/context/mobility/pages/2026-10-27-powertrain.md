---
title: Powertrain
domain: Mobility and Automotive
subdomain: Vehicle Catalog
synonyms:
  - fuel type
  - drivetrain
  - engine type
description: ev (battery electric), hybrid, petrol or diesel.
related_assets:
  - <catalog>.mobility.dim_vehicle_model
  - <catalog>.mobility.vehicle_sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Powertrain

## Definition

Every model has one **powertrain**: `ev`, `hybrid`, `petrol` or `diesel` (`dim_vehicle_model.powertrain`, flag `is_ev`). Vehicle types: `car`, `van`, `truck`.

## How to calculate

Use the governed metric view `<catalog>.mobility.vehicle_sales_metrics` (measure `ev_share_pct`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(ev_share_pct) AS ev_share_pct
FROM <catalog>.mobility.vehicle_sales_metrics
WHERE vehicle_type = 'truck'
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**57.14 %** (EV share of trucks Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Treating 'XC60 Plug-in Hybrid' as an EV.

## Related terms

* [EV Share](2026-10-27-ev-share.md)

## Example questions

* Units sold by powertrain
