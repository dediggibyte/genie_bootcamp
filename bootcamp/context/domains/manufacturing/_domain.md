---
title: Manufacturing
domain: Manufacturing
domain_tag: Manufacturing
subtitle: Plants, lines, production orders, batches, yield and OEE
description: Owns production planning, scheduling and execution in Fjällmark's four plants — plant and line master data, BOMs and routings, planned and production orders, confirmations, electronic batch records and yield tracking.
business_owner: Head of Manufacturing Excellence (role)
technical_owner: Operations Data Product Team (role)
schema: <catalog>.manufacturing
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "manufacturing" (tools/model/consumer_goods_v2_mvm.json)
  - bootcamp/context/company_profile.md
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# Manufacturing

**Industry model description:** *"Owns production planning, scheduling, and execution across
manufacturing facilities. Manages production orders, batch records, work orders, MES integration
(Siemens Opcenter), line performance (OEE), yield tracking, MRP runs, GMP compliance events,
changeover management, and shop floor data collection aligned with ISO 22716 standards."*
(Division: operations. References: ISO 22716, ISO 9001, MES.)

## Purpose at Fjällmark

Manufacturing answers **how well our plants run**: how much we made, how efficiently (OEE), how
much good output we got from the input (yield), how much we threw away (scrap), how long lines
stood still (downtime) and whether we finished orders on time. Plants: Lund (SE-LUN), Norrköping
(SE-NKP), Tampere (FI-TMP, since April 2025) and Poznań (PL-POZ).

| | |
|---|---|
| Business owner | Head of Manufacturing Excellence (role) |
| Technical owner | Operations Data Product Team (role) |
| Gold schema | `<catalog>.manufacturing` — governed tag `Manufacturing` |

## Subdomains

| Subdomain (tag) | What it covers | Tables |
|---|---|---|
| Asset Configuration (`Manufacturing/Asset Configuration`) | Plants, lines, work centres, equipment | `manufacturing_facility`, `production_line`, `work_center`, `equipment` |
| Recipe Planning (`Manufacturing/Recipe Planning`) | What to make and how: BOMs, routings, planned orders | `manufacturing_bom`, `routing`, `planned_order` |
| Batch Execution (`Manufacturing/Batch Execution`) | What was made: production orders, confirmations, batches, yields | `production_order`, `production_confirmation`, `batch_record`, `yield_record` |

## Key tables

* `production_order` — one order to make a SKU on a line: `order_status`, `scheduled_start_date`,
  `scheduled_finish_date`, `actual_start_timestamp`, `actual_finish_timestamp`, `order_quantity`,
  `confirmed_quantity`, `scrap_quantity`, `yield_percentage`, `oee_percentage`, `downtime_minutes`,
  `planned_cost`, `actual_cost`, `manufacturing_facility_id`, `production_line_id`, `sku_id`.
* `yield_record` — input vs. output per order/batch: `input_quantity`, `output_quantity`,
  `scrap_quantity`, `actual_yield_percentage`, `theoretical_yield_percentage`,
  `yield_loss_reason_code`, `yield_variance_cost_impact`.
* `batch_record` — electronic batch record: `batch_status`, `manufacturing_date`, `yield_percentage`,
  `scrap_quantity`, `downtime_minutes`, `gmp_deviation_flag`.
* `production_confirmation` — shop-floor confirmations with OEE components
  (`oee_availability_percent`, `oee_performance_percent`, `oee_quality_percent`).
* `manufacturing_facility` / `production_line` — plant and line master data.

## Key metrics (Pages)

| Page | One-liner |
|---|---|
| [OEE](pages/oee.md) | Availability × Performance × Quality, in % |
| [Yield](pages/yield.md) | Good output ÷ input, in % |
| [Scrap Rate](pages/scrap_rate.md) | Scrapped quantity ÷ input quantity |
| [Downtime](pages/downtime.md) | Minutes a line was not producing during planned time |
| [Schedule Adherence](pages/schedule_adherence.md) | Share of production orders finished by the scheduled finish date |
| [Production Order Status](pages/production_order_status.md) | SAP-style lifecycle CRTD → REL → PCNF → CNF → DLV → TECO → CLSD |
| [Production Cost Variance](pages/production_cost_variance.md) | Actual − planned cost of production orders |
| [Plant](pages/plant.md) | The four manufacturing facilities and their codes |
| [Production Line](pages/production_line.md) | The 16 lines and how they are named |

Governed metric view: `<catalog>.manufacturing.production_performance_metrics` (OEE, yield %,
scrap rate, cost variance, on-time completion %, downtime — by plant, line, month, order status,
SKU/brand). Industry metric views: `<catalog>.manufacturing.production_order_metrics`,
`yield_record_metrics`, `batch_record_metrics`, `manufacturing_facility_metrics`,
`production_line_metrics`, `equipment_metrics`.

## Rules of thumb for Genie

1. Percentages (`oee_percentage`, `yield_percentage`) are stored as **0–100**, not 0–1.
2. Average OEE/yield across orders unless the user asks for a weighted figure — and say which.
3. Downtime exists at several grains (order, batch, confirmation): **never add them together**.
4. Tampere started in April 2025 — its early months are a ramp-up, not a performance problem.
5. Poznań line PL-POZ-L2 had an equipment malfunction in March 2026 (fixed 4 April 2026).

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
