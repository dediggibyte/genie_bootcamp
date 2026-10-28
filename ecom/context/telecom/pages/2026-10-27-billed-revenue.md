---
title: Billed Revenue
domain: Telecommunications and Media
subdomain: Billing
synonyms:
  - revenue
  - billing
  - turnover
  - intäkter
description: Invoiced amount excl. VAT of the monthly invoices.
related_assets:
  - <catalog>.telecom.billing_metrics
  - <catalog>.telecom.fact_billing
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Billed Revenue

## Definition

**Billed revenue** = Σ `amount_excl_vat_sek` of `telecom.fact_billing` (one invoice per subscription and billing month = monthly fee + extra mobile usage). VAT (25 %) is not revenue.

## How to calculate

Use the governed metric view `<catalog>.telecom.billing_metrics` (measure `billed_revenue_sek`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(billed_revenue_sek) AS billed_revenue_sek
FROM <catalog>.telecom.billing_metrics
WHERE billing_month = DATE'2026-06-01'
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**10 304 SEK** (June 2026, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Using amount incl. VAT.

## Related terms

* [ARPU](2026-10-27-arpu.md)
* [Overdue Amount](2026-10-27-overdue-amount.md)

## Example questions

* Billed revenue by plan type
* Billed revenue per month
