---
title: Billing
domain: Telecommunications and Media
subdomain: Billing
subdomain_key: billing
subdomain_tag: Nordvik Telecommunications and Media/Billing
description: "Monthly invoices per subscription: amounts, due dates, payment status."
objects:
  - <catalog>.telecom.billing_metrics
  - <catalog>.telecom.fact_billing
---

# Billing (Telecommunications and Media)

Monthly invoices per subscription: amounts, due dates, payment status.

* **Governed tag / UC subdomain:** `Nordvik Telecommunications and Media/Billing` - applied to the objects below by notebook 05c.
* **Business terms:** [Billed Revenue](../pages/2026-10-27-billed-revenue.md), [ARPU](../pages/2026-10-27-arpu.md), [Overdue Amount](../pages/2026-10-27-overdue-amount.md)

## Tables and metric views

| object | type |
|---|---|
| `<catalog>.telecom.billing_metrics` | metric view |
| `<catalog>.telecom.fact_billing` | fact |
