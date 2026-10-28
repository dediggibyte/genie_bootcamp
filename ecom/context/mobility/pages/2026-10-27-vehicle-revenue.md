---
title: Vehicle Revenue
domain: Mobility and Automotive
subdomain: Vehicle Sales
synonyms:
  - revenue
  - vehicle sales value
  - turnover
description: Sale price minus discount of the vehicles sold, SEK excl. VAT.
related_assets:
  - <catalog>.mobility.dim_customer
  - <catalog>.mobility.fact_vehicle_sales
  - <catalog>.mobility.vehicle_sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Vehicle Revenue

## Definition

**Vehicle revenue** = Σ (`sale_price_sek` − `discount_sek`) = Σ `net_sale_price_sek`. **Average sale price** = vehicle revenue / vehicles sold. Trucks cost 2-4 MSEK, so mixed averages are dominated by trucks - compare averages within a vehicle type.

## How to calculate

Use the governed metric view `<catalog>.mobility.vehicle_sales_metrics` (measure `vehicle_revenue_sek`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(vehicle_revenue_sek) AS vehicle_revenue_sek
FROM <catalog>.mobility.vehicle_sales_metrics
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**34 199 534 SEK** (Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Using the list price without the discount.
* Comparing average prices across cars and trucks.

## Related terms

* [Vehicles Sold](2026-10-27-units-sold.md)
* [Service Revenue](2026-10-27-service-revenue.md)

## Example questions

* What is the average sale price of cars?
* Vehicle revenue by brand
