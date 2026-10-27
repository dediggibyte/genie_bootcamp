---
title: Fiscal Period
domain: Finance
subdomain: General Ledger
synonyms:
  - fiscal year
  - fiscal month
  - accounting period
  - posting period
  - FY
  - quarter
  - period
  - räkenskapsår
description: "Fjällmark's fiscal year equals the calendar year and each fiscal period is one calendar month (1–12); quarters are periods 1–3, 4–6, 7–9, 10–12. The last closed period in the data is September 2026."
owner: Group Financial Controller (role)
related_assets:
  - <catalog>.finance.journal_entry
  - <catalog>.finance.ar_invoice
  - <catalog>.finance.standard_cost
  - <catalog>.finance.cogs_allocation
sources:
  - Fjällmark Group Accounting Manual, chapter 1 "Financial calendar" (fictional policy document)
  - bootcamp/context/company_profile.md
---

# Fiscal Period

## Definition

* **Fiscal year** = calendar year (January–December). Fiscal year variant `K4` (12 periods, no
  special periods).
* **Fiscal period** = calendar month, numbered **1–12**. Period 3 of 2026 = March 2026.
* **Quarter** = Q1 periods 1–3, Q2 4–6, Q3 7–9, Q4 10–12.
* Data window: 2024-01 … 2026-09. **September 2026 (2026/09) is the last closed period.** Period
  10/2026 is open: it holds only a handful of supplier invoices posted 1–3 October before the extract
  (15 October) — no revenue, no COGS. Leave it out of trends and period comparisons.

## Business rules

1. Finance questions are answered by **fiscal period of posting**:
   `journal_entry.fiscal_year`, `journal_entry.fiscal_period` (integers), not by document date.
2. Other tables with period columns: `ar_invoice.fiscal_year` / `fiscal_period` (INT),
   `cogs_allocation.fiscal_year` / `fiscal_period` (INT), `standard_cost.fiscal_year` /
   `fiscal_period` (**strings**, `'2026'`, `'03'`).
3. Operational tables (webshop, production) have dates/timestamps only — derive the period with
   `year(<date>)` and `month(<date>)`, which matches the fiscal calendar 1:1.
4. "Last month" = September 2026, "this year" / "YTD" = January–September 2026, "last year" = 2025,
   unless the user says otherwise. Compare YTD with the **same months** of the prior year
   (January–September 2025), not the full year 2025.

## How to calculate (SQL)

```sql
-- Year-to-date (Jan–Sep) Net Revenue 2026 vs the same periods of 2025, in EUR
SELECT je.fiscal_year,
       ROUND(SUM(CASE WHEN jel.debit_credit_indicator = 'C' THEN jel.amount_group_currency
                      ELSE -jel.amount_group_currency END), 2) AS net_revenue_ytd_eur
FROM finance.journal_entry_line jel
JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
JOIN finance.gl_account   ga ON ga.gl_account_id    = jel.gl_account_id
WHERE ga.account_group = 'REVENUE'
  AND je.posting_status = 'posted'
  AND je.fiscal_year IN (2025, 2026)
  AND je.fiscal_period BETWEEN 1 AND 9
GROUP BY je.fiscal_year
ORDER BY je.fiscal_year;
```

```sql
-- Quarter label from a fiscal period
SELECT DISTINCT fiscal_year, fiscal_period,
       concat(fiscal_year, '-Q', CAST(ceil(fiscal_period / 3) AS INT)) AS fiscal_quarter
FROM finance.journal_entry
ORDER BY fiscal_year, fiscal_period;
```

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Comparing YTD 2026 (9 months) with full-year 2025 (12 months) | Not like-for-like. |
| Grouping journal entries by `document_date` | Finance reports by posting period. |
| `standard_cost.fiscal_period = 3` | The column is a string `'03'`. |
| Including period 10/2026 in a trend | It is an open period with a few AP invoices only; the last closed period is 2026/09. |

## Example questions

* What was Net Revenue in Q3 2026 compared with Q3 2025?
* Show COGS by fiscal period for 2025.
* What is year-to-date gross margin?
