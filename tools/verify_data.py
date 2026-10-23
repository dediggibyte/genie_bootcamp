#!/usr/bin/env python3
"""Standalone checker for the bootcamp data set.

The CSV files are stored once, split over the two bundle folders: ``bootcamp/data/<domain>/<table>.csv``
(bootcamp domains consumer, finance, manufacturing) and ``full_model/data/<domain>/<table>.csv`` (the
other 7 domains). The checker reads both (every table must be in exactly one place - the right one).

Usage (from the repository root)::

    python3 -I tools/verify_data.py [--data bootcamp/data full_model/data] [--quiet]

It re-implements the silver-layer cleaning rules (it does not import the generator):

* rows with an empty primary key are dropped;
* ``consumer.dtc_order_line`` rows with a negative ``quantity_ordered`` are dropped;
* duplicates per primary key: exact copies collapse, otherwise the row with the latest
  updated/modified timestamp wins;
* enum values are normalised with trim + case-fold before checking them against the
  ``value_regex`` list; dates may be ``yyyy-MM-dd`` or ``dd/MM/yyyy``; booleans may be
  true/false, Y/N or 1/0.

Checks: CSV headers vs the model, value types and DECIMAL precision, PK uniqueness,
FK integrity (only the documented guest-checkout ``dtc_order.shopper_id`` orphans are
allowed), enum and regex validity, date window (backward-looking ``last_*`` dates never
after the extract), journal entries balanced (debit = credit per journal_entry_id in
transaction, company-code and group currency), arithmetic of DTC orders, AR invoices,
production orders and yield records, file sizes (each CSV < 10 MB, both data folders together below
the 39.5 MB guard of the 40 MB budget), file placement (bootcamp domains in bootcamp/data only), and business realism / storyline rules: DTC growth in
value, P&L margins and balance-sheet balances, loyalty tier rules and redemptions, names,
phones, GTIN check digits, placeholder texts, real company names, receivables (S6),
Tampere ramp-up timing (S4), plant utilisation and schedule adherence. Finally prints the
storyline KPIs S1-S6.

Exit code 0 when everything passes, 1 otherwise. Standard library only.
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MODEL_PATH = os.path.join(HERE, "model", "consumer_goods_v2_mvm.json")

EXTRACT_TS = "2026-10-15 23:59:59"
FUTURE_MAX = "2036-12-31 23:59:59"
GUEST_ID_MIN = 990000000
MAX_FILE_BYTES = 10 * 1000 * 1000
MAX_TOTAL_BYTES = 40 * 1000 * 1000          # hard budget of all data folders together (build spec section 3)
BOOTCAMP_DOMAINS = ("consumer", "finance", "manufacturing")   # stored in bootcamp/data, the rest in full_model/data
DEFAULT_DATA_DIRS = (os.path.join("bootcamp", "data"), os.path.join("full_model", "data"))
SIZE_GUARD_BYTES = int(39.5 * 1000 * 1000)  # fail early: keep 0.5 MB reserve below the budget
TXN_END = "2026-09-30"
TRUE_SET = {"true", "y", "1"}
FALSE_SET = {"false", "n", "0"}
D0 = Decimal(0)


# --------------------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------------------

def _is_enum(v):
    return bool(v) and not (v.startswith("^") or "[" in v or "\\" in v or "(" in v)


def load_model(path=MODEL_PATH):
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    tables = []
    for dom in raw["model"]["domains"]:
        for p in dom["products"]:
            cols = []
            for a in p["attributes"]:
                typ = (a.get("type") or "STRING").upper()
                m = re.match(r"DECIMAL\((\d+),\s*(\d+)\)", typ)
                rx = a.get("value_regex") or ""
                fk = a.get("foreign_key_to")
                cols.append({
                    "name": a["column_name"], "type": typ, "base": "DECIMAL" if m else typ,
                    "prec": int(m.group(1)) if m else None, "scale": int(m.group(2)) if m else None,
                    "enum": [x.casefold() for x in rx.split("|")] if _is_enum(rx) else None,
                    "pattern": re.compile(rx) if (rx and not _is_enum(rx)) else None,
                    "fk": ("%s.%s" % tuple(fk.split(".")[:2])) if fk and fk.count(".") == 2 else None,
                })
            tables.append({"domain": dom["name"], "name": p["table_name"],
                           "fqn": "%s.%s" % (dom["name"], p["table_name"]), "pk": p["primary_key"],
                           "kind": (p.get("type") or "").lower(), "columns": cols})
    return tables


_UPDATED = ("updated_timestamp", "last_updated_timestamp", "last_modified_timestamp", "modified_timestamp",
            "record_audit_updated", "record_updated_timestamp", "cost_estimate_modified_timestamp")


def dedup_column(table):
    names = [c["name"] for c in table["columns"] if c["base"] == "TIMESTAMP"]
    for pref in _UPDATED:
        if pref in names:
            return pref
    for n in names:
        if "updated" in n or "modified" in n:
            return n
    return None


def _tokens(name):
    return [t for t in re.split(r"[^a-z0-9]+", name.lower()) if t]


_END = {"end", "until", "to", "closed", "close", "termination", "terminated", "dissolution", "decommissioning",
        "discontinuation", "divestiture", "cancellation", "cancelled", "withdrawal", "retirement", "retired",
        "finish", "completion", "completed", "resolution", "resolved", "closure", "deactivation", "exit",
        "departure"}
_FUTURE = {"due", "expiry", "expiration", "expires", "expire", "deadline", "renewal", "maturity",
           "requalification", "review"}


def forward_looking(name):
    """Columns that may legitimately hold dates after the extract date."""
    t = _tokens(name)
    s = set(t)
    if "birth" in s or s & {"created", "creation", "inserted", "updated", "modified", "changed"}:
        return False
    if t and t[0] in ("last", "latest", "previous", "prior", "most"):
        return False            # backward-looking (last_review_date is in the past)
    if t and t[0] == "next":
        return True
    if s & {"warranty", "depreciation"} and s & _END:
        return True
    return bool(s & _FUTURE)


# --------------------------------------------------------------------------------------
# parsing helpers
# --------------------------------------------------------------------------------------

def parse_date(v):
    v = v.strip()
    try:
        if len(v) == 10 and v[4] == "-":
            return datetime.date(int(v[:4]), int(v[5:7]), int(v[8:10]))
        if len(v) == 10 and v[2] == "/":
            return datetime.date(int(v[6:]), int(v[3:5]), int(v[:2]))
    except ValueError:
        return None
    return None


def parse_ts(v):
    try:
        return datetime.datetime.strptime(v.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def dec(v):
    if v is None or v == "":
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def boolean(v):
    v = (v or "").strip().lower()
    if v in TRUE_SET:
        return True
    if v in FALSE_SET:
        return False
    return None


class Report(object):
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.kpis = {}
        self.lines = []
        self.stats = {}

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def out(self, msg=""):
        self.lines.append(msg)


# --------------------------------------------------------------------------------------
# load + silver rules
# --------------------------------------------------------------------------------------

def load_tables(data_dirs, tables, rep):
    """Read every table's CSV from the first data folder that has it. With the default two folders a
    bootcamp-domain table must be in the first one (bootcamp/data) and every other table in the second
    (full_model/data), and no table may be stored twice."""
    data = {}
    total = 0
    for t in tables:
        found = [os.path.join(d, t["domain"], t["name"] + ".csv") for d in data_dirs]
        found = [p for p in found if os.path.exists(p)]
        if not found:
            rep.error("%s: file missing (looked in %s)" % (t["fqn"], ", ".join(data_dirs)))
            continue
        if len(found) > 1:
            rep.error("%s: stored more than once (%s) - every CSV must exist exactly once" % (t["fqn"], ", ".join(found)))
        path = found[0]
        if len(data_dirs) == 2:
            want = data_dirs[0] if t["domain"] in BOOTCAMP_DOMAINS else data_dirs[1]
            if os.path.dirname(os.path.dirname(path)) != want.rstrip(os.sep):
                rep.error("%s: stored in %s, expected below %s" % (t["fqn"], path, want))
        size = os.path.getsize(path)
        total += size
        if size >= MAX_FILE_BYTES:
            rep.error("%s: file is %.2f MB (limit 10 MB)" % (t["fqn"], size / 1e6))
        with open(path, encoding="utf-8", newline="") as fh:
            raw = fh.read()
        if "\r" in raw:
            rep.error("%s: CR characters found (expected LF line endings)" % t["fqn"])
        rows = list(csv.reader(raw.splitlines()))
        header = rows[0] if rows else []
        expected = [c["name"] for c in t["columns"]]
        if header != expected:
            rep.error("%s: header does not match the model column list/order" % t["fqn"])
            continue
        body = rows[1:]
        bad_width = sum(1 for r in body if len(r) != len(expected))
        if bad_width:
            rep.error("%s: %d rows with a wrong number of fields" % (t["fqn"], bad_width))
            body = [r for r in body if len(r) == len(expected)]
        data[t["fqn"]] = {"raw": body, "bytes": size}
    rep.stats["csv_bytes"] = total
    return data


def silver(t, body, rep):
    """Apply the documented cleaning rules; return {pk: row} and counters."""
    cols = [c["name"] for c in t["columns"]]
    pk_i = cols.index(t["pk"])
    stats = {"raw": len(body), "empty_pk": 0, "negative_qty": 0, "exact_dup": 0, "updated_dup": 0}
    kept = []
    for r in body:
        if r[pk_i].strip() == "":
            stats["empty_pk"] += 1
            continue
        kept.append(r)
    if t["fqn"] == "consumer.dtc_order_line":
        qi = cols.index("quantity_ordered")
        before = len(kept)
        kept = [r for r in kept if not (r[qi].strip().startswith("-"))]
        stats["negative_qty"] = before - len(kept)
    upd = dedup_column(t)
    ui = cols.index(upd) if upd else None
    by_pk = {}
    for r in kept:
        k = r[pk_i].strip()
        if k not in by_pk:
            by_pk[k] = r
            continue
        prev = by_pk[k]
        if prev == r:
            stats["exact_dup"] += 1
            continue
        if ui is None:
            rep.error("%s: PK %s has conflicting rows and no updated/modified timestamp" % (t["fqn"], k))
            continue
        if prev[ui] == r[ui]:
            rep.error("%s: PK %s has conflicting rows with the same %s" % (t["fqn"], k, upd))
            continue
        stats["updated_dup"] += 1
        if r[ui] > prev[ui]:
            by_pk[k] = r
    stats["clean"] = len(by_pk)
    return by_pk, stats


# --------------------------------------------------------------------------------------
# generic checks
# --------------------------------------------------------------------------------------

def check_values(t, rows, rep):
    cols = t["columns"]
    for j, c in enumerate(cols):
        bad = defaultdict(int)
        example = {}
        nonempty = 0
        for r in rows:
            v = r[j]
            if v == "":
                continue
            nonempty += 1
            base = c["base"]
            kind = None
            if base in ("INT", "BIGINT"):
                if not re.fullmatch(r"-?\d+", v):
                    kind = "type"
            elif base == "DECIMAL":
                if not re.fullmatch(r"-?\d+(\.\d+)?", v):
                    kind = "type"
                else:
                    ip, _, fp = v.lstrip("-").partition(".")
                    if len(fp) != c["scale"] or len(ip.lstrip("0")) > c["prec"] - c["scale"]:
                        kind = "precision"
            elif base == "BOOLEAN":
                if boolean(v) is None:
                    kind = "boolean"
            elif base == "DATE":
                d = parse_date(v)
                if d is None:
                    kind = "date"
                elif d.isoformat() + " 00:00:00" > (FUTURE_MAX if forward_looking(c["name"]) else EXTRACT_TS):
                    kind = "after_window"
            elif base == "TIMESTAMP":
                ts = parse_ts(v)
                if ts is None:
                    kind = "timestamp"
                elif v > (FUTURE_MAX if forward_looking(c["name"]) else EXTRACT_TS):
                    kind = "after_window"
            elif base == "STRING":
                if c["enum"] is not None and v.strip().casefold() not in c["enum"]:
                    kind = "enum"
                elif c["pattern"] is not None and not c["pattern"].fullmatch(v.strip()):
                    kind = "regex"
            if kind:
                bad[kind] += 1
                example.setdefault(kind, v)
        for kind, n in sorted(bad.items()):
            rep.error("%s.%s: %d %s violations (e.g. %r)" % (t["fqn"], c["name"], n, kind, example[kind]))
        if nonempty == 0 and rows:
            rep.warn("%s.%s: column is empty in every row" % (t["fqn"], c["name"]))


def check_fks(tables, clean, rep):
    pks = dict((fqn, set(rows)) for fqn, rows in clean.items())
    orphans_allowed = 0
    for t in tables:
        rows = clean.get(t["fqn"])
        if rows is None:
            continue
        for j, c in enumerate(t["columns"]):
            if not c["fk"] or c["name"] == t["pk"]:
                continue
            parent = pks.get(c["fk"], set())
            bad = 0
            ex = None
            for r in rows.values():
                v = r[j].strip()
                if v and v not in parent:
                    if t["fqn"] == "consumer.dtc_order" and c["name"] == "shopper_id" and int(v) >= GUEST_ID_MIN:
                        orphans_allowed += 1
                        continue
                    bad += 1
                    ex = ex or v
            if bad:
                rep.error("%s.%s: %d orphan values not found in %s (e.g. %s)" % (t["fqn"], c["name"], bad, c["fk"], ex))
    rep.stats["guest_checkout_orphans"] = orphans_allowed


# --------------------------------------------------------------------------------------
# table views (column access by name)
# --------------------------------------------------------------------------------------

class View(object):
    def __init__(self, table, rows):
        self.idx = dict((c["name"], i) for i, c in enumerate(table["columns"]))
        self.rows = list(rows.values())

    def get(self, r, name):
        return r[self.idx[name]]

    def dicts(self, *names):
        ix = [self.idx[n] for n in names]
        for r in self.rows:
            yield dict((n, r[i]) for n, i in zip(names, ix))


def check_journal(views, rep):
    jel = views["finance.journal_entry_line"]
    sums = defaultdict(lambda: [D0] * 6)
    for r in jel.dicts("journal_entry_id", "debit_credit_indicator", "amount_transaction_currency",
                       "amount_company_code_currency", "amount_group_currency"):
        s = sums[r["journal_entry_id"]]
        k = 0 if r["debit_credit_indicator"].strip().upper() == "D" else 3
        s[k] += dec(r["amount_transaction_currency"]) or D0
        s[k + 1] += dec(r["amount_company_code_currency"]) or D0
        s[k + 2] += dec(r["amount_group_currency"]) or D0
    unbalanced = [(je, s) for je, s in sums.items() if s[0] != s[3] or s[1] != s[4] or s[2] != s[5]]
    if unbalanced:
        je, s = unbalanced[0]
        rep.error("journal_entry_line: %d journal entries are not balanced (e.g. %s: D %s / C %s)"
                  % (len(unbalanced), je, s[0], s[3]))
    headers = set(r[0] for r in views["finance.journal_entry"].rows)
    missing = len(headers - set(sums))
    if missing:
        rep.error("journal_entry: %d headers without lines" % missing)
    rep.stats["journal_entries_checked"] = len(sums)


def _close(a, b, tol=Decimal("0.0001")):
    return a is not None and b is not None and abs(a - b) <= tol


def check_arithmetic(views, rep):
    lines = views["consumer.dtc_order_line"]
    agg = defaultdict(lambda: [D0, D0, D0])
    bad = 0
    for r in lines.dicts("dtc_order_id", "quantity_ordered", "unit_price", "line_subtotal", "line_discount_pct",
                         "line_discount_amount", "line_net_amount", "tax_amount", "line_total_amount"):
        q, up, sub = dec(r["quantity_ordered"]), dec(r["unit_price"]), dec(r["line_subtotal"])
        pct, disc, net = dec(r["line_discount_pct"]), dec(r["line_discount_amount"]), dec(r["line_net_amount"])
        tax, tot = dec(r["tax_amount"]), dec(r["line_total_amount"])
        ok = (_close(q * up, sub, Decimal("0.00005")) and _close((sub * pct / 100), disc, Decimal("0.00006"))
              and sub - disc == net and net + tax == tot)
        if not ok:
            bad += 1
        a = agg[r["dtc_order_id"]]
        a[0] += sub
        a[1] += disc
        a[2] += tax
    if bad:
        rep.error("dtc_order_line: %d lines violate subtotal/discount/net/total arithmetic" % bad)
    bad = 0
    for r in views["consumer.dtc_order"].dicts("dtc_order_id", "subtotal_amount", "discount_amount", "tax_amount",
                                               "shipping_amount", "order_total_amount"):
        a = agg.get(r["dtc_order_id"])
        sub, disc, tax = dec(r["subtotal_amount"]), dec(r["discount_amount"]), dec(r["tax_amount"])
        ship, tot = dec(r["shipping_amount"]), dec(r["order_total_amount"])
        if a is None or a != [sub, disc, tax] or sub - disc + ship + tax != tot:
            bad += 1
    if bad:
        rep.error("dtc_order: %d orders whose totals do not equal the sum of their lines (+ shipping)" % bad)
    bad = 0
    for r in views["finance.ar_invoice"].dicts("gross_amount", "trade_discount_amount", "net_amount", "tax_amount",
                                               "total_amount", "amount_received", "write_off_amount",
                                               "outstanding_balance"):
        g, td, n, tx, tot = (dec(r[k]) for k in ("gross_amount", "trade_discount_amount", "net_amount",
                                                  "tax_amount", "total_amount"))
        rec, wo, out = dec(r["amount_received"]) or D0, dec(r["write_off_amount"]) or D0, dec(r["outstanding_balance"])
        if g - td != n or n + tx != tot or tot - rec - wo != out or out < 0:
            bad += 1
    if bad:
        rep.error("ar_invoice: %d invoices with inconsistent gross/net/tax/total/outstanding" % bad)
    bad = 0
    for r in views["manufacturing.production_order"].dicts("order_quantity", "confirmed_quantity",
                                                           "yield_percentage", "order_status"):
        y = dec(r["yield_percentage"])
        if y is None or r["order_status"].strip().upper() in ("PCNF", "REL", "CRTD"):
            continue
        calc = dec(r["confirmed_quantity"]) / dec(r["order_quantity"]) * 100
        if abs(calc - y) > Decimal("0.01"):
            bad += 1
    if bad:
        rep.error("production_order: %d orders where yield_percentage != confirmed/order*100" % bad)
    bad = 0
    for r in views["manufacturing.yield_record"].dicts("input_quantity", "output_quantity", "actual_yield_percentage"):
        i, o, y = dec(r["input_quantity"]), dec(r["output_quantity"]), dec(r["actual_yield_percentage"])
        if i and abs(o / i * 100 - y) > Decimal("0.01"):
            bad += 1
    if bad:
        rep.error("yield_record: %d records where actual_yield_percentage != output/input*100" % bad)


# --------------------------------------------------------------------------------------
# storyline KPIs
# --------------------------------------------------------------------------------------

def _ym(v):
    return v[:7]


def fx_table(views):
    """(currency, 'yyyy-MM') -> EUR per unit, derived from the GL (group / company code amounts)."""
    je = dict((r["journal_entry_id"], r) for r in views["finance.journal_entry"].dicts(
        "journal_entry_id", "fiscal_year", "fiscal_period"))
    out = {}
    for r in views["finance.journal_entry_line"].dicts("journal_entry_id", "company_code_currency_code", "exchange_rate"):
        h = je.get(r["journal_entry_id"])
        if not h:
            continue
        key = (r["company_code_currency_code"], "%s-%02d" % (h["fiscal_year"], int(h["fiscal_period"])))
        out.setdefault(key, dec(r["exchange_rate"]))
    return out


def kpis(views, rep):
    k = {}
    fx = fx_table(views)
    gl = dict((r["gl_account_id"], r) for r in views["finance.gl_account"].dicts(
        "gl_account_id", "account_number", "account_group", "company_code_id"))
    cc = dict((r["company_code_id"], r["code"]) for r in views["finance.company_code"].dicts("company_code_id", "code"))
    je = dict((r["journal_entry_id"], r) for r in views["finance.journal_entry"].dicts(
        "journal_entry_id", "fiscal_year", "fiscal_period", "company_code_id"))

    # ---- S1 DTC gross vs finance net revenue ----
    gross = defaultdict(lambda: D0)
    for r in views["consumer.dtc_order"].dicts("order_date", "currency_code", "order_total_amount"):
        ym = _ym(r["order_date"])
        rate = fx.get((r["currency_code"], ym))
        if rate is None:
            continue
        gross[ym] += dec(r["order_total_amount"]) * rate
    net_dtc = defaultdict(lambda: D0)
    net_all = defaultdict(lambda: D0)
    naive_local = D0
    group_total = D0
    for r in views["finance.journal_entry_line"].dicts("journal_entry_id", "gl_account_id", "debit_credit_indicator",
                                                       "amount_group_currency", "amount_company_code_currency"):
        g = gl.get(r["gl_account_id"])
        if not g or g["account_group"] != "REVENUE":
            continue
        h = je[r["journal_entry_id"]]
        ym = "%s-%02d" % (h["fiscal_year"], int(h["fiscal_period"]))
        sign = 1 if r["debit_credit_indicator"].strip().upper() == "C" else -1
        amt = dec(r["amount_group_currency"]) * sign
        net_all[ym] += amt
        group_total += amt
        naive_local += dec(r["amount_company_code_currency"]) * sign
        if g["account_number"] in ("3010", "3050"):
            net_dtc[ym] += amt
    months = sorted(set(gross) & set(net_dtc))
    gaps = [(m, gross[m], net_dtc[m], 1 - net_dtc[m] / gross[m]) for m in months if gross[m]]
    k["S1"] = {"months": [{"month": m, "dtc_gross_eur": float(round(g, 2)), "finance_dtc_net_revenue_eur": float(round(n, 2)),
                           "gap_pct": float(round(x * 100, 1))} for m, g, n, x in gaps],
               "total_dtc_gross_eur": float(round(sum(g for _, g, _, _ in gaps), 2)),
               "total_dtc_net_revenue_eur": float(round(sum(n for _, _, n, _ in gaps), 2)),
               "net_revenue_all_channels_eur": float(round(group_total, 2))}
    tg, tn = sum(g for _, g, _, _ in gaps), sum(n for _, _, n, _ in gaps)
    k["S1"]["overall_gap_pct"] = float(round((1 - tn / tg) * 100, 1)) if tg else None
    k["S1"]["gross_over_net_pct"] = float(round((tg / tn - 1) * 100, 1)) if tn else None
    k["S1"]["gap_range_pct"] = [min(x["gap_pct"] for x in k["S1"]["months"]), max(x["gap_pct"] for x in k["S1"]["months"])]
    shipped_months = k["S1"]["months"][:-1] or k["S1"]["months"]      # the last month has unshipped orders
    k["S1"]["gap_range_shipped_months_pct"] = [min(x["gap_pct"] for x in shipped_months),
                                               max(x["gap_pct"] for x in shipped_months)]
    k["S1"]["last_month"] = k["S1"]["months"][-1] if k["S1"]["months"] else None
    # bridge from webshop gross to finance DTC net revenue, as shares of gross
    comp = defaultdict(lambda: D0)
    orders = {}
    for r in views["consumer.dtc_order"].dicts("dtc_order_id", "order_date", "currency_code", "order_status",
                                               "order_total_amount", "tax_amount", "shipping_amount"):
        rate = fx.get((r["currency_code"].strip(), _ym(r["order_date"])))
        if rate is None:
            continue
        rec = r["order_status"].strip().casefold() in ("shipped", "delivered", "returned")
        orders[r["dtc_order_id"]] = (rate, rec)
        comp["gross"] += dec(r["order_total_amount"]) * rate
        if not rec:
            comp["not_recognised"] += dec(r["order_total_amount"]) * rate
        else:
            comp["vat"] += dec(r["tax_amount"]) * rate
            comp["shipping"] += dec(r["shipping_amount"]) * rate
    for r in views["consumer.dtc_order_line"].dicts("dtc_order_id", "line_net_amount", "is_returned"):
        o = orders.get(r["dtc_order_id"])
        if o and o[1] and boolean(r["is_returned"]):
            comp["returns"] += dec(r["line_net_amount"]) * o[0]
    if comp["gross"]:
        k["S1"]["bridge_pct_of_gross"] = dict((key, float(round(comp[key] / comp["gross"] * 100, 2)))
                                              for key in ("vat", "returns", "shipping", "not_recognised"))

    # ---- S2 currency trap ----
    k["S2"] = {"naive_sum_company_code_currency": float(round(naive_local, 2)),
               "correct_sum_group_currency_eur": float(round(group_total, 2)),
               "naive_over_correct_ratio": float(round(naive_local / group_total, 2)) if group_total else None}

    # ---- S3 PL-POZ-L2 ----
    lines = dict((r["production_line_id"], r["line_code"]) for r in views["manufacturing.production_line"].dicts(
        "production_line_id", "line_code"))
    s3 = defaultdict(lambda: [D0, D0, D0, 0, 0, 0])
    for r in views["manufacturing.production_order"].dicts("production_line_id", "actual_finish_timestamp",
                                                           "order_quantity", "confirmed_quantity", "scrap_quantity",
                                                           "downtime_minutes", "scheduled_finish_date"):
        if lines.get(r["production_line_id"]) != "POZNL2" or not r["actual_finish_timestamp"]:
            continue
        ym = _ym(r["actual_finish_timestamp"])
        a = s3[ym]
        a[0] += dec(r["order_quantity"])
        a[1] += dec(r["confirmed_quantity"])
        a[2] += dec(r["scrap_quantity"])
        a[3] += int(r["downtime_minutes"] or 0)
        a[4] += 1
        a[5] += 1 if r["actual_finish_timestamp"][:10] > r["scheduled_finish_date"] else 0
    pl_var = defaultdict(lambda: D0)
    for r in views["finance.journal_entry_line"].dicts("journal_entry_id", "gl_account_id", "debit_credit_indicator",
                                                       "amount_group_currency"):
        g = gl.get(r["gl_account_id"])
        if not g or g["account_number"] != "4100" or cc.get(g["company_code_id"]) != "PL01":
            continue
        h = je[r["journal_entry_id"]]
        ym = "%s-%02d" % (h["fiscal_year"], int(h["fiscal_period"]))
        sign = 1 if r["debit_credit_indicator"].strip().upper() == "D" else -1
        pl_var[ym] += dec(r["amount_group_currency"]) * sign
    eq = sum(1 for r in views["manufacturing.yield_record"].dicts("yield_loss_reason_code")
             if r["yield_loss_reason_code"].strip() == "EQMALF")
    k["S3"] = {"months": [{"month": m, "orders": a[4], "yield_pct": float(round(a[1] / a[0] * 100, 1)),
                           "scrap_pct": float(round(a[2] / a[0] * 100, 2)), "downtime_min": a[3], "late_orders": a[5],
                           "pl01_production_variance_eur": float(round(pl_var.get(m, D0), 2))}
                          for m, a in sorted(s3.items()) if "2025-11" <= m <= "2026-06"],
               "yield_records_with_EQMALF": eq}

    # ---- S4 Tampere OEE ----
    plants = dict((r["manufacturing_facility_id"], r["plant_code"]) for r in views["manufacturing.manufacturing_facility"].dicts(
        "manufacturing_facility_id", "plant_code"))
    s4 = defaultdict(list)
    for r in views["manufacturing.production_order"].dicts("manufacturing_facility_id", "actual_start_timestamp",
                                                           "oee_percentage"):
        if plants.get(r["manufacturing_facility_id"]) != "TMPR" or not r["oee_percentage"]:
            continue
        y, m = int(r["actual_start_timestamp"][:4]), int(r["actual_start_timestamp"][5:7])
        s4["%d-Q%d" % (y, (m - 1) // 3 + 1)].append(dec(r["oee_percentage"]))
    k["S4"] = {"quarters": [{"quarter": q, "orders": len(v), "avg_oee_pct": float(round(sum(v) / len(v), 1))}
                            for q, v in sorted(s4.items())]}

    # ---- S5 loyalty ----
    tiers = dict((r["loyalty_tier_id"], r["tier_name"]) for r in views["consumer.loyalty_tier"].dicts(
        "loyalty_tier_id", "tier_name"))
    shop = {}
    for r in views["consumer.shopper"].dicts("shopper_id", "loyalty_tier_id", "cltv_segment"):
        shop[r["shopper_id"]] = (tiers.get(r["loyalty_tier_id"], "Non-member"), r["cltv_segment"].strip().casefold())
    seg_n = defaultdict(int)
    for sid, (tier, _) in shop.items():
        seg_n[tier] += 1
    agg = defaultdict(lambda: [0, D0])
    last_order = {}
    for r in views["consumer.dtc_order"].dicts("shopper_id", "order_date", "currency_code", "order_total_amount",
                                               "order_status"):
        s = shop.get(r["shopper_id"])
        d = r["order_date"][:10]
        if r["shopper_id"] in shop:
            last_order[r["shopper_id"]] = max(last_order.get(r["shopper_id"], ""), d)
        if s is None or r["order_status"].strip().casefold() == "cancelled":
            continue
        rate = fx.get((r["currency_code"], _ym(r["order_date"])))
        if rate is None:
            continue
        a = agg[s[0]]
        a[0] += 1
        a[1] += dec(r["order_total_amount"]) * rate
    base = agg.get("Non-member")
    rows = []
    for tier in ("Non-member", "Bronze", "Silver", "Gold", "Platinum"):
        a = agg.get(tier, [0, D0])
        n = seg_n.get(tier, 0)
        aov = a[1] / a[0] if a[0] else D0
        freq = Decimal(a[0]) / n if n else D0
        rows.append({"tier": tier, "shoppers": n, "orders": a[0], "orders_per_shopper": float(round(freq, 2)),
                     "aov_eur": float(round(aov, 2))})
    nm = rows[0]
    gp = [r for r in rows if r["tier"] in ("Gold", "Platinum")]
    gp_orders = sum(r["orders"] for r in gp)
    gp_aov = sum(Decimal(str(r["aov_eur"])) * r["orders"] for r in gp) / gp_orders if gp_orders else D0
    gp_freq = Decimal(gp_orders) / sum(r["shoppers"] for r in gp) if gp else D0
    cutoff = (datetime.date(2026, 10, 15) - datetime.timedelta(days=180)).isoformat()
    at_risk = [sid for sid, (_, seg) in shop.items() if seg == "at_risk"]
    violations = sum(1 for sid in at_risk if last_order.get(sid, "") > cutoff)
    k["S5"] = {"tiers": rows,
               "gold_platinum_vs_non_member_aov_ratio": float(round(gp_aov / Decimal(str(nm["aov_eur"])), 2)) if nm["aov_eur"] else None,
               "gold_platinum_vs_non_member_frequency_ratio": float(round(gp_freq / Decimal(str(nm["orders_per_shopper"])), 2)) if nm["orders_per_shopper"] else None,
               "at_risk_shoppers": len(at_risk), "at_risk_with_order_in_last_180_days": violations}
    if violations:
        rep.error("S5: %d at_risk shoppers have an order in the last 180 days" % violations)

    # ---- S6 DSO ----
    open_ar = defaultdict(lambda: D0)
    billed = defaultdict(lambda: D0)
    cur_of = {}
    disputed = [0, D0]
    for r in views["finance.ar_invoice"].dicts("company_code_id", "currency_code", "billing_date", "total_amount",
                                               "outstanding_balance", "dispute_flag"):
        code = cc.get(r["company_code_id"])
        cur_of[code] = r["currency_code"]
        open_ar[code] += dec(r["outstanding_balance"]) or D0
        if "2026-07-01" <= r["billing_date"] <= "2026-09-30":
            billed[code] += dec(r["total_amount"])
        if boolean(r["dispute_flag"]):
            disputed[0] += 1
            disputed[1] += (dec(r["outstanding_balance"]) or D0) * (fx.get((r["currency_code"], "2026-09")) or D0)
    days = Decimal(92)
    rows = []
    g_open = g_billed = D0
    for code in sorted(open_ar):
        rate = fx.get((cur_of[code], "2026-09"), Decimal(1))
        g_open += open_ar[code] * rate
        g_billed += billed[code] * rate
        dso = open_ar[code] / (billed[code] / days) if billed[code] else None
        rows.append({"company_code": code, "open_ar_eur": float(round(open_ar[code] * rate, 0)),
                     "dso_days": float(round(dso, 1)) if dso is not None else None})
    k["S6"] = {"company_codes": rows, "group_dso_days": float(round(g_open / (g_billed / days), 1)) if g_billed else None,
               "disputed_invoices": disputed[0], "disputed_open_eur": float(round(disputed[1], 0)),
               "definition": "DSO = open AR at 2026-09-30 / (billing Jul-Sep 2026 / 92 days)"}
    return k


def format_kpis(k):
    out = []
    s1 = k["S1"]
    out.append("S1  DTC gross (order_total_amount, converted to EUR) vs finance DTC net revenue (GL 3010-3050, EUR)")
    out.append("    finance DTC net revenue is %.1f %% lower than DTC gross (gross is %.1f %% higher than net); monthly "
               "range %.1f .. %.1f %% (last month %.1f %%); DTC gross EUR %.0f vs net EUR %.0f"
               % (s1["overall_gap_pct"], s1["gross_over_net_pct"], s1["gap_range_shipped_months_pct"][0],
                  s1["gap_range_shipped_months_pct"][1], s1["last_month"]["gap_pct"],
                  s1["total_dtc_gross_eur"], s1["total_dtc_net_revenue_eur"]))
    if s1.get("bridge_pct_of_gross"):
        b_ = s1["bridge_pct_of_gross"]
        out.append("    bridge (share of gross): VAT %.1f %%, returns %.1f %%, shipping %.1f %%, cancelled/unshipped %.1f %%"
                   % (b_["vat"], b_["returns"], b_["shipping"], b_["not_recognised"]))
    for mth in s1["months"]:
        if mth["month"] in ("2024-01", "2024-07", "2024-12", "2025-06", "2025-12", "2026-03", "2026-09"):
            out.append("    %s  gross %10.2f  net %10.2f  gap %4.1f %%" % (mth["month"], mth["dtc_gross_eur"],
                                                                         mth["finance_dtc_net_revenue_eur"], mth["gap_pct"]))
    out.append("    Net Revenue all channels (authoritative, EUR): %.0f" % s1["net_revenue_all_channels_eur"])
    s2 = k["S2"]
    out.append("S2  Revenue summed in company-code currency (mixed SEK/NOK/DKK/PLN/EUR) = %.0f vs group EUR = %.0f (x%.2f)"
               % (s2["naive_sum_company_code_currency"], s2["correct_sum_group_currency_eur"], s2["naive_over_correct_ratio"]))
    out.append("S3  PL-POZ-L2 (line_code POZNL2) by month of completion; PL01 production variance (GL 4100, EUR)")
    for mth in k["S3"]["months"]:
        out.append("    %s  orders %2d  yield %5.1f %%  scrap %5.2f %%  downtime %4d min  late %d  variance EUR %9.0f"
                   % (mth["month"], mth["orders"], mth["yield_pct"], mth["scrap_pct"], mth["downtime_min"],
                      mth["late_orders"], mth["pl01_production_variance_eur"]))
    out.append("    yield records with reason EQMALF: %d" % k["S3"]["yield_records_with_EQMALF"])
    out.append("S4  Tampere (TMPR) average OEE by quarter: " + ", ".join(
        "%s %.1f%%" % (q["quarter"], q["avg_oee_pct"]) for q in k["S4"]["quarters"]))
    s5 = k["S5"]
    out.append("S5  Orders per shopper and AOV (EUR, gross) by loyalty tier:")
    for t in s5["tiers"]:
        out.append("    %-10s shoppers %5d  orders %5d  orders/shopper %.2f  AOV EUR %.2f"
                   % (t["tier"], t["shoppers"], t["orders"], t["orders_per_shopper"], t["aov_eur"]))
    out.append("    Gold+Platinum vs non-members: AOV x%.2f, frequency x%.2f; at_risk shoppers %d (with order in last 180 days: %d)"
               % (s5["gold_platinum_vs_non_member_aov_ratio"], s5["gold_platinum_vs_non_member_frequency_ratio"],
                  s5["at_risk_shoppers"], s5["at_risk_with_order_in_last_180_days"]))
    s6 = k["S6"]
    out.append("S6  DSO by company code (%s):" % s6["definition"])
    out.append("    " + ", ".join("%s %.1f d" % (r["company_code"], r["dso_days"]) for r in s6["company_codes"])
               + "; group %.1f d; disputed invoices %d (open EUR %.0f)" % (s6["group_dso_days"], s6["disputed_invoices"],
                                                                         s6["disputed_open_eur"]))
    return out


# --------------------------------------------------------------------------------------
# business realism and storyline rules
# --------------------------------------------------------------------------------------

def _n(v):
    return (v or "").strip().casefold()


def _ts(v):
    v = (v or "").strip()
    return parse_ts(v) if len(v) == 19 else (datetime.datetime.combine(parse_date(v), datetime.time()) if parse_date(v) else None)


def _gs1_ok(code):
    digits, check = code[:-1], int(code[-1])
    total = sum(int(ch) * (3 if i % 2 == 0 else 1) for i, ch in enumerate(reversed(digits)))
    return (10 - total % 10) % 10 == check


PNL_REVENUE = ("3000", "3010", "3040", "3050")
PNL_COGS = ("4000", "4100")
PNL_OPEX = ("5000", "6100", "6300", "6400", "7000")
EBIT_RANGE = (Decimal("0"), Decimal("20"))           # EBIT margin per company and year, percent
DTC_GROWTH_RANGE = (Decimal("12"), Decimal("24"))    # DTC gross value growth in EUR, percent
B2B_GROWTH_RANGE = (Decimal("1"), Decimal("10"))     # B2B net revenue growth in EUR, percent
REDEEM_SHARE_RANGE = (Decimal("0.10"), Decimal("0.30"))
NAME_PLACEHOLDER = re.compile(r"^(Main|North|South|Baltic|Central|Nordic) .* \d{3}$")
REAL_COMPANY_NAMES = re.compile(r"\b(krones|tetra pak|sidel|syntegon|gea|alfa laval|mettler-toledo|norden machinery|"
                                r"bosch|rockwell|videojet|ishida|marchesini|spx|dhl|postnord|budbee|posten|posti|hermes|"
                                r"dpd|gls|postnl|db schenker|schenker|bring|dsv)\b", re.I)
PHONE_PLAN = {"SWE": ("46", 9), "NOR": ("47", 8), "DNK": ("45", 8), "FIN": ("358", 9), "DEU": ("49", 10),
              "NLD": ("31", 9), "POL": ("48", 9)}
RETAIL_TRADE_CHANNELS = ("grocery", "convenience", "discount", "specialty", "organic", "health_food", "drugstore",
                         "pharmacy")


def check_business_rules(views, tables, rep):
    fx = fx_table(views)
    _check_gl(views, rep)
    _check_dtc(views, fx, rep)
    _check_loyalty(views, rep)
    _check_people(views, rep)
    _check_codes_and_texts(views, tables, rep)
    _check_receivables(views, fx, rep)
    _check_manufacturing(views, rep)


def _check_gl(views, rep):
    """Posting window, P&L margins and plausible balance-sheet balances (issue classes: opex 2-3x revenue,
    payroll never paid, inventory never received, negative bank balances, postings after period end)."""
    cc = dict((r["company_code_id"], r["code"]) for r in views["finance.company_code"].dicts("company_code_id", "code"))
    gl = dict((r["gl_account_id"], r["account_number"]) for r in views["finance.gl_account"].dicts(
        "gl_account_id", "account_number"))
    je = {}
    late = 0
    for r in views["finance.journal_entry"].dicts("journal_entry_id", "posting_date", "fiscal_year", "fiscal_period"):
        je[r["journal_entry_id"]] = (r["posting_date"][:7], int(r["fiscal_year"]))
        if r["posting_date"] > TXN_END or "%s-%02d" % (r["fiscal_year"], int(r["fiscal_period"])) > TXN_END[:7]:
            late += 1
    if late:
        rep.error("journal_entry: %d entries posted after the last closed period (%s)" % (late, TXN_END))
    pnl = defaultdict(lambda: D0)
    mov = defaultdict(lambda: D0)          # (company, account, yyyy-MM) -> debit-positive local amount
    credits = defaultdict(lambda: D0)      # (company, account, yyyy-MM) -> credits only
    for r in views["finance.journal_entry_line"].dicts("journal_entry_id", "gl_account_id", "company_code_id",
                                                       "debit_credit_indicator", "amount_company_code_currency",
                                                       "amount_group_currency"):
        ym, fy = je[r["journal_entry_id"]]
        code, acct = cc[r["company_code_id"]], gl[r["gl_account_id"]]
        debit = _n(r["debit_credit_indicator"]) == "d"
        loc, grp = dec(r["amount_company_code_currency"]), dec(r["amount_group_currency"])
        mov[(code, acct, ym)] += loc if debit else -loc
        if not debit:
            credits[(code, acct, ym)] += loc
        for key in ((code, fy, acct), ("ALL", fy, acct)):
            pnl[key] += -grp if debit else grp          # credit-positive
    years = sorted(set(k[1] for k in pnl))
    for code in sorted(set(cc.values())) + ["ALL"]:
        for fy in years:
            rev = sum(pnl[(code, fy, a)] for a in PNL_REVENUE)
            if rev <= 0:
                continue
            ebit = rev + pnl[(code, fy, "3900")] + sum(pnl[(code, fy, a)] for a in PNL_COGS + PNL_OPEX)
            margin = ebit / rev * 100
            rep.stats.setdefault("ebit_margin_pct", {})["%s %d" % (code, fy)] = float(round(margin, 1))
            if not EBIT_RANGE[0] <= margin <= EBIT_RANGE[1]:
                rep.error("P&L %s %d: EBIT margin %.1f %% outside %s-%s %%" % (code, fy, margin, EBIT_RANGE[0], EBIT_RANGE[1]))
    months = sorted(set(k[2] for k in mov))
    last12 = months[-12:]
    for code in sorted(set(cc.values())):
        bal = defaultdict(lambda: D0)
        negative = {}
        for ym in months:
            for acct in ("1110", "1410", "1430", "1210", "2110", "2610", "2710", "2410", "1240"):
                bal[acct] += mov.get((code, acct, ym), D0)
            for acct in ("1110", "1410", "1430"):
                if bal[acct] < -1 and acct not in negative:
                    negative[acct] = (ym, bal[acct])
        for acct, (ym, v) in sorted(negative.items()):
            rep.error("balance %s %s is negative from the end of %s (%.0f)" % (code, acct, ym, v))
        for acct in ("2710", "2410", "1240"):
            if abs(bal[acct]) > 1:
                rep.error("balance %s %s should be settled at %s but is %.2f" % (code, acct, TXN_END, bal[acct]))
        for acct in ("1410", "1430"):
            relief = sum(credits.get((code, acct, ym), D0) for ym in last12) / 12
            if relief and bal[acct] > 3 * relief:
                rep.error("balance %s %s = %.0f is more than 3 months of issues (%.0f per month)"
                          % (code, acct, bal[acct], relief))
            if not relief and abs(bal[acct]) > 1:
                rep.error("balance %s %s = %.0f without any issue in the last 12 months" % (code, acct, bal[acct]))
        out_vat = sum(credits.get((code, "2610", ym), D0) for ym in last12) / 12
        if out_vat and -bal["2610"] > 4 * out_vat:
            rep.error("balance %s 2610 output VAT payable %.0f exceeds 4 months of output VAT" % (code, -bal["2610"]))
    rev = lambda y: sum(pnl[("ALL", y, a)] for a in ("3000", "3040"))
    if rev(2024) and rev(2025):
        g = (rev(2025) / rev(2024) - 1) * 100
        rep.stats["b2b_growth_2025_pct"] = float(round(g, 1))
        if not B2B_GROWTH_RANGE[0] <= g <= B2B_GROWTH_RANGE[1]:
            rep.error("B2B net revenue growth 2025 vs 2024 is %.1f %% (expected %s-%s %%)" % (g, B2B_GROWTH_RANGE[0], B2B_GROWTH_RANGE[1]))


def _check_dtc(views, fx, rep):
    """DTC grows ~18 % a year in value (EUR), not only in order count."""
    val = defaultdict(lambda: D0)
    for r in views["consumer.dtc_order"].dicts("order_date", "currency_code", "order_total_amount", "order_status"):
        if _n(r["order_status"]) == "cancelled":
            continue
        ym = r["order_date"][:7]
        val[ym] += dec(r["order_total_amount"]) * (fx.get((r["currency_code"].strip(), ym)) or D0)
    full = lambda y: sum(v for k, v in val.items() if k[:4] == y)
    ytd = lambda y: sum(v for k, v in val.items() if k[:4] == y and k[5:7] <= TXN_END[5:7])
    for label, a, b in (("2025 vs 2024", full("2024"), full("2025")), ("Jan-Sep 2026 vs 2025", ytd("2025"), ytd("2026"))):
        if not a:
            continue
        g = (b / a - 1) * 100
        rep.stats.setdefault("dtc_value_growth_pct", {})[label] = float(round(g, 1))
        if not DTC_GROWTH_RANGE[0] <= g <= DTC_GROWTH_RANGE[1]:
            rep.error("DTC gross value growth (EUR) %s is %.1f %% (expected %s-%s %%)" % (label, g, DTC_GROWTH_RANGE[0], DTC_GROWTH_RANGE[1]))


def _check_loyalty(views, rep):
    """Tier rules hold for every active account; points are redeemed (15-25 % of credits)."""
    tiers = {}
    for r in views["consumer.loyalty_tier"].dicts("loyalty_tier_id", "tier_name", "required_points", "required_spend_usd"):
        tiers[r["loyalty_tier_id"]] = (r["tier_name"], dec(r["required_points"]) or D0, dec(r["required_spend_usd"]) or D0)
    bad = bad_bal = 0
    for r in views["consumer.loyalty_account"].dicts("loyalty_tier_id", "account_status", "lifetime_points_earned",
                                                     "lifetime_points_redeemed", "lifetime_points_expired",
                                                     "points_balance", "tier_qualification_spend"):
        e, red, x, b = (dec(r[k]) or D0 for k in ("lifetime_points_earned", "lifetime_points_redeemed",
                                                   "lifetime_points_expired", "points_balance"))
        if abs(b - (e - red - x)) > Decimal("0.01"):
            bad_bal += 1
        t = tiers.get(r["loyalty_tier_id"])
        if t and _n(r["account_status"]) == "active" and (t[1] or t[2]):
            if not (e >= t[1] or (dec(r["tier_qualification_spend"]) or D0) >= t[2]):
                bad += 1
    if bad:
        rep.error("loyalty_account: %d active accounts meet neither the points nor the spend requirement of their tier" % bad)
    if bad_bal:
        rep.error("loyalty_account: %d accounts where points_balance != earned - redeemed - expired" % bad_bal)
    by_acc = defaultdict(list)
    for r in views["consumer.loyalty_transaction"].dicts("loyalty_account_id", "transaction_timestamp", "loyalty_transaction_id",
                                                         "points_direction", "points_amount", "points_balance_before",
                                                         "points_balance_after"):
        by_acc[r["loyalty_account_id"]].append(r)
    bad_chain = 0
    for acc, txs in by_acc.items():
        txs.sort(key=lambda t: (t["transaction_timestamp"], int(t["loyalty_transaction_id"])))
        prev = None
        for t in txs:
            b_, a_, p_ = dec(t["points_balance_before"]), dec(t["points_balance_after"]), dec(t["points_amount"])
            sign = 1 if _n(t["points_direction"]) == "credit" else -1
            if (prev is not None and b_ != prev) or a_ != b_ + sign * p_ or a_ < 0:
                bad_chain += 1
            prev = a_
    if bad_chain:
        rep.error("loyalty_transaction: %d movements break the chronological balance chain (before = previous after)"
                  % bad_chain)
    pts = defaultdict(lambda: D0)
    for r in views["consumer.loyalty_transaction"].dicts("transaction_type", "trigger_event", "points_amount"):
        pts[_n(r["transaction_type"])] += dec(r["points_amount"]) or D0
        if _n(r["transaction_type"]) == "redeem" and _n(r["trigger_event"]) == "purchase":
            pts["redeem_on_orders"] += dec(r["points_amount"]) or D0
    credit = pts["earn"] + pts["adjust"]
    share = pts["redeem"] / credit if credit else D0
    rep.stats["loyalty_redeemed_share"] = float(round(share, 3))
    if not REDEEM_SHARE_RANGE[0] <= share <= REDEEM_SHARE_RANGE[1]:
        rep.error("loyalty: redeemed points are %.1f %% of earned points (expected %s-%s %%)"
                  % (share * 100, REDEEM_SHARE_RANGE[0] * 100, REDEEM_SHARE_RANGE[1] * 100))
    on_orders = sum((dec(r["loyalty_points_redeemed"]) or D0) for r in views["consumer.dtc_order"].dicts("loyalty_points_redeemed"))
    if on_orders != pts["redeem_on_orders"]:
        rep.error("loyalty: dtc_order.loyalty_points_redeemed (%s) != redeem movements on purchases (%s)"
                  % (on_orders, pts["redeem_on_orders"]))


def _check_people(views, rep):
    """Gendered given names, national phone lengths, account created before the first order,
    preferred banners are store-operating retailers, full_name = first + last."""
    shoppers = list(views["consumer.shopper"].dicts("shopper_id", "gender", "given_name", "country_code",
                                                    "primary_phone", "created_timestamp", "preferred_store_banner"))
    by_name = defaultdict(set)
    for r in shoppers:
        if _n(r["gender"]) in ("male", "female"):
            by_name[r["given_name"]].add(_n(r["gender"]))
    mixed = sorted(n for n, g in by_name.items() if len(g) > 1)
    if mixed:
        rep.error("consumer.shopper: %d given names occur as both male and female (e.g. %s)" % (len(mixed), mixed[:3]))
    bad_phone = [r["primary_phone"] for r in shoppers if r["country_code"].strip() in PHONE_PLAN and r["primary_phone"]
                 and not (r["primary_phone"].startswith("+" + PHONE_PLAN[r["country_code"].strip()][0]) and
                          len(re.sub(r"\D", "", r["primary_phone"])) - len(PHONE_PLAN[r["country_code"].strip()][0])
                          == PHONE_PLAN[r["country_code"].strip()][1])]
    if bad_phone:
        rep.error("consumer.shopper.primary_phone: %d numbers with a wrong national length (e.g. %s)" % (len(bad_phone), bad_phone[0]))
    first = {}
    for r in views["consumer.dtc_order"].dicts("shopper_id", "order_date"):
        if r["shopper_id"] not in first or r["order_date"] < first[r["shopper_id"]]:
            first[r["shopper_id"]] = r["order_date"]
    late = [r["shopper_id"] for r in shoppers if r["shopper_id"] in first and r["created_timestamp"] > first[r["shopper_id"]]]
    if late:
        rep.error("consumer.shopper: %d shoppers created after their first order" % len(late))
    banners = defaultdict(set)
    for r in views["sales.trade_account"].dicts("dba_name", "account_type", "trade_channel", "headquarters_country_code"):
        if _n(r["account_type"]) == "retailer" and _n(r["trade_channel"]) in RETAIL_TRADE_CHANNELS:
            banners[r["headquarters_country_code"].strip()].add(r["dba_name"])
    bad_banner = [r["preferred_store_banner"] for r in shoppers if r["preferred_store_banner"]
                  and r["preferred_store_banner"] not in banners.get(r["country_code"].strip(), set())]
    if bad_banner:
        rep.error("consumer.shopper.preferred_store_banner: %d values are not a retail banner of the shopper's country "
                  "(e.g. %s)" % (len(bad_banner), bad_banner[0]))
    for fqn, v in views.items():
        if all(c in v.idx for c in ("first_name", "last_name", "full_name")):
            bad = sum(1 for r in v.dicts("first_name", "last_name", "full_name")
                      if r["full_name"] and r["first_name"] and r["full_name"] != "%s %s" % (r["first_name"], r["last_name"]))
            if bad:
                rep.error("%s: %d rows where full_name != first_name + last_name" % (fqn, bad))


def _check_codes_and_texts(views, tables, rep):
    """GTIN/EAN check digits, no placeholder names or '<Table> - <note>' descriptions, no real
    vendor or carrier names, product specifications consistent with the product category."""
    for t in tables:
        v = views.get(t["fqn"])
        if v is None:
            continue
        title = t["name"].replace("_", " ").title() + " - "
        for c in t["columns"]:
            toks = set(_tokens(c["name"]))
            col = [r[v.idx[c["name"]]] for r in v.rows if r[v.idx[c["name"]]]]
            if not col:
                continue
            if toks & {"gtin", "ean"} and c["base"] == "STRING":
                bad = [x for x in col if x.isdigit() and len(x) in (8, 12, 13, 14) and not _gs1_ok(x)]
                if bad:
                    rep.error("%s.%s: %d GTIN/EAN values with a wrong check digit (e.g. %s)" % (t["fqn"], c["name"], len(bad), bad[0]))
            if toks & {"gtin", "ean", "upc"} and c["base"] == "DECIMAL":
                bad = [x for x in col if not (x.endswith(".00") and len(x[:-3]) in (12, 13) and _gs1_ok(x[:-3]))]
                if bad:
                    rep.error("%s.%s: %d barcode numbers that are not a valid GTIN (e.g. %s)" % (t["fqn"], c["name"], len(bad), bad[0]))
            if c["base"] == "STRING" and toks & {"name", "title"}:
                bad = [x for x in col if NAME_PLACEHOLDER.match(x)]
                if bad:
                    rep.error("%s.%s: %d placeholder names (e.g. %r)" % (t["fqn"], c["name"], len(bad), bad[0]))
            if c["base"] == "STRING" and toks & {"description", "notes", "comments"}:
                bad = [x for x in col if x.startswith(title)]
                if bad:
                    rep.error("%s.%s: %d template texts '%s<note>' (e.g. %r)" % (t["fqn"], c["name"], len(bad), title, bad[0]))
            if c["base"] == "STRING" and (toks & {"manufacturer", "carrier", "vendor"} or c["name"] == "supplier_name"):
                bad = [x for x in col if REAL_COMPANY_NAMES.search(x)]
                if bad:
                    rep.error("%s.%s: %d real company names (e.g. %r)" % (t["fqn"], c["name"], len(bad), bad[0]))
    sku_cat = {}
    cat_of = dict((r["product_category_id"], r) for r in views["product.product_category"].dicts(
        "product_category_id", "parent_product_category_id", "category_code"))
    for r in views["product.sku"].dicts("sku_id", "product_category_id"):
        c = cat_of.get(r["product_category_id"])
        top = cat_of.get(c["parent_product_category_id"]) if c and c["parent_product_category_id"] else c
        sku_cat[r["sku_id"]] = top["category_code"] if top else None
    bad = 0
    for r in views["product.formulation"].dicts("sku_id", "inci_declaration", "regulatory_classification"):
        pc = sku_cat.get(r["sku_id"]) == "PERSONAL_CARE"
        if pc != bool(r["inci_declaration"]) or (not pc and _n(r["regulatory_classification"]) == "cosmetic"):
            bad += 1
    for r in views["product.label_spec"].dicts("sku_id", "regulatory_framework", "nutrition_facts_required"):
        pc = sku_cat.get(r["sku_id"]) == "PERSONAL_CARE"
        if pc != ("cosmetic" in _n(r["regulatory_framework"])) or pc == bool(boolean(r["nutrition_facts_required"])):
            bad += 1
    if bad:
        rep.error("product specifications: %d formulation/label rows inconsistent with the SKU's category" % bad)
    bad = sum(1 for r in views["product.packaging_spec"].dicts("unit_cost", "height_mm")
              if not (Decimal("0.001") <= (dec(r["unit_cost"]) or D0) <= Decimal("5")
                      and Decimal("10") <= (dec(r["height_mm"]) or D0) <= Decimal("600")))
    if bad:
        rep.error("product.packaging_spec: %d rows with implausible unit cost (EUR) or dimensions (mm)" % bad)


def _check_receivables(views, fx, rep):
    """S6: DE01 has the worst overdue AR by amount and share; no billing after a credit hold;
    contract value (acv_total) in the account's currency, about one year of billing."""
    cc = dict((r["company_code_id"], r["code"]) for r in views["finance.company_code"].dicts("company_code_id", "code"))
    as_of = datetime.date(2026, 9, 30)
    open_, over = defaultdict(lambda: D0), defaultdict(lambda: D0)
    billed = defaultdict(lambda: D0)
    last_bill = {}
    for r in views["finance.ar_invoice"].dicts("company_code_id", "trade_account_id", "currency_code", "billing_date",
                                               "due_date", "outstanding_balance", "net_amount"):
        code = cc[r["company_code_id"]]
        rate = fx.get((r["currency_code"].strip(), "2026-09")) or D0
        ob = (dec(r["outstanding_balance"]) or D0) * rate
        open_[code] += ob
        if parse_date(r["due_date"]) < as_of:
            over[code] += ob
        if r["billing_date"] >= "2025-10-01":
            billed[r["trade_account_id"]] += dec(r["net_amount"]) or D0
        last_bill[r["trade_account_id"]] = max(last_bill.get(r["trade_account_id"], ""), r["billing_date"])
    share = dict((c, over[c] / open_[c]) for c in open_ if open_[c])
    worst_amt = max(over, key=lambda c: over[c]) if over else None
    worst_share = max(share, key=lambda c: share[c]) if share else None
    rep.stats["overdue_share_pct"] = dict((c, float(round(v * 100, 1))) for c, v in share.items())
    if worst_amt != "DE01" or worst_share != "DE01":
        rep.error("S6: DE01 must have the largest overdue AR by amount and share (largest amount %s, largest share %s)"
                  % (worst_amt, worst_share))
    for r in views["sales.trade_account"].dicts("trade_account_id", "dba_name", "account_status", "status_change_timestamp",
                                                "last_order_date", "acv_total"):
        if _n(r["account_status"]) == "credit_hold" and r["status_change_timestamp"]:
            hold = r["status_change_timestamp"][:10]
            if last_bill.get(r["trade_account_id"], "") > hold or (r["last_order_date"] or "") > hold:
                rep.error("S6: %s is on credit hold since %s but has orders/billing after it" % (r["dba_name"], hold))
        b = billed.get(r["trade_account_id"])
        if b:
            ratio = (dec(r["acv_total"]) or D0) / b
            if not Decimal("0.7") <= ratio <= Decimal("1.6"):
                rep.error("sales.trade_account %s: acv_total is %.1f x the last 12 months' net billing (currency mix-up?)"
                          % (r["dba_name"], ratio))


def _check_manufacturing(views, rep):
    """S4 timing (Tampere at the 78 % target by June 2026), S3 repair date consistent, plants not idle,
    capacity in line with output, operations start close to their schedule."""
    plants = dict((r["manufacturing_facility_id"], r) for r in views["manufacturing.manufacturing_facility"].dicts(
        "manufacturing_facility_id", "plant_code", "production_capacity_units_per_day"))
    lines = dict((r["production_line_id"], r) for r in views["manufacturing.production_line"].dicts(
        "production_line_id", "line_code", "notes", "last_major_overhaul_date"))
    oee = defaultdict(list)
    hours = defaultdict(float)
    units = defaultdict(float)
    for r in views["manufacturing.production_order"].dicts("manufacturing_facility_id", "production_line_id",
                                                           "actual_start_timestamp", "actual_finish_timestamp",
                                                           "oee_percentage", "confirmed_quantity"):
        p = plants[r["manufacturing_facility_id"]]["plant_code"]
        if r["oee_percentage"] and r["actual_start_timestamp"]:
            oee[(p, r["actual_start_timestamp"][:7])].append(dec(r["oee_percentage"]))
        if r["actual_finish_timestamp"] and "2025-10" <= r["actual_finish_timestamp"][:7] <= TXN_END[:7]:
            a, b = parse_ts(r["actual_start_timestamp"]), parse_ts(r["actual_finish_timestamp"])
            hours[r["production_line_id"]] += (b - a).total_seconds() / 3600.0
            units[r["manufacturing_facility_id"]] += float(dec(r["confirmed_quantity"]) or 0)
    june = oee.get(("TMPR", "2026-06"))
    if june and sum(june) / len(june) < 78:
        rep.error("S4: Tampere June 2026 average OEE %.1f %% is below the 78 %% target" % (sum(june) / len(june)))
    for lid, ln in lines.items():
        if ln["line_code"] == "POZNL2" and ln["last_major_overhaul_date"] not in (ln["notes"] or ""):
            rep.error("S3: PL-POZ-L2 notes do not mention the repair date %s" % ln["last_major_overhaul_date"])
        h = hours.get(lid, 0.0)
        if lid in hours and not 800 <= h <= 4000:
            rep.error("manufacturing: line %s ran %.0f hours in the last 12 months (plausible 800-4000 h for a two-shift line)"
                      % (ln["line_code"], h))
    for fid, p in plants.items():
        cap = float(dec(p["production_capacity_units_per_day"]) or 0)
        if fid in units and cap:
            util = units[fid] / 250.0 / cap          # 250 working days in the last 12 months
            if not 0.10 <= util <= 0.85:
                rep.error("manufacturing: plant %s output is %.0f %% of its daily capacity" % (p["plant_code"], util * 100))
    n = ok = 0
    for r in views["manufacturing.production_confirmation"].dicts("actual_start_datetime", "scheduled_start_datetime"):
        a, s_ = _ts(r["actual_start_datetime"]), _ts(r["scheduled_start_datetime"])
        if a and s_:
            n += 1
            ok += abs((a - s_).total_seconds()) <= 3 * 3600
    if n and ok / n < 0.85:
        rep.error("manufacturing: only %.0f %% of operations start within 3 h of their schedule" % (ok / n * 100))


# --------------------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------------------

def run(data_dirs, quiet=False):
    """data_dirs: list of data folders (default layout: [bootcamp/data, full_model/data])."""
    if isinstance(data_dirs, str):
        data_dirs = [data_dirs]
    data_dirs = [os.path.normpath(d) for d in data_dirs]
    rep = Report()
    tables = load_model()
    data = load_tables(data_dirs, tables, rep)
    clean = {}
    table_stats = {}
    for t in tables:
        if t["fqn"] not in data:
            continue
        rows, st = silver(t, data[t["fqn"]]["raw"], rep)
        clean[t["fqn"]] = rows
        table_stats[t["fqn"]] = st
        check_values(t, list(rows.values()), rep)
    check_fks(tables, clean, rep)
    views = dict((t["fqn"], View(t, clean[t["fqn"]])) for t in tables if t["fqn"] in clean)
    if "finance.journal_entry_line" in views:
        check_journal(views, rep)
        check_arithmetic(views, rep)
        rep.kpis = kpis(views, rep)
        check_business_rules(views, tables, rep)
    total = 0
    for folder in data_dirs:
        for root, _, files in os.walk(folder):
            for f in files:
                total += os.path.getsize(os.path.join(root, f))
    rep.stats["folder_bytes"] = total
    if total >= MAX_TOTAL_BYTES:
        rep.error("data folders are %.2f MB (limit 40 MB)" % (total / 1e6))
    elif total >= SIZE_GUARD_BYTES:
        rep.error("data folders are %.2f MB - above the %.1f MB guard (budget 40 MB); trim rows before adding more"
                  % (total / 1e6, SIZE_GUARD_BYTES / 1e6))
    rep.stats["tables"] = table_stats
    result = {"errors": rep.errors, "warnings": rep.warnings, "kpis": rep.kpis, "stats": rep.stats,
              "kpi_lines": format_kpis(rep.kpis) if rep.kpis else []}
    if not quiet:
        _print(result, tables)
    return result


def _print(result, tables):
    st = result["stats"]
    raw = sum(s["raw"] for s in st["tables"].values())
    clean = sum(s["clean"] for s in st["tables"].values())
    agg = defaultdict(int)
    for s in st["tables"].values():
        for k in ("empty_pk", "negative_qty", "exact_dup", "updated_dup"):
            agg[k] += s[k]
    print("Tables: %d   CSV rows: %d   rows after silver rules: %d" % (len(st["tables"]), raw, clean))
    print("Silver rules applied: %d empty-PK rows dropped, %d negative-quantity lines dropped, %d exact duplicates "
          "collapsed, %d updated duplicates resolved (latest wins)" % (agg["empty_pk"], agg["negative_qty"],
                                                                    agg["exact_dup"], agg["updated_dup"]))
    print("Size: CSV %.2f MB, data folders %.2f MB (limits: 10 MB per file, 40 MB total)"
          % (st["csv_bytes"] / 1e6, st["folder_bytes"] / 1e6))
    print("Journal entries checked: %d; documented guest-checkout orphans: %d"
          % (st.get("journal_entries_checked", 0), st.get("guest_checkout_orphans", 0)))
    print()
    for line in result["kpi_lines"]:
        print(line)
    print()
    if result["warnings"]:
        print("Warnings (%d):" % len(result["warnings"]))
        for w in result["warnings"][:40]:
            print("  - " + w)
        if len(result["warnings"]) > 40:
            print("  ... %d more" % (len(result["warnings"]) - 40))
    if result["errors"]:
        print("ERRORS (%d):" % len(result["errors"]))
        for e in result["errors"][:100]:
            print("  - " + e)
        print("FAILED")
    else:
        print("All checks passed.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Verify the bootcamp data set.")
    ap.add_argument("--data", nargs="+", default=list(DEFAULT_DATA_DIRS),
                    help="data folder(s) with <domain>/<table>.csv (default: bootcamp/data full_model/data)")
    ap.add_argument("--quiet", action="store_true", help="only print the result line")
    ap.add_argument("--json", help="also write the full report (incl. KPIs) as JSON to this file")
    args = ap.parse_args(argv)
    data_dirs = [d if os.path.isabs(d) else os.path.join(REPO, d) for d in args.data]
    result = run(data_dirs, quiet=args.quiet)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str)
    if args.quiet:
        print("FAILED (%d errors)" % len(result["errors"]) if result["errors"] else "All checks passed.")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
