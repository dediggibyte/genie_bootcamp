---
title: Product Category and Brand
domain: Retail and Commerce
subdomain: Product Catalog
synonyms:
  - category
  - department
  - brand
  - subcategory
description: Categories electronics, fashion, beauty; 9 brands; subcategories such as phone or perfume.
related_assets:
  - <catalog>.retail.dim_product
  - <catalog>.retail.sales_metrics
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Product Category and Brand

## Definition

Products belong to one **category** (`electronics`, `fashion`, `beauty`), one **subcategory** (phone, laptop, tablet, jeans, jacket, sweatshirt, office_wear, perfume) and one **brand** (Apple, Samsung, Google, H&M, Åhléns, Yves Saint Laurent, Jean Paul Gaultier, Dior, Chanel).

## How to calculate

Use the governed metric view `<catalog>.retail.sales_metrics` (measure `net_revenue_sek`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(net_revenue_sek) AS net_revenue_sek
FROM <catalog>.retail.sales_metrics
WHERE category = 'electronics'
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**224 267 SEK** (electronics net revenue Jan-Jun 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Treating 'Åhléns' as a store - here it is a fashion brand on sale in Nordvik stores.

## Related terms

* [Net Revenue](2026-10-27-net-revenue.md)
* [Gross Margin](2026-10-27-gross-margin.md)

## Example questions

* Net revenue by brand
* Which subcategory sells the most units?
