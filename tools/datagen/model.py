"""Read the vendored Lakehouse Industry Data Model (Consumer Goods v2, MVM).

Only the information the generator needs is kept: tables in model order, their primary
key, and per column the declared type, description, value constraints and foreign key.

Value constraints come in two flavours in ``value_regex``:

* a pipe-separated list of allowed values (``"active|inactive|closed"``) - an *enum*;
* a real regular expression (``"^[A-Z]{3}$"``) - a *pattern*.

Some free-text columns carry an ``[ENUM-REF-CANDIDATE: a|b|c ...]`` hint in their
description; those values are used as a soft vocabulary (``enum_candidates``) but are
not enforced.
"""
import json
import os
import re

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "model", "consumer_goods_v2_mvm.json")

CORE_DOMAINS = ("consumer", "finance", "manufacturing")

_CANDIDATE_RX = re.compile(r"\[ENUM-REF-CANDIDATE:([^\]]*)\]")
_DECIMAL_RX = re.compile(r"DECIMAL\((\d+),\s*(\d+)\)", re.I)


def is_enum_regex(value_regex):
    """True when ``value_regex`` is a plain pipe-list of allowed values."""
    if not value_regex:
        return False
    v = value_regex
    return not (v.startswith("^") or "[" in v or "\\" in v or "(" in v)


class Column(object):
    """One attribute of a table."""

    __slots__ = ("name", "type", "base", "precision", "scale", "description", "regex",
                 "enum", "enum_candidates", "pattern", "tags", "fk", "is_pk", "position")

    def __init__(self, attr, pk_name, position):
        self.name = attr["column_name"]
        self.type = (attr.get("type") or "STRING").strip().upper()
        self.description = attr.get("description") or ""
        self.regex = attr.get("value_regex") or ""
        self.tags = list(attr.get("tags") or [])
        self.is_pk = self.name == pk_name
        self.position = position
        m = _DECIMAL_RX.match(self.type)
        if m:
            self.base = "DECIMAL"
            self.precision, self.scale = int(m.group(1)), int(m.group(2))
        else:
            self.base = self.type
            self.precision, self.scale = None, None
        self.enum = self.regex.split("|") if is_enum_regex(self.regex) else None
        self.pattern = re.compile(self.regex) if (self.regex and not self.enum) else None
        self.enum_candidates = None
        m = _CANDIDATE_RX.search(self.description)
        if m:
            vals = m.group(1).split("—")[0].strip()
            cands = [v.strip() for v in vals.split("|") if v.strip()]
            if len(cands) >= 2:
                self.enum_candidates = cands
        fk = attr.get("foreign_key_to")
        self.fk = None
        if fk:
            parts = fk.split(".")
            if len(parts) == 3:
                self.fk = (parts[0], parts[1], parts[2])

    @property
    def fk_table(self):
        return "%s.%s" % (self.fk[0], self.fk[1]) if self.fk else None

    @property
    def max_abs(self):
        """Largest absolute value a DECIMAL column can hold."""
        if self.base != "DECIMAL":
            return None
        return 10 ** (self.precision - self.scale) - 10 ** (-self.scale)

    def __repr__(self):
        return "Column(%s %s)" % (self.name, self.type)


class Table(object):
    """One product (table) of the model."""

    def __init__(self, domain, product, index):
        self.domain = domain
        self.name = product["table_name"]
        self.fqn = "%s.%s" % (domain, self.name)
        self.index = index
        self.pk = product["primary_key"]
        self.kind = (product.get("type") or "").strip().lower()
        self.description = product.get("description") or ""
        self.subdomain = product.get("subdomain") or ""
        self.columns = [Column(a, self.pk, i) for i, a in enumerate(product["attributes"])]
        self.col = dict((c.name, c) for c in self.columns)

    @property
    def is_transactional(self):
        return self.kind == "transactional"

    @property
    def is_core(self):
        return self.domain in CORE_DOMAINS

    @property
    def column_names(self):
        return [c.name for c in self.columns]

    def fk_columns(self):
        return [c for c in self.columns if c.fk and not c.is_pk]

    def __repr__(self):
        return "Table(%s)" % self.fqn


class Model(object):
    """All tables of the model, in model order (domain order, then product order)."""

    def __init__(self, path=MODEL_PATH):
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        self.source = raw.get("source")
        self.upstream_commit = raw.get("upstream_commit")
        self.release_version = raw.get("release_version")
        m = raw["model"]
        self.domains = [d["name"] for d in m["domains"]]
        self.tables = []
        idx = 0
        for dom in m["domains"]:
            for prod in dom["products"]:
                idx += 1
                self.tables.append(Table(dom["name"], prod, idx))
        self.by_fqn = dict((t.fqn, t) for t in self.tables)

    def table(self, fqn):
        return self.by_fqn[fqn]

    def tables_of(self, domain):
        return [t for t in self.tables if t.domain == domain]
