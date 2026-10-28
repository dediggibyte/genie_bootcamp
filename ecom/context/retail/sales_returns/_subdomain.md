---
title: Sales and Returns
domain: Retail and Commerce
subdomain: Sales and Returns
subdomain_key: sales_returns
subdomain_tag: Nordvik Retail and Commerce/Sales and Returns
description: Completed order lines and returned lines - revenue, margin, returns.
objects:
  - <catalog>.retail.fact_returns
  - <catalog>.retail.fact_sales
  - <catalog>.retail.return_metrics
  - <catalog>.retail.sales_metrics
---

# Sales and Returns (Retail and Commerce)

Completed order lines and returned lines - revenue, margin, returns.

* **Governed tag / UC subdomain:** `Nordvik Retail and Commerce/Sales and Returns` - applied to the objects below by notebook 05a.
* **Business terms:** [Net Revenue](../pages/2026-10-27-net-revenue.md), [Gross Margin](../pages/2026-10-27-gross-margin.md), [Average Order Value](../pages/2026-10-27-average-order-value.md), [Return Rate](../pages/2026-10-27-return-rate.md), [Return Reason](../pages/2026-10-27-return-reason.md)

## Tables and metric views

| object | type |
|---|---|
| `<catalog>.retail.fact_returns` | fact |
| `<catalog>.retail.fact_sales` | fact |
| `<catalog>.retail.return_metrics` | metric view |
| `<catalog>.retail.sales_metrics` | metric view |
