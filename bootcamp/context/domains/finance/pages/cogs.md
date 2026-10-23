---
title: COGS
domain: Finance
subdomain: General Ledger
synonyms:
  - cost of goods sold
  - cost of sales
  - product cost
  - COGS EUR
  - production variance
  - varukostnad
description: "Cost of goods sold: debits minus credits on GL accounts in account group COGS (4000 standard cost of goods sold, 4100 production variances), in group currency EUR, for posted documents."
owner: Group Financial Controller (role)
related_assets:
  - <catalog>.finance.net_revenue_metrics
  - <catalog>.finance.journal_entry_line
  - <catalog>.finance.journal_entry
  - <catalog>.finance.gl_account
  - <catalog>.finance.standard_cost
  - <catalog>.finance.cogs_allocation
  - <catalog>.consumer.dtc_order_line
sources:
  - Fjällmark Group Accounting Manual, chapter 5 "Inventory and cost of sales" (fictional policy document)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: finance.journal_entry_line, finance.gl_account, finance.cogs_allocation"
---

# COGS (Cost of Goods Sold)

## Definition

> COGS = Σ debits − Σ credits on GL accounts with `gl_account.account_group = 'COGS'`, in EUR
> (`journal_entry_line.amount_group_currency`), for posted journal entries.

| `account_number` | `account_name` | Meaning |
|---|---|---|
| 4000 | Cost of goods sold - standard cost | Units sold × standard cost (see *Standard Cost*) |
| 4100 | Production variances | Actual − standard production cost (yield, price, efficiency variances); can be negative |

COGS is an expense, so its normal side is **debit** (the opposite of revenue).

## Business rules

1. Same rules as Net Revenue for currency (EUR), status (`posted`) and period (`journal_entry`
   fiscal year/period) — but sign is **D − C**.
2. COGS covers DTC **and** B2B sales, all brands and entities.
3. Production variances are booked by the **producing** entity (e.g. PL01 for the Poznań plant),
   while revenue is booked by the **selling** entity — compare margin at group or brand level, not
   plant entity vs. selling entity.
4. Line-level `consumer.dtc_order_line.cost_of_goods_sold` is the **standard cost of the units on a
   webshop line in local currency** — useful for DTC basket margin, not for the P&L.

## How to calculate (SQL)

```sql
-- COGS (EUR) by company code and fiscal period, split standard cost vs variances
SELECT cc.code AS company_code,
       je.fiscal_year,
       je.fiscal_period,
       ROUND(SUM(CASE WHEN ga.account_number = '4000'
                      THEN CASE WHEN jel.debit_credit_indicator = 'D' THEN jel.amount_group_currency ELSE -jel.amount_group_currency END
                      ELSE 0 END), 2) AS cogs_standard_eur,
       ROUND(SUM(CASE WHEN ga.account_number = '4100'
                      THEN CASE WHEN jel.debit_credit_indicator = 'D' THEN jel.amount_group_currency ELSE -jel.amount_group_currency END
                      ELSE 0 END), 2) AS production_variance_eur,
       ROUND(SUM(CASE WHEN jel.debit_credit_indicator = 'D' THEN jel.amount_group_currency
                      ELSE -jel.amount_group_currency END), 2) AS cogs_eur
FROM finance.journal_entry_line jel
JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
JOIN finance.gl_account   ga ON ga.gl_account_id    = jel.gl_account_id
JOIN finance.company_code cc ON cc.company_code_id  = jel.company_code_id
WHERE ga.account_group = 'COGS'
  AND je.posting_status = 'posted'
GROUP BY ALL
ORDER BY je.fiscal_year, je.fiscal_period, company_code;
```

Governed: `<catalog>.finance.net_revenue_metrics` (COGS EUR measure).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `SUM(amount_group_currency)` with C − D (revenue sign) | Turns COGS negative. |
| `SUM(dtc_order_line.cost_of_goods_sold)` as company COGS | DTC only, standard cost only (no variances), local currency. |
| `SUM(cogs_allocation.total_cost_amount)` | Cost-estimate / allocation records per SKU and period, not posted P&L cost. |
| Ignoring account 4100 | Misses production variances — e.g. the March 2026 spike at PL01 when Poznań line PL-POZ-L2 lost yield. |

## Example questions

* What was COGS by month in 2026?
* Why did COGS jump for PL01 in March 2026?
* How large were production variances compared with standard COGS last year?
