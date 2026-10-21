# Nordhem Retail Group — Regional Methodology (Sweden, Norway, Denmark)

> How Nordhem defines, compares and explains performance by region. **[DATA]** means you can check it in
> `retail_bootcamp.gold`. **[POLICY]** means a company rule or market practice that is not stored in a table.
> All amounts are in EUR, and the data runs to 2026-09-30.

---

## 1. Region definitions

**[DATA]**

| Region | Country | Stores | Customers |
|---|---|---|---|
| Scandinavia East | Sweden (SE) | ST01–ST04 + **ON01 Online** | 80 |
| Scandinavia West | Norway (NO) | ST05–ST07 | 62 |
| Scandinavia South | Denmark (DK) | ST08–ST10 | 55 |
| Unassigned | Faroe Islands | none | 3 |

Two region concepts exist. Always say which one you are using:

| Concept | Column | Meaning | Use for |
|---|---|---|---|
| **Store region** (default) | `dim_store.region` | Where the sale was made | Sales, margin, discounts, stock, store P&L |
| **Customer region** | `dim_customer.region` | Where the customer lives | Customer base, loyalty, online demand by market, segments |

## 2. Rules for regional reporting

1. **Default to store region** for "sales by region", "which region sells most" and similar questions. **[DATA]**
2. **Online sits in Scandinavia East.** ON01 is run from Sweden, so its store region is Scandinavia East. **[DATA]**
   - For a **like-for-like store comparison** between countries, filter `dim_store.channel = 'Store'`.
   - For **online demand by market**, use the **customer region** of online orders.
   - When a total for Scandinavia East includes online, say so in the answer.
3. **Normalise by store count** when comparing physical regions. Sweden has 4 stores, while Norway and Denmark have 3 each. **[POLICY]**
   Report "net sales per store" alongside totals.
4. **Keep Unassigned visible.** Faroe Islands customers (region `Unassigned`) placed 5 online orders (≈ 3,041 EUR)
   and 3 store orders (≈ 1,346 EUR). Show them as a separate row in customer-region views and don't drop them. **[DATA]**
5. **Currency.** All gold amounts are already in EUR. Do not convert. Local currencies (SEK, NOK, DKK) are context
   only. **[POLICY]**
6. **Finance is per store.** `fact_finance_monthly` comes from the general ledger. Region totals for P&L are built from
   `dim_store.region`, and are never added to order-line revenue. **[DATA]**

### Region benchmarks [DATA] (2024-01 to 2026-09)

| Metric | Scandinavia East (stores only) | Scandinavia West | Scandinavia South | Online (ON01) |
|---|---|---|---|---|
| Net sales (EUR) | 155,841.45 | 150,511.80 | 136,948.20 | 207,500.10 |
| Net sales per store (EUR) | ≈ 38,960 | ≈ 50,171 | ≈ 45,649 | — |
| Average order value (EUR) | 461.07 | 549.31 | 487.36 | 481.44 |
| Gross margin % | 40.9 % | 39.9 % | 41.0 % | 41.4 % |
| Discount rate (discount ÷ gross sales) | 4.4 % | 4.7 % | 4.2 % | 4.3 % |
| Share of lines on promotion (incl. online for East) | 31.2 % | 32.3 % | 34.1 % | — |
| Stock-out rate % (last 90 days) | 2.6 % (incl. ON01) | 2.3 % | 2.3 % | 1.4 % |

Return rates by region: Scandinavia East 8.2 % (includes online), West 5.9 %, South 5.8 %. Online returns
(9.8 %) are much higher than store returns (5.9 %). Compare channels before blaming a region.

**Brand mix by region [DATA]:** Electrolux is ≈ 61–65 % of net sales in every region (store region, East incl. online). Norway has the highest
Electrolux average order value (≈ 726 EUR), which explains its high AOV and slightly lower margin (34.4 % on
Electrolux vs 35.0–35.8 % elsewhere). Helly Hansen margin is ≈ 54.5–55.4 % in every region.

## 3. Country-specific market practices

### 3.1 Sweden — Scandinavia East
- **Payments [DATA]:** in stores, Card 67 %, **Swish** 26 %, Cash 7 %.
- **National days and peaks [POLICY]:** Midsummer Eve (a Friday between 19 and 25 June) and National Day (6 June).
  Neither is flagged in `dim_date.is_holiday`. Swedish stores open on reduced hours at Midsummer, so a June dip in
  a Swedish store is expected.
- **Pricing [POLICY]:** shelf prices include 25 % VAT. Sweden is in the EU, so a "before" price in a promotion
  must be the lowest price of the previous 30 days (EU Omnibus price-indication rule).
- **Region role [POLICY]:** home market and online hub. All online fulfilment runs from warehouse WH01 in Sweden.

### 3.2 Norway — Scandinavia West
- **Payments [DATA]:** in stores, Card 66 %, **Vipps** 26 %, Cash 8 %.
- **National days and peaks [POLICY]:** Constitution Day (17 May) is not flagged in `dim_date.is_holiday`. Stores
  close, so expect a one-day dip. November (Black Week) is Norway's strongest store month by a wide margin: about
  10,900 EUR per November vs about 8,200 in Sweden and 7,600 in Denmark **[DATA]**.
- **Pricing [POLICY]:** prices include 25 % VAT. Norway is in the EEA but outside the EU customs union. Online orders
  shipped from Sweden to Norwegian customers are cross-border and handled through the Norwegian VAT scheme for
  low-value goods. Promotion "before" prices follow Norwegian Consumer Authority guidance: the product must have
  been sold at that price for a real and recent period.
- **Region role [POLICY]:** highest value per store. It suits premium Electrolux ranges and Helly Hansen
  winter outerwear (Bergen and Oslo weather).

### 3.3 Denmark — Scandinavia South
- **Payments [DATA]:** in stores, Card 64 %, **MobilePay** 22 %, Cash 14 % (highest cash share).
- **National days and peaks [POLICY]:** Constitution Day (5 June) is not flagged in `dim_date.is_holiday`.
  Many stores close at midday. Danish stores have the weakest October of the three countries (≈ 2,400 EUR per
  October vs ≈ 6,200 in Sweden) **[DATA]**.
  > Month comparisons use the **average per year** for that month: October–December appear in 2 years of data,
  > while January–September appear in 3. Monthly store samples are small, so treat them as indicative.
- **Pricing [POLICY]:** prices include 25 % VAT. EU Omnibus 30-day lowest-price rule applies.
- **Region role [POLICY]:** LEGO's home market. Christmas and toy promotions are expected to perform well here.
  Denmark has the highest share of order lines on promotion (34 %).

### 3.4 Online (ON01) across markets
- **Payments [DATA]:** Card 41 %, **Klarna 29 %**, Swish 14 %, MobilePay 10 %, Vipps 7 %. Klarna (invoice or
  instalments) is offered online only.
- **Demand by customer region [DATA]:** Scandinavia East 40.0 %, West 30.3 %, South 28.2 %, Unassigned 1.5 % of
  online net sales.
- **Conversion [DATA]:** 8.62 % of 5,000 web sessions ordered. Conversion exists only for online. Never compute it
  for stores.

## 4. Regional promotion methodology

**[DATA] All nine promotions so far ran in every region and both channels at the same discount %.** No promotion
is limited to one country. Regional differences come from uptake and mix, not from different discount levels.

**Promotion results by region [DATA]** (net sales on promoted lines, EUR):

| Promotion | East (incl. online) | West | South |
|---|---|---|---|
| PR01 Black Friday 2024 (20 %) | 8,988 | 1,235 | 2,990 |
| PR05 Black Friday 2025 (25 %) | 6,258 | 7,446 | 3,136 |
| PR06 Christmas Gift Deal 2025 (10 %) | 10,213 | 4,101 | 3,398 |
| PR08 Summer Sale 2026 (15 %) | 15,457 | 6,096 | 6,815 |
| PR09 Loyalty Spring Bonus (5 %) | 17,147 | 6,158 | 9,637 |

Norway responded most to the deeper 2025 Black Friday discount: it grew from 4 to 14 promoted orders. Its margin
on those lines fell to 20.1 %, the lowest of any region and promotion.

**Policy for future regional promotions [POLICY]:**
1. A national promotion may be added for local events: Midsummer (SE), 17 May (NO) or Constitution Day (DK).
   It must be set up as its own `promotion_id` whose name contains the country (e.g. "Midsummer 2027 SE"), so it can be
   analysed separately.
2. The discount % for one promotion is the same in every region where it runs. Use different promotions instead of
   different rates.
3. Regional promotion results are always reported by **store region with channel split**, plus the uplift method
   from `2026-10-21-promotions-and-discounts.md`.

## 5. Example questions and how to answer them

| Question | How to answer |
|---|---|
| "Which region sells the most?" | Store region, `channel = 'Store'`, plus net sales per store. Mention online separately. |
| "Where do our online customers live?" | `dim_customer.region` for lines with `store_id = 'ON01'`. |
| "Which country prefers mobile payment?" | `fact_order_line.payment_method` by `dim_store.country`, stores only. |
| "Is Denmark more promotion-driven?" | Share of lines with `promotion_id <> 'PR00'` by store region, stores only. |
| "Why are returns high in Sweden?" | Split Scandinavia East into Store and Online first. Online drives it. |

```sql
-- Like-for-like net sales per physical store by region
SELECT s.region,
       COUNT(DISTINCT s.store_id)                              AS stores,
       ROUND(SUM(f.net_sales), 2)                              AS net_sales_eur,
       ROUND(SUM(f.net_sales) / COUNT(DISTINCT s.store_id), 2) AS net_sales_per_store_eur
FROM gold.fact_order_line f
JOIN gold.dim_store s USING (store_id)
WHERE s.channel = 'Store'
GROUP BY s.region
ORDER BY net_sales_per_store_eur DESC;
```
