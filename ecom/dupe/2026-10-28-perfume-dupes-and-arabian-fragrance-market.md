---
title: Perfume dupes and the Arabian fragrance market
domain: Retail and Commerce
subdomain: Product Catalog
synonyms:
  - perfume dupes
  - fragrance dupes
  - Arabian alternatives
  - Middle Eastern perfume brands
  - Lattafa
  - Armaf
  - Afnan
  - Al Haramain
  - Rasasi
  - Maison Alhambra
  - Amouage
description: "Reference document for questions about perfume dupes: estimated Amazon sales of five Middle Eastern perfume brands (12 months reported in October 2025), the size of the Arabian fragrance category, and Arabian alternatives to the eight Nordvik Retail perfumes."
related_assets:
  - <catalog>.retail.dim_product
  - <catalog>.retail.fact_sales
  - <catalog>.retail.sales_metrics
sources:
  - "Market Defense data, reported by WWD (October 2025) - estimated Amazon sales"
  - "Euromonitor, cited by Retail Asia - Arabian fragrance category 2025"
  - "Business of Fashion - Amouage 2025"
---

# Perfume dupes and the Arabian fragrance market

This document has three parts: **market figures** for Middle Eastern perfume brands, **category context**, and a
**dupe map** from the eight Nordvik Retail perfumes to Arabian alternatives. A last section shows how to line the
map up with Nordvik Retail's own perfume sales.

> **Provenance.** The figures and matches below were supplied by the document author with the sources named in each
> section. They have **not** been independently verified or updated, and the source articles are not reproduced here.
> Check a figure at its source before you quote it outside this project.

## How to read the numbers

* **Platform sales, not company revenue.** The brand table shows *estimated sales on Amazon* only. It is not a
  brand's total company revenue.
* **No unit counts.** The source reports no units sold, so units cannot be derived and must not be guessed.
* **Total company revenue is not public** for these private brands - do not estimate it from the Amazon figures.
* **Different scope from Nordvik's data.** Nordvik Group is fictional and its sales are synthetic (SEK, orders
  2026-01-01 to 2026-06-30). The market figures are real-world estimates in USD for other periods. Show them
  **side by side with their scope, currency and period; never add, subtract or divide them, and do not convert
  currencies** unless the user supplies a rate and a period.

## 1. Estimated Amazon sales of Middle Eastern perfume brands

Source: Market Defense data reported by WWD. Period: the **12 months reported in October 2025**. Currency: USD.

| Middle Eastern perfume brand | Estimated Amazon sales, last 12 months | Estimated monthly average (as reported) | Annual sales ÷ 12 (computed) | Units sold | Total company revenue |
|---|---|---|---|---|---|
| Lattafa | $100M+ | ~$7.5M | at least ~$8.3M | Not reported | Not publicly disclosed |
| Armaf | $39M | ~$3.5M | ~$3.25M | Not reported | Not publicly disclosed |
| Afnan | $17M | ~$1.6M | ~$1.4M | Not reported | Not publicly disclosed |
| Al Haramain | $14M | ~$1.0M | ~$1.2M | Not reported | Not publicly disclosed |
| Rasasi | $12M | ~$1.3M | ~$1.0M | Not reported | Not publicly disclosed |

**Data-quality note.** The "estimated monthly average" column is copied as reported, but it does not equal the
annual estimate ÷ 12 for any of the five brands (Lattafa's ~$7.5M is even below the $8.3M implied by its own
"$100M+"). The source may average over a different window or use different underlying data. When a question needs a
monthly figure, give the reported average **and** the computed one, and say they differ.

Ranking by estimated Amazon sales: Lattafa, Armaf, Afnan, Al Haramain, Rasasi. Lattafa's figure is a floor
("$100M+"), so its exact lead over Armaf is not known.

### Dataset columns

If this table is turned into a dataset, the clearest columns are:

| column | content |
|---|---|
| `brand` | brand name |
| `amazon_sales_estimate_usd` | estimated Amazon sales for the period (Lattafa: 100,000,000 with a "floor" flag) |
| `period` | "12 months reported in October 2025" |
| `source` | Market Defense data, reported by WWD |
| `company_revenue_disclosure_status` | "Not publicly disclosed" |

Exact total revenue and units sold are generally not publicly available for these private brands.

## 2. Category context

* **Arabian fragrance category:** Euromonitor estimates global retail sales of **$4.9 billion in 2025**, including
  about **$2.9 billion in GCC domestic sales** (source: Retail Asia, citing Euromonitor). This is **category-wide
  retail spending, not the revenue of one brand**.
* **Amouage:** one brand with separately reported figures. It reported **over $430 million in global retail sales in
  2025, with revenue up 66%** (source: Business of Fashion). Note the measure: *retail sales*, which is not the same
  as the Amazon-only estimates in section 1, so the two must not be ranked against each other.

## 3. Arabian alternatives to the Nordvik Retail perfumes (dupe map)

These are **commonly cited scent matches, not exact copies**. Where no match is listed, the author could not
confidently recommend one - say so instead of suggesting one. The author read "laffa" as **Lattafa**.

| Original fragrance (Nordvik product) | Product id | Arabian alternative | Brand of the alternative |
|---|---|---|---|
| YSL Libre EDP | P022 | Libbra or Léonie | Maison Alhambra |
| YSL Black Opium EDP | P023 | Opera Noir | Maison Alhambra |
| JPG Le Male EDT | P024 | Glacier Pour Homme | Maison Alhambra |
| JPG Scandal EDP | P025 | No close Arabian match I can confidently recommend | - |
| Dior Sauvage EDT | P026 | Salvo | Maison Alhambra |
| Dior J'adore EDP | P027 | No close Arabian match I can confidently recommend | - |
| Chanel N°5 EDP | P028 | No close Arabian match I can confidently recommend | - |
| Chanel Bleu de Chanel EDP | P029 | Maahir Legacy | Lattafa |

Summary: **5 of 8** originals have a suggested alternative (4 from Maison Alhambra, 1 from Lattafa); **3 of 8** (Scandal,
J'adore, N°5) have none.

## 4. Lining the map up with Nordvik Retail's sales

The eight originals are exactly the eight perfumes in `<catalog>.retail.dim_product` (subcategory `perfume`). The map
can therefore be joined on `product_id`. This query lists each perfume with its alternative and Nordvik's own units and
net revenue (SEK, completed orders, 2026-01-01 to 2026-06-30). Perfumes without sales show NULL.

```sql
WITH dupe_map (product_id, arabian_alternative, alternative_brand) AS (
  VALUES
    ('P022', 'Libbra or Léonie', 'Maison Alhambra'),
    ('P023', 'Opera Noir', 'Maison Alhambra'),
    ('P024', 'Glacier Pour Homme', 'Maison Alhambra'),
    ('P025', NULL, NULL),
    ('P026', 'Salvo', 'Maison Alhambra'),
    ('P027', NULL, NULL),
    ('P028', NULL, NULL),
    ('P029', 'Maahir Legacy', 'Lattafa')
)
SELECT p.brand_name,
       p.product_name,
       m.arabian_alternative,
       m.alternative_brand,
       SUM(s.quantity) AS units_sold,
       SUM(s.net_revenue_sek) AS net_revenue_sek
FROM <catalog>.retail.dim_product p
LEFT JOIN dupe_map m ON m.product_id = p.product_id
LEFT JOIN <catalog>.retail.fact_sales s ON s.product_id = p.product_id
WHERE p.subcategory = 'perfume'
GROUP BY ALL
ORDER BY net_revenue_sek DESC NULLS LAST
```

How to answer comparison questions:

1. Get **Nordvik's** figure from the query above (or `retail.sales_metrics`) and quote it with its scope: SEK, completed
   orders, H1 2026, synthetic data.
2. Quote the **market** figure from section 1 or 2 with its scope: USD, Amazon only (or category retail sales), the
   period and the source.
3. Put them side by side and state that currency, period, scope and data type differ. Do not compute a ratio, a share
   or a "market share".
4. For brand-level company revenue or units, answer that they are **not publicly disclosed / not reported** in the
   source.

## Example questions this document answers

* Which Middle Eastern perfume brand has the highest estimated Amazon sales, and how big is it? *(Lattafa, $100M+ over
  the 12 months reported in October 2025.)*
* How much does Rasasi sell on Amazon per month? *(Reported ~$1.3M; annual $12M ÷ 12 = ~$1.0M - the two differ.)*
* How many units did Armaf sell? *(Not reported by the source.)*
* What is the total revenue of Lattafa? *(Not publicly disclosed.)*
* How big is the Arabian fragrance market? *($4.9 billion global retail sales in 2025, about $2.9 billion in GCC
  domestic sales - category-wide, per Euromonitor via Retail Asia.)*
* Is there an Arabian alternative to Dior Sauvage? *(Salvo by Maison Alhambra - a commonly cited scent match, not an
  exact copy.)*
* Which of our perfumes have no Arabian alternative? *(Scandal, J'adore and N°5.)*
* Which of our perfumes with an Arabian alternative sold the most? *(Use the query in section 4.)*
