-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - SILVER layer, domain `mobility` (Mobility and Automotive, 5 tables).
-- One materialized view per bronze table that turns the raw STRING columns into typed columns:
--   * text      -> trim, empty string becomes NULL
--   * codes     -> trim + one canonical case ('got ' -> 'GOT')
--   * numbers   -> TRY_CAST (bad values become NULL instead of failing the pipeline)
--   * dates     -> yyyy-MM-dd and dd/MM/yyyy
--   * booleans  -> true/false, t/f, y/n, yes/no, 1/0 (any case)
-- Duplicates: one row per primary key (latest _ingested_at wins). Rows with an empty primary key are
-- kept by the dedup step so that the expectation drops (and counts) every one of them.
-- Silver = the clean data: its row counts equal clean_rows in data/2026-10-27-manifest.json.
-- Silver is NOT governed (no row filters / column masks): give consumers access to the gold schema only.
-- ================================================================================================

-- mobility.vehicle_models ------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.mobility_vehicle_models (
  CONSTRAINT model_id_not_null EXPECT (model_id IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Silver: mobility.vehicle_models typed and cleaned, one row per model_id.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(model_id)), '') AS model_id,
    NULLIF(trim(brand), '') AS brand,
    NULLIF(trim(model_name), '') AS model_name,
    NULLIF(lower(trim(vehicle_type)), '') AS vehicle_type,
    NULLIF(lower(trim(body_type)), '') AS body_type,
    NULLIF(lower(trim(powertrain)), '') AS powertrain,
    TRY_CAST(NULLIF(trim(model_year), '') AS INT) AS model_year,
    TRY_CAST(NULLIF(trim(list_price_sek), '') AS DECIMAL(14, 2)) AS list_price_sek,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.mobility_vehicle_models
)
SELECT *
FROM typed
QUALIFY model_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY model_id ORDER BY _ingested_at DESC) = 1;

-- mobility.dealers -------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.mobility_dealers (
  CONSTRAINT dealer_id_not_null EXPECT (dealer_id IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Silver: mobility.dealers typed and cleaned (region code trimmed and upper case), one row per dealer_id.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(dealer_id)), '') AS dealer_id,
    NULLIF(trim(dealer_name), '') AS dealer_name,
    NULLIF(trim(city), '') AS city,
    NULLIF(upper(trim(region_code)), '') AS region_code,
    CASE WHEN lower(trim(has_workshop)) IN ('true', 't', 'yes', 'y', '1') THEN TRUE
         WHEN lower(trim(has_workshop)) IN ('false', 'f', 'no', 'n', '0') THEN FALSE END AS has_workshop,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.mobility_dealers
)
SELECT *
FROM typed
QUALIFY dealer_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY dealer_id ORDER BY _ingested_at DESC) = 1;

-- mobility.customers -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.mobility_customers (
  CONSTRAINT customer_id_not_null EXPECT (customer_id IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Silver: mobility.customers typed and cleaned, one row per customer_id - the exact duplicate row of the extract is removed.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(customer_id)), '') AS customer_id,
    NULLIF(lower(trim(customer_type)), '') AS customer_type,
    NULLIF(trim(customer_name), '') AS customer_name,
    NULLIF(lower(trim(email)), '') AS email,
    NULLIF(trim(phone), '') AS phone,
    NULLIF(trim(city), '') AS city,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.mobility_customers
)
SELECT *
FROM typed
QUALIFY customer_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY _ingested_at DESC) = 1;

-- mobility.vehicle_sales -------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.mobility_vehicle_sales (
  CONSTRAINT sale_id_not_null EXPECT (sale_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT sale_price_positive EXPECT (sale_price_sek > 0),
  CONSTRAINT discount_not_negative EXPECT (discount_sek >= 0)
)
COMMENT 'Silver: mobility.vehicle_sales typed and cleaned, one row per sale_id - the row without a sale_id is dropped by the expectation.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(sale_id)), '') AS sale_id,
    COALESCE(try_to_date(trim(sale_date), 'yyyy-MM-dd'), try_to_date(trim(sale_date), 'dd/MM/yyyy')) AS sale_date,
    NULLIF(upper(trim(dealer_id)), '') AS dealer_id,
    NULLIF(upper(trim(customer_id)), '') AS customer_id,
    NULLIF(upper(trim(model_id)), '') AS model_id,
    NULLIF(upper(trim(vin)), '') AS vin,
    TRY_CAST(NULLIF(trim(sale_price_sek), '') AS DECIMAL(14, 2)) AS sale_price_sek,
    TRY_CAST(NULLIF(trim(discount_sek), '') AS DECIMAL(14, 2)) AS discount_sek,
    NULLIF(lower(trim(financing)), '') AS financing,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.mobility_vehicle_sales
)
SELECT *
FROM typed
QUALIFY sale_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY sale_id ORDER BY _ingested_at DESC) = 1;

-- mobility.service_visits ------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.mobility_service_visits (
  CONSTRAINT visit_id_not_null EXPECT (visit_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT warranty_parsed EXPECT (warranty IS NOT NULL)
)
COMMENT 'Silver: mobility.service_visits typed and cleaned (warranty flag Y/N and true/false mapped to BOOLEAN), one row per visit_id.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(visit_id)), '') AS visit_id,
    COALESCE(try_to_date(trim(visit_date), 'yyyy-MM-dd'), try_to_date(trim(visit_date), 'dd/MM/yyyy')) AS visit_date,
    NULLIF(upper(trim(dealer_id)), '') AS dealer_id,
    NULLIF(upper(trim(customer_id)), '') AS customer_id,
    NULLIF(upper(trim(model_id)), '') AS model_id,
    NULLIF(upper(trim(vin)), '') AS vin,
    NULLIF(lower(trim(service_type)), '') AS service_type,
    TRY_CAST(NULLIF(trim(labour_hours), '') AS DECIMAL(6, 1)) AS labour_hours,
    TRY_CAST(NULLIF(trim(labour_cost_sek), '') AS DECIMAL(14, 2)) AS labour_cost_sek,
    TRY_CAST(NULLIF(trim(parts_cost_sek), '') AS DECIMAL(14, 2)) AS parts_cost_sek,
    TRY_CAST(NULLIF(trim(billed_amount_sek), '') AS DECIMAL(14, 2)) AS billed_amount_sek,
    CASE WHEN lower(trim(warranty)) IN ('true', 't', 'yes', 'y', '1') THEN TRUE
         WHEN lower(trim(warranty)) IN ('false', 'f', 'no', 'n', '0') THEN FALSE END AS warranty,
    TRY_CAST(NULLIF(trim(mileage_km), '') AS INT) AS mileage_km,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.mobility_service_visits
)
SELECT *
FROM typed
QUALIFY visit_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY _ingested_at DESC) = 1;
