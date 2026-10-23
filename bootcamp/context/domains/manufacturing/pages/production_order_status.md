---
title: Production Order Status
domain: Manufacturing
subdomain: Batch Execution
synonyms:
  - order status
  - production status
  - released orders
  - completed production orders
  - TECO
  - CNF
  - SAP order status
description: "The SAP-style lifecycle status of a production order: CRTD created, REL released, PCNF partially confirmed, CNF confirmed, DLV delivered, TECO technically complete, CLSD closed. Completed = CNF, DLV, TECO or CLSD."
owner: Head of Production Planning (role)
related_assets:
  - <catalog>.manufacturing.production_order
  - <catalog>.manufacturing.production_confirmation
  - <catalog>.manufacturing.planned_order
  - <catalog>.manufacturing.production_performance_metrics
  - <catalog>.manufacturing.production_order_metrics
sources:
  - SAP S/4HANA PP system status reference (standard SAP status codes)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: manufacturing.production_order.order_status"
---

# Production Order Status

## Definition

`manufacturing.production_order.order_status` uses SAP system status codes:

| `order_status` | Name | Meaning | Group |
|---|---|---|---|
| `CRTD` | Created | Order created from a planned order, not yet released | Open – not started |
| `REL` | Released | Released to the shop floor, production can start | Open – in progress |
| `PCNF` | Partially confirmed | Some operations/quantities confirmed | Open – in progress |
| `CNF` | Confirmed | All operations confirmed | **Completed** |
| `DLV` | Delivered | Goods receipt of the finished product posted | **Completed** |
| `TECO` | Technically complete | Closed for logistics; no further production | **Completed** |
| `CLSD` | Closed | Closed for logistics and costing (settled) | **Completed** |

Order types (`order_type`): `PP01` standard production, `PP03` rework, `PP05`, `PP10`, `PP20` other
order types.

## Business rules

1. **Completed orders** = `order_status IN ('CNF', 'DLV', 'TECO', 'CLSD')`. Most KPIs (OEE, yield,
   schedule adherence, cost variance) use completed orders; actual finish is in
   `actual_finish_timestamp`.
2. **Open / WIP orders** = `CRTD`, `REL`, `PCNF`. In the 2026-09-30 snapshot every production order is
   already completed (`CNF`, `DLV`, `TECO` or `CLSD` — older orders mostly `CLSD`), so "open production
   orders" correctly returns zero.
3. Codes are upper case; compare with `upper(order_status)` to be safe.
4. Planned orders (`manufacturing.planned_order`) have their own statuses (`DRAFT`, `FIRMED`,
   `RELEASED`, `CONVERTED`, ...); a converted planned order points to its production order via
   `converted_production_order_id`.

## How to calculate (SQL)

```sql
-- Production orders by status group and plant
SELECT f.erp_plant_code AS plant,
       CASE WHEN upper(po.order_status) IN ('CNF', 'DLV', 'TECO', 'CLSD') THEN 'completed'
            WHEN upper(po.order_status) IN ('REL', 'PCNF')               THEN 'in progress'
            WHEN upper(po.order_status) = 'CRTD'                         THEN 'created'
            ELSE 'other' END AS status_group,
       COUNT(*)         AS orders
FROM manufacturing.production_order po
JOIN manufacturing.manufacturing_facility f
  ON f.manufacturing_facility_id = po.manufacturing_facility_id
GROUP BY ALL
ORDER BY plant, status_group;
```

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `order_status = 'Completed'` | No such value; use the SAP codes. |
| Treating `TECO` as cancelled | TECO means technically complete — production is finished (possibly short). |
| Counting only `CLSD` as completed | Recent orders are confirmed/delivered but not yet settled. |

## Example questions

* How many production orders are still open per plant?
* How many orders were completed in September 2026?
* Which orders are released but not yet confirmed?
