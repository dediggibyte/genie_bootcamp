---
title: Retail and Commerce
domain: Retail and Commerce
domain_tag: Nordvik Retail and Commerce
business_unit: Nordvik Retail
subtitle: Stores, webshop, products, customers, sales and returns
description: Nordvik Retail sells electronics, fashion and beauty in 5 stores (Stockholm, Göteborg, Malmö) and a webshop. Owns the product catalog, stores and channels, loyalty customers, sales and returns - the source for net revenue, orders, average order value, gross margin and return rate.
business_owner: Head of Retail Commercial (role)
technical_owner: Retail Data Product Team (role)
schema: <catalog>.retail
genie_agent: Nordvik Retail Analyst
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Retail and Commerce (Nordvik Retail)

Nordvik Retail sells electronics, fashion and beauty in 5 stores (Stockholm, Göteborg, Malmö) and a webshop. Owns the product catalog, stores and channels, loyalty customers, sales and returns - the source for net revenue, orders, average order value, gross margin and return rate.

* **Governed tag / UC domain:** `Nordvik Retail and Commerce` - applied to the gold schema `<catalog>.retail` by notebook
  `notebooks/2026-10-27-05-context-common.py` (run through `05a`), which can also create the domain itself.
* **Data:** orders 2026-01-01 to 2026-06-30. Amounts in SEK excl. VAT. All data is synthetic.
* **Genie Agent:** *Nordvik Retail Analyst* (`genie/2026-10-27-retail-agent.json`, created by notebook 04).

## Subdomains

| subdomain | governed tag | what it holds | gold objects |
|---|---|---|---|
| Product Catalog | `Nordvik Retail and Commerce/Product Catalog` | Products and their brands, categories, list prices and purchase costs. | `retail.dim_product` |
| Stores and Channels | `Nordvik Retail and Commerce/Stores and Channels` | The 5 stores and the webshop, their regions and sales channels. | `retail.dim_store` |
| Customers | `Nordvik Retail and Commerce/Customers` | Loyalty customers of the Nordvik Club with tier and home city (personal data). | `retail.dim_customer` |
| Sales and Returns | `Nordvik Retail and Commerce/Sales and Returns` | Completed order lines and returned lines - revenue, margin, returns. | `retail.fact_returns`, `retail.fact_sales`, `retail.return_metrics`, `retail.sales_metrics` |

## Business terms

| term | subdomain | definition |
|---|---|---|
| [Net Revenue](pages/2026-10-27-net-revenue.md) | Sales and Returns | Sales value of completed orders after line discounts, in SEK excl. VAT. |
| [Gross Margin](pages/2026-10-27-gross-margin.md) | Sales and Returns | Net revenue minus purchase cost of the goods sold, in SEK and as % of net revenue. |
| [Average Order Value](pages/2026-10-27-average-order-value.md) | Sales and Returns | Net revenue divided by the number of completed orders. |
| [Return Rate](pages/2026-10-27-return-rate.md) | Sales and Returns | Returned units as a share of units sold, by the order date of the sale. |
| [Return Reason](pages/2026-10-27-return-reason.md) | Sales and Returns | Why a customer returned goods: wrong_size, changed_mind, defect or damaged. |
| [Sales Region and Channel](pages/2026-10-27-sales-region-channel.md) | Stores and Channels | Regions STO, GOT, MAL and ONLINE (webshop); channels store and online. |
| [Loyalty Tier](pages/2026-10-27-loyalty-tier.md) | Customers | Tier of the Nordvik Club loyalty programme: none, silver or gold. |
| [Product Category and Brand](pages/2026-10-27-product-category.md) | Product Catalog | Categories electronics, fashion, beauty; 9 brands; subcategories such as phone or perfume. |
