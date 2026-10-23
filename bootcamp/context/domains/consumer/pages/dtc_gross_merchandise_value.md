---
title: DTC Gross Merchandise Value
domain: Consumer
subdomain: Direct Sales
synonyms:
  - GMV
  - gross merchandise value
  - webshop sales
  - DTC sales
  - online sales
  - e-commerce sales
  - order value
  - webshop revenue
description: "The value of merchandise ordered on the webshop before discounts, VAT, shipping and returns (Σ unit price × quantity ordered of non-cancelled orders), in the market's local currency. An operational DTC KPI — not Fjällmark's revenue."
owner: Head of DTC & CRM (role)
related_assets:
  - <catalog>.consumer.dtc_sales_metrics
  - <catalog>.consumer.dtc_order_line
  - <catalog>.consumer.dtc_order
  - <catalog>.consumer.address
  - <catalog>.consumer.dtc_order_metrics
  - <catalog>.finance.net_revenue_metrics
sources:
  - Fjällmark DTC KPI handbook, "Webshop KPIs" (fictional policy document)
  - bootcamp/context/domains/finance/pages/net_revenue.md
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: consumer.dtc_order, consumer.dtc_order_line"
---

# DTC Gross Merchandise Value (GMV)

## Definition

> **GMV** = Σ `dtc_order_line.line_subtotal` (= `unit_price` × `quantity_ordered`, **excl. VAT**,
> **before** line/order discounts, shipping and returns) of **non-cancelled** webshop orders, in the
> order's **local currency** (`currency_code`).

The webshop amount family, from biggest to smallest (per order, local currency):

| Amount | Column(s) | Contains |
|---|---|---|
| **Order value incl. VAT** ("what the customer paid") | `dtc_order.order_total_amount` | subtotal − discount + shipping + VAT |
| **GMV** | `dtc_order.subtotal_amount` = Σ `dtc_order_line.line_subtotal` | merchandise at list price, excl. VAT |
| **DTC net sales** | Σ `dtc_order_line.line_net_amount` (= subtotal − discounts) | merchandise after discounts, excl. VAT, before returns |
| *Finance DTC Net Revenue* | GL accounts 3010 − 3050, EUR | net sales − returns, in EUR — the official number |

## Business rules

1. **Local currency.** Always group by `currency_code` (SEK, NOK, DKK, EUR) or convert to EUR with
   the finance rate (see *Group Currency & FX*). Never add markets without converting.
2. **Exclude cancelled orders** (see *DTC Order Status*). Returns do **not** reduce GMV; they reduce
   Net Revenue.
3. Order month = `date_trunc('MONTH', dtc_order.order_date)` (order placement time, local market time —
   the timestamps carry no time zone).
4. **Market = the ship-to country** of the order: `dtc_order.ship_to_address_id` → `consumer.address.country_code`
   (ISO alpha-3: SWE, NOR, DNK, FIN, DEU, NLD). For registered shoppers this equals `shopper.country_code`, so
   `coalesce(address.country_code, shopper.country_code)` with LEFT JOINs is the robust form. Guest checkouts
   have neither (no ship-to address in the extract, no shopper profile) — show them as a separate
   "Unknown (guest)" bucket. Market is **not** the company code or the currency: DE01 / EUR covers both
   Germany and the Netherlands, and EUR also covers Finland.
5. When someone asks for "webshop revenue" or "online sales", give GMV or DTC net sales **and** say that
   the official revenue is Finance *Net Revenue*; DTC Net Revenue is typically 24–30 % below the
   webshop order total (VAT, shipping, returns, not-yet-shipped orders).

## How to calculate (SQL)

```sql
-- DTC GMV and DTC net sales by month and currency (local currency)
SELECT date_trunc('MONTH', o.order_date)          AS order_month,
       o.currency_code,
       COUNT(DISTINCT o.dtc_order_id)             AS orders,
       ROUND(SUM(l.line_subtotal), 2)             AS gmv_local,
       ROUND(SUM(l.line_net_amount), 2)           AS dtc_net_sales_local
FROM consumer.dtc_order o
JOIN consumer.dtc_order_line l ON l.dtc_order_id = o.dtc_order_id
WHERE lower(o.order_status) <> 'cancelled'
GROUP BY ALL
ORDER BY order_month, o.currency_code;
```

```sql
-- DTC GMV by market (ship-to country) and currency, September 2026
SELECT coalesce(a.country_code, sh.country_code, 'Unknown (guest)') AS market,
       o.currency_code,
       COUNT(DISTINCT o.dtc_order_id)                               AS orders,
       ROUND(SUM(l.line_subtotal), 2)                               AS gmv_local
FROM consumer.dtc_order o
JOIN consumer.dtc_order_line l ON l.dtc_order_id = o.dtc_order_id
LEFT JOIN consumer.address   a  ON a.address_id  = o.ship_to_address_id
LEFT JOIN consumer.shopper   sh ON sh.shopper_id = o.shopper_id
WHERE lower(o.order_status) <> 'cancelled'
  AND o.order_date >= DATE'2026-09-01' AND o.order_date < DATE'2026-10-01'
GROUP BY ALL
ORDER BY market, o.currency_code;
```

Governed: `<catalog>.consumer.dtc_sales_metrics` (measures for GMV and DTC net sales in local
currency, with currency as a dimension). The industry view `<catalog>.consumer.dtc_order_metrics`
names `SUM(order_total_amount)` "gross_merchandise_value" — that figure **includes VAT and
shipping**; do not present it as GMV or revenue.

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `SUM(order_total_amount)` called "sales" or "GMV" | Includes VAT (19–25 %) and shipping fees. |
| Summing all markets in one number without FX | SEK/NOK/DKK amounts are ~10× EUR amounts. |
| "Market" = company code or currency | DE01 / EUR merges Germany and the Netherlands (and EUR adds Finland); use the ship-to country. |
| Including cancelled orders | Cancelled orders never shipped. |
| Comparing GMV with finance revenue and calling the gap an error | They are different measures by design (see table above). |

## Example questions

* What was DTC GMV by market in September 2026?
* How did webshop sales grow year over year in Sweden?
* Why is the webshop's sales figure higher than finance's DTC revenue?
