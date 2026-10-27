---
title: Average Order Value
domain: Consumer
subdomain: Direct Sales
synonyms:
  - AOV
  - average basket
  - basket size
  - average order size
  - average ticket
  - snittorder
  - genomsnittligt ordervärde
description: "Average net merchandise value per non-cancelled webshop order: Σ (subtotal − discount) ÷ number of orders, excl. VAT and shipping, per currency."
owner: Head of DTC & CRM (role)
related_assets:
  - <catalog>.consumer.dtc_sales_metrics
  - <catalog>.consumer.dtc_order
  - <catalog>.consumer.shopper
  - <catalog>.consumer.loyalty_tier
  - <catalog>.consumer.dtc_order_metrics
sources:
  - Fjällmark DTC KPI handbook, "Webshop KPIs" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: consumer.dtc_order"
---

# Average Order Value (AOV)

## Definition

> **AOV** = Σ (`dtc_order.subtotal_amount` − `dtc_order.discount_amount`) ÷ COUNT(DISTINCT
> `dtc_order_id`) over **non-cancelled** orders, **per currency** (or in EUR after conversion).

AOV is measured on **net merchandise value excl. VAT and shipping**, so that it is comparable
across markets with different VAT rates and free-shipping thresholds.

## Business rules

1. Compute AOV per `currency_code` (SEK, NOK, DKK, EUR) or convert to EUR first — an AOV over mixed
   currencies is meaningless.
2. Exclude cancelled orders (see *DTC Order Status*).
3. It is a **ratio of sums**: Σ value ÷ Σ orders — never average monthly or segment AOVs.
4. By loyalty tier: use the shopper's current tier — `dtc_order.shopper_id` → `shopper.loyalty_tier_id`
   → `loyalty_tier.tier_name`; shoppers without a tier are **Non-member** (see *Loyalty Tier*).
5. Known pattern: Gold and Platinum members have about **2.6×** the AOV of registered non-members on
   this page's basis (net merchandise value, EUR: ≈ 57.5 vs 22.5 EUR; ≈ 2.5× if guest checkouts are
   counted as non-members). On order value incl. VAT and shipping the ratio is about 2.4×.

## How to calculate (SQL)

```sql
-- AOV by currency and loyalty tier (current tier of the shopper; no tier = Non-member)
SELECT o.currency_code,
       coalesce(t.tier_name, 'Non-member')                                    AS loyalty_tier,
       COUNT(DISTINCT o.dtc_order_id)                                         AS orders,
       ROUND(SUM(o.subtotal_amount - o.discount_amount)
             / COUNT(DISTINCT o.dtc_order_id), 2)                             AS aov_local
FROM consumer.dtc_order o
LEFT JOIN consumer.shopper      s ON s.shopper_id      = o.shopper_id
LEFT JOIN consumer.loyalty_tier t ON t.loyalty_tier_id = s.loyalty_tier_id
WHERE lower(o.order_status) <> 'cancelled'
GROUP BY ALL
ORDER BY o.currency_code, loyalty_tier;
```

Governed: `<catalog>.consumer.dtc_sales_metrics` (AOV measure, loyalty tier and currency dimensions).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `AVG(order_total_amount)` | Includes VAT and shipping (the industry view `dtc_order_metrics.avg_order_value` does this). |
| AOV across all markets in one number | Mixes SEK with EUR. |
| `AVG(line_net_amount)` | Average *line* value, not order value. |
| Average of monthly AOVs | Unweighted; use Σ value ÷ Σ orders. |

## Example questions

* What is the average order value of Gold and Platinum members compared with non-members?
* How did AOV in Germany develop in 2026?
* Which market has the highest AOV in EUR?
