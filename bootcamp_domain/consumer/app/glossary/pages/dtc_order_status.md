---
title: DTC Order Status
domain: Consumer
subdomain: Direct Sales
synonyms:
  - order status
  - cancelled orders
  - cancellations
  - open orders
  - delivered orders
  - returned orders
  - order lifecycle
  - orderstatus
description: "The lifecycle state of a webshop order (pending, confirmed, processing, shipped, delivered, returned, cancelled) and which states count as sales: everything except cancelled."
owner: Head of DTC & CRM (role)
related_assets:
  - <catalog>.consumer.dtc_order
  - <catalog>.consumer.dtc_order_line
  - <catalog>.consumer.dtc_sales_metrics
  - <catalog>.consumer.dtc_order_metrics
sources:
  - Fjällmark webshop order management process description (fictional)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: consumer.dtc_order.order_status, fulfillment_status, payment_status"
---

# DTC Order Status

## Definition

`consumer.dtc_order.order_status` tracks a webshop order from checkout to delivery:

| `order_status` | Meaning | Counts as a sale? |
|---|---|---|
| `pending` | Placed, payment authorised, not yet confirmed | yes (open order) |
| `confirmed` | Confirmed by order management | yes (open order) |
| `processing` | Being picked and packed at the distribution centre | yes (open order) |
| `shipped` | Handed to the carrier | yes |
| `delivered` | Delivered to the consumer (lines may still be returned later) | yes |
| `returned` | Delivered, and **all** lines were sent back | yes for GMV; returns reduce Net Revenue |
| `cancelled` | Cancelled before shipment (by the consumer or out of stock) — about 1.7 % of orders | **no** |

Because the data ends on 2026-09-30, only orders from the last days of September are still
`pending`, `confirmed`, `processing` or `shipped`.

## Business rules

1. **Sales, GMV, AOV, active shoppers (webshop view):** all orders **except `cancelled`**.
   **Finance** recognises DTC revenue only for orders that left the warehouse — `shipped`, `delivered`,
   `returned` — in the month of `order_date`; fully or partly returned lines are booked to returns
   (GL 3050) in the same month. Open orders (`pending`, `confirmed`, `processing`) are in GMV but not
   yet in Net Revenue.
2. **Completed orders** (for delivery KPIs): `delivered` and `returned`.
3. **Partial returns** keep the status `delivered`; find them with `dtc_order.return_flag = true`
   or line-level `dtc_order_line.is_returned = true` (see *Return Rate*).
4. Related statuses: `fulfillment_status` (`unfulfilled`, `partially_fulfilled`, `fulfilled`,
   `cancelled`) and `payment_status` (`authorized`, `captured`, `refunded`, ...). Cancelled and fully
   returned orders have `payment_status = 'refunded'`.
5. Status values are lower-case; compare with `lower(order_status)` to be safe.

## How to calculate (SQL)

```sql
-- Orders by status and month
SELECT date_trunc('MONTH', o.order_date) AS order_month,
       lower(o.order_status)             AS order_status,
       COUNT(*)                          AS orders
FROM consumer.dtc_order o
GROUP BY ALL
ORDER BY order_month, order_status;
```

```sql
-- Cancellation rate by market currency
SELECT o.currency_code,
       ROUND(100 * AVG(CASE WHEN lower(o.order_status) = 'cancelled' THEN 1 ELSE 0 END), 2) AS cancellation_rate_pct
FROM consumer.dtc_order o
GROUP BY o.currency_code
ORDER BY cancellation_rate_pct DESC;
```

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Counting all orders as sales | Includes cancelled orders. |
| `order_status = 'returned'` as "orders with returns" | Only fully returned orders; partial returns are `delivered` with `return_flag = true`. |
| Filtering `order_status = 'completed'` | There is no such value; use `delivered` / `returned`. |

## Example questions

* How many webshop orders were cancelled last quarter, and what is the cancellation rate?
* How many orders are still open at the end of September 2026?
* What share of delivered orders had at least one returned item?
