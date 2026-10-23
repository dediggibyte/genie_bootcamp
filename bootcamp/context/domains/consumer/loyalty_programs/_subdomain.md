---
title: Loyalty Programs
domain: Consumer
subdomain: Loyalty Programs
subdomain_tag: Consumer/Loyalty Programs
description: "The Fjällmark Friends loyalty programme. One programme (Fjällmark Friends), four tiers (Bronze, Silver, Gold, Platinum — ranked 1 to 4), one loyalty account per enrolled shopper, and every points movement (earn, redeem, adjust, expire)."
owner: Head of DTC & CRM (role)
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "consumer", subdomain "loyalty_programs" (tools/model/consumer_goods_v2_mvm.json)
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# Loyalty Programs (Consumer)

**The Fjällmark Friends loyalty programme.** One programme (Fjällmark Friends), four tiers (Bronze, Silver, Gold, Platinum — ranked 1 to 4), one loyalty account per enrolled shopper, and every points movement (earn, redeem, adjust, expire). 100 points are worth 1 EUR.

* Governed tag (UC Semantics subdomain): `Consumer/Loyalty Programs` — applied to the tables below by notebook `05_business_context`.
* Gold tables: `<catalog>.consumer.<table>`; industry model subdomain key `loyalty_programs`.

## Tables

| Table | Type | Primary key | What it holds |
|---|---|---|---|
| `loyalty_account` | Master | `loyalty_account_id` | Loyalty program membership account and transaction history for a consumer enrolled in a CPG brand loyalty or rewards program. Captures account master (program name, membership tier, enrollment date, points balance, lifetime points earned/redeemed, tier qualification spend, tier review date, status) and individual points movement events (earn, redeem, adjust, expire — with points amount, triggering event, associated … |
| `loyalty_transaction` | Transactional | `loyalty_transaction_id` | Individual points movement event within a loyalty account — earn, redeem, adjust, or expire. Records points amount, triggering event (purchase, referral, review, birthday bonus, promotion), associated order reference, balance snapshot (before/after), processing status, and transaction timestamp. |
| `loyalty_program` | Master | `loyalty_program_id` | Master reference table for loyalty_program. Referenced by loyalty_program_id. |
| `loyalty_tier` | Master | `loyalty_tier_id` | Master reference table for loyalty_tier. Referenced by tier_id. |

## Main joins (foreign keys inside the bootcamp scope)

* `loyalty_account.consent_record_id` → `consumer.consent_record.consent_record_id`
* `loyalty_account.loyalty_program_id` → `consumer.loyalty_program.loyalty_program_id`
* `loyalty_account.loyalty_tier_id` → `consumer.loyalty_tier.loyalty_tier_id`
* `loyalty_account.shopper_id` → `consumer.shopper.shopper_id`
* `loyalty_transaction.gl_account_id` → `finance.gl_account.gl_account_id`
* `loyalty_transaction.loyalty_account_id` → `consumer.loyalty_account.loyalty_account_id`
* `loyalty_transaction.loyalty_program_id` → `consumer.loyalty_program.loyalty_program_id`
* `loyalty_transaction.loyalty_tier_id` → `consumer.loyalty_tier.loyalty_tier_id`
* `loyalty_transaction.shopper_id` → `consumer.shopper.shopper_id`
* `loyalty_program.company_code_id` → `finance.company_code.company_code_id`
* `loyalty_tier.loyalty_program_id` → `consumer.loyalty_program.loyalty_program_id`

## Questions this subdomain answers

* How many members are in each tier?
* Do Gold and Platinum members spend more per order?
* How many points were redeemed last quarter?

## Pages in this subdomain

* [Loyalty Tier](../pages/loyalty_tier.md)

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
