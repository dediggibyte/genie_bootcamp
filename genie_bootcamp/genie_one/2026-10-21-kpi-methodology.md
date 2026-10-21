# Nordhem Retail Group — KPI Methodology

> The single definition of every KPI Nordhem reports. The same formulas are used by the Genie agent (gold tables
> and metric views) and by Genie One, so both give the same number. All formulas use `retail_bootcamp.gold`. All
> amounts are in EUR. The data's as-of date is 2026-09-30.

---

## 1. Reporting conventions

1. Money is rounded to **2 decimals**, percentages to **1 decimal**. Always state "EUR".
2. Percentages are **ratios of sums**, never averages of per-row or per-store percentages.
3. "Revenue", "sales" and "turnover" mean `fact_order_line.net_sales`, unless the user says "net revenue",
   "booked revenue" or "P&L".
4. Time is taken from `dim_date` via `date_key`. Returns are dated by **return date**, shipments by ship or delivery date and
   finance by `month_date_key`.
5. "Today" is **2026-09-30**. Don't use `current_date()`.
6. Orders with `order_status = 'Processing'` (recent online orders) are included unless "completed only" is asked.

## 2. The five headline KPIs (validated values)

| # | KPI | Formula | Validated value |
|---|---|---|---|
| 1 | **Net Revenue** | `SUM(fact_order_line.net_sales) − SUM(fact_returns.refund_amount)` | **604,798.15 EUR** (650,801.55 − 46,003.40) |
| 2 | **Gross Margin %** | `SUM(gross_profit) / SUM(net_sales) × 100` | **40.8 %** (40.84) |
| 3 | **Online Conversion Rate %** | `COUNT_IF(ordered_flag) / COUNT(*) × 100` on fact_web_session | **8.6 %** (431 / 5,000) |
| 4 | **Return Rate %** | `SUM(fact_returns.return_qty) / SUM(fact_order_line.quantity) × 100` | **7.2 %** (175 / 2,435 units) |
| 5 | **Stock-out Rate %** | `COUNT_IF(is_stock_out) / COUNT(*) × 100` on fact_inventory_daily | **2.4 %** (363 / 14,850) |

If an answer for the full period differs from these values, the query is wrong.

## 3. Full KPI dictionary

### Sales and margin (fact_order_line)
| KPI | Formula | Notes |
|---|---|---|
| Gross sales | `SUM(gross_sales)` | Before discount |
| Net sales | `SUM(net_sales)` | Default "revenue" |
| Discount amount | `SUM(discount_amount)` | All discounts are promotions |
| Discount rate % | `SUM(discount_amount) / SUM(gross_sales) × 100` | ≈ 4.4 % overall |
| COGS | `SUM(cogs)` | Standard cost × quantity |
| Gross profit | `SUM(gross_profit)` | "Profit" on order data |
| Gross Margin % | `SUM(gross_profit) / SUM(net_sales) × 100` | |
| Units sold | `SUM(quantity)` | |
| Orders | `COUNT(DISTINCT order_id)` | 1,324 in total |
| Average Order Value | `SUM(net_sales) / COUNT(DISTINCT order_id)` | ≈ 491.54 EUR overall |
| Units per order | `SUM(quantity) / COUNT(DISTINCT order_id)` | |
| Promotion penetration % | `COUNT_IF(promotion_id <> 'PR00') / COUNT(*) × 100` | Lines on promotion |
| Net sales per store | net sales ÷ `COUNT(DISTINCT store_id)` | Use for regional comparisons, stores only |

### Net revenue and returns (fact_returns + fact_order_line)
| KPI | Formula | Notes |
|---|---|---|
| Refunds | `SUM(refund_amount)` | Dated by return date |
| Net Revenue | net sales − refunds | **Aggregate each fact separately at the same grain (e.g. brand, month), then subtract.** Never join returns to lines and sum `net_sales`, because that loses unreturned lines. |
| Return Rate % | returned units ÷ sold units × 100 | Same rule: aggregate separately, then divide |
| Return reason mix % | units per `return_reason` ÷ all returned units | |

### Online (fact_web_session, fact_shipment)
| KPI | Formula | Notes |
|---|---|---|
| Sessions | `COUNT(*)` | Includes anonymous sessions (`customer_id IS NULL`) |
| Add-to-cart rate % | `COUNT_IF(added_to_cart_flag) / COUNT(*) × 100` | |
| Conversion Rate % | `COUNT_IF(ordered_flag) / COUNT(*) × 100` | Online only |
| Cart-to-order % | `COUNT_IF(ordered_flag) / COUNT_IF(added_to_cart_flag) × 100` | |
| On-time Delivery % | `COUNT_IF(is_on_time) / COUNT(is_on_time) × 100` | Delivered shipments only. Promise is 3 days |
| Average delivery days | `AVG(delivery_days)` | |

### Inventory (fact_inventory_daily) — **semi-additive**
| KPI | Formula | Notes |
|---|---|---|
| Stock on hand | `SUM(on_hand_qty)` for **one date** (latest = 20260930) | Never sum across dates |
| Average stock | `AVG(on_hand_qty)` per product and location over the period | |
| Stock-out Rate % | `COUNT_IF(is_stock_out) / COUNT(*) × 100` | Covers 2026-07-03 to 2026-09-30 only |
| Below reorder point | `COUNT_IF(available_qty <= reorder_point)` on the latest date | Replenishment signal |

### Finance (fact_finance_monthly) — general ledger, separate world
| KPI | Formula | Notes |
|---|---|---|
| GL revenue | `SUM(revenue)` | **Never add to or compare with order-line net sales** |
| Operating profit | `SUM(operating_profit)` | revenue − cogs − operating_expenses |
| Operating margin % | `SUM(operating_profit) / SUM(revenue) × 100` | |
| Budget variance | `SUM(operating_profit) − SUM(budget_operating_profit)` | Negative = missed budget |
| Revenue vs budget % | `SUM(revenue) / SUM(budget_revenue) × 100` | |

### Customers (dim_customer)
| KPI | Formula | Notes |
|---|---|---|
| Active customers | `COUNT(DISTINCT customer_id)` in fact_order_line for the period | |
| Spend per customer | net sales ÷ active customers | |
| Segment mix | customers by `customer_segment` (VIP / New / Regular) | Segment is fixed at 2026-09-30 |

## 4. Grain and join rules

| Fact | Grain | Join to |
|---|---|---|
| fact_order_line | one order line | dim_date, dim_customer, dim_product, dim_store, dim_promotion |
| fact_returns | one return | dim_date (return date), dim_customer, dim_product, dim_store; `order_item_id` → fact_order_line |
| fact_web_session | one web session | dim_date, dim_customer (nullable) |
| fact_inventory_daily | date × product × location | dim_date, dim_product, dim_store (WH01 reported as ON01) |
| fact_shipment | one online shipment | dim_date via ship/delivery date; `order_id` → fact_order_line |
| fact_finance_monthly | month × store | dim_date (first of month), dim_store |

## 5. Common mistakes to avoid
1. Adding `fact_finance_monthly.revenue` to `fact_order_line.net_sales`.
2. Summing `on_hand_qty` over several days.
3. Averaging store-level percentages instead of dividing sums.
4. Calculating a conversion rate for physical stores.
5. Reporting Scandinavia East without saying it includes online. See `2026-10-21-regional-methodology.md`.
6. Using customer region for "sales by region". The default is store region.
7. Dropping Faroe Islands customers (`region = 'Unassigned'`).
8. Mixing the two Black Friday definitions. See `2026-10-21-promotions-and-discounts.md`.

## 6. Metric view alignment
If the Genie agent uses a Unity Catalog **metric view** on top of `fact_order_line`, its measures must use exactly
the formulas above (e.g. `gross_margin_pct = SUM(gross_profit) / SUM(net_sales) * 100`). Its dimensions should be named after the
gold columns (`brand`, `category`, `region`, `channel`, `promotion_name`, `season`, `year`, `month_name`).
When this document and a metric view disagree, the validated values in §2 decide which one is right.
