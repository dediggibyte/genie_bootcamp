---
title: Gross Margin
domain: Finance
subdomain: General Ledger
synonyms:
  - gross profit
  - GM
  - gross margin %
  - GM%
  - margin
  - bruttomarginal
  - bruttovinst
description: "Gross Margin = Net Revenue − COGS, in EUR from the general ledger; Gross Margin % = Gross Margin ÷ Net Revenue."
owner: Group Financial Controller (role)
related_assets:
  - <catalog>.finance.net_revenue_metrics
  - <catalog>.finance.journal_entry_line
  - <catalog>.finance.journal_entry
  - <catalog>.finance.gl_account
  - <catalog>.finance.company_code
  - <catalog>.finance.profit_center
sources:
  - Fjällmark Group Accounting Manual, chapter 7 "Management P&L" (fictional policy document)
  - bootcamp/context/domains/finance/pages/net_revenue.md
  - bootcamp/context/domains/finance/pages/cogs.md
---

# Gross Margin

## Definition

> **Gross Margin (EUR)** = *Net Revenue* (account group `REVENUE`, C − D) − *COGS*
> (account group `COGS`, D − C), both in `amount_group_currency`, posted documents only.
>
> **Gross Margin %** = Gross Margin ÷ Net Revenue × 100.

Fjällmark's group gross margin is about **52 %** (monthly 50–53 %; standard cost is 35–55 % of the
net selling price, plus production variances). Shipping income (account 3900) and operating expenses
(marketing, freight, salaries) are **below** gross margin.

## Business rules

1. Both components come from the GL — never mix webshop revenue with GL COGS.
2. Calculate the % from the summed EUR amounts (ratio of sums), **not** as an average of monthly or
   entity percentages.
3. At company-code level, margins of producing entities (SE01, FI01, PL01 carry production
   variances) and pure selling entities (NO01, DK01, DE01) are not directly comparable; the group
   total is the meaningful number.
4. **By brand:** group the GL lines by `profit_center.brand_code` of the posting profit centre
   (brand × channel centres for revenue and standard COGS, plant centres for production variances) —
   the brand name is the `name` of the profit centre whose `code` equals that `brand_code`
   (BJORKO → Björkö Pantry, KALLKALLA → Kallkälla, MJUKCARE → Mjuk Care).

## How to calculate (SQL)

```sql
-- Gross margin (EUR and %) by fiscal year and period, whole group
WITH pl AS (
  SELECT je.fiscal_year,
         je.fiscal_period,
         SUM(CASE WHEN ga.account_group = 'REVENUE'
                  THEN CASE WHEN jel.debit_credit_indicator = 'C' THEN jel.amount_group_currency ELSE -jel.amount_group_currency END
                  ELSE 0 END) AS net_revenue_eur,
         SUM(CASE WHEN ga.account_group = 'COGS'
                  THEN CASE WHEN jel.debit_credit_indicator = 'D' THEN jel.amount_group_currency ELSE -jel.amount_group_currency END
                  ELSE 0 END) AS cogs_eur
  FROM finance.journal_entry_line jel
  JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
  JOIN finance.gl_account   ga ON ga.gl_account_id    = jel.gl_account_id
  WHERE je.posting_status = 'posted'
    AND ga.account_group IN ('REVENUE', 'COGS')
  GROUP BY je.fiscal_year, je.fiscal_period
)
SELECT fiscal_year,
       fiscal_period,
       ROUND(net_revenue_eur, 2)                                   AS net_revenue_eur,
       ROUND(cogs_eur, 2)                                          AS cogs_eur,
       ROUND(net_revenue_eur - cogs_eur, 2)                        AS gross_margin_eur,
       ROUND(100 * (net_revenue_eur - cogs_eur) / NULLIF(net_revenue_eur, 0), 1) AS gross_margin_pct
FROM pl
ORDER BY fiscal_year, fiscal_period;
```

Governed: `<catalog>.finance.net_revenue_metrics` (Gross Margin EUR and Gross Margin % measures).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `AVG(gross_margin_pct)` over months or entities | Unweighted average of ratios; use Σ margin ÷ Σ revenue. |
| Webshop `order_total_amount` − GL COGS | Different scope (DTC vs all), VAT included, local currency. |
| `dtc_order_line.line_net_amount − cost_of_goods_sold` as company margin | That is a DTC basket margin at standard cost in local currency — label it as such. |
| Including account 3900 shipping income | Not revenue (account group `OTHER_INCOME`). |

## Example questions

* What was gross margin % in 2025 versus 2024?
* Which month in 2026 had the lowest gross margin and why?
* How did the Poznań quality incident in March 2026 affect gross margin?
* What is the gross margin by brand?
