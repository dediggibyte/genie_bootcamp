---
title: Company profile — Fjällmark Consumer Goods AB
description: Who Fjällmark is, its legal entities, currencies, brands, plants, markets, fiscal calendar and the business events every analyst should know about.
owner: Group Business Analytics (role)
sources:
  - bootcamp/context/company_profile.md (this repository)
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM (tools/model/)
---

# Fjällmark Consumer Goods AB — company profile

> Fjällmark is a **fictional** company created for the Genie bootcamp. All names, places of
> business, customers and figures are invented; all data is synthetic.

Fjällmark Consumer Goods AB is a Nordic consumer-goods group headquartered in **Stockholm,
Sweden**. It makes and sells packaged food, beverages and personal-care products under three
brands, sells **direct to consumers (DTC)** through its own webshop `fjallmark.example`, and
sells **business to business (B2B)** to about 25 retail and wholesale trade accounts.

## 1. Legal entities (company codes) and currencies

The **group reporting currency is EUR**. Every legal entity keeps its books in its own
**local (company code) currency**.

| Company code | Legal entity | Country | Local currency | Role |
|---|---|---|---|---|
| `SE01` | Fjällmark Consumer Goods AB (group parent) | Sweden (SWE) | SEK | HQ, DTC Sweden, Lund and Norrköping plants |
| `NO01` | Fjällmark Norge AS | Norway (NOR) | NOK | Sales and DTC Norway |
| `DK01` | Fjällmark Danmark A/S | Denmark (DNK) | DKK | Sales and DTC Denmark |
| `FI01` | Fjällmark Suomi Oy | Finland (FIN) | EUR | Sales and DTC Finland, Tampere plant |
| `DE01` | Fjällmark Deutschland GmbH | Germany (DEU) | EUR | Sales and DTC Germany **and the Netherlands** |
| `PL01` | Fjällmark Polska Sp. z o.o. | Poland (POL) | PLN | Poznań personal-care plant, local B2B, **no DTC** |

Approximate FX rates (EUR per 1 unit of local currency; finance uses a monthly average rate
that moves within about ±2 %): SEK 0.087 · NOK 0.085 · DKK 0.134 · PLN 0.232 · EUR 1.000.
The rate actually used is stored on every GL posting (see the *Group Currency & FX* page).

## 2. Brands and products

| Brand | Category | Products | Made in |
|---|---|---|---|
| **Björkö Pantry** | Food (`FOOD`) | crispbread, granola & muesli, oat porridge, berry jams, muesli bars | Lund (SE-LUN) |
| **Kallkälla** | Beverages (`BEVERAGE`) | sparkling spring water (lemon, lime, elderflower, natural), juices, oat drinks (launched April 2025) | Norrköping (SE-NKP) for water and juices, Tampere (FI-TMP) for oat drinks |
| **Mjuk Care** | Personal care (`PERSONAL_CARE`) | shampoo, conditioner, body wash, deodorant, toothpaste, hand cream, gift sets | Poznań (PL-POZ) |

About 90 SKUs with GS1 GTIN-13 codes. Standard cost (COGS) is typically 35–55 % of the net
selling price. Some SKUs are seasonal (Christmas gift sets, summer flavours).

## 3. Plants (manufacturing facilities)

| Plant | Site | Lines | Notes |
|---|---|---|---|
| SE-LUN | Lund Food Plant, Sweden | 4 | Björkö Pantry |
| SE-NKP | Norrköping Beverage Plant, Sweden | 4 | Kallkälla sparkling water and juices |
| FI-TMP | Tampere Oat Drink Plant, Finland | 3 | Kallkälla oat drinks; **commissioned April 2025** |
| PL-POZ | Poznań Personal Care Plant, Poland | 5 | Mjuk Care; line PL-POZ-L2 = liquid filling (shampoo, body wash) |

Production lines are named `<plant>-L<n>` on the shop floor (e.g. `PL-POZ-L2`).

## 4. Markets and channels

* **DTC webshop** `fjallmark.example` in Sweden, Norway, Denmark, Finland, Germany and the
  Netherlands. Orders are priced and stored in the market currency (SEK, NOK, DKK, EUR) and
  include VAT (SE/NO/DK 25 %, FI 24 %, DE 19 %, NL 21 %) and a shipping fee below a free-shipping
  threshold. Dutch orders are booked by the German entity `DE01`.
* **Loyalty programme "Fjällmark Friends"** with four tiers: **Bronze, Silver, Gold, Platinum**.
  100 points are worth 1 EUR.
* **Subscriptions** (monthly auto-replenishment): granola box, oat-drink crates, Mjuk Care refills.
* **B2B trade accounts**: about 25 fictional grocery, drugstore, pharmacy, wholesale and
  food-service customers across the six countries (e.g. NorthCart Retail, Fjordhandel,
  Baltic FreshMarket, Kaleva Kauppa, Alpina Drogerie). Payment terms 30 days (45 days in DE/NL).
* **Distribution centres**: Jönköping (SE), Oslo (NO), Odense (DK), Vantaa (FI), Hamburg (DE).

## 5. Calendar and data window

* **Fiscal year = calendar year**; **fiscal period = calendar month (1–12)**. Q1 = periods 1–3, etc.
* Transactions cover **1 January 2024 – 30 September 2026**. The books for September 2026 are
  closed; receivables are reported **as of 30 September 2026** (data extract 15 October 2026).
  "Today", "last month" and "last 12 months" should be read relative to **2026-09-30** unless the
  user says otherwise.
* Seasonality: Q4 Christmas peak (November–December about +35 % DTC orders); beverages peak in
  summer (June–August about +40 %); personal care is flat. DTC grows about 18 % a year, B2B about 5 %.

## 6. Business facts every analyst should know

1. **Two revenue numbers exist — finance's is the official one.** The webshop reports order
   totals *including VAT and shipping, before returns, in local currency*. Finance reports
   **Net Revenue** from the general ledger: revenue accounts only, **excluding VAT and shipping,
   after returns and trade discounts, in EUR**, for DTC *and* B2B. For the same month the
   finance's DTC net revenue is typically 24–30 % lower than the webshop's DTC "sales" (order totals
   converted to EUR) — or, the other way round, the webshop figure is about a third higher. Board,
   budget and bonus figures always use Net Revenue.
2. **Never add amounts in different currencies.** SEK, NOK, DKK, PLN and EUR amounts may only be
   added after conversion to EUR. The GL carries the EUR amount on every line.
3. **Poznań line PL-POZ-L2 quality incident, March 2026.** Worn filler nozzles on the liquid
   filling line caused under-filled bottles and leaking caps (yield loss reason
   *equipment malfunction*). Yield fell from about 97 % to about 87 %, scrap roughly tripled (2.4 % → 7.3 %),
   downtime spiked and production orders finished late. Maintenance fixed it in early April 2026
   (4 April). Finance saw a matching spike in production variances (COGS) for `PL01` in March 2026.
4. **Tampere ramp-up.** The Tampere oat-drink plant started production in April 2025 with OEE
   around 55 %; it reached its 78 % target in June 2026 (quarterly average Q2 2026 78.4 %,
   Q3 2026 78.9 %). Compare Tampere with the mature plants only for periods after the ramp-up, and say so.
5. **Loyalty pays.** Gold and Platinum members place about three times as many orders as
   shoppers without a loyalty account and spend about 2.4 times as much per order.
   Shoppers in CLTV segment `at_risk` have not ordered in the last 180 days.
6. **German receivables are the problem child.** Alpina Drogerie GmbH, one of DE01's largest
   trade customers, has disputed invoices since June 2026. DE01's DSO is about 66 days against a
   group DSO of about 39 days, and DE01 carries the largest overdue balance.

## 7. Data and privacy

* Shopper names, e-mail addresses, phone numbers, birth dates and postal codes are personal
  data. They are masked for most users, and analysts may only see rows of the company codes
  they are entitled to. Never ask Genie to list individual shoppers' contact details; analyse
  shoppers in aggregate (counts, segments, tiers, markets).
* E-mail addresses in the data use the reserved domain `example.com`; phone numbers are fake.
