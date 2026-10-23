-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 04 · Governance: region row filters and PII masking (Unity Catalog)
-- MAGIC
-- MAGIC | Who | What they see |
-- MAGIC |---|---|
-- MAGIC | `bootcamp_admins` | Everything, unmasked |
-- MAGIC | `pii_readers` + region access | Unmasked PII for their regions only |
-- MAGIC | Everyone else | Only rows for regions mapped to them in `governance.user_region_access` (`ALL` = every region), with PII masked |
-- MAGIC
-- MAGIC **Before you start:** create the account groups `bootcamp_admins`, `pii_readers`, `bootcamp_analysts` and `bootcamp_engineers` in the account console and assign them to the workspace.
-- MAGIC For the live demo, do **not** put yourself in `bootcamp_admins`, otherwise the filters will not visibly apply.
-- MAGIC
-- MAGIC **Important:**
-- MAGIC - Re-running Notebook 03 or the Silver customers step recreates the tables and removes these policies. Re-run this notebook afterwards.
-- MAGIC - If you re-run only this notebook and a `CREATE OR REPLACE FUNCTION` fails because the function is in use, run the rollback cell (section 8) first, then run this notebook again.
-- MAGIC - Genie runs queries as the signed-in user, so these policies also apply to Genie answers.
-- MAGIC - Row filters and masks need a Unity Catalog-enabled compute: serverless, a SQL warehouse, or a cluster on DBR 15.4+ (standard or dedicated access mode).

-- COMMAND ----------

USE CATALOG fashion_bootcamp;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1. User-to-region mapping table

-- COMMAND ----------

CREATE OR REPLACE TABLE fashion_bootcamp.governance.user_region_access (
  user_email STRING NOT NULL COMMENT 'User principal (email) as returned by current_user().',
  region     STRING NOT NULL COMMENT 'Region the user may see, e.g. Southern Europe. ALL = every region.'
)
COMMENT 'Maps users to the regions they are allowed to see. Drives row filters and PII masks.';

INSERT INTO fashion_bootcamp.governance.user_region_access VALUES
  ('anna.analyst@example.com',   'Western Europe'),
  ('marco.analyst@example.com',  'Southern Europe'),
  ('erik.analyst@example.com',   'Northern Europe'),
  ('lena.analyst@example.com',   'Central Europe'),
  ('piotr.analyst@example.com',  'Eastern Europe'),
  ('claire.manager@example.com', 'ALL');

-- The person running the demo: Southern Europe only
INSERT INTO fashion_bootcamp.governance.user_region_access
SELECT current_user(), 'Southern Europe';

SELECT * FROM fashion_bootcamp.governance.user_region_access ORDER BY region, user_email;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2. Access functions

-- COMMAND ----------

-- Region access: admin, or mapped to the region, or mapped to ALL
CREATE OR REPLACE FUNCTION fashion_bootcamp.governance.has_region_access(p_region STRING)
RETURNS BOOLEAN
COMMENT 'True if the current user is a bootcamp admin or is mapped to p_region (or ALL) in user_region_access.'
RETURN is_account_group_member('bootcamp_admins')
    OR EXISTS (
         SELECT 1 FROM fashion_bootcamp.governance.user_region_access a
         WHERE lower(a.user_email) = lower(current_user())
           AND (a.region = 'ALL' OR a.region = p_region)
       );

-- Store-based row filter for the fact tables: look up the store's region
CREATE OR REPLACE FUNCTION fashion_bootcamp.governance.store_row_filter(p_store_id STRING)
RETURNS BOOLEAN
COMMENT 'Row filter for facts: true if the current user may see the region of the store p_store_id.'
RETURN is_account_group_member('bootcamp_admins')
    OR EXISTS (
         SELECT 1
         FROM fashion_bootcamp.silver.stores s
         JOIN fashion_bootcamp.governance.user_region_access a
           ON a.region = 'ALL' OR a.region = s.region
         WHERE s.store_id = p_store_id
           AND lower(a.user_email) = lower(current_user())
       );

-- PII access: admin, or pii_readers with access to the row's region
CREATE OR REPLACE FUNCTION fashion_bootcamp.governance.has_pii_access(p_region STRING)
RETURNS BOOLEAN
COMMENT 'True if the current user is an admin, or is in pii_readers and has access to p_region.'
RETURN is_account_group_member('bootcamp_admins')
    OR (is_account_group_member('pii_readers') AND fashion_bootcamp.governance.has_region_access(p_region));

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3. Column mask functions (region-aware via `USING COLUMNS (region)`)

-- COMMAND ----------

CREATE OR REPLACE FUNCTION fashion_bootcamp.governance.mask_name(p_value STRING, p_region STRING)
RETURNS STRING
COMMENT 'Shows the name to PII readers for the region; otherwise first letter + ***.'
RETURN CASE WHEN fashion_bootcamp.governance.has_pii_access(p_region) THEN p_value
            WHEN p_value IS NULL THEN NULL
            ELSE concat(left(p_value, 1), '***') END;

CREATE OR REPLACE FUNCTION fashion_bootcamp.governance.mask_email(p_value STRING, p_region STRING)
RETURNS STRING
COMMENT 'Shows the email to PII readers for the region; otherwise s***@domain.'
RETURN CASE WHEN fashion_bootcamp.governance.has_pii_access(p_region) THEN p_value
            WHEN p_value IS NULL THEN NULL
            ELSE concat(left(p_value, 1), '***@', substring_index(p_value, '@', -1)) END;

CREATE OR REPLACE FUNCTION fashion_bootcamp.governance.mask_phone(p_value STRING, p_region STRING)
RETURNS STRING
COMMENT 'Shows the phone to PII readers for the region; otherwise *** *** + last 3 digits.'
RETURN CASE WHEN fashion_bootcamp.governance.has_pii_access(p_region) THEN p_value
            WHEN p_value IS NULL THEN NULL
            ELSE concat('*** *** ', right(regexp_replace(p_value, '[^0-9]', ''), 3)) END;

CREATE OR REPLACE FUNCTION fashion_bootcamp.governance.mask_dob(p_value DATE, p_region STRING)
RETURNS DATE
COMMENT 'Shows the date of birth to PII readers for the region; otherwise truncates it to 1 January of the birth year.'
RETURN CASE WHEN fashion_bootcamp.governance.has_pii_access(p_region) THEN p_value
            ELSE trunc(p_value, 'YEAR') END;

CREATE OR REPLACE FUNCTION fashion_bootcamp.governance.mask_text(p_value STRING, p_region STRING)
RETURNS STRING
COMMENT 'Shows the text to PII readers for the region; otherwise *** REDACTED ***.'
RETURN CASE WHEN fashion_bootcamp.governance.has_pii_access(p_region) THEN p_value
            WHEN p_value IS NULL THEN NULL
            ELSE '*** REDACTED ***' END;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4. Apply row filters

-- COMMAND ----------

ALTER TABLE fashion_bootcamp.gold.dim_customer SET ROW FILTER fashion_bootcamp.governance.has_region_access ON (region);
ALTER TABLE fashion_bootcamp.gold.dim_store    SET ROW FILTER fashion_bootcamp.governance.has_region_access ON (region);
ALTER TABLE fashion_bootcamp.gold.fact_sales   SET ROW FILTER fashion_bootcamp.governance.store_row_filter ON (store_id);
ALTER TABLE fashion_bootcamp.gold.fact_returns SET ROW FILTER fashion_bootcamp.governance.store_row_filter ON (store_id);
ALTER TABLE fashion_bootcamp.gold.fact_finance SET ROW FILTER fashion_bootcamp.governance.store_row_filter ON (store_id);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 5. Apply column masks

-- COMMAND ----------

-- Gold customer dimension
ALTER TABLE fashion_bootcamp.gold.dim_customer ALTER COLUMN customer_name SET MASK fashion_bootcamp.governance.mask_name  USING COLUMNS (region);
ALTER TABLE fashion_bootcamp.gold.dim_customer ALTER COLUMN email         SET MASK fashion_bootcamp.governance.mask_email USING COLUMNS (region);
ALTER TABLE fashion_bootcamp.gold.dim_customer ALTER COLUMN phone         SET MASK fashion_bootcamp.governance.mask_phone USING COLUMNS (region);

-- Silver customers (full PII)
ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN first_name     SET MASK fashion_bootcamp.governance.mask_name  USING COLUMNS (region);
ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN last_name      SET MASK fashion_bootcamp.governance.mask_name  USING COLUMNS (region);
ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN email          SET MASK fashion_bootcamp.governance.mask_email USING COLUMNS (region);
ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN phone          SET MASK fashion_bootcamp.governance.mask_phone USING COLUMNS (region);
ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN date_of_birth  SET MASK fashion_bootcamp.governance.mask_dob   USING COLUMNS (region);
ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN street_address SET MASK fashion_bootcamp.governance.mask_text  USING COLUMNS (region);
ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN postal_code    SET MASK fashion_bootcamp.governance.mask_text  USING COLUMNS (region);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 6. Grants
-- MAGIC Analysts see only Gold. Engineers get Bronze, Silver and Gold; Bronze holds raw, **unmasked** PII, so keep that group small.

-- COMMAND ----------

GRANT ALL PRIVILEGES ON CATALOG fashion_bootcamp TO `bootcamp_admins`;

GRANT USE CATALOG ON CATALOG fashion_bootcamp TO `bootcamp_analysts`;
GRANT USE SCHEMA, SELECT ON SCHEMA fashion_bootcamp.gold TO `bootcamp_analysts`;

GRANT USE CATALOG ON CATALOG fashion_bootcamp TO `pii_readers`;
GRANT USE SCHEMA, SELECT ON SCHEMA fashion_bootcamp.gold TO `pii_readers`;

GRANT USE CATALOG ON CATALOG fashion_bootcamp TO `bootcamp_engineers`;
GRANT USE SCHEMA, SELECT, MODIFY ON SCHEMA fashion_bootcamp.bronze TO `bootcamp_engineers`;
GRANT USE SCHEMA, SELECT, MODIFY ON SCHEMA fashion_bootcamp.silver TO `bootcamp_engineers`;
GRANT USE SCHEMA, SELECT, MODIFY ON SCHEMA fashion_bootcamp.gold   TO `bootcamp_engineers`;

SHOW GRANTS ON SCHEMA fashion_bootcamp.gold;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 7. Demo

-- COMMAND ----------

-- Who am I, and which groups am I in?
SELECT current_user()                                  AS me,
       is_account_group_member('bootcamp_admins')      AS is_admin,
       is_account_group_member('pii_readers')          AS is_pii_reader,
       is_account_group_member('bootcamp_analysts')    AS is_analyst,
       is_account_group_member('bootcamp_engineers')   AS is_engineer,
       (SELECT collect_list(region) FROM fashion_bootcamp.governance.user_region_access
        WHERE lower(user_email) = lower(current_user())) AS my_regions;

-- COMMAND ----------

-- Masked customer query: you should only see Southern Europe customers, with masked PII
SELECT customer_id, customer_name, email, phone, region, customer_segment, loyalty_tier
FROM fashion_bootcamp.gold.dim_customer
ORDER BY customer_id;

-- COMMAND ----------

-- Revenue by store region: only Southern Europe stores appear
SELECT st.region, st.store_name, SUM(f.net_sales_eur) AS revenue_eur
FROM fashion_bootcamp.gold.fact_sales f
JOIN fashion_bootcamp.gold.dim_store st USING (store_id)
GROUP BY st.region, st.store_name
ORDER BY revenue_eur DESC;

-- COMMAND ----------

-- Widen my access to ALL, then re-run the two cells above
UPDATE fashion_bootcamp.governance.user_region_access
SET region = 'ALL'
WHERE lower(user_email) = lower(current_user());

-- COMMAND ----------

-- Put my access back to Southern Europe
UPDATE fashion_bootcamp.governance.user_region_access
SET region = 'Southern Europe'
WHERE lower(user_email) = lower(current_user());

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 8. Rollback (optional)
-- MAGIC The statements below are commented out so that "Run all" does not remove the policies. Uncomment and run them to roll back.

-- COMMAND ----------

SELECT 'Rollback statements are commented out. Uncomment them to remove the policies.' AS note;

-- ALTER TABLE fashion_bootcamp.gold.dim_customer DROP ROW FILTER;
-- ALTER TABLE fashion_bootcamp.gold.dim_store    DROP ROW FILTER;
-- ALTER TABLE fashion_bootcamp.gold.fact_sales   DROP ROW FILTER;
-- ALTER TABLE fashion_bootcamp.gold.fact_returns DROP ROW FILTER;
-- ALTER TABLE fashion_bootcamp.gold.fact_finance DROP ROW FILTER;

-- ALTER TABLE fashion_bootcamp.gold.dim_customer ALTER COLUMN customer_name DROP MASK;
-- ALTER TABLE fashion_bootcamp.gold.dim_customer ALTER COLUMN email         DROP MASK;
-- ALTER TABLE fashion_bootcamp.gold.dim_customer ALTER COLUMN phone         DROP MASK;

-- ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN first_name     DROP MASK;
-- ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN last_name      DROP MASK;
-- ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN email          DROP MASK;
-- ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN phone          DROP MASK;
-- ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN date_of_birth  DROP MASK;
-- ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN street_address DROP MASK;
-- ALTER TABLE fashion_bootcamp.silver.customers ALTER COLUMN postal_code    DROP MASK;
