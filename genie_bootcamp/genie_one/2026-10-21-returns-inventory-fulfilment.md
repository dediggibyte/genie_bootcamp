# Nordhem Retail Group — Returns, Inventory, Fulfilment and Loyalty Operations

> Operating policies and how to analyse them. **[DATA]** means you can check it in `retail_bootcamp.gold`.
> **[POLICY]** means a company rule that no table stores. All amounts are in EUR.

---

## 1. Returns

### Policy [POLICY]
- **Online:** 14-day right of withdrawal from delivery in all three countries (EU / Norwegian consumer law), plus
  Nordhem's own extension to **30 days**.
- **Stores:** 30-day return with receipt, at any Nordhem store in the same country.
- **Refund:** to the original payment method. The refund can be partial when the item is damaged by the customer.
- Defective products are handled under the 2-year statutory complaint period (5 years in Norway for durable
  goods such as appliances). These still appear in `fact_returns` with reason `Defective`.

### Facts [DATA]
- 159 returns, 175 units, 46,003.40 EUR refunded. Return rate **7.2 %** of units sold.
- Online returns **9.8 %** vs stores **5.9 %**.
- By store region: Scandinavia East 8.2 % (includes online), West 5.9 %, South 5.8 %.
- Promoted units are returned slightly less often (6.8 %) than full-price units (7.4 %).

**Return reasons (units) [DATA]:**

| Brand | Changed mind | Damaged on arrival | Defective | Not as described | Wrong size | Total |
|---|---|---|---|---|---|---|
| Electrolux | 16 | 15 | 10 | 4 | 0 | 45 |
| Helly Hansen | 22 | 10 | 11 | 9 | **30** | **82** |
| LEGO | 21 | 11 | 6 | 10 | 0 | 48 |
| **Total** | 59 | 36 | 27 | 23 | 30 | 175 |

Helly Hansen accounts for 47 % of returned units, and "Wrong size" is its biggest reason. The action is better size
guides and fit content online. "Damaged on arrival" for Electrolux points to carrier handling of large appliances.

### Method
- Return rate = `SUM(return_qty) / SUM(quantity)`. Aggregate each fact separately at the same grain, then divide.
- Returns are dated by the **return date**. For "return rate of products sold in period X", join `fact_returns`
  to `fact_order_line` via `order_item_id` and filter on the sale date. State which basis you used.

## 2. Inventory and replenishment

### Facts [DATA]
- `fact_inventory_daily` covers **90 days (2026-07-03 to 2026-09-30)**: 15 products × 11 locations.
- Warehouse WH01 is reported as location `ON01`.
- Stock-out = `available_qty <= 0`, where `available_qty = on_hand_qty − reserved_qty`.
- Stock-out rate **2.4 %** overall. By location it ranges from 1.0 % (ST07 Lagunen Bergen) and 1.4 % (ON01 / warehouse)
  to 3.3 % (ST05 Storo Oslo) and 3.2 % (ST03 Nordstan Gothenburg).

### Policy [POLICY]
- **Reorder point** (`reorder_point`) = expected demand during supplier lead time plus safety stock. Lead times:
  LEGO 14 days, Electrolux 21 days, Helly Hansen 28 days (`dim_supplier.lead_time_days`).
- **Target:** stock-out rate below **3 %** per store per month. Stores above **5 %** in the last 30 days get a
  replenishment review.
- **Pre-season build:** Helly Hansen stock is built up from September for the October–February winter season.
  LEGO is built up from October for Christmas, and Electrolux by mid-November for Black Week. Helly Hansen has the
  longest lead time, so its orders are placed earliest.
- **Rebalancing:** move stock between stores in the same country before raising a new purchase order.

### Method
- Stock is a snapshot. Use the latest date (`date_key = 20260930`) or an average. Never sum across dates.
- "Which products are at risk?" means `available_qty <= reorder_point` on the latest date.

## 3. Online fulfilment and delivery

### Facts [DATA]
- All online orders ship from warehouse **WH01 (Sweden)** with PostNord, Bring, DHL Express or Budbee.
- **Delivery promise: 3 days.** On-time delivery is ≈ 81 % of delivered shipments.

| Carrier | Delivered shipments | Avg delivery days | On-time % |
|---|---|---|---|
| DHL Express | 91 | 2.5 | 87.9 % |
| Bring | 105 | 2.8 | 81.0 % |
| Budbee | 74 | 2.7 | 79.7 % |
| PostNord | 161 | 2.7 | 78.9 % |

- Shipping cost charged per order is 4.90, 6.90, 9.90 or 14.90 EUR.

### Policy [POLICY]
- **Carrier by market:** PostNord is the default for Sweden and Denmark, Bring for Norway, and Budbee for
  urban home delivery. DHL Express is used for large or urgent parcels such as appliances.
- **Target:** on-time delivery ≥ 90 %. Carriers below 80 % for two consecutive months are reviewed.
- **Norway shipments** are cross-border from Sweden and can take a day longer because of customs handling.

## 4. Loyalty programme

### Facts [DATA]
- Tiers: None (59 customers), Bronze (65), Silver (46), Gold (21), Platinum (9).
- Platinum customers have the highest average order value (≈ 596 EUR vs ≈ 480–500 EUR for other tiers).
- VIP segment = lifetime net sales ≥ 2,000 EUR **or** Platinum.

### Policy [POLICY]
- One programme across Sweden, Norway, Denmark and online. 1 point per EUR of net sales, earned on promoted orders too.
- Tier thresholds (rolling 12 months net spend): Bronze on enrolment, Silver 500 EUR, Gold 1,500 EUR,
  Platinum 3,000 EUR.
- Member-only promotions use `promotion_type = 'Loyalty'` and must be restricted to members at checkout.
  PR09 was not restricted correctly in 2025. See `2026-10-21-promotions-and-discounts.md`.
- VIP benefits: free shipping, extended 60-day returns and early access to Black Week.

## 5. Finance (P&L vs budget)

### Facts [DATA]
- `fact_finance_monthly`: 33 months × 11 stores of general-ledger actuals and budget.
- GL revenue is **booked store revenue**. It is larger than order-line net sales, because the order lines only cover
  tracked customer transactions. **The two are never added together or compared directly.**
- Operating profit = revenue − COGS − operating expenses (staff, rent, marketing, utilities).

### Policy [POLICY]
- Each store has two cost centres, Operations and Local Marketing (`CC-<store>-OPS`, `CC-<store>-MKT`).
- A store **misses budget** when its year-to-date operating profit is below `budget_operating_profit`.
  Two consecutive missed quarters trigger a store performance plan.
- Group campaign budgets (see the promotions document) are held centrally and are not part of store P&L.
