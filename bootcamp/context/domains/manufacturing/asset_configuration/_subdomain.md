---
title: Asset Configuration
domain: Manufacturing
subdomain: Asset Configuration
subdomain_tag: Manufacturing/Asset Configuration
description: "Plants, lines, work centres and equipment. The four plants (Lund, Norrköping, Tampere, Poznań), their 16 production lines, the work centres on each line and the equipment register."
owner: Head of Manufacturing Excellence (role)
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "manufacturing", subdomain "asset_configuration" (tools/model/consumer_goods_v2_mvm.json)
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# Asset Configuration (Manufacturing)

**Plants, lines, work centres and equipment.** The four plants (Lund, Norrköping, Tampere, Poznań), their 16 production lines, the work centres on each line and the equipment register. Use these tables to label production facts by plant and line.

* Governed tag (UC Semantics subdomain): `Manufacturing/Asset Configuration` — applied to the tables below by notebook `05_business_context`.
* Gold tables: `<catalog>.manufacturing.<table>`; industry model subdomain key `asset_configuration`.

## Tables

| Table | Type | Primary key | What it holds |
|---|---|---|---|
| `manufacturing_facility` | Master | `manufacturing_facility_id` | Master record for each manufacturing facility (plant/site) in the Consumer Goods network. Captures plant code, site name, address, GMP certification status, ISO 22716 compliance tier, production capacity (units/day), facility type (mixing, filling, packaging, co-manufacturing), regulatory registration numbers (FDA establishment ID, EPA site ID), and operational status. |
| `production_line` | Master | `production_line_id` | Master record for each physical production line within a manufacturing facility. Captures line code, line name, facility reference, line type (filling, blending, packaging, assembly), design speed (units/hour), nominal OEE target, GMP classification, MES asset tag (Siemens Opcenter), changeover time standard (minutes), and current operational status. |
| `work_center` | Master | `work_center_id` | Master record for individual work centers (machines, stations, cells) within a production line. Captures work center code, description, work center type (mixing vessel, filling machine, labeler, capper, palletizer), rated capacity, standard cycle time, maintenance class, MES equipment ID (Siemens Opcenter), GMP equipment qualification status (IQ/OQ/PQ), and calibration due date. |
| `equipment` | Master | `equipment_id` | Master reference table for equipment. Referenced by equipment_id. |

## Main joins (foreign keys inside the bootcamp scope)

* `manufacturing_facility.cost_center_id` → `finance.cost_center.cost_center_id`
* `manufacturing_facility.profit_center_id` → `finance.profit_center.profit_center_id`
* `production_line.cost_center_id` → `finance.cost_center.cost_center_id`
* `production_line.manufacturing_facility_id` → `manufacturing.manufacturing_facility.manufacturing_facility_id`
* `work_center.cost_center_id` → `finance.cost_center.cost_center_id`
* `work_center.manufacturing_facility_id` → `manufacturing.manufacturing_facility.manufacturing_facility_id`
* `work_center.production_line_id` → `manufacturing.production_line.production_line_id`
* `equipment.cost_center_id` → `finance.cost_center.cost_center_id`
* `equipment.gl_account_id` → `finance.gl_account.gl_account_id`
* `equipment.manufacturing_facility_id` → `manufacturing.manufacturing_facility.manufacturing_facility_id`
* `equipment.production_line_id` → `manufacturing.production_line.production_line_id`
* `equipment.work_center_id` → `manufacturing.work_center.work_center_id`

## Questions this subdomain answers

* Which lines does the Poznań plant have?
* What is the OEE target per line?
* When was the Tampere plant commissioned?

## Pages in this subdomain

* [Plant](../pages/plant.md)
* [Production Line](../pages/production_line.md)

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
