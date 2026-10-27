---
title: Return Rate
domain: Consumer
subdomain: Direct Sales
synonyms:
  - returns
  - return %
  - returned orders
  - returned items
  - refund rate
  - returrate
  - Retourenquote
description: "Share of webshop merchandise that consumers send back: returned order-line net value ÷ total order-line net value of non-cancelled orders (value-based); about 5–6 % of DTC order lines are returned."
owner: Head of DTC & CRM (role)
related_assets:
  - <catalog>.consumer.dtc_sales_metrics
  - <catalog>.consumer.dtc_order_line
  - <catalog>.consumer.dtc_order
  - <catalog>.consumer.dtc_order_line_metrics
  - <catalog>.finance.journal_entry_line
sources:
  - Fjällmark DTC KPI handbook, "Returns" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: consumer.dtc_order_line.is_returned, consumer.dtc_order.return_flag"
---

# Return Rate

## Definition

> **Return rate (value)** = Σ `line_net_amount` of order lines with `is_returned = true` ÷
> Σ `line_net_amount` of all lines, non-cancelled orders, per currency or in EUR.
>
> **Return rate (lines)** = lines with `is_returned = true` ÷ all lines.

The **value-based line rate is the default**. About **5–6 %** of DTC order lines (and of their value)
are returned; about 10 % of orders have at least one returned line.

## Business rules

1. Use the **line** flag `dtc_order_line.is_returned` (which SKU came back) and its reason
   `dtc_order_line.return_reason_code`. The **order** flag `dtc_order.return_flag` is true when *any*
   line of the order was returned — an order-level return rate is therefore much higher than the line
   rate; only use it when the user asks "share of orders with a return".
2. Exclude cancelled orders from numerator and denominator.
3. Returns reduce finance Net Revenue (GL account 3050 *Sales returns - DTC*); they do **not** reduce GMV.
4. By product: the order line itself carries `brand_code` (BJORKO, KALLKALLA, MJUKCARE),
   `product_category_code` and `product_name` — no join needed.

## How to calculate (SQL)

```sql
-- Value-based (in EUR, so markets can be added) and line-based return rate by brand
WITH fx AS (   -- finance monthly rate per company code (see Group Currency & FX)
  SELECT jel.company_code_id, je.fiscal_year, je.fiscal_period, AVG(jel.exchange_rate) AS eur_rate
  FROM finance.journal_entry_line jel
  JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
  WHERE je.posting_status = 'posted'
  GROUP BY ALL
)
SELECT l.brand_code                                                                      AS brand,
       COUNT(*)                                                                          AS lines,
       ROUND(100 * AVG(CASE WHEN l.is_returned THEN 1 ELSE 0 END), 2)                    AS line_return_rate_pct,
       ROUND(100 * SUM(CASE WHEN l.is_returned THEN l.line_net_amount * fx.eur_rate ELSE 0 END)
                 / SUM(l.line_net_amount * fx.eur_rate), 2)                              AS value_return_rate_pct
FROM consumer.dtc_order_line l
JOIN consumer.dtc_order o ON o.dtc_order_id = l.dtc_order_id
JOIN fx                   ON fx.company_code_id = o.company_code_id
                         AND fx.fiscal_year     = year(o.order_date)
                         AND fx.fiscal_period   = month(o.order_date)
WHERE lower(o.order_status) <> 'cancelled'
GROUP BY l.brand_code
ORDER BY value_return_rate_pct DESC;
```

For a single market you can skip the conversion: add `dtc_order_line.currency_code` to the SELECT and
GROUP BY and use `dtc_order_line.line_net_amount` directly — the ratio is then computed within one currency.

Governed: `<catalog>.consumer.dtc_sales_metrics` (return rate measure).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `AVG(CASE WHEN dtc_order.return_flag ...)` called "return rate" | Order-level: one returned line marks the whole order. |
| Value rate over mixed currencies without grouping | Ratio is fine only if numerator and denominator are in the same currency per group; group by currency or convert. |
| Using `quantity_cancelled` as returns | Cancelled units never shipped; returns are shipped and sent back. |

## Example questions

* What is the DTC return rate by brand?
* Which product category has the highest return rate and why (reason codes)?
* How did the return rate develop month by month in 2026?
