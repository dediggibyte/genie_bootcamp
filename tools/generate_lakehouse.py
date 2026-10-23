#!/usr/bin/env python3
"""Generate the bootcamp lakehouse code from the Lakehouse Industry Data Model.

Source of truth: ``tools/model/consumer_goods_v2_mvm.json`` - the Databricks "Lakehouse Industry
Data Model - Consumer Goods v2 MVM" (Databricks license, see tools/model/LICENSE.md + NOTICE.md).

One run (re)writes every generated file of BOTH bundles; the output is deterministic (same model ->
same bytes). Two self-contained bundle folders are written:

  bootcamp/   the hands-on lab - ONLY the bootcamp domains (consumer, finance, manufacturing, 36 tables)
    pipeline/<domain>/01_bronze.sql            bronze streaming tables (Auto Loader on the landing volume)
    pipeline/<domain>/02_silver.sql            silver materialized views (typed, cleaned, deduplicated,
                                               data-quality expectations)
    pipeline/<domain>/03_gold.sql              gold materialized views = the exact industry tables with
                                               comments and PRIMARY KEY; FOREIGN KEYs only to tables of the
                                               bootcamp domains (the others are not built by this bundle)
    metric_views/industry/<domain>.sql         the model's metric views, renamed to
                                               ${catalog}.<domain>.<table>_metrics
    model_tags/<domain>.json                   the model's dbx_* tags for schema / tables / columns

  full_model/ the complete industry model - all 10 domains, 116 tables
    src/pipeline/<domain>/01_bronze.sql, 02_silver.sql, 03_gold.sql (ALL model FOREIGN KEYs)
    src/metric_views/industry/<domain>.sql     (79 metric views)
    src/model_tags/<domain>.json

  both: LICENSE.md and NOTICE.md (verbatim copies of tools/model/LICENSE.md and NOTICE.md)

--check also reports files in the generated folders that the generator would not write (e.g. a
domain folder that is no longer in scope).

Usage (from the repo root, standard library only):

  python3 -I tools/generate_lakehouse.py           # write all files
  python3 -I tools/generate_lakehouse.py --check   # exit 1 if a generated file is missing or stale
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(ROOT, "tools", "model", "consumer_goods_v2_mvm.json")
SCRIPT = "tools/generate_lakehouse.py"

# Domains built by the bootcamp bundle (bootcamp/, the hands-on lab and its one Genie Agent). Product
# names and brands needed by the Genie questions are denormalised in these domains
# (consumer.dtc_order_line.product_name / brand_code, finance.profit_center.brand_code, ...).
BOOTCAMP_DOMAINS = ("consumer", "finance", "manufacturing")

# Output folders (relative to the repository root) of the two bundles.
BOOTCAMP_DIR = "bootcamp"
FULL_DIR = "full_model"
BOOTCAMP_PATHS = {"pipeline": "bootcamp/pipeline", "metric_views": "bootcamp/metric_views/industry",
                  "model_tags": "bootcamp/model_tags",
                  "mv_notebook": "notebooks/job_tasks/02a_create_metric_views.py",
                  "tag_notebook": "notebooks/job_tasks/02b_apply_model_tags.py"}
FULL_PATHS = {"pipeline": "full_model/src/pipeline", "metric_views": "full_model/src/metric_views/industry",
              "model_tags": "full_model/src/model_tags",
              "mv_notebook": "notebooks/job_tasks/02a_create_metric_views.py",
              "tag_notebook": "notebooks/job_tasks/02b_apply_model_tags.py"}

# Copied verbatim from tools/model/ into bootcamp/ and full_model/ (--check verifies they are identical).
LICENSE_FILES = ("LICENSE.md", "NOTICE.md")

# The model's catalog name in its metric-view SQL; replaced by the ${catalog} placeholder.
MODEL_CATALOG = "vibe_consumer_goods_v1"

# Self-referencing foreign keys (e.g. finance.company_code.parent_company_code_id -> company_code) are
# rejected by Lakeflow pipelines: "[TABLE_MATERIALIZATION_CYCLIC_FOREIGN_KEY_DEPENDENCY] ... detected a
# cyclic chain of foreign key constraints" (tested live 2026-10-22). They are therefore left out of the
# gold DDL and listed in a comment above each affected table. (The model's other FKs form no cycles.)
INCLUDE_SELF_REFERENCING_FKS = False

# Gold build order inside the pipeline (see the header of the generated 03_gold*.sql files):
#   "chain"      - all gold tables one after another in foreign-key order
#   "fk_targets" - each gold table waits only for the tables its foreign keys reference
GOLD_BUILD_ORDER = "fk_targets"

# Silver keeps the latest version of a record: the first of these TIMESTAMP columns that exists
# (else any TIMESTAMP column whose name contains "updated"/"modified") orders the duplicates.
UPDATED_COLUMN_PREFERENCE = (
    "updated_timestamp", "last_updated_timestamp", "last_modified_timestamp", "modified_timestamp",
    "record_audit_updated", "record_updated_timestamp", "cost_estimate_modified_timestamp",
)

# Warn-level expectations ("value must not be negative") on the focus tables of the Genie domains.
# Violations are counted in the pipeline event log but the rows are kept.
WARN_NON_NEGATIVE = {
    "consumer.dtc_order": ["subtotal_amount", "discount_amount", "shipping_amount", "tax_amount",
                           "order_total_amount"],
    "consumer.dtc_order_line": ["unit_price", "line_subtotal", "line_discount_amount", "line_net_amount",
                                "tax_amount", "line_total_amount", "quantity_shipped", "quantity_cancelled"],
    "consumer.loyalty_transaction": ["qualifying_spend_amount"],
    "finance.ar_invoice": ["gross_amount", "net_amount", "tax_amount", "total_amount", "amount_received"],
    "finance.ar_payment": ["payment_amount", "applied_amount"],
    "finance.ap_invoice": ["gross_amount", "net_amount", "tax_amount"],
    "finance.ap_payment": ["payment_amount"],
    "finance.cogs_allocation": ["total_cost_amount"],
    "manufacturing.production_order": ["order_quantity", "confirmed_quantity", "scrap_quantity",
                                       "planned_cost", "actual_cost"],
    "manufacturing.production_confirmation": ["confirmed_yield_quantity", "confirmed_scrap_quantity"],
    "manufacturing.yield_record": ["input_quantity", "output_quantity", "scrap_quantity"],
    "manufacturing.batch_record": ["scrap_quantity", "rework_quantity"],
}
# Drop-level expectations: rows violating these never reach silver/gold.
DROP_NON_NEGATIVE = {
    "consumer.dtc_order_line": ["quantity_ordered"],   # reversal lines from a legacy feed
}

# Fixes applied to the model's metric views: view_name -> (new owner table, new source table).
METRIC_VIEW_FIXES = {
    # upstream bug: the return-order metrics read sales.order instead of sales.return_order
    "sales_return_order": ("return_order", "sales.return_order"),
}

BOOL_TRUE = ("true", "t", "yes", "y", "1")
BOOL_FALSE = ("false", "f", "no", "n", "0")


# ---------------------------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------------------------

def load_model(path=MODEL_PATH):
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return raw["model"]


def is_enum(value_regex):
    """A value_regex that is a plain pipe-list of allowed values (not a real regex)."""
    v = value_regex or ""
    return bool(v) and not (v.startswith("^") or "[" in v or "\\" in v or "(" in v)


def base_type(sql_type):
    return sql_type.split("(")[0].strip().upper()


def updated_column(product):
    names = [a["column_name"] for a in product["attributes"] if base_type(a["type"]) == "TIMESTAMP"]
    for pref in UPDATED_COLUMN_PREFERENCE:
        if pref in names:
            return pref
    for n in names:
        if "updated" in n or "modified" in n:
            return n
    return None


def column_comment(attr):
    text = (attr.get("description") or "").strip()
    if attr.get("value_regex"):
        sep = " " if text.endswith(".") else ". "
        text = "%s%sValid values are `%s`" % (text, sep, attr["value_regex"])
    return text


# ---------------------------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------------------------

def q(name):
    """Back-quote an identifier (column/table names such as `order` or `level` are keywords)."""
    return "`%s`" % name.replace("`", "``")


def lit(text):
    """SQL string literal: Databricks SQL treats backslash as an escape character."""
    if "${" in text:
        raise ValueError("unexpected ${ in model text: %r" % text[:80])
    return "'%s'" % text.replace("\\", "\\\\").replace("'", "\\'")


def header(lines):
    out = ["-- " + "=" * 96,
           "-- GENERATED FILE - DO NOT EDIT BY HAND. Regenerate with: python3 -I %s" % SCRIPT,
           "-- Generated by %s from the Lakehouse Industry Data Model \"Consumer Goods v2 MVM\"" % SCRIPT,
           "-- (Copyright Databricks, Inc.; Databricks license - see LICENSE.md and NOTICE.md in this",
           "-- bundle folder, copies of tools/model/). Modified for the Fjallmark Genie bootcamp.",
           "-- " + "-" * 96]
    out += ["-- " + ln if ln else "--" for ln in lines]
    out.append("-- " + "=" * 96)
    return "\n".join(out) + "\n"


def silver_expr(attr):
    """Typed + cleaned expression for one raw STRING column."""
    c = q(attr["column_name"])
    t = attr["type"].strip().upper()
    b = base_type(t)
    v = "trim(%s)" % c
    if b == "STRING":
        if is_enum(attr.get("value_regex")):
            values = attr["value_regex"].split("|")
            seen = set()
            whens = []
            for val in values:
                key = val.strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                whens.append("      WHEN %s THEN %s" % (lit(key), lit(val.strip())))
            return "CASE lower(%s)\n%s\n      ELSE NULLIF(%s, '')\n    END" % (v, "\n".join(whens), v)
        return "NULLIF(%s, '')" % v
    if b == "BOOLEAN":
        return ("CASE WHEN lower(%s) IN (%s) THEN TRUE\n         WHEN lower(%s) IN (%s) THEN FALSE END"
                % (v, ", ".join(lit(x) for x in BOOL_TRUE), v, ", ".join(lit(x) for x in BOOL_FALSE)))
    if b == "DATE":
        return ("COALESCE(try_to_date(%s, 'yyyy-MM-dd'), try_to_date(%s, 'dd/MM/yyyy'), TRY_CAST(%s AS DATE))"
                % (v, v, v))
    if b == "TIMESTAMP":
        return "COALESCE(try_to_timestamp(%s, 'yyyy-MM-dd HH:mm:ss'), TRY_CAST(%s AS TIMESTAMP))" % (v, v)
    # INT, BIGINT, DECIMAL(p,s), DOUBLE ...
    return "TRY_CAST(NULLIF(%s, '') AS %s)" % (v, t)


# ---------------------------------------------------------------------------------------------
# pipeline files
# ---------------------------------------------------------------------------------------------

def gen_bronze(domain):
    d = domain["name"]
    parts = [header([
        "BRONZE layer - domain `%s` (%d tables)." % (d, len(domain["products"])),
        "One streaming table per source table: Auto Loader (read_files) ingests every new CSV file in",
        "/Volumes/${catalog}/landing/raw_files/%s/<table>/ exactly once. All columns stay STRING" % d,
        "(inferColumnTypes => false); values that do not fit land in _rescued_data.",
        "Lineage columns: _source_file (file path) and _ingested_at (load time).",
        "${catalog} is replaced by the pipeline configuration value `catalog`.",
    ])]
    for p in domain["products"]:
        t = p["table_name"]
        parts.append(
            "\nCREATE OR REFRESH STREAMING TABLE ${catalog}.bronze.%s_%s\n"
            "COMMENT %s\n"
            "AS SELECT\n"
            "  *,\n"
            "  _metadata.file_path AS _source_file,\n"
            "  current_timestamp() AS _ingested_at\n"
            "FROM STREAM read_files(\n"
            "  '/Volumes/${catalog}/landing/raw_files/%s/%s/',\n"
            "  format => 'csv',\n"
            "  header => true,\n"
            "  inferColumnTypes => false\n"
            ");\n" % (d, t, lit("Bronze: raw %s.%s rows exactly as delivered in the CSV extract "
                                            "(all columns STRING)." % (d, t)), d, t))
    return "".join(parts)


def gen_silver(domain):
    d = domain["name"]
    parts = [header([
        "SILVER layer - domain `%s` (%d tables)." % (d, len(domain["products"])),
        "One materialized view per table that turns the raw STRING columns into the model's types:",
        "  * text            -> trim, empty string becomes NULL",
        "  * enum text       -> case-insensitive match on the model's allowed values (value_regex list),",
        "                       mapped to the exact canonical spelling (' Gold' / 'GOLD' -> 'gold')",
        "  * numbers         -> TRY_CAST (bad values become NULL instead of failing the pipeline)",
        "  * dates           -> yyyy-MM-dd, dd/MM/yyyy (and other ISO variants via TRY_CAST)",
        "  * timestamps      -> 'yyyy-MM-dd HH:mm:ss' and ISO-8601 variants (T, Z, offsets, fractions)",
        "  * booleans        -> true/false, t/f, y/n, yes/no, 1/0 (any case)",
        "Duplicates: one row per primary key - the latest by the table's updated/modified timestamp",
        "(when it has one), then by _ingested_at. Rows with an empty primary key are kept by the dedup",
        "step so that the expectation below drops (and counts) every one of them.",
        "Expectations: primary key NOT NULL -> DROP ROW; selected amounts/quantities must not be",
        "negative (warn = counted only, DROP ROW where stated). Metrics: pipeline event log / UI.",
    ])]
    for p in domain["products"]:
        t = p["table_name"]
        fqn = "%s.%s" % (d, t)
        pk = p["primary_key"]
        upd = updated_column(p)
        cols = {a["column_name"]: a for a in p["attributes"]}
        constraints = ["  CONSTRAINT %s EXPECT (%s IS NOT NULL) ON VIOLATION DROP ROW" % (q(pk + "_not_null"), q(pk))]
        for c in DROP_NON_NEGATIVE.get(fqn, []):
            assert c in cols, (fqn, c)
            constraints.append("  CONSTRAINT %s EXPECT (%s IS NULL OR %s >= 0) ON VIOLATION DROP ROW"
                               % (q(c + "_not_negative"), q(c), q(c)))
        for c in WARN_NON_NEGATIVE.get(fqn, []):
            assert c in cols, (fqn, c)
            constraints.append("  CONSTRAINT %s EXPECT (%s IS NULL OR %s >= 0)" % (q(c + "_not_negative"), q(c), q(c)))
        order = ("%s DESC NULLS LAST, _ingested_at DESC" % q(upd)) if upd else "_ingested_at DESC"
        dedup_txt = ("latest %s wins" % upd) if upd else "latest _ingested_at wins"
        select = ",\n".join("    %s AS %s" % (silver_expr(a), q(a["column_name"])) for a in p["attributes"])
        parts.append(
            "\n-- %s ----------------------------------------------------------------\n"
            "CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.%s_%s (\n%s\n)\n"
            "COMMENT %s\n"
            "AS\nWITH typed AS (\n  SELECT\n%s,\n    _source_file,\n    _ingested_at\n"
            "  FROM ${catalog}.bronze.%s_%s\n)\n"
            "SELECT *\nFROM typed\n"
            "QUALIFY %s IS NULL\n"
            "     OR ROW_NUMBER() OVER (PARTITION BY %s ORDER BY %s) = 1;\n"
            % (fqn, d, t, ",\n".join(constraints),
               lit("Silver: %s typed and cleaned, one row per %s (%s)." % (fqn, pk, dedup_txt)),
               select, d, t, q(pk), q(pk), order))
    return "".join(parts)


def gold_build_order(model, scope_domains):
    """All gold tables of the scope in foreign-key order (referenced tables first; ties keep model
    order). Returns {(domain, table): (domain, table) built just before it}."""
    keys, deps = [], {}
    for dm in model["domains"]:
        if dm["name"] not in scope_domains:
            continue
        for p in dm["products"]:
            key = (dm["name"], p["table_name"])
            keys.append(key)
            deps[key] = set()
            for a in p["attributes"]:
                fk = a.get("foreign_key_to")
                if fk:
                    rd, rt, _ = fk.split(".")
                    if rd in scope_domains and (rd, rt) != key:
                        deps[key].add((rd, rt))
    order, done = [], set()
    while len(order) < len(keys):
        nxt = next((k for k in keys if k not in done and deps[k] <= done), None)
        if nxt is None:
            raise ValueError("foreign keys form a cycle")
        order.append(nxt)
        done.add(nxt)
    if GOLD_BUILD_ORDER == "fk_targets":
        return {k: sorted(deps[k], key=order.index) for k in order if deps[k]}
    return {order[i]: [order[i - 1]] for i in range(1, len(order))}


def gen_gold(domain, scope_domains=None, previous=None):
    """Gold DDL. scope_domains=None -> every model FK; else only FKs into those domains.
    previous: {(domain, table): (domain, table)} build order from gold_build_order()."""
    previous = previous or {}
    d = domain["name"]
    if scope_domains is None:
        intro = ["GOLD layer - domain `%s` (%d tables), ALL model foreign keys (full_model bundle)."
                 % (d, len(domain["products"])),
                 "Every referenced table is built by this pipeline (all 10 domains).",
                 "Self-referencing FKs are left out (pipelines reject cyclic FK chains), see per-table notes."]
    else:
        intro = ["GOLD layer - domain `%s` (%d tables), BOOTCAMP variant (bootcamp bundle)."
                 % (d, len(domain["products"])),
                 "Identical to full_model/src/pipeline/%s/03_gold.sql except that FOREIGN KEYs to tables" % d,
                 "outside the bootcamp domains (%s) are omitted: this bundle does not build" % ", ".join(scope_domains),
                 "those tables, and a foreign key needs its referenced table to exist. Self-referencing FKs are",
                 "left out as well (pipelines reject cyclic FK chains). Each table lists what was omitted."]
    parts = [header(intro + [
        "Each materialized view is the exact industry table: same column names, order, types and",
        "comments, the table comment, NOT NULL + PRIMARY KEY and FOREIGN KEY constraints (informational",
        "constraints, they are not enforced; Genie and BI tools use them to join tables).",
        "Constraints and comments cannot be changed after creation - they live here, in the pipeline.",
        "Gold data comes from silver only; governance (row filters / column masks) is applied on gold",
        "afterwards.",
        "Build order: a FOREIGN KEY can only be created once the referenced table has its PRIMARY KEY,",
        "but a pipeline only orders tables by the data they read. Each gold query therefore ends with",
        "  WHERE TRUE OR EXISTS (SELECT 1 FROM <referenced table>) ...",
        "which never filters a row but makes the pipeline build the referenced tables first. Because this",
        "hint reads the referenced GOLD table, a gold table whose hint reads a table with a row filter or",
        "column mask (bootcamp lab step 3: consumer.shopper, consumer.dtc_order, finance.ar_invoice) cannot be",
        "maintained incrementally (event log: PLAN_NOT_INCREMENTALIZABLE, SecureViewUnaryNode): while",
        "the policies are attached, every update recomputes those gold tables from silver (11 of the 36",
        "bootcamp gold tables) - same rows, no file read, bronze and silver stay NO_OP.",
        "Very first run of a fresh catalog: the first update loads ALL data, then ends 'FAILED",
        "unexpectedly' while registering the keys (Lakeflow registers the keys of brand-new tables only",
        "for small sets: up to 8 FKs worked, 13 or more failed). The pipeline's automatic retry reads no",
        "files and registers every primary and foreign key (measured on zz_cpg_bc_e2e: every",
        "materialized view NO_OP in the retry). Never use a full refresh.",
    ])]
    for p in domain["products"]:
        t = p["table_name"]
        pk = p["primary_key"]
        lines = []
        for a in p["attributes"]:
            nn = " NOT NULL" if a["column_name"] == pk else ""
            lines.append("  %s %s%s COMMENT %s" % (q(a["column_name"]), a["type"].strip().upper(), nn,
                                                   lit(column_comment(a))))
        lines.append("  CONSTRAINT %s PRIMARY KEY (%s)" % (q("pk_" + t), q(pk)))
        omitted = []
        for a in p["attributes"]:
            fk = a.get("foreign_key_to")
            if not fk:
                continue
            rd, rt, rc = fk.split(".")
            self_ref = (rd == d and rt == t)
            if self_ref and not INCLUDE_SELF_REFERENCING_FKS:
                omitted.append("%s -> %s (self-reference: pipelines reject cyclic FK chains)"
                               % (a["column_name"], fk))
                continue
            if scope_domains is not None and rd not in scope_domains:
                omitted.append("%s -> %s (table not in the bootcamp scope)" % (a["column_name"], fk))
                continue
            lines.append("  CONSTRAINT %s FOREIGN KEY (%s) REFERENCES ${catalog}.%s.%s (%s)"
                         % (q("fk_%s_%s_%s" % (d, t, a["column_name"])), q(a["column_name"]), rd, q(rt), q(rc)))
        note = ""
        if omitted:
            note = ("-- Omitted foreign keys:\n"
                    + "".join("--   %s\n" % o for o in omitted))
        select = ",\n".join("  %s" % q(a["column_name"]) for a in p["attributes"])
        where = ""
        if previous.get((d, t)):
            before = previous[(d, t)]
            where = ("\n-- Build order only - never filters a row: makes the pipeline build %s first.\n"
                     "WHERE TRUE" % ", ".join("%s.%s" % x for x in before)
                     + "".join("\n   OR EXISTS (SELECT 1 FROM ${catalog}.%s.%s)" % (pd, q(pt)) for pd, pt in before))
        parts.append(
            "\n-- %s.%s ----------------------------------------------------------------\n%s"
            "CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.%s.%s (\n%s\n)\n"
            "COMMENT %s\n"
            "AS SELECT\n%s\nFROM ${catalog}.silver.%s_%s%s;\n"
            % (d, t, note, d, q(t), ",\n".join(lines), lit((p.get("description") or "").strip()),
               select, d, t, where))
    return "".join(parts)


# ---------------------------------------------------------------------------------------------
# metric views
# ---------------------------------------------------------------------------------------------

def rewrite_metric_view(mv):
    """Return (target_name, sql) with catalog placeholder, domain schema and fixes applied."""
    d = mv["owner_domain"]
    owner = mv["owner_product"]
    sql = mv["sql"].strip()
    old_head = "CREATE OR REPLACE VIEW `%s`.`_metrics`.`%s`" % (MODEL_CATALOG, mv["view_name"])
    if not sql.startswith(old_head):
        raise ValueError("unexpected metric view header: %s" % sql[:120])
    fix = METRIC_VIEW_FIXES.get(mv["view_name"])
    if fix:
        new_owner, new_source = fix
        old_source = "`%s`.`%s`.`%s`" % (MODEL_CATALOG, d, owner)
        if sql.count(old_source) != 1:
            raise ValueError("cannot apply fix to %s" % mv["view_name"])
        sd, st = new_source.split(".")
        sql = sql.replace(old_source, "`%s`.`%s`.`%s`" % (MODEL_CATALOG, sd, st))
        owner = new_owner
    target = "%s_metrics" % owner
    sql = "CREATE OR REPLACE VIEW ${catalog}.%s.%s" % (d, q(target)) + sql[len(old_head):]
    sql = sql.replace("`%s`" % MODEL_CATALOG, "`${catalog}`")
    if MODEL_CATALOG in sql:
        raise ValueError("catalog name left in %s" % mv["view_name"])
    if not sql.endswith("$$"):
        raise ValueError("metric view %s does not end with $$" % mv["view_name"])
    return target, sql + ";"


def gen_metric_views(model, domain, notebook):
    d = domain["name"]
    views = [mv for mv in model["metric_views"] if mv["owner_domain"] == d]
    lines = ["INDUSTRY METRIC VIEWS - domain `%s` (%d views)." % (d, len(views)),
             "Changes vs. the model: created in the domain schema as ${catalog}.%s.<table>_metrics" % d,
             "(model: <model catalog>._metrics.%s_<table>), model catalog replaced by ${catalog}." % d]
    for name, (owner, src) in sorted(METRIC_VIEW_FIXES.items()):
        if any(mv["view_name"] == name for mv in views):
            lines.append("Fixed: %s now reads %s (model reads the wrong table) and is named %s_metrics."
                         % (name, src, owner))
    lines += ["Created by %s (job task metric_views): ${catalog} is" % notebook,
              "replaced with the catalog parameter, then each statement runs with spark.sql()."]
    parts = [header(lines)]
    for mv in views:
        target, sql = rewrite_metric_view(mv)
        parts.append("\n-- %s.%s  (model view: %s)\n-- %s\n%s\n"
                     % (d, target, mv["view_name"], (mv.get("description") or "").strip().replace("\n", " "), sql))
    return "".join(parts), len(views)


# ---------------------------------------------------------------------------------------------
# model tags
# ---------------------------------------------------------------------------------------------

def tag_dict(tag_set):
    """Model tag_set -> {key: value}. Labels become dbx_<label> = 'true' (as in the model's DDL);
    the labels primary_key / foreign_key are expressed as constraints instead."""
    out = {}
    for t in tag_set or []:
        if t.get("kind") == "label":
            if t["key"] in ("primary_key", "foreign_key"):
                continue
            key = t["key"] if t["key"].startswith("dbx_") else "dbx_" + t["key"]
            out[key] = "true"
        else:
            out[t["key"]] = t.get("value") or ""
    return out


def gen_tags(domain, notebook, foreign_key_count):
    d = domain["name"]
    tables = {}
    n = 0
    for p in domain["products"]:
        cols = {}
        for a in p["attributes"]:
            tags = tag_dict(a.get("tag_set"))
            if a.get("value_regex"):
                tags["dbx_value_regex"] = a["value_regex"]
            if tags:
                cols[a["column_name"]] = tags
                n += len(tags)
        ttags = tag_dict(p.get("tag_set"))
        n += len(ttags)
        tables[p["table_name"]] = {"table_tags": ttags, "column_tags": cols}
    stags = tag_dict(domain.get("tag_set"))
    n += len(stags)
    doc = {
        "_notice": ("GENERATED FILE - do not edit by hand; regenerate with python3 -I %s. Tags from the "
                    "Lakehouse Industry Data Model 'Consumer Goods v2 MVM' (Copyright Databricks, Inc.; "
                    "Databricks license - see LICENSE.md and NOTICE.md in this bundle folder), modified "
                    "for the Fjallmark Genie bootcamp. Applied by %s." % (SCRIPT, notebook)),
        "domain": d,
        "schema_comment": (domain.get("description") or "").strip(),
        "tag_count": n,
        "foreign_key_count": foreign_key_count,   # FOREIGN KEYs of this domain's gold tables (02c checks it)
        "schema_tags": stags,
        "tables": tables,
    }
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n", n


# ---------------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------------

def build(model):
    files = {}
    stats = {"tables": 0, "fks_all": 0, "fks_bootcamp": 0, "metric_views": 0, "tags": 0,
             "bootcamp_tables": 0, "bootcamp_metric_views": 0, "bootcamp_tags": 0}
    names = [dm["name"] for dm in model["domains"]]
    for b in BOOTCAMP_DOMAINS:
        assert b in names, b
    order_full = gold_build_order(model, names)
    order_bootcamp = gold_build_order(model, BOOTCAMP_DOMAINS)
    for dm in model["domains"]:
        d = dm["name"]
        variants = [(FULL_PATHS, None, order_full)]
        if d in BOOTCAMP_DOMAINS:
            variants.append((BOOTCAMP_PATHS, BOOTCAMP_DOMAINS, order_bootcamp))
        for paths, scope, order in variants:
            base = "%s/%s/" % (paths["pipeline"], d)
            files[base + "01_bronze.sql"] = gen_bronze(dm)
            files[base + "02_silver.sql"] = gen_silver(dm)
            files[base + "03_gold.sql"] = gen_gold(dm, scope, order)
            nfk = files[base + "03_gold.sql"].count("` FOREIGN KEY (`")   # constraint lines only
            files["%s/%s.sql" % (paths["metric_views"], d)], nmv = gen_metric_views(model, dm, paths["mv_notebook"])
            files["%s/%s.json" % (paths["model_tags"], d)], ntags = gen_tags(dm, paths["tag_notebook"], nfk)
            if scope is None:
                stats["fks_all"] += nfk
                stats["tables"] += len(dm["products"])
                stats["metric_views"] += nmv
                stats["tags"] += ntags
            else:
                stats["fks_bootcamp"] += nfk
                stats["bootcamp_tables"] += len(dm["products"])
                stats["bootcamp_metric_views"] += nmv
                stats["bootcamp_tags"] += ntags
    # D2: each bundle folder is self-contained, so it carries its own copy of the model's license and
    # notice (the license requires giving recipients a copy; bundle deployments sync only the folder).
    for name in LICENSE_FILES:
        with open(os.path.join(ROOT, "tools", "model", name), encoding="utf-8") as fh:
            text = fh.read()
        for folder in (BOOTCAMP_DIR, FULL_DIR):
            files["%s/%s" % (folder, name)] = text
    return files, stats


def unexpected_files(files):
    """Files below the generated folders that this generator does not write."""
    out = []
    for paths in (BOOTCAMP_PATHS, FULL_PATHS):
        for key in ("pipeline", "metric_views", "model_tags"):
            top = os.path.join(ROOT, paths[key])
            for dirpath, _, names in os.walk(top):
                for n in names:
                    rel = os.path.relpath(os.path.join(dirpath, n), ROOT).replace(os.sep, "/")
                    if rel not in files and not n.endswith(".md") and n != ".DS_Store":
                        out.append(rel)
    return sorted(out)


def main(argv):
    check = "--check" in argv
    model = load_model()
    files, stats = build(model)
    stale = []
    for rel, text in sorted(files.items()):
        path = os.path.join(ROOT, rel)
        old = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                old = fh.read()
        if old == text:
            continue
        stale.append(rel)
        if not check:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
    extra = unexpected_files(files)
    print("%s: %d files (%d %s)" % (SCRIPT, len(files), len(stale), "stale" if check else "written"))
    print("  full_model/: %d tables, %d FKs, %d metric views, %d tags"
          % (stats["tables"], stats["fks_all"], stats["metric_views"], stats["tags"]))
    print("  bootcamp/  : %d tables (%s), %d FKs, %d metric views, %d tags"
          % (stats["bootcamp_tables"], ", ".join(BOOTCAMP_DOMAINS), stats["fks_bootcamp"],
             stats["bootcamp_metric_views"], stats["bootcamp_tags"]))
    for x in extra:
        print("  unexpected (not generated - delete it): " + x)
    if check and stale:
        for s in stale:
            print("  stale: " + s)
    if check and (stale or extra):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
