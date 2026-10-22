# 📊 Nordhem Retail Group — KPI Methodology

> **🎯 Purpose:** the single definition of every KPI Nordhem reports. The Genie agent (gold tables and the metric view
> `gold.kpi_metrics`) and Genie One use the same formulas, so both give the same number.
> All formulas use `retail_bootcamp.gold`. All amounts are in EUR. The data's as-of date is **2026-09-30**.

### ⚡ At a glance

| 💶 Net Revenue | 📈 Gross Margin | 🛒 Online Conversion | ↩️ Return Rate | 📦 Stock-out Rate |
|---|---|---|---|---|
| **604,798.15 EUR** | **40.8 %** | **8.6 %** | **7.2 %** | **2.4 %** |

> ✅ If an answer for the full period differs from these values, the query is wrong.
>
> 🔐 These values are for **admins on the base data**. Non-admin users see only their regions and categories
> (see `2026-10-22-data-governance.md`), and notebook 05 adds 🎁 Services & Gifts sales, so their numbers differ by design.

---

## 1. 📏 Reporting conventions

| # | Rule |
|---|---|
| 1 | 💶 Money is rounded to **2 decimals**, percentages to **1 decimal**. Always state "EUR". |
| 2 | ➗ Percentages are **ratios of sums**, never averages of per-row or per-store percentages. |
| 3 | 🏷️ "Revenue", "sales" and "turnover" mean `fact_order_line.net_sales`, unless the user says "net revenue", "booked revenue" or "P&L". |
| 4 | 📅 Time comes from `dim_date` via `date_key`. Returns are dated by **return date**, shipments by ship or delivery date, finance by `month_date_key`. |
| 5 | 🕐 "Today" is **2026-09-30**. Don't use `current_date()`. |
| 6 | 📦 Orders with `order_status = 'Processing'` (recent online orders) are included unless "completed only" is asked. |

---

## 2. 🏆 The five headline KPIs (validated values)

| # | KPI | Formula | Validated value |
|---|---|---|---|
| 1 | 💶 **Net Revenue** | `SUM(fact_order_line.net_sales) − SUM(fact_returns.refund_amount)` | **604,798.15 EUR** (650,801.55 − 46,003.40) |
| 2 | 📈 **Gross Margin %** | `SUM(gross_profit) / SUM(net_sales) × 100` | **40.8 %** (40.84) |
| 3 | 🛒 **Online Conversion Rate %** | `COUNT_IF(ordered_flag) / COUNT(*) × 100` on `fact_web_session` | **8.6 %** (431 / 5,000) |
| 4 | ↩️ **Return Rate %** | `SUM(fact_returns.return_qty) / SUM(fact_order_line.quantity) × 100` | **7.2 %** (175 / 2,435 units) |
| 5 | 📦 **Stock-out Rate %** | `COUNT_IF(is_stock_out) / COUNT(*) × 100` on `fact_inventory_daily` | **2.4 %** (363 / 14,850) |

---

## 3. 📖 Full KPI dictionary

### 💰 Sales and margin (`fact_order_line`)
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

### ↩️ Net revenue and returns (`fact_returns` + `fact_order_line`)
| KPI | Formula | Notes |
|---|---|---|
| Refunds | `SUM(refund_amount)` | Dated by return date |
| Net Revenue | net sales − refunds | ⚠️ **Aggregate each fact separately at the same grain (e.g. brand, month), then subtract.** Never join returns to lines and sum `net_sales`, because that loses unreturned lines. |
| Return Rate % | returned units ÷ sold units × 100 | Same rule: aggregate separately, then divide |
| Return reason mix % | units per `return_reason` ÷ all returned units | |

### 🛒 Online (`fact_web_session`, `fact_shipment`)
| KPI | Formula | Notes |
|---|---|---|
| Sessions | `COUNT(*)` | Includes anonymous sessions (`customer_id IS NULL`) |
| Add-to-cart rate % | `COUNT_IF(added_to_cart_flag) / COUNT(*) × 100` | |
| Conversion Rate % | `COUNT_IF(ordered_flag) / COUNT(*) × 100` | Online only |
| Cart-to-order % | `COUNT_IF(ordered_flag) / COUNT_IF(added_to_cart_flag) × 100` | |
| On-time Delivery % | `COUNT_IF(is_on_time) / COUNT(is_on_time) × 100` | Delivered shipments only. Promise is 3 days |
| Average delivery days | `AVG(delivery_days)` | |

### 📦 Inventory (`fact_inventory_daily`) — ⚠️ semi-additive
| KPI | Formula | Notes |
|---|---|---|
| Stock on hand | `SUM(on_hand_qty)` for **one date** (latest = 20260930) | Never sum across dates |
| Average stock | `AVG(on_hand_qty)` per product and location over the period | |
| Stock-out Rate % | `COUNT_IF(is_stock_out) / COUNT(*) × 100` | Covers 2026-07-03 → 2026-09-30 only |
| Below reorder point | `COUNT_IF(available_qty <= reorder_point)` on the latest date | Replenishment signal |

### 💶 Finance (`fact_finance_monthly`) — general ledger, a separate world
| KPI | Formula | Notes |
|---|---|---|
| GL revenue | `SUM(revenue)` | ⚠️ **Never add to or compare with order-line net sales** |
| Operating profit | `SUM(operating_profit)` | revenue − cogs − operating_expenses |
| Operating margin % | `SUM(operating_profit) / SUM(revenue) × 100` | |
| Budget variance | `SUM(operating_profit) − SUM(budget_operating_profit)` | Negative = missed budget |
| Revenue vs budget % | `SUM(revenue) / SUM(budget_revenue) × 100` | |

### 👥 Customers (`dim_customer`)
| KPI | Formula | Notes |
|---|---|---|
| Active customers | `COUNT(DISTINCT customer_id)` in `fact_order_line` for the period | |
| Spend per customer | net sales ÷ active customers | |
| Segment mix | customers by `customer_segment` (VIP / New / Regular) | Segment is fixed at 2026-09-30 |

---

## 4. 🔗 Grain and join rules

| Fact | Grain | Join to |
|---|---|---|
| `fact_order_line` | one order line | dim_date, dim_customer, dim_product, dim_store, dim_promotion |
| `fact_returns` | one return | dim_date (return date), dim_customer, dim_product, dim_store; `order_item_id` → fact_order_line |
| `fact_web_session` | one web session | dim_date, dim_customer (nullable) |
| `fact_inventory_daily` | date × product × location | dim_date, dim_product, dim_store (WH01 reported as ON01) |
| `fact_shipment` | one online shipment | dim_date via ship/delivery date; `order_id` → fact_order_line |
| `fact_finance_monthly` | month × store | dim_date (first of month), dim_store |

---

## 5. 🚫 Common mistakes to avoid

| # | ❌ Don't | ✅ Do |
|---|---|---|
| 1 | Add `fact_finance_monthly.revenue` to `fact_order_line.net_sales` | Report GL and order-line figures separately |
| 2 | Sum `on_hand_qty` over several days | Use one date, or an average |
| 3 | Average store-level percentages | Divide the sums |
| 4 | Calculate a conversion rate for physical stores | Conversion is online only |
| 5 | Report Scandinavia East without saying it includes online | Say so, or filter `channel = 'Store'` (see `2026-10-21-regional-methodology.md`) |
| 6 | Use customer region for "sales by region" | Default to store region |
| 7 | Drop Faroe Islands customers (`region = 'Unassigned'`) | Show them as their own row |
| 8 | Mix the two Black Friday definitions | State which one you used (see `2026-10-21-promotions-and-discounts.md`) |

---

## 6. 📐 Metric view `retail_bootcamp.gold.kpi_metrics`

The metric view is built by `notebooks/2026-10-22-04-metric-view.py`. It uses exactly the formulas in §2, at a
**month × store** grain, and the notebook checks it against the validated values.

| Measure | Formula in the view | Format |
|---|---|---|
| 💶 `Net Revenue` | `SUM(net_sales) - SUM(refund_amount)` | EUR |
| `Net Sales` | `SUM(net_sales)` (default "revenue") | EUR |
| `Refunds` | `SUM(refund_amount)` | EUR |
| 📈 `Gross Margin Pct` | `SUM(gross_profit) / SUM(net_sales)` | % |
| 🛒 `Online Conversion Rate Pct` | `SUM(web_orders) / SUM(web_sessions)` | % |
| ↩️ `Return Rate Pct` | `SUM(returned_units) / SUM(units_sold)` | % |
| 📦 `Stock Out Rate Pct` | `SUM(stock_out_snapshots) / SUM(inv_snapshots)` | % |
| `Units Sold` | `SUM(units_sold)` | units |

**Dimensions:** Month, Year, Season, Store, Store Name, Channel, Country, Region (store region).

> ℹ️ Percentages in the view are stored as **0–1 ratios** and shown as % by the format. Multiply by 100 when you
> compare them with the numbers in §2.
>
> ℹ️ The view has no brand, product, customer or promotion dimension. For those questions, query
> `fact_order_line` with the formulas above.
>
> ⚖️ If this document and the metric view ever disagree, the validated values in §2 decide which one is right.
