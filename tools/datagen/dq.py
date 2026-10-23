"""Deterministic raw data-quality injection (build_spec section 4).

The generator first produces *clean* rows. This module then makes the raw CSV files
look like real extracts. Every injected issue is recorded in a :class:`DQLog` so that
``data/README.md`` and ``data/manifest.json`` document exactly what silver must fix.

Issue catalogue (core domains consumer / finance / manufacturing only):

==========================  =============================================  ===========================
issue                       where                                          silver handling
==========================  =============================================  ===========================
exact_duplicate_rows        ~1 % of rows of every transactional table      dedup by PK (exact copies
                                                                           collapse)
updated_duplicate_rows      ~2 % of rows of master tables that have an     dedup by PK, keep latest
                            updated/modified timestamp (>= 25 rows)        updated/modified timestamp
enum_case_whitespace        ~3 % of values of every pipe-list enum column  trim + case-fold to the
                                                                           canonical value_regex value
date_format_ddmmyyyy        ~5 % of values of 5 selected DATE columns      parse yyyy-MM-dd or
                                                                           dd/MM/yyyy
boolean_mixed_format        6 tables mix true/false, Y/N and 1/0           map Y/1/true -> TRUE,
                                                                           N/0/false -> FALSE
empty_primary_key           ~0.2 % extra rows with an empty PK              expectation PK NOT NULL ->
                                                                           DROP ROW
negative_quantity_lines     10 extra dtc_order_line rows, quantity < 0      expectation -> DROP ROW
guest_checkout_orphans      ~0.5 % of dtc_order rows reference a shopper   kept; documented (left join
                            id that is not in consumer.shopper             to shopper)
==========================  =============================================  ===========================
"""
import datetime

from . import engine

RATE_ENUM = 0.03
RATE_DATE = 0.05
RATE_EXACT_DUP = 0.01
RATE_UPDATED_DUP = 0.02
RATE_EMPTY_PK = 0.002
RATE_GUEST = 0.005
NEGATIVE_QTY_LINES = 10
MIN_ROWS_FOR_UPDATED_DUP = 25

DATE_FORMAT_COLUMNS = {
    "consumer.shopper": ["birth_date", "acquisition_date"],
    "consumer.loyalty_account": ["enrollment_date"],
    "finance.ar_invoice": ["due_date"],
    "finance.ap_invoice": ["invoice_date"],
}
# table -> (share Y/N, share 1/0); remaining rows keep true/false
BOOL_MIX_TABLES = {
    "consumer.shopper": (0.20, 0.10),
    "consumer.consent_record": (0.15, 0.15),
    "consumer.loyalty_account": (0.25, 0.0),
    "finance.ar_invoice": (0.20, 0.0),
    "manufacturing.batch_record": (0.0, 0.25),
    "manufacturing.production_order": (0.15, 0.10),
}
CORE = ("consumer", "finance", "manufacturing")

_UPDATED_PREFERENCE = ("updated_timestamp", "last_updated_timestamp", "last_modified_timestamp",
                       "modified_timestamp", "record_audit_updated", "record_updated_timestamp",
                       "cost_estimate_modified_timestamp")


def dedup_column(table):
    """The updated/modified timestamp silver orders by (None if the table has none)."""
    names = [c.name for c in table.columns if c.base == "TIMESTAMP"]
    for pref in _UPDATED_PREFERENCE:
        if pref in names:
            return pref
    for n in names:
        if "updated" in n or "modified" in n:
            return n
    return None


def created_column(table):
    for c in table.columns:
        if c.base == "TIMESTAMP" and engine.date_role(c.name) == "created":
            return c.name
    return None


class DQLog(object):
    def __init__(self):
        self.by_table = {}

    def add(self, fqn, issue, count, handling, columns=None, detail=None):
        if count <= 0:
            return
        entry = {"issue": issue, "rows_or_values": count, "handling": handling}
        if columns:
            entry["columns"] = list(columns)
        if detail:
            entry["detail"] = detail
        self.by_table.setdefault(fqn, []).append(entry)

    def issues(self, fqn):
        return self.by_table.get(fqn, [])


# --------------------------------------------------------------------------------------
# cross-table issue (applied on dict rows before formatting)
# --------------------------------------------------------------------------------------

def apply_guest_checkout(reg, log):
    """Re-label ~0.5 % of non-member DTC orders as guest checkouts (orphan shopper_id)."""
    orders = reg.rows.get("consumer.dtc_order")
    lines = reg.rows.get("consumer.dtc_order_line")
    if not orders:
        return
    rnd = reg.rng("dq", "guest")
    last_order = {}
    for o in orders:
        sid = o["shopper_id"]
        if sid is not None:
            if sid not in last_order or o["order_date"] > last_order[sid]:
                last_order[sid] = o["order_date"]
    candidates = [o for o in orders if o.get("loyalty_account_id") is None and o["shopper_id"] is not None
                  and o["order_date"] < last_order[o["shopper_id"]] and not o.get("subscription_id")]
    n = int(round(len(orders) * RATE_GUEST))
    chosen = sorted(rnd.sample(range(len(candidates)), min(n, len(candidates))))
    guest_orders = {}
    for k, idx in enumerate(chosen):
        o = candidates[idx]
        gid = engine.GUEST_ID_BASE + k + 1
        o["shopper_id"] = gid
        o["ship_to_address_id"] = None
        guest_orders[o["dtc_order_id"]] = gid
    blanked = 0
    for ln in lines or []:
        if ln["dtc_order_id"] in guest_orders:
            ln["shopper_id"] = None
            blanked += 1
    reg.ctx["guest_order_ids"] = sorted(guest_orders)
    log.add("consumer.dtc_order", "guest_checkout_orphans", len(guest_orders),
            "kept in silver/gold; shopper_id >= %d is a guest checkout without a shopper profile "
            "(use LEFT JOIN to consumer.shopper)" % engine.GUEST_ID_BASE, ["shopper_id"],
            "guest ids %d..%d; ship_to_address_id is NULL for these orders"
            % (engine.GUEST_ID_BASE + 1, engine.GUEST_ID_BASE + len(guest_orders)))
    log.add("consumer.dtc_order_line", "guest_checkout_lines", blanked,
            "kept; shopper_id is NULL on lines of guest-checkout orders", ["shopper_id"])


# --------------------------------------------------------------------------------------
# per-table string-level injection
# --------------------------------------------------------------------------------------

def _enum_variant(value, rnd):
    variants = []
    if value != value.upper():
        variants.append(value.upper())
    if value != value.lower():
        variants.append(value.lower())
    if value != value.title() and value.title() != value.upper():
        variants.append(value.title())
    variants.extend([" " + value, value + " ", " " + value.upper() + " "])
    variants = [v for v in variants if v != value]
    return rnd.choice(variants)


def _ddmmyyyy(iso):
    try:
        d = datetime.date.fromisoformat(iso)
    except ValueError:
        return iso
    return d.strftime("%d/%m/%Y")


def inject(reg, table, rows, log):
    """Return the raw string rows of ``table`` with data-quality issues injected."""
    if table.domain not in CORE:
        return rows
    fqn = table.fqn
    rnd = reg.rng("dq", fqn)
    idx = dict((c.name, i) for i, c in enumerate(table.columns))
    pk_i = idx[table.pk]

    # 1. enum case / whitespace noise
    enum_cols = [c for c in table.columns if c.enum and not c.is_pk]
    noisy = 0
    touched = []
    for c in enum_cols:
        ci = idx[c.name]
        hit = 0
        for r in rows:
            v = r[ci]
            if v and rnd.random() < RATE_ENUM:
                r[ci] = _enum_variant(v, rnd)
                hit += 1
        if hit:
            touched.append(c.name)
            noisy += hit
    log.add(fqn, "enum_case_whitespace", noisy,
            "trim + case-fold, then map to the canonical value of the column's value_regex list",
            touched)

    # 2. dd/MM/yyyy dates
    for cname in DATE_FORMAT_COLUMNS.get(fqn, []):
        ci = idx[cname]
        hit = 0
        for r in rows:
            if r[ci] and rnd.random() < RATE_DATE:
                r[ci] = _ddmmyyyy(r[ci])
                hit += 1
        log.add(fqn, "date_format_ddmmyyyy", hit,
                "parse with yyyy-MM-dd first, fall back to dd/MM/yyyy", [cname])

    # 3. mixed boolean formats
    if fqn in BOOL_MIX_TABLES:
        p_yn, p_10 = BOOL_MIX_TABLES[fqn]
        bcols = [idx[c.name] for c in table.columns if c.base == "BOOLEAN"]
        hit = 0
        for r in rows:
            x = rnd.random()
            style = "yn" if x < p_yn else ("10" if x < p_yn + p_10 else None)
            if not style:
                continue
            for ci in bcols:
                v = r[ci]
                if v == "true":
                    r[ci] = "Y" if style == "yn" else "1"
                    hit += 1
                elif v == "false":
                    r[ci] = "N" if style == "yn" else "0"
                    hit += 1
        log.add(fqn, "boolean_mixed_format", hit,
                "map true/Y/1 -> TRUE and false/N/0 -> FALSE (case-insensitive)",
                [c.name for c in table.columns if c.base == "BOOLEAN"])

    out = rows

    # 4. updated duplicates (master tables)
    upd = dedup_column(table)
    if not table.is_transactional and upd and len(rows) >= MIN_ROWS_FOR_UPDATED_DUP:
        n = int(round(len(rows) * RATE_UPDATED_DUP))
        chosen = set(rnd.sample(range(len(rows)), n))
        created = created_column(table)
        ui = idx[upd]
        ci_created = idx[created] if created else None
        change_cols = [idx[c.name] for c in enum_cols if "status" in c.name] or [idx[c.name] for c in enum_cols]
        new_rows = []
        made = 0
        for i, r in enumerate(rows):
            if i in chosen and r[ui]:
                old = list(r)
                latest = datetime.datetime.strptime(r[ui], "%Y-%m-%d %H:%M:%S")
                lo = None
                if ci_created is not None and r[ci_created]:
                    lo = datetime.datetime.strptime(r[ci_created], "%Y-%m-%d %H:%M:%S")
                if lo is None or lo >= latest:
                    lo = latest - datetime.timedelta(days=rnd.randint(5, 200))
                span = (latest - lo).total_seconds()
                prev = lo + datetime.timedelta(seconds=int(span * rnd.uniform(0.2, 0.8)))
                if prev >= latest:
                    prev = latest - datetime.timedelta(hours=1)
                old[ui] = prev.strftime("%Y-%m-%d %H:%M:%S")
                if change_cols:
                    ci = rnd.choice(change_cols)
                    col = table.columns[ci]
                    choices = [v for v in col.enum if v != (r[ci] or "").strip()]
                    if choices:
                        old[ci] = rnd.choice(choices)
                new_rows.append(old)
                made += 1
            new_rows.append(r)
        out = new_rows
        log.add(fqn, "updated_duplicate_rows", made,
                "deduplicate on %s keeping the row with the latest %s" % (table.pk, upd), [table.pk, upd],
                "older version precedes the current one; one attribute differs (typically a status)")

    # 5. exact duplicates (transactional tables)
    if table.is_transactional:
        n = int(round(len(rows) * RATE_EXACT_DUP))
        chosen = sorted(rnd.sample(range(len(rows)), n))
        dups = [list(rows[i]) for i in chosen]
        out = list(out) + dups
        log.add(fqn, "exact_duplicate_rows", len(dups),
                "deduplicate on %s (exact copies collapse)" % table.pk, [table.pk],
                "re-delivered extract rows appended at the end of the file")

    # 6. negative quantities on DTC order lines
    if fqn == "consumer.dtc_order_line":
        qi = idx["quantity_ordered"]
        extra = reg.extra_ids(fqn, NEGATIVE_QTY_LINES)
        picks = rnd.sample(range(len(rows)), NEGATIVE_QTY_LINES)
        neg = []
        money = [idx[c] for c in ("line_subtotal", "line_discount_amount", "line_net_amount", "tax_amount",
                                  "line_total_amount", "cost_of_goods_sold")]
        for k, i in enumerate(picks):
            r = list(rows[i])
            r[pk_i] = str(extra[k])
            r[qi] = "-" + r[qi]
            for mi in money:
                if r[mi] and not r[mi].startswith("-") and r[mi].strip("0.") != "":
                    r[mi] = "-" + r[mi]
            r[idx["quantity_shipped"]] = "0"
            neg.append(r)
        positions = sorted(rnd.sample(range(len(out)), len(neg)), reverse=True)
        out = list(out)
        for pos, r in zip(positions, neg):
            out.insert(pos, r)
        log.add(fqn, "negative_quantity_lines", len(neg),
                "expectation quantity_ordered >= 0 -> DROP ROW", ["quantity_ordered"],
                "reversal lines from a legacy order-management feed (ids %d..%d)" % (extra[0], extra[-1]))

    # 7. rows with an empty primary key
    n = int(round(len(rows) * RATE_EMPTY_PK))
    if n:
        picks = rnd.sample(range(len(rows)), n)
        junk = []
        for i in picks:
            r = list(rows[i])
            r[pk_i] = ""
            junk.append(r)
        positions = sorted(rnd.sample(range(len(out)), len(junk)), reverse=True)
        out = list(out)
        for pos, r in zip(positions, junk):
            out.insert(pos, r)
        log.add(fqn, "empty_primary_key", len(junk),
                "expectation %s IS NOT NULL -> DROP ROW" % table.pk, [table.pk])
    return out
