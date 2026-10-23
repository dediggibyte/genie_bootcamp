---
title: Batch Execution
domain: Manufacturing
subdomain: Batch Execution
subdomain_tag: Manufacturing/Batch Execution
description: "What was actually produced, how well, and when. Production orders (one SKU on one line, with schedule, quantities, OEE, yield, scrap, downtime, planned and actual cost), shop-floor confirmations with OEE components, electronic batch records and yield records with loss reasons."
owner: Head of Manufacturing Excellence (role)
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "manufacturing", subdomain "batch_execution" (tools/model/consumer_goods_v2_mvm.json)
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# Batch Execution (Manufacturing)

**What was actually produced, how well, and when.** Production orders (one SKU on one line, with schedule, quantities, OEE, yield, scrap, downtime, planned and actual cost), shop-floor confirmations with OEE components, electronic batch records and yield records with loss reasons. All plant performance KPIs come from here.

* Governed tag (UC Semantics subdomain): `Manufacturing/Batch Execution` — applied to the tables below by notebook `05_business_context`.
* Gold tables: `<catalog>.manufacturing.<table>`; industry model subdomain key `batch_execution`.

## Tables

| Table | Type | Primary key | What it holds |
|---|---|---|---|
| `production_order` | Transactional | `production_order_id` | Core transactional record representing a manufacturing production order issued to produce a specific SKU quantity at a facility. Captures order number, order type (PP01 standard, PP03 rework), SKU reference, plant, production line, scheduled start/finish dates, actual start/finish dates, order quantity, confirmed quantity, scrap quantity, order status (created, released, partially confirmed, technically complete, … |
| `batch_record` | Transactional | `batch_record_id` | Electronic batch manufacturing record (eBMR) capturing the complete GMP-compliant execution history for a production batch. Captures batch number, production order reference, SKU, batch size, manufacturing date, expiry date (FEFO), facility, production line, batch status (in-process, released, rejected, quarantine, recalled), GMP deviation flag, electronic signature records, yield percentage, and Veeva Vault … |
| `yield_record` | Transactional | `yield_record_id` | Yield tracking record capturing input vs. output quantities at each stage of the manufacturing process for a production order or batch. |
| `production_confirmation` | Transactional | `production_confirmation_id` | Shop floor execution and confirmation record capturing the complete lifecycle of each manufacturing operation within a production order — from assignment and scheduling through actual execution and final confirmation. Captures work order number, parent production order reference, operation number, work center, assigned operator, scheduled start/end, actual start/end, confirmation type (partial, final), confirmed … |

## Main joins (foreign keys inside the bootcamp scope)

* `production_order.cost_center_id` → `finance.cost_center.cost_center_id`
* `production_order.gl_account_id` → `finance.gl_account.gl_account_id`
* `production_order.manufacturing_bom_id` → `manufacturing.manufacturing_bom.manufacturing_bom_id`
* `production_order.manufacturing_facility_id` → `manufacturing.manufacturing_facility.manufacturing_facility_id`
* `production_order.production_line_id` → `manufacturing.production_line.production_line_id`
* `production_order.routing_id` → `manufacturing.routing.routing_id`
* `batch_record.cost_center_id` → `finance.cost_center.cost_center_id`
* `batch_record.manufacturing_bom_id` → `manufacturing.manufacturing_bom.manufacturing_bom_id`
* `batch_record.manufacturing_facility_id` → `manufacturing.manufacturing_facility.manufacturing_facility_id`
* `batch_record.production_line_id` → `manufacturing.production_line.production_line_id`
* `batch_record.production_order_id` → `manufacturing.production_order.production_order_id`
* … and 14 more (see the table constraints in Catalog Explorer)

## Questions this subdomain answers

* What was OEE by plant and month?
* Which line had the lowest yield in March 2026 and why?
* What share of production orders finished on time?

## Pages in this subdomain

* [OEE (Overall Equipment Effectiveness)](../pages/oee.md)
* [Yield](../pages/yield.md)
* [Scrap Rate](../pages/scrap_rate.md)
* [Downtime](../pages/downtime.md)
* [Schedule Adherence (On-time Completion)](../pages/schedule_adherence.md)
* [Production Order Status](../pages/production_order_status.md)
* [Production Cost Variance](../pages/production_cost_variance.md)

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
