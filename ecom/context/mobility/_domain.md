---
title: Mobility and Automotive
domain: Mobility and Automotive
domain_tag: Nordvik Mobility and Automotive
business_unit: Nordvik Mobility
subtitle: Vehicle catalog, dealers, vehicle sales and aftersales service
description: Nordvik Mobility sells new cars, vans and trucks through 5 dealers and a truck centre and services them in its workshops. Owns the vehicle catalog, the dealer network, vehicle sales and aftersales - the source for units sold, vehicle revenue, EV share and service revenue.
business_owner: Head of Mobility Sales and Aftersales (role)
technical_owner: Mobility Data Product Team (role)
schema: <catalog>.mobility
genie_agent: Nordvik Mobility Analyst
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Mobility and Automotive (Nordvik Mobility)

Nordvik Mobility sells new cars, vans and trucks through 5 dealers and a truck centre and services them in its workshops. Owns the vehicle catalog, the dealer network, vehicle sales and aftersales - the source for units sold, vehicle revenue, EV share and service revenue.

* **Governed tag / UC domain:** `Nordvik Mobility and Automotive` - applied to the gold schema `<catalog>.mobility` by notebook
  `notebooks/2026-10-27-05-context-common.py` (run through `05b`), which can also create the domain itself.
* **Data:** sales and workshop visits 2026-01-01 to 2026-06-30. Amounts in SEK excl. VAT. All data is synthetic.
* **Genie Agent:** *Nordvik Mobility Analyst* (`genie/2026-10-27-mobility-agent.json`, created by notebook 04).

## Subdomains

| subdomain | governed tag | what it holds | gold objects |
|---|---|---|---|
| Vehicle Catalog | `Nordvik Mobility and Automotive/Vehicle Catalog` | Vehicle models with brand, type, body, powertrain and list price. | `mobility.dim_vehicle_model` |
| Dealer Network | `Nordvik Mobility and Automotive/Dealer Network` | Dealers and the truck centre, their regions and workshops. | `mobility.dim_dealer` |
| Vehicle Sales | `Nordvik Mobility and Automotive/Vehicle Sales` | New-vehicle sales and the private and fleet customers who buy them. | `mobility.dim_customer`, `mobility.fact_vehicle_sales`, `mobility.vehicle_sales_metrics` |
| Aftersales Service | `Nordvik Mobility and Automotive/Aftersales Service` | Workshop visits: service types, labour, parts, warranty work. | `mobility.fact_service_visits`, `mobility.service_metrics` |

## Business terms

| term | subdomain | definition |
|---|---|---|
| [Vehicles Sold](pages/2026-10-27-units-sold.md) | Vehicle Sales | Number of new vehicles sold (one row per vehicle in fact_vehicle_sales). |
| [Vehicle Revenue](pages/2026-10-27-vehicle-revenue.md) | Vehicle Sales | Sale price minus discount of the vehicles sold, SEK excl. VAT. |
| [EV Share](pages/2026-10-27-ev-share.md) | Vehicle Sales | Battery electric vehicles as a share of vehicles sold. |
| [Powertrain](pages/2026-10-27-powertrain.md) | Vehicle Catalog | ev (battery electric), hybrid, petrol or diesel. |
| [Dealer and Region](pages/2026-10-27-dealer-region.md) | Dealer Network | 5 car dealers and the truck centre in regions STO, GOT, MAL and UME. |
| [Service Revenue](pages/2026-10-27-service-revenue.md) | Aftersales Service | Amount billed to customers for workshop visits (warranty work is 0), SEK excl. VAT. |
| [Warranty Share](pages/2026-10-27-warranty-share.md) | Aftersales Service | Warranty visits as a share of all workshop visits. |
| [Fleet Customer](pages/2026-10-27-fleet-customer.md) | Vehicle Sales | A company that buys vans and trucks (customer_type = fleet); others are private. |
