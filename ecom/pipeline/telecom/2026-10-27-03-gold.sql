-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - GOLD layer, domain `telecom` (Telecommunications and Media): star
-- schema of Nordvik Connect - 3 dimensions (dim_plan, dim_customer, dim_subscription) and 2 facts
-- (fact_billing, fact_usage), 6 FOREIGN KEYs. Data comes from silver only.
-- Every materialized view carries column comments, NOT NULL + PRIMARY KEY and FOREIGN KEY constraints
-- (informational, not enforced; Genie and BI tools use them to join). Constraints and comments cannot be
-- changed after creation - they live here, in the pipeline.
-- dim_subscription and the facts carry customer_segment (denormalised from the customer) and the facts
-- carry plan_id: the governance row filter scopes on the segment and Genie / metric views reach the
-- plan without a join chain.
-- Build order: a FOREIGN KEY needs the referenced table's PRIMARY KEY first, but a pipeline only orders
-- tables by the data they read. Tables with foreign keys therefore end with
--   WHERE TRUE OR EXISTS (SELECT 1 FROM <referenced table>) ...
-- which never filters a row but makes the pipeline build the referenced tables first.
-- No foreign keys to other domains (the three domain pipelines run in parallel).
-- Governance (row filters / column masks) is attached to these tables afterwards by
-- notebooks/2026-10-27-03-governance.py.
-- ================================================================================================

-- telecom.dim_plan -------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.telecom.dim_plan (
  plan_id STRING NOT NULL COMMENT 'Price plan key, e.g. T01.',
  plan_name STRING COMMENT 'Plan name, e.g. Mobil 5G Unlimited, Fiber 1000/1000, Streaming Duo: Netflix and Spotify Premium.',
  plan_type STRING COMMENT 'Plan type: mobile, broadband, tv_streaming or bundle (mobile + fibre + streaming).',
  segment STRING COMMENT 'Segment the plan is sold to: consumer or business.',
  monthly_fee_sek DECIMAL(14, 2) COMMENT 'Monthly fee in SEK excl. VAT.',
  data_allowance_gb INT COMMENT 'Mobile data included per month in GB; NULL = unlimited (or not a mobile plan).',
  included_streaming STRING COMMENT 'Streaming services included in the fee, separated by "; " (Netflix Standard, Spotify Premium, Disney+ Standard, Max); NULL = none.',
  has_streaming BOOLEAN COMMENT 'True if the plan includes at least one streaming service.',
  CONSTRAINT pk_telecom_dim_plan PRIMARY KEY (plan_id)
)
COMMENT 'Price plans of Nordvik Connect: mobile, fibre broadband, TV and streaming add-ons, bundles (Plans & Products subdomain). Streaming service names describe the add-ons; prices are illustrative.'
AS SELECT
  plan_id,
  plan_name,
  plan_type,
  segment,
  monthly_fee_sek,
  data_allowance_gb,
  included_streaming,
  included_streaming IS NOT NULL AS has_streaming
FROM ${catalog}.silver.telecom_plans;

-- telecom.dim_customer ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.telecom.dim_customer (
  customer_id STRING NOT NULL COMMENT 'Customer key, e.g. N001.',
  customer_segment STRING COMMENT 'consumer or business. Scope of the governance row filter.',
  customer_name STRING COMMENT 'Name of the person or company. Personal data: masked for users who are not PII readers of telecom.',
  email STRING COMMENT 'E-mail address. Personal data: masked for users who are not PII readers of telecom.',
  phone STRING COMMENT 'Mobile number (MSISDN). Personal data: masked to +46 7** *** **NN for users who are not PII readers of telecom.',
  city STRING COMMENT 'City of the customer.',
  signup_date DATE COMMENT 'Date the customer first signed a contract.',
  CONSTRAINT pk_telecom_dim_customer PRIMARY KEY (customer_id)
)
COMMENT 'Customers of Nordvik Connect, consumer and business (Customers & Subscriptions subdomain). Contains personal data (name, e-mail, phone number).'
AS SELECT
  customer_id,
  customer_segment,
  customer_name,
  email,
  phone,
  city,
  signup_date
FROM ${catalog}.silver.telecom_customers;

-- telecom.dim_subscription -----------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.telecom.dim_subscription (
  subscription_id STRING NOT NULL COMMENT 'Subscription key, e.g. SUB001. A customer can have several subscriptions.',
  customer_id STRING COMMENT 'Customer who holds the subscription.',
  customer_segment STRING COMMENT 'Segment of the customer: consumer or business (copied from dim_customer). Scope of the governance row filter.',
  plan_id STRING COMMENT 'Price plan of the subscription.',
  start_date DATE COMMENT 'Date the subscription started.',
  end_date DATE COMMENT 'Date the subscription ended; NULL = still running.',
  status STRING COMMENT 'active or cancelled.',
  sales_channel STRING COMMENT 'Where the subscription was sold: online, store or telesales.',
  CONSTRAINT pk_telecom_dim_subscription PRIMARY KEY (subscription_id),
  CONSTRAINT fk_telecom_dim_subscription_customer FOREIGN KEY (customer_id) REFERENCES ${catalog}.telecom.dim_customer (customer_id),
  CONSTRAINT fk_telecom_dim_subscription_plan FOREIGN KEY (plan_id) REFERENCES ${catalog}.telecom.dim_plan (plan_id)
)
COMMENT 'Subscriptions of Nordvik Connect, one row per subscription (Customers & Subscriptions subdomain). Active subscriptions = status active.'
AS SELECT
  s.subscription_id,
  s.customer_id,
  c.customer_segment,
  s.plan_id,
  s.start_date,
  s.end_date,
  s.status,
  s.sales_channel
FROM ${catalog}.silver.telecom_subscriptions s
LEFT JOIN ${catalog}.silver.telecom_customers c ON c.customer_id = s.customer_id
-- Build order only - never filters a row: makes the pipeline build the referenced tables first.
WHERE TRUE
   OR EXISTS (SELECT 1 FROM ${catalog}.telecom.dim_customer)
   OR EXISTS (SELECT 1 FROM ${catalog}.telecom.dim_plan);

-- telecom.fact_billing ---------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.telecom.fact_billing (
  invoice_id STRING NOT NULL COMMENT 'Invoice key, e.g. INV0001 - one invoice per subscription and billing month.',
  subscription_id STRING COMMENT 'Subscription billed.',
  plan_id STRING COMMENT 'Price plan of the subscription (copied from dim_subscription).',
  customer_segment STRING COMMENT 'Segment of the customer: consumer or business (copied from dim_subscription). Scope of the governance row filter.',
  billing_month DATE COMMENT 'Month billed (first day of the month): 2026-05-01 or 2026-06-01.',
  invoice_date DATE COMMENT 'Date the invoice was issued.',
  due_date DATE COMMENT 'Payment due date (invoice date + 30 days).',
  amount_excl_vat_sek DECIMAL(14, 2) COMMENT 'Invoiced amount in SEK excl. VAT (monthly fee + extra usage). Billed revenue = SUM(amount_excl_vat_sek).',
  vat_sek DECIMAL(14, 2) COMMENT 'VAT in SEK (25 %).',
  amount_incl_vat_sek DECIMAL(14, 2) COMMENT 'Amount the customer pays in SEK = amount_excl_vat_sek + vat_sek.',
  payment_status STRING COMMENT 'paid, open (not yet due) or overdue (due date passed, not paid).',
  CONSTRAINT pk_telecom_fact_billing PRIMARY KEY (invoice_id),
  CONSTRAINT fk_telecom_fact_billing_subscription FOREIGN KEY (subscription_id) REFERENCES ${catalog}.telecom.dim_subscription (subscription_id),
  CONSTRAINT fk_telecom_fact_billing_plan FOREIGN KEY (plan_id) REFERENCES ${catalog}.telecom.dim_plan (plan_id)
)
COMMENT 'Monthly invoices of Nordvik Connect, one row per subscription and billing month, May-Jun 2026 (Billing subdomain). ARPU = billed revenue / billed subscriptions per month.'
AS SELECT
  i.invoice_id,
  i.subscription_id,
  s.plan_id,
  c.customer_segment,
  i.billing_month,
  i.invoice_date,
  i.due_date,
  i.amount_excl_vat_sek,
  i.vat_sek,
  CAST(i.amount_excl_vat_sek + i.vat_sek AS DECIMAL(14, 2)) AS amount_incl_vat_sek,
  i.payment_status
FROM ${catalog}.silver.telecom_invoices i
LEFT JOIN ${catalog}.silver.telecom_subscriptions s ON s.subscription_id = i.subscription_id
LEFT JOIN ${catalog}.silver.telecom_customers c ON c.customer_id = s.customer_id
-- Build order only - never filters a row: makes the pipeline build the referenced tables first.
WHERE TRUE
   OR EXISTS (SELECT 1 FROM ${catalog}.telecom.dim_subscription)
   OR EXISTS (SELECT 1 FROM ${catalog}.telecom.dim_plan);

-- telecom.fact_usage -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.telecom.fact_usage (
  usage_id STRING NOT NULL COMMENT 'Usage record key, e.g. U0001 - one row per subscription and usage month.',
  subscription_id STRING COMMENT 'Subscription that generated the usage.',
  plan_id STRING COMMENT 'Price plan of the subscription (copied from dim_subscription).',
  customer_segment STRING COMMENT 'Segment of the customer: consumer or business (copied from dim_subscription). Scope of the governance row filter.',
  usage_month DATE COMMENT 'Month of the usage (first day of the month): 2026-05-01 or 2026-06-01.',
  data_gb DECIMAL(10, 1) COMMENT 'Data used in GB (mobile and fixed).',
  voice_minutes INT COMMENT 'Outgoing call minutes (0 for broadband and TV plans).',
  sms_count INT COMMENT 'SMS sent (0 for broadband and TV plans).',
  streaming_hours DECIMAL(10, 1) COMMENT 'Hours streamed in the Nordvik Connect TV app and the included streaming services.',
  CONSTRAINT pk_telecom_fact_usage PRIMARY KEY (usage_id),
  CONSTRAINT fk_telecom_fact_usage_subscription FOREIGN KEY (subscription_id) REFERENCES ${catalog}.telecom.dim_subscription (subscription_id),
  CONSTRAINT fk_telecom_fact_usage_plan FOREIGN KEY (plan_id) REFERENCES ${catalog}.telecom.dim_plan (plan_id)
)
COMMENT 'Monthly usage of Nordvik Connect subscriptions, one row per subscription and month, May-Jun 2026 (Usage subdomain).'
AS SELECT
  u.usage_id,
  u.subscription_id,
  s.plan_id,
  c.customer_segment,
  u.usage_month,
  u.data_gb,
  u.voice_minutes,
  u.sms_count,
  u.streaming_hours
FROM ${catalog}.silver.telecom_usage u
LEFT JOIN ${catalog}.silver.telecom_subscriptions s ON s.subscription_id = u.subscription_id
LEFT JOIN ${catalog}.silver.telecom_customers c ON c.customer_id = s.customer_id
-- Build order only - never filters a row: makes the pipeline build the referenced tables first.
WHERE TRUE
   OR EXISTS (SELECT 1 FROM ${catalog}.telecom.dim_subscription)
   OR EXISTS (SELECT 1 FROM ${catalog}.telecom.dim_plan);
