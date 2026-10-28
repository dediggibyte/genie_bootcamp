---
title: Dealer and Region
domain: Mobility and Automotive
subdomain: Dealer Network
synonyms:
  - dealer
  - dealership
  - region
  - workshop
description: 5 car dealers and the truck centre in regions STO, GOT, MAL and UME.
related_assets:
  - <catalog>.mobility.dim_dealer
  - <catalog>.mobility.vehicle_sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Dealer and Region

## Definition

Dealers roll up to **regions**: `STO` (Bromma, Täby and the truck centre Södertälje), `GOT` (Hisingen), `MAL` (Bulltofta), `UME` (Umeå, no workshop). Trucks are sold and serviced only by the **truck centre** (D06). The region is the scope of the governance row filter.

## How to calculate

Use the governed metric view `<catalog>.mobility.vehicle_sales_metrics` (measure `units_sold`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(units_sold) AS units_sold
FROM <catalog>.mobility.vehicle_sales_metrics
WHERE dealer_region = 'STO'
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**23** (vehicles sold in STO Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Expecting service visits in UME - the Umeå dealer has no workshop.

## Related terms

* [Vehicles Sold](2026-10-27-units-sold.md)
* [Service Revenue](2026-10-27-service-revenue.md)

## Example questions

* Which dealer sold the most vehicles?
* Service visits by region
