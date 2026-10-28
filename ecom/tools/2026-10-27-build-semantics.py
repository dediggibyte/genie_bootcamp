#!/usr/bin/env python3
"""Build the business context and the Genie Agent templates of the ecom bootcamp (Nordvik Group) from ONE spec.

Writes, deterministically (same script -> same bytes):

  ecom/context/2026-10-27-glossary.csv                       index of every business term (domain, subdomain, page)
  ecom/context/<domain>/_domain.md                           the domain: name, governed tag, owner, subdomains
  ecom/context/<domain>/<subdomain>/_subdomain.md            each subdomain with its tables and metric views
  ecom/context/<domain>/pages/2026-10-27-<term>.md           one page per business term (definition, SQL, value)
  ecom/genie/2026-10-27-<domain>-agent.json                  Genie Agent template (serialized space, __CATALOG__)

Single sources it reads (never duplicates):
  * which table / metric view belongs to which subdomain    -> ecom/config/2026-10-27-tags.json (ecom_subdomain)
  * reference values quoted on pages and in benchmarks      -> ecom/data/2026-10-27-expected-answers.json
  * column / dimension names checked in every config        -> ecom/pipeline/*/2026-10-27-03-gold.sql, ecom/metric_views

Read by notebooks/2026-10-27-04-genie-agents.py (templates) and notebooks/2026-10-27-05-context-common.py (context).

Usage (from the repo root, standard library only):

  python3 -I ecom/tools/2026-10-27-build-semantics.py           # write the files
  python3 -I ecom/tools/2026-10-27-build-semantics.py --check   # exit 1 if a file is missing or stale
"""
import csv
import hashlib
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATE = "2026-10-27"
ECOM = "ecom"
SCRIPT = "ecom/tools/%s-build-semantics.py" % DATE
C = "__CATALOG__"
GITHUB_REPO = "dediggibyte/genie_bootcamp"
SOURCE_NOTE = "Nordvik Group business glossary (fictional), ecom bootcamp - ecom/context/"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


ANSWERS = json.loads(read("%s/data/%s-expected-answers.json" % (ECOM, DATE)))
TAGS = json.loads(read("%s/config/%s-tags.json" % (ECOM, DATE)))["tables"]


def ref(path):
    """A value of the expected answers, e.g. ref('retail.total.net_revenue_sek')."""
    node = ANSWERS
    for part in path.split("."):
        node = node[part]
    return node


def fmt(value, unit=""):
    if isinstance(value, str):
        return value
    text = "{:,.2f}".format(value).replace(",", " ") if isinstance(value, float) and value != int(value) \
        else "{:,}".format(int(value)).replace(",", " ")
    return text + ({"SEK": " SEK", "%": " %", "GB": " GB"}.get(unit, (" " + unit) if unit else ""))


def nid(key):
    """Deterministic 32-hex id (stable across rebuilds)."""
    return hashlib.md5(("nordvik-genie:" + key).encode("utf-8")).hexdigest()


def lines(sql):
    parts = sql.strip("\n").split("\n")
    return [p + "\n" for p in parts[:-1]] + [parts[-1]]


# -------------------------------------------------------------------------------------------------------------
# Columns and metric-view dimensions that exist (every config below is checked against them)
# -------------------------------------------------------------------------------------------------------------
GOLD_COLS, MV_DIMS, MV_MEASURES = {}, {}, {}
for _d in ("retail", "mobility", "telecom"):
    for _block in read("%s/pipeline/%s/%s-03-gold.sql" % (ECOM, _d, DATE)).split("CREATE OR REFRESH MATERIALIZED VIEW ")[1:]:
        _name = re.match(r"\$\{catalog\}\.(\w+\.\w+)", _block).group(1)
        GOLD_COLS[_name] = re.findall(r"^  (\w+) (?:STRING|INT|DATE|DECIMAL|BOOLEAN)", _block, re.M)
    for _name, _yaml in re.findall(r"VIEW \$\{catalog\}\.(\w+\.\w+)\nWITH METRICS\nLANGUAGE YAML\nAS \$\$\n(.*?)\$\$;",
                                   read("%s/metric_views/%s-%s-metrics.sql" % (ECOM, DATE, _d)), re.S):
        _dims, _meas = _yaml.split("\n  dimensions:\n")[1].split("\n  measures:\n")
        MV_DIMS[_name] = re.findall(r"^    - name: (\w+)", _dims, re.M)
        MV_MEASURES[_name] = re.findall(r"^    - name: (\w+)", _meas, re.M)

# =============================================================================================================
# THE SPEC - domains, subdomains, business terms, Genie Agents
# =============================================================================================================
AGENTS = {"retail": "Nordvik Retail Analyst", "mobility": "Nordvik Mobility Analyst", "telecom": "Nordvik Connect Analyst"}

COMMON_RULES = """GOVERNANCE AND PRIVACY
- Every query runs with the permissions of the person who asks. Row filters (region / segment) and column masks
  (names, e-mail, phone, purchase cost, VIN) are applied by Unity Catalog - never try to work around them. If a
  result is empty or masked, say that the user may not have access to that scope.
- Answer about customers only in aggregate (counts, shares, segments); never list personal data.

STYLE
- Use the metric views for KPIs: SELECT <dimensions>, MEASURE(<measure>) FROM <metric view> ... GROUP BY ALL.
  Use the gold tables only for lists and details the metric views do not cover.
- Show amounts in SEK with two decimals and percentages 0-100 with two decimals; name the period you used.
- All data is synthetic (fictional Nordvik Group). Brand and model names only describe products."""

DOMAINS = {
    "retail": {
        "name": "Retail and Commerce",
        "unit": "Nordvik Retail",
        "domain_tag": "Nordvik Retail and Commerce",
        "subtitle": "Stores, webshop, products, customers, sales and returns",
        "description": ("Nordvik Retail sells electronics, fashion and beauty in 5 stores (Stockholm, Göteborg, Malmö) "
                        "and a webshop. Owns the product catalog, stores and channels, loyalty customers, sales and "
                        "returns - the source for net revenue, orders, average order value, gross margin and return rate."),
        "business_owner": "Head of Retail Commercial (role)",
        "technical_owner": "Retail Data Product Team (role)",
        "period": "orders 2026-01-01 to 2026-06-30",
        "subdomains": {
            "product_catalog": ("Product Catalog", "Products and their brands, categories, list prices and purchase costs."),
            "stores_channels": ("Stores and Channels", "The 5 stores and the webshop, their regions and sales channels."),
            "customers": ("Customers", "Loyalty customers of the Nordvik Club with tier and home city (personal data)."),
            "sales_returns": ("Sales and Returns", "Completed order lines and returned lines - revenue, margin, returns."),
        },
    },
    "mobility": {
        "name": "Mobility and Automotive",
        "unit": "Nordvik Mobility",
        "domain_tag": "Nordvik Mobility and Automotive",
        "subtitle": "Vehicle catalog, dealers, vehicle sales and aftersales service",
        "description": ("Nordvik Mobility sells new cars, vans and trucks through 5 dealers and a truck centre and "
                        "services them in its workshops. Owns the vehicle catalog, the dealer network, vehicle sales "
                        "and aftersales - the source for units sold, vehicle revenue, EV share and service revenue."),
        "business_owner": "Head of Mobility Sales and Aftersales (role)",
        "technical_owner": "Mobility Data Product Team (role)",
        "period": "sales and workshop visits 2026-01-01 to 2026-06-30",
        "subdomains": {
            "vehicle_catalog": ("Vehicle Catalog", "Vehicle models with brand, type, body, powertrain and list price."),
            "dealer_network": ("Dealer Network", "Dealers and the truck centre, their regions and workshops."),
            "vehicle_sales": ("Vehicle Sales", "New-vehicle sales and the private and fleet customers who buy them."),
            "aftersales_service": ("Aftersales Service", "Workshop visits: service types, labour, parts, warranty work."),
        },
    },
    "telecom": {
        "name": "Telecommunications and Media",
        "unit": "Nordvik Connect",
        "domain_tag": "Nordvik Telecommunications and Media",
        "subtitle": "Plans, subscriptions, billing and usage of the operator",
        "description": ("Nordvik Connect is a mobile, fibre and TV / streaming operator for consumers and businesses. "
                        "Owns price plans, customers and subscriptions, monthly billing and usage - the source for "
                        "billed revenue, ARPU, overdue amounts, data usage and streaming hours."),
        "business_owner": "Head of Connect Consumer and Business (role)",
        "technical_owner": "Connect Data Product Team (role)",
        "period": "billing and usage months 2026-05 and 2026-06",
        "subdomains": {
            "plans_products": ("Plans and Products", "Mobile, fibre, TV / streaming plans and bundles with their fees."),
            "customers_subscriptions": ("Customers and Subscriptions", "Consumer and business customers and their subscriptions."),
            "billing": ("Billing", "Monthly invoices per subscription: amounts, due dates, payment status."),
            "usage": ("Usage", "Monthly data, voice, SMS and streaming usage per subscription."),
        },
    },
}

# Business terms: key, title, subdomain, synonyms, short description, definition (markdown), metric view + measure,
# reference value (expected-answers path, unit, label), related terms, pitfalls, example questions.
TERMS = {
    "retail": [
        dict(key="net_revenue", title="Net Revenue", sub="sales_returns",
             syn=["revenue", "sales", "net sales", "turnover", "omsättning"],
             desc="Sales value of completed orders after line discounts, in SEK excl. VAT.",
             definition="**Net revenue** = Σ (`quantity` × `unit_price_sek` − `discount_sek`) over the lines of "
                        "**completed** orders (`retail.fact_sales.net_revenue_sek`). Cancelled orders are not sales "
                        "and are not in `fact_sales`. Returns are reported separately (refunds), not netted.",
             mv="retail.sales_metrics", measure="net_revenue_sek", value=("retail.total.net_revenue_sek", "SEK", "Jan-Jun 2026"),
             related=["gross_margin", "average_order_value", "return_rate"],
             pitfalls=["Adding cancelled orders - they are not in fact_sales and are not revenue.",
                       "Subtracting refunds from net revenue - Nordvik reports returns separately (return rate, refunds)."],
             questions=["What was net revenue by month?", "Which store region has the highest net revenue?"]),
        dict(key="gross_margin", title="Gross Margin", sub="sales_returns",
             syn=["margin", "gross profit", "GM%", "bruttomarginal"],
             desc="Net revenue minus purchase cost of the goods sold, in SEK and as % of net revenue.",
             definition="**Gross margin (SEK)** = net revenue − Σ (`quantity` × `dim_product.unit_cost_sek`). "
                        "**Gross margin %** = gross margin / net revenue × 100. Purchase cost is **confidential**: "
                        "users who are not cost readers see NULL (column mask), so the margin is NULL for them.",
             mv="retail.sales_metrics", measure="gross_margin_pct", value=("retail.total.gross_margin_pct", "%", "Jan-Jun 2026"),
             related=["net_revenue", "product_category"],
             pitfalls=["Averaging the margin % of categories - always divide total margin by total revenue.",
                       "Reporting a NULL margin as 0 - NULL means the purchase cost is masked for you."],
             questions=["What is the gross margin % by category?", "Which brand has the lowest gross margin?"]),
        dict(key="average_order_value", title="Average Order Value", sub="sales_returns",
             syn=["AOV", "basket size", "average basket", "average ticket"],
             desc="Net revenue divided by the number of completed orders.",
             definition="**AOV** = net revenue / number of distinct completed orders (`order_id`). It is a ratio of "
                        "sums, so it is computed per group from the totals - never as an average of line values.",
             mv="retail.sales_metrics", measure="average_order_value_sek",
             value=("retail.total.average_order_value_sek", "SEK", "Jan-Jun 2026"),
             related=["net_revenue", "sales_region_channel"],
             pitfalls=["AVG(net_revenue_sek) over order lines - that is the average line value, not the order value."],
             questions=["What is the average order value per channel?", "How did AOV develop by month?"]),
        dict(key="return_rate", title="Return Rate", sub="sales_returns",
             syn=["returns %", "return percentage", "returrate"],
             desc="Returned units as a share of units sold, by the order date of the sale.",
             definition="**Return rate %** = returned units / units sold × 100. Returns are matched to the sold line "
                        "(`fact_returns.order_line_id`) and counted in the month of the **order**, so a return in July "
                        "of a June order belongs to June. **Refunds** = Σ `fact_returns.refund_sek`.",
             mv="retail.sales_metrics", measure="return_rate_pct", value=("retail.total.return_rate_pct", "%", "Jan-Jun 2026"),
             related=["net_revenue", "return_reason"],
             pitfalls=["Counting returned orders instead of units.",
                       "Using the return date month - the rate is by order month."],
             questions=["What is the return rate by category?", "Which brands have the highest return rate?"]),
        dict(key="return_reason", title="Return Reason", sub="sales_returns",
             syn=["why returned", "return cause"],
             desc="Why a customer returned goods: wrong_size, changed_mind, defect or damaged.",
             definition="Every return carries one **reason**: `wrong_size`, `changed_mind`, `defect`, `damaged`. "
                        "`defect` and `damaged` are quality returns; `wrong_size` and `changed_mind` are customer returns.",
             mv="retail.return_metrics", measure="return_count", value=("retail.total.returns", "", "returns Jan-Jun 2026"),
             related=["return_rate"],
             pitfalls=["Mixing return counts (lines) with returned units."],
             questions=["What are the most common return reasons?", "How much was refunded for defects?"]),
        dict(key="sales_region_channel", title="Sales Region and Channel", sub="stores_channels",
             syn=["region", "channel", "online vs store", "webshop"],
             desc="Regions STO, GOT, MAL and ONLINE (webshop); channels store and online.",
             definition="Each order belongs to the **store** that sold it. Stores roll up to a **region**: `STO` "
                        "(Stockholm City, Kista), `GOT` (Göteborg Nordstan, Frölunda), `MAL` (Malmö Triangeln) and "
                        "`ONLINE` (the webshop). **Channel** = `store` or `online`. The region is the scope of the "
                        "governance row filter: a store manager sees only their region.",
             mv="retail.sales_metrics", measure="order_count", value=("retail.by_channel.online.orders", "", "webshop orders Jan-Jun 2026"),
             where="channel = 'online'",
             related=["net_revenue", "average_order_value"],
             pitfalls=["Filtering on the city 'Göteborg' instead of region GOT (the webshop is also registered in Stockholm)."],
             questions=["Compare webshop and store revenue.", "Which region had the most orders?"]),
        dict(key="loyalty_tier", title="Loyalty Tier", sub="customers",
             syn=["tier", "membership level", "Nordvik Club"],
             desc="Tier of the Nordvik Club loyalty programme: none, silver or gold.",
             definition="Every customer has a **loyalty tier** of the Nordvik Club: `none`, `silver`, `gold`. The tier "
                        "is the customer's current tier (no history). Customer names, e-mail and phone are personal "
                        "data - analyse customers only in aggregate.",
             mv="retail.sales_metrics", measure="order_count", value=("retail.total.orders", "", "completed orders Jan-Jun 2026, all tiers"),
             related=["average_order_value"],
             pitfalls=["Listing individual customers - answer with counts and shares."],
             questions=["How do gold members' orders compare with non-members?"]),
        dict(key="product_category", title="Product Category and Brand", sub="product_catalog",
             syn=["category", "department", "brand", "subcategory"],
             desc="Categories electronics, fashion, beauty; 9 brands; subcategories such as phone or perfume.",
             definition="Products belong to one **category** (`electronics`, `fashion`, `beauty`), one **subcategory** "
                        "(phone, laptop, tablet, jeans, jacket, sweatshirt, office_wear, perfume) and one **brand** "
                        "(Apple, Samsung, Google, H&M, Åhléns, Yves Saint Laurent, Jean Paul Gaultier, Dior, Chanel).",
             mv="retail.sales_metrics", measure="net_revenue_sek",
             value=("retail.by_category.electronics.net_revenue_sek", "SEK", "electronics net revenue Jan-Jun 2026"),
             where="category = 'electronics'",
             related=["net_revenue", "gross_margin"],
             pitfalls=["Treating 'Åhléns' as a store - here it is a fashion brand on sale in Nordvik stores."],
             questions=["Net revenue by brand", "Which subcategory sells the most units?"]),
    ],
    "mobility": [
        dict(key="units_sold", title="Vehicles Sold", sub="vehicle_sales",
             syn=["units", "registrations", "volume", "cars sold"],
             desc="Number of new vehicles sold (one row per vehicle in fact_vehicle_sales).",
             definition="**Vehicles sold** = number of rows in `mobility.fact_vehicle_sales` (one row per vehicle, "
                        "contract date `sale_date`). Cars, vans and trucks are counted alike - filter `vehicle_type` "
                        "for a single type.",
             mv="mobility.vehicle_sales_metrics", measure="units_sold", value=("mobility.sales_total.units_sold", "", "Jan-Jun 2026"),
             related=["vehicle_revenue", "ev_share"],
             pitfalls=["Counting service visits as sales."],
             questions=["How many vehicles did we sell per month?", "Units sold by dealer"]),
        dict(key="vehicle_revenue", title="Vehicle Revenue", sub="vehicle_sales",
             syn=["revenue", "vehicle sales value", "turnover"],
             desc="Sale price minus discount of the vehicles sold, SEK excl. VAT.",
             definition="**Vehicle revenue** = Σ (`sale_price_sek` − `discount_sek`) = Σ `net_sale_price_sek`. "
                        "**Average sale price** = vehicle revenue / vehicles sold. Trucks cost 2-4 MSEK, so mixed "
                        "averages are dominated by trucks - compare averages within a vehicle type.",
             mv="mobility.vehicle_sales_metrics", measure="vehicle_revenue_sek",
             value=("mobility.sales_total.vehicle_revenue_sek", "SEK", "Jan-Jun 2026"),
             related=["units_sold", "service_revenue"],
             pitfalls=["Using the list price without the discount.",
                       "Comparing average prices across cars and trucks."],
             questions=["What is the average sale price of cars?", "Vehicle revenue by brand"]),
        dict(key="ev_share", title="EV Share", sub="vehicle_sales",
             syn=["electric share", "EV mix", "share of electric"],
             desc="Battery electric vehicles as a share of vehicles sold.",
             definition="**EV share %** = vehicles with `powertrain = 'ev'` / vehicles sold × 100. Plug-in and full "
                        "**hybrids are not EVs** (only battery electric vehicles count).",
             mv="mobility.vehicle_sales_metrics", measure="ev_share_pct", value=("mobility.sales_total.ev_share_pct", "%", "Jan-Jun 2026"),
             related=["powertrain", "units_sold"],
             pitfalls=["Counting hybrids as EVs."],
             questions=["What is the EV share by vehicle type?", "How did EV share develop per month?"]),
        dict(key="powertrain", title="Powertrain", sub="vehicle_catalog",
             syn=["fuel type", "drivetrain", "engine type"],
             desc="ev (battery electric), hybrid, petrol or diesel.",
             definition="Every model has one **powertrain**: `ev`, `hybrid`, `petrol` or `diesel` "
                        "(`dim_vehicle_model.powertrain`, flag `is_ev`). Vehicle types: `car`, `van`, `truck`.",
             mv="mobility.vehicle_sales_metrics", measure="ev_share_pct", value=("mobility.sales_by_vehicle_type.truck.ev_share_pct", "%",
                                                                                "EV share of trucks Jan-Jun 2026"),
             where="vehicle_type = 'truck'",
             related=["ev_share"],
             pitfalls=["Treating 'XC60 Plug-in Hybrid' as an EV."],
             questions=["Units sold by powertrain"]),
        dict(key="dealer_region", title="Dealer and Region", sub="dealer_network",
             syn=["dealer", "dealership", "region", "workshop"],
             desc="5 car dealers and the truck centre in regions STO, GOT, MAL and UME.",
             definition="Dealers roll up to **regions**: `STO` (Bromma, Täby and the truck centre Södertälje), `GOT` "
                        "(Hisingen), `MAL` (Bulltofta), `UME` (Umeå, no workshop). Trucks are sold and serviced only "
                        "by the **truck centre** (D06). The region is the scope of the governance row filter.",
             mv="mobility.vehicle_sales_metrics", measure="units_sold", value=("mobility.sales_by_region.STO.units_sold", "",
                                                                               "vehicles sold in STO Jan-Jun 2026"),
             where="dealer_region = 'STO'",
             related=["units_sold", "service_revenue"],
             pitfalls=["Expecting service visits in UME - the Umeå dealer has no workshop."],
             questions=["Which dealer sold the most vehicles?", "Service visits by region"]),
        dict(key="service_revenue", title="Service Revenue", sub="aftersales_service",
             syn=["aftersales revenue", "workshop revenue"],
             desc="Amount billed to customers for workshop visits (warranty work is 0), SEK excl. VAT.",
             definition="**Service revenue** = Σ `billed_amount_sek` of the workshop visits = labour + parts, except "
                        "**warranty work**, which the manufacturer pays (billed 0 to the customer). Labour is 1 150 SEK "
                        "per hour for cars and vans, 1 450 SEK for trucks.",
             mv="mobility.service_metrics", measure="service_revenue_sek",
             value=("mobility.service_total.service_revenue_sek", "SEK", "Jan-Jun 2026"),
             related=["warranty_share", "vehicle_revenue"],
             pitfalls=["Adding labour + parts of warranty visits to revenue."],
             questions=["Service revenue by service type", "Which workshop earns the most?"]),
        dict(key="warranty_share", title="Warranty Share", sub="aftersales_service",
             syn=["warranty rate", "warranty work"],
             desc="Warranty visits as a share of all workshop visits.",
             definition="**Warranty share %** = visits with `is_warranty = true` / visits × 100. Warranty visits use "
                        "workshop hours but bring no service revenue.",
             mv="mobility.service_metrics", measure="warranty_share_pct",
             value=("mobility.service_total.warranty_share_pct", "%", "Jan-Jun 2026"),
             related=["service_revenue"],
             pitfalls=["Computing the share of service revenue instead of visits."],
             questions=["What is the warranty share by brand?"]),
        dict(key="fleet_customer", title="Fleet Customer", sub="vehicle_sales",
             syn=["fleet", "B2B customer", "company customer"],
             desc="A company that buys vans and trucks (customer_type = fleet); others are private.",
             definition="**Fleet customers** (`customer_type = 'fleet'`) are companies that buy vans and trucks and "
                        "some cars; **private** customers buy cars. Customer names, e-mail and phone are personal data.",
             mv="mobility.vehicle_sales_metrics", measure="units_sold", value=("mobility.sales_by_vehicle_type.truck.units_sold", "",
                                                                               "trucks sold Jan-Jun 2026 - all to fleet customers"),
             where="vehicle_type = 'truck'",
             related=["units_sold"],
             pitfalls=["Listing individual private customers - answer in aggregate."],
             questions=["How many vehicles did fleet customers buy?"]),
    ],
    "telecom": [
        dict(key="billed_revenue", title="Billed Revenue", sub="billing",
             syn=["revenue", "billing", "turnover", "intäkter"],
             desc="Invoiced amount excl. VAT of the monthly invoices.",
             definition="**Billed revenue** = Σ `amount_excl_vat_sek` of `telecom.fact_billing` (one invoice per "
                        "subscription and billing month = monthly fee + extra mobile usage). VAT (25 %) is not revenue.",
             mv="telecom.billing_metrics", measure="billed_revenue_sek",
             value=("telecom.billing_by_month.2026-06.billed_revenue_sek", "SEK", "June 2026"),
             where="billing_month = DATE'2026-06-01'",
             related=["arpu", "overdue_amount"],
             pitfalls=["Using amount incl. VAT."],
             questions=["Billed revenue by plan type", "Billed revenue per month"]),
        dict(key="arpu", title="ARPU", sub="billing",
             syn=["average revenue per user", "average revenue per subscription"],
             desc="Billed revenue divided by billed subscriptions, per month.",
             definition="**ARPU** = billed revenue / distinct billed subscriptions **in a month**. Always group by "
                        "`billing_month`: over two months the ratio divides two months of revenue by one set of "
                        "subscriptions and doubles.",
             mv="telecom.billing_metrics", measure="arpu_sek", value=("telecom.billing_by_month.2026-06.arpu_sek", "SEK", "June 2026"),
             where="billing_month = DATE'2026-06-01'",
             related=["billed_revenue", "customer_segment"],
             pitfalls=["ARPU over both months without grouping by month.",
                       "Dividing by customers instead of subscriptions."],
             questions=["What is ARPU by customer segment in June?", "ARPU by plan type"]),
        dict(key="overdue_amount", title="Overdue Amount", sub="billing",
             syn=["overdue", "arrears", "late payments"],
             desc="Invoiced amount excl. VAT of invoices past their due date and not paid.",
             definition="An invoice is **overdue** when its due date (invoice date + 30 days) has passed and it is not "
                        "paid (`payment_status = 'overdue'`). **Open** invoices are not yet due. June invoices are all "
                        "paid or open. **Paid share %** = paid invoices / invoices × 100.",
             mv="telecom.billing_metrics", measure="overdue_amount_sek",
             value=("telecom.billing_by_month.2026-05.overdue_amount_sek", "SEK", "May 2026 invoices"),
             where="billing_month = DATE'2026-05-01'",
             related=["billed_revenue"],
             pitfalls=["Counting open (not yet due) invoices as overdue."],
             questions=["Overdue amount by segment", "What share of June invoices is paid?"]),
        dict(key="active_subscription", title="Active Subscription", sub="customers_subscriptions",
             syn=["active lines", "subscriptions", "abonnemang"],
             desc="A subscription with status active (no end date).",
             definition="A subscription is **active** when `status = 'active'` (end date empty). Two subscriptions "
                        "were cancelled on 2026-05-31: they have May invoices and usage but nothing for June. A "
                        "customer can hold several subscriptions.",
             mv="telecom.billing_metrics", measure="billed_subscriptions",
             value=("telecom.active_subscriptions_now", "", "active subscriptions today"),
             sql="SELECT COUNT(*) AS active_subscriptions\nFROM <catalog>.telecom.dim_subscription\nWHERE status = 'active'",
             related=["arpu", "customer_segment"],
             pitfalls=["Counting customers instead of subscriptions."],
             questions=["How many active subscriptions per plan type?"]),
        dict(key="customer_segment", title="Customer Segment", sub="customers_subscriptions",
             syn=["segment", "consumer vs business", "B2B vs B2C"],
             desc="consumer or business; the scope of the governance row filter.",
             definition="Every customer is `consumer` or `business` (`dim_customer.customer_segment`, copied to "
                        "subscriptions, invoices and usage). Business customers buy the Företag plans. The segment is "
                        "the scope of the governance row filter.",
             mv="telecom.billing_metrics", measure="billed_revenue_sek",
             value=("telecom.billing_by_segment_june.business.billed_revenue_sek", "SEK", "business billed revenue June 2026"),
             where="billing_month = DATE'2026-06-01' AND customer_segment = 'business'",
             related=["arpu", "active_subscription"],
             pitfalls=["Mixing the plan's target segment with the customer's segment - use customer_segment."],
             questions=["Billed revenue by segment"]),
        dict(key="data_usage", title="Data Usage", sub="usage",
             syn=["data", "traffic", "GB"],
             desc="Data used in GB per subscription and month, mobile and fixed.",
             definition="**Data used** = Σ `data_gb` of `telecom.fact_usage` (one row per subscription and month). "
                        "**Data per subscription** = data used / subscriptions with usage, per month. Broadband and "
                        "bundles dominate the totals - compare within a plan type.",
             mv="telecom.usage_metrics", measure="avg_data_gb_per_subscription",
             value=("telecom.usage_by_month.2026-06.avg_data_gb_per_subscription", "GB", "per subscription, June 2026"),
             where="usage_month = DATE'2026-06-01'",
             related=["streaming_hours"],
             pitfalls=["Averaging over both months without grouping by month."],
             questions=["Data usage by plan type", "Average data per mobile subscription"]),
        dict(key="streaming_hours", title="Streaming Hours and Add-ons", sub="plans_products",
             syn=["viewing hours", "watch time", "streaming add-on", "Netflix", "Spotify", "Disney+", "Max"],
             desc="Hours streamed; plans can include Netflix, Spotify, Disney+ or Max.",
             definition="**Streaming hours** = Σ `streaming_hours` in the TV app and the included services. A plan "
                        "**includes streaming** when `dim_plan.included_streaming` lists a service (Netflix Standard, "
                        "Spotify Premium, Disney+ Standard, Max) - flag `has_streaming`.",
             mv="telecom.usage_metrics", measure="streaming_hours",
             value=("telecom.usage_by_month.2026-06.streaming_hours", "", "hours, June 2026"),
             where="usage_month = DATE'2026-06-01'",
             related=["data_usage"],
             pitfalls=["Assuming every TV plan includes Netflix - check included_streaming."],
             questions=["Streaming hours by plan", "Do customers with streaming add-ons use more data?"]),
    ],
}

# Genie Agents: sample questions (shown in the UI), example SQL (teaches), snippets, benchmarks (tests - never the
# same questions as the examples). A benchmark's "expect" names the value in expected-answers.json the first column
# of the first row must equal (checked by the DuckDB test in the README).
GENIE = {
    "retail": {
        "instruction": """You are the Nordvik Retail Analyst - one of three Genie Agents of Nordvik Group (fictional). You
answer questions about Nordvik Retail: 5 stores and a webshop selling electronics, fashion and beauty in Sweden.
Data: orders 2026-01-01 to 2026-06-30, amounts in SEK excl. VAT. Business definitions: GitHub repository
dediggibyte/genie_bootcamp, folder ecom/context/retail/ (index ecom/context/2026-10-27-glossary.csv).

WHO ANSWERS WHAT
- Nordvik Retail Analyst (you): products, brands, stores, webshop, loyalty customers, sales, margin, returns.
- Nordvik Mobility Analyst: cars, vans, trucks, dealers, workshop visits. Nordvik Connect Analyst: mobile, fibre,
  TV / streaming subscriptions, invoices, usage. If a question belongs to another agent, say which one.

DEFINITIONS (use retail.sales_metrics and retail.return_metrics)
- Net revenue = SUM(quantity * unit_price_sek - discount_sek) of COMPLETED orders = MEASURE(net_revenue_sek).
  Cancelled orders are not sales and not in fact_sales. Do not subtract refunds from revenue.
- Orders = distinct completed orders (MEASURE(order_count)). Average order value = net revenue / orders - a ratio of
  sums, never AVG over lines.
- Gross margin % = (net revenue - units * unit_cost_sek) / net revenue * 100. unit_cost_sek is confidential and
  masked (NULL) for non cost readers: then say the margin is not visible to the user, never show 0.
- Return rate % = returned units / units sold * 100, by ORDER month (MEASURE(return_rate_pct) in sales_metrics).
  Return reasons and refunds by return month: retail.return_metrics.
- Regions: STO (Stockholm City, Kista), GOT (Göteborg Nordstan, Frölunda), MAL (Malmö), ONLINE (webshop).
  "Göteborg" means region GOT; "webshop" / "online" means channel = 'online' (= region ONLINE).
- Categories: electronics, fashion, beauty. Åhléns and H&M are fashion BRANDS, not stores.
- "This year" / "H1" = 2026-01-01 to 2026-06-30 (all data). Months: order_month (first day of month).

""" + COMMON_RULES,
        "sample_questions": [
            ("sq_rev_month", "What was net revenue and average order value by month?"),
            ("sq_margin_cat", "Which product category has the highest gross margin?"),
            ("sq_returns", "What are the most common return reasons and how much did we refund?"),
            ("sq_channel", "How does the webshop compare with the stores?"),
        ],
        "examples": [
            ("ex_rev_month", "Show net revenue, orders and average order value by month.", """
SELECT order_month,
       MEASURE(net_revenue_sek) AS net_revenue_sek,
       MEASURE(order_count) AS orders,
       MEASURE(average_order_value_sek) AS average_order_value_sek
FROM __CATALOG__.retail.sales_metrics
GROUP BY ALL
ORDER BY order_month""", "Revenue, orders and AOV over time: retail.sales_metrics by order_month."),
            ("ex_margin_brand", "What is the gross margin by brand?", """
SELECT brand_name,
       MEASURE(net_revenue_sek) AS net_revenue_sek,
       MEASURE(gross_margin_sek) AS gross_margin_sek,
       MEASURE(gross_margin_pct) AS gross_margin_pct
FROM __CATALOG__.retail.sales_metrics
GROUP BY ALL
ORDER BY gross_margin_pct DESC""", "Margin questions: gross_margin_pct is a ratio of sums; NULL means cost is masked."),
            ("ex_return_rate_cat", "Return rate and refunds by category", """
SELECT category,
       MEASURE(units_sold) AS units_sold,
       MEASURE(returned_units) AS returned_units,
       MEASURE(return_rate_pct) AS return_rate_pct,
       MEASURE(refund_amount_sek) AS refund_amount_sek
FROM __CATALOG__.retail.sales_metrics
GROUP BY ALL
ORDER BY return_rate_pct DESC""", "Return rate = returned units / units sold by order month, from sales_metrics."),
            ("ex_reasons", "Why do customers return goods?", """
SELECT reason,
       MEASURE(return_count) AS returns,
       MEASURE(refund_amount_sek) AS refund_amount_sek
FROM __CATALOG__.retail.return_metrics
GROUP BY ALL
ORDER BY returns DESC""", "Return reasons and refunds: retail.return_metrics."),
            ("ex_region_channel", "Net revenue and orders by region and channel", """
SELECT store_region, channel,
       MEASURE(net_revenue_sek) AS net_revenue_sek,
       MEASURE(order_count) AS orders
FROM __CATALOG__.retail.sales_metrics
GROUP BY ALL
ORDER BY net_revenue_sek DESC""", "Regions are STO, GOT, MAL, ONLINE; channel is store or online."),
        ],
        "snippets": {
            "measures": [("sn_net_revenue", "net_revenue_sek", "Net revenue (SEK)", "SUM(fact_sales.net_revenue_sek)",
                          ["revenue", "sales"])],
            "filters": [("sn_webshop", "Webshop orders", "fact_sales.channel = 'online'", ["online", "e-commerce"]),
                        ("sn_beauty", "Beauty products", "dim_product.category = 'beauty'", ["perfume", "fragrance"])],
            "expressions": [("sn_order_month", "order_month", "Order month", "DATE_TRUNC('MONTH', fact_sales.order_date)",
                             ["month"])],
        },
        "columns": {
            "retail.dim_product": ["brand_name", "category", "subcategory", "product_name"],
            "retail.dim_store": ["store_name", "city", "region_code", "channel"],
            "retail.dim_customer": ["city", "loyalty_tier"],
            "retail.fact_sales": ["store_region", "channel", "payment_method"],
            "retail.fact_returns": ["reason", "store_region"],
            "retail.sales_metrics": ["store_region", "channel", "store_name", "brand_name", "category", "subcategory",
                                     "product_name", "payment_method", "loyalty_tier"],
            "retail.return_metrics": ["reason", "store_region", "channel", "brand_name", "category", "product_name"],
        },
        "exclude": {"retail.dim_customer": ["email", "phone"]},
        "benchmarks": [
            ("bm_total_rev", "What was our total net revenue in the first half of 2026?", """
SELECT MEASURE(net_revenue_sek) AS net_revenue_sek
FROM __CATALOG__.retail.sales_metrics""", "retail.total.net_revenue_sek", False),
            ("bm_aov_got", "What is the average order value in Göteborg?", """
SELECT MEASURE(average_order_value_sek) AS average_order_value_sek
FROM __CATALOG__.retail.sales_metrics
WHERE store_region = 'GOT'""", "retail.by_region.GOT.average_order_value_sek", True),
            ("bm_return_rate", "What is our return rate?", """
SELECT MEASURE(return_rate_pct) AS return_rate_pct
FROM __CATALOG__.retail.sales_metrics""", "retail.total.return_rate_pct", True),
            ("bm_top_brand", "Which brand brought in the most net revenue?", """
SELECT brand_name, MEASURE(net_revenue_sek) AS net_revenue_sek
FROM __CATALOG__.retail.sales_metrics
GROUP BY ALL
ORDER BY net_revenue_sek DESC
LIMIT 1""", "retail.top_brand_by_revenue", False),
            ("bm_beauty_margin", "What is the gross margin percentage for beauty products?", """
SELECT MEASURE(gross_margin_pct) AS gross_margin_pct
FROM __CATALOG__.retail.sales_metrics
WHERE category = 'beauty'""", "retail.by_category.beauty.gross_margin_pct", False),
            ("bm_webshop_orders", "How many orders did the webshop take?", """
SELECT MEASURE(order_count) AS orders
FROM __CATALOG__.retail.sales_metrics
WHERE channel = 'online'""", "retail.by_channel.online.orders", True),
        ],
    },
    "mobility": {
        "instruction": """You are the Nordvik Mobility Analyst - one of three Genie Agents of Nordvik Group (fictional). You
answer questions about Nordvik Mobility: new-vehicle sales (cars, vans, trucks) at 5 dealers and a truck centre, and
aftersales service in their workshops. Data: 2026-01-01 to 2026-06-30, amounts in SEK excl. VAT. Business
definitions: GitHub repository dediggibyte/genie_bootcamp, folder ecom/context/mobility/.

WHO ANSWERS WHAT
- Nordvik Mobility Analyst (you): vehicle models, dealers, vehicle sales, EV share, workshop visits, warranty.
- Nordvik Retail Analyst: stores, webshop, electronics / fashion / beauty sales. Nordvik Connect Analyst: telecom
  plans, subscriptions, invoices, usage. If a question belongs to another agent, say which one.

DEFINITIONS (use mobility.vehicle_sales_metrics and mobility.service_metrics)
- Vehicles sold = MEASURE(units_sold) (one row per vehicle). Vehicle revenue = SUM(sale_price_sek - discount_sek)
  = MEASURE(vehicle_revenue_sek). Average sale price = vehicle revenue / vehicles sold - compare it within one
  vehicle_type (trucks cost 2-4 MSEK).
- EV share % = battery electric vehicles (powertrain = 'ev') / vehicles sold * 100. Hybrids are NOT EVs.
- Service revenue = SUM(billed_amount_sek): labour + parts billed to the customer; warranty work is billed 0 (paid
  by the manufacturer). Warranty share % = warranty visits / visits * 100.
- Regions: STO (Bromma, Täby, truck centre Södertälje), GOT (Hisingen), MAL (Bulltofta), UME (Umeå - no workshop).
  Trucks are sold and serviced only by Nordvik Truck Center Södertälje.
- Model = brand + model name, e.g. 'Volvo EX30'. Customer types: private, fleet.
- "This year" / "H1" = 2026-01-01 to 2026-06-30 (all data). Months: sale_month / visit_month.

""" + COMMON_RULES,
        "sample_questions": [
            ("sq_units_month", "How many vehicles did we sell per month, and what share were EVs?"),
            ("sq_asp_type", "What is the average sale price by vehicle type?"),
            ("sq_service_type", "Which service types bring in the most service revenue?"),
            ("sq_dealer", "Which dealer sold the most vehicles?"),
        ],
        "examples": [
            ("ex_units_ev_month", "Vehicles sold, revenue and EV share by month", """
SELECT sale_month,
       MEASURE(units_sold) AS units_sold,
       MEASURE(vehicle_revenue_sek) AS vehicle_revenue_sek,
       MEASURE(ev_share_pct) AS ev_share_pct
FROM __CATALOG__.mobility.vehicle_sales_metrics
GROUP BY ALL
ORDER BY sale_month""", "Sales over time: mobility.vehicle_sales_metrics by sale_month."),
            ("ex_asp_brand", "Average sale price by brand for cars", """
SELECT brand,
       MEASURE(units_sold) AS units_sold,
       MEASURE(average_sale_price_sek) AS average_sale_price_sek
FROM __CATALOG__.mobility.vehicle_sales_metrics
WHERE vehicle_type = 'car'
GROUP BY ALL
ORDER BY average_sale_price_sek DESC""", "Average prices: always within one vehicle_type."),
            ("ex_ev_region", "EV share by region", """
SELECT dealer_region,
       MEASURE(units_sold) AS units_sold,
       MEASURE(ev_units) AS ev_units,
       MEASURE(ev_share_pct) AS ev_share_pct
FROM __CATALOG__.mobility.vehicle_sales_metrics
GROUP BY ALL
ORDER BY ev_share_pct DESC""", "EV share counts battery electric vehicles only (powertrain = 'ev')."),
            ("ex_service_type", "Service visits, revenue and labour hours by service type", """
SELECT service_type,
       MEASURE(service_visits) AS service_visits,
       MEASURE(service_revenue_sek) AS service_revenue_sek,
       MEASURE(labour_hours) AS labour_hours
FROM __CATALOG__.mobility.service_metrics
GROUP BY ALL
ORDER BY service_revenue_sek DESC""", "Aftersales: mobility.service_metrics; warranty work is billed 0."),
            ("ex_warranty_brand", "Warranty share by vehicle brand", """
SELECT brand,
       MEASURE(service_visits) AS service_visits,
       MEASURE(warranty_share_pct) AS warranty_share_pct
FROM __CATALOG__.mobility.service_metrics
GROUP BY ALL
ORDER BY warranty_share_pct DESC""", "Warranty share = warranty visits / visits."),
        ],
        "snippets": {
            "measures": [("sn_vehicle_revenue", "vehicle_revenue_sek", "Vehicle revenue (SEK)",
                          "SUM(fact_vehicle_sales.net_sale_price_sek)", ["revenue", "sales value"])],
            "filters": [("sn_ev", "Battery electric vehicles", "dim_vehicle_model.powertrain = 'ev'", ["EV", "electric"]),
                        ("sn_trucks", "Trucks", "dim_vehicle_model.vehicle_type = 'truck'", ["heavy vehicles", "lorries"])],
            "expressions": [("sn_model", "model", "Model", "CONCAT(dim_vehicle_model.brand, ' ', dim_vehicle_model.model_name)",
                             ["vehicle model", "car model"])],
        },
        "columns": {
            "mobility.dim_vehicle_model": ["brand", "model_name", "vehicle_type", "body_type", "powertrain"],
            "mobility.dim_dealer": ["dealer_name", "city", "region_code"],
            "mobility.dim_customer": ["customer_type", "city"],
            "mobility.fact_vehicle_sales": ["dealer_region", "financing"],
            "mobility.fact_service_visits": ["dealer_region", "service_type"],
            "mobility.vehicle_sales_metrics": ["dealer_region", "dealer_name", "brand", "model", "vehicle_type",
                                               "powertrain", "customer_type", "financing"],
            "mobility.service_metrics": ["dealer_region", "dealer_name", "service_type", "warranty", "brand",
                                         "vehicle_type", "powertrain"],
        },
        "exclude": {"mobility.dim_customer": ["email", "phone"]},
        "benchmarks": [
            ("bm_units_total", "How many vehicles did we sell in the first half of 2026?", """
SELECT MEASURE(units_sold) AS units_sold
FROM __CATALOG__.mobility.vehicle_sales_metrics""", "mobility.sales_total.units_sold", False),
            ("bm_truck_ev", "What share of the trucks we sold were electric?", """
SELECT MEASURE(ev_share_pct) AS ev_share_pct
FROM __CATALOG__.mobility.vehicle_sales_metrics
WHERE vehicle_type = 'truck'""", "mobility.sales_by_vehicle_type.truck.ev_share_pct", True),
            ("bm_car_asp", "What is the average sale price of a car?", """
SELECT MEASURE(average_sale_price_sek) AS average_sale_price_sek
FROM __CATALOG__.mobility.vehicle_sales_metrics
WHERE vehicle_type = 'car'""", "mobility.sales_by_vehicle_type.car.average_sale_price_sek", True),
            ("bm_service_sto", "How much service revenue did the Stockholm region earn?", """
SELECT MEASURE(service_revenue_sek) AS service_revenue_sek
FROM __CATALOG__.mobility.service_metrics
WHERE dealer_region = 'STO'""", "mobility.service_by_region.STO.service_revenue_sek", False),
            ("bm_warranty", "What share of workshop visits were warranty work?", """
SELECT MEASURE(warranty_share_pct) AS warranty_share_pct
FROM __CATALOG__.mobility.service_metrics""", "mobility.service_total.warranty_share_pct", False),
            ("bm_top_model", "Which model sold the most units?", """
SELECT model, MEASURE(units_sold) AS units_sold
FROM __CATALOG__.mobility.vehicle_sales_metrics
GROUP BY ALL
ORDER BY units_sold DESC, model
LIMIT 1""", "mobility.top_model_by_units", False),
        ],
    },
    "telecom": {
        "instruction": """You are the Nordvik Connect Analyst - one of three Genie Agents of Nordvik Group (fictional). You
answer questions about Nordvik Connect, a mobile, fibre and TV / streaming operator for consumers and businesses.
Data: billing and usage months 2026-05 and 2026-06, amounts in SEK excl. VAT. Business definitions: GitHub
repository dediggibyte/genie_bootcamp, folder ecom/context/telecom/.

WHO ANSWERS WHAT
- Nordvik Connect Analyst (you): plans, streaming add-ons, customers, subscriptions, invoices, ARPU, usage.
- Nordvik Retail Analyst: stores, webshop, electronics / fashion / beauty. Nordvik Mobility Analyst: cars, vans,
  trucks, workshops. If a question belongs to another agent, say which one.

DEFINITIONS (use telecom.billing_metrics and telecom.usage_metrics)
- Billed revenue = SUM(amount_excl_vat_sek) = MEASURE(billed_revenue_sek). VAT is not revenue.
- ARPU = billed revenue / distinct billed subscriptions PER MONTH: always group by (or filter) billing_month.
- Overdue = due date passed and not paid (payment_status = 'overdue'); open = not yet due. June invoices are
  paid or open. Paid share % = paid invoices / invoices * 100.
- Active subscription = status 'active' (dim_subscription). Two subscriptions were cancelled on 2026-05-31.
- Segments: consumer, business (customer_segment). Plan types: mobile, broadband, tv_streaming, bundle.
- Data per subscription = data GB / subscriptions with usage, per usage_month.
- "Last month" / "latest month" = June 2026 (2026-06-01). Months are first-of-month dates.

""" + COMMON_RULES,
        "sample_questions": [
            ("sq_arpu_month", "What was billed revenue and ARPU per month?"),
            ("sq_overdue_seg", "How much is overdue per customer segment?"),
            ("sq_usage_plan", "How much data and streaming do customers use per plan type?"),
            ("sq_subs", "How many active subscriptions do we have per plan type?"),
        ],
        "examples": [
            ("ex_billing_month", "Billed revenue, billed subscriptions and ARPU by month", """
SELECT billing_month,
       MEASURE(billed_revenue_sek) AS billed_revenue_sek,
       MEASURE(billed_subscriptions) AS billed_subscriptions,
       MEASURE(arpu_sek) AS arpu_sek
FROM __CATALOG__.telecom.billing_metrics
GROUP BY ALL
ORDER BY billing_month""", "ARPU is monthly: always group by or filter billing_month."),
            ("ex_arpu_segment", "ARPU by customer segment and plan type in June", """
SELECT customer_segment, plan_type,
       MEASURE(billed_revenue_sek) AS billed_revenue_sek,
       MEASURE(arpu_sek) AS arpu_sek
FROM __CATALOG__.telecom.billing_metrics
WHERE billing_month = DATE'2026-06-01'
GROUP BY ALL
ORDER BY customer_segment, arpu_sek DESC""", "Latest month = June 2026."),
            ("ex_payment_status", "Overdue and open amounts and paid share by billing month", """
SELECT billing_month,
       MEASURE(overdue_amount_sek) AS overdue_amount_sek,
       MEASURE(open_amount_sek) AS open_amount_sek,
       MEASURE(paid_share_pct) AS paid_share_pct
FROM __CATALOG__.telecom.billing_metrics
GROUP BY ALL
ORDER BY billing_month""", "Overdue = past due and unpaid; open = not yet due."),
            ("ex_usage_plan", "Data, voice and streaming usage by plan type per month", """
SELECT usage_month, plan_type,
       MEASURE(data_gb) AS data_gb,
       MEASURE(avg_data_gb_per_subscription) AS avg_data_gb_per_subscription,
       MEASURE(voice_minutes) AS voice_minutes,
       MEASURE(streaming_hours) AS streaming_hours
FROM __CATALOG__.telecom.usage_metrics
GROUP BY ALL
ORDER BY usage_month, plan_type""", "Usage: telecom.usage_metrics; averages per usage_month."),
            ("ex_active_subs", "Active subscriptions by plan type", """
SELECT p.plan_type, COUNT(*) AS active_subscriptions
FROM __CATALOG__.telecom.dim_subscription s
JOIN __CATALOG__.telecom.dim_plan p ON p.plan_id = s.plan_id
WHERE s.status = 'active'
GROUP BY ALL
ORDER BY active_subscriptions DESC""", "Current subscription counts come from dim_subscription (status = 'active')."),
        ],
        "snippets": {
            "measures": [("sn_billed_revenue", "billed_revenue_sek", "Billed revenue (SEK)",
                          "SUM(fact_billing.amount_excl_vat_sek)", ["revenue", "billing"])],
            "filters": [("sn_overdue", "Overdue invoices", "fact_billing.payment_status = 'overdue'", ["overdue", "late"]),
                        ("sn_business", "Business customers", "fact_billing.customer_segment = 'business'", ["B2B", "företag"])],
            "expressions": [("sn_incl_vat", "amount_incl_vat_sek", "Amount incl. VAT",
                             "fact_billing.amount_excl_vat_sek + fact_billing.vat_sek", ["gross amount", "with VAT"])],
        },
        "columns": {
            "telecom.dim_plan": ["plan_name", "plan_type", "segment", "included_streaming"],
            "telecom.dim_customer": ["customer_segment", "city"],
            "telecom.dim_subscription": ["customer_segment", "status", "sales_channel"],
            "telecom.fact_billing": ["customer_segment", "payment_status"],
            "telecom.fact_usage": ["customer_segment"],
            "telecom.billing_metrics": ["customer_segment", "plan_type", "plan_name", "has_streaming", "sales_channel",
                                        "payment_status"],
            "telecom.usage_metrics": ["customer_segment", "plan_type", "plan_name", "has_streaming"],
        },
        "exclude": {"telecom.dim_customer": ["email", "phone"]},
        "benchmarks": [
            ("bm_arpu_june", "What was ARPU last month?", """
SELECT MEASURE(arpu_sek) AS arpu_sek
FROM __CATALOG__.telecom.billing_metrics
WHERE billing_month = DATE'2026-06-01'""", "telecom.billing_by_month.2026-06.arpu_sek", True),
            ("bm_rev_may", "How much did we bill in May 2026?", """
SELECT MEASURE(billed_revenue_sek) AS billed_revenue_sek
FROM __CATALOG__.telecom.billing_metrics
WHERE billing_month = DATE'2026-05-01'""", "telecom.billing_by_month.2026-05.billed_revenue_sek", False),
            ("bm_overdue_may", "What is the overdue amount of the May invoices?", """
SELECT MEASURE(overdue_amount_sek) AS overdue_amount_sek
FROM __CATALOG__.telecom.billing_metrics
WHERE billing_month = DATE'2026-05-01'""", "telecom.billing_by_month.2026-05.overdue_amount_sek", False),
            ("bm_paid_business", "What share of business invoices for June has been paid?", """
SELECT MEASURE(paid_share_pct) AS paid_share_pct
FROM __CATALOG__.telecom.billing_metrics
WHERE billing_month = DATE'2026-06-01' AND customer_segment = 'business'""",
             "telecom.billing_by_segment_june.business.paid_share_pct", False),
            ("bm_data_june", "How much data did a subscription use on average in June?", """
SELECT MEASURE(avg_data_gb_per_subscription) AS avg_data_gb_per_subscription
FROM __CATALOG__.telecom.usage_metrics
WHERE usage_month = DATE'2026-06-01'""", "telecom.usage_by_month.2026-06.avg_data_gb_per_subscription", True),
            ("bm_active", "How many active subscriptions do we have?", """
SELECT COUNT(*) AS active_subscriptions
FROM __CATALOG__.telecom.dim_subscription
WHERE status = 'active'""", "telecom.active_subscriptions_now", True),
        ],
    },
}

# =============================================================================================================
# Builders
# =============================================================================================================


def subdomain_objects(domain):
    """{subdomain key: [schema.object, ...]} from the ecom_subdomain tags (config/tags.json)."""
    out = {}
    for obj, entry in sorted(TAGS.items()):
        if obj.split(".")[0] == domain:
            out.setdefault(entry["tags"]["ecom_subdomain"], []).append(obj)
    return out


def front_matter(fields):
    out = ["---"]
    for k, v in fields:
        if isinstance(v, list):
            out.append("%s:" % k)
            out += ["  - %s" % (json.dumps(x, ensure_ascii=False) if any(ch in x for ch in ":#'\"") else x) for x in v]
        else:
            out.append("%s: %s" % (k, json.dumps(v, ensure_ascii=False) if any(ch in v for ch in ":#'\"") else v))
    return "\n".join(out + ["---", ""])


def page_path(domain, key):
    return "%s/context/%s/pages/%s-%s.md" % (ECOM, domain, DATE, key.replace("_", "-"))


def build_context(files):
    glossary = []
    for domain, d in DOMAINS.items():
        objs = subdomain_objects(domain)
        if set(objs) != set(d["subdomains"]):
            sys.exit("%s: subdomains of tags.json %s != spec %s" % (domain, sorted(objs), sorted(d["subdomains"])))
        terms = TERMS[domain]
        # _domain.md
        rows = "\n".join("| %s | `%s/%s` | %s | %s |" % (name, d["domain_tag"], name, desc, ", ".join("`%s`" % o for o in objs[k]))
                         for k, (name, desc) in d["subdomains"].items())
        body = """# %s (%s)

%s

* **Governed tag / UC domain:** `%s` - applied to the gold schema `<catalog>.%s` by notebook
  `notebooks/%s-05-context-common.py` (run through `05%s`), which can also create the domain itself.
* **Data:** %s. Amounts in SEK excl. VAT. All data is synthetic.
* **Genie Agent:** *%s* (`genie/%s-%s-agent.json`, created by notebook 04).

## Subdomains

| subdomain | governed tag | what it holds | gold objects |
|---|---|---|---|
%s

## Business terms

| term | subdomain | definition |
|---|---|---|
%s
""" % (d["name"], d["unit"], d["description"], d["domain_tag"], domain, DATE, "abc"[list(DOMAINS).index(domain)],
       d["period"], AGENTS[domain], DATE, domain, rows,
       "\n".join("| [%s](pages/%s) | %s | %s |" % (t["title"], os.path.basename(page_path(domain, t["key"])),
                                                    d["subdomains"][t["sub"]][0], t["desc"]) for t in terms))
        files["%s/context/%s/_domain.md" % (ECOM, domain)] = front_matter([
            ("title", d["name"]), ("domain", d["name"]), ("domain_tag", d["domain_tag"]), ("business_unit", d["unit"]),
            ("subtitle", d["subtitle"]), ("description", d["description"]), ("business_owner", d["business_owner"]),
            ("technical_owner", d["technical_owner"]), ("schema", "<catalog>.%s" % domain), ("genie_agent", AGENTS[domain]),
            ("sources", [SOURCE_NOTE])]) + "\n" + body
        # _subdomain.md
        for key, (name, desc) in d["subdomains"].items():
            sub_terms = [t for t in terms if t["sub"] == key]
            body = """# %s (%s)

%s

* **Governed tag / UC subdomain:** `%s/%s` - applied to the objects below by notebook 05%s.
* **Business terms:** %s

## Tables and metric views

| object | type |
|---|---|
%s
""" % (name, d["name"], desc, d["domain_tag"], name, "abc"[list(DOMAINS).index(domain)],
       ", ".join("[%s](../pages/%s)" % (t["title"], os.path.basename(page_path(domain, t["key"]))) for t in sub_terms) or "-",
       "\n".join("| `<catalog>.%s` | %s |" % (o, TAGS[o]["tags"]["ecom_table_type"].replace("_", " ")) for o in objs[key]))
            files["%s/context/%s/%s/_subdomain.md" % (ECOM, domain, key)] = front_matter([
                ("title", name), ("domain", d["name"]), ("subdomain", name), ("subdomain_key", key),
                ("subdomain_tag", "%s/%s" % (d["domain_tag"], name)), ("description", desc),
                ("objects", ["<catalog>.%s" % o for o in objs[key]])]) + "\n" + body
        # term pages
        for t in terms:
            mv = t["mv"]
            if t["measure"] not in MV_MEASURES[mv]:
                sys.exit("%s: measure %s not in %s" % (t["key"], t["measure"], mv))
            value = ref(t["value"][0])
            related = [x for x in terms if x["key"] in t["related"]]
            sql = t.get("sql") or "SELECT MEASURE(%s) AS %s\nFROM <catalog>.%s%s" % (
                t["measure"], t["measure"], mv, ("\nWHERE " + t["where"]) if t.get("where") else "")
            body = """# %s

## Definition

%s

## How to calculate

Use the governed metric view `<catalog>.%s` (measure `%s`) - Genie, dashboards and SQL then all agree.
This query returns the reference value below:

```sql
%s
```

For a breakdown, select a dimension of the view (e.g. month, region) next to the measure and add `GROUP BY ALL`.

## Reference value

**%s** (%s, all data, for a user who may see every row; from `data/%s-expected-answers.json`).

## Common wrong answers

%s

## Related terms

%s

## Example questions

%s
""" % (t["title"], t["definition"], mv, t["measure"], sql, fmt(value, t["value"][1]), t["value"][2], DATE,
       "\n".join("* " + p for p in t["pitfalls"]),
       "\n".join("* [%s](%s)" % (r["title"], os.path.basename(page_path(domain, r["key"]))) for r in related) or "-",
       "\n".join("* " + q for q in t["questions"]))
            rel = page_path(domain, t["key"])
            files[rel] = front_matter([
                ("title", t["title"]), ("domain", d["name"]), ("subdomain", d["subdomains"][t["sub"]][0]),
                ("synonyms", t["syn"]), ("description", t["desc"]),
                ("related_assets", sorted({"<catalog>.%s" % mv} | {"<catalog>.%s" % o for o in objs[t["sub"]]})),
                ("sources", [SOURCE_NOTE])]) + "\n" + body
            glossary.append({"domain": d["name"], "domain_key": domain, "subdomain": d["subdomains"][t["sub"]][0],
                             "subdomain_key": t["sub"], "term": t["title"], "short_definition": t["desc"],
                             "metric_view": mv, "measure": t["measure"], "synonyms": "; ".join(t["syn"]),
                             "related_terms": "; ".join(r["title"] for r in related), "page_path": rel})
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(glossary[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(glossary)
    files["%s/context/%s-glossary.csv" % (ECOM, DATE)] = out.getvalue()


def build_space(domain):
    g = GENIE[domain]
    by_id = lambda xs: sorted(xs, key=lambda x: x["id"])  # noqa: E731
    sources = {"tables": [], "metric_views": []}
    for obj in sorted(set(g["columns"]) | {o for o in TAGS if o.startswith(domain + ".")}):
        is_mv = TAGS[obj]["type"] == "METRIC_VIEW"
        cols = MV_DIMS[obj] if is_mv else GOLD_COLS[obj]
        cfgs = []
        for c in g["columns"].get(obj, []):
            if c not in cols:
                sys.exit("%s: column %s not in %s" % (domain, c, obj))
            cfgs.append({"column_name": c, "enable_format_assistance": True, "enable_entity_matching": True})
        for c in g["exclude"].get(obj, []):
            if c not in cols:
                sys.exit("%s: column %s not in %s" % (domain, c, obj))
            cfgs.append({"column_name": c, "exclude": True})
        entry = {"identifier": "%s.%s" % (C, obj), "description": [TAGS[obj]["tags"]["ecom_subdomain"].replace("_", " ")
                                                                  .title() + " - " + DOMAINS[domain]["name"]]}
        if cfgs:
            entry["column_configs"] = sorted(cfgs, key=lambda c: c["column_name"])
        sources["metric_views" if is_mv else "tables"].append(entry)
    sn = g["snippets"]
    space = {
        "version": 2,
        "config": {"sample_questions": by_id([{"id": nid(domain + k), "question": [q]} for k, q in g["sample_questions"]])},
        "data_sources": {"tables": sorted(sources["tables"], key=lambda x: x["identifier"]),
                         "metric_views": sorted(sources["metric_views"], key=lambda x: x["identifier"])},
        "instructions": {
            "text_instructions": [{"id": nid(domain + ":text"), "content": lines(g["instruction"])}],
            "example_question_sqls": by_id([{"id": nid(domain + k), "question": [q], "sql": lines(s), "usage_guidance": [u]}
                                            for k, q, s, u in g["examples"]]),
            "join_specs": [],
            "sql_snippets": {
                "measures": by_id([{"id": nid(domain + k), "alias": a, "display_name": dn, "sql": [s], "synonyms": syn}
                                   for k, a, dn, s, syn in sn["measures"]]),
                "filters": by_id([{"id": nid(domain + k), "display_name": dn, "sql": [s], "synonyms": syn}
                                  for k, dn, s, syn in sn["filters"]]),
                "expressions": by_id([{"id": nid(domain + k), "alias": a, "display_name": dn, "sql": [s], "synonyms": syn}
                                      for k, a, dn, s, syn in sn["expressions"]]),
            },
        },
        "benchmarks": {"questions": by_id([{"id": nid(domain + k), "question": [q],
                                            "answer": [{"format": "SQL", "content": lines(s)}]}
                                           for k, q, s, _, _ in g["benchmarks"]])},
    }
    validate(domain, space)
    return space


def validate(domain, space):
    g = GENIE[domain]
    n_sources = len(space["data_sources"]["tables"]) + len(space["data_sources"]["metric_views"])
    assert n_sources <= 45, "%s: %d data sources" % (domain, n_sources)
    ins = space["instructions"]
    assert len(ins["text_instructions"]) == 1
    ins_ids = [x["id"] for x in ins["text_instructions"] + ins["example_question_sqls"] + ins["join_specs"]
               + ins["sql_snippets"]["measures"] + ins["sql_snippets"]["filters"] + ins["sql_snippets"]["expressions"]]
    q_ids = [x["id"] for x in space["config"]["sample_questions"] + space["benchmarks"]["questions"]]
    assert len(set(ins_ids)) == len(ins_ids), "instruction ids not unique"
    assert len(set(q_ids)) == len(q_ids), "question ids not unique"
    assert len("".join(ins["text_instructions"][0]["content"])) < 25000, "text instruction too long"
    examples = {x["question"][0] for x in ins["example_question_sqls"]}
    for b in space["benchmarks"]["questions"]:
        assert b["question"][0] not in examples, "benchmark question is also an example: %s" % b["question"][0]
    for x in ins["example_question_sqls"] + space["benchmarks"]["questions"]:
        sql = "".join(x.get("sql") or x["answer"][0]["content"])
        assert "SELECT *" not in sql.upper().replace("COUNT(*)", ""), "SELECT * in %s" % x["question"]
        for view in re.findall(r"__CATALOG__\.(\w+\.\w+)", sql):
            assert view in TAGS, "%s: unknown object %s" % (domain, view)
            if view in MV_MEASURES:
                for m in re.findall(r"MEASURE\((\w+)\)", sql):
                    assert m in MV_MEASURES[view], "%s: measure %s not in %s" % (domain, m, view)
    for k, q, s, path, _ in g["benchmarks"]:
        ref(path)   # the expected value exists


def build_genie(files):
    for domain in DOMAINS:
        space = build_space(domain)
        version = hashlib.md5(json.dumps(space, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        d = DOMAINS[domain]
        template = {
            "_notice": ["Genie Agent template of the ecom bootcamp (fictional Nordvik Group) - GENERATED by %s, do not edit "
                        "by hand. __CATALOG__ is replaced by your catalog in notebooks/%s-04-genie-agents.py." % (SCRIPT, DATE),
                        "Benchmarks test the agent and are never among the example SQLs; their expected values are in "
                        "data/%s-expected-answers.json." % DATE],
            "template_version": version,
            "domain": domain,
            "title": AGENTS[domain],
            "description": "%s analyst for %s (fictional Nordvik Group, %s). Answers from the %s gold tables and "
                           "metric views; definitions in ecom/context/%s/." % (d["name"], d["unit"], d["period"], domain, domain),
            "tricky_benchmark_ids": sorted(nid(domain + k) for k, _, _, _, tricky in GENIE[domain]["benchmarks"] if tricky),
            "serialized_space": space,
        }
        files["%s/genie/%s-%s-agent.json" % (ECOM, DATE, domain)] = json.dumps(template, indent=1, ensure_ascii=False) + "\n"


def build():
    files = {}
    build_context(files)
    build_genie(files)
    return files


def main(argv):
    check = "--check" in argv
    files = build()
    stale = []
    for rel, text in sorted(files.items()):
        path = os.path.join(ROOT, rel)
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if old == text:
            continue
        stale.append(rel)
        if not check:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
    print("%s: %d files (%d %s)" % (SCRIPT, len(files), len(stale), "stale" if check else "written"))
    for s in stale if check else []:
        print("  stale: " + s)
    return 1 if check and stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
