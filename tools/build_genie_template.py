#!/usr/bin/env python3
"""Build the bootcamp's Genie Agent template ``bootcamp/genie/fjallmark_business_analyst.json``.

The template is a serialized Genie space (version 2) for the agent "Fjällmark Business Analyst" over the
three bootcamp domains (consumer, finance, manufacturing) of the Lakehouse Industry Data Model - Consumer
Goods v2 MVM (Copyright Databricks, Inc.; Databricks license - see tools/model/LICENSE.md and
tools/model/NOTICE.md). Every table and column name comes from that model; the agent content (descriptions,
instructions, example SQL, benchmarks) is written for the fictional company Fjällmark Consumer Goods AB.

Single sources reused here (not copied by hand):
  * the text instruction = the ```text block of bootcamp/context/genie/agent_instructions.md (business rules,
    owned by the context stream) + a short "HOW TO QUERY" block written below;
  * the curated metric views bootcamp/metric_views/curated/*.sql (measure / dimension names).

The template uses the placeholder ``__CATALOG__``; notebook bootcamp/notebooks/04_genie_agent.py replaces it
with the participant's catalog and creates or updates the agent (REST /api/2.0/genie/spaces).

IDs are deterministic (md5 of a stable key), so re-building keeps question / instruction IDs stable and
benchmark history comparable. The output is deterministic (same input -> same bytes).

Usage (from the repository root):

  python3 -I tools/build_genie_template.py            # (re)write the template
  python3 -I tools/build_genie_template.py --check    # exit 1 if the template is missing or stale
  python3 -I tools/build_genie_template.py --run-sql --catalog zz_cpg_bc_e2e --warehouse <id> --profile <p>
        # live check: every data source exists, every example / benchmark SQL and every SQL snippet
        # (wrapped in a test query) runs on the catalog; prints row counts and the first row
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "bootcamp", "genie", "fjallmark_business_analyst.json")
INSTRUCTIONS_MD = os.path.join(ROOT, "bootcamp", "context", "genie", "agent_instructions.md")
SCRIPT = "tools/build_genie_template.py"
C = "__CATALOG__"

TITLE = "Fjällmark Business Analyst"
DESCRIPTION = (
    "Business analyst for Fjällmark Consumer Goods AB (fictional Nordic consumer-goods group: Björkö Pantry, "
    "Kallkälla, Mjuk Care). Answers questions on official Net Revenue, COGS and gross margin (general ledger, EUR), "
    "receivables and DSO, webshop (DTC) sales, shoppers and loyalty tiers, and plant performance (OEE, yield, "
    "scrap, downtime, cost variance) from the consumer, finance and manufacturing gold tables and governed "
    "metric views of the Lakehouse Industry Data Model - Consumer Goods v2. Data: 2024-01 to 2026-09."
)


def nid(key):
    """Deterministic 32-hex id."""
    return hashlib.md5(f"fjallmark-genie:{key}".encode("utf-8")).hexdigest()


def lines(text):
    """Split SQL / text into the array-of-strings form of serialized_space (each line keeps its newline)."""
    text = text.strip("\n")
    parts = text.split("\n")
    return [p + "\n" for p in parts[:-1]] + [parts[-1]]


# ---------------------------------------------------------------------------------------------------------
# 1. Data sources (<= 50 combined; see bootcamp/genie/README.md for the inclusion / exclusion rationale)
# ---------------------------------------------------------------------------------------------------------
def cc(name, synonyms=None, description=None, match=False, exclude=False):
    d = {"column_name": name}
    if description:
        d["description"] = [description]
    if synonyms:
        d["synonyms"] = list(synonyms)
    if match:
        d["enable_format_assistance"] = True
        d["enable_entity_matching"] = True
    if exclude:
        d["exclude"] = True
    return d


def hide(*names):
    return [cc(n, exclude=True) for n in names]


# Personal data never needed for analysis: hidden from the agent (also masked by notebook 03).
PII_SHOPPER = ("given_name", "family_name", "display_name", "primary_email", "primary_phone", "birth_date",
               "postal_code", "registration_source_url", "source_system_consumer_ref")
PII_ADDRESS = ("line_1", "line_2", "line_3", "postal_code", "plus4_code", "standardized_address", "latitude",
               "longitude", "carrier_route", "census_tract", "dma_code", "dpv_confirmation", "geocoding_accuracy")

METRIC_VIEWS = [
    {
        "id": "consumer.dtc_sales_metrics",
        "description": "CURATED. Webshop (DTC) sales KPIs at order-line grain: GMV, DTC net sales, discounts, orders, "
                       "units, AOV, return rate, active shoppers, order frequency, merchandise margin by month, market, "
                       "currency, brand, product, loyalty tier, CLTV segment. Cancelled orders excluded. *_local = order "
                       "currency (group by currency_code), *_eur = converted. Operational webshop view, NOT finance revenue.",
        "column_configs": [
            cc("brand", ["brand name"], match=True),
            cc("cltv_segment", ["customer segment", "value segment"], match=True),
            cc("company_code", ["legal entity", "entity"], match=True),
            cc("currency_code", ["currency"], match=True),
            cc("customer_type", match=True),
            cc("dtc_net_sales_local", description="LOCAL currency - only per currency_code. For a total over several "
               "markets or the whole webshop use dtc_net_sales_eur."),
            cc("gmv_local", description="LOCAL currency - only per currency_code. For a total over several markets or "
               "the whole webshop ('total GMV', 'all markets') use gmv_eur."),
            cc("line_returned", match=True),
            cc("loyalty_tier", ["tier", "membership tier", "member status"], match=True),
            cc("market", ["country", "ship-to country", "webshop market"], match=True),
            cc("order_status", match=True),
            cc("order_type", match=True),
            cc("product_category", ["category"], match=True),
            cc("product_name", ["product", "sku", "item"], match=True),
            cc("return_reason", match=True),
            cc("sales_channel", ["webshop channel", "touchpoint"], match=True),
        ],
    },
    {
        "id": "finance.net_revenue_metrics",
        "description": "CURATED. The OFFICIAL Net Revenue, COGS and gross margin (EUR, posted general-ledger lines, after "
                       "returns and trade discounts) by fiscal year / period / quarter, company code, channel (DTC, B2B), "
                       "brand, profit centre and GL account. Use it for every revenue, sales, turnover or margin question.",
        "column_configs": [
            cc("account_group", match=True),
            cc("brand", ["brand name"], match=True),
            cc("channel", ["sales channel", "DTC or B2B"], match=True),
            cc("company_code", ["legal entity", "entity"], match=True),
            cc("company_name", match=True),
            cc("gl_account_name", ["account name"], match=True),
            cc("profit_center", ["profit centre"], match=True),
        ],
    },
    {
        "id": "finance.receivables_metrics",
        "description": "CURATED. Accounts receivable snapshot as of 2026-09-30 at invoice grain: open, overdue and disputed "
                       "AR (local and EUR), overdue share, aging bucket, billing, collection rate, DSO and days past due by "
                       "company code, currency, customer (trade_account_id), invoice status. Slice DSO by company code, "
                       "customer or currency only.",
        "column_configs": [
            cc("aging_bucket", ["aging", "days overdue bucket"], match=True),
            cc("company_code", ["legal entity", "entity"], match=True),
            cc("company_name", match=True),
            cc("currency_code", ["currency"], match=True),
            cc("dispute_reason", match=True),
            cc("dispute_status", match=True),
            cc("invoice_status", match=True),
            cc("is_overdue", ["overdue"], match=True),
        ],
    },
    {
        "id": "manufacturing.production_performance_metrics",
        "description": "CURATED. Plant performance at production-order grain (finished orders, period = finish month): OEE "
                       "(simple, volume-weighted, target), yield %, scrap rate %, on-time completion %, late orders, "
                       "downtime, changeovers, planned vs actual cost and cost variance (plant currency and EUR) by plant, "
                       "production line, month / quarter / year, order status and material.",
        "column_configs": [
            cc("currency_code", ["plant currency"], match=True),
            cc("line_code", match=True),
            cc("line_name", match=True),
            cc("order_status", match=True),
            cc("plant", ["plant code", "site", "factory"], match=True),
            cc("plant_name", ["plant", "factory", "site name"], match=True),
            cc("production_line", ["line", "line tag", "asset tag"], match=True),
        ],
    },
    {
        "id": "consumer.loyalty_account_metrics",
        "description": "Industry model metric view: Fjällmark Friends loyalty accounts - counts, points balances, lifetime "
                       "points earned / redeemed / expired, redemption rate by account status, CLTV segment, country, "
                       "enrollment channel and year.",
        "column_configs": [
            cc("account_status", match=True),
            cc("cltv_segment", match=True),
            cc("country_code", ["country"], match=True),
            cc("enrollment_channel", match=True),
        ],
    },
    {
        "id": "consumer.shopper_metrics",
        "description": "Industry model metric view: number of registered shoppers and opt-in / consent rates by acquisition "
                       "channel, lifecycle status, CLTV segment, consumer type, country and acquisition year.",
        "column_configs": [
            cc("acquisition_channel", match=True),
            cc("cltv_segment", ["customer segment"], match=True),
            cc("country_code", ["country"], match=True),
            cc("lifecycle_status", match=True),
        ],
    },
    {
        "id": "consumer.consent_record_metrics",
        "description": "Industry model metric view: GDPR consent records by consent type, status, legal basis, jurisdiction, "
                       "country and capture month (double opt-in, profiling and third-party sharing rates).",
        "column_configs": [
            cc("consent_status", match=True),
            cc("consent_type", match=True),
            cc("country_code", ["country"], match=True),
            cc("legal_basis", match=True),
        ],
    },
    {
        "id": "manufacturing.yield_record_metrics",
        "description": "Industry model metric view: yield records - input / output / scrap / rework quantities, overall yield "
                       "and scrap rate by yield loss reason code, shift and measurement month / quarter / year (no plant or "
                       "line dimension: use manufacturing.yield_record for those).",
        "column_configs": [
            cc("shift_code", ["shift"], match=True),
            cc("yield_loss_reason_code", ["loss reason", "yield loss reason"], match=True),
        ],
    },
    {
        "id": "manufacturing.batch_record_metrics",
        "description": "Industry model metric view: manufactured batches - quantities, quality release rate, GMP deviation "
                       "rate, rework, cost by batch status and manufacturing month / quarter / year.",
        "column_configs": [cc("batch_status", match=True)],
    },
    {
        "id": "manufacturing.equipment_metrics",
        "description": "Industry model metric view: plant equipment - counts, acquisition and maintenance cost, MTBF, MTTR, "
                       "actual vs target OEE by equipment type, manufacturer, hazard class and installation year.",
        "column_configs": [cc("equipment_type", match=True), cc("manufacturer", match=True)],
    },
]

TABLES = [
    # ---------------- consumer ----------------
    {
        "id": "consumer.shopper",
        "description": "Registered webshop shoppers (one row per shopper): country, CLTV segment, lifecycle status, current "
                       "loyalty tier, consent flags. Personal data columns are hidden and masked.",
        "column_configs": [
            cc("cltv_segment", ["customer segment", "value segment"], match=True),
            cc("country_code", ["country", "market"], "ISO alpha-3 country of the shopper (SWE, NOR, DNK, FIN, DEU, NLD).", match=True),
            cc("last_purchase_date", ["last order date"]),
            cc("lifecycle_status", match=True),
            cc("loyalty_tier_id", description="Current Fjällmark Friends tier (join consumer.loyalty_tier); NULL = non-member."),
            cc("preferred_currency", match=True),
        ] + hide(*PII_SHOPPER, "loyalty_program_id", "age_verified", "ccpa_subject", "gdpr_subject", "consent_timestamp",
                 "created_timestamp", "updated_timestamp", "preferred_store_banner"),
    },
    {
        "id": "consumer.dtc_order",
        "description": "Webshop (DTC) order headers, one row per order, amounts in the order's LOCAL currency (currency_code). "
                       "order_total_amount includes VAT and shipping and is NOT revenue.",
        "column_configs": [
            cc("channel_code", ["webshop channel", "touchpoint"], match=True),
            cc("currency_code", ["currency"], match=True),
            cc("order_date", ["purchase date"]),
            cc("order_status", ["status"], "Order status; exclude 'cancelled' from sales. 'returned' = fully returned.", match=True),
            cc("order_total_amount", ["gross order value", "order value incl. VAT"],
               "Subtotal - discount + shipping + VAT, local currency, before returns. Not revenue."),
            cc("payment_status", match=True),
            cc("return_reason_code", match=True),
            cc("subtotal_amount", ["merchandise value"], "Unit price x quantity, excl. VAT and shipping, before discounts (local currency)."),
        ] + hide("order_id", "primary_dtc_procurement_purchase_order_id", "trade_account_id", "outbound_order_id",
                 "created_timestamp", "updated_timestamp", "fulfillment_ref", "payment_transaction_ref",
                 "source_system_order_ref", "tracking_number", "ship_to_name", "ip_country_code", "sku_id"),
    },
    {
        "id": "consumer.dtc_order_line",
        "description": "Webshop order lines (one row per product on an order) with product name, brand, category, quantities, "
                       "net amount, standard cost and return flag; local currency (currency_code).",
        "column_configs": [
            cc("brand_code", ["brand"], "BJORKO = Björkö Pantry, KALLKALLA = Kallkälla, MJUKCARE = Mjuk Care.", match=True),
            cc("currency_code", ["currency"], match=True),
            cc("is_returned", ["returned", "return flag"]),
            cc("line_net_amount", ["net sales", "net merchandise value"], "line_subtotal - line_discount_amount, excl. VAT, local currency."),
            cc("product_category_code", ["category", "product category"], match=True),
            cc("product_name", ["product", "sku", "item", "article"], match=True),
            cc("return_reason_code", match=True),
        ] + hide("outbound_order_line_id", "created_timestamp", "updated_timestamp", "regulatory_hold_flag", "unit_of_measure",
                 "supply_atp_record_id", "event_id", "distribution_facility_id", "shipment_id"),
    },
    {
        "id": "consumer.loyalty_account",
        "description": "Fjällmark Friends loyalty accounts (one per member): status, tier, CLTV segment, points balance, "
                       "lifetime points, enrollment.",
        "column_configs": [
            cc("account_status", match=True),
            cc("cltv_segment", match=True),
            cc("country_code", ["country"], match=True),
            cc("points_balance", ["points", "loyalty points"]),
        ] + hide("loyalty_program_id", "pos_transaction_id", "account_type", "consent_timestamp", "created_timestamp",
                 "updated_timestamp", "points_currency_code", "points_expiry_policy", "source_system_code",
                 "retail_store_id", "account_number"),
    },
    {
        "id": "consumer.loyalty_tier",
        "description": "The four Fjällmark Friends tiers (Bronze, Silver, Gold, Platinum) with rank, member discount and points rules.",
        "column_configs": [
            cc("tier_name", ["tier", "loyalty level", "membership tier"], match=True),
            cc("tier_rank", description="1 = Bronze ... 4 = Platinum (sort key)."),
        ] + hide("loyalty_program_id", "created_timestamp", "updated_timestamp", "effective_from", "effective_until",
                 "expiration_policy", "loyalty_tier_status", "tier_type", "required_spend_usd", "reward_points_per_dollar",
                 "promotional_code"),
    },
    {
        "id": "consumer.address",
        "description": "Shopper addresses; only country_code is needed for analysis (webshop market = ship-to country of "
                       "dtc_order.ship_to_address_id). Street, postal code and coordinates are hidden.",
        "column_configs": [
            cc("address_type", match=True),
            cc("country_code", ["country", "market", "ship-to country"], match=True),
        ] + hide(*PII_ADDRESS, "consent_captured", "created_timestamp", "updated_timestamp", "data_residency_region",
                 "format_type", "source_system_code", "source_system_name", "validation_provider", "validation_timestamp",
                 "validation_status", "deliverability_score", "residential_indicator", "timezone", "city",
                 "state_province", "source"),
    },
    {
        "id": "consumer.subscription",
        "description": "Webshop subscriptions (granola box, oat drink crates, Mjuk Care refills): type, frequency, status, "
                       "price in local currency, start / cancellation dates and reasons.",
        "column_configs": [
            cc("cancellation_reason", match=True),
            cc("frequency", match=True),
            cc("subscription_status", ["status"], match=True),
            cc("subscription_type", match=True),
        ] + hide("loyalty_program_id", "auto_renew_flag", "ccpa_opt_out_flag", "created_timestamp", "updated_timestamp",
                 "discount_rate", "gdpr_consent_flag", "payment_token_reference", "promotion_code", "event_id",
                 "distribution_facility_id"),
    },
    # ---------------- finance ----------------
    {
        "id": "finance.company_code",
        "description": "The six legal entities (company codes) with their local currency: SE01 Sweden SEK (parent), NO01 "
                       "Norway NOK, DK01 Denmark DKK, FI01 Finland EUR, DE01 Germany EUR, PL01 Poland PLN. Group currency EUR.",
        "column_configs": [
            cc("code", ["company code", "legal entity", "entity"], match=True),
            cc("currency_code", ["local currency", "company currency"], match=True),
            cc("name", ["company name", "entity name"], match=True),
        ] + hide("parent_company_code_id", "address_line1", "address_line2", "effective_to", "is_consolidated_entity",
                 "is_public_company", "lifecycle_status", "parent_company_code", "primary_contact_method",
                 "record_audit_created", "record_audit_updated", "email_address", "phone_number", "postal_code",
                 "tax_number", "state_province"),
    },
    {
        "id": "finance.gl_account",
        "description": "Chart of accounts per company code (same numbering everywhere). account_group REVENUE (3000 B2B, "
                       "3010 DTC, 3040 trade discounts, 3050 DTC returns) and COGS (4000 standard cost, 4100 production variances).",
        "column_configs": [
            cc("account_group", ["account type group"], match=True),
            cc("account_name", match=True),
            cc("account_number", ["GL account", "account"], match=True),
        ] + hide("account_status", "blocked_for_posting_flag", "created_by_user", "created_timestamp",
                 "intercompany_clearing_flag", "last_modified_by_user", "last_modified_timestamp", "line_item_display_flag",
                 "posting_allowed_flag", "valid_to_date", "field_status_group", "sort_key"),
    },
    {
        "id": "finance.journal_entry",
        "description": "Journal entry headers: fiscal_year / fiscal_period (= calendar month) of the posting, document type, "
                       "posting status. Do not use its exchange_rate.",
        "column_configs": [
            cc("document_type", match=True),
            cc("exchange_rate", description="Header document rate (mostly NULL). Never use it for EUR conversion."),
            cc("fiscal_period", ["period", "month"], "Fiscal period 1-12 = calendar month."),
            cc("fiscal_year", ["year"], "Fiscal year = calendar year."),
            cc("posting_status", match=True),
        ] + hide("product_category_id", "approval_timestamp", "batch_input_session", "clearing_date",
                 "clearing_document_number", "controlling_area", "created_timestamp", "exchange_rate_type", "ledger_group",
                 "modified_timestamp", "reversal_indicator", "reversal_reason_code", "reversed_document_number",
                 "source_system_code", "transaction_code"),
    },
    {
        "id": "finance.journal_entry_line",
        "description": "General-ledger lines (one row per debit / credit line). amount_group_currency = EUR (safe to add across "
                       "company codes); amount_company_code_currency = local. exchange_rate = EUR per unit of local currency.",
        "column_configs": [
            cc("amount_company_code_currency", ["local amount"], "Amount in the company code's local currency - never add across company codes."),
            cc("amount_group_currency", ["EUR amount", "group currency amount"], "Amount in EUR (group currency)."),
            cc("company_code_currency_code", ["local currency"], match=True),
            cc("debit_credit_indicator", description="'C' credit, 'D' debit. Revenue = credit minus debit.", match=True),
            cc("exchange_rate", ["FX rate"], "EUR per unit of the company-code currency for the posting month."),
            cc("plant_code", description="Plant of production postings (LUND, NKPG, TMPR, POZN).", match=True),
        ] + hide("assignment_field", "clearing_date", "clearing_document_number", "material_number", "quantity",
                 "reversal_indicator", "reversed_document_number", "special_gl_indicator", "storage_location_code",
                 "unit_of_measure", "wbs_element_code", "internal_order_number", "posting_key", "value_date"),
    },
    {
        "id": "finance.profit_center",
        "description": "Profit centres: brand centres (code BJORKO, KALLKALLA, MJUKCARE; name = brand name), brand x channel "
                       "centres (channel_code dtc / retail) and plant centres. brand_code links GL lines to brands.",
        "column_configs": [
            cc("brand_code", ["brand"], match=True),
            cc("channel_code", match=True),
            cc("code", ["profit center code"], match=True),
            cc("name", ["profit centre", "brand name"], match=True),
            cc("profit_center_type", match=True),
        ] + hide("address_line_1", "address_line_2", "controlling_area_code", "created_timestamp", "fax_number",
                 "last_modified_by_user", "last_modified_timestamp", "lock_indicator", "planning_enabled_flag",
                 "profit_center_status", "sox_control_flag", "state_province_code", "valid_to_date", "email_address",
                 "phone_number", "postal_code", "responsible_person_email", "responsible_person_name"),
    },
    {
        "id": "finance.ar_invoice",
        "description": "Customer invoices (accounts receivable) incl. VAT, local currency (currency_code); outstanding_balance "
                       "is the open amount as of 2026-09-30; dispute_flag / dispute_reason for disputed invoices.",
        "column_configs": [
            cc("currency_code", ["currency"], match=True),
            cc("dispute_reason", match=True),
            cc("invoice_status", ["status"], match=True),
            cc("outstanding_balance", ["open amount", "open AR"], "Open amount at 2026-09-30, local currency incl. VAT."),
        ] + hide("shopper_id", "billing_document_type", "clearing_date", "clearing_reference", "created_timestamp",
                 "modified_by_user", "modified_timestamp", "write_off_reason_code", "dso_aging_bucket"),
    },
    {
        "id": "finance.ap_invoice",
        "description": "Supplier invoices (accounts payable), local currency (currency_code): category, status, amounts, due "
                       "and payment dates.",
        "column_configs": [
            cc("currency_code", ["currency"], match=True),
            cc("invoice_category", ["spend category"], match=True),
            cc("invoice_status", ["status"], match=True),
        ] + hide("clearing_document_number", "created_by_user", "created_timestamp", "modified_by_user",
                 "modified_timestamp", "payment_block_code", "tax_code", "withholding_tax_amount",
                 "vendor_bank_account_code", "goods_receipt_id", "supplier_invoice_id"),
    },
    {
        "id": "finance.standard_cost",
        "description": "Cost estimates per product and plant (local currency): standard, actual and planned costing versions; "
                       "cost_estimate_number = CE-<sku code>-<year>-<STA|ACT|PLA>.",
        "column_configs": [
            cc("costing_type", match=True),
            cc("currency_code", ["currency"], match=True),
            cc("release_status", match=True),
        ] + hide("approval_status", "approved_by", "approved_timestamp", "bom_usage", "cost_estimate_created_by",
                 "cost_estimate_created_timestamp", "cost_estimate_modified_by", "cost_estimate_modified_timestamp",
                 "costing_lot_size", "costing_lot_size_uom", "costing_sheet", "routing_usage", "valuation_variant"),
    },
    # ---------------- manufacturing ----------------
    {
        "id": "manufacturing.manufacturing_facility",
        "description": "The four plants: SE-LUN Lund Food Plant, SE-NKP Norrköping Beverage Plant, FI-TMP Tampere Oat Drink "
                       "Plant (commissioned April 2025), PL-POZ Poznań Personal Care Plant.",
        "column_configs": [
            cc("erp_plant_code", ["plant", "plant code", "site"], match=True),
            cc("facility_name", ["plant name", "factory", "site name"], match=True),
            cc("plant_code", description="Short plant code used on GL lines and production orders (LUND, NKPG, TMPR, POZN).", match=True),
        ] + hide("address_line_1", "address_line_2", "created_timestamp", "epa_site_number", "fda_establishment_number",
                 "gmp_certified", "iso_22716_compliance_tier", "iso_9001_certified", "last_modified_timestamp",
                 "mes_system_integrated", "operational_status", "osha_establishment_number", "ownership_type",
                 "shift_pattern", "email_address", "phone_number", "postal_code", "latitude", "longitude"),
    },
    {
        "id": "manufacturing.production_line",
        "description": "The 16 production lines; mes_asset_tag is the line name people use (e.g. PL-POZ-L2), line_code the "
                       "short code (e.g. POZNL2); nominal_oee_target_percent = OEE target.",
        "column_configs": [
            cc("line_code", ["line code"], match=True),
            cc("line_name", match=True),
            cc("line_type", match=True),
            cc("mes_asset_tag", ["line", "production line", "line tag"], match=True),
            cc("notes", description="Free-text maintenance notes, e.g. the PL-POZ-L2 nozzle repair in April 2026."),
        ] + hide("created_timestamp", "depreciation_method", "last_modified_timestamp", "modified_by_user",
                 "operational_status", "record_source_system", "scada_integration_enabled", "shift_pattern",
                 "temperature_range_celsius", "useful_life_years", "cleaning_validation_protocol", "plc_system_type"),
    },
    {
        "id": "manufacturing.production_order",
        "description": "Production orders (one row per order) with quantities, yield, scrap, OEE (0-100), downtime, planned vs "
                       "actual cost in plant currency, scheduled vs actual finish. Completed = CNF, DLV, TECO, CLSD.",
        "column_configs": [
            cc("actual_finish_timestamp", ["finish date", "completion date"], "Period of a production order = month of this timestamp."),
            cc("currency_code", ["plant currency"], match=True),
            cc("oee_percentage", ["OEE"], "OEE of the order in percent (0-100)."),
            cc("order_status", ["status"], match=True),
            cc("plant_code", ["plant"], match=True),
            cc("yield_percentage", ["yield"], "Yield in percent (0-100)."),
        ] + hide("created_timestamp", "gmp_compliance_flag", "last_modified_timestamp", "production_version",
                 "quality_inspection_required", "released_by", "released_timestamp", "settlement_rule", "unit_of_measure",
                 "created_by", "production_supervisor", "inspection_lot_number", "cost_object", "sales_order_id",
                 "trade_account_id", "inspection_plan_id"),
    },
    {
        "id": "manufacturing.yield_record",
        "description": "Yield measurements per production order (input, output, scrap, rework, actual yield %) with the yield "
                       "loss reason (e.g. EQMALF equipment malfunction, RAMPUP Tampere start-up losses).",
        "column_configs": [
            cc("actual_yield_percentage", ["yield"], "Measured yield in percent (0-100)."),
            cc("measurement_timestamp", ["measurement date"]),
            cc("shift_code", ["shift"], match=True),
            cc("yield_loss_reason_code", ["loss reason", "yield loss reason"], match=True),
            cc("yield_loss_reason_description", match=True),
        ] + hide("created_timestamp", "erp_document_number", "gmp_compliance_flag", "last_modified_timestamp",
                 "mes_transaction_reference", "routing_operation_number", "unit_of_measure", "quality_inspection_lot_number",
                 "comments"),
    },
    {
        "id": "manufacturing.batch_record",
        "description": "Manufactured batches (one per production order): batch status, quality release, GMP deviations, "
                       "actual vs planned batch size, scrap, rework, downtime.",
        "column_configs": [
            cc("batch_status", match=True),
        ] + hide("bom_version", "created_timestamp", "last_modified_timestamp", "lot_genealogy_complete_flag", "recall_flag",
                 "recall_initiated_date", "record_locked_flag", "routing_version", "unit_of_measure",
                 "veeva_vault_document_reference", "electronic_signature_count", "goods_receipt_id", "formulation_id"),
    },
    {
        "id": "manufacturing.equipment",
        "description": "Plant equipment (fillers, cappers, labelers ...) per line: type, manufacturer, MTBF / MTTR, actual vs "
                       "target OEE, maintenance dates and cost.",
        "column_configs": [
            cc("equipment_type", match=True),
            cc("manufacturer", match=True),
        ] + hide("capacity_units", "compliance_gmp", "department", "depreciation_method", "equipment_status", "voltage",
                 "serial_number", "model_number", "acquisition_purchase_order_id", "asset_tag"),
    },
]

# ---------------------------------------------------------------------------------------------------------
# 2. Text instruction (exactly one item)
# ---------------------------------------------------------------------------------------------------------
HOW_TO_QUERY = """
HOW TO QUERY (agent template, tools/build_genie_template.py)
- Prefer the four curated metric views: finance.net_revenue_metrics (revenue, COGS, margin, production
  variances), consumer.dtc_sales_metrics (webshop GMV, net sales, AOV, returns, active shoppers),
  finance.receivables_metrics (open / overdue / disputed AR, DSO) and manufacturing.production_performance_metrics
  (OEE, yield, scrap, downtime, on-time, cost variance). Query them with MEASURE(<measure>) and GROUP BY ALL;
  filter only on dimensions, never put a measure in WHERE, never SELECT *.
- Return only the columns the question needs: the grouping dimensions plus the requested measures.
- A total "across all markets / company codes / the group" is ONE number in EUR (the *_eur measure, no
  grouping) - never answer it with a per-currency breakdown of *_local measures.
- When the user groups categories ("Gold and Platinum members vs non-members", "food and beverages"), build that
  grouping with a CASE on the dimension and compute the measure per group; do not just list every category.
- Use the gold tables only for row-level detail or attributes the metric views do not have (yield loss reasons
  per line, subscriptions, payables, loyalty accounts, production line notes).
- Industry metric views named <table>_metrics are generic model views; their amounts are NOT currency converted.
- Production lines are named by production_line.mes_asset_tag (e.g. PL-POZ-L2) = production_performance_metrics.production_line;
  plants by manufacturing_facility.erp_plant_code (e.g. FI-TMP) = production_performance_metrics.plant.
"""


def text_instruction():
    md = open(INSTRUCTIONS_MD, encoding="utf-8").read()
    m = re.search(r"^```text\n(.*?)^```", md, re.S | re.M)
    if not m:
        sys.exit(f"no ```text block in {INSTRUCTIONS_MD}")
    body = m.group(1).rstrip("\n") + "\n" + HOW_TO_QUERY.rstrip("\n")
    return lines(body)


# ---------------------------------------------------------------------------------------------------------
# 3. Example SQL (instructive query shapes; benchmarks use different questions / slices)
# ---------------------------------------------------------------------------------------------------------
EXAMPLES = [
    ("ex_nr_by_year",
     "What are net revenue, COGS and gross margin by fiscal year?",
     f"""SELECT fiscal_year,
       MEASURE(net_revenue_eur) AS net_revenue_eur,
       MEASURE(cogs_eur) AS cogs_eur,
       MEASURE(gross_margin_eur) AS gross_margin_eur,
       MEASURE(gross_margin_pct) AS gross_margin_pct
FROM {C}.finance.net_revenue_metrics
GROUP BY ALL
ORDER BY fiscal_year""",
     "Revenue / sales / turnover / margin questions: always the official Net Revenue (posted GL, EUR, after returns and "
     "trade discounts) from finance.net_revenue_metrics."),
    ("ex_nr_by_company_quarter",
     "Net revenue by legal entity for the last closed quarter",
     f"""SELECT company_code, company_name,
       MEASURE(net_revenue_eur) AS net_revenue_eur
FROM {C}.finance.net_revenue_metrics
WHERE fiscal_quarter = '2026-Q3'
GROUP BY ALL
ORDER BY net_revenue_eur DESC""",
     "Revenue by company code / entity / country of the legal entity. The last closed quarter is 2026-Q3 (data ends 2026-09-30)."),
    ("ex_nr_brand_channel",
     "Net revenue and gross margin % by brand and channel in 2025",
     f"""SELECT brand, channel,
       MEASURE(net_revenue_eur) AS net_revenue_eur,
       MEASURE(gross_margin_pct) AS gross_margin_pct
FROM {C}.finance.net_revenue_metrics
WHERE fiscal_year = 2025
  AND channel IN ('DTC', 'B2B')
GROUP BY ALL
ORDER BY brand, channel""",
     "Revenue or margin by brand and / or channel (DTC webshop vs B2B trade customers)."),
    ("ex_dtc_b2b_trend",
     "Monthly DTC and B2B net revenue over the last 12 months",
     f"""SELECT fiscal_month,
       MEASURE(dtc_net_revenue_eur) AS dtc_net_revenue_eur,
       MEASURE(b2b_net_revenue_eur) AS b2b_net_revenue_eur,
       MEASURE(net_revenue_eur) AS net_revenue_eur
FROM {C}.finance.net_revenue_metrics
WHERE fiscal_month BETWEEN DATE'2025-10-01' AND DATE'2026-09-01'
GROUP BY ALL
ORDER BY fiscal_month""",
     "Monthly trends; 'last 12 months' = October 2025 to September 2026."),
    ("ex_webshop_vs_finance_se01",
     "Why is the webshop order total higher than finance DTC revenue for Sweden in June 2026?",
     f"""WITH webshop AS (
  SELECT SUM(o.order_total_amount) AS order_total_sek
  FROM {C}.consumer.dtc_order o
  JOIN {C}.finance.company_code cc ON cc.company_code_id = o.company_code_id
  WHERE cc.code = 'SE01'
    AND lower(o.order_status) <> 'cancelled'
    AND o.order_date >= DATE'2026-06-01' AND o.order_date < DATE'2026-07-01'
),
finance_dtc AS (
  SELECT SUM(CASE WHEN jel.debit_credit_indicator = 'C' THEN jel.amount_company_code_currency
                  ELSE -jel.amount_company_code_currency END) AS dtc_net_revenue_sek
  FROM {C}.finance.journal_entry_line jel
  JOIN {C}.finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
  JOIN {C}.finance.gl_account ga ON ga.gl_account_id = jel.gl_account_id
  JOIN {C}.finance.company_code cc ON cc.company_code_id = jel.company_code_id
  WHERE cc.code = 'SE01'
    AND ga.account_number IN ('3010', '3050')
    AND je.posting_status = 'posted'
    AND je.fiscal_year = 2026 AND je.fiscal_period = 6
)
SELECT ROUND(w.order_total_sek, 0) AS webshop_order_total_sek_incl_vat,
       ROUND(f.dtc_net_revenue_sek, 0) AS finance_dtc_net_revenue_sek,
       ROUND(100 * (1 - f.dtc_net_revenue_sek / w.order_total_sek), 1) AS finance_below_webshop_pct
FROM webshop w CROSS JOIN finance_dtc f""",
     "Revenue-definition conflict: the webshop order total includes VAT and shipping and is before returns; finance DTC "
     "revenue (accounts 3010 + 3050) is net. Compare in ONE currency (here SEK for SE01)."),
    ("ex_webshop_by_market_local",
     "Webshop GMV, net sales and orders by market in local currency for 2026",
     f"""SELECT market, currency_code,
       MEASURE(gmv_local) AS gmv_local,
       MEASURE(dtc_net_sales_local) AS dtc_net_sales_local,
       MEASURE(order_count) AS orders
FROM {C}.consumer.dtc_sales_metrics
WHERE order_year = 2026
GROUP BY ALL
ORDER BY market""",
     "Webshop sales per market: local-currency measures ALWAYS together with currency_code. Use *_eur measures for totals "
     "across markets."),
    ("ex_tier_aov_frequency",
     "Average order value and order frequency by loyalty tier in the last 12 months",
     f"""SELECT loyalty_tier, loyalty_tier_rank,
       MEASURE(avg_order_value_eur) AS aov_eur,
       MEASURE(orders_per_active_shopper) AS orders_per_shopper,
       MEASURE(active_shoppers) AS active_shoppers
FROM {C}.consumer.dtc_sales_metrics
WHERE order_date BETWEEN DATE'2025-10-01' AND DATE'2026-09-30'
GROUP BY ALL
ORDER BY loyalty_tier_rank""",
     "Loyalty tier comparisons (AOV, frequency, active shoppers). Non-members are the tier 'Non-member'."),
    ("ex_tier_groups_frequency",
     "Order frequency of Bronze and Silver members versus Gold and Platinum members in 2025",
     f"""SELECT CASE WHEN loyalty_tier IN ('Gold', 'Platinum') THEN 'Gold/Platinum'
            WHEN loyalty_tier IN ('Bronze', 'Silver') THEN 'Bronze/Silver' END AS member_group,
       MEASURE(orders_per_active_shopper) AS orders_per_shopper,
       MEASURE(active_shoppers) AS active_shoppers
FROM {C}.consumer.dtc_sales_metrics
WHERE order_year = 2025
  AND loyalty_tier IN ('Bronze', 'Silver', 'Gold', 'Platinum')
GROUP BY ALL
ORDER BY member_group""",
     "Comparisons between GROUPS of tiers / categories: CASE on the dimension in SELECT, GROUP BY ALL, filter the "
     "categories in WHERE; the measure is recomputed per group (never average the per-tier values)."),
    ("ex_return_rate_brand",
     "Webshop return rate and returned value by brand",
     f"""SELECT brand,
       MEASURE(return_rate_pct) AS return_rate_pct,
       MEASURE(returned_net_sales_eur) AS returned_net_sales_eur
FROM {C}.consumer.dtc_sales_metrics
GROUP BY ALL
ORDER BY return_rate_pct DESC""",
     "Return rate = returned line net value / line net value (value-based, percent). line_return_rate_pct is the line-count variant."),
    ("ex_top_products",
     "Top 10 webshop products by units in 2026",
     f"""SELECT product_name, brand,
       MEASURE(units_ordered) AS units,
       MEASURE(dtc_net_sales_eur) AS dtc_net_sales_eur
FROM {C}.consumer.dtc_sales_metrics
WHERE order_year = 2026
GROUP BY ALL
ORDER BY units DESC
LIMIT 10""",
     "Ranking of products / categories / brands in the webshop."),
    ("ex_dso_by_company",
     "DSO, open and overdue receivables by company code",
     f"""SELECT company_code,
       MEASURE(dso_days) AS dso_days,
       MEASURE(open_ar_eur) AS open_ar_eur,
       MEASURE(overdue_ar_eur) AS overdue_ar_eur,
       MEASURE(overdue_share_pct) AS overdue_share_pct
FROM {C}.finance.receivables_metrics
GROUP BY ALL
ORDER BY dso_days DESC""",
     "Receivables, overdue and DSO per entity (snapshot 2026-09-30, EUR). Do not slice DSO by month."),
    ("ex_aging_local",
     "Overdue receivables of NO01 by aging bucket",
     f"""SELECT aging_bucket, currency_code,
       MEASURE(overdue_invoice_count) AS overdue_invoices,
       MEASURE(overdue_ar_local) AS overdue_ar_local
FROM {C}.finance.receivables_metrics
WHERE company_code = 'NO01'
  AND is_overdue = 'Overdue'
GROUP BY ALL
ORDER BY aging_bucket""",
     "Aging analysis for one entity in its local currency (state the currency)."),
    ("ex_oee_plant_quarter",
     "OEE by plant and quarter compared with the target",
     f"""SELECT plant, plant_name, finish_quarter,
       MEASURE(oee_pct) AS oee_pct,
       MEASURE(oee_target_pct) AS oee_target_pct
FROM {C}.manufacturing.production_performance_metrics
WHERE finish_year >= 2025
GROUP BY ALL
ORDER BY plant, finish_quarter""",
     "OEE trends per plant or line (OEE is 0-100; target from production_line.nominal_oee_target_percent)."),
    ("ex_line_month_kpis",
     "Monthly yield, scrap rate, downtime and late orders for line SE-NKP-L2 in 2026",
     f"""SELECT finish_month,
       MEASURE(yield_pct) AS yield_pct,
       MEASURE(scrap_rate_pct) AS scrap_rate_pct,
       MEASURE(downtime_minutes) AS downtime_minutes,
       MEASURE(late_order_count) AS late_orders
FROM {C}.manufacturing.production_performance_metrics
WHERE production_line = 'SE-NKP-L2'
  AND finish_year = 2026
GROUP BY ALL
ORDER BY finish_month""",
     "Line-level monthly quality / performance. Lines are named by their tag (PL-POZ-L2, FI-TMP-L1, ...)."),
    ("ex_cost_variance_eur",
     "Planned vs actual production cost and variance in EUR by plant for 2026",
     f"""SELECT plant,
       MEASURE(planned_cost_eur) AS planned_cost_eur,
       MEASURE(actual_cost_eur) AS actual_cost_eur,
       MEASURE(cost_variance_eur) AS cost_variance_eur,
       MEASURE(cost_variance_eur_pct) AS cost_variance_pct
FROM {C}.manufacturing.production_performance_metrics
WHERE finish_year = 2026
GROUP BY ALL
ORDER BY cost_variance_eur DESC""",
     "Production cost variance across plants: use the EUR measures (plants book in SEK, PLN, EUR)."),
    ("ex_yield_loss_reasons",
     "Yield losses by reason code and plant",
     f"""SELECT f.erp_plant_code AS plant,
       y.yield_loss_reason_code,
       y.yield_loss_reason_description,
       COUNT(*) AS yield_records,
       SUM(y.scrap_quantity) AS scrap_quantity,
       ROUND(100 * SUM(y.output_quantity) / SUM(y.input_quantity), 2) AS yield_pct
FROM {C}.manufacturing.yield_record y
JOIN {C}.manufacturing.manufacturing_facility f ON f.manufacturing_facility_id = y.manufacturing_facility_id
WHERE y.yield_loss_reason_code IS NOT NULL
GROUP BY ALL
ORDER BY scrap_quantity DESC""",
     "Root cause of yield / scrap problems: yield_record.yield_loss_reason_code (join production_line on production_line_id "
     "for a specific line, filter on measurement_timestamp for a period)."),
    ("ex_shoppers_segment_country",
     "Number of shoppers by country and CLTV segment",
     f"""SELECT country_code, cltv_segment,
       MEASURE(total_shoppers) AS shoppers
FROM {C}.consumer.shopper_metrics
GROUP BY ALL
ORDER BY country_code, shoppers DESC""",
     "Shopper base questions (counts by segment / country / lifecycle). Never list individual shoppers."),
    ("ex_active_subscriptions",
     "Active subscriptions by type and delivery frequency",
     f"""SELECT subscription_type, frequency,
       COUNT(*) AS active_subscriptions
FROM {C}.consumer.subscription
WHERE subscription_status = 'active'
GROUP BY ALL
ORDER BY active_subscriptions DESC""",
     "Subscription questions use consumer.subscription (status active / paused / cancelled / expired)."),
    ("ex_open_payables_eur",
     "Unpaid supplier invoices by company code in EUR",
     f"""WITH fx AS (
  SELECT jel.company_code_id, AVG(jel.exchange_rate) AS eur_rate
  FROM {C}.finance.journal_entry_line jel
  JOIN {C}.finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
  WHERE je.posting_status = 'posted' AND je.fiscal_year = 2026 AND je.fiscal_period = 9
  GROUP BY jel.company_code_id
)
SELECT cc.code AS company_code,
       COUNT(*) AS unpaid_invoices,
       ROUND(SUM(ap.gross_amount * fx.eur_rate), 2) AS unpaid_amount_eur
FROM {C}.finance.ap_invoice ap
JOIN {C}.finance.company_code cc ON cc.company_code_id = ap.company_code_id
JOIN fx ON fx.company_code_id = ap.company_code_id
WHERE ap.invoice_status <> 'paid'
GROUP BY ALL
ORDER BY unpaid_amount_eur DESC""",
     "Pattern for converting local-currency amounts to EUR: FX CTE from journal_entry_line.exchange_rate per company code "
     "(and month); balances at the September 2026 rate."),
]

# ---------------------------------------------------------------------------------------------------------
# 4. SQL snippets (raw-table measures / filters / expressions; metric views already govern their measures)
#    Each snippet carries a test FROM clause (not emitted) used by --run-sql.
# ---------------------------------------------------------------------------------------------------------
GL_FROM = (f"{C}.finance.journal_entry_line journal_entry_line JOIN {C}.finance.journal_entry journal_entry "
           "ON journal_entry.journal_entry_id = journal_entry_line.journal_entry_id JOIN "
           f"{C}.finance.gl_account gl_account ON gl_account.gl_account_id = journal_entry_line.gl_account_id")
SNIPPETS = {
    "measures": [
        ("sm_nr_gl", "net_revenue_eur_gl", "Net Revenue (EUR, GL)",
         "SUM(CASE WHEN gl_account.account_group = 'REVENUE' THEN CASE WHEN journal_entry_line.debit_credit_indicator = 'C' "
         "THEN journal_entry_line.amount_group_currency ELSE -journal_entry_line.amount_group_currency END END)",
         ["revenue", "net revenue", "net sales", "turnover", "sales"], GL_FROM),
        ("sm_cogs_gl", "cogs_eur_gl", "COGS (EUR, GL)",
         "SUM(CASE WHEN gl_account.account_group = 'COGS' THEN CASE WHEN journal_entry_line.debit_credit_indicator = 'D' "
         "THEN journal_entry_line.amount_group_currency ELSE -journal_entry_line.amount_group_currency END END)",
         ["cost of goods sold", "cost of sales"], GL_FROM),
        ("sm_webshop_orders", "webshop_orders", "Webshop orders",
         "COUNT(DISTINCT dtc_order.dtc_order_id)", ["number of orders", "order count"],
         f"{C}.consumer.dtc_order dtc_order"),
        ("sm_open_ar_local", "open_ar_local", "Open AR (local currency)",
         "SUM(ar_invoice.outstanding_balance)", ["open receivables", "outstanding balance"],
         f"{C}.finance.ar_invoice ar_invoice"),
        ("sm_order_yield", "production_yield_pct", "Production yield %",
         "100 * SUM(production_order.confirmed_quantity) / SUM(production_order.order_quantity)", ["yield", "yield rate"],
         f"{C}.manufacturing.production_order production_order"),
        ("sm_record_scrap", "yield_record_scrap_pct", "Scrap rate % (yield records)",
         "100 * SUM(yield_record.scrap_quantity) / SUM(yield_record.input_quantity)", ["scrap rate", "scrap %"],
         f"{C}.manufacturing.yield_record yield_record"),
    ],
    "filters": [
        ("sf_posted", "Posted GL documents", "journal_entry.posting_status = 'posted'", ["posted", "booked"], GL_FROM),
        ("sf_revenue_accounts", "Revenue accounts", "gl_account.account_group = 'REVENUE'", ["revenue accounts"], GL_FROM),
        ("sf_not_cancelled", "Non-cancelled webshop orders", "lower(dtc_order.order_status) <> 'cancelled'",
         ["valid orders", "excluding cancellations"], f"{C}.consumer.dtc_order dtc_order"),
        ("sf_last_12m_orders", "Webshop orders in the last 12 months",
         "dtc_order.order_date BETWEEN DATE'2025-10-01' AND DATE'2026-09-30'", ["last 12 months", "past year", "LTM"],
         f"{C}.consumer.dtc_order dtc_order"),
        ("sf_completed_po", "Completed production orders",
         "upper(production_order.order_status) IN ('CNF', 'DLV', 'TECO', 'CLSD')", ["completed orders", "finished orders"],
         f"{C}.manufacturing.production_order production_order"),
        ("sf_overdue_ar", "Overdue receivables",
         "ar_invoice.outstanding_balance > 0 AND ar_invoice.due_date < DATE'2026-09-30'", ["overdue", "past due"],
         f"{C}.finance.ar_invoice ar_invoice"),
    ],
    "expressions": [
        ("se_order_month", "order_month", "Order month", "DATE_TRUNC('MONTH', dtc_order.order_date)",
         ["order month"], f"{C}.consumer.dtc_order dtc_order"),
        ("se_fiscal_month", "fiscal_month", "Fiscal month",
         "MAKE_DATE(journal_entry.fiscal_year, journal_entry.fiscal_period, 1)", ["posting month", "fiscal month"],
         f"{C}.finance.journal_entry journal_entry"),
        ("se_on_time", "on_time", "Finished on time",
         "CAST(production_order.actual_finish_timestamp AS DATE) <= production_order.scheduled_finish_date",
         ["on time", "on-time"], f"{C}.manufacturing.production_order production_order"),
        ("se_days_past_due", "days_past_due", "Days past due",
         "datediff(DATE'2026-09-30', ar_invoice.due_date)", ["days overdue"], f"{C}.finance.ar_invoice ar_invoice"),
    ],
}

# Non-FK joins only (FK-backed joins are derived by Genie from the Unity Catalog constraints).
JOINS = [
    ("js_jel_plant",
     ("finance.journal_entry_line", "journal_entry_line"), ("manufacturing.manufacturing_facility", "manufacturing_facility"),
     "`journal_entry_line`.`plant_code` = `manufacturing_facility`.`plant_code`", "MANY_TO_ONE"),
]

# ---------------------------------------------------------------------------------------------------------
# 5. Sample questions (shown in the UI)
# ---------------------------------------------------------------------------------------------------------
SAMPLE_QUESTIONS = [
    ("sq_nr_quarter", "What were net revenue and gross margin by quarter in 2026?"),
    ("sq_webshop_vs_finance", "Why is webshop revenue higher than the revenue finance reports?"),
    ("sq_worst_ar", "Which company has the most overdue receivables, and why?"),
    ("sq_tampere", "How did the Tampere plant's OEE develop since start-up?"),
    ("sq_poznan", "What happened on Poznań line PL-POZ-L2 in March 2026?"),
    ("sq_loyalty", "How do Gold and Platinum members shop compared with non-members?"),
    ("sq_market_sep", "Show webshop sales by market for September 2026"),
    ("sq_brand_margin", "Which brand has the highest gross margin?"),
    ("sq_returns", "What are the top reasons for webshop returns?"),
]

# ---------------------------------------------------------------------------------------------------------
# 6. Benchmarks (checked SQL; questions differ from the examples). Tricky ones are marked in the README.
# ---------------------------------------------------------------------------------------------------------
BENCHMARKS = [
    # finance - revenue definition (S1) and currency (S2)
    ("bm_revenue_2025", "What was our total revenue in 2025?",
     f"SELECT MEASURE(net_revenue_eur) AS net_revenue_eur FROM {C}.finance.net_revenue_metrics WHERE fiscal_year = 2025"),
    ("bm_gm_ytd_2026", "What is our gross margin percentage year to date?",
     f"SELECT MEASURE(gross_margin_pct) AS gross_margin_pct FROM {C}.finance.net_revenue_metrics WHERE fiscal_year = 2026"),
    ("bm_top_entity_2025", "Which legal entity generated the most net revenue in 2025?",
     f"""SELECT company_code, MEASURE(net_revenue_eur) AS net_revenue_eur
FROM {C}.finance.net_revenue_metrics WHERE fiscal_year = 2025
GROUP BY ALL ORDER BY net_revenue_eur DESC LIMIT 1"""),
    ("bm_mjuk_2025", "How much net revenue did Mjuk Care generate in 2025?",
     f"""SELECT MEASURE(net_revenue_eur) AS net_revenue_eur
FROM {C}.finance.net_revenue_metrics WHERE fiscal_year = 2025 AND brand = 'Mjuk Care'"""),
    ("bm_pl01_variance", "How much production variance did PL01 book in March 2026?",
     f"""SELECT MEASURE(production_variance_eur) AS production_variance_eur
FROM {C}.finance.net_revenue_metrics WHERE company_code = 'PL01' AND fiscal_year = 2026 AND fiscal_period = 3"""),
    ("bm_dtc_vs_finance_2025", "Compare webshop net sales with the DTC net revenue booked in finance for 2025, in EUR.",
     f"""WITH web AS (SELECT MEASURE(dtc_net_sales_eur) AS webshop_net_sales_eur
                 FROM {C}.consumer.dtc_sales_metrics WHERE order_year = 2025),
     fin AS (SELECT MEASURE(dtc_net_revenue_eur) AS finance_dtc_net_revenue_eur
             FROM {C}.finance.net_revenue_metrics WHERE fiscal_year = 2025)
SELECT web.webshop_net_sales_eur, fin.finance_dtc_net_revenue_eur FROM web CROSS JOIN fin"""),
    # consumer
    ("bm_gmv_sep_eur", "What was total webshop GMV across all markets in September 2026?",
     f"SELECT MEASURE(gmv_eur) AS gmv_eur FROM {C}.consumer.dtc_sales_metrics WHERE order_month = DATE'2026-09-01'"),
    ("bm_swe_net_sales_2025", "What were webshop net sales in Sweden in 2025 in Swedish kronor?",
     f"""SELECT MEASURE(dtc_net_sales_local) AS dtc_net_sales_sek
FROM {C}.consumer.dtc_sales_metrics WHERE market = 'SWE' AND order_year = 2025 AND currency_code = 'SEK'"""),
    ("bm_orders_q3", "How many webshop orders did we receive in Q3 2026?",
     f"SELECT MEASURE(order_count) AS orders FROM {C}.consumer.dtc_sales_metrics WHERE order_quarter = '2026-Q3'"),
    ("bm_active_shoppers_12m", "How many active shoppers did we have in the 12 months to September 2026?",
     f"""SELECT MEASURE(active_shoppers) AS active_shoppers
FROM {C}.consumer.dtc_sales_metrics WHERE order_date BETWEEN DATE'2025-10-01' AND DATE'2026-09-30'"""),
    ("bm_gold_plat_aov", "Compare the average order value of Gold and Platinum members with non-members over the last 12 months.",
     f"""SELECT CASE WHEN loyalty_tier IN ('Gold', 'Platinum') THEN 'Gold/Platinum' ELSE 'Non-member' END AS member_group,
       MEASURE(avg_order_value_eur) AS aov_eur
FROM {C}.consumer.dtc_sales_metrics
WHERE order_date BETWEEN DATE'2025-10-01' AND DATE'2026-09-30'
  AND loyalty_tier IN ('Gold', 'Platinum', 'Non-member')
GROUP BY ALL ORDER BY member_group"""),
    ("bm_return_rate_2025", "What share of webshop sales value was returned in 2025?",
     f"SELECT MEASURE(return_rate_pct) AS return_rate_pct FROM {C}.consumer.dtc_sales_metrics WHERE order_year = 2025"),
    ("bm_members_per_tier", "How many loyalty members are in each Fjällmark Friends tier?",
     f"""SELECT t.tier_name, COUNT(*) AS members
FROM {C}.consumer.shopper s
JOIN {C}.consumer.loyalty_tier t ON t.loyalty_tier_id = s.loyalty_tier_id
GROUP BY t.tier_name, t.tier_rank ORDER BY t.tier_rank"""),
    ("bm_at_risk", "How many shoppers are in the at-risk CLTV segment?",
     f"SELECT MEASURE(total_shoppers) AS shoppers FROM {C}.consumer.shopper_metrics WHERE cltv_segment = 'at_risk'"),
    # finance - receivables (S6)
    ("bm_highest_dso", "Which company code has the highest DSO?",
     f"""SELECT company_code, MEASURE(dso_days) AS dso_days
FROM {C}.finance.receivables_metrics GROUP BY ALL ORDER BY dso_days DESC LIMIT 1"""),
    ("bm_group_dso", "What is the group DSO?",
     f"SELECT MEASURE(dso_days) AS dso_days FROM {C}.finance.receivables_metrics"),
    ("bm_de01_overdue", "How much of DE01's open receivables is overdue, in EUR?",
     f"SELECT MEASURE(overdue_ar_eur) AS overdue_ar_eur FROM {C}.finance.receivables_metrics WHERE company_code = 'DE01'"),
    ("bm_disputed", "How many invoices are currently disputed and what is their open value in EUR?",
     f"""SELECT MEASURE(disputed_invoice_count) AS disputed_invoices, MEASURE(disputed_ar_eur) AS disputed_ar_eur
FROM {C}.finance.receivables_metrics"""),
    # manufacturing - Tampere ramp-up (S4), Poznań incident (S3)
    ("bm_tampere_oee", "What was the OEE of the Tampere plant in each quarter since it started?",
     f"""SELECT finish_quarter, MEASURE(oee_pct) AS oee_pct
FROM {C}.manufacturing.production_performance_metrics WHERE plant = 'FI-TMP'
GROUP BY ALL ORDER BY finish_quarter"""),
    ("bm_lowest_oee_2025", "Which plant had the lowest OEE in 2025?",
     f"""SELECT plant_name, MEASURE(oee_pct) AS oee_pct
FROM {C}.manufacturing.production_performance_metrics WHERE finish_year = 2025
GROUP BY ALL ORDER BY oee_pct ASC LIMIT 1"""),
    ("bm_poznan_l2_feb_apr", "How did yield, scrap rate and downtime on line PL-POZ-L2 change from February to April 2026?",
     f"""SELECT finish_month,
       MEASURE(yield_pct) AS yield_pct, MEASURE(scrap_rate_pct) AS scrap_rate_pct, MEASURE(downtime_minutes) AS downtime_minutes
FROM {C}.manufacturing.production_performance_metrics
WHERE production_line = 'PL-POZ-L2' AND finish_month BETWEEN DATE'2026-02-01' AND DATE'2026-04-01'
GROUP BY ALL ORDER BY finish_month"""),
    ("bm_poznan_reason", "What was the yield loss reason on Poznań line 2 in March 2026?",
     f"""SELECT DISTINCT y.yield_loss_reason_code, y.yield_loss_reason_description
FROM {C}.manufacturing.yield_record y
JOIN {C}.manufacturing.production_line pl ON pl.production_line_id = y.production_line_id
WHERE pl.mes_asset_tag = 'PL-POZ-L2'
  AND y.measurement_timestamp >= TIMESTAMP'2026-03-01' AND y.measurement_timestamp < TIMESTAMP'2026-04-01'
  AND y.yield_loss_reason_code IS NOT NULL"""),
    ("bm_late_2026", "How many production orders finished late in 2026 at each plant?",
     f"""SELECT plant, MEASURE(late_order_count) AS late_orders
FROM {C}.manufacturing.production_performance_metrics WHERE finish_year = 2026
GROUP BY ALL ORDER BY plant"""),
    ("bm_poz_downtime_month", "In which month of 2026 did the Poznań plant have the most downtime?",
     f"""SELECT finish_month, MEASURE(downtime_minutes) AS downtime_minutes
FROM {C}.manufacturing.production_performance_metrics WHERE plant = 'PL-POZ' AND finish_year = 2026
GROUP BY ALL ORDER BY downtime_minutes DESC LIMIT 1"""),
    ("bm_on_time_2026", "What is the on-time completion rate of production orders per plant in 2026?",
     f"""SELECT plant, MEASURE(on_time_completion_pct) AS on_time_completion_pct
FROM {C}.manufacturing.production_performance_metrics WHERE finish_year = 2026
GROUP BY ALL ORDER BY plant"""),
]

TRICKY = {"bm_revenue_2025", "bm_gm_ytd_2026", "bm_gmv_sep_eur", "bm_active_shoppers_12m", "bm_dtc_vs_finance_2025",
          "bm_gold_plat_aov", "bm_poznan_reason", "bm_swe_net_sales_2025"}


# ---------------------------------------------------------------------------------------------------------
# Assemble
# ---------------------------------------------------------------------------------------------------------
def source_entry(s):
    e = {"identifier": f"{C}.{s['id']}", "description": [s["description"]]}
    if s.get("column_configs"):
        cfgs = sorted(s["column_configs"], key=lambda c: c["column_name"])
        names = [c["column_name"] for c in cfgs]
        dup = {n for n in names if names.count(n) > 1}
        if dup:
            sys.exit(f"duplicate column_configs in {s['id']}: {sorted(dup)}")
        e["column_configs"] = cfgs
    return e


def build_space():
    by_id = lambda xs: sorted(xs, key=lambda x: x["id"])  # noqa: E731
    space = {
        "version": 2,
        "config": {"sample_questions": by_id([{"id": nid(k), "question": [q]} for k, q in SAMPLE_QUESTIONS])},
        "data_sources": {
            "tables": sorted([source_entry(t) for t in TABLES], key=lambda x: x["identifier"]),
            "metric_views": sorted([source_entry(m) for m in METRIC_VIEWS], key=lambda x: x["identifier"]),
        },
        "instructions": {
            "text_instructions": [{"id": nid("text_instruction"), "content": text_instruction()}],
            "example_question_sqls": by_id([
                {"id": nid(k), "question": [q], "sql": lines(sql), "usage_guidance": [g]} for k, q, sql, g in EXAMPLES]),
            "join_specs": by_id([
                {"id": nid(k), "left": {"identifier": f"{C}.{l[0]}", "alias": l[1]},
                 "right": {"identifier": f"{C}.{r[0]}", "alias": r[1]},
                 "sql": [cond, f"--rt=FROM_RELATIONSHIP_TYPE_{rt}--"]} for k, l, r, cond, rt in JOINS]),
            "sql_snippets": {
                "measures": by_id([{"id": nid(k), "alias": a, "display_name": dn, "sql": [s], "synonyms": syn}
                                   for k, a, dn, s, syn, _ in SNIPPETS["measures"]]),
                "filters": by_id([{"id": nid(k), "display_name": dn, "sql": [s], "synonyms": syn}
                                  for k, dn, s, syn, _ in SNIPPETS["filters"]]),
                "expressions": by_id([{"id": nid(k), "alias": a, "display_name": dn, "sql": [s], "synonyms": syn}
                                      for k, a, dn, s, syn, _ in SNIPPETS["expressions"]]),
            },
        },
        "benchmarks": {"questions": by_id([
            {"id": nid(k), "question": [q], "answer": [{"format": "SQL", "content": lines(sql)}]}
            for k, q, sql in BENCHMARKS])},
    }
    validate(space)
    return space


def validate(space):
    n_sources = len(space["data_sources"]["tables"]) + len(space["data_sources"]["metric_views"])
    assert n_sources <= 45, f"{n_sources} data sources (bootcamp limit 45, platform limit 50)"
    ins = space["instructions"]
    assert len(ins["text_instructions"]) == 1
    ins_ids = [x["id"] for x in ins["text_instructions"] + ins["example_question_sqls"] + ins["join_specs"]
               + ins["sql_snippets"]["measures"] + ins["sql_snippets"]["filters"] + ins["sql_snippets"]["expressions"]]
    q_ids = [x["id"] for x in space["config"]["sample_questions"] + space["benchmarks"]["questions"]]
    assert len(set(ins_ids)) == len(ins_ids), "instruction ids not unique"
    assert len(set(q_ids)) == len(q_ids), "question ids not unique"
    for s in space["data_sources"]["tables"] + space["data_sources"]["metric_views"]:
        for c in s.get("column_configs", []):
            if c.get("exclude") and (c.get("enable_entity_matching") or c.get("synonyms")):
                raise AssertionError(f"{s['identifier']}.{c['column_name']} is excluded and configured")
    text = "".join(ins["text_instructions"][0]["content"])
    assert len(text) < 25000, "text instruction too long"
    for x in ins["example_question_sqls"] + [b for b in space["benchmarks"]["questions"]]:
        sql = "".join(x.get("sql") or x["answer"][0]["content"])
        assert "SELECT *" not in sql.upper().replace("COUNT(*)", ""), f"SELECT * in {x['question']}"


LICENSE_NOTE = [
    "Genie Agent template for the Fjällmark Genie bootcamp - generated by tools/build_genie_template.py, do not edit by hand.",
    "Built on tables of the Lakehouse Industry Data Model - Consumer Goods v2 MVM, Copyright (2025) Databricks, Inc.;",
    "use is subject to the Databricks license (LICENSE.md and NOTICE.md in the bootcamp folder, copies of tools/model/).",
    "Modified: agent content (descriptions, instructions, examples, benchmarks) written for the fictional company",
    "Fjällmark Consumer Goods AB. Placeholder __CATALOG__ is replaced by bootcamp/notebooks/04_genie_agent.py.",
]


def render():
    space = build_space()
    space_json = json.dumps(space, ensure_ascii=False, sort_keys=False)
    version = hashlib.sha256(space_json.encode("utf-8")).hexdigest()[:12]
    doc = {
        "_license": LICENSE_NOTE,
        "_generated_by": SCRIPT,
        "template_version": version,
        "title": TITLE,
        "description": DESCRIPTION,
        "tricky_benchmark_ids": sorted(nid(k) for k in TRICKY),
        "serialized_space": space,
    }
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n", space


# ---------------------------------------------------------------------------------------------------------
# Live SQL check (Databricks CLI + Statement Execution API; standard library only)
# ---------------------------------------------------------------------------------------------------------
def run_sql(sql, warehouse, profile):
    body = json.dumps({"statement": sql, "warehouse_id": warehouse, "wait_timeout": "50s",
                       "on_wait_timeout": "CONTINUE", "format": "JSON_ARRAY", "disposition": "INLINE"})
    out = subprocess.run(["databricks", "api", "post", "/api/2.0/sql/statements", "--json", body, "-p", profile],
                         capture_output=True, text=True)
    if out.returncode:
        return "ERROR", out.stderr.strip()[:300], None
    r = json.loads(out.stdout)
    import time
    while r["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(2)
        g = subprocess.run(["databricks", "api", "get", f"/api/2.0/sql/statements/{r['statement_id']}", "-p", profile],
                           capture_output=True, text=True)
        r = json.loads(g.stdout)
    if r["status"]["state"] != "SUCCEEDED":
        return "ERROR", r["status"].get("error", {}).get("message", "")[:300], None
    rows = r.get("result", {}).get("data_array") or []
    cols = [c["name"] for c in r["manifest"]["schema"]["columns"]]
    return "OK", len(rows), (cols, rows[:6])


def live_check(space, catalog, warehouse, profile):
    rep = lambda s: s.replace(C, catalog)  # noqa: E731
    jobs = []
    for s in space["data_sources"]["tables"] + space["data_sources"]["metric_views"]:
        jobs.append(("source", s["identifier"], f"DESCRIBE TABLE {rep(s['identifier'])}"))
    for x in space["instructions"]["example_question_sqls"]:
        jobs.append(("example", x["question"][0], rep("".join(x["sql"]))))
    for k, a, dn, s, syn, frm in SNIPPETS["measures"]:
        jobs.append(("snippet", dn, rep(f"SELECT {s} AS v FROM {frm}")))
    for k, dn, s, syn, frm in SNIPPETS["filters"]:
        jobs.append(("snippet", dn, rep(f"SELECT COUNT(*) AS n FROM {frm} WHERE {s}")))
    for k, a, dn, s, syn, frm in SNIPPETS["expressions"]:
        jobs.append(("snippet", dn, rep(f"SELECT {s} AS v, COUNT(*) AS n FROM {frm} GROUP BY 1 ORDER BY 2 DESC LIMIT 3")))
    for k, l, r, cond, rt in JOINS:
        cond_sql = cond.replace("`", "")
        jobs.append(("join", k, rep(f"SELECT COUNT(*) AS n FROM {C}.{l[0]} {l[1]} JOIN {C}.{r[0]} {r[1]} ON {cond_sql}")))
    for x in space["benchmarks"]["questions"]:
        jobs.append(("benchmark", x["question"][0], rep("".join(x["answer"][0]["content"]))))
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda j: (j, run_sql(j[2], warehouse, profile)), jobs))
    errors = 0
    for (kind, name, sql), (state, n, sample) in results:
        if state != "OK":
            errors += 1
            print(f"ERROR {kind:9} {name}\n      {n}")
        else:
            first = "" if not sample or not sample[1] else dict(zip(sample[0], sample[1][0]))
            zero = "  <-- 0 rows" if n == 0 and kind in ("example", "benchmark") else ""
            print(f"OK    {kind:9} rows={n:<3} {name[:70]}{zero}\n      {first if kind != 'source' else ''}")
            if zero:
                errors += 1
    print(f"\n{len(results)} checks, {errors} errors")
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if the template file is missing or stale")
    ap.add_argument("--run-sql", action="store_true", help="run every SQL of the template on --catalog")
    ap.add_argument("--catalog")
    ap.add_argument("--warehouse")
    ap.add_argument("--profile", default="DEFAULT")
    a = ap.parse_args()
    text, space = render()
    if a.run_sql:
        if not (a.catalog and a.warehouse):
            sys.exit("--run-sql needs --catalog and --warehouse")
        sys.exit(1 if live_check(space, a.catalog, a.warehouse, a.profile) else 0)
    current = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else None
    if a.check:
        if current != text:
            print(f"STALE: {os.path.relpath(OUT, ROOT)} - run python3 -I {SCRIPT}")
            sys.exit(1)
        print("template is up to date")
        return
    if current != text:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {os.path.relpath(OUT, ROOT)}")
    else:
        print("template unchanged")
    n_src = len(space["data_sources"]["tables"]) + len(space["data_sources"]["metric_views"])
    print(f"{n_src} data sources ({len(space['data_sources']['metric_views'])} metric views), "
          f"{len(space['instructions']['example_question_sqls'])} example SQLs, "
          f"{sum(len(v) for v in space['instructions']['sql_snippets'].values())} snippets, "
          f"{len(space['instructions']['join_specs'])} join specs, "
          f"{len(space['config']['sample_questions'])} sample questions, "
          f"{len(space['benchmarks']['questions'])} benchmarks")


if __name__ == "__main__":
    main()
