---
title: Vehicles Sold
domain: Mobility and Automotive
subdomain: Vehicle Sales
synonyms:
  - units
  - registrations
  - volume
  - cars sold
description: Number of new vehicles sold (one row per vehicle in fact_vehicle_sales).
related_assets:
  - <catalog>.mobility.dim_customer
  - <catalog>.mobility.fact_vehicle_sales
  - <catalog>.mobility.vehicle_sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Vehicles Sold

## Definition

**Vehicles sold** = number of rows in `mobility.fact_vehicle_sales` (one row per vehicle, contract date `sale_date`). Cars, vans and trucks are counted alike - filter `vehicle_type` for a single type.

## How to calculate

Use the governed metric view `<catalog>.mobility.vehicle_sales_metrics` (measure `units_sold`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(units_sold) AS units_sold
FROM <catalog>.mobility.vehicle_sales_metrics
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**38** (Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Counting service visits as sales.

## Related terms

* [Vehicle Revenue](2026-10-27-vehicle-revenue.md)
* [EV Share](2026-10-27-ev-share.md)

## Example questions

* How many vehicles did we sell per month?
* Units sold by dealer
