-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - BRONZE layer, domain `mobility` (Mobility and Automotive, 5 tables).
-- One streaming table per source file: read_files (Auto Loader) ingests every new CSV file in
-- /Volumes/${catalog}/landing/raw_files/mobility/<table>/ exactly once. All columns stay STRING
-- (inferColumnTypes => false); values that do not fit land in _rescued_data.
-- Lineage columns: _source_file (file path) and _ingested_at (load time).
-- ${catalog} is replaced by the pipeline configuration value `catalog` (resources/ecom.pipelines.yml).
-- ================================================================================================

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.mobility_vehicle_models
COMMENT 'Bronze: raw mobility.vehicle_models rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/mobility/vehicle_models/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.mobility_dealers
COMMENT 'Bronze: raw mobility.dealers rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/mobility/dealers/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.mobility_customers
COMMENT 'Bronze: raw mobility.customers rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/mobility/customers/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.mobility_vehicle_sales
COMMENT 'Bronze: raw mobility.vehicle_sales rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/mobility/vehicle_sales/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.mobility_service_visits
COMMENT 'Bronze: raw mobility.service_visits rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/mobility/service_visits/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);
