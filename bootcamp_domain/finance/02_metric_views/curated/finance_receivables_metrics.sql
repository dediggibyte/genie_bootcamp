-- ================================================================================================
-- CURATED BOOTCAMP METRIC VIEW (hand-written) - finance.receivables_metrics
-- Built on tables of the Lakehouse Industry Data Model "Consumer Goods v2 MVM" (Copyright Databricks,
-- Inc.; Databricks license - see LICENSE.md and NOTICE.md in the bootcamp folder, copies of
-- tools/model/). Created by notebooks/job_tasks/02a_create_metric_views.py (job task metric_views).
--
-- B2B trade receivables at INVOICE grain (finance.ar_invoice; company code and FX are many-to-one).
-- Status, balances and aging are a period-end SNAPSHOT as of the reporting date 2026-09-30 (the last
-- closed period of the extract) - the date is fixed in this view on purpose. Definitions follow the
-- glossary pages dso and overdue_receivable:
--   Open AR       = SUM(outstanding_balance)                       (total - received - written off)
--   Overdue AR    = open balance of invoices with due_date < 2026-09-30
--   DSO           = open AR / (credit sales billed Jul-Sep 2026 / 92 days)
-- *_local amounts are in the invoice currency (group by currency_code / company_code); *_eur amounts
-- are translated with the September 2026 finance rate of the company code (closing-month rate, the
-- glossary's rule for balances) so they can be added across entities.
-- ================================================================================================

CREATE OR REPLACE VIEW ${catalog}.finance.`receivables_metrics`
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: >-
    B2B accounts-receivable KPIs as of the reporting date 2026-09-30, at invoice grain: open AR,
    overdue AR and overdue share, disputed AR, billing, collections, DSO (open AR / Q3-2026 credit
    sales per day, 92 days) and days past due; by company code, aging bucket, invoice status, dispute
    flag, trade account and billing month. *_local amounts are in the invoice currency (group by
    currency_code); *_eur amounts are translated at the September 2026 finance rate. Webshop orders
    are prepaid and not part of receivables.
  source: ${catalog}.finance.ar_invoice
  joins:
    - name: company_dim
      source: ${catalog}.finance.company_code
      'on': source.company_code_id = company_dim.company_code_id
    - name: fx_dim
      source: |-
        SELECT jel.company_code_id, AVG(jel.exchange_rate) AS eur_rate
        FROM ${catalog}.finance.journal_entry_line jel
        JOIN ${catalog}.finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
        WHERE je.posting_status = 'posted' AND je.fiscal_year = 2026 AND je.fiscal_period = 9
        GROUP BY jel.company_code_id
      'on': source.company_code_id = fx_dim.company_code_id
  dimensions:
    - name: company_code
      expr: company_dim.code
      display_name: Company code
      comment: Selling legal entity that owns the receivable (SE01, NO01, DK01, FI01, DE01, PL01).
      synonyms: [legal entity, entity, company]
    - name: company_name
      expr: company_dim.name
      display_name: Company name
      comment: Name of the legal entity, e.g. Fjällmark Deutschland GmbH.
    - name: currency_code
      expr: source.currency_code
      display_name: Invoice currency
      comment: Currency of the invoice = currency of the selling entity (SEK, NOK, DKK, EUR, PLN). Group *_local measures by it.
      synonyms: [currency, local currency]
    - name: aging_bucket
      expr: >-
        CASE WHEN source.outstanding_balance IS NULL OR source.outstanding_balance <= 0 THEN 'settled'
             WHEN source.due_date >= DATE'2026-09-30' THEN 'current'
             WHEN datediff(DATE'2026-09-30', source.due_date) <= 30 THEN '1_30_days'
             WHEN datediff(DATE'2026-09-30', source.due_date) <= 60 THEN '31_60_days'
             WHEN datediff(DATE'2026-09-30', source.due_date) <= 90 THEN '61_90_days'
             WHEN datediff(DATE'2026-09-30', source.due_date) <= 120 THEN 'over_90_days'
             ELSE 'over_120_days' END
      display_name: Aging bucket
      comment: >-
        Days past due at 2026-09-30 for invoices with an open balance: current (not yet due), 1_30_days,
        31_60_days, 61_90_days, over_90_days (91-120), over_120_days; settled = nothing open.
      synonyms: [AR aging, aging, days past due bucket, overdue bucket]
    - name: is_overdue
      expr: CASE WHEN source.outstanding_balance > 0 AND source.due_date < DATE'2026-09-30' THEN 'Overdue' ELSE 'Not overdue' END
      display_name: Overdue
      comment: Overdue = open balance and due date before the reporting date 2026-09-30.
      synonyms: [past due, late]
    - name: invoice_status
      expr: source.invoice_status
      display_name: Invoice status
      comment: Status at 2026-09-30 - open, partially_paid, paid, disputed, written_off.
      synonyms: [status]
    - name: dispute_status
      expr: CASE WHEN source.dispute_flag THEN 'Disputed' ELSE 'Not disputed' END
      display_name: Dispute status
      comment: Whether the customer disputes the invoice (dispute_flag; reason in dispute_reason). Disputed items stay in AR and DSO.
      synonyms: [disputed, dispute]
    - name: dispute_reason
      expr: source.dispute_reason
      display_name: Dispute reason
      comment: Reason given by the customer for a disputed invoice.
    - name: trade_account_id
      expr: source.trade_account_id
      display_name: Trade account (customer id)
      comment: >-
        B2B customer key (sales.trade_account). Customer names are in the sales domain, which is only
        built by the full industry model - in the bootcamp analyse by this id.
      synonyms: [customer, customer id, account, debtor]
    - name: distribution_channel
      expr: source.distribution_channel
      display_name: Distribution channel
      comment: Distribution channel of the billing document.
    - name: billing_month
      expr: CAST(DATE_TRUNC('MONTH', source.billing_date) AS DATE)
      display_name: Billing month
      comment: First day of the month the invoice was issued.
      synonyms: [invoice month, month]
    - name: billing_year
      expr: YEAR(source.billing_date)
      display_name: Billing year
      comment: Year the invoice was issued.
      synonyms: [year]
    - name: due_month
      expr: CAST(DATE_TRUNC('MONTH', source.due_date) AS DATE)
      display_name: Due month
      comment: First day of the month the invoice is (was) due.
    - name: payment_terms_code
      expr: source.payment_terms_code
      display_name: Payment terms
      comment: Payment terms code of the invoice (normally 30 days, 45 days in DE/NL).
  measures:
    - name: invoice_count
      expr: COUNT(source.ar_invoice_id)
      display_name: Invoices
      comment: Number of AR invoices.
      synonyms: [number of invoices]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: open_invoice_count
      expr: COUNT(source.ar_invoice_id) FILTER (WHERE source.outstanding_balance > 0)
      display_name: Open invoices
      comment: Invoices with an open balance at 2026-09-30.
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: overdue_invoice_count
      expr: COUNT(source.ar_invoice_id) FILTER (WHERE source.outstanding_balance > 0 AND source.due_date < DATE'2026-09-30')
      display_name: Overdue invoices
      comment: Invoices with an open balance whose due date is before 2026-09-30.
      synonyms: [late invoices, past due invoices]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: disputed_invoice_count
      expr: COUNT(source.ar_invoice_id) FILTER (WHERE source.dispute_flag)
      display_name: Disputed invoices
      comment: Invoices the customer disputes (dispute_flag = true).
      synonyms: [disputes, number of disputes]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: open_ar_local
      expr: SUM(source.outstanding_balance)
      display_name: Open AR (local currency)
      comment: Open receivables at 2026-09-30 in the invoice currency - only meaningful per currency_code / company_code.
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: overdue_ar_local
      expr: SUM(source.outstanding_balance) FILTER (WHERE source.due_date < DATE'2026-09-30')
      display_name: Overdue AR (local currency)
      comment: Open balance of overdue invoices in the invoice currency - only meaningful per currency_code / company_code.
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: billed_amount_local
      expr: SUM(source.total_amount) FILTER (WHERE lower(source.invoice_status) <> 'cancelled')
      display_name: Billed amount (local currency)
      comment: Invoiced amount incl. VAT (total_amount) in the invoice currency.
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: open_ar_eur
      expr: SUM(source.outstanding_balance * fx_dim.eur_rate)
      display_name: Open AR (EUR)
      comment: Open receivables at 2026-09-30 translated to EUR at the September 2026 rate; can be added across entities.
      synonyms: [open AR, open receivables, accounts receivable, receivables balance, outstanding balance]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: overdue_ar_eur
      expr: SUM(source.outstanding_balance * fx_dim.eur_rate) FILTER (WHERE source.due_date < DATE'2026-09-30')
      display_name: Overdue AR (EUR)
      comment: Open balance of invoices past their due date at 2026-09-30, EUR (September 2026 rate).
      synonyms: [overdue AR, overdue receivables, past due receivables, late payments]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: overdue_share_pct
      expr: 100 * MEASURE(overdue_ar_eur) / MEASURE(open_ar_eur)
      display_name: Overdue share of open AR %
      comment: Overdue AR / open AR in percent (0-100).
      synonyms: [overdue ratio, overdue percentage]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: disputed_ar_eur
      expr: SUM(source.outstanding_balance * fx_dim.eur_rate) FILTER (WHERE source.dispute_flag)
      display_name: Disputed AR (EUR)
      comment: Open balance of disputed invoices, EUR (September 2026 rate). Disputed items are excluded from automatic dunning.
      synonyms: [disputed receivables, disputed amount]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: billed_amount_eur
      expr: SUM(source.total_amount * fx_dim.eur_rate) FILTER (WHERE lower(source.invoice_status) <> 'cancelled')
      display_name: Billed amount (EUR, Sep-2026 rate)
      comment: >-
        Invoiced amount incl. VAT translated at the September 2026 rate (the DSO convention). Not revenue -
        use finance.net_revenue_metrics for Net Revenue.
      synonyms: [billing, credit sales, invoiced amount]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: collection_rate_pct
      expr: 100 * SUM(source.amount_received * fx_dim.eur_rate) / SUM(source.total_amount * fx_dim.eur_rate)
      display_name: Collection rate %
      comment: Amount received / amount billed in percent (0-100), EUR basis.
      synonyms: [collected share, cash collection rate]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: dso_days
      expr: >-
        MEASURE(open_ar_eur)
          / (SUM(source.total_amount * fx_dim.eur_rate)
               FILTER (WHERE source.billing_date BETWEEN DATE'2026-07-01' AND DATE'2026-09-30'
                         AND lower(source.invoice_status) <> 'cancelled') / 92)
      display_name: DSO (days)
      comment: >-
        Days sales outstanding at 2026-09-30 = open AR / (credit sales billed Jul-Sep 2026 / 92 days),
        both in EUR at the September 2026 rate (per company code this equals the local-currency
        ratio). Group by company code (or customer / currency), not by billing or due month.
      synonyms: [DSO, days sales outstanding, debtor days, collection period, receivable days]
      format:
        type: number
        decimal_places: {type: exact, places: 1}
    - name: avg_days_past_due
      expr: AVG(datediff(DATE'2026-09-30', source.due_date)) FILTER (WHERE source.outstanding_balance > 0 AND source.due_date < DATE'2026-09-30')
      display_name: Average days past due
      comment: Average days past due (2026-09-30 - due date) of the overdue invoices.
      synonyms: [days overdue, average delay]
      format:
        type: number
        decimal_places: {type: exact, places: 1}
$$;
