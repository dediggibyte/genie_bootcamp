---
title: Active Shopper
domain: Consumer
subdomain: Customer Identity
synonyms:
  - active customer
  - active consumer
  - active buyer
  - buying customer
  - active shoppers
  - aktiv kund
  - 12-month active
description: "A registered shopper who placed at least one non-cancelled webshop order in the 12 months up to the reporting date (2026-09-30). This behavioural definition differs from the CRM field shopper.lifecycle_status = 'active'."
owner: Head of DTC & CRM (role)
related_assets:
  - <catalog>.consumer.dtc_sales_metrics
  - <catalog>.consumer.shopper
  - <catalog>.consumer.dtc_order
  - <catalog>.consumer.shopper_metrics
sources:
  - Fjällmark DTC KPI handbook, "Customer base KPIs" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: consumer.shopper, consumer.dtc_order"
---

# Active Shopper

## Definition

> A shopper is **active** if they exist in `consumer.shopper` **and** placed **at least one
> non-cancelled** `consumer.dtc_order` with `order_date` in the **12 months** ending on the
> reporting date (default 2026-09-30: orders from 2025-10-01 onwards).
>
> **Active shoppers** = COUNT(DISTINCT `shopper_id`) meeting that rule.

For a calendar period (e.g. "active shoppers in Q2 2026") the window is that period instead of
12 months — always state the window.

## Business rules

1. **Behaviour beats status.** `shopper.lifecycle_status` (`active`, `inactive`, `opted_out`,
   `suspended`, `pending_verification`) is a CRM account status, not purchase activity. Use it only
   when the user explicitly asks for the CRM status.
2. Guest checkouts: about 0.5 % of orders carry a `shopper_id` that is not in `consumer.shopper`.
   They are orders, but not registered shoppers — they are not counted.
3. Exclude cancelled orders.
4. Market of a shopper = `shopper.country_code` (ISO alpha-3: SWE, NOR, DNK, FIN, DEU, NLD).
5. Opposite end: shoppers with no order in the last 180 days are in CLTV segment `at_risk`
   (see *CLTV Segment*).

## How to calculate (SQL)

```sql
-- 12-month active shoppers by country, as of 2026-09-30
SELECT s.country_code,
       COUNT(DISTINCT s.shopper_id) AS active_shoppers
FROM consumer.shopper s
JOIN consumer.dtc_order o ON o.shopper_id = s.shopper_id
WHERE lower(o.order_status) <> 'cancelled'
  AND o.order_date >= DATE'2025-10-01'
  AND o.order_date <  DATE'2026-10-01'
GROUP BY s.country_code
ORDER BY active_shoppers DESC;
```

Governed: `<catalog>.consumer.dtc_sales_metrics` (active shoppers = distinct shoppers with orders in
the selected period).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `COUNT(*) FROM shopper WHERE lifecycle_status = 'active'` | CRM status, not buying behaviour. |
| `COUNT(DISTINCT dtc_order.shopper_id)` over all time | Not "active" — no time window. |
| Counting via `shopper.last_purchase_date` only | Denormalised field; fine as a shortcut but orders are the source of truth (and cancelled orders may have updated it). |
| Listing active shoppers by name/e-mail | Personal data — answer in aggregate. |

## Example questions

* How many active shoppers do we have per market?
* How did the number of active shoppers change compared with a year ago?
* What share of active shoppers are loyalty members?
