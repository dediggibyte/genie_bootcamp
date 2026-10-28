---
title: Fleet Customer
domain: Mobility and Automotive
subdomain: Vehicle Sales
synonyms:
  - fleet
  - B2B customer
  - company customer
description: A company that buys vans and trucks (customer_type = fleet); others are private.
related_assets:
  - <catalog>.mobility.dim_customer
  - <catalog>.mobility.fact_vehicle_sales
  - <catalog>.mobility.vehicle_sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Fleet Customer

## Definition

**Fleet customers** (`customer_type = 'fleet'`) are companies that buy vans and trucks and some cars; **private** customers buy cars. Customer names, e-mail and phone are personal data.

## How to calculate

Use the governed metric view `<catalog>.mobility.vehicle_sales_metrics` (measure `units_sold`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(units_sold) AS units_sold
FROM <catalog>.mobility.vehicle_sales_metrics
WHERE vehicle_type = 'truck'
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**7** (trucks sold Jan-Jun 2026 - all to fleet customers, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Listing individual private customers - answer in aggregate.

## Related terms

* [Vehicles Sold](2026-10-27-units-sold.md)

## Example questions

* How many vehicles did fleet customers buy?
