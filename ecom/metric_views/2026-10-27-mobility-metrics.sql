-- ================================================================================================
-- ecom bootcamp (Nordvik Group) - METRIC VIEWS of the Mobility and Automotive domain:
--   mobility.vehicle_sales_metrics - vehicle grain (mobility.fact_vehicle_sales): units, revenue,
--                                    average price, discounts, EV share
--   mobility.service_metrics       - visit grain (mobility.fact_service_visits): visits, service
--                                    revenue, labour hours, warranty share
-- Created by notebooks/job_tasks/2026-10-27-02a-create-metric-views.py (job task metric_views);
-- ${catalog} is replaced by the job parameter `catalog`.
-- Definitions = ecom/data/README.md "Business definitions"; the totals are in
-- data/2026-10-27-expected-answers.json (mobility). Measures are sums / counts at the fact grain and
-- ratios are ratios of sums. Percent measures return 0-100.
-- Governance: the views follow the row filters of their source tables (dealer region).
-- ================================================================================================

CREATE OR REPLACE VIEW ${catalog}.mobility.vehicle_sales_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: >-
    Nordvik Mobility new-vehicle sales KPIs, one row per vehicle sold, Jan-Jun 2026, SEK excl. VAT:
    units sold, vehicle revenue (price after discount), average sale price, discounts and EV share; by
    month, region, dealer, brand, model, vehicle type, powertrain, customer type and financing.
  source: ${catalog}.mobility.fact_vehicle_sales
  joins:
    - name: model_dim
      source: ${catalog}.mobility.dim_vehicle_model
      'on': source.model_id = model_dim.model_id
    - name: dealer_dim
      source: ${catalog}.mobility.dim_dealer
      'on': source.dealer_id = dealer_dim.dealer_id
    - name: customer_dim
      source: ${catalog}.mobility.dim_customer
      'on': source.customer_id = customer_dim.customer_id
  dimensions:
    - name: sale_date
      expr: source.sale_date
      display_name: Sale date
      comment: Date of the sale.
      synonyms: [date, contract date]
    - name: sale_month
      expr: CAST(DATE_TRUNC('MONTH', source.sale_date) AS DATE)
      display_name: Sale month
      comment: First day of the month of the sale (2026-01-01 .. 2026-06-01).
      synonyms: [month]
    - name: dealer_region
      expr: source.dealer_region
      display_name: Region
      comment: Region of the dealer - STO (Stockholm incl. Södertälje), GOT, MAL, UME.
      synonyms: [region, area, market]
    - name: dealer_name
      expr: dealer_dim.dealer_name
      display_name: Dealer
      comment: Dealer that sold the vehicle, e.g. Nordvik Mobility Täby; trucks are sold by Nordvik Truck Center Södertälje.
      synonyms: [dealership, showroom, retailer]
    - name: brand
      expr: model_dim.brand
      display_name: Vehicle brand
      comment: Volvo, Tesla, Volkswagen, Toyota, BMW, Kia, Ford, Scania or Mercedes-Benz.
      synonyms: [make, brand, manufacturer]
    - name: model
      expr: CONCAT(model_dim.brand, ' ', model_dim.model_name)
      display_name: Model
      comment: Brand and model, e.g. Volvo EX30, Tesla Model Y.
      synonyms: [vehicle model, car model]
    - name: vehicle_type
      expr: model_dim.vehicle_type
      display_name: Vehicle type
      comment: car, van or truck.
      synonyms: [segment, vehicle category]
    - name: powertrain
      expr: model_dim.powertrain
      display_name: Powertrain
      comment: ev (battery electric), hybrid, petrol or diesel.
      synonyms: [fuel type, drivetrain, engine type]
    - name: customer_type
      expr: customer_dim.customer_type
      display_name: Customer type
      comment: private or fleet.
      synonyms: [buyer type, B2B vs B2C]
    - name: financing
      expr: source.financing
      display_name: Financing
      comment: cash, loan or lease.
      synonyms: [payment type, leasing]
  measures:
    - name: units_sold
      expr: COUNT(source.sale_id)
      display_name: Vehicles sold
      comment: Number of vehicles sold (one row per vehicle).
      synonyms: [units, vehicles, cars sold, registrations, volume]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: vehicle_revenue_sek
      expr: SUM(source.net_sale_price_sek)
      display_name: Vehicle revenue (SEK)
      comment: Sale price - discount, SEK excl. VAT.
      synonyms: [revenue, sales, turnover, vehicle sales]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: average_sale_price_sek
      expr: MEASURE(vehicle_revenue_sek) / MEASURE(units_sold)
      display_name: Average sale price (SEK)
      comment: Vehicle revenue / vehicles sold.
      synonyms: [average price, ASP, average transaction price]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: discount_sek
      expr: SUM(source.discount_sek)
      display_name: Discounts (SEK)
      comment: Discounts given on vehicle sales.
      synonyms: [discount, rebate]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: ev_units
      expr: COUNT(source.sale_id) FILTER (WHERE model_dim.is_ev)
      display_name: EVs sold
      comment: Battery electric vehicles sold (powertrain = ev).
      synonyms: [electric vehicles sold, EV sales]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: ev_share_pct
      expr: MEASURE(ev_units) / MEASURE(units_sold) * 100
      display_name: EV share %
      comment: Battery electric vehicles / vehicles sold, 0-100.
      synonyms: [EV share, electric share, EV mix, share of electric]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
$$;

CREATE OR REPLACE VIEW ${catalog}.mobility.service_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: >-
    Nordvik Mobility aftersales KPIs, one row per workshop visit, Jan-Jun 2026, SEK excl. VAT: visits,
    service revenue (amount billed to customers; warranty work is 0), labour hours, parts and labour cost,
    warranty share; by month, region, dealer, service type, brand, vehicle type and powertrain.
  source: ${catalog}.mobility.fact_service_visits
  joins:
    - name: model_dim
      source: ${catalog}.mobility.dim_vehicle_model
      'on': source.model_id = model_dim.model_id
    - name: dealer_dim
      source: ${catalog}.mobility.dim_dealer
      'on': source.dealer_id = dealer_dim.dealer_id
  dimensions:
    - name: visit_date
      expr: source.visit_date
      display_name: Visit date
      comment: Date of the workshop visit.
      synonyms: [date, service date]
    - name: visit_month
      expr: CAST(DATE_TRUNC('MONTH', source.visit_date) AS DATE)
      display_name: Visit month
      comment: First day of the month of the visit.
      synonyms: [month]
    - name: dealer_region
      expr: source.dealer_region
      display_name: Region
      comment: Region of the workshop - STO, GOT, MAL (no workshop in UME).
      synonyms: [region, area]
    - name: dealer_name
      expr: dealer_dim.dealer_name
      display_name: Workshop
      comment: Dealer workshop that did the work.
      synonyms: [dealer, workshop, service centre, garage]
    - name: service_type
      expr: source.service_type
      display_name: Service type
      comment: annual_service, tyre_change, brake_service, battery_check, software_update or warranty_repair.
      synonyms: [job type, work type, service]
    - name: warranty
      expr: CASE WHEN source.is_warranty THEN 'Warranty' ELSE 'Customer paid' END
      display_name: Warranty
      comment: Warranty (paid by the manufacturer, billed 0) or Customer paid.
      synonyms: [warranty work, paid by]
    - name: brand
      expr: model_dim.brand
      display_name: Vehicle brand
      comment: Brand of the serviced vehicle.
      synonyms: [make, brand]
    - name: vehicle_type
      expr: model_dim.vehicle_type
      display_name: Vehicle type
      comment: car, van or truck.
    - name: powertrain
      expr: model_dim.powertrain
      display_name: Powertrain
      comment: ev, hybrid, petrol or diesel.
      synonyms: [fuel type]
  measures:
    - name: service_visits
      expr: COUNT(source.visit_id)
      display_name: Service visits
      comment: Number of workshop visits.
      synonyms: [visits, jobs, workshop visits, repair orders]
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: service_revenue_sek
      expr: SUM(source.billed_amount_sek)
      display_name: Service revenue (SEK)
      comment: Amount billed to customers (labour + parts; 0 for warranty work), SEK excl. VAT.
      synonyms: [aftersales revenue, workshop revenue, service sales]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: labour_hours
      expr: SUM(source.labour_hours)
      display_name: Labour hours
      comment: Workshop hours worked (incl. warranty work).
      synonyms: [hours, workshop hours, mechanic hours]
      format:
        type: number
        decimal_places: {type: exact, places: 1}
    - name: labour_cost_sek
      expr: SUM(source.labour_cost_sek)
      display_name: Labour value (SEK)
      comment: Labour at the workshop hourly rate (incl. warranty work).
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: parts_cost_sek
      expr: SUM(source.parts_cost_sek)
      display_name: Parts (SEK)
      comment: Parts used (incl. warranty work).
      synonyms: [parts, spare parts]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
    - name: warranty_visits
      expr: COUNT(source.visit_id) FILTER (WHERE source.is_warranty)
      display_name: Warranty visits
      comment: Visits for warranty repairs.
      format:
        type: number
        decimal_places: {type: exact, places: 0}
    - name: warranty_share_pct
      expr: MEASURE(warranty_visits) / MEASURE(service_visits) * 100
      display_name: Warranty share %
      comment: Warranty visits / visits, 0-100.
      synonyms: [warranty rate, warranty share]
      format:
        type: number
        decimal_places: {type: exact, places: 2}
$$;
