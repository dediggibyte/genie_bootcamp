-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - METRIC VIEWS of the Telecommunications and Media domain:
--   telecom.billing_metrics - invoice grain (telecom.fact_billing): billed revenue, ARPU, overdue
--                             amount, paid share
--   telecom.usage_metrics   - subscription-month grain (telecom.fact_usage): data, voice, SMS,
--                             streaming hours
-- Created by notebooks/job_tasks/2026-10-27-02a-create-metric-views.py (job task metric_views);
-- ${catalog} is replaced by the job parameter `catalog`.
-- Definitions = ecom/data/README.md "Business definitions"; the totals are in
-- data/2026-10-27-expected-answers.json (telecom). ARPU and per-subscription averages are monthly
-- figures: group by billing_month / usage_month (across both months they divide two months of revenue
-- by the distinct subscriptions). Percent measures return 0-100.
-- Governance: the views follow the row filters of their source tables (customer segment).
-- ================================================================================================

CREATE OR REPLACE VIEW ${catalog}.telecom.billing_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: >-
    Nordvik Connect billing KPIs at invoice grain (one invoice per subscription and month), billing
    months 2026-05 and 2026-06, SEK excl. VAT: billed revenue, invoices, billed subscriptions, ARPU,
    overdue and open amounts, paid share; by billing month, customer segment, plan type, plan, sales
    channel and payment status. ARPU is monthly - group by billing_month.
  source: ${catalog}.telecom.fact_billing
  joins:
    - name: plan_dim
      source: ${catalog}.telecom.dim_plan
      'on': source.plan_id = plan_dim.plan_id
    - name: subscription_dim
      source: ${catalog}.telecom.dim_subscription
      'on': source.subscription_id = subscription_dim.subscription_id
  dimensions:
    - name: billing_month
      expr: source.billing_month
      display_name: Billing month
      comment: Month billed (first day of the month) - 2026-05-01 or 2026-06-01.
      synonyms: [month, invoice month, period]
    - name: customer_segment
      expr: source.customer_segment
      display_name: Customer segment
      comment: consumer or business.
      synonyms: [segment, B2B vs B2C, consumer vs business]
    - name: plan_type
      expr: plan_dim.plan_type
      display_name: Plan type
      comment: mobile, broadband, tv_streaming or bundle.
      synonyms: [product, product line, service type]
    - name: plan_name
      expr: plan_dim.plan_name
      display_name: Plan
      comment: Price plan, e.g. Mobil 5G Unlimited, Fiber 1000/1000.
      synonyms: [tariff, price plan, package]
    - name: has_streaming
      expr: CASE WHEN plan_dim.has_streaming THEN 'With streaming' ELSE 'Without streaming' END
      display_name: Streaming included
      comment: Whether the plan includes a streaming service (Netflix, Spotify, Disney+, Max).
      synonyms: [streaming add-on]
    - name: sales_channel
      expr: subscription_dim.sales_channel
      display_name: Sales channel
      comment: Where the subscription was sold - online, store or telesales.
      synonyms: [channel]
    - name: payment_status
      expr: source.payment_status
      display_name: Payment status
      comment: paid, open (not yet due) or overdue.
      synonyms: [status, paid or not]
  measures:
    - name: billed_revenue_sek
      expr: SUM(source.amount_excl_vat_sek)
      display_name: Billed revenue (SEK)
      comment: Invoiced amount excl. VAT.
      synonyms: [revenue, billing, billed amount, sales, turnover]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: invoice_count
      expr: COUNT(source.invoice_id)
      display_name: Invoices
      comment: Number of invoices.
      synonyms: [number of invoices, bills]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: billed_subscriptions
      expr: COUNT(DISTINCT source.subscription_id)
      display_name: Billed subscriptions
      comment: Distinct subscriptions with an invoice.
      synonyms: [subscriptions billed, paying subscriptions]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: arpu_sek
      expr: MEASURE(billed_revenue_sek) / MEASURE(billed_subscriptions)
      display_name: ARPU (SEK)
      comment: Average revenue per billed subscription = billed revenue / billed subscriptions; a monthly figure - group by billing month.
      synonyms: [ARPU, average revenue per user, average revenue per subscription]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: overdue_amount_sek
      expr: COALESCE(SUM(source.amount_excl_vat_sek) FILTER (WHERE source.payment_status = 'overdue'), 0)
      display_name: Overdue amount (SEK)
      comment: Invoiced amount excl. VAT of invoices past their due date and not paid.
      synonyms: [overdue, arrears, late payments, unpaid overdue]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: open_amount_sek
      expr: COALESCE(SUM(source.amount_excl_vat_sek) FILTER (WHERE source.payment_status = 'open'), 0)
      display_name: Open amount (SEK)
      comment: Invoiced amount excl. VAT of invoices not yet due.
      synonyms: [not yet due, outstanding not due]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: paid_share_pct
      expr: COUNT(source.invoice_id) FILTER (WHERE source.payment_status = 'paid') / COUNT(source.invoice_id) * 100
      display_name: Paid share %
      comment: Paid invoices / invoices, 0-100.
      synonyms: [paid rate, collection rate, share paid]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
$$;

CREATE OR REPLACE VIEW ${catalog}.telecom.usage_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: >-
    Nordvik Connect usage KPIs, one row per subscription and month, usage months 2026-05 and 2026-06:
    data GB, voice minutes, SMS, streaming hours, subscriptions with usage and per-subscription averages;
    by usage month, customer segment, plan type and plan. Per-subscription averages are monthly - group
    by usage_month.
  source: ${catalog}.telecom.fact_usage
  joins:
    - name: plan_dim
      source: ${catalog}.telecom.dim_plan
      'on': source.plan_id = plan_dim.plan_id
  dimensions:
    - name: usage_month
      expr: source.usage_month
      display_name: Usage month
      comment: Month of the usage (first day of the month) - 2026-05-01 or 2026-06-01.
      synonyms: [month, period]
    - name: customer_segment
      expr: source.customer_segment
      display_name: Customer segment
      comment: consumer or business.
      synonyms: [segment]
    - name: plan_type
      expr: plan_dim.plan_type
      display_name: Plan type
      comment: mobile, broadband, tv_streaming or bundle.
      synonyms: [product, service type]
    - name: plan_name
      expr: plan_dim.plan_name
      display_name: Plan
      comment: Price plan of the subscription.
      synonyms: [tariff, package]
    - name: has_streaming
      expr: CASE WHEN plan_dim.has_streaming THEN 'With streaming' ELSE 'Without streaming' END
      display_name: Streaming included
      comment: Whether the plan includes a streaming service (Netflix, Spotify, Disney+, Max).
      synonyms: [streaming add-on]
  measures:
    - name: data_gb
      expr: SUM(source.data_gb)
      display_name: Data used (GB)
      comment: Data used in GB, mobile and fixed.
      synonyms: [data, data usage, traffic, GB]
      format:
        type: number
        decimal_places: {type: exact, places: 1}
    - name: active_subscriptions
      expr: COUNT(DISTINCT source.subscription_id)
      display_name: Subscriptions with usage
      comment: Distinct subscriptions with a usage record.
      synonyms: [active subscriptions, active lines, users]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: avg_data_gb_per_subscription
      expr: MEASURE(data_gb) / MEASURE(active_subscriptions)
      display_name: Data per subscription (GB)
      comment: Data used / subscriptions with usage; monthly - group by usage month.
      synonyms: [average data usage, GB per user]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: voice_minutes
      expr: SUM(source.voice_minutes)
      display_name: Voice minutes
      comment: Outgoing call minutes.
      synonyms: [minutes, calls, voice traffic]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: sms_count
      expr: SUM(source.sms_count)
      display_name: SMS
      comment: SMS sent.
      synonyms: [text messages, messages]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: streaming_hours
      expr: SUM(source.streaming_hours)
      display_name: Streaming hours
      comment: Hours streamed in the TV app and the included streaming services.
      synonyms: [viewing hours, watch time, streaming]
      format:
        type: number
        decimal_places: {type: exact, places: 1}
$$;
