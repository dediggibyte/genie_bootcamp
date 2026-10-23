"""Orchestration: generate every table, validate, inject data-quality issues, write CSVs.

Order of work (dependencies flow downwards):

1. allocate key pools for all *generic* tables (so curated rows can reference them)
2. finance masters -> plants -> product (+ specifications) -> trade accounts / DCs ->
   manufacturing masters
3. demand: consumer (webshop + loyalty) and B2B billing (AR invoices + payments)
4. production execution, planned from the demand -> standard costs
5. finance transactions (COGS allocation, AP, general ledger)
6. generic rows for every remaining table (with coherence hooks for a few of them)
7. validation of the clean rows (enums, regexes, precision, date window)
8. data-quality injection and CSV writing
"""
import datetime
import json
import os
from decimal import Decimal

from . import (curated_consumer, curated_finance, curated_generic, curated_manufacturing, curated_masters,
               curated_product, curated_product_specs, dq, engine, world, writer)
from .model import Model

CURATED_OTHER = ("product.brand", "product.product_category", "product.category", "product.sku",
                 "sales.trade_account", "distribution.distribution_facility") + curated_product_specs.TABLES
GENERIC_COUNTS = {"master": 45, "reference": 25, "associative": 40, "transactional": 70}
GENERIC_OVERRIDES = {"procurement.supplier": 60, "sales.territory": 18,
                     "sales.rep": 40, "sales.retail_store": 100, "procurement.spend_category": 20,
                     "sales.order": 120, "sales.invoice": 120}


def is_curated(table):
    return table.is_core or table.fqn in CURATED_OTHER


def generic_count(table):
    if table.fqn in GENERIC_OVERRIDES:
        return GENERIC_OVERRIDES[table.fqn]
    return GENERIC_COUNTS.get(table.kind, 80)


def _actual_ratios(reg):
    agg = {}
    for po in reg.rows["manufacturing.production_order"]:
        m = po["_meta"]
        if m["progress"] < 1.0:
            continue
        fin = po["actual_finish_timestamp"]
        key = (m["sku"]["code"], fin.year, 1 if fin.month <= 6 else 2)
        a = agg.setdefault(key, [Decimal(0), Decimal(0)])
        a[0] += po["actual_cost"]
        a[1] += po["planned_cost"]
    return dict((k, (v[0] / v[1]).quantize(Decimal("0.000001"))) for k, v in agg.items() if v[1] > 0)


def generate(seed, log=print):
    model = Model()
    reg = engine.Registry(model, seed)
    generic = [t for t in model.tables if not is_curated(t)]
    for t in generic:
        reg.alloc(t.fqn, generic_count(t))
    log("  finance masters, plants, product, trade accounts, DCs ...")
    curated_finance.masters(reg)
    curated_manufacturing.facilities(reg)
    curated_product.generate(reg)
    curated_product_specs.generate(reg)
    curated_masters.generate(reg)
    curated_manufacturing.masters(reg)
    log("  consumer webshop and loyalty ...")
    curated_consumer.generate(reg)
    log("  B2B billing and receivables ...")
    curated_finance.receivables(reg)
    log("  production execution ...")
    curated_manufacturing.production(reg)
    curated_manufacturing.size_facilities(reg)
    reg.ctx["actual_ratio"] = _actual_ratios(reg)
    curated_finance.standard_costs(reg)
    log("  finance transactions and general ledger ...")
    curated_finance.transactions(reg)
    log("  generic tables (%d) ..." % len(generic))
    for t in generic:
        rows = reg.gen(t.fqn).rows(len(reg.pools[t.fqn]), fixed_fn=curated_generic.fixed_fn(reg, t.fqn))
        engine.ensure_filled(reg, t, rows)
        reg.rows[t.fqn] = rows
    missing = [t.fqn for t in model.tables if t.fqn not in reg.rows]
    if missing:
        raise RuntimeError("tables without rows: %s" % missing)
    return reg


# --------------------------------------------------------------------------------------
# validation of clean rows
# --------------------------------------------------------------------------------------

def validate(reg):
    """Return a list of problems in the clean (pre-DQ) rows."""
    problems = []
    max_ts = world.EXTRACT_TS
    future_ts = datetime.datetime.combine(world.FUTURE_MAX, datetime.time(23, 59, 59))
    for t in reg.model.tables:
        rows = reg.rows[t.fqn]
        roles = dict((c.name, engine.date_role(c.name)) for c in t.columns if c.base in ("DATE", "TIMESTAMP"))
        seen_pk = set()
        for c in t.columns:
            bad = 0
            example = None
            for r in rows:
                v = r.get(c.name)
                if v is None:
                    continue
                ok = True
                if c.base == "STRING":
                    if not isinstance(v, str):
                        ok = False
                    elif c.enum and v not in c.enum:
                        ok = False
                    elif c.pattern is not None and not c.pattern.fullmatch(v):
                        ok = False
                elif c.base == "DECIMAL":
                    ok = isinstance(v, (Decimal, int, float)) and abs(Decimal(str(v))) <= c.max_abs
                elif c.base in ("INT", "BIGINT"):
                    ok = isinstance(v, int) and not isinstance(v, bool)
                elif c.base == "BOOLEAN":
                    ok = isinstance(v, bool)
                elif c.base in ("DATE", "TIMESTAMP"):
                    dv = engine.as_dt(v)
                    limit = future_ts if roles[c.name] == "future" else max_ts
                    ok = isinstance(v, (datetime.date, datetime.datetime)) and dv <= limit and \
                        dv >= datetime.datetime(1940, 1, 1)
                if not ok:
                    bad += 1
                    example = example or v
            if bad:
                problems.append("%s.%s: %d invalid values (e.g. %r)" % (t.fqn, c.name, bad, example))
        for r in rows:
            pk = r.get(t.pk)
            if pk is None or pk in seen_pk:
                problems.append("%s: missing/duplicate PK %r" % (t.fqn, pk))
                break
            seen_pk.add(pk)
        # FK integrity (guest checkouts are injected later)
        for c in t.fk_columns():
            parent = set(reg.pools.get(c.fk_table, []))
            orphans = sum(1 for r in rows if r.get(c.name) is not None and r.get(c.name) not in parent)
            if orphans:
                problems.append("%s.%s: %d orphan FK values -> %s" % (t.fqn, c.name, orphans, c.fk_table))
    return problems


def empty_columns(reg):
    out = {}
    for t in reg.model.tables:
        rows = reg.rows[t.fqn]
        cols = [c.name for c in t.columns if all(r.get(c.name) is None for r in rows)]
        if cols:
            out[t.fqn] = cols
    return out


# --------------------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------------------

def write(reg, locate, log=print):
    """Inject DQ issues and write every table's CSV; return the manifest dict.

    ``locate(domain)`` returns ``(absolute folder, repository-relative folder)`` of the domain's CSV
    files (``<folder>/<table>.csv``): the bootcamp domains go to ``bootcamp/data/<domain>``, the
    other domains to ``full_model/data/<domain>`` - every file is stored exactly once."""
    dqlog = dq.DQLog()
    dq.apply_guest_checkout(reg, dqlog)
    manifest = {}
    for t in reg.model.tables:
        rows = writer.format_rows(t, reg.rows[t.fqn])
        clean = len(rows)
        raw = dq.inject(reg, t, rows, dqlog)
        data = writer.to_csv_bytes(t.column_names, raw)
        d, rel = locate(t.domain)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "%s.csv" % t.name)
        with open(path, "wb") as fh:
            fh.write(data)
        manifest.setdefault(t.domain, {})[t.name] = {
            "rows": len(raw), "clean_rows": clean, "scope": "bootcamp" if t.is_core else "full",
            "primary_key": t.pk, "dedup_order_column": dq.dedup_column(t),
            "file": "%s/%s.csv" % (rel, t.name), "bytes": len(data),
            "dq_issues": dqlog.issues(t.fqn),
        }
    return manifest, dqlog


MANIFEST_NOTICE = (
    "GENERATED FILE - do not edit by hand; regenerate with python3 -I tools/generate_data.py. Synthetic data "
    "whose tables, column names and value formats follow the Lakehouse Industry Data Model 'Consumer Goods v2 "
    "MVM' (Copyright Databricks, Inc.; Databricks license - see LICENSE.md and NOTICE.md in this bundle folder, "
    "copies of tools/model/), modified for the Fjallmark Genie bootcamp. The CSV files are documented in "
    "data/README.md.")


def write_manifest(manifest, path):
    """Write manifest.json: a "_notice" string, then {domain: {table: {...}}} (readers skip non-dict values)."""
    doc = {"_notice": MANIFEST_NOTICE}
    doc.update(manifest)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
