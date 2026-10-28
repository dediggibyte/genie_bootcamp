# Nordvik Group - synthetic data for the ecom bootcamp

> **All data in this folder is synthetic and fictional.** Nordvik Group and its business units Nordvik Retail, Nordvik Mobility and Nordvik Connect do not exist. Every store, dealer, customer, order, sale, service visit, subscription and invoice is invented. Names are random combinations, e-mail addresses use the reserved `example.com` domain and phone numbers come from the Swedish range reserved for fiction (`+46 70 174 06 05` .. `99`). **Real brand and model names (Apple, Samsung, H&M, Dior, Volvo, Tesla, Scania, Netflix, Spotify, ...) only describe the products, vehicle models and streaming add-ons on sale**; prices are illustrative. Any resemblance to real companies or persons is coincidental.

The generator is `ecom/tools/2026-10-27-generate-data.py` (standard library only, deterministic: the same script always writes the same bytes). Do not edit the files by hand:

```bash
python3 -I ecom/tools/2026-10-27-generate-data.py           # (re)write the files
python3 -I ecom/tools/2026-10-27-generate-data.py --check   # exit 1 if a file is missing or stale
```

## Contents

* `<domain>/2026-10-27-<table>.csv` - one file per table, 17 files, **every file below 50 rows**. `notebooks/2026-10-27-01-setup-catalog.py` copies them to `/Volumes/<catalog>/landing/raw_files/<domain>/<table>/` (one folder per table for `read_files`).
* `2026-10-27-manifest.json` - per domain and table: `file`, `rows` (rows in the CSV), `clean_rows` (rows silver keeps), `primary_key`, `columns` and `dq_issues`. The top-level `_notice` key is a string, not a domain - skip it when you loop over the domains.
* `2026-10-27-expected-answers.json` - the numbers computed from the clean data (= what silver and gold contain): the single source for the Genie benchmarks, the dashboard sanity checks, the governance row counts and the example answers in `ecom/README.md`.
* `README.md` - this file.

## CSV format

* UTF-8, comma separated, `\n` line endings, header row. Only fields that contain a comma are quoted (`csv` module, RFC 4180). Read every column as STRING in bronze.
* Empty field = NULL. Dates `yyyy-MM-dd` (except the documented `dd/MM/yyyy` rows), amounts in **SEK** with two decimals, booleans `true` / `false` (except the documented `Y` / `N` rows).
* Keys are readable strings with a per-table prefix (`P001` product, `O0001` order, `D01` dealer, `SUB001` subscription, ...). Customer ids differ per business unit (`C` retail, `K` mobility, `N` telecom): the three domains have separate customer registers and are never joined.

## The company in brief

**Nordvik Group** (HQ Stockholm) runs three business units in Sweden. Each one is a data domain with its own gold schema, metric views, Genie agent and dashboard.

| domain | business unit | gold schema | period | subdomains |
|---|---|---|---|---|
| Retail and Commerce | Nordvik Retail - 5 stores + webshop (electronics, fashion, beauty) | `retail` | orders 2026-01-01 .. 2026-06-30 | Product Catalog, Stores & Channels, Customers, Sales & Returns |
| Mobility and Automotive | Nordvik Mobility - 5 car dealers with workshops + 1 truck centre | `mobility` | sales and service visits 2026-01-01 .. 2026-06-30 | Vehicle Catalog, Dealer Network, Vehicle Sales, Aftersales Service |
| Telecommunications and Media | Nordvik Connect - mobile, fibre and TV / streaming operator | `telecom` | billing and usage months **2026-05 and 2026-06** (two months keep the files below 50 rows) | Plans & Products, Customers & Subscriptions, Billing, Usage |

**Regions** (row-filter scopes of the governance notebook): retail stores `STO`, `GOT`, `MAL` and the webshop `ONLINE`; mobility dealers `STO`, `GOT`, `MAL`, `UME` (the truck centre in Södertälje is `STO`); telecom customers by segment `consumer` / `business`.

## Tables

### Retail and Commerce (`retail/`)

| table | rows (clean) | grain | columns |
|---|---|---|---|
| `brands` | 9 (9) | brand | `brand_id`, `brand_name`, `category` (electronics / fashion / beauty), `country_of_origin` (ISO alpha-2) |
| `products` | 29 (29) | product | `product_id`, `sku`, `product_name`, `brand_id`, `category`, `subcategory` (phone, laptop, tablet, jeans, jacket, sweatshirt, office_wear, perfume), `list_price_sek`, `unit_cost_sek` (purchase cost - **confidential**), `launch_date` |
| `stores` | 6 (6) | store or webshop | `store_id`, `store_name`, `city`, `region_code`, `channel` (store / online), `opened_date` |
| `customers` | 37 (36) | loyalty customer | `customer_id`, `first_name`, `last_name`, `email`, `phone` (**PII**), `city`, `loyalty_tier` (none / silver / gold), `signup_date` |
| `orders` | 40 (40) | order | `order_id`, `order_date`, `customer_id`, `store_id`, `payment_method` (card, swish, klarna, invoice - the last two online only), `order_status` (completed / cancelled) |
| `order_lines` | 49 (48) | order line | `order_line_id`, `order_id`, `product_id`, `quantity`, `unit_price_sek`, `discount_sek` (line total) |
| `returns` | 10 (10) | returned order line | `return_id`, `order_line_id`, `return_date`, `quantity`, `reason` (wrong_size, changed_mind, defect, damaged), `refund_sek` |

### Mobility and Automotive (`mobility/`)

| table | rows (clean) | grain | columns |
|---|---|---|---|
| `vehicle_models` | 16 (16) | model | `model_id`, `brand`, `model_name`, `vehicle_type` (car / van / truck), `body_type`, `powertrain` (ev, hybrid, petrol, diesel), `model_year`, `list_price_sek` |
| `dealers` | 6 (6) | dealer | `dealer_id`, `dealer_name`, `city`, `region_code`, `has_workshop` |
| `customers` | 31 (30) | customer | `customer_id`, `customer_type` (private / fleet), `customer_name`, `email`, `phone` (**PII**), `city` |
| `vehicle_sales` | 39 (38) | sold vehicle | `sale_id`, `sale_date`, `dealer_id`, `customer_id`, `model_id`, `vin` (**sensitive**), `sale_price_sek` (list price), `discount_sek`, `financing` (cash, loan, lease) |
| `service_visits` | 44 (44) | workshop visit | `visit_id`, `visit_date`, `dealer_id`, `customer_id`, `model_id`, `vin`, `service_type` (annual_service, tyre_change, brake_service, battery_check, software_update, warranty_repair), `labour_hours`, `labour_cost_sek`, `parts_cost_sek`, `billed_amount_sek` (0 for warranty work), `warranty`, `mileage_km` |

Service visits cover vehicles sold in 2026 (always after the sale date, at low mileage) and vehicles bought before 2026. EVs get a battery check instead of an annual service. Trucks are sold and serviced only by the truck centre (`D06`).

### Telecommunications and Media (`telecom/`)

| table | rows (clean) | grain | columns |
|---|---|---|---|
| `plans` | 12 (12) | price plan | `plan_id`, `plan_name`, `plan_type` (mobile, broadband, tv_streaming, bundle), `segment`, `monthly_fee_sek`, `data_allowance_gb` (empty = unlimited), `included_streaming` (`; `-separated add-ons) |
| `customers` | 20 (20) | customer | `customer_id`, `customer_segment` (consumer / business), `customer_name`, `email`, `phone` (**PII**, MSISDN), `city`, `signup_date` |
| `subscriptions` | 24 (24) | subscription | `subscription_id`, `customer_id`, `plan_id`, `start_date`, `end_date` (empty = running), `status` (active / cancelled), `sales_channel` (online, store, telesales) |
| `invoices` | 47 (46) | invoice = subscription x billing month | `invoice_id`, `subscription_id`, `billing_month` (first day of month), `invoice_date`, `due_date` (+30 days), `amount_excl_vat_sek`, `vat_sek` (25 %), `payment_status` (paid, open, overdue) |
| `usage` | 46 (46) | subscription x usage month | `usage_id`, `subscription_id`, `usage_month` (first day of month), `data_gb`, `voice_minutes`, `sms_count`, `streaming_hours` |

Two subscriptions were cancelled on 2026-05-31, so they have a May invoice and May usage but nothing for June. June invoices are not yet due: `open`, never `overdue`.

## Business definitions

The metric views implement exactly these definitions, and `2026-10-27-expected-answers.json` is computed with them.

| measure | definition |
|---|---|
| Net revenue (retail) | `quantity * unit_price_sek - discount_sek` over lines of **completed** orders (cancelled orders excluded), SEK excl. VAT |
| Gross margin % | (net revenue - `quantity * unit_cost_sek`) / net revenue |
| Average order value | net revenue / distinct completed orders |
| Return rate % | returned units / units sold; refund amount = sum of `refund_sek` |
| Vehicle revenue | `sale_price_sek - discount_sek`; average sale price = vehicle revenue / units sold |
| EV share % | vehicles with `powertrain = 'ev'` / vehicles sold |
| Service revenue | sum of `billed_amount_sek` (warranty work is billed to the manufacturer, 0 to the customer); warranty share = warranty visits / visits |
| Billed revenue (telecom) | sum of `amount_excl_vat_sek` |
| ARPU | billed revenue / distinct billed subscriptions in the month |
| Overdue amount, paid share | sum of `amount_excl_vat_sek` with status `overdue`; paid invoices / invoices |

## Deliberate data-quality issues

Silver repairs every issue exactly, so silver row counts = `clean_rows` in the manifest and gold = the expected answers.

| domain | table | issue | rows | silver handling |
|---|---|---|---|---|
| retail | `stores` | region code in lower case with a leading space (`" got"`) | 1 | trim + upper case |
| retail | `customers` | loyalty tier with whitespace / upper case (`" Gold"`, `"SILVER"`) | 2 | trim + lower case |
| retail | `customers` | exact duplicate row | 1 | one row per `customer_id` |
| retail | `orders` | order date as `dd/MM/yyyy` | 2 | parse both date formats |
| retail | `order_lines` | row without `order_line_id` (legacy feed) | 1 | expectation drops the row |
| mobility | `dealers` | region code in lower case with a trailing space (`"got "`) | 1 | trim + upper case |
| mobility | `customers` | exact duplicate row | 1 | one row per `customer_id` |
| mobility | `vehicle_sales` | row without `sale_id` | 1 | expectation drops the row |
| mobility | `service_visits` | warranty flag as `Y` / `N` | 3 | map `Y`/`N`, `true`/`false` to BOOLEAN |
| telecom | `customers` | segment with upper case and a trailing space (`"Business "`) | 1 | trim + lower case |
| telecom | `invoices` | exact duplicate row | 1 | one row per `invoice_id` |
| telecom | `usage` | usage month as `dd/MM/yyyy` | 2 | parse both date formats |
