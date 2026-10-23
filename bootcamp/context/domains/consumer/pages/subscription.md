---
title: Subscription
domain: Consumer
subdomain: Direct Sales
synonyms:
  - subscribe and save
  - auto-replenishment
  - subscription box
  - recurring order
  - active subscriptions
  - subscription churn
  - prenumeration
  - Abo
description: "A shopper's recurring webshop plan (granola box, oat-drink crates, Mjuk Care refills) that generates an order every cycle; counted as active when subscription_status = 'active'. Recurring value = net price per cycle in local currency."
owner: Head of DTC & CRM (role)
related_assets:
  - <catalog>.consumer.subscription
  - <catalog>.consumer.dtc_order
  - <catalog>.consumer.subscription_metrics
sources:
  - Fjällmark DTC KPI handbook, "Subscriptions" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: consumer.subscription"
---

# Subscription

## Definition

A **subscription** is a shopper's standing order for a SKU or box, delivered every cycle
(`frequency`: mostly `monthly`, also `bi_monthly`, `quarterly`, `bi_weekly`). Each cycle creates a
webshop order with `dtc_order.subscription_order_flag = true` and `dtc_order.subscription_id` set.

* **Active subscriptions** = subscriptions with `subscription_status = 'active'` at the reporting
  date. Other statuses: `paused`, `cancelled`, `pending`, `expired`.
* **Recurring value per cycle** = `net_price` (= `price` × (1 − `discount_rate`)) in the
  subscription's `currency_code`. **Monthly recurring value** = Σ over active subscriptions of
  `net_price` × cycles per month (`monthly` 1, `bi_monthly` ½, `quarterly` ⅓, `bi_weekly` 26/12,
  `weekly` 52/12).
* **Subscription churn (period)** = subscriptions with `cancellation_date` in the period ÷
  subscriptions active at the start of the period.

## Business rules

1. Amounts are local currency — group by `currency_code` or convert to EUR.
2. A paused subscription is not active (no orders while paused, `pause_start_date` –
   `pause_end_date`), but it is not churned either.
3. Cancellation reasons are in `cancellation_reason` (`price_too_high`,
   `product_dissatisfaction`, `found_alternative`, `no_longer_needed`, `financial_hardship`,
   `other`).
4. Subscription orders are part of DTC GMV and Net Revenue — do not add them again.

## How to calculate (SQL)

```sql
-- Subscriptions by type and currency, with the monthly recurring value of active plans
-- (net price per cycle converted to a monthly equivalent)
SELECT sub.subscription_type,
       sub.currency_code,
       COUNT(*)                                                                    AS subscriptions,
       SUM(CASE WHEN lower(sub.subscription_status) = 'active' THEN 1 ELSE 0 END)  AS active_subscriptions,
       ROUND(SUM(CASE WHEN lower(sub.subscription_status) = 'active'
                      THEN sub.net_price * CASE lower(sub.frequency)
                                             WHEN 'weekly'     THEN 52 / 12
                                             WHEN 'bi_weekly'  THEN 26 / 12
                                             WHEN 'monthly'    THEN 1
                                             WHEN 'bi_monthly' THEN 0.5
                                             WHEN 'quarterly'  THEN 1 / 3
                                           END
                      ELSE 0 END), 2)                                               AS monthly_recurring_value_local
FROM consumer.subscription sub
GROUP BY ALL
ORDER BY sub.subscription_type, sub.currency_code;
```

```sql
-- Subscription cancellations per month and reason
SELECT date_trunc('MONTH', sub.cancellation_date) AS cancellation_month,
       sub.cancellation_reason,
       COUNT(*) AS cancellations
FROM consumer.subscription sub
WHERE sub.cancellation_date IS NOT NULL
GROUP BY ALL
ORDER BY cancellation_month, cancellations DESC;
```

Industry metric view: `<catalog>.consumer.subscription_metrics`.

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `COUNT(*) FROM subscription` as "subscribers" | Includes cancelled, expired and paused plans. |
| `SUM(price)` as recurring revenue | Before the subscription discount; use `net_price`. |
| Adding subscription order value to DTC GMV | Subscription orders are already in `dtc_order`. |

## Example questions

* How many active subscriptions do we have, by product type?
* What is the monthly recurring value of subscriptions in Sweden?
* Why do subscribers cancel?
