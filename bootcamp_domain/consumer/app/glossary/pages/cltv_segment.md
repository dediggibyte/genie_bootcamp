---
title: CLTV Segment
domain: Consumer
subdomain: Customer Identity
synonyms:
  - customer lifetime value segment
  - CLV segment
  - value segment
  - customer segment
  - at risk
  - churned
  - high value customers
description: "The customer-lifetime-value segment of a shopper (high_value, mid_value, low_value, at_risk, churned) from shopper.cltv_segment; at_risk means no webshop order in the last 180 days."
owner: CRM Analytics Lead (role)
related_assets:
  - <catalog>.consumer.shopper
  - <catalog>.consumer.loyalty_account
  - <catalog>.consumer.dtc_order
  - <catalog>.consumer.dtc_sales_metrics
  - <catalog>.consumer.shopper_metrics
sources:
  - Fjällmark CRM segmentation model v3 (fictional)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: consumer.shopper.cltv_segment, consumer.loyalty_account.cltv_segment"
---

# CLTV Segment

## Definition

The **CLTV segment** classifies every shopper by expected lifetime value and recency. The
authoritative column is **`consumer.shopper.cltv_segment`**:

| Value | Meaning (snapshot at the data extract, 2026-10-15) |
|---|---|
| `high_value` | Bought in the last 180 days; top ~22 % of those shoppers by total webshop spend |
| `mid_value` | Bought in the last 180 days; next ~43 % by spend |
| `low_value` | Bought in the last 180 days; remaining ~35 % |
| `at_risk` | **No order in the last 180 days** (last purchase 181–365 days ago) — retention target |
| `churned` | No order for more than 365 days |

## Business rules

1. Use `shopper.cltv_segment` for shopper-level questions. `loyalty_account.cltv_segment` is a
   loyalty-system copy for members only and uses `lapsed` instead of `churned` — do not mix the two
   columns in one answer.
2. Segment values are lower-case snake_case; filter with the exact value (e.g. `'at_risk'`).
3. Recency is measured from `shopper.last_purchase_date` to the extract date 2026-10-15;
   "no order in the last 180 days" therefore means last purchase before 2026-04-18.
4. Segments are a **snapshot**; they are not historised, so "how many shoppers were at risk a year
   ago" cannot be answered from this column.
5. `shopper.lifecycle_status` follows the segment: churned shoppers are `inactive`, the others
   `active` (a few `opted_out`).
6. Analyse segments in aggregate — never list individual at-risk shoppers with contact details.

## How to calculate (SQL)

```sql
-- Shoppers and 12-month DTC net sales by CLTV segment (SEK market only, to stay in one currency)
SELECT s.cltv_segment,
       COUNT(DISTINCT s.shopper_id)                           AS shoppers,
       ROUND(SUM(o.subtotal_amount - o.discount_amount), 2)   AS net_merchandise_sek_12m
FROM consumer.shopper s
LEFT JOIN consumer.dtc_order o
       ON o.shopper_id = s.shopper_id
      AND lower(o.order_status) <> 'cancelled'
      AND o.order_date >= DATE'2025-10-01'
      AND o.currency_code = 'SEK'
WHERE s.country_code = 'SWE'
GROUP BY s.cltv_segment
ORDER BY shoppers DESC;
```

```sql
-- Recency per segment: days from last purchase to the extract date 2026-10-15
SELECT s.cltv_segment,
       COUNT(*)                                                      AS shoppers,
       MIN(datediff(DATE'2026-10-15', s.last_purchase_date))         AS min_days_since_purchase,
       MAX(datediff(DATE'2026-10-15', s.last_purchase_date))         AS max_days_since_purchase
FROM consumer.shopper s
GROUP BY s.cltv_segment
ORDER BY min_days_since_purchase;
```

Governed: `<catalog>.consumer.dtc_sales_metrics` (CLTV segment dimension).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Filtering `cltv_segment = 'At Risk'` | Values are lower-case snake_case: `'at_risk'`. |
| Using `loyalty_account.cltv_segment` for all shoppers | Only members have it, and its vocabulary differs (`lapsed`). |
| Treating `churned` and `at_risk` as the same | At risk can still be won back; churned are gone. |

## Example questions

* How many shoppers are at risk of churning, by market?
* What share of DTC sales comes from high-value shoppers?
* Are at-risk shoppers more often loyalty members or non-members?
