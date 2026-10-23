---
title: Finance
domain: Finance
domain_tag: Finance
subtitle: Legal entities, general ledger, receivables and product costing
description: Owns financial accounting and reporting for the Fjällmark group — company codes, chart of accounts, journal entries, receivables and payables, standard cost and COGS. The authoritative source for revenue, margin and cash KPIs in group currency EUR.
business_owner: Group Financial Controller (role)
technical_owner: Finance Data Product Team (role)
schema: <catalog>.finance
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "finance" (tools/model/consumer_goods_v2_mvm.json)
  - bootcamp/context/company_profile.md
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# Finance

**Industry model description:** *"Owns financial planning, accounting, and reporting including
general ledger, accounts payable/receivable, cost accounting, COGS allocation, EBITDA reporting,
DSO/DIO tracking, budgeting, revenue recognition, and SOX-compliant financial controls and audit
trails."* (Division: corporate. References: SOX, GAAP.)

## Purpose at Fjällmark

Finance is the **single source of truth for money**. When a question is about revenue, margin,
cost, receivables or cash, the answer comes from this domain, in **group currency EUR**, by
**company code** and **fiscal period** — unless the user explicitly asks for a local-currency or
operational (webshop) view.

| | |
|---|---|
| Business owner | Group Financial Controller (role) |
| Technical owner | Finance Data Product Team (role) |
| Gold schema | `<catalog>.finance` — governed tag `Finance` |
| Row-level security | Analysts see only the company codes they are mapped to (notebook 03) |

## Subdomains

| Subdomain (tag) | What it covers | Tables |
|---|---|---|
| Organizational Accounting (`Finance/Organizational Accounting`) | The structure money is booked against | `company_code`, `gl_account`, `cost_center`, `profit_center`, `ledger` |
| General Ledger (`Finance/General Ledger`) | Every posting, plus product costing | `journal_entry`, `journal_entry_line`, `standard_cost`, `cogs_allocation` |
| Receivables Payables (`Finance/Receivables Payables`) | Customer invoices and payments, supplier invoices and payments | `ar_invoice`, `ar_payment`, `ap_invoice`, `ap_payment` |

## Key tables

* `journal_entry_line` — one debit or credit line of a GL document. Amounts are **positive**; the
  direction is `debit_credit_indicator` (`D`/`C`). Carries the amount in transaction, company-code
  and **group currency** (`amount_group_currency`, EUR).
* `journal_entry` — the document header: `posting_date`, `fiscal_year`, `fiscal_period`,
  `posting_status`, `company_code_id`.
* `gl_account` — chart of accounts; `account_group` (REVENUE, OTHER_INCOME, COGS, OPEX, ASSET,
  LIABILITY, EQUITY) decides which P&L line a posting belongs to.
* `company_code` — the six legal entities (`code` = SE01, NO01, DK01, FI01, DE01, PL01).
* `ar_invoice` — B2B trade receivables (local currency) with due date, outstanding balance,
  dispute flag and aging bucket, as of 30 September 2026.
* `standard_cost` / `cogs_allocation` — standard cost per SKU and plant, and the cost/variance split.

## Key metrics (Pages)

| Page | One-liner |
|---|---|
| [Net Revenue](pages/net_revenue.md) | **The** revenue: GL revenue accounts, credit − debit, EUR, excl. VAT, after returns and trade discounts |
| [Group Currency & FX](pages/group_currency_fx.md) | EUR is the only currency you may add across company codes |
| [COGS](pages/cogs.md) | GL accounts in account group COGS (standard cost + production variances), EUR |
| [Gross Margin](pages/gross_margin.md) | Net Revenue − COGS, and as % of Net Revenue |
| [Standard Cost](pages/standard_cost.md) | Planned cost per unit of a SKU, by cost component |
| [DSO](pages/dso.md) | Days Sales Outstanding = open receivables ÷ credit sales × days |
| [Overdue Receivable](pages/overdue_receivable.md) | Open invoice balance past its due date |
| [Company Code](pages/company_code.md) | The legal entity every transaction belongs to |
| [Fiscal Period](pages/fiscal_period.md) | Fiscal year = calendar year, period = month |

Governed metric views: `<catalog>.finance.net_revenue_metrics` (Net Revenue, COGS, Gross Margin
in EUR) and `<catalog>.finance.receivables_metrics` (open / overdue AR, DSO, disputes). The
industry metric views `<catalog>.finance.journal_entry_line_metrics`,
`<catalog>.finance.ar_invoice_metrics`, `<catalog>.finance.standard_cost_metrics` and
`<catalog>.finance.cogs_allocation_metrics` are available for generic analysis.

## Rules of thumb for Genie

1. Revenue questions → **Net Revenue** in EUR from the GL, never DTC order totals.
2. Across company codes → **`amount_group_currency`** only.
3. Only **posted** documents count (`journal_entry.posting_status = 'posted'`).
4. Periods → `journal_entry.fiscal_year` / `fiscal_period`.
5. Receivables are a snapshot **as of 2026-09-30**.

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
