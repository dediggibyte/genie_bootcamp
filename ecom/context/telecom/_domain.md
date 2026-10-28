---
title: Telecommunications and Media
domain: Telecommunications and Media
domain_tag: Nordvik Telecommunications and Media
business_unit: Nordvik Connect
subtitle: Plans, subscriptions, billing and usage of the operator
description: Nordvik Connect is a mobile, fibre and TV / streaming operator for consumers and businesses. Owns price plans, customers and subscriptions, monthly billing and usage - the source for billed revenue, ARPU, overdue amounts, data usage and streaming hours.
business_owner: Head of Connect Consumer and Business (role)
technical_owner: Connect Data Product Team (role)
schema: <catalog>.telecom
genie_agent: Nordvik Connect Analyst
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Telecommunications and Media (Nordvik Connect)

Nordvik Connect is a mobile, fibre and TV / streaming operator for consumers and businesses. Owns price plans, customers and subscriptions, monthly billing and usage - the source for billed revenue, ARPU, overdue amounts, data usage and streaming hours.

* **Governed tag / UC domain:** `Nordvik Telecommunications and Media` - applied to the gold schema `<catalog>.telecom` by notebook
  `notebooks/2026-10-27-05-context-common.py` (run through `05c`), which can also create the domain itself.
* **Data:** billing and usage months 2026-05 and 2026-06. Amounts in SEK excl. VAT. All data is synthetic.
* **Genie Agent:** *Nordvik Connect Analyst* (`genie/2026-10-27-telecom-agent.json`, created by notebook 04).

## Subdomains

| subdomain | governed tag | what it holds | gold objects |
|---|---|---|---|
| Plans and Products | `Nordvik Telecommunications and Media/Plans and Products` | Mobile, fibre, TV / streaming plans and bundles with their fees. | `telecom.dim_plan` |
| Customers and Subscriptions | `Nordvik Telecommunications and Media/Customers and Subscriptions` | Consumer and business customers and their subscriptions. | `telecom.dim_customer`, `telecom.dim_subscription` |
| Billing | `Nordvik Telecommunications and Media/Billing` | Monthly invoices per subscription: amounts, due dates, payment status. | `telecom.billing_metrics`, `telecom.fact_billing` |
| Usage | `Nordvik Telecommunications and Media/Usage` | Monthly data, voice, SMS and streaming usage per subscription. | `telecom.fact_usage`, `telecom.usage_metrics` |

## Business terms

| term | subdomain | definition |
|---|---|---|
| [Billed Revenue](pages/2026-10-27-billed-revenue.md) | Billing | Invoiced amount excl. VAT of the monthly invoices. |
| [ARPU](pages/2026-10-27-arpu.md) | Billing | Billed revenue divided by billed subscriptions, per month. |
| [Overdue Amount](pages/2026-10-27-overdue-amount.md) | Billing | Invoiced amount excl. VAT of invoices past their due date and not paid. |
| [Active Subscription](pages/2026-10-27-active-subscription.md) | Customers and Subscriptions | A subscription with status active (no end date). |
| [Customer Segment](pages/2026-10-27-customer-segment.md) | Customers and Subscriptions | consumer or business; the scope of the governance row filter. |
| [Data Usage](pages/2026-10-27-data-usage.md) | Usage | Data used in GB per subscription and month, mobile and fixed. |
| [Streaming Hours and Add-ons](pages/2026-10-27-streaming-hours.md) | Plans and Products | Hours streamed; plans can include Netflix, Spotify, Disney+ or Max. |
