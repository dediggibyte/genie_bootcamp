---
title: Vehicle Sales
domain: Mobility and Automotive
subdomain: Vehicle Sales
subdomain_key: vehicle_sales
subdomain_tag: Nordvik Mobility and Automotive/Vehicle Sales
description: New-vehicle sales and the private and fleet customers who buy them.
objects:
  - <catalog>.mobility.dim_customer
  - <catalog>.mobility.fact_vehicle_sales
  - <catalog>.mobility.vehicle_sales_metrics
---

# Vehicle Sales (Mobility and Automotive)

New-vehicle sales and the private and fleet customers who buy them.

* **Governed tag / UC subdomain:** `Nordvik Mobility and Automotive/Vehicle Sales` - applied to the objects below by notebook 05b.
* **Business terms:** [Vehicles Sold](../pages/2026-10-27-units-sold.md), [Vehicle Revenue](../pages/2026-10-27-vehicle-revenue.md), [EV Share](../pages/2026-10-27-ev-share.md), [Fleet Customer](../pages/2026-10-27-fleet-customer.md)

## Tables and metric views

| object | type |
|---|---|
| `<catalog>.mobility.dim_customer` | dimension |
| `<catalog>.mobility.fact_vehicle_sales` | fact |
| `<catalog>.mobility.vehicle_sales_metrics` | metric view |
