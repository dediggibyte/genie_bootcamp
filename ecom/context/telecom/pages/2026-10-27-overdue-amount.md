---
title: Overdue Amount
domain: Telecommunications and Media
subdomain: Billing
synonyms:
  - overdue
  - arrears
  - late payments
description: Invoiced amount excl. VAT of invoices past their due date and not paid.
related_assets:
  - <catalog>.telecom.billing_metrics
  - <catalog>.telecom.fact_billing
sources:
  - Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/
---

# Overdue Amount

## Definition

An invoice is **overdue** when its due date (invoice date + 30 days) has passed and it is not paid (`payment_status = 'overdue'`). **Open** invoices are not yet due. June invoices are all paid or open. **Paid share %** = paid invoices / invoices × 100.

## How to calculate

Use the governed metric view `<catalog>.telecom.billing_metrics` (measure `overdue_amount_sek`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
SELECT MEASURE(overdue_amount_sek) AS overdue_amount_sek
FROM <catalog>.telecom.billing_metrics
WHERE billing_month = DATE'2026-05-01'
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**2 293 SEK** (May 2026 invoices, all data, for a user who may see every row; from `data/2026-10-27-expected-answers.json`).

## Common wrong answers

* Counting open (not yet due) invoices as overdue.

## Related terms

* [Billed Revenue](2026-10-27-billed-revenue.md)

## Example questions

* Overdue amount by segment
* What share of June invoices is paid?
