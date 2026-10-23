"""Synthetic data generator for the Genie Bootcamp (Fjällmark Consumer Goods AB).

The package turns the vendored Lakehouse Industry Data Model (Consumer Goods v2, MVM,
``tools/model/consumer_goods_v2_mvm.json``) into deterministic, story-consistent CSV
files, stored once: ``bootcamp/data/<domain>/<table>.csv`` (consumer, finance,
manufacturing) and ``full_model/data/<domain>/<table>.csv`` (the other 7 domains).

Modules
-------
model                 reads the model JSON (tables, columns, PKs, FKs, enums, regexes)
regexgen              produces strings that match the simple regexes used in the model
engine                generic, model-driven row generator (PK pools, FK draws, value
                      heuristics, temporal ordering) used for every table
world                 the fictional company: legal entities, FX, brands, SKUs, plants,
                      markets, VAT, loyalty tiers, calendars and seasonality
curated_product       brand / product_category / category / sku
curated_product_specs product specifications derived from the SKUs: material, hierarchy,
                      formulation (+ ingredients), packaging_spec, label_spec, gtin_registry,
                      product_bom, bom_line
curated_masters       sales.trade_account and distribution.distribution_facility
curated_generic       coherence hooks for a few engine-generated tables (retail stores, POS
                      records, account contacts, shipments)
curated_finance       finance masters and transactions (AR/AP, GL, costing), the financial plan
                      (revenue, cost ratios, demand per plant) and intercompany supplies
curated_manufacturing plants, lines, orders, confirmations, batches, yields
curated_consumer      shoppers, loyalty, consent, subscriptions, DTC orders
dq                    deterministic raw data-quality injection (documented)
writer                CSV formatting (RFC-4180, UTF-8, LF)
build                 orchestration used by ``tools/generate_data.py``
readme                renders ``bootcamp/data/README.md`` and ``full_model/data/README.md``

All data is synthetic. Every person, company, retailer, carrier, equipment vendor and
address is fictional;
e-mail addresses use the reserved ``example.com`` domain and phone numbers use
obviously fake ``000`` blocks.
"""

GENERATOR_VERSION = "1.1.0"
