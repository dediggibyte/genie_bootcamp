-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - BRONZE layer, domain `telecom` (Telecommunications and Media, 5 tables).
-- One streaming table per source file: read_files (Auto Loader) ingests every new CSV file in
-- /Volumes/${catalog}/landing/raw_files/telecom/<table>/ exactly once. All columns stay STRING
-- (inferColumnTypes => false); values that do not fit land in _rescued_data.
-- Lineage columns: _source_file (file path) and _ingested_at (load time).
-- ${catalog} is replaced by the pipeline configuration value `catalog` (resources/ecom.pipelines.yml).
-- ================================================================================================

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.telecom_plans
COMMENT 'Bronze: raw telecom.plans rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/telecom/plans/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.telecom_customers
COMMENT 'Bronze: raw telecom.customers rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/telecom/customers/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.telecom_subscriptions
COMMENT 'Bronze: raw telecom.subscriptions rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/telecom/subscriptions/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.telecom_invoices
COMMENT 'Bronze: raw telecom.invoices rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/telecom/invoices/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);

CREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.telecom_usage
COMMENT 'Bronze: raw telecom.usage rows exactly as delivered in the CSV extract (all columns STRING).'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/${catalog}/landing/raw_files/telecom/usage/',
  format => 'csv',
  header => true,
  inferColumnTypes => false
);
