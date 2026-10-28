-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - SILVER layer, domain `retail` (Retail and Commerce, 7 tables).
-- One materialized view per bronze table that turns the raw STRING columns into typed columns:
--   * text      -> trim, empty string becomes NULL
--   * codes     -> trim + one canonical case (' got' -> 'GOT', ' Gold' / 'SILVER' -> 'gold' / 'silver')
--   * numbers   -> TRY_CAST (bad values become NULL instead of failing the pipeline)
--   * dates     -> yyyy-MM-dd and dd/MM/yyyy
-- Duplicates: one row per primary key (latest _ingested_at wins). Rows with an empty primary key are
-- kept by the dedup step so that the expectation drops (and counts) every one of them.
-- Silver = the clean data: its row counts equal clean_rows in data/2026-10-27-manifest.json.
-- Silver is NOT governed (no row filters / column masks): give consumers access to the gold schema only.
-- ================================================================================================

-- retail.brands ----------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.retail_brands (
  CONSTRAINT brand_id_not_null EXPECT (brand_id IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Silver: retail.brands typed and cleaned, one row per brand_id.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(brand_id)), '') AS brand_id,
    NULLIF(trim(brand_name), '') AS brand_name,
    NULLIF(lower(trim(category)), '') AS category,
    NULLIF(upper(trim(country_of_origin)), '') AS country_of_origin,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.retail_brands
)
SELECT *
FROM typed
QUALIFY brand_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY brand_id ORDER BY _ingested_at DESC) = 1;

-- retail.products --------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.retail_products (
  CONSTRAINT product_id_not_null EXPECT (product_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT list_price_positive EXPECT (list_price_sek > 0)
)
COMMENT 'Silver: retail.products typed and cleaned, one row per product_id.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(product_id)), '') AS product_id,
    NULLIF(trim(sku), '') AS sku,
    NULLIF(trim(product_name), '') AS product_name,
    NULLIF(upper(trim(brand_id)), '') AS brand_id,
    NULLIF(lower(trim(category)), '') AS category,
    NULLIF(lower(trim(subcategory)), '') AS subcategory,
    TRY_CAST(NULLIF(trim(list_price_sek), '') AS DECIMAL(14, 2)) AS list_price_sek,
    TRY_CAST(NULLIF(trim(unit_cost_sek), '') AS DECIMAL(14, 2)) AS unit_cost_sek,
    COALESCE(try_to_date(trim(launch_date), 'yyyy-MM-dd'), try_to_date(trim(launch_date), 'dd/MM/yyyy')) AS launch_date,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.retail_products
)
SELECT *
FROM typed
QUALIFY product_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY _ingested_at DESC) = 1;

-- retail.stores ----------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.retail_stores (
  CONSTRAINT store_id_not_null EXPECT (store_id IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Silver: retail.stores typed and cleaned (region code trimmed and upper case), one row per store_id.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(store_id)), '') AS store_id,
    NULLIF(trim(store_name), '') AS store_name,
    NULLIF(trim(city), '') AS city,
    NULLIF(upper(trim(region_code)), '') AS region_code,
    NULLIF(lower(trim(channel)), '') AS channel,
    COALESCE(try_to_date(trim(opened_date), 'yyyy-MM-dd'), try_to_date(trim(opened_date), 'dd/MM/yyyy')) AS opened_date,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.retail_stores
)
SELECT *
FROM typed
QUALIFY store_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY store_id ORDER BY _ingested_at DESC) = 1;

-- retail.customers -------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.retail_customers (
  CONSTRAINT customer_id_not_null EXPECT (customer_id IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Silver: retail.customers typed and cleaned (loyalty tier trimmed and lower case), one row per customer_id - the exact duplicate row of the extract is removed.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(customer_id)), '') AS customer_id,
    NULLIF(trim(first_name), '') AS first_name,
    NULLIF(trim(last_name), '') AS last_name,
    NULLIF(lower(trim(email)), '') AS email,
    NULLIF(trim(phone), '') AS phone,
    NULLIF(trim(city), '') AS city,
    NULLIF(lower(trim(loyalty_tier)), '') AS loyalty_tier,
    COALESCE(try_to_date(trim(signup_date), 'yyyy-MM-dd'), try_to_date(trim(signup_date), 'dd/MM/yyyy')) AS signup_date,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.retail_customers
)
SELECT *
FROM typed
QUALIFY customer_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY _ingested_at DESC) = 1;

-- retail.orders ----------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.retail_orders (
  CONSTRAINT order_id_not_null EXPECT (order_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT order_date_parsed EXPECT (order_date IS NOT NULL)
)
COMMENT 'Silver: retail.orders typed and cleaned (order dates in yyyy-MM-dd and dd/MM/yyyy parsed), one row per order_id.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(order_id)), '') AS order_id,
    COALESCE(try_to_date(trim(order_date), 'yyyy-MM-dd'), try_to_date(trim(order_date), 'dd/MM/yyyy')) AS order_date,
    NULLIF(upper(trim(customer_id)), '') AS customer_id,
    NULLIF(upper(trim(store_id)), '') AS store_id,
    NULLIF(lower(trim(payment_method)), '') AS payment_method,
    NULLIF(lower(trim(order_status)), '') AS order_status,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.retail_orders
)
SELECT *
FROM typed
QUALIFY order_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY _ingested_at DESC) = 1;

-- retail.order_lines -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.retail_order_lines (
  CONSTRAINT order_line_id_not_null EXPECT (order_line_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT quantity_positive EXPECT (quantity > 0),
  CONSTRAINT discount_not_negative EXPECT (discount_sek >= 0)
)
COMMENT 'Silver: retail.order_lines typed and cleaned, one row per order_line_id - the legacy-feed row without an order_line_id is dropped by the expectation.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(order_line_id)), '') AS order_line_id,
    NULLIF(upper(trim(order_id)), '') AS order_id,
    NULLIF(upper(trim(product_id)), '') AS product_id,
    TRY_CAST(NULLIF(trim(quantity), '') AS INT) AS quantity,
    TRY_CAST(NULLIF(trim(unit_price_sek), '') AS DECIMAL(14, 2)) AS unit_price_sek,
    TRY_CAST(NULLIF(trim(discount_sek), '') AS DECIMAL(14, 2)) AS discount_sek,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.retail_order_lines
)
SELECT *
FROM typed
QUALIFY order_line_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY order_line_id ORDER BY _ingested_at DESC) = 1;

-- retail.returns ---------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.retail_returns (
  CONSTRAINT return_id_not_null EXPECT (return_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT return_quantity_positive EXPECT (quantity > 0)
)
COMMENT 'Silver: retail.returns typed and cleaned, one row per return_id.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(return_id)), '') AS return_id,
    NULLIF(upper(trim(order_line_id)), '') AS order_line_id,
    COALESCE(try_to_date(trim(return_date), 'yyyy-MM-dd'), try_to_date(trim(return_date), 'dd/MM/yyyy')) AS return_date,
    TRY_CAST(NULLIF(trim(quantity), '') AS INT) AS quantity,
    NULLIF(lower(trim(reason)), '') AS reason,
    TRY_CAST(NULLIF(trim(refund_sek), '') AS DECIMAL(14, 2)) AS refund_sek,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.retail_returns
)
SELECT *
FROM typed
QUALIFY return_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY return_id ORDER BY _ingested_at DESC) = 1;
