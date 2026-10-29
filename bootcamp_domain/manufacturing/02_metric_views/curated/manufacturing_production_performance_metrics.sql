-- ================================================================================================
-- CURATED BOOTCAMP METRIC VIEW (hand-written) - manufacturing.production_performance_metrics
-- Built on tables of the Lakehouse Industry Data Model "Consumer Goods v2 MVM" (Copyright Databricks,
-- Inc.; Databricks license - see LICENSE.md and NOTICE.md in the bootcamp folder, copies of
-- tools/model/). Created by notebooks/job_tasks/02a_create_metric_views.py (job task metric_views).
--
-- Plant and line performance at PRODUCTION-ORDER grain (manufacturing.production_order; plant, line
-- and FX are many-to-one joins). Only FINISHED orders (actual_finish_timestamp set); the period is
-- the month of actual_finish_timestamp. Definitions follow the glossary pages oee, yield, scrap_rate,
-- schedule_adherence, downtime and production_cost_variance:
--   OEE %            = average of production_order.oee_percentage (0-100)
--   Yield %          = SUM(confirmed_quantity) / SUM(order_quantity)   (quantity-weighted; the same
--                      quantities as manufacturing.yield_record input / output - one record per order)
--   Scrap rate %     = SUM(scrap_quantity) / SUM(order_quantity)
--   On-time %        = orders with actual finish date <= scheduled_finish_date / finished orders
--   Downtime         = SUM(production_order.downtime_minutes)  (order grain only - never add the
--                      confirmation or batch downtime, they describe the same stops)
--   Cost variance    = actual_cost - planned_cost of completed orders (CNF, DLV, TECO, CLSD)
-- Costs are in the plant currency (*_local: SEK, EUR, PLN - group by currency_code) or in EUR
-- (*_eur) with the finance monthly rate of that currency in the finish month.
-- ================================================================================================

CREATE OR REPLACE VIEW ${catalog}.manufacturing.`production_performance_metrics`
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: >-
    Fjällmark plant and production-line performance for finished production orders: OEE, yield,
    scrap rate, on-time completion, downtime, changeover time and planned vs actual cost variance
    (plant currency and EUR), by plant, line, finish month, order status and order type. Period =
    month of the actual finish. Use for questions such as Tampere ramp-up OEE or the March 2026
    Poznań line PL-POZ-L2 incident.
  source: ${catalog}.manufacturing.production_order
  filter: source.actual_finish_timestamp IS NOT NULL
  joins:
    - name: plant_dim
      source: ${catalog}.manufacturing.manufacturing_facility
      'on': source.manufacturing_facility_id = plant_dim.manufacturing_facility_id
    - name: line_dim
      source: ${catalog}.manufacturing.production_line
      'on': source.production_line_id = line_dim.production_line_id
    - name: fx_dim
      source: |-
        SELECT jel.company_code_currency_code AS currency_code, je.fiscal_year, je.fiscal_period,
               AVG(jel.exchange_rate) AS eur_rate
        FROM ${catalog}.finance.journal_entry_line jel
        JOIN ${catalog}.finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
        WHERE je.posting_status = 'posted'
        GROUP BY jel.company_code_currency_code, je.fiscal_year, je.fiscal_period
      'on': >-
        source.currency_code = fx_dim.currency_code
        AND year(source.actual_finish_timestamp) = fx_dim.fiscal_year
        AND month(source.actual_finish_timestamp) = fx_dim.fiscal_period
  dimensions:
    - name: finish_month
      expr: CAST(DATE_TRUNC('MONTH', source.actual_finish_timestamp) AS DATE)
      display_name: Finish month
      comment: First day of the month the production order finished (actual_finish_timestamp).
      synonyms: [month, production month, period]
    - name: finish_quarter
      expr: CONCAT(CAST(YEAR(source.actual_finish_timestamp) AS STRING), '-Q', CAST(QUARTER(source.actual_finish_timestamp) AS STRING))
      display_name: Finish quarter
      comment: Quarter of the actual finish, e.g. 2026-Q2.
      synonyms: [quarter]
    - name: finish_year
      expr: YEAR(source.actual_finish_timestamp)
      display_name: Finish year
      comment: Year of the actual finish.
      synonyms: [year]
    - name: plant
      expr: plant_dim.erp_plant_code
      display_name: Plant
      comment: Site code SE-LUN (Lund food), SE-NKP (Norrköping beverages), FI-TMP (Tampere oat drinks, from April 2025), PL-POZ (Poznań personal care).
      synonyms: [site, factory, facility, plant code]
    - name: plant_name
      expr: plant_dim.facility_name
      display_name: Plant name
      comment: Name of the plant, e.g. 'Tampere Oat Drink Plant'.
      synonyms: [factory name, site name]
    - name: plant_code
      expr: source.plant_code
      display_name: SAP plant code
      comment: 4-character SAP plant code (LUND, NKPG, TMPR, POZN).
    - name: production_line
      expr: line_dim.mes_asset_tag
      display_name: Production line
      comment: Line tag, e.g. PL-POZ-L2 (Poznań liquid filling) or FI-TMP-L1.
      synonyms: [line, line tag, packing line, filling line]
    - name: line_code
      expr: line_dim.line_code
      display_name: Line code
      comment: SAP-style line code, e.g. POZNL2.
    - name: line_name
      expr: line_dim.line_name
      display_name: Line name
      comment: Descriptive line name.
    - name: order_status
      expr: source.order_status
      display_name: Order status
      comment: SAP status of the order - CNF, DLV, TECO, CLSD (completed); CRTD, REL, PCNF (open).
      synonyms: [status, production order status]
    - name: order_type
      expr: source.order_type
      display_name: Order type
      comment: PP01 standard production, PP03 rework, other PP types.
    - name: material_number
      expr: source.material_number
      display_name: Material number
      comment: Finished-good material number produced (FG...). Product names are in the product domain (full model only).
      synonyms: [material, finished good]
    - name: currency_code
      expr: source.currency_code
      display_name: Plant currency
      comment: Currency of the order costs (SEK for Lund/Norrköping, EUR for Tampere, PLN for Poznań). Group *_local measures by it.
      synonyms: [currency, local currency]
  measures:
    - name: finished_order_count
      expr: COUNT(source.production_order_id)
      display_name: Finished production orders
      comment: Number of production orders finished in the period.
      synonyms: [production orders, orders, number of orders]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: oee_pct
      expr: AVG(source.oee_percentage)
      display_name: OEE %
      comment: Overall equipment effectiveness = simple average of order OEE (availability x performance x quality), 0-100, orders with an OEE value.
      synonyms: [OEE, overall equipment effectiveness, line efficiency, equipment effectiveness]
      format:
        type: number
        decimal_places: {type: exact, places: 1}
    - name: oee_weighted_pct
      expr: SUM(source.oee_percentage * source.confirmed_quantity) FILTER (WHERE source.oee_percentage IS NOT NULL) / SUM(source.confirmed_quantity) FILTER (WHERE source.oee_percentage IS NOT NULL)
      display_name: OEE % (volume-weighted)
      comment: OEE weighted by confirmed quantity, 0-100 - only when a volume-weighted OEE is asked for.
      format:
        type: number
        decimal_places: {type: exact, places: 1}
    - name: oee_target_pct
      expr: AVG(line_dim.nominal_oee_target_percent)
      display_name: OEE target %
      comment: Average nominal OEE target of the lines that ran the orders (line targets 78-83 %).
      synonyms: [OEE target, target OEE]
      format:
        type: number
        decimal_places: {type: exact, places: 1}
    - name: order_quantity
      expr: SUM(source.order_quantity)
      display_name: Planned quantity
      comment: Planned (input) quantity of the orders, EA.
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: confirmed_quantity
      expr: SUM(source.confirmed_quantity)
      display_name: Good output quantity
      comment: Confirmed good output, EA.
      synonyms: [output, produced quantity, production volume]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: scrap_quantity
      expr: SUM(source.scrap_quantity)
      display_name: Scrap quantity
      comment: Scrapped quantity, EA.
      synonyms: [scrap, waste]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: yield_pct
      expr: 100 * SUM(source.confirmed_quantity) / SUM(source.order_quantity)
      display_name: Yield %
      comment: Quantity-weighted yield = good output / input quantity in percent (0-100); normal ~97 %.
      synonyms: [yield, production yield, first pass yield, output yield]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: scrap_rate_pct
      expr: 100 * SUM(source.scrap_quantity) / SUM(source.order_quantity)
      display_name: Scrap rate %
      comment: Scrapped quantity / input quantity in percent (0-100); line target 2.5 %.
      synonyms: [scrap rate, scrap %, waste rate, reject rate]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: on_time_completion_pct
      expr: 100 * COUNT(source.production_order_id) FILTER (WHERE CAST(source.actual_finish_timestamp AS DATE) <= source.scheduled_finish_date) / COUNT(source.production_order_id)
      display_name: On-time completion %
      comment: Schedule adherence = orders finished on or before their scheduled finish date / finished orders, in percent (0-100).
      synonyms: [schedule adherence, on-time completion, on time production, schedule attainment]
      format:
        type: number
        decimal_places: {type: exact, places: 1}
    - name: late_order_count
      expr: COUNT(source.production_order_id) FILTER (WHERE CAST(source.actual_finish_timestamp AS DATE) > source.scheduled_finish_date)
      display_name: Late orders
      comment: Orders finished after their scheduled finish date.
      synonyms: [late production orders, delayed orders]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: avg_days_late
      expr: AVG(datediff(CAST(source.actual_finish_timestamp AS DATE), source.scheduled_finish_date)) FILTER (WHERE CAST(source.actual_finish_timestamp AS DATE) > source.scheduled_finish_date)
      display_name: Average days late
      comment: Average delay in days of the late orders.
      format:
        type: number
        decimal_places: {type: exact, places: 1}
    - name: downtime_minutes
      expr: SUM(source.downtime_minutes)
      display_name: Downtime (minutes)
      comment: Stop time during production orders (order grain). Changeovers are separate.
      synonyms: [downtime, line stops, stoppage, breakdown time]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: downtime_minutes_per_order
      expr: SUM(source.downtime_minutes) / COUNT(source.production_order_id)
      display_name: Downtime per order (minutes)
      comment: Downtime minutes per finished order - use to compare lines of different volume.
      format:
        type: number
        decimal_places: {type: exact, places: 1}
    - name: changeover_minutes
      expr: SUM(source.changeover_time_minutes)
      display_name: Changeover time (minutes)
      comment: Changeover minutes before the orders (not downtime).
      synonyms: [changeover, setup time]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: planned_cost_local
      expr: SUM(source.planned_cost) FILTER (WHERE upper(source.order_status) IN ('CNF', 'DLV', 'TECO', 'CLSD'))
      display_name: Planned cost (plant currency)
      comment: Planned cost (order quantity x standard cost) of completed orders in the plant currency - group by currency_code.
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: actual_cost_local
      expr: SUM(source.actual_cost) FILTER (WHERE upper(source.order_status) IN ('CNF', 'DLV', 'TECO', 'CLSD'))
      display_name: Actual cost (plant currency)
      comment: Actual cost of completed orders in the plant currency - group by currency_code.
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: cost_variance_local
      expr: MEASURE(actual_cost_local) - MEASURE(planned_cost_local)
      display_name: Cost variance (plant currency)
      comment: Actual - planned cost of completed orders in the plant currency (positive = overrun) - group by currency_code.
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: cost_variance_pct
      expr: 100 * (MEASURE(actual_cost_local) - MEASURE(planned_cost_local)) / MEASURE(planned_cost_local)
      display_name: Cost variance %
      comment: (Actual - planned) / planned cost in percent; computed in the plant currency, so only meaningful per currency_code / plant (use cost_variance_eur_pct across plants).
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: planned_cost_eur
      expr: SUM(source.planned_cost * fx_dim.eur_rate) FILTER (WHERE upper(source.order_status) IN ('CNF', 'DLV', 'TECO', 'CLSD'))
      display_name: Planned cost (EUR)
      comment: Planned cost of completed orders in EUR (finance monthly rate of the plant currency).
      synonyms: [planned cost, standard cost of production]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: actual_cost_eur
      expr: SUM(source.actual_cost * fx_dim.eur_rate) FILTER (WHERE upper(source.order_status) IN ('CNF', 'DLV', 'TECO', 'CLSD'))
      display_name: Actual cost (EUR)
      comment: Actual cost of completed orders in EUR.
      synonyms: [actual cost, production cost]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: cost_variance_eur
      expr: MEASURE(actual_cost_eur) - MEASURE(planned_cost_eur)
      display_name: Cost variance (EUR)
      comment: Actual - planned production cost of completed orders in EUR (positive = overrun); reaches the P&L as production variances (GL 4100).
      synonyms: [cost variance, production cost variance, cost overrun, manufacturing variance]
      format:
        type: currency
        currency_code: EUR
        decimal_places: {type: exact, places: 2}
    - name: cost_variance_eur_pct
      expr: 100 * (MEASURE(actual_cost_eur) - MEASURE(planned_cost_eur)) / MEASURE(planned_cost_eur)
      display_name: Cost variance % (EUR basis)
      comment: (Actual - planned) / planned cost in percent on an EUR basis - safe across plants.
      synonyms: [cost variance percent, overrun %]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
$$;
