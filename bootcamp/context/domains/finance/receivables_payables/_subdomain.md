---
title: Receivables Payables
domain: Finance
subdomain: Receivables Payables
subdomain_tag: Finance/Receivables Payables
description: "Money customers owe us and money we owe suppliers. B2B customer invoices and their payments (accounts receivable) and supplier invoices and payments (accounts payable)."
owner: Group Financial Controller (role)
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "finance", subdomain "receivables_payables" (tools/model/consumer_goods_v2_mvm.json)
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# Receivables Payables (Finance)

**Money customers owe us and money we owe suppliers.** B2B customer invoices and their payments (accounts receivable) and supplier invoices and payments (accounts payable). Receivables carry due date, outstanding balance, dispute flag and an aging bucket as of the 30 September 2026 close. Amounts are in the invoice's local currency.

* Governed tag (UC Semantics subdomain): `Finance/Receivables Payables` — applied to the tables below by notebook `05_business_context`.
* Gold tables: `<catalog>.finance.<table>`; industry model subdomain key `receivables_payables`.

## Tables

| Table | Type | Primary key | What it holds |
|---|---|---|---|
| `ar_invoice` | Transactional | `ar_invoice_id` | Accounts receivable master record representing the full trade receivable lifecycle for consumer goods sales to retailers, distributors, and wholesalers. Owns invoice creation, payment terms, cash receipt application, partial payments, deductions/short-payments, clearing, and write-offs. |
| `ar_payment` | Transactional | `ar_payment_id` | Accounts receivable payment record capturing cash receipts from trade customers against outstanding AR invoices. Records payment date, payment method (ACH, wire, check, EDI 820), amount received, currency, exchange rate, bank account, clearing document reference, partial payment flag, and deduction/short-payment details. |
| `ap_invoice` | Transactional | `ap_invoice_id` | Accounts payable master record representing the full trade payable lifecycle for raw materials, packaging, contract manufacturing, and indirect goods/services. Owns invoice receipt, three-way match verification, payment scheduling, payment execution, early payment discount capture, and clearing. |
| `ap_payment` | Transactional | `ap_payment_id` | Accounts payable payment record capturing outgoing payments to suppliers for raw materials, packaging, and services. Records payment date, payment method (ACH, wire, check, EDI 820), payment amount, currency, exchange rate, bank account, payment run ID, clearing document, early payment discount taken, and payment block release authorization. |

## Main joins (foreign keys inside the bootcamp scope)

* `ar_invoice.company_code_id` → `finance.company_code.company_code_id`
* `ar_invoice.gl_account_id` → `finance.gl_account.gl_account_id`
* `ar_invoice.shopper_id` → `consumer.shopper.shopper_id`
* `ar_payment.ar_invoice_id` → `finance.ar_invoice.ar_invoice_id`
* `ar_payment.company_code_id` → `finance.company_code.company_code_id`
* `ar_payment.cost_center_id` → `finance.cost_center.cost_center_id`
* `ar_payment.gl_account_id` → `finance.gl_account.gl_account_id`
* `ar_payment.shopper_id` → `consumer.shopper.shopper_id`
* `ap_invoice.company_code_id` → `finance.company_code.company_code_id`
* `ap_invoice.cost_center_id` → `finance.cost_center.cost_center_id`
* `ap_invoice.gl_account_id` → `finance.gl_account.gl_account_id`
* `ap_invoice.profit_center_id` → `finance.profit_center.profit_center_id`
* `ap_payment.ap_invoice_id` → `finance.ap_invoice.ap_invoice_id`
* `ap_payment.company_code_id` → `finance.company_code.company_code_id`
* … and 3 more (see the table constraints in Catalog Explorer)

## Questions this subdomain answers

* What is DSO by company code?
* How much receivable is overdue more than 60 days?
* Which company code has the most disputed or overdue invoices?

## Pages in this subdomain

* [DSO (Days Sales Outstanding)](../pages/dso.md)
* [Overdue Receivable](../pages/overdue_receivable.md)

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
