---
title: DSO (Days Sales Outstanding)
domain: Finance
subdomain: Receivables Payables
synonyms:
  - DSO
  - days sales outstanding
  - debtor days
  - collection period
  - receivable days
  - kundfordringsdagar
description: "How many days of credit sales are tied up in open trade receivables: open AR at the reporting date ÷ (credit sales billed in the last quarter ÷ days in the quarter), per company code, as of 2026-09-30 (Q3 2026 = 92 days)."
owner: Group Credit Manager (role)
related_assets:
  - <catalog>.finance.receivables_metrics
  - <catalog>.finance.ar_invoice
  - <catalog>.finance.ar_payment
  - <catalog>.finance.company_code
  - <catalog>.finance.ar_invoice_metrics
sources:
  - Fjällmark Credit & Collections Policy, section 4 "KPIs" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: finance.ar_invoice"
---

# DSO — Days Sales Outstanding

## Definition

Fjällmark uses the **quarter-based simple DSO** (count-back over the last quarter):

> **DSO** = open receivables at the reporting date ÷ (credit sales billed in the last quarter ÷ number
> of days in that quarter)

* **Open receivables** = Σ `ar_invoice.outstanding_balance` at the reporting date
  (`outstanding_balance = total_amount − amount_received − write_off_amount`, 0 when settled).
* **Credit sales** = Σ `ar_invoice.total_amount` (the amount the customer owes, incl. VAT) of
  invoices with `billing_date` in the quarter that ends on the reporting date.
* **Reporting date** = **2026-09-30** (last closed period) → quarter = **July–September 2026 = 92 days**.

Receivables are **B2B trade receivables** (retail and wholesale customers). Webshop orders are paid
up-front by card or wallet and are not in DSO.

Reference values at 2026-09-30: **group DSO ≈ 39 days**; **DE01 ≈ 66 days** (SE01, NO01, DK01, FI01
and PL01 between 31 and 38 days). The German outlier is driven by invoices that the drugstore
customer Alpina Drogerie has disputed since June 2026. Normal payment terms are 30 days (45 days in
DE/NL), so a DSO near the terms is healthy.

## Business rules

1. Calculate DSO **per company code** in local currency (a ratio needs no FX). For a **group** DSO,
   convert both open AR and credit sales to EUR with the September 2026 rate (see *Group Currency &
   FX*), add them up, then divide.
2. Disputed invoices (`dispute_flag = true`, `invoice_status = 'disputed'`) stay **in** DSO — they are
   still unpaid — but are reported separately so collections can act.
3. Exclude cancelled invoices (`invoice_status = 'cancelled'`) from credit sales, should any exist.
4. The `dso_aging_bucket` column classifies days past due; it is not DSO.

## How to calculate (SQL)

```sql
-- DSO per company code as of 2026-09-30 (local currency ratio; Q3 2026 = 92 days)
WITH ar AS (
  SELECT i.company_code_id,
         SUM(i.outstanding_balance)                                                       AS open_ar,
         SUM(CASE WHEN i.billing_date BETWEEN DATE'2026-07-01' AND DATE'2026-09-30'
                   AND lower(i.invoice_status) <> 'cancelled' THEN i.total_amount ELSE 0 END) AS billed_q3
  FROM finance.ar_invoice i
  WHERE i.billing_date <= DATE'2026-09-30'
  GROUP BY i.company_code_id
)
SELECT cc.code                                     AS company_code,
       cc.currency_code,
       ROUND(ar.open_ar, 2)                        AS open_ar_local,
       ROUND(ar.billed_q3, 2)                      AS credit_sales_q3_local,
       ROUND(ar.open_ar / (ar.billed_q3 / 92), 1)  AS dso_days
FROM ar
JOIN finance.company_code cc ON cc.company_code_id = ar.company_code_id
ORDER BY dso_days DESC;
```

```sql
-- Group DSO in EUR (both components translated with the September 2026 finance rate)
WITH fx AS (
  SELECT jel.company_code_id, AVG(jel.exchange_rate) AS eur_rate
  FROM finance.journal_entry_line jel
  JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
  WHERE je.fiscal_year = 2026 AND je.fiscal_period = 9
  GROUP BY jel.company_code_id
)
SELECT ROUND(SUM(i.outstanding_balance * fx.eur_rate), 0)                                   AS open_ar_eur,
       ROUND(SUM(CASE WHEN i.billing_date >= DATE'2026-07-01' THEN i.total_amount * fx.eur_rate ELSE 0 END), 0) AS billed_q3_eur,
       ROUND(SUM(i.outstanding_balance * fx.eur_rate)
             / (SUM(CASE WHEN i.billing_date >= DATE'2026-07-01' THEN i.total_amount * fx.eur_rate ELSE 0 END) / 92), 1) AS group_dso_days
FROM finance.ar_invoice i
JOIN fx ON fx.company_code_id = i.company_code_id
WHERE i.billing_date <= DATE'2026-09-30';
```

Governed: `<catalog>.finance.receivables_metrics` (open AR, overdue AR, DSO approximation, disputes).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `AVG(datediff(payment_date, billing_date))` | That is *average days to pay* of **paid** invoices; it ignores what is still open (the disputed DE01 invoices). |
| Summing open AR of all company codes in local currency for a group DSO | Adds SEK, NOK, DKK, PLN and EUR — convert to EUR first. |
| Averaging the company-code DSOs | Unweighted; the group DSO is Σ open AR (EUR) ÷ (Σ Q3 credit sales (EUR) ÷ 92). |
| Using `net_amount` for credit sales but `outstanding_balance` (incl. VAT) for AR | Inconsistent bases; both should include VAT (`total_amount`). |
| Using today's date as reporting date | The data ends with the 2026-09-30 close. |

## Example questions

* What is DSO by company code at the end of September 2026?
* Why is DSO in Germany so much higher than in the rest of the group?
* How has DE01's DSO developed since June 2026?
