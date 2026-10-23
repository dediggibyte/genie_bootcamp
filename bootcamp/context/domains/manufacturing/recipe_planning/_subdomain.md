---
title: Recipe Planning
domain: Manufacturing
subdomain: Recipe Planning
subdomain_tag: Manufacturing/Recipe Planning
description: "What to make and how to make it. Manufacturing bills of material, routings (operation sequences and standard times) and the planned orders produced by MRP / S&OP that are later converted into production orders."
owner: Head of Manufacturing Excellence (role)
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "manufacturing", subdomain "recipe_planning" (tools/model/consumer_goods_v2_mvm.json)
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# Recipe Planning (Manufacturing)

**What to make and how to make it.** Manufacturing bills of material, routings (operation sequences and standard times) and the planned orders produced by MRP / S&OP that are later converted into production orders.

* Governed tag (UC Semantics subdomain): `Manufacturing/Recipe Planning` — applied to the tables below by notebook `05_business_context`.
* Gold tables: `<catalog>.manufacturing.<table>`; industry model subdomain key `recipe_planning`.

## Tables

| Table | Type | Primary key | What it holds |
|---|---|---|---|
| `manufacturing_bom` | Master | `manufacturing_bom_id` | Bill of Materials master record (header + component lines) defining the complete material structure for each finished good or semi-finished SKU. Header captures BOM number, BOM type (production, co-product, phantom), base quantity, unit of measure, validity dates, PLM system reference, and BOM status. |
| `routing` | Master | `routing_id` | Production routing master (header + operation steps) defining the complete manufacturing process sequence for a finished or semi-finished SKU. Header captures routing number, routing type (standard, reference, rate), base quantity, plant, validity dates, and total standard lead time. |
| `planned_order` | Transactional | `planned_order_id` | Production planning record representing the complete planning pipeline from S&OP/IBP through MRP execution to production order conversion. Encompasses both Master Production Schedule (MPS) entries (planned quantities by SKU/facility/period with schedule versioning) and MRP-generated planned orders (system-proposed production or procurement proposals). |

## Main joins (foreign keys inside the bootcamp scope)

* `manufacturing_bom.manufacturing_facility_id` → `manufacturing.manufacturing_facility.manufacturing_facility_id`
* `routing.manufacturing_facility_id` → `manufacturing.manufacturing_facility.manufacturing_facility_id`
* `planned_order.converted_production_order_id` → `manufacturing.production_order.production_order_id`
* `planned_order.manufacturing_bom_id` → `manufacturing.manufacturing_bom.manufacturing_bom_id`
* `planned_order.manufacturing_facility_id` → `manufacturing.manufacturing_facility.manufacturing_facility_id`
* `planned_order.routing_id` → `manufacturing.routing.routing_id`

## Questions this subdomain answers

* How many planned orders were converted to production orders last month?
* Which SKUs have more than one routing?

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
