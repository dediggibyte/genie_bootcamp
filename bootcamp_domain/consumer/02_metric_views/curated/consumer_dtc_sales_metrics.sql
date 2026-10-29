-- ================================================================================================
-- CURATED BOOTCAMP METRIC VIEW (hand-written) - consumer.dtc_sales_metrics
-- Built on tables of the Lakehouse Industry Data Model "Consumer Goods v2 MVM" (Copyright Databricks,
-- Inc.; Databricks license - see LICENSE.md and NOTICE.md in the bootcamp folder, copies of
-- tools/model/). Created by notebooks/job_tasks/02a_create_metric_views.py (job task metric_views), which
-- replaces ${catalog} with your catalog and only creates / replaces the view when it is missing or
-- its YAML changed.
--
-- Webshop (DTC) sales KPIs, computed at ORDER-LINE grain (consumer.dtc_order_line): every measure is
-- a sum / count / distinct count over lines, so nothing is double counted when the order header,
-- shopper, loyalty tier, ship-to address, company code or brand are joined (all many-to-one).
-- Definitions follow the business glossary (bootcamp/context/domains/consumer/pages/):
--   GMV                 = SUM(line_subtotal)        unit price x quantity, excl. VAT, before discounts
--   DTC net sales       = SUM(line_net_amount)      after line discounts, excl. VAT and shipping
--   AOV                 = DTC net sales / orders    (ratio of sums)
--   Return rate (value) = returned line net value / line net value
--   Active shoppers     = distinct REGISTERED shoppers with an order in the selected period
-- Cancelled orders are excluded (global filter). Amounts in the order's LOCAL currency (*_local,
-- always group by currency_code) or converted to EUR (*_eur) with the finance monthly rate of the
-- order's company code and order month (journal_entry_line.exchange_rate). NOT finance revenue:
-- the official revenue is finance.net_revenue_metrics (GL, EUR, after returns).
-- ================================================================================================

CREATE OR REPLACE VIEW ${catalog}.consumer.`dtc_sales_metrics`
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: >-
    Fjällmark webshop (DTC) sales KPIs at order-line grain: GMV, DTC net sales, discounts, units,
    orders, average order value, return rate, active shoppers and merchandise margin, by month,
    market, currency, brand, product category, loyalty tier and CLTV segment. Cancelled orders are
    excluded. *_local measures are in the order's local currency (SEK, NOK, DKK, EUR) - always group
    by currency_code; *_eur measures are converted with the finance monthly FX rate. This is an
    operational webshop view, NOT the official revenue (use finance.net_revenue_metrics for Net
    Revenue).
  source: ${catalog}.consumer.dtc_order_line
  filter: lower(hdr.order_status) <> 'cancelled'
  joins:
    - name: hdr
      source: ${catalog}.consumer.dtc_order
      'on': source.dtc_order_id = hdr.dtc_order_id
      joins:
        - name: shopper_dim
          source: ${catalog}.consumer.shopper
          'on': hdr.shopper_id = shopper_dim.shopper_id
          joins:
            - name: tier_dim
              source: ${catalog}.consumer.loyalty_tier
              'on': shopper_dim.loyalty_tier_id = tier_dim.loyalty_tier_id
        - name: ship_to_dim
          source: ${catalog}.consumer.address
          'on': hdr.ship_to_address_id = ship_to_dim.address_id
        - name: company_dim
          source: ${catalog}.finance.company_code
          'on': hdr.company_code_id = company_dim.company_code_id
        - name: fx_dim
          source: |-
            SELECT jel.company_code_id, je.fiscal_year, je.fiscal_period, AVG(jel.exchange_rate) AS eur_rate
            FROM ${catalog}.finance.journal_entry_line jel
            JOIN ${catalog}.finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
            WHERE je.posting_status = 'posted'
            GROUP BY jel.company_code_id, je.fiscal_year, je.fiscal_period
          'on': >-
            hdr.company_code_id = fx_dim.company_code_id
            AND year(hdr.order_date) = fx_dim.fiscal_year
            AND month(hdr.order_date) = fx_dim.fiscal_period
    - name: brand_dim
      source: ${catalog}.finance.profit_center
      'on': source.brand_code = brand_dim.code
  dimensions:
    - name: order_month
      expr: CAST(DATE_TRUNC('MONTH', hdr.order_date) AS DATE)
      display_name: Order month
      comment: First day of the month the order was placed (dtc_order.order_date, local market time).
      synonyms: [month, sales month, period]
    - name: order_quarter
      expr: CONCAT(CAST(YEAR(hdr.order_date) AS STRING), '-Q', CAST(QUARTER(hdr.order_date) AS STRING))
      display_name: Order quarter
      comment: Calendar quarter of the order date, e.g. 2026-Q3 (fiscal year = calendar year).
      synonyms: [quarter]
    - name: order_year
      expr: YEAR(hdr.order_date)
      display_name: Order year
      comment: Calendar year of the order date (fiscal year = calendar year).
      synonyms: [year]
    - name: order_date
      expr: CAST(hdr.order_date AS DATE)
      display_name: Order date
      comment: Day the order was placed.
      synonyms: [date, day]
    - name: market
      expr: COALESCE(hdr.ship_to_dim.country_code, hdr.shopper_dim.country_code, 'Unknown (guest)')
      display_name: Market
      comment: >-
        Webshop market = ship-to country of the order (ISO alpha-3: SWE, NOR, DNK, FIN, DEU, NLD), falling
        back to the shopper's country; guest checkouts without address are 'Unknown (guest)'. Not the
        same as company code or currency (DE01 / EUR covers Germany and the Netherlands).
      synonyms: [country, ship-to country, webshop market, region]
    - name: currency_code
      expr: source.currency_code
      display_name: Currency
      comment: Order currency = market currency (SEK, NOK, DKK, EUR). Group *_local measures by it.
      synonyms: [currency, local currency]
    - name: company_code
      expr: hdr.company_dim.code
      display_name: Company code
      comment: Selling legal entity of the order (SE01, NO01, DK01, FI01, DE01).
      synonyms: [legal entity, entity, company]
    - name: sales_channel
      expr: hdr.channel_code
      display_name: Webshop channel
      comment: Webshop touchpoint of the order (brand_website, mobile_app, dtc_subscription, social_commerce, voice_commerce).
      synonyms: [channel, touchpoint, device channel]
    - name: brand_code
      expr: source.brand_code
      display_name: Brand code
      comment: Brand of the order line (BJORKO, KALLKALLA, MJUKCARE).
    - name: brand
      expr: COALESCE(brand_dim.name, source.brand_code)
      display_name: Brand
      comment: Brand name of the order line (Björkö Pantry, Kallkälla, Mjuk Care) from the brand profit centre.
      synonyms: [brand name, label]
    - name: product_category
      expr: source.product_category_code
      display_name: Product category
      comment: Product category code of the order line (e.g. GRANOLA, SPARKLING, HAIRCARE).
      synonyms: [category, product group]
    - name: product_name
      expr: source.product_name
      display_name: Product
      comment: Product (SKU) name of the order line.
      synonyms: [product, sku, item, article]
    - name: loyalty_tier
      expr: COALESCE(hdr.shopper_dim.tier_dim.tier_name, 'Non-member')
      display_name: Loyalty tier
      comment: >-
        Current Fjällmark Friends tier of the ordering shopper (Bronze, Silver, Gold, Platinum);
        shoppers without a tier and guest checkouts are 'Non-member'.
      synonyms: [tier, membership tier, member status, loyalty level]
    - name: loyalty_tier_rank
      expr: COALESCE(hdr.shopper_dim.tier_dim.tier_rank, 0)
      display_name: Loyalty tier rank
      comment: Sort key for loyalty_tier (0 = Non-member, 1 = Bronze ... 4 = Platinum).
    - name: customer_type
      expr: CASE WHEN hdr.shopper_dim.shopper_id IS NULL THEN 'Guest checkout' ELSE 'Registered shopper' END
      display_name: Customer type
      comment: Registered shopper (profile in consumer.shopper) or guest checkout (no shopper profile).
      synonyms: [guest, registered]
    - name: cltv_segment
      expr: COALESCE(hdr.shopper_dim.cltv_segment, 'unknown (guest)')
      display_name: CLTV segment
      comment: Customer-lifetime-value segment of the shopper (high_value, mid_value, low_value, at_risk, churned).
      synonyms: [customer segment, value segment, clv segment]
    - name: order_status
      expr: hdr.order_status
      display_name: Order status
      comment: Order lifecycle status (pending, confirmed, processing, shipped, delivered, returned); cancelled orders are excluded.
      synonyms: [status]
    - name: order_type
      expr: CASE WHEN hdr.subscription_order_flag THEN 'Subscription delivery' ELSE 'One-off order' END
      display_name: Order type
      comment: Subscription delivery or one-off order (dtc_order.subscription_order_flag).
      synonyms: [subscription, subscription order]
    - name: line_returned
      expr: CASE WHEN source.is_returned THEN 'Returned' ELSE 'Kept' END
      display_name: Line returned
      comment: Whether the order line was sent back by the consumer (dtc_order_line.is_returned).
      synonyms: [returned, return flag]
    - name: return_reason
      expr: source.return_reason_code
      display_name: Return reason
      comment: Return reason code of a returned line.
  measures:
    - name: order_count
      expr: COUNT(DISTINCT source.dtc_order_id)
      display_name: Orders
      comment: Number of distinct non-cancelled webshop orders.
      synonyms: [orders, number of orders, order volume]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: order_line_count
      expr: COUNT(source.dtc_order_line_id)
      display_name: Order lines
      comment: Number of order lines.
      synonyms: [lines]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: units_ordered
      expr: SUM(source.quantity_ordered)
      display_name: Units ordered
      comment: Units (EA) ordered.
      synonyms: [units, quantity, volume]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: gmv_local
      expr: SUM(source.line_subtotal)
      display_name: GMV (local currency)
      comment: >-
        Gross merchandise value = unit price x quantity, excl. VAT, before discounts, shipping and
        returns, in the order's LOCAL currency - only meaningful per currency_code.
      synonyms: [gross merchandise value local, webshop sales local]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: discount_local
      expr: SUM(source.line_discount_amount)
      display_name: Discounts (local currency)
      comment: Line discounts (loyalty member discount and promotions) in local currency.
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: dtc_net_sales_local
      expr: SUM(source.line_net_amount)
      display_name: DTC net sales (local currency)
      comment: GMV minus discounts, excl. VAT and shipping, before returns, in local currency - only meaningful per currency_code.
      synonyms: [net merchandise value local, webshop net sales local]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: gmv_eur
      expr: SUM(source.line_subtotal * hdr.fx_dim.eur_rate)
      display_name: GMV (EUR)
      comment: >-
        Gross merchandise value converted to EUR with the finance monthly rate (company code, order
        month); safe to add across markets. Not revenue.
      synonyms: [GMV, gross merchandise value, webshop sales, DTC sales, online sales, e-commerce sales]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: discount_eur
      expr: SUM(source.line_discount_amount * hdr.fx_dim.eur_rate)
      display_name: Discounts (EUR)
      comment: Line discounts converted to EUR.
      synonyms: [discounts, discount amount]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: dtc_net_sales_eur
      expr: SUM(source.line_net_amount * hdr.fx_dim.eur_rate)
      display_name: DTC net sales (EUR)
      comment: >-
        Net merchandise value (after discounts, excl. VAT and shipping, before returns) in EUR. Finance
        DTC Net Revenue is lower (returns, not yet shipped orders) - see finance.net_revenue_metrics.
      synonyms: [DTC net sales, net merchandise value, webshop net sales, net sales webshop]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: returned_net_sales_eur
      expr: SUM(source.line_net_amount * hdr.fx_dim.eur_rate) FILTER (WHERE source.is_returned)
      display_name: Returned net sales (EUR)
      comment: Net value of the order lines that were returned, in EUR.
      synonyms: [returns value, returned value]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: avg_order_value_local
      expr: MEASURE(dtc_net_sales_local) / MEASURE(order_count)
      display_name: AOV (local currency)
      comment: Average order value = DTC net sales / orders, local currency - only meaningful per currency_code.
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: avg_order_value_eur
      expr: MEASURE(dtc_net_sales_eur) / MEASURE(order_count)
      display_name: AOV (EUR)
      comment: Average order value = net merchandise value (excl. VAT and shipping) per non-cancelled order, in EUR (ratio of sums).
      synonyms: [AOV, average order value, average basket, basket size, average order size]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: discount_rate_pct
      expr: 100 * MEASURE(discount_eur) / MEASURE(gmv_eur)
      display_name: Discount rate %
      comment: Discounts as a percentage of GMV (0-100, EUR basis).
      synonyms: [discount rate, discount %]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: return_rate_pct
      expr: 100 * MEASURE(returned_net_sales_eur) / MEASURE(dtc_net_sales_eur)
      display_name: Return rate % (value)
      comment: Value-based return rate = returned line net value / line net value, in percent (0-100, EUR basis). The default return rate.
      synonyms: [return rate, returns %, refund rate, return percentage]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: line_return_rate_pct
      expr: 100 * COUNT(source.dtc_order_line_id) FILTER (WHERE source.is_returned) / COUNT(source.dtc_order_line_id)
      display_name: Return rate % (lines)
      comment: Share of order lines that were returned, in percent (0-100).
      synonyms: [line return rate]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: active_shoppers
      expr: COUNT(DISTINCT hdr.shopper_dim.shopper_id)
      display_name: Active shoppers
      comment: >-
        Distinct registered shoppers with at least one non-cancelled order in the selected period
        (guest checkouts are not counted). The glossary's default window is the 12 months to 2026-09-30.
      synonyms: [active customers, buying customers, active buyers, unique shoppers]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: orders_per_active_shopper
      expr: COUNT(DISTINCT source.dtc_order_id) FILTER (WHERE hdr.shopper_dim.shopper_id IS NOT NULL) / MEASURE(active_shoppers)
      display_name: Orders per active shopper
      comment: Order frequency = orders of registered shoppers / active shoppers in the selected period.
      synonyms: [order frequency, purchase frequency]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: merchandise_margin_pct
      expr: 100 * (MEASURE(dtc_net_sales_eur) - SUM(source.cost_of_goods_sold * hdr.fx_dim.eur_rate)) / MEASURE(dtc_net_sales_eur)
      display_name: Merchandise margin % (webshop)
      comment: >-
        Webshop basket margin = (net sales - standard cost of the units on the line) / net sales, EUR
        basis. Operational DTC indicator, not the P&L gross margin (finance.net_revenue_metrics).
      synonyms: [basket margin, webshop margin]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
$$;
