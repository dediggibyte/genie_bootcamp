-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - GOLD layer, domain `retail` (Retail and Commerce): star schema of
-- Nordvik Retail - 3 dimensions (dim_product, dim_store, dim_customer) and 2 facts (fact_sales,
-- fact_returns), 5 FOREIGN KEYs. Data comes from silver only.
-- Every materialized view carries column comments, NOT NULL + PRIMARY KEY and FOREIGN KEY constraints
-- (informational, not enforced; Genie and BI tools use them to join). Constraints and comments cannot be
-- changed after creation - they live here, in the pipeline.
-- Facts carry store_region (denormalised from the store): the governance row filter scopes on it and
-- Genie can answer "by region" without a join.
-- Build order: a FOREIGN KEY needs the referenced table's PRIMARY KEY first, but a pipeline only orders
-- tables by the data they read. The facts therefore end with
--   AND (TRUE OR EXISTS (SELECT 1 FROM <referenced table>) ...)
-- which never filters a row but makes the pipeline build the dimensions first.
-- No foreign keys to other domains (the three domain pipelines run in parallel).
-- Governance (row filters / column masks) is attached to these tables afterwards by
-- notebooks/2026-10-27-03-governance.py.
-- ================================================================================================

-- retail.dim_product -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.retail.dim_product (
  product_id STRING NOT NULL COMMENT 'Product key, e.g. P001.',
  sku STRING COMMENT 'Stock keeping unit printed on the shelf label, e.g. NR-001.',
  product_name STRING COMMENT 'Product name as sold, e.g. iPhone 16 128 GB, Slim Jeans, Sauvage Eau de Toilette 100 ml.',
  brand_id STRING COMMENT 'Brand key, e.g. B01.',
  brand_name STRING COMMENT 'Brand of the product: Apple, Samsung, Google, H&M, Åhléns, Yves Saint Laurent, Jean Paul Gaultier, Dior, Chanel.',
  brand_country STRING COMMENT 'Country of origin of the brand (ISO 3166 alpha-2: US, KR, SE, FR).',
  category STRING COMMENT 'Product category: electronics, fashion or beauty.',
  subcategory STRING COMMENT 'Product subcategory: phone, laptop, tablet, jeans, jacket, sweatshirt, office_wear, perfume.',
  list_price_sek DECIMAL(14, 2) COMMENT 'Shelf price per unit in SEK incl. any campaign, excl. line discounts.',
  unit_cost_sek DECIMAL(14, 2) COMMENT 'Purchase cost per unit in SEK. Confidential: masked (NULL) for users who are not cost readers.',
  launch_date DATE COMMENT 'Date the product was first sold by Nordvik Retail.',
  CONSTRAINT pk_retail_dim_product PRIMARY KEY (product_id)
)
COMMENT 'Retail product catalog of Nordvik Retail: one row per product with its brand and category (Product Catalog subdomain). Brand and product names describe real products; prices are illustrative.'
AS SELECT
  p.product_id,
  p.sku,
  p.product_name,
  p.brand_id,
  b.brand_name,
  b.country_of_origin AS brand_country,
  p.category,
  p.subcategory,
  p.list_price_sek,
  p.unit_cost_sek,
  p.launch_date
FROM ${catalog}.silver.retail_products p
LEFT JOIN ${catalog}.silver.retail_brands b ON b.brand_id = p.brand_id;

-- retail.dim_store -------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.retail.dim_store (
  store_id STRING NOT NULL COMMENT 'Store key, e.g. S01. S06 is the webshop.',
  store_name STRING COMMENT 'Store name, e.g. Nordvik Retail Göteborg Nordstan, Nordvik Webshop.',
  city STRING COMMENT 'City of the store (the webshop is run from Stockholm).',
  region_code STRING COMMENT 'Sales region: STO (Stockholm), GOT (Göteborg), MAL (Malmö), ONLINE (webshop). Scope of the governance row filter.',
  channel STRING COMMENT 'Sales channel: store or online.',
  opened_date DATE COMMENT 'Date the store (or the webshop) opened.',
  CONSTRAINT pk_retail_dim_store PRIMARY KEY (store_id)
)
COMMENT 'Stores and channels of Nordvik Retail: 5 physical stores and the webshop (Stores & Channels subdomain).'
AS SELECT
  store_id,
  store_name,
  city,
  region_code,
  channel,
  opened_date
FROM ${catalog}.silver.retail_stores;

-- retail.dim_customer ----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.retail.dim_customer (
  customer_id STRING NOT NULL COMMENT 'Loyalty customer key, e.g. C001.',
  first_name STRING COMMENT 'First name. Personal data: masked for users who are not PII readers of retail.',
  last_name STRING COMMENT 'Last name. Personal data: masked for users who are not PII readers of retail.',
  email STRING COMMENT 'E-mail address. Personal data: masked for users who are not PII readers of retail.',
  phone STRING COMMENT 'Mobile number. Personal data: masked for users who are not PII readers of retail.',
  city STRING COMMENT 'Home city of the customer.',
  loyalty_tier STRING COMMENT 'Loyalty tier of the Nordvik Club: none, silver or gold.',
  signup_date DATE COMMENT 'Date the customer joined the loyalty programme.',
  CONSTRAINT pk_retail_dim_customer PRIMARY KEY (customer_id)
)
COMMENT 'Loyalty customers of Nordvik Retail, one row per customer (Customers subdomain). Contains personal data (name, e-mail, phone).'
AS SELECT
  customer_id,
  first_name,
  last_name,
  email,
  phone,
  city,
  loyalty_tier,
  signup_date
FROM ${catalog}.silver.retail_customers;

-- retail.fact_sales ------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.retail.fact_sales (
  order_line_id STRING NOT NULL COMMENT 'Order line key, e.g. L0001 - the grain of this table.',
  order_id STRING COMMENT 'Order (receipt or webshop order) the line belongs to. Count distinct order_id for the number of orders.',
  order_date DATE COMMENT 'Date of the order.',
  customer_id STRING COMMENT 'Loyalty customer who placed the order.',
  store_id STRING COMMENT 'Store or webshop that sold the line.',
  store_region STRING COMMENT 'Region of the store: STO, GOT, MAL or ONLINE (copied from dim_store). Scope of the governance row filter.',
  channel STRING COMMENT 'Sales channel of the store: store or online.',
  product_id STRING COMMENT 'Product sold.',
  payment_method STRING COMMENT 'Payment method of the order: card, swish, klarna or invoice (klarna and invoice only online).',
  quantity INT COMMENT 'Units sold on the line.',
  unit_price_sek DECIMAL(14, 2) COMMENT 'Price per unit in SEK before the line discount.',
  discount_sek DECIMAL(14, 2) COMMENT 'Discount on the whole line in SEK.',
  net_revenue_sek DECIMAL(14, 2) COMMENT 'Net revenue of the line in SEK excl. VAT = quantity * unit_price_sek - discount_sek.',
  CONSTRAINT pk_retail_fact_sales PRIMARY KEY (order_line_id),
  CONSTRAINT fk_retail_fact_sales_product FOREIGN KEY (product_id) REFERENCES ${catalog}.retail.dim_product (product_id),
  CONSTRAINT fk_retail_fact_sales_store FOREIGN KEY (store_id) REFERENCES ${catalog}.retail.dim_store (store_id),
  CONSTRAINT fk_retail_fact_sales_customer FOREIGN KEY (customer_id) REFERENCES ${catalog}.retail.dim_customer (customer_id)
)
COMMENT 'Retail sales at order-line grain, Jan-Jun 2026 (Sales & Returns subdomain). Only lines of COMPLETED orders: cancelled orders are not sales and are left out. Amounts in SEK excl. VAT.'
AS SELECT
  l.order_line_id,
  o.order_id,
  o.order_date,
  o.customer_id,
  o.store_id,
  s.region_code AS store_region,
  s.channel,
  l.product_id,
  o.payment_method,
  l.quantity,
  l.unit_price_sek,
  l.discount_sek,
  CAST(l.quantity * l.unit_price_sek - l.discount_sek AS DECIMAL(14, 2)) AS net_revenue_sek
FROM ${catalog}.silver.retail_order_lines l
JOIN ${catalog}.silver.retail_orders o ON o.order_id = l.order_id
LEFT JOIN ${catalog}.silver.retail_stores s ON s.store_id = o.store_id
WHERE o.order_status = 'completed'
  -- Build order only - never filters a row: makes the pipeline build the dimensions first.
  AND (TRUE
       OR EXISTS (SELECT 1 FROM ${catalog}.retail.dim_product)
       OR EXISTS (SELECT 1 FROM ${catalog}.retail.dim_store)
       OR EXISTS (SELECT 1 FROM ${catalog}.retail.dim_customer));

-- retail.fact_returns ----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.retail.fact_returns (
  return_id STRING NOT NULL COMMENT 'Return key, e.g. R001 - the grain of this table.',
  order_line_id STRING COMMENT 'Order line that was returned (fact_sales.order_line_id).',
  order_id STRING COMMENT 'Order of the returned line.',
  order_date DATE COMMENT 'Date of the original order.',
  return_date DATE COMMENT 'Date the goods came back.',
  product_id STRING COMMENT 'Product returned.',
  store_id STRING COMMENT 'Store or webshop of the original order.',
  store_region STRING COMMENT 'Region of the store of the original order: STO, GOT, MAL or ONLINE. Scope of the governance row filter.',
  quantity INT COMMENT 'Units returned.',
  reason STRING COMMENT 'Return reason: wrong_size, changed_mind, defect or damaged.',
  refund_sek DECIMAL(14, 2) COMMENT 'Amount refunded to the customer in SEK excl. VAT.',
  CONSTRAINT pk_retail_fact_returns PRIMARY KEY (return_id),
  CONSTRAINT fk_retail_fact_returns_product FOREIGN KEY (product_id) REFERENCES ${catalog}.retail.dim_product (product_id),
  CONSTRAINT fk_retail_fact_returns_store FOREIGN KEY (store_id) REFERENCES ${catalog}.retail.dim_store (store_id)
)
COMMENT 'Retail returns, one row per returned order line (Sales & Returns subdomain). Return rate = returned units / units sold (retail.sales_metrics).'
AS SELECT
  r.return_id,
  r.order_line_id,
  o.order_id,
  o.order_date,
  r.return_date,
  l.product_id,
  o.store_id,
  s.region_code AS store_region,
  r.quantity,
  r.reason,
  r.refund_sek
FROM ${catalog}.silver.retail_returns r
LEFT JOIN ${catalog}.silver.retail_order_lines l ON l.order_line_id = r.order_line_id
LEFT JOIN ${catalog}.silver.retail_orders o ON o.order_id = l.order_id
LEFT JOIN ${catalog}.silver.retail_stores s ON s.store_id = o.store_id
-- Build order only - never filters a row: makes the pipeline build the dimensions first.
WHERE TRUE
   OR EXISTS (SELECT 1 FROM ${catalog}.retail.dim_product)
   OR EXISTS (SELECT 1 FROM ${catalog}.retail.dim_store);
