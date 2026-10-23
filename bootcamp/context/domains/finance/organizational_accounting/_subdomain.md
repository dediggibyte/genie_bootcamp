---
title: Organizational Accounting
domain: Finance
subdomain: Organizational Accounting
subdomain_tag: Finance/Organizational Accounting
description: "The structure that money is booked against. Six legal entities (company codes SE01, NO01, DK01, FI01, DE01, PL01), the chart of accounts (about 25 GL accounts per company code with shared numbering), cost centres, profit centres (brands, channels, plants) and ledgers."
owner: Group Financial Controller (role)
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "finance", subdomain "organizational_accounting" (tools/model/consumer_goods_v2_mvm.json)
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# Organizational Accounting (Finance)

**The structure that money is booked against.** Six legal entities (company codes SE01, NO01, DK01, FI01, DE01, PL01), the chart of accounts (about 25 GL accounts per company code with shared numbering), cost centres, profit centres (brands, channels, plants) and ledgers. Use these tables to label and filter the general ledger.

* Governed tag (UC Semantics subdomain): `Finance/Organizational Accounting` — applied to the tables below by notebook `05_business_context`.
* Gold tables: `<catalog>.finance.<table>`; industry model subdomain key `organizational_accounting`.

## Tables

| Table | Type | Primary key | What it holds |
|---|---|---|---|
| `cost_center` | Master | `cost_center_id` | Master record for organizational cost centers used in SAP S/4HANA CO module. Defines the financial accountability units within the CPG enterprise — brand units, manufacturing plants, regional sales offices, and shared service centers. |
| `profit_center` | Master | `profit_center_id` | Master record for profit centers representing autonomous business segments within the consumer goods enterprise — product lines, brands, or geographic business units. Tracks revenue, cost, and profitability at a granular level below the legal entity. |
| `gl_account` | Master | `gl_account_id` | General ledger chart of accounts master for the consumer goods enterprise. Defines every account in the COA including P&L accounts (revenue, COGS, trade spend, marketing, SG&A), balance sheet accounts (inventory, AR, AP, fixed assets), and statistical accounts. |
| `ledger` | Master | `ledger_id` | Financial ledger master defining the accounting ledgers maintained in the enterprise — leading ledger (IFRS/GAAP), parallel ledgers for local GAAP, and extension ledgers for management reporting. Each ledger record captures ledger type, accounting principle, currency type, fiscal year variant, and posting period variant. |
| `company_code` | Master | `company_code_id` | Master reference table for company_code. Referenced by company_code_id. |

## Main joins (foreign keys inside the bootcamp scope)

* `cost_center.company_code_id` → `finance.company_code.company_code_id`
* `cost_center.gl_account_id` → `finance.gl_account.gl_account_id`
* `cost_center.profit_center_id` → `finance.profit_center.profit_center_id`
* `profit_center.company_code_id` → `finance.company_code.company_code_id`
* `profit_center.gl_account_id` → `finance.gl_account.gl_account_id`
* `gl_account.company_code_id` → `finance.company_code.company_code_id`
* `ledger.company_code_id` → `finance.company_code.company_code_id`
* `ledger.gl_account_id` → `finance.gl_account.gl_account_id`

## Questions this subdomain answers

* Which company codes report in which currency?
* Which GL accounts make up net revenue?
* Net revenue by profit center?

## Pages in this subdomain

* [Company Code](../pages/company_code.md)

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
