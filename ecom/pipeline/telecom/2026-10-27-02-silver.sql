-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - SILVER layer, domain `telecom` (Telecommunications and Media, 5 tables).
-- One materialized view per bronze table that turns the raw STRING columns into typed columns:
--   * text      -> trim, empty string becomes NULL
--   * codes     -> trim + one canonical case ('Business ' -> 'business')
--   * numbers   -> TRY_CAST (bad values become NULL instead of failing the pipeline)
--   * dates     -> yyyy-MM-dd and dd/MM/yyyy
-- Duplicates: one row per primary key (latest _ingested_at wins). Rows with an empty primary key are
-- kept by the dedup step so that the expectation drops (and counts) every one of them.
-- Silver = the clean data: its row counts equal clean_rows in data/2026-10-27-manifest.json.
-- Silver is NOT governed (no row filters / column masks): give consumers access to the gold schema only.
-- ================================================================================================

-- telecom.plans ----------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.telecom_plans (
  CONSTRAINT plan_id_not_null EXPECT (plan_id IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Silver: telecom.plans typed and cleaned, one row per plan_id (empty data allowance = unlimited).'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(plan_id)), '') AS plan_id,
    NULLIF(trim(plan_name), '') AS plan_name,
    NULLIF(lower(trim(plan_type)), '') AS plan_type,
    NULLIF(lower(trim(segment)), '') AS segment,
    TRY_CAST(NULLIF(trim(monthly_fee_sek), '') AS DECIMAL(14, 2)) AS monthly_fee_sek,
    TRY_CAST(NULLIF(trim(data_allowance_gb), '') AS INT) AS data_allowance_gb,
    NULLIF(trim(included_streaming), '') AS included_streaming,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.telecom_plans
)
SELECT *
FROM typed
QUALIFY plan_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY plan_id ORDER BY _ingested_at DESC) = 1;

-- telecom.customers ------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.telecom_customers (
  CONSTRAINT customer_id_not_null EXPECT (customer_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT segment_known EXPECT (customer_segment IN ('consumer', 'business'))
)
COMMENT 'Silver: telecom.customers typed and cleaned (segment trimmed and lower case), one row per customer_id.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(customer_id)), '') AS customer_id,
    NULLIF(lower(trim(customer_segment)), '') AS customer_segment,
    NULLIF(trim(customer_name), '') AS customer_name,
    NULLIF(lower(trim(email)), '') AS email,
    NULLIF(trim(phone), '') AS phone,
    NULLIF(trim(city), '') AS city,
    COALESCE(try_to_date(trim(signup_date), 'yyyy-MM-dd'), try_to_date(trim(signup_date), 'dd/MM/yyyy')) AS signup_date,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.telecom_customers
)
SELECT *
FROM typed
QUALIFY customer_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY _ingested_at DESC) = 1;

-- telecom.subscriptions --------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.telecom_subscriptions (
  CONSTRAINT subscription_id_not_null EXPECT (subscription_id IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Silver: telecom.subscriptions typed and cleaned, one row per subscription_id (empty end_date = running).'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(subscription_id)), '') AS subscription_id,
    NULLIF(upper(trim(customer_id)), '') AS customer_id,
    NULLIF(upper(trim(plan_id)), '') AS plan_id,
    COALESCE(try_to_date(trim(start_date), 'yyyy-MM-dd'), try_to_date(trim(start_date), 'dd/MM/yyyy')) AS start_date,
    COALESCE(try_to_date(trim(end_date), 'yyyy-MM-dd'), try_to_date(trim(end_date), 'dd/MM/yyyy')) AS end_date,
    NULLIF(lower(trim(status)), '') AS status,
    NULLIF(lower(trim(sales_channel)), '') AS sales_channel,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.telecom_subscriptions
)
SELECT *
FROM typed
QUALIFY subscription_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY subscription_id ORDER BY _ingested_at DESC) = 1;

-- telecom.invoices -------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.telecom_invoices (
  CONSTRAINT invoice_id_not_null EXPECT (invoice_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT amount_not_negative EXPECT (amount_excl_vat_sek >= 0)
)
COMMENT 'Silver: telecom.invoices typed and cleaned, one row per invoice_id - the exact duplicate row of the extract is removed.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(invoice_id)), '') AS invoice_id,
    NULLIF(upper(trim(subscription_id)), '') AS subscription_id,
    COALESCE(try_to_date(trim(billing_month), 'yyyy-MM-dd'), try_to_date(trim(billing_month), 'dd/MM/yyyy')) AS billing_month,
    COALESCE(try_to_date(trim(invoice_date), 'yyyy-MM-dd'), try_to_date(trim(invoice_date), 'dd/MM/yyyy')) AS invoice_date,
    COALESCE(try_to_date(trim(due_date), 'yyyy-MM-dd'), try_to_date(trim(due_date), 'dd/MM/yyyy')) AS due_date,
    TRY_CAST(NULLIF(trim(amount_excl_vat_sek), '') AS DECIMAL(14, 2)) AS amount_excl_vat_sek,
    TRY_CAST(NULLIF(trim(vat_sek), '') AS DECIMAL(14, 2)) AS vat_sek,
    NULLIF(lower(trim(payment_status)), '') AS payment_status,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.telecom_invoices
)
SELECT *
FROM typed
QUALIFY invoice_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY invoice_id ORDER BY _ingested_at DESC) = 1;

-- telecom.usage ----------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.telecom_usage (
  CONSTRAINT usage_id_not_null EXPECT (usage_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT usage_month_parsed EXPECT (usage_month IS NOT NULL)
)
COMMENT 'Silver: telecom.usage typed and cleaned (usage months in yyyy-MM-dd and dd/MM/yyyy parsed), one row per usage_id.'
AS
WITH typed AS (
  SELECT
    NULLIF(upper(trim(usage_id)), '') AS usage_id,
    NULLIF(upper(trim(subscription_id)), '') AS subscription_id,
    COALESCE(try_to_date(trim(usage_month), 'yyyy-MM-dd'), try_to_date(trim(usage_month), 'dd/MM/yyyy')) AS usage_month,
    TRY_CAST(NULLIF(trim(data_gb), '') AS DECIMAL(10, 1)) AS data_gb,
    TRY_CAST(NULLIF(trim(voice_minutes), '') AS INT) AS voice_minutes,
    TRY_CAST(NULLIF(trim(sms_count), '') AS INT) AS sms_count,
    TRY_CAST(NULLIF(trim(streaming_hours), '') AS DECIMAL(10, 1)) AS streaming_hours,
    _source_file,
    _ingested_at
  FROM ${catalog}.bronze.telecom_usage
)
SELECT *
FROM typed
QUALIFY usage_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY usage_id ORDER BY _ingested_at DESC) = 1;
