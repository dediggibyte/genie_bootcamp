---
title: Customer Identity
domain: Consumer
subdomain: Customer Identity
subdomain_tag: Consumer/Customer Identity
description: "Who our consumers are and what they allowed us to do with their data. The shopper golden record (one row per consumer across the webshop and loyalty programme), the households and addresses they belong to, their stated preferences, and the full GDPR consent history."
owner: Head of DTC & CRM (role)
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "consumer", subdomain "customer_identity" (tools/model/consumer_goods_v2_mvm.json)
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# Customer Identity (Consumer)

**Who our consumers are and what they allowed us to do with their data.** The shopper golden record (one row per consumer across the webshop and loyalty programme), the households and addresses they belong to, their stated preferences, and the full GDPR consent history. This is where personal data lives: names, e-mails, phones, birth dates and postal codes are masked for most users, and analysis should be done in aggregate.

* Governed tag (UC Semantics subdomain): `Consumer/Customer Identity` — applied to the tables below by notebook `05_business_context`.
* Gold tables: `<catalog>.consumer.<table>`; industry model subdomain key `customer_identity`.

## Tables

| Table | Type | Primary key | What it holds |
|---|---|---|---|
| `shopper` | Master | `shopper_id` | Golden master record for every end consumer and shopper across B2C and DTC channels. Stores consumer identity (full name, date of birth, gender), contact details (primary email, phone), language and currency preferences, acquisition metadata (channel, date), consumer lifecycle status (active/inactive/opted-out), identity verification status, and source system references. |
| `household` | Master | `household_id` | Household unit grouping multiple shoppers who share a residence and purchasing decisions. Captures household demographics (estimated size, income band, life stage), formation date, status, and primary shopper designation. |
| `address` | Master | `address_id` | Physical and digital address records associated with a consumer/shopper. Stores address type (billing, shipping, home, work), street lines, city, state/province, postal code, country, geocoordinates (latitude/longitude), address validation status, address source, effective date, and expiry date. |
| `preference` | Master | `preference_id` | Unified consumer preference profile capturing product, brand, channel, and communication preferences. Stores preference category (product category, brand, flavor, fragrance, pack size, channel, communication channel, contact frequency, preferred time of day, preferred language), preference value, opt-in/opt-out status, preference source (declared via web/app/call-center vs. |
| `consent_record` | Master | `consent_record_id` | Formal consent and privacy preference record for a consumer capturing GDPR, CCPA, and other regulatory consent obligations, including full audit history of all consent changes. Stores consent type (marketing email, SMS, push notification, data sharing, profiling, cookies), current consent status (granted, withdrawn, pending), consent version, capture method (web form, app, in-store, call center), capture timestamp, … |

## Main joins (foreign keys inside the bootcamp scope)

* `shopper.loyalty_program_id` → `consumer.loyalty_program.loyalty_program_id`
* `shopper.loyalty_tier_id` → `consumer.loyalty_tier.loyalty_tier_id`
* `household.loyalty_program_id` → `consumer.loyalty_program.loyalty_program_id`
* `household.loyalty_tier_id` → `consumer.loyalty_tier.loyalty_tier_id`
* `household.shopper_id` → `consumer.shopper.shopper_id`
* `address.household_id` → `consumer.household.household_id`
* `address.shopper_id` → `consumer.shopper.shopper_id`
* `preference.consent_record_id` → `consumer.consent_record.consent_record_id`
* `preference.household_id` → `consumer.household.household_id`
* `preference.loyalty_program_id` → `consumer.loyalty_program.loyalty_program_id`
* `preference.shopper_id` → `consumer.shopper.shopper_id`
* … and 3 more (see the table constraints in Catalog Explorer)

## Questions this subdomain answers

* How many shoppers do we have per market and CLTV segment?
* How many shoppers have granted marketing e-mail consent?
* How many shoppers are at risk of churning?

## Pages in this subdomain

* [Active Shopper](../pages/active_shopper.md)
* [CLTV Segment](../pages/cltv_segment.md)
* [Consent / GDPR](../pages/consent_gdpr.md)

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
