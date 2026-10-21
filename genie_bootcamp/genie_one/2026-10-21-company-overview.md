# Nordhem Retail Group — Company Overview

> **Purpose.** Business context for Genie One. It explains who the company is, where it sells and how its data
> is organised. Column and table names refer to the Unity Catalog schema `retail_bootcamp.gold`.
>
> **Labels used in every Genie One document:**
> - **[DATA]** — a fact you can check in the gold tables. Numbers are calculated from the bootcamp data (2024-01-01 to 2026-09-30).
> - **[POLICY]** — a company rule or business practice. It guides interpretation and recommendations, but no
>   table records it, so Genie cannot check it with SQL.
>
> Nordhem Retail Group is fictional and all data is synthetic. The brand names Electrolux, LEGO and Helly Hansen are
> used for realism only. No price, cost, volume or financial figure relates to the real companies.

---

## 1. Who we are

**[DATA]** Nordhem Retail Group is a multi-brand retailer in Scandinavia. It sells three Nordic brands through
10 physical stores and one web shop. All amounts are reported in **EUR**. The data's as-of date is **2026-09-30**.
Questions about "today", "this month" or "last 30 days" are relative to that date.

| Brand | Home country | Category (`dim_product.category`) | Products | Seasonal peak | Supplier lead time |
|---|---|---|---|---|---|
| Electrolux | Sweden | Home Appliances | 5 | Black Friday (November) | 21 days |
| LEGO | Denmark | Toys | 5 | Christmas (December) | 14 days |
| Helly Hansen | Norway | Outdoor Apparel | 5 | Winter (October–February) | 28 days |

Sub-categories (`dim_product.sub_category`): Dishwashers, Laundry, Floor Care, Cooking, Air Care (Electrolux);
Construction Sets, Display Models (LEGO); Shell Jackets, Midlayers, Base Layers, Rainwear, Ski Jackets (Helly Hansen).

**Brand economics [DATA]** (all order lines, 2024-01 to 2026-09):

| Brand | Net sales (EUR) | Share | Gross margin % without promotion | Typical ticket |
|---|---|---|---|---|
| Electrolux | ≈ 404,000 | 62 % | 37.7 % | High (299–899 EUR list price), 1 unit per line |
| Helly Hansen | ≈ 128,000 | 20 % | 57.3 % | Medium (69–449 EUR) |
| LEGO | ≈ 119,000 | 18 % | 47.8 % | Low–medium (49–449 EUR), often 2–3 units per line |

Electrolux drives revenue. Helly Hansen and LEGO drive margin. This matters for discount decisions. See
`2026-10-21-promotions-and-discounts.md`.

## 2. Market regions and store network

**[DATA]** Each country is one sales region (`dim_store.region`, derived from `country_region`):

| Region | Country | Local currency [POLICY context] | Physical stores |
|---|---|---|---|
| **Scandinavia East** | Sweden | SEK | ST01 Mall of Scandinavia (Stockholm), ST02 Gallerian Stockholm, ST03 Nordstan Gothenburg, ST04 Emporia Malmo |
| **Scandinavia West** | Norway | NOK | ST05 Storo Oslo, ST06 Byporten Oslo, ST07 Lagunen Bergen |
| **Scandinavia South** | Denmark | DKK | ST08 Fields Copenhagen, ST09 Stroget Copenhagen, ST10 Bruuns Galleri Aarhus |
| (Online) | Run from Sweden | — | **ON01 Online Store**, shipped from warehouse WH01 |

> **Important [DATA]:** `ON01` has `country = 'Sweden'`, so its `region` is **Scandinavia East**. Any "sales by
> region" total for Scandinavia East therefore includes all online sales (≈ 207,500 EUR of ≈ 363,300 EUR).
> To compare regions fairly, filter `dim_store.channel = 'Store'`. See `2026-10-21-regional-methodology.md`.

**Net sales by channel and region [DATA]:**

| Region | Channel | Orders | Net sales (EUR) | Gross margin % | Avg order value (EUR) |
|---|---|---|---|---|---|
| Scandinavia East | Online (ON01) | 431 | 207,500.10 | 41.4 % | 481.44 |
| Scandinavia East | Store (4 stores) | 338 | 155,841.45 | 40.9 % | 461.07 |
| Scandinavia West | Store (3 stores) | 274 | 150,511.80 | 39.9 % | 549.31 |
| Scandinavia South | Store (3 stores) | 281 | 136,948.20 | 41.0 % | 487.36 |
| **Total** | | **1,324** | **650,801.55** | **40.8 %** | |

Per physical store, Norway sells the most (≈ 50,200 EUR per store), ahead of Denmark (≈ 45,600) and Sweden (≈ 39,000).
Norway also has the highest average order value, because it buys more Electrolux per order.

## 3. Channels

**[DATA]** `dim_store.channel` is either **Store** (ST01–ST10) or **Online** (ON01).
- About 32 % of orders are online. Online orders have IDs `WEB-*` and lines `WEBI-*`; store orders have `POS-*` / `POSI-*`.
- Online orders are delivered by PostNord, Bring, DHL Express or Budbee with a **3-day delivery promise**.
- Web-shop behaviour (sessions, device, traffic source, conversion) is only in `fact_web_session`.
- About 90 % of store customers live in the same country as the store. Online customers come from all three countries.

## 4. Customers and loyalty

**[DATA]** 200 customers: Sweden 80, Norway 62, Denmark 55, Faroe Islands 3 (region `Unassigned`).

Loyalty tiers (`dim_customer.loyalty_tier`): None 59, Bronze 65, Silver 46, Gold 21, Platinum 9.

Customer segments (`dim_customer.customer_segment`), calculated at 2026-09-30:
- **VIP**: lifetime net sales ≥ 2,000 EUR, or Platinum tier.
- **New**: signed up within 180 days of 2026-09-30, or at most 1 order.
- **Regular**: everyone else.

**[POLICY]** Loyalty is a single Nordhem programme across all three countries. Points and tiers are shared by every
store and the web shop. A customer keeps their home region (`dim_customer.region`) wherever they shop.

## 5. Calendar and seasons

**[DATA]** `dim_date` covers 2024-01-01 to 2026-12-31 and defines:
- `season`: Winter (Dec–Feb), Spring (Mar–May), Summer (Jun–Aug), Autumn (Sep–Nov).
- `is_holiday`: only public holidays **shared by all three countries**, such as New Year, Easter, 1 May,
  Ascension, Whit Monday and Christmas. National days are **not** flagged. See the regional methodology.
- `is_weekend`: Saturday and Sunday. Weekend days sell about 30 % more than weekdays.

**Retail calendar [DATA + POLICY]:**

| Period | Dates | What happens |
|---|---|---|
| Winter low | January–February | Lowest sales of the year |
| Loyalty Spring Bonus | March–April (2025 only) | 5 % loyalty promotion (PR09) |
| Summer Sale | mid-June to 31 July | 15 % clearance (PR03/PR04/PR08) |
| Winter Outdoor | October (2025) | 20 % "Winter Outdoor Week" (PR07); Helly Hansen season starts |
| Black Week | last week of November | Black Friday promotion (20 % in 2024, 25 % in 2025). Highest daily sales of the year |
| Christmas | early December to 23 December | 10 % Christmas Gift Deal; LEGO peak |

## 6. Data sources (for lineage questions)

**[DATA]** CRM (customers, loyalty), E-commerce (sessions, online orders), POS (store orders), ERP (products,
suppliers, purchase orders), WMS (inventory, shipments), Payment gateway (payments, refunds), Returns portal,
Marketing (promotions, campaigns), Finance GL (gl_entries, budgets, cost centres) and Master data (stores,
channels, regions). Silver cleans them and Gold models them as a star schema with 6 dimensions and 6 facts.

## 7. Related documents
- `2026-10-21-regional-methodology.md`: how we compare and report Sweden, Norway and Denmark.
- `2026-10-21-promotions-and-discounts.md`: promotion types, discount calculation, lift and ROI methods.
- `2026-10-21-kpi-methodology.md`: every KPI formula, grain and validated value.
- `2026-10-21-returns-inventory-fulfilment.md`: returns, stock, delivery and loyalty operations.
