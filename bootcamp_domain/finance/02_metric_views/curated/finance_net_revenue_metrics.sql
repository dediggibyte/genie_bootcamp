-- ================================================================================================
-- CURATED BOOTCAMP METRIC VIEW (hand-written) - finance.net_revenue_metrics
-- Built on tables of the Lakehouse Industry Data Model "Consumer Goods v2 MVM" (Copyright Databricks,
-- Inc.; Databricks license - see LICENSE.md and NOTICE.md in the bootcamp folder, copies of
-- tools/model/). Created by notebooks/job_tasks/02a_create_metric_views.py (job task metric_views).
--
-- THE authoritative revenue definition of Fjällmark (glossary pages net_revenue, cogs, gross_margin):
--   Net Revenue  = credits - debits on GL accounts of account group REVENUE
--                  (3000 trade revenue, 3010 DTC revenue, 3040 trade discounts, 3050 DTC returns)
--   COGS         = debits - credits on account group COGS (4000 standard cost, 4100 production variances)
--   Gross Margin = Net Revenue - COGS;  Gross Margin % = Gross Margin / Net Revenue (ratio of sums)
-- always in GROUP CURRENCY EUR (journal_entry_line.amount_group_currency), posted documents only.
-- Grain = journal entry LINE (the posting); the header (period, status), account, company code and
-- profit centre are many-to-one joins, so no amount is ever counted twice. There is deliberately no
-- local-currency amount in this view (adding SEK, NOK, DKK, PLN and EUR is the classic currency trap).
-- ================================================================================================

CREATE OR REPLACE VIEW ${catalog}.finance.`net_revenue_metrics`
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: >-
    Official Fjällmark P&L top lines from the general ledger, in group currency EUR, posted
    documents only: Net Revenue (account group REVENUE, credit - debit; after B2B trade discounts and
    DTC returns, excl. VAT and shipping fees), COGS (account group COGS, debit - credit), Gross Margin
    and Gross Margin %, plus DTC / B2B revenue, trade discounts, returns, standard COGS and production
    variances; by fiscal year / period, company code, channel, brand, profit centre and GL account.
    Use this view for any question about revenue, sales, turnover, COGS or margin.
  source: ${catalog}.finance.journal_entry_line
  filter: je_hdr.posting_status = 'posted' AND gl_dim.account_group IN ('REVENUE', 'COGS')
  joins:
    - name: je_hdr
      source: ${catalog}.finance.journal_entry
      'on': source.journal_entry_id = je_hdr.journal_entry_id
    - name: gl_dim
      source: ${catalog}.finance.gl_account
      'on': source.gl_account_id = gl_dim.gl_account_id
    - name: company_dim
      source: ${catalog}.finance.company_code
      'on': source.company_code_id = company_dim.company_code_id
    - name: pc_dim
      source: ${catalog}.finance.profit_center
      'on': source.profit_center_id = pc_dim.profit_center_id
      joins:
        - name: brand_dim
          source: ${catalog}.finance.profit_center
          'on': pc_dim.brand_code = brand_dim.code
  dimensions:
    - name: fiscal_year
      expr: je_hdr.fiscal_year
      display_name: Fiscal year
      comment: Fiscal year of the posting (= calendar year).
      synonyms: [year, financial year, FY]
    - name: fiscal_period
      expr: je_hdr.fiscal_period
      display_name: Fiscal period
      comment: Fiscal period 1-12 (= calendar month).
      synonyms: [period, month number, posting period]
    - name: fiscal_month
      expr: MAKE_DATE(je_hdr.fiscal_year, je_hdr.fiscal_period, 1)
      display_name: Fiscal month
      comment: First day of the fiscal period (fiscal year + period as a date), for monthly trends.
      synonyms: [month, period start]
    - name: fiscal_quarter
      expr: CONCAT(CAST(je_hdr.fiscal_year AS STRING), '-Q', CAST(CEIL(je_hdr.fiscal_period / 3) AS STRING))
      display_name: Fiscal quarter
      comment: Fiscal quarter, e.g. 2026-Q3.
      synonyms: [quarter]
    - name: company_code
      expr: company_dim.code
      display_name: Company code
      comment: Legal entity that booked the line (SE01, NO01, DK01, FI01, DE01, PL01).
      synonyms: [legal entity, entity, company]
    - name: company_name
      expr: company_dim.name
      display_name: Company name
      comment: Name of the legal entity, e.g. Fjällmark Deutschland GmbH.
      synonyms: [entity name, subsidiary]
    - name: company_currency
      expr: company_dim.currency_code
      display_name: Company currency
      comment: Local (company-code) currency of the entity. All measures are nevertheless in EUR.
    - name: channel
      expr: >-
        CASE WHEN gl_dim.account_number IN ('3010', '3050') OR pc_dim.channel_code = 'dtc' THEN 'DTC'
             WHEN gl_dim.account_number IN ('3000', '3040') OR pc_dim.channel_code = 'retail' THEN 'B2B'
             ELSE 'Not allocated (production variances)' END
      display_name: Channel
      comment: >-
        DTC = webshop (accounts 3010/3050, DTC profit centres), B2B = trade customers (3000/3040,
        retail profit centres). Production variances (4100) are booked on plant profit centres and are
        not allocated to a channel.
      synonyms: [sales channel, DTC vs B2B, webshop vs trade]
    - name: account_group
      expr: gl_dim.account_group
      display_name: Account group
      comment: REVENUE or COGS.
    - name: gl_account_number
      expr: gl_dim.account_number
      display_name: GL account number
      comment: 3000, 3010, 3040, 3050 (revenue), 4000, 4100 (COGS) - same numbering in every company code.
      synonyms: [account, account number]
    - name: gl_account_name
      expr: gl_dim.account_name
      display_name: GL account
      comment: Name of the GL account, e.g. 'Revenue - DTC webshop', 'Production variances'.
      synonyms: [account name]
    - name: brand_code
      expr: pc_dim.brand_code
      display_name: Brand code
      comment: Brand of the posting profit centre (BJORKO, KALLKALLA, MJUKCARE).
    - name: brand
      expr: COALESCE(pc_dim.brand_dim.name, pc_dim.brand_code, 'No brand')
      display_name: Brand
      comment: Brand name (Björkö Pantry, Kallkälla, Mjuk Care) of the posting profit centre (brand x channel centres; plant centres carry the brand they produce).
      synonyms: [brand name, label]
    - name: profit_center
      expr: pc_dim.name
      display_name: Profit centre
      comment: Posting profit centre, e.g. 'Mjuk Care - Direct to Consumer' or 'Poznań Personal Care Plant'.
      synonyms: [profit center, segment]
    - name: document_type
      expr: je_hdr.document_type
      display_name: Document type
      comment: SAP-style document type of the journal entry (DR billing/DTC sales, KN DTC returns, WA COGS, SA settlements ...).
  measures:
    - name: net_revenue_eur
      expr: >-
        SUM(CASE WHEN source.debit_credit_indicator = 'C' THEN source.amount_group_currency
                 ELSE -source.amount_group_currency END)
          FILTER (WHERE gl_dim.account_group = 'REVENUE')
      display_name: Net Revenue (EUR)
      comment: >-
        Official Net Revenue: credits - debits on account group REVENUE in group currency EUR (after
        trade discounts and DTC returns; excl. VAT and shipping fees). DTC + B2B.
      synonyms: [net revenue, revenue, net sales, sales, turnover, top line, official revenue, finance revenue]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: cogs_eur
      expr: >-
        SUM(CASE WHEN source.debit_credit_indicator = 'D' THEN source.amount_group_currency
                 ELSE -source.amount_group_currency END)
          FILTER (WHERE gl_dim.account_group = 'COGS')
      display_name: COGS (EUR)
      comment: Cost of goods sold = debits - credits on account group COGS (4000 standard cost + 4100 production variances), EUR.
      synonyms: [COGS, cost of goods sold, cost of sales, product cost]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: gross_margin_eur
      expr: MEASURE(net_revenue_eur) - MEASURE(cogs_eur)
      display_name: Gross Margin (EUR)
      comment: Net Revenue - COGS, EUR.
      synonyms: [gross margin, gross profit, GM]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: gross_margin_pct
      expr: 100 * (MEASURE(net_revenue_eur) - MEASURE(cogs_eur)) / MEASURE(net_revenue_eur)
      display_name: Gross Margin %
      comment: Gross Margin / Net Revenue in percent (0-100), computed from summed EUR amounts (never an average of percentages).
      synonyms: [gross margin percent, GM%, margin %, margin]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: dtc_net_revenue_eur
      expr: >-
        SUM(CASE WHEN source.debit_credit_indicator = 'C' THEN source.amount_group_currency
                 ELSE -source.amount_group_currency END)
          FILTER (WHERE gl_dim.account_number IN ('3010', '3050'))
      display_name: DTC Net Revenue (EUR)
      comment: Webshop revenue in the books = 3010 DTC revenue - 3050 DTC returns, EUR (excl. VAT and shipping; about 25 % below webshop order totals).
      synonyms: [DTC revenue, webshop revenue finance, e-commerce revenue]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: b2b_net_revenue_eur
      expr: >-
        SUM(CASE WHEN source.debit_credit_indicator = 'C' THEN source.amount_group_currency
                 ELSE -source.amount_group_currency END)
          FILTER (WHERE gl_dim.account_number IN ('3000', '3040'))
      display_name: B2B Net Revenue (EUR)
      comment: Trade-customer revenue = 3000 revenue - 3040 trade discounts and rebates, EUR.
      synonyms: [B2B revenue, trade revenue, retail revenue, wholesale revenue]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: gross_sales_eur
      expr: >-
        SUM(CASE WHEN source.debit_credit_indicator = 'C' THEN source.amount_group_currency
                 ELSE -source.amount_group_currency END)
          FILTER (WHERE gl_dim.account_number IN ('3000', '3010'))
      display_name: Gross sales (EUR)
      comment: Revenue before trade discounts and returns (accounts 3000 + 3010), EUR.
      synonyms: [gross revenue, gross sales]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: trade_discounts_eur
      expr: >-
        SUM(CASE WHEN source.debit_credit_indicator = 'D' THEN source.amount_group_currency
                 ELSE -source.amount_group_currency END)
          FILTER (WHERE gl_dim.account_number = '3040')
      display_name: Trade discounts and rebates (EUR)
      comment: B2B trade discounts and rebates (account 3040), EUR, shown as a positive amount.
      synonyms: [trade discounts, rebates, trade spend deductions]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: dtc_returns_eur
      expr: >-
        SUM(CASE WHEN source.debit_credit_indicator = 'D' THEN source.amount_group_currency
                 ELSE -source.amount_group_currency END)
          FILTER (WHERE gl_dim.account_number = '3050')
      display_name: DTC sales returns (EUR)
      comment: Webshop returns booked against revenue (account 3050), EUR, shown as a positive amount.
      synonyms: [returns, sales returns]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: standard_cogs_eur
      expr: >-
        SUM(CASE WHEN source.debit_credit_indicator = 'D' THEN source.amount_group_currency
                 ELSE -source.amount_group_currency END)
          FILTER (WHERE gl_dim.account_number = '4000')
      display_name: COGS at standard cost (EUR)
      comment: Units sold x standard cost (account 4000), EUR.
      synonyms: [standard COGS, standard cost of sales]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: production_variance_eur
      expr: >-
        SUM(CASE WHEN source.debit_credit_indicator = 'D' THEN source.amount_group_currency
                 ELSE -source.amount_group_currency END)
          FILTER (WHERE gl_dim.account_number = '4100')
      display_name: Production variances (EUR)
      comment: Actual - standard production cost booked by the producing entity (account 4100), EUR; positive = cost overrun (e.g. PL01 in March 2026).
      synonyms: [production variance, cost variance, manufacturing variance, yield variance]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: journal_line_count
      expr: COUNT(source.journal_entry_line_id)
      display_name: GL lines
      comment: Number of posted revenue / COGS journal entry lines.
      format:
        type: number
        decimal_places: {type: exact, places: 0}
$$;
