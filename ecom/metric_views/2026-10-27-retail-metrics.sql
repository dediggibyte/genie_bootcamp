-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - METRIC VIEWS of the Retail and Commerce domain:
--   retail.sales_metrics   - order-line grain (retail.fact_sales): revenue, units, orders, AOV,
--                            gross margin, return rate
--   retail.return_metrics  - return grain (retail.fact_returns): returns by reason, refunds
-- Created by notebooks/job_tasks/2026-10-27-02a-create-metric-views.py (job task metric_views);
-- ${catalog} is replaced by the job parameter `catalog`.
-- Definitions = ecom/data/README.md "Business definitions"; the totals are in
-- data/2026-10-27-expected-answers.json (retail). Measures are sums / counts at the fact grain and
-- ratios are ratios of sums, so they are never averaged twice. Percent measures return 0-100.
-- Governance: the views follow the row filters and column masks of their source tables - a user
-- scoped to GOT sees GOT numbers; gross margin is NULL for users who may not read unit_cost_sek.
-- ================================================================================================

CREATE OR REPLACE VIEW ${catalog}.retail.sales_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: >-
    Nordvik Retail sales KPIs at order-line grain, Jan-Jun 2026, completed orders only, SEK excl. VAT:
    net revenue, units, orders, average order value, discounts, gross margin and return rate; by month,
    region, store, channel, brand, category, product, payment method and loyalty tier.
  source: ${catalog}.retail.fact_sales
  joins:
    - name: product_dim
      source: ${catalog}.retail.dim_product
      'on': source.product_id = product_dim.product_id
    - name: store_dim
      source: ${catalog}.retail.dim_store
      'on': source.store_id = store_dim.store_id
    - name: customer_dim
      source: ${catalog}.retail.dim_customer
      'on': source.customer_id = customer_dim.customer_id
    - name: returns_dim
      source: |-
        SELECT order_line_id, SUM(quantity) AS returned_units, SUM(refund_sek) AS refund_sek
        FROM ${catalog}.retail.fact_returns
        GROUP BY order_line_id
      'on': source.order_line_id = returns_dim.order_line_id
  dimensions:
    - name: order_date
      expr: source.order_date
      display_name: Order date
      comment: Date of the order.
      synonyms: [date, sales date]
    - name: order_month
      expr: CAST(DATE_TRUNC('MONTH', source.order_date) AS DATE)
      display_name: Order month
      comment: First day of the month of the order (2026-01-01 .. 2026-06-01).
      synonyms: [month, sales month]
    - name: store_region
      expr: source.store_region
      display_name: Region
      comment: Sales region - STO (Stockholm), GOT (Göteborg), MAL (Malmö), ONLINE (webshop).
      synonyms: [region, area, market]
    - name: channel
      expr: source.channel
      display_name: Channel
      comment: store or online (webshop).
      synonyms: [sales channel, online vs store]
    - name: store_name
      expr: store_dim.store_name
      display_name: Store
      comment: Store name, e.g. Nordvik Retail Göteborg Nordstan; Nordvik Webshop for online orders.
      synonyms: [shop, outlet]
    - name: store_city
      expr: store_dim.city
      display_name: Store city
      comment: City of the store.
    - name: brand_name
      expr: product_dim.brand_name
      display_name: Brand
      comment: Brand of the product - Apple, Samsung, Google, H&M, Åhléns, Yves Saint Laurent, Jean Paul Gaultier, Dior, Chanel.
      synonyms: [brand, manufacturer, label]
    - name: category
      expr: product_dim.category
      display_name: Category
      comment: Product category - electronics, fashion or beauty.
      synonyms: [product category, department]
    - name: subcategory
      expr: product_dim.subcategory
      display_name: Subcategory
      comment: phone, laptop, tablet, jeans, jacket, sweatshirt, office_wear or perfume.
      synonyms: [product type]
    - name: product_name
      expr: product_dim.product_name
      display_name: Product
      comment: Product name, e.g. iPhone 16 128 GB.
      synonyms: [item, article, product]
    - name: payment_method
      expr: source.payment_method
      display_name: Payment method
      comment: card, swish, klarna or invoice (klarna and invoice only online).
      synonyms: [payment, paid with]
    - name: loyalty_tier
      expr: customer_dim.loyalty_tier
      display_name: Loyalty tier
      comment: Loyalty tier of the customer - none, silver or gold.
      synonyms: [tier, membership level]
    - name: customer_city
      expr: customer_dim.city
      display_name: Customer city
      comment: Home city of the customer.
  measures:
    - name: net_revenue_sek
      expr: SUM(source.net_revenue_sek)
      display_name: Net revenue (SEK)
      comment: Sum of quantity * unit price - line discount over completed orders, SEK excl. VAT.
      synonyms: [revenue, sales, net sales, turnover]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: units_sold
      expr: SUM(source.quantity)
      display_name: Units sold
      comment: Units sold on completed orders.
      synonyms: [units, quantity, items sold]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: order_count
      expr: COUNT(DISTINCT source.order_id)
      display_name: Orders
      comment: Number of completed orders (receipts and webshop orders).
      synonyms: [orders, number of orders, transactions, baskets]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: average_order_value_sek
      expr: MEASURE(net_revenue_sek) / MEASURE(order_count)
      display_name: Average order value (SEK)
      comment: Net revenue / completed orders.
      synonyms: [AOV, basket size, average basket, average ticket]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: discount_sek
      expr: SUM(source.discount_sek)
      display_name: Discounts (SEK)
      comment: Line discounts given on completed orders.
      synonyms: [discount, markdown]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: customer_count
      expr: COUNT(DISTINCT source.customer_id)
      display_name: Customers
      comment: Distinct loyalty customers with a completed order.
      synonyms: [buyers, shoppers, active customers]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: cost_of_goods_sek
      expr: SUM(source.quantity * product_dim.unit_cost_sek)
      display_name: Cost of goods (SEK)
      comment: Units * purchase cost. Confidential - NULL for users who may not read unit_cost_sek.
      synonyms: [COGS, cost of sales, purchase cost]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: gross_margin_sek
      expr: MEASURE(net_revenue_sek) - MEASURE(cost_of_goods_sek)
      display_name: Gross margin (SEK)
      comment: Net revenue - cost of goods. Confidential - NULL for users who may not read unit_cost_sek.
      synonyms: [gross profit, margin]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: gross_margin_pct
      expr: (MEASURE(net_revenue_sek) - MEASURE(cost_of_goods_sek)) / MEASURE(net_revenue_sek) * 100
      display_name: Gross margin %
      comment: (Net revenue - cost of goods) / net revenue, 0-100. Confidential - NULL for users who may not read unit_cost_sek.
      synonyms: [margin %, gross margin percentage, GM%]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: returned_units
      expr: SUM(returns_dim.returned_units)
      display_name: Returned units
      comment: Units returned from the sold lines, counted on the order date of the sale.
      synonyms: [returns, units returned]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: return_rate_pct
      expr: COALESCE(MEASURE(returned_units), 0) / MEASURE(units_sold) * 100
      display_name: Return rate %
      comment: Returned units / units sold, 0-100, by the order date of the sale.
      synonyms: [return rate, returns %, return percentage]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: refund_amount_sek
      expr: SUM(returns_dim.refund_sek)
      display_name: Refunds (SEK)
      comment: Amount refunded for returned lines, SEK excl. VAT.
      synonyms: [refunds, refunded amount, money back]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
$$;

CREATE OR REPLACE VIEW ${catalog}.retail.return_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: >-
    Nordvik Retail returns at return grain, Jan-Jun 2026 orders: number of returns, returned units and
    refunds by return month, reason, region, channel, brand, category and product. For the return rate
    (returned units / units sold) use retail.sales_metrics.
  source: ${catalog}.retail.fact_returns
  joins:
    - name: product_dim
      source: ${catalog}.retail.dim_product
      'on': source.product_id = product_dim.product_id
    - name: store_dim
      source: ${catalog}.retail.dim_store
      'on': source.store_id = store_dim.store_id
  dimensions:
    - name: return_date
      expr: source.return_date
      display_name: Return date
      comment: Date the goods came back.
    - name: return_month
      expr: CAST(DATE_TRUNC('MONTH', source.return_date) AS DATE)
      display_name: Return month
      comment: First day of the month the goods came back.
      synonyms: [month]
    - name: reason
      expr: source.reason
      display_name: Return reason
      comment: wrong_size, changed_mind, defect or damaged.
      synonyms: [reason, why returned, return cause]
    - name: store_region
      expr: source.store_region
      display_name: Region
      comment: Region of the original order - STO, GOT, MAL or ONLINE.
      synonyms: [region, area]
    - name: channel
      expr: store_dim.channel
      display_name: Channel
      comment: store or online.
      synonyms: [sales channel]
    - name: brand_name
      expr: product_dim.brand_name
      display_name: Brand
      comment: Brand of the returned product.
      synonyms: [brand]
    - name: category
      expr: product_dim.category
      display_name: Category
      comment: electronics, fashion or beauty.
      synonyms: [product category]
    - name: product_name
      expr: product_dim.product_name
      display_name: Product
      comment: Returned product.
      synonyms: [item, article]
  measures:
    - name: return_count
      expr: COUNT(source.return_id)
      display_name: Returns
      comment: Number of returned order lines.
      synonyms: [number of returns, returns]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: returned_units
      expr: SUM(source.quantity)
      display_name: Returned units
      comment: Units returned.
      synonyms: [units returned]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: refund_amount_sek
      expr: SUM(source.refund_sek)
      display_name: Refunds (SEK)
      comment: Amount refunded, SEK excl. VAT.
      synonyms: [refunds, refunded amount]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
$$;
