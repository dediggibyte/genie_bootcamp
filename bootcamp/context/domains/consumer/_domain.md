---
title: Consumer
domain: Consumer
domain_tag: Consumer
subtitle: Shoppers, the DTC webshop, loyalty and consent
description: Owns everything about end consumers of Fjällmark's brands — shopper profiles and households, consent and privacy preferences, the "Fjällmark Friends" loyalty programme, subscriptions and the direct-to-consumer webshop orders.
business_owner: Head of DTC & CRM (role)
technical_owner: Consumer Data Product Team (role)
schema: <catalog>.consumer
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "consumer" (tools/model/consumer_goods_v2_mvm.json)
  - bootcamp/context/company_profile.md
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# Consumer

**Industry model description:** *"SSOT for all end consumers, shoppers, households, and loyalty
program members in B2C and DTC channels. Manages consumer profiles, preferences, purchase history,
segmentation, NPS scores, CLTV calculations, consent and privacy preferences (GDPR/CCPA), and
contact data."* (Division: business. References: GDPR, CCPA.)

## Purpose at Fjällmark

The Consumer domain answers **who buys from us directly, how often, how much, and whether we may
contact them**. It is the operational view of the DTC webshop `fjallmark.example` (SE, NO, DK, FI,
DE, NL). Its money amounts are **order amounts in the market's local currency** — useful for
basket, conversion and loyalty analysis, but **not** the official revenue (that is Finance's
*Net Revenue*).

| | |
|---|---|
| Business owner | Head of DTC & CRM (role) |
| Technical owner | Consumer Data Product Team (role) |
| Gold schema | `<catalog>.consumer` — governed tag `Consumer` |
| Privacy | `shopper` and `address` contain personal data → column masks; rows filtered by company code (notebook 03) |

## Subdomains

| Subdomain (tag) | What it covers | Tables |
|---|---|---|
| Customer Identity (`Consumer/Customer Identity`) | The shopper golden record, households, addresses, preferences, consent | `shopper`, `household`, `address`, `preference`, `consent_record` |
| Loyalty Programs (`Consumer/Loyalty Programs`) | Fjällmark Friends programme, tiers, member accounts, points movements | `loyalty_program`, `loyalty_tier`, `loyalty_account`, `loyalty_transaction` |
| Direct Sales (`Consumer/Direct Sales`) | Webshop orders, order lines, subscriptions | `dtc_order`, `dtc_order_line`, `subscription` |

## Key tables

* `dtc_order` — order header: `order_date`, `order_status`, `currency_code`, `subtotal_amount`,
  `discount_amount`, `shipping_amount`, `tax_amount`, `order_total_amount`, `company_code_id`,
  `shopper_id`, `loyalty_account_id`, `return_flag`.
* `dtc_order_line` — one SKU on an order: `quantity_ordered`, `unit_price`, `line_subtotal`,
  `line_discount_amount`, `line_net_amount` (after discount, before VAT), `tax_amount`,
  `line_total_amount`, `is_returned`, `cost_of_goods_sold`, `sku_id`.
* `shopper` — one row per consumer: `cltv_segment`, `lifecycle_status`, `country_code`,
  `last_purchase_date`, `loyalty_tier_id`. Contains personal data (masked).
* `loyalty_account` / `loyalty_tier` — membership and tier (Bronze, Silver, Gold, Platinum).
* `consent_record` — GDPR consent history per shopper and consent type.
* `subscription` — monthly auto-replenishment plans.

## Key metrics (Pages)

| Page | One-liner |
|---|---|
| [DTC Gross Merchandise Value](pages/dtc_gross_merchandise_value.md) | Value of webshop orders before discounts, VAT and shipping, local currency |
| [Average Order Value](pages/average_order_value.md) | Net merchandise value per non-cancelled order |
| [Active Shopper](pages/active_shopper.md) | Shopper with ≥ 1 non-cancelled order in the last 12 months |
| [Return Rate](pages/return_rate.md) | Share of order lines (or value) returned |
| [DTC Order Status](pages/dtc_order_status.md) | Which orders count as sales, which are cancelled |
| [Loyalty Tier](pages/loyalty_tier.md) | Bronze / Silver / Gold / Platinum membership level |
| [CLTV Segment](pages/cltv_segment.md) | Customer-lifetime-value segment (high_value … at_risk, churned) |
| [Consent / GDPR](pages/consent_gdpr.md) | Whether we may contact or profile a shopper |
| [Subscription](pages/subscription.md) | Recurring auto-replenishment plans and their status |

Governed metric view: `<catalog>.consumer.dtc_sales_metrics` (GMV, net sales in local currency,
orders, units, active shoppers, AOV, discount rate, return rate — by month, market, currency,
brand, category, loyalty tier, CLTV segment). Industry metric views:
`<catalog>.consumer.dtc_order_metrics`, `dtc_order_line_metrics`, `shopper_metrics`,
`loyalty_account_metrics`, `subscription_metrics`, `consent_record_metrics`.

## Rules of thumb for Genie

1. Webshop amounts are **local currency** (`currency_code`) — group by currency or convert to EUR
   before comparing markets; never sum SEK and EUR.
2. "Sales" / "revenue" → say that the official figure is Finance *Net Revenue*; webshop figures are
   *GMV* or *DTC net sales*.
3. Exclude cancelled orders from sales, AOV and active-shopper counts.
4. Never list shopper names, e-mails, phone numbers or birth dates; analyse in aggregate.
5. Some orders are guest checkouts whose `shopper_id` is not in `shopper` → use LEFT JOIN.
6. "Market" = the order's **ship-to country** (`dtc_order.ship_to_address_id` → `address.country_code`,
   equal to `shopper.country_code` for registered shoppers) — not the company code or the currency
   (DE01 / EUR covers Germany and the Netherlands).

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
