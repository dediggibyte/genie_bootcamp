---
title: Net Revenue
domain: Finance
subdomain: General Ledger
synonyms:
  - revenue
  - net sales
  - sales
  - turnover
  - top line
  - official revenue
  - finance revenue
  - nettoomsättning
description: "The official revenue of Fjällmark: credits minus debits on GL accounts in account group REVENUE, in group currency EUR, excluding VAT and shipping fees, after DTC returns and B2B trade discounts, for DTC and B2B together."
owner: Group Financial Controller (role)
related_assets:
  - <catalog>.finance.net_revenue_metrics
  - <catalog>.finance.journal_entry_line
  - <catalog>.finance.journal_entry
  - <catalog>.finance.gl_account
  - <catalog>.finance.company_code
  - <catalog>.finance.profit_center
  - <catalog>.consumer.dtc_order
sources:
  - Fjällmark Group Accounting Manual, chapter 3 "Revenue recognition" (fictional policy document)
  - bootcamp/context/domains/finance/pages/net_revenue.md (github.com/dediggibyte/genie_bootcamp)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: finance.journal_entry_line, finance.gl_account"
---

# Net Revenue

## Definition

**Net Revenue** is the revenue Fjällmark reports to the board, in the budget and in bonus
targets. It is taken from the **general ledger**:

> Net Revenue = Σ credits − Σ debits on GL accounts whose `account_group` is **`REVENUE`**,
> in **group currency EUR** (`journal_entry_line.amount_group_currency`), for **posted** journal
> entries, in the requested fiscal period(s).

The REVENUE account group contains four accounts (same numbering in every company code):

| `gl_account.account_number` | `account_name` | Normal side | Effect |
|---|---|---|---|
| 3000 | Revenue - trade customers | credit | + B2B revenue (excl. VAT) |
| 3010 | Revenue - DTC webshop | credit | + DTC revenue (excl. VAT, excl. shipping) |
| 3040 | Trade discounts and rebates | debit | − B2B trade discounts |
| 3050 | Sales returns - DTC | debit | − DTC returns |

**Not** part of Net Revenue: VAT (balance-sheet account 2610), shipping fees charged to consumers
(account 3900, account group `OTHER_INCOME`), loyalty point liabilities.

## Business rules

1. **Currency:** always `amount_group_currency` (EUR). Never add `amount_company_code_currency` or
   `amount_transaction_currency` across company codes — see *Group Currency & FX*.
2. **Sign:** amounts in `journal_entry_line` are stored **positive**; the direction is
   `debit_credit_indicator` (`C` = credit, `D` = debit). Revenue = C − D.
3. **Status:** only documents with `journal_entry.posting_status = 'posted'`.
4. **Period:** use `journal_entry.fiscal_year` and `journal_entry.fiscal_period` (fiscal year =
   calendar year, period = month). The line table has no period columns — join the header.
5. **Entity:** `journal_entry_line.company_code_id` → `company_code.code` (SE01, NO01, DK01, FI01,
   DE01, PL01).
6. **Channel:** DTC vs B2B is visible by account (3010/3050 = DTC, 3000/3040 = B2B) or by
   `profit_center.channel_code` where the line carries a profit centre.

## How to calculate (SQL)

Run in your catalog (`USE CATALOG cpg_<your_short_name>;`).

```sql
-- Net Revenue (EUR) by company code and fiscal period
SELECT cc.code                                   AS company_code,
       je.fiscal_year,
       je.fiscal_period,
       ROUND(SUM(CASE WHEN jel.debit_credit_indicator = 'C' THEN jel.amount_group_currency
                      ELSE -jel.amount_group_currency END), 2) AS net_revenue_eur
FROM finance.journal_entry_line jel
JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
JOIN finance.gl_account   ga ON ga.gl_account_id    = jel.gl_account_id
JOIN finance.company_code cc ON cc.company_code_id  = jel.company_code_id
WHERE ga.account_group = 'REVENUE'
  AND je.posting_status = 'posted'
GROUP BY cc.code, je.fiscal_year, je.fiscal_period
ORDER BY je.fiscal_year, je.fiscal_period, company_code;
```

```sql
-- DTC versus B2B Net Revenue (EUR) per fiscal year, split by revenue account
SELECT je.fiscal_year,
       CASE WHEN ga.account_number IN ('3010', '3050') THEN 'DTC' ELSE 'B2B' END AS channel,
       ROUND(SUM(CASE WHEN jel.debit_credit_indicator = 'C' THEN jel.amount_group_currency
                      ELSE -jel.amount_group_currency END), 2) AS net_revenue_eur
FROM finance.journal_entry_line jel
JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
JOIN finance.gl_account   ga ON ga.gl_account_id    = jel.gl_account_id
WHERE ga.account_group = 'REVENUE'
  AND je.posting_status = 'posted'
GROUP BY ALL
ORDER BY je.fiscal_year, channel;
```

**Governed metric view:** `<catalog>.finance.net_revenue_metrics` implements exactly this rule
(measure for Net Revenue in EUR, plus COGS and Gross Margin) — prefer it in dashboards and Genie.

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `SUM(consumer.dtc_order.order_total_amount)` | Webshop order total = subtotal − discount **+ shipping + VAT**, **before returns**, in **local currency**, DTC only. For the same month DTC Net Revenue is typically **24–30 % lower** than the webshop total (converted to EUR; the webshop figure is about a third higher) — and the raw sum mixes SEK, NOK, DKK and EUR. That number is *DTC order value*, not revenue. |
| `SUM(amount_group_currency)` without the sign | Debit lines (trade discounts 3040, returns 3050) would be **added** instead of subtracted. |
| `SUM(amount_company_code_currency)` across entities | Adds SEK, NOK, DKK, PLN and EUR. |
| Filtering `gl_account.account_type = 'revenue'` | Also includes account 3900 *Shipping fees charged to consumers* (`OTHER_INCOME`). Use `account_group = 'REVENUE'`. |
| Including draft/parked/reversed documents | Only `posting_status = 'posted'` counts. |
| Using `ar_invoice.total_amount` | B2B only, **includes VAT**, local currency. |

If a user explicitly asks for webshop "sales", answer with *DTC Gross Merchandise Value* or DTC
order value, **label it clearly as not Net Revenue**, and state the currency.

## Example questions

* What was Net Revenue in Q2 2026 by company code?
* How did Net Revenue develop month by month in 2026 compared with 2025?
* What share of Net Revenue came from DTC in 2025?
* Why is the webshop's September sales figure higher than finance's revenue?
