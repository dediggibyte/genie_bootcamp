-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - GOLD layer, domain `mobility` (Mobility and Automotive): star schema
-- of Nordvik Mobility - 3 dimensions (dim_vehicle_model, dim_dealer, dim_customer) and 2 facts
-- (fact_vehicle_sales, fact_service_visits), 6 FOREIGN KEYs. Data comes from silver only.
-- Every materialized view carries column comments, NOT NULL + PRIMARY KEY and FOREIGN KEY constraints
-- (informational, not enforced; Genie and BI tools use them to join). Constraints and comments cannot be
-- changed after creation - they live here, in the pipeline.
-- Facts carry dealer_region (denormalised from the dealer): the governance row filter scopes on it and
-- Genie can answer "by region" without a join.
-- Build order: a FOREIGN KEY needs the referenced table's PRIMARY KEY first, but a pipeline only orders
-- tables by the data they read. The facts therefore end with
--   WHERE TRUE OR EXISTS (SELECT 1 FROM <referenced table>) ...
-- which never filters a row but makes the pipeline build the dimensions first.
-- No foreign keys to other domains (the three domain pipelines run in parallel).
-- Governance (row filters / column masks) is attached to these tables afterwards by
-- notebooks/2026-10-27-03-governance.py.
-- ================================================================================================

-- mobility.dim_vehicle_model ---------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.mobility.dim_vehicle_model (
  model_id STRING NOT NULL COMMENT 'Vehicle model key, e.g. M01.',
  brand STRING COMMENT 'Vehicle brand: Volvo, Tesla, Volkswagen, Toyota, BMW, Kia, Ford, Scania, Mercedes-Benz.',
  model_name STRING COMMENT 'Model name, e.g. EX30, Model Y, FH Electric.',
  vehicle_type STRING COMMENT 'Vehicle type: car, van or truck.',
  body_type STRING COMMENT 'Body type: suv, sedan, hatchback, van, tractor_unit.',
  powertrain STRING COMMENT 'Powertrain: ev (battery electric), hybrid, petrol or diesel.',
  is_ev BOOLEAN COMMENT 'True for battery electric vehicles (powertrain = ev). EV share = EVs sold / vehicles sold.',
  model_year INT COMMENT 'Model year.',
  list_price_sek DECIMAL(14, 2) COMMENT 'List price per vehicle in SEK excl. VAT.',
  CONSTRAINT pk_mobility_dim_vehicle_model PRIMARY KEY (model_id)
)
COMMENT 'Vehicle catalog of Nordvik Mobility: cars, vans and trucks on sale (Vehicle Catalog subdomain). Brand and model names describe real vehicles; prices are illustrative.'
AS SELECT
  model_id,
  brand,
  model_name,
  vehicle_type,
  body_type,
  powertrain,
  powertrain = 'ev' AS is_ev,
  model_year,
  list_price_sek
FROM ${catalog}.silver.mobility_vehicle_models;

-- mobility.dim_dealer ----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.mobility.dim_dealer (
  dealer_id STRING NOT NULL COMMENT 'Dealer key, e.g. D01. D06 is the truck centre.',
  dealer_name STRING COMMENT 'Dealer name, e.g. Nordvik Mobility Täby, Nordvik Truck Center Södertälje.',
  city STRING COMMENT 'City of the dealer.',
  region_code STRING COMMENT 'Sales region: STO (Stockholm incl. Södertälje), GOT (Göteborg), MAL (Malmö), UME (Umeå). Scope of the governance row filter.',
  has_workshop BOOLEAN COMMENT 'True if the dealer has a service workshop (aftersales).',
  CONSTRAINT pk_mobility_dim_dealer PRIMARY KEY (dealer_id)
)
COMMENT 'Dealer network of Nordvik Mobility: 5 car dealers and 1 truck centre (Dealer Network subdomain).'
AS SELECT
  dealer_id,
  dealer_name,
  city,
  region_code,
  has_workshop
FROM ${catalog}.silver.mobility_dealers;

-- mobility.dim_customer --------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.mobility.dim_customer (
  customer_id STRING NOT NULL COMMENT 'Customer key, e.g. K001.',
  customer_type STRING COMMENT 'private (consumer) or fleet (company buying vans and trucks).',
  customer_name STRING COMMENT 'Name of the person or company. Personal data: masked for users who are not PII readers of mobility.',
  email STRING COMMENT 'E-mail address. Personal data: masked for users who are not PII readers of mobility.',
  phone STRING COMMENT 'Phone number. Personal data: masked for users who are not PII readers of mobility.',
  city STRING COMMENT 'City of the customer.',
  CONSTRAINT pk_mobility_dim_customer PRIMARY KEY (customer_id)
)
COMMENT 'Customers of Nordvik Mobility, private and fleet (Vehicle Sales subdomain). Contains personal data (name, e-mail, phone).'
AS SELECT
  customer_id,
  customer_type,
  customer_name,
  email,
  phone,
  city
FROM ${catalog}.silver.mobility_customers;

-- mobility.fact_vehicle_sales --------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.mobility.fact_vehicle_sales (
  sale_id STRING NOT NULL COMMENT 'Vehicle sale key, e.g. VS001 - one row per vehicle sold.',
  sale_date DATE COMMENT 'Date of the sale (contract date).',
  dealer_id STRING COMMENT 'Dealer that sold the vehicle.',
  dealer_region STRING COMMENT 'Region of the dealer: STO, GOT, MAL or UME (copied from dim_dealer). Scope of the governance row filter.',
  customer_id STRING COMMENT 'Buyer of the vehicle.',
  model_id STRING COMMENT 'Vehicle model sold.',
  vin STRING COMMENT 'Vehicle identification number. Sensitive: shows only the last 4 characters to users who are not PII readers of mobility.',
  sale_price_sek DECIMAL(14, 2) COMMENT 'List price of the vehicle at the time of sale in SEK excl. VAT.',
  discount_sek DECIMAL(14, 2) COMMENT 'Discount given on the sale in SEK.',
  net_sale_price_sek DECIMAL(14, 2) COMMENT 'Vehicle revenue in SEK excl. VAT = sale_price_sek - discount_sek.',
  financing STRING COMMENT 'How the vehicle was paid: cash, loan or lease.',
  CONSTRAINT pk_mobility_fact_vehicle_sales PRIMARY KEY (sale_id),
  CONSTRAINT fk_mobility_fact_vehicle_sales_model FOREIGN KEY (model_id) REFERENCES ${catalog}.mobility.dim_vehicle_model (model_id),
  CONSTRAINT fk_mobility_fact_vehicle_sales_dealer FOREIGN KEY (dealer_id) REFERENCES ${catalog}.mobility.dim_dealer (dealer_id),
  CONSTRAINT fk_mobility_fact_vehicle_sales_customer FOREIGN KEY (customer_id) REFERENCES ${catalog}.mobility.dim_customer (customer_id)
)
COMMENT 'New-vehicle sales of Nordvik Mobility, one row per vehicle sold, Jan-Jun 2026 (Vehicle Sales subdomain). Amounts in SEK excl. VAT.'
AS SELECT
  v.sale_id,
  v.sale_date,
  v.dealer_id,
  d.region_code AS dealer_region,
  v.customer_id,
  v.model_id,
  v.vin,
  v.sale_price_sek,
  v.discount_sek,
  CAST(v.sale_price_sek - v.discount_sek AS DECIMAL(14, 2)) AS net_sale_price_sek,
  v.financing
FROM ${catalog}.silver.mobility_vehicle_sales v
LEFT JOIN ${catalog}.silver.mobility_dealers d ON d.dealer_id = v.dealer_id
-- Build order only - never filters a row: makes the pipeline build the dimensions first.
WHERE TRUE
   OR EXISTS (SELECT 1 FROM ${catalog}.mobility.dim_vehicle_model)
   OR EXISTS (SELECT 1 FROM ${catalog}.mobility.dim_dealer)
   OR EXISTS (SELECT 1 FROM ${catalog}.mobility.dim_customer);

-- mobility.fact_service_visits -------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.mobility.fact_service_visits (
  visit_id STRING NOT NULL COMMENT 'Workshop visit key, e.g. SV001 - one row per visit.',
  visit_date DATE COMMENT 'Date of the workshop visit.',
  dealer_id STRING COMMENT 'Dealer whose workshop did the work.',
  dealer_region STRING COMMENT 'Region of the dealer: STO, GOT, MAL or UME (copied from dim_dealer). Scope of the governance row filter.',
  customer_id STRING COMMENT 'Owner of the vehicle.',
  model_id STRING COMMENT 'Model of the serviced vehicle.',
  vin STRING COMMENT 'Vehicle identification number. Sensitive: shows only the last 4 characters to users who are not PII readers of mobility.',
  service_type STRING COMMENT 'Work done: annual_service, tyre_change, brake_service, battery_check (EVs instead of an annual service), software_update, warranty_repair.',
  labour_hours DECIMAL(6, 1) COMMENT 'Workshop hours worked.',
  labour_cost_sek DECIMAL(14, 2) COMMENT 'Labour at the workshop hourly rate in SEK (1150 per hour for cars and vans, 1450 for trucks).',
  parts_cost_sek DECIMAL(14, 2) COMMENT 'Parts used in SEK.',
  billed_amount_sek DECIMAL(14, 2) COMMENT 'Amount billed to the customer in SEK excl. VAT = labour + parts; 0 for warranty work (billed to the manufacturer). Service revenue = SUM(billed_amount_sek).',
  is_warranty BOOLEAN COMMENT 'True for warranty work, which the customer does not pay.',
  mileage_km INT COMMENT 'Odometer reading at the visit in km.',
  CONSTRAINT pk_mobility_fact_service_visits PRIMARY KEY (visit_id),
  CONSTRAINT fk_mobility_fact_service_visits_model FOREIGN KEY (model_id) REFERENCES ${catalog}.mobility.dim_vehicle_model (model_id),
  CONSTRAINT fk_mobility_fact_service_visits_dealer FOREIGN KEY (dealer_id) REFERENCES ${catalog}.mobility.dim_dealer (dealer_id),
  CONSTRAINT fk_mobility_fact_service_visits_customer FOREIGN KEY (customer_id) REFERENCES ${catalog}.mobility.dim_customer (customer_id)
)
COMMENT 'Aftersales workshop visits of Nordvik Mobility, one row per visit, Jan-Jun 2026 (Aftersales Service subdomain). Amounts in SEK excl. VAT.'
AS SELECT
  s.visit_id,
  s.visit_date,
  s.dealer_id,
  d.region_code AS dealer_region,
  s.customer_id,
  s.model_id,
  s.vin,
  s.service_type,
  s.labour_hours,
  s.labour_cost_sek,
  s.parts_cost_sek,
  s.billed_amount_sek,
  s.warranty AS is_warranty,
  s.mileage_km
FROM ${catalog}.silver.mobility_service_visits s
LEFT JOIN ${catalog}.silver.mobility_dealers d ON d.dealer_id = s.dealer_id
-- Build order only - never filters a row: makes the pipeline build the dimensions first.
WHERE TRUE
   OR EXISTS (SELECT 1 FROM ${catalog}.mobility.dim_vehicle_model)
   OR EXISTS (SELECT 1 FROM ${catalog}.mobility.dim_dealer)
   OR EXISTS (SELECT 1 FROM ${catalog}.mobility.dim_customer);
