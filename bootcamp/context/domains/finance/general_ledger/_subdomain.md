---
title: General Ledger
domain: Finance
subdomain: General Ledger
subdomain_tag: Finance/General Ledger
description: "Every financial posting, plus product costing. Journal entry headers (posting date, fiscal year/period, status) and lines (GL account, debit/credit indicator, amounts in transaction, company-code and group currency EUR), the standard cost of every SKU, and the COGS allocations that split cost into components and variances."
owner: Group Financial Controller (role)
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "finance", subdomain "general_ledger" (tools/model/consumer_goods_v2_mvm.json)
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# General Ledger (Finance)

**Every financial posting, plus product costing.** Journal entry headers (posting date, fiscal year/period, status) and lines (GL account, debit/credit indicator, amounts in transaction, company-code and group currency EUR), the standard cost of every SKU, and the COGS allocations that split cost into components and variances. Net Revenue, COGS and Gross Margin are calculated here.

* Governed tag (UC Semantics subdomain): `Finance/General Ledger` — applied to the tables below by notebook `05_business_context`.
* Gold tables: `<catalog>.finance.<table>`; industry model subdomain key `general_ledger`.

## Tables

| Table | Type | Primary key | What it holds |
|---|---|---|---|
| `journal_entry` | Transactional | `journal_entry_id` | Core general ledger journal entry header capturing every financial posting in the consumer goods enterprise. Records document type (vendor invoice, customer payment, goods issue, payroll posting, accrual, reversal), posting date, fiscal period, company code, ledger, currency, exchange rate, reference document, and SOX-compliant posting user and approval chain. |
| `journal_entry_line` | Transactional | `journal_entry_line_id` | Individual line items of a general ledger journal entry. Each line captures the GL account, cost center, profit center, WBS element, business area, debit/credit indicator, amount in transaction currency, amount in company code currency, amount in group currency, tax code, and assignment field. |
| `cogs_allocation` | Transactional | `cogs_allocation_id` | Product costing and COGS allocation master for CPG manufacturing. Owns both standard cost estimates (planned) and actual cost allocations for finished goods, semi-finished goods, and raw materials. |
| `standard_cost` | Master | `standard_cost_id` | Standard cost master record for finished goods, semi-finished goods, and raw materials used in CPG manufacturing. Stores the cost estimate per SKU/material including cost component split (raw material, packaging, direct labor, machine overhead, fixed overhead, freight-in), costing version, validity period, plant, costing lot size, and release status. |

## Main joins (foreign keys inside the bootcamp scope)

* `journal_entry.company_code_id` → `finance.company_code.company_code_id`
* `journal_entry.cost_center_id` → `finance.cost_center.cost_center_id`
* `journal_entry.gl_account_id` → `finance.gl_account.gl_account_id`
* `journal_entry.ledger_id` → `finance.ledger.ledger_id`
* `journal_entry.profit_center_id` → `finance.profit_center.profit_center_id`
* `journal_entry_line.company_code_id` → `finance.company_code.company_code_id`
* `journal_entry_line.cost_center_id` → `finance.cost_center.cost_center_id`
* `journal_entry_line.gl_account_id` → `finance.gl_account.gl_account_id`
* `journal_entry_line.journal_entry_id` → `finance.journal_entry.journal_entry_id`
* `journal_entry_line.profit_center_id` → `finance.profit_center.profit_center_id`
* `cogs_allocation.cost_center_id` → `finance.cost_center.cost_center_id`
* `cogs_allocation.manufacturing_facility_id` → `manufacturing.manufacturing_facility.manufacturing_facility_id`
* … and 5 more (see the table constraints in Catalog Explorer)

## Questions this subdomain answers

* What was net revenue by company code in Q2 2026?
* What is gross margin % by month?
* Why did COGS spike for PL01 in March 2026?

## Pages in this subdomain

* [Net Revenue](../pages/net_revenue.md)
* [Group Currency & FX](../pages/group_currency_fx.md)
* [COGS](../pages/cogs.md)
* [Gross Margin](../pages/gross_margin.md)
* [Standard Cost](../pages/standard_cost.md)
* [Fiscal Period](../pages/fiscal_period.md)

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
