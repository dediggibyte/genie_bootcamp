-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - BRONZE layer, domain `retail` (Retail and Commerce, 7 tables).
-- One streaming table per source file: read_files (Auto Loader) ingests every new CSV file in
-- /Volumes/${catalog}/landing/raw_files/retail/<table>/ exactly once. All columns stay STRING
-- (inferColumnTypes => false); values that do not fit land in _rescued_data.
-- Lineage columns: _source_file (file path) and _ingested_at (load time).
-- ${catalog} is replaced by the pipeline configuration value `catalog` (resources/ecom.pipelines.yml).
-- ================================================================================================

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.retail_brands
COMMENT 'Bronze: raw retail.brands rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/retail/brands/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.retail_products
COMMENT 'Bronze: raw retail.products rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/retail/products/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.retail_stores
COMMENT 'Bronze: raw retail.stores rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/retail/stores/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.retail_customers
COMMENT 'Bronze: raw retail.customers rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/retail/customers/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.retail_orders
COMMENT 'Bronze: raw retail.orders rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/retail/orders/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.retail_order_lines
COMMENT 'Bronze: raw retail.order_lines rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/retail/order_lines/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.retail_returns
COMMENT 'Bronze: raw retail.returns rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/retail/returns/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);
