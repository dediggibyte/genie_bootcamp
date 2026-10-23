---
title: Direct Sales
domain: Consumer
subdomain: Direct Sales
subdomain_tag: Consumer/Direct Sales
description: "The DTC webshop: orders, order lines and subscriptions. Every order placed on fjallmark."
owner: Head of DTC & CRM (role)
sources:
  - Lakehouse Industry Data Model — Consumer Goods v2 MVM, domain "consumer", subdomain "direct_sales" (tools/model/consumer_goods_v2_mvm.json)
license: "Derived in part from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (Copyright Databricks, Inc.; Databricks license, see bootcamp/LICENSE.md and bootcamp/NOTICE.md); modified for the Fjallmark Genie bootcamp."
---

# Direct Sales (Consumer)

**The DTC webshop: orders, order lines and subscriptions.** Every order placed on fjallmark.example in Sweden, Norway, Denmark, Finland, Germany and the Netherlands, its lines (one SKU each) and the monthly subscriptions that generate repeat orders. Amounts are in the market's local currency and include VAT and shipping at order level — this is the operational sales view, not the official revenue.

* Governed tag (UC Semantics subdomain): `Consumer/Direct Sales` — applied to the tables below by notebook `05_business_context`.
* Gold tables: `<catalog>.consumer.<table>`; industry model subdomain key `direct_sales`.

## Tables

| Table | Type | Primary key | What it holds |
|---|---|---|---|
| `dtc_order` | Transactional | `dtc_order_id` | Direct-to-Consumer (DTC) order with line-item detail placed by a shopper through owned e-commerce or brand website channels. Captures order header (order number, date, status, channel, shipping/billing address, payment method, subtotal, discount, shipping cost, tax, total, currency, fulfillment reference) and line items (SKU/GTIN, product name, quantity ordered/shipped, unit price, line discount, line total, … |
| `dtc_order_line` | Transactional | `dtc_order_line_id` | Individual line item within a DTC order representing a single SKU purchased. Stores order reference, SKU/GTIN, product name, quantity ordered, quantity shipped, unit price, line discount, line total, promotion code applied, fulfillment status, and return flag. |
| `subscription` | Master | `subscription_id` | Consumer subscription record for DTC auto-replenishment or subscription box programs. Stores subscription plan name, subscribed SKU(s), subscription frequency (weekly, monthly, bi-monthly), subscription status (active, paused, cancelled), start date, next order date, billing cycle, subscription price, discount rate, payment method reference, and cancellation reason if applicable. |

## Main joins (foreign keys inside the bootcamp scope)

* `dtc_order.company_code_id` → `finance.company_code.company_code_id`
* `dtc_order.cost_center_id` → `finance.cost_center.cost_center_id`
* `dtc_order.loyalty_account_id` → `consumer.loyalty_account.loyalty_account_id`
* `dtc_order.ship_to_address_id` → `consumer.address.address_id`
* `dtc_order.shopper_id` → `consumer.shopper.shopper_id`
* `dtc_order.subscription_id` → `consumer.subscription.subscription_id`
* `dtc_order_line.dtc_order_id` → `consumer.dtc_order.dtc_order_id`
* `dtc_order_line.profit_center_id` → `finance.profit_center.profit_center_id`
* `dtc_order_line.shopper_id` → `consumer.shopper.shopper_id`
* `dtc_order_line.subscription_id` → `consumer.subscription.subscription_id`
* `subscription.company_code_id` → `finance.company_code.company_code_id`
* `subscription.delivery_address_id` → `consumer.address.address_id`
* … and 2 more (see the table constraints in Catalog Explorer)

## Questions this subdomain answers

* What is DTC GMV by market and month?
* What is the average order value by loyalty tier?
* What share of order lines is returned?
* How many active subscriptions do we have?

## Pages in this subdomain

* [DTC Gross Merchandise Value](../pages/dtc_gross_merchandise_value.md)
* [Average Order Value](../pages/average_order_value.md)
* [Return Rate](../pages/return_rate.md)
* [DTC Order Status](../pages/dtc_order_status.md)
* [Subscription](../pages/subscription.md)

*Notice: the industry-model descriptions quoted on this page come from the Lakehouse Industry Data Model - Consumer Goods v2 MVM (© Databricks, Inc., Databricks license - see [`bootcamp/LICENSE.md`](../../../../LICENSE.md) and [`bootcamp/NOTICE.md`](../../../../NOTICE.md)); the page is modified for the Fjällmark Genie bootcamp.*
