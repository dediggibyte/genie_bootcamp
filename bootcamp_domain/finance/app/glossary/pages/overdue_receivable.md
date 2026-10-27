---
title: Overdue Receivable
domain: Finance
subdomain: Receivables Payables
synonyms:
  - overdue AR
  - past due
  - overdue invoices
  - aged receivables
  - AR aging
  - förfallna fordringar
  - late payments
description: "The unpaid balance of customer invoices whose due date has passed at the reporting date (2026-09-30), analysed in aging buckets by days past due."
owner: Group Credit Manager (role)
related_assets:
  - <catalog>.finance.receivables_metrics
  - <catalog>.finance.ar_invoice
  - <catalog>.finance.company_code
  - <catalog>.finance.ar_invoice_metrics
sources:
  - Fjällmark Credit & Collections Policy, section 3 "Dunning and aging" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: finance.ar_invoice (due_date, outstanding_balance, dso_aging_bucket)"
---

# Overdue Receivable

## Definition

An invoice is **overdue** when, at the reporting date, it still has an open balance and its due date
has passed:

> overdue ⇔ `outstanding_balance > 0` **and** `due_date < reporting date` (2026-09-30)
>
> **Overdue receivable** = Σ `outstanding_balance` of overdue invoices.
>
> **Days past due** = `datediff(reporting date, due_date)`.

Aging buckets (same as `ar_invoice.dso_aging_bucket`): `current` (not yet due), `1_30_days`,
`31_60_days`, `61_90_days`, `over_90_days`, `over_120_days`.

## Business rules

1. Reporting date = **2026-09-30** (the snapshot in `dso_aging_bucket` is as of that close).
2. Amounts are in the invoice's local currency (`currency_code`); for totals across company codes
   convert to EUR with the September 2026 rate (see *Group Currency & FX*).
3. **Disputed** invoices (`dispute_flag = true`, `invoice_status = 'disputed'`, reason in
   `dispute_reason`) are overdue like any other but are excluded from automatic dunning — always show
   them separately. Other statuses: `open`, `partially_paid`, `paid`, `written_off`.
4. Written-off invoices (`write_off_amount` > 0, `invoice_status = 'written_off'`) are no longer
   receivables.
5. Customer names live in the sales domain's trade-account master, which is only part of the full
   industry model; in the bootcamp analyse by company code, `trade_account_id`, status and dispute flag.

## How to calculate (SQL)

```sql
-- Overdue receivables by company code and aging bucket at 2026-09-30 (local currency)
SELECT cc.code AS company_code,
       cc.currency_code,
       CASE WHEN datediff(DATE'2026-09-30', i.due_date) <= 30  THEN '1_30_days'
            WHEN datediff(DATE'2026-09-30', i.due_date) <= 60  THEN '31_60_days'
            WHEN datediff(DATE'2026-09-30', i.due_date) <= 90  THEN '61_90_days'
            WHEN datediff(DATE'2026-09-30', i.due_date) <= 120 THEN 'over_90_days'
            ELSE 'over_120_days' END                         AS aging_bucket,
       COUNT(*)                                              AS overdue_invoices,
       SUM(CASE WHEN i.dispute_flag THEN 1 ELSE 0 END)       AS disputed_invoices,
       ROUND(SUM(i.outstanding_balance), 2)                  AS overdue_balance_local
FROM finance.ar_invoice i
JOIN finance.company_code cc ON cc.company_code_id = i.company_code_id
WHERE i.outstanding_balance > 0
  AND i.due_date < DATE'2026-09-30'
GROUP BY ALL
ORDER BY company_code, aging_bucket;
```

Governed: `<catalog>.finance.receivables_metrics` (overdue AR measure, aging bucket dimension).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `invoice_status = 'open'` as "overdue" | Open ≠ overdue; most open invoices are not yet due (`current`). |
| `SUM(total_amount)` of overdue invoices | Ignores partial payments; use `outstanding_balance`. |
| Comparing to `current_date()` | The extract ends 2026-09-30; "today" in this dataset is the reporting date. |
| Summing SEK/NOK/DKK/PLN/EUR balances | Convert to EUR first. |

## Example questions

* How much receivable is overdue by more than 60 days, by company code?
* Which company code has the largest overdue balance and how much of it is disputed?
* How many invoices of DE01 are in dispute since June 2026?
