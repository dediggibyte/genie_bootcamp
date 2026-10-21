# Nordhem Retail Group — Promotions, Discounts and Campaigns

> How promotions work, how discounts are calculated and how Nordhem measures promotion performance.
> **[DATA]** means you can check it in `retail_bootcamp.gold`. **[POLICY]** means a company rule that no table stores.
> All amounts are in EUR.

---

## 1. How a discount is recorded

**[DATA]**
- A promotion is attached to the **whole order** (`fact_order_line.promotion_id`). All lines of an order share it.
- **One promotion per order. Promotions never stack.**
- `promotion_id = 'PR00'` means **no promotion**. It is a real row in `dim_promotion`, so every line joins.
- Line formulas:
  - `gross_sales = quantity × unit_price` (unit price = list price incl. VAT)
  - `discount_amount = gross_sales × discount_pct / 100` (verified on every promoted line)
  - `net_sales = gross_sales − discount_amount`
  - `gross_profit = net_sales − cogs`, `cogs = quantity × unit_cost`
- There are no other price reductions: no manual markdowns, coupons or staff discounts. Every unpromoted line is sold at
  list price. **Discount = promotion discount.**
- Every promoted line falls inside its promotion's `start_date`–`end_date`.
- Inside a promotion window, about 60–85 % of order lines use the promotion. The rest pay full price, because the customer did not
  qualify or did not use the offer. Those orders are the **in-window control group**.

## 2. Promotion catalogue

**[DATA]** (`dim_promotion` plus the marketing campaign it belongs to)

| ID | Name | Type | Discount | Valid | Campaign (media, budget EUR) |
|---|---|---|---|---|---|
| PR00 | No promotion | None | 0 % | — | — |
| PR01 | Black Friday 2024 | Seasonal discount | 20 % | 2024-11-25 → 2024-12-02 | CMP01 Paid social + email, 45,000 (from 2024-11-18) |
| PR02 | Christmas Gift Deal 2024 | Seasonal discount | 10 % | 2024-12-03 → 2024-12-23 | CMP02 TV + display, 60,000 |
| PR03 | Summer Sale 2024 | Clearance | 15 % | 2024-06-17 → 2024-07-31 | CMP03 Email + search, 30,000 |
| PR04 | Summer Sale 2025 | Clearance | 15 % | 2025-06-16 → 2025-07-31 | CMP04 Email + search, 32,000 |
| PR05 | Black Friday 2025 | Seasonal discount | 25 % | 2025-11-24 → 2025-12-01 | CMP05 Paid social + email, 50,000 (from 2025-11-17) |
| PR06 | Christmas Gift Deal 2025 | Seasonal discount | 10 % | 2025-12-02 → 2025-12-23 | CMP06 TV + display, 65,000 |
| PR07 | Winter Outdoor Week | Category discount | 20 % | 2025-10-01 → 2025-10-31 | CMP07 Outdoor media, 20,000 |
| PR08 | Summer Sale 2026 | Clearance | 15 % | 2026-06-15 → 2026-07-31 | CMP08 Email + search, 34,000 |
| PR09 | Loyalty Spring Bonus | Loyalty | 5 % | 2025-03-01 → 2025-04-30 | none (no media budget) |

Campaign budgets are in the bronze table `mkt_campaigns_raw`, not in gold. Campaigns start up to 7 days before the
promotion: Black Friday campaigns start one week early as teaser media.

### Promotion types [POLICY definitions]

| Type | Intent | Typical depth | Who qualifies |
|---|---|---|---|
| **Seasonal discount** | Win the market's peak weeks (Black Week, Christmas) | 10–25 % | Everyone |
| **Clearance** | Clear seasonal stock before new ranges (summer) | 15 % | Everyone |
| **Category discount** | Push one category at its season start | 20 % | Products in the named category |
| **Loyalty** | Reward members and drive sign-ups | 5 % | Loyalty members |

### Known gaps between policy and data [DATA] — mention these when relevant
1. **PR07 "Winter Outdoor Week" was applied to every brand, not only Outdoor Apparel.** Of 31 promoted lines,
   Helly Hansen accounts for 4,782 EUR of 8,982 EUR net sales. Electrolux (3,355 EUR) and LEGO (845 EUR) also got 20 %.
   Treat this as a set-up error when you evaluate the category promotion.
2. **PR09 "Loyalty Spring Bonus" was also used by non-members.** 34 of 100 promoted lines belong to customers with
   `loyalty_tier = 'None'`.
3. **"Black Friday" has two definitions.** The Genie agent instructions use the calendar week **22–30 November**.
   The actual promotions run **2024-11-25 → 2024-12-02** and **2025-11-24 → 2025-12-01**. Use the promotion dates
   for promotion performance, and the calendar week for "Black Friday week" sales trends. State which one you used.

## 3. Measuring promotion performance

### 3.1 Core promotion KPIs

| KPI | Formula (fact_order_line) | Meaning |
|---|---|---|
| Promoted net sales | `SUM(net_sales) WHERE promotion_id <> 'PR00'` | Revenue on promoted lines |
| Discount cost | `SUM(discount_amount)` | Margin given away |
| Discount rate % | `SUM(discount_amount) / SUM(gross_sales) × 100` | Average depth across the scope |
| Promotion penetration % | `COUNT_IF(promotion_id <> 'PR00') / COUNT(*) × 100` (lines) | How promotion-dependent sales are |
| Promoted gross margin % | `SUM(gross_profit) / SUM(net_sales) × 100` on promoted lines | Margin after discount |
| Margin dilution (pp) | promoted GM % − unpromoted GM % for the same brand | Cost of the discount in margin points |
| Campaign efficiency | promoted net sales ÷ campaign budget | Sales per EUR of media |
| Total promotion cost | discount cost + campaign budget | Full investment |

### 3.2 Uplift (lift) — three accepted methods [POLICY]
Always say which method you used.
1. **Year over year (preferred for recurring events).** Compare net sales in the promotion window with the same
   promotion window one year earlier. Example: PR05 (2025) vs PR01 (2024).
2. **Pre-period baseline.** Compare the window with the same number of days ending 28 days before it.
   This overstates lift for Black Friday and Christmas, because those weeks are naturally high.
3. **In-window control.** Compare promoted with unpromoted orders in the same window, using AOV and units per order.
   No seasonality bias, but customers choose whether to use the offer.

### 3.3 Results so far [DATA]

| Promotion | Net sales (promoted lines) | Discount cost | Promoted GM % | Net sales ÷ media budget |
|---|---|---|---|---|
| PR01 Black Friday 2024 (20 %) | 13,213.60 | 3,303.40 | 30.1 % | 0.29 |
| PR02 Christmas 2024 (10 %) | 14,493.60 | 1,610.40 | 42.8 % | 0.24 |
| PR03 Summer Sale 2024 (15 %) | 22,267.45 | 3,929.55 | 34.1 % | 0.74 |
| PR04 Summer Sale 2025 (15 %) | 24,951.75 | 4,403.25 | 31.7 % | 0.78 |
| PR05 Black Friday 2025 (25 %) | 16,839.75 | 5,613.25 | **23.8 %** | 0.34 |
| PR06 Christmas 2025 (10 %) | 17,712.00 | 1,968.00 | 42.5 % | 0.27 |
| PR07 Winter Outdoor (20 %) | 8,982.40 | 2,245.60 | 35.2 % | 0.45 |
| PR08 Summer Sale 2026 (15 %) | 28,368.75 | 5,006.25 | 32.2 % | 0.83 |
| PR09 Loyalty Spring (5 %) | 32,941.25 | 1,733.75 | 39.0 % | — |
| **All promoted** | **179,770.55** | **29,813.45** | **34.7 %** | |
| Unpromoted (PR00) | 471,031.00 | 0 | 43.2 % | |

Promoted lines make up 32 % of order lines and 27.6 % of net sales.

**Black Friday 2025 vs 2024 (year over year) [DATA]:**
- Whole promotion window (all orders): 18,858.60 → 21,406.75 EUR (**+13.5 %**).
- Electrolux in the window: 11,242.00 → 14,741.25 EUR (**+31.1 %**), 21 → 27 units.
- Calendar week 22–30 November: 27,153.00 → 25,744.75 EUR (−5.2 %). Electrolux +7.7 %, LEGO −37 %.
- Cost: discount depth rose from 20 % to 25 %. Discount cost rose 70 % (3,303 → 5,613 EUR), and promoted margin fell
  from 30.1 % to 23.8 %. Electrolux promoted margin fell to **16.3 %**.

**Summer Sale [DATA]:** promoted net sales grew every year (22.3k → 25.0k → 28.4k EUR) at a stable 15 %. It is
the most efficient campaign, with about 0.8 EUR of promoted sales per EUR of media.

**Returns [DATA]:** promoted units are returned slightly less often (6.8 %) than full-price units (7.4 %).
Promotions do not cause extra returns.

## 4. Discount governance [POLICY]

1. **Margin floors per brand during a promotion** (promoted gross margin %):
   Electrolux ≥ 20 %, LEGO ≥ 30 %, Helly Hansen ≥ 40 %. PR05 broke the Electrolux floor (16.3 %).
2. **Maximum depth without CFO approval:** 20 %. Anything deeper (e.g. Black Friday 25 %) needs CFO and Commercial Director sign-off.
3. **No stacking.** One promotion per order. Loyalty points are still earned on promoted orders.
4. **Category and loyalty promotions must be restricted** at the point of sale to their scope (see the gaps in §2).
5. **Price-indication rules:** in Sweden and Denmark (EU), the "before" price must be the lowest price of the last 30 days.
   In Norway, follow Consumer Authority guidance. See `2026-10-21-regional-methodology.md`.
6. **Every promotion needs a post-campaign review** within 4 weeks: lift (method stated), discount cost, margin
   dilution against the floor, campaign efficiency and return rate.
7. **Regional promotions** are separate `promotion_id`s with the country in the name. The discount % is never varied by region
   within one promotion.

## 5. Recommended answers for common questions

| Question | Approach |
|---|---|
| "Did the deeper Black Friday discount pay off?" | YoY lift with PR05 vs PR01 dates, plus discount cost and margin vs the floor. Conclusion: more sales (+13.5 %), but margin breached the Electrolux floor. |
| "What is our average discount?" | Discount rate % = `SUM(discount_amount)/SUM(gross_sales)`. Overall ≈ 4.4 %; on promoted lines it equals the promotion %. |
| "Which promotion was most profitable?" | Gross profit on promoted lines, then subtract the campaign budget. |
| "How dependent are we on promotions?" | Promotion penetration % by year, region and brand. |

```sql
-- Promotion scorecard (one row per promotion, PR00 = baseline)
SELECT p.promotion_id, p.promotion_name, p.promotion_type, p.discount_pct,
       COUNT(DISTINCT f.order_id)                                   AS orders,
       ROUND(SUM(f.gross_sales), 2)                                 AS gross_sales_eur,
       ROUND(SUM(f.discount_amount), 2)                             AS discount_cost_eur,
       ROUND(SUM(f.net_sales), 2)                                   AS net_sales_eur,
       ROUND(SUM(f.gross_profit) / SUM(f.net_sales) * 100, 1)       AS gross_margin_pct
FROM gold.fact_order_line f
JOIN gold.dim_promotion p USING (promotion_id)
GROUP BY ALL
ORDER BY p.promotion_id;
```

```sql
-- Year-over-year Black Friday lift by brand, using the promotion windows (PR01 vs PR05)
WITH w AS (
  SELECT promotion_id, start_date, end_date FROM gold.dim_promotion WHERE promotion_id IN ('PR01', 'PR05')
)
SELECT pr.brand,
       ROUND(SUM(CASE WHEN w.promotion_id = 'PR01' THEN f.net_sales END), 2) AS bf_2024_eur,
       ROUND(SUM(CASE WHEN w.promotion_id = 'PR05' THEN f.net_sales END), 2) AS bf_2025_eur
FROM gold.fact_order_line f
JOIN gold.dim_date d     USING (date_key)
JOIN gold.dim_product pr USING (product_id)
JOIN w ON d.date BETWEEN w.start_date AND w.end_date
GROUP BY pr.brand;
```
