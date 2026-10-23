"""Generic, model-driven row generator.

The engine can populate *any* table of the model:

1. **Keys first.** ``Registry.alloc`` gives each table a disjoint block of BIGINT
   surrogate keys (``table.index * 100_000 + n``), so a key identifies its table.
2. **Then columns.** A *column plan* (one small closure per column) is compiled once per
   table from the column's type, name, description and ``value_regex``:

   * foreign keys draw from the parent's key pool (self references point to earlier
     rows, optional references are sometimes NULL);
   * pipe-list ``value_regex`` columns only ever receive one of the listed values;
   * regex ``value_regex`` columns get a semantic value (country, currency, user id ...)
     that is verified with ``re.fullmatch`` and otherwise a generated match;
   * dates and timestamps are placed relative to a per-row *anchor* according to their
     role (created, modified, start, end, due/expiry, last_*, event ...) and then put in
     temporal order (created <= updated, start <= end, effective <= expiry ...);
   * amounts, percentages, counts, durations ... come from name-aware ranges clamped to
     the declared DECIMAL precision;
   * names, e-mails (``@example.com``), fake phones, addresses and free text come from
     the fictional world and ``texts``.

The curated generators call :meth:`TableGen.row` with the columns they care about
already fixed; the engine fills in everything else around them and never overwrites a
fixed value.
"""
import datetime
import random
import re
from decimal import Decimal, ROUND_HALF_UP

from . import regexgen, texts, world

ID_BLOCK = 100000
GUEST_ID_BASE = 990000000     # guest-checkout shopper ids (no table owns this block)

_TOKEN_RX = re.compile(r"[^a-z0-9]+")
_NULLABLE_RX = re.compile(r"\bnull\b|\bnullable\b|populated only|only (?:when|if|for)\b|if applicable|"
                          r"\(optional\)|blank indicates|empty if|when applicable", re.I)


def tokens(name):
    return [t for t in _TOKEN_RX.split(name.lower()) if t]


def ascii_fold(text):
    table = str.maketrans({"å": "a", "ä": "a", "ö": "o", "ø": "o", "æ": "ae", "ü": "u", "é": "e",
                           "ß": "ss", "ł": "l", "ń": "n", "ś": "s", "ą": "a", "ę": "e", "ó": "o",
                           "ż": "z", "ź": "z", "ć": "c", "Å": "A", "Ä": "A", "Ö": "O", "Ø": "O",
                           "Æ": "AE", "Ü": "U", "Ł": "L", "Ś": "S", "Ż": "Z"})
    return text.translate(table)


def q(value, scale):
    """Quantize a Decimal/float/int to ``scale`` decimals (half-up)."""
    if value is None:
        return None
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------------------
# registry: key pools, generated rows, shared context
# --------------------------------------------------------------------------------------

class Registry(object):
    """Holds key pools and rows for every table plus lookups shared by generators."""

    def __init__(self, model, seed):
        self.model = model
        self.seed = seed
        self.pools = {}
        self.rows = {}
        self.ctx = {}
        self._gens = {}

    def rng(self, *parts):
        """A deterministic ``random.Random`` for a named purpose."""
        return random.Random("%s|%s" % (self.seed, "|".join(str(p) for p in parts)))

    def alloc(self, fqn, n):
        """Allocate ``n`` surrogate keys for ``fqn`` (idempotent per table)."""
        base = self.model.table(fqn).index * ID_BLOCK
        if n >= 90000:
            raise ValueError("too many rows for %s" % fqn)
        pool = list(range(base + 1, base + n + 1))
        self.pools[fqn] = pool
        return pool

    def extra_ids(self, fqn, n):
        """Keys beyond the pool (used for injected rows that silver drops)."""
        base = self.model.table(fqn).index * ID_BLOCK
        start = base + 90000
        return list(range(start + 1, start + n + 1))

    def pick(self, fqn, rnd):
        pool = self.pools[fqn]
        return pool[rnd.randrange(len(pool))]

    def gen(self, fqn):
        if fqn not in self._gens:
            self._gens[fqn] = TableGen(self, self.model.table(fqn))
        return self._gens[fqn]


# --------------------------------------------------------------------------------------
# per-row context
# --------------------------------------------------------------------------------------

_LOCALES = ["SWE"] * 30 + ["NOR"] * 14 + ["DNK"] * 12 + ["FIN"] * 14 + ["DEU"] * 16 + ["NLD"] * 7 + ["POL"] * 7


class RowCtx(object):
    __slots__ = ("rnd", "i", "anchor", "is_master", "country", "fixed", "row", "_person",
                 "_city", "table")

    def __init__(self, rnd, i, anchor, is_master, country, fixed, table):
        self.rnd = rnd
        self.i = i
        self.anchor = anchor
        self.is_master = is_master
        self.country = country or _LOCALES[rnd.randrange(len(_LOCALES))]
        self.fixed = fixed
        self.row = None
        self._person = None
        self._city = None
        self.table = table

    @property
    def person(self):
        if self._person is None:
            c = self.country if self.country in world.FIRST_NAMES else "SWE"
            self._person = (self.rnd.choice(world.FIRST_NAMES[c]), self.rnd.choice(world.LAST_NAMES[c]))
        return self._person

    @property
    def city(self):
        if self._city is None:
            c = self.country if self.country in world.CITIES else "SWE"
            self._city = self.rnd.choice(world.CITIES[c])
        return self._city


# --------------------------------------------------------------------------------------
# value helpers shared with curated generators
# --------------------------------------------------------------------------------------

def postal_code(template, rnd):
    out = []
    for ch in template:
        if ch == "#":
            out.append(str(rnd.randint(0, 9)))
        elif ch == "@":
            out.append(rnd.choice("ABCDEFGHJKLMNPRSTVWXZ"))
        else:
            out.append(ch)
    return "".join(out)


def phone(country, rnd, e164=False):
    """Obviously fake mobile numbers <cc> <prefix> 000 <n digits> with the national length."""
    cc, mid, n = world.COUNTRY_PHONE.get(country, world.COUNTRY_PHONE["SWE"])
    tail = "%0*d" % (n, rnd.randint(0, 10 ** n - 1))
    if e164:
        return "%s%s000%s" % (cc, mid, tail)
    return "%s %s 000 %s" % (cc, mid, tail)


def person_name(country, rnd):
    c = country if country in world.FIRST_NAMES else "SWE"
    return "%s %s" % (rnd.choice(world.FIRST_NAMES[c]), rnd.choice(world.LAST_NAMES[c]))


def email_for(first, last, rnd, n=None):
    local = "%s.%s" % (ascii_fold(first).lower(), ascii_fold(last).lower().replace(" ", ""))
    local = re.sub(r"[^a-z0-9.]", "", local)
    if n is None:
        n = rnd.randint(1, 9999)
    return "%s.%d@example.com" % (local, n)


def user_id(first, last, rnd):
    base = (ascii_fold(first)[:1] + ascii_fold(last)[:6]).upper()
    base = re.sub(r"[^A-Z]", "", base)
    return "%s%02d" % (base, rnd.randint(1, 99))


def street_address(country, rnd):
    streets = world.STREETS.get(country, world.STREETS["SWE"])
    st = rnd.choice(streets)
    num = rnd.randint(1, 148)
    if country == "POL":
        return "%s %d" % (st, num)
    if country in ("NLD", "DEU", "SWE", "NOR", "DNK", "FIN"):
        return "%s %d" % (st, num)
    return "%d %s" % (num, st)


def rand_dt(rnd, start, end):
    """Uniform random datetime between two dates/datetimes."""
    if not isinstance(start, datetime.datetime):
        start = datetime.datetime.combine(start, datetime.time())
    if not isinstance(end, datetime.datetime):
        end = datetime.datetime.combine(end, datetime.time(23, 59, 59))
    span = int((end - start).total_seconds())
    if span <= 0:
        return start
    return start + datetime.timedelta(seconds=rnd.randint(0, span))


def as_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime.datetime):
        return v
    return datetime.datetime.combine(v, datetime.time())


# --------------------------------------------------------------------------------------
# date roles and temporal order
# --------------------------------------------------------------------------------------

_END_TOKENS = {"end", "until", "to", "closed", "close", "termination", "terminated", "dissolution",
               "decommissioning", "discontinuation", "divestiture", "cancellation", "cancelled",
               "withdrawal", "retirement", "retired", "finish", "completion", "completed", "resolution",
               "resolved", "closure", "deactivation", "exit", "departure"}
_START_TOKENS = {"start", "from", "effective", "valid", "launch", "open", "opened", "opening",
                 "commissioning", "installation", "install", "installed", "purchase", "acquisition",
                 "enrollment", "enrolment", "formation", "hire", "registration", "incorporation",
                 "founded", "established", "begin", "onboarding", "activation", "introduction"}
_FUTURE_TOKENS = {"due", "expiry", "expiration", "expires", "expire", "deadline", "renewal", "maturity",
                  "requalification", "review"}


def date_role(name):
    t = tokens(name)
    s = set(t)
    if "birth" in s or name.endswith("dob"):
        return "birth"
    if s & {"created", "creation", "inserted"} or name in ("record_audit_created", "entry_date"):
        return "created"
    if s & {"updated", "modified", "changed"}:
        return "modified"
    if t and t[0] == "next":
        return "future"
    if t and t[0] in ("last", "latest", "previous", "prior", "most"):
        # backward-looking even when the name mentions a review/due event (last_review_date)
        return "past"
    if s & {"warranty", "depreciation"} and s & _END_TOKENS:
        return "future"
    if s & _FUTURE_TOKENS:
        return "future"
    if s & _END_TOKENS:
        return "end"
    if s & _START_TOKENS:
        return "start"
    return "event"


_ORDER_PAIRS = (
    ("start", "end"), ("begin", "end"), ("from", "to"), ("from", "until"), ("open", "close"),
    ("created", "updated"), ("created", "modified"), ("created", "closed"), ("issued", "expiry"),
    ("issue", "expiry"), ("issue", "due"), ("effective", "expiry"), ("effective", "until"),
    ("valid", "expiry"), ("order", "ship"), ("order", "delivery"), ("ship", "delivery"),
    ("shipped", "delivery"), ("entry", "exit"), ("arrival", "departure"), ("hire", "termination"),
    ("first", "last"), ("request", "approval"), ("approval", "completion"), ("purchase", "installation"),
    ("installation", "last"), ("enrollment", "last"), ("acquisition", "last"), ("billing", "due"),
    ("billing", "payment"), ("invoice", "due"), ("invoice", "payment"), ("document", "posting"),
    ("planned", "actual"), ("scheduled", "actual"), ("released", "actual"), ("manufacturing", "expiry"),
    ("manufacturing", "release"), ("start", "release"), ("capture", "withdrawal"), ("effective", "end"),
    ("formation", "dissolution"), ("launch", "discontinuation"), ("commissioning", "decommissioning"),
    ("pause", "resume"), ("start", "cancellation"), ("start", "next"), ("start", "last"),
    ("last", "next"), ("calibration", "calibration"), ("measurement", "modified"),
)


def _tok_pos(parts, token):
    for i, part in enumerate(parts):
        if part == token or (len(token) >= 4 and part.startswith(token)):
            return i
    return -1


def temporal_edges(names):
    edges = []
    for lo_tok, hi_tok in _ORDER_PAIRS:
        if lo_tok == hi_tok:
            continue
        lows = [n for n in names if _tok_pos(tokens(n), lo_tok) >= 0]
        highs = [n for n in names if _tok_pos(tokens(n), hi_tok) >= 0]
        for lo in lows:
            lp = tokens(lo)
            if _tok_pos(lp, hi_tok) >= 0 and _tok_pos(lp, hi_tok) > _tok_pos(lp, lo_tok):
                continue
            for hi in highs:
                if hi == lo:
                    continue
                hp = tokens(hi)
                if _tok_pos(hp, lo_tok) >= 0 and _tok_pos(hp, lo_tok) > _tok_pos(hp, hi_tok):
                    continue
                if (lo, hi) not in edges and (hi, lo) not in edges:
                    edges.append((lo, hi))
    # created <= every other timestamp-ish column except birth/start dates of masters
    return edges


def temporal_plan(names):
    edges = temporal_edges(names)
    parents = dict((n, []) for n in names)
    for lo, hi in edges:
        parents[hi].append(lo)
    resolved, plan = set(), []
    remaining = list(names)
    guard = 0
    while remaining and guard < 100:
        guard += 1
        ready = [n for n in remaining if all(p in resolved for p in parents[n])]
        if not ready:
            # break cycles deterministically: drop the edges into the first remaining node
            parents[remaining[0]] = []
            continue
        for n in ready:
            if parents[n]:
                plan.append((n, list(parents[n])))
            resolved.add(n)
            remaining.remove(n)
    return plan


# --------------------------------------------------------------------------------------
# value rules
# --------------------------------------------------------------------------------------

_POSITIVE_STATES = ("active", "completed", "complete", "approved", "released", "posted", "paid",
                    "delivered", "closed", "valid", "granted", "passed", "accepted", "cleared",
                    "fulfilled", "available", "confirmed", "processed", "compliant", "fully_qualified",
                    "matched", "validated", "received", "applied", "shipped", "settled", "in_stock",
                    "operational", "certified", "current", "open", "standard", "pass", "none")
_NEGATIVE_STATES = ("cancelled", "canceled", "failed", "rejected", "blocked", "suspended", "fraud",
                    "recalled", "deleted", "terminated", "error", "expired", "decommissioned",
                    "confirmed_fraud", "written_off", "disputed", "quarantine", "non_compliant",
                    "churned", "lapsed", "divested", "discontinued", "obsolete", "reversed")


def enum_weights(values):
    w = [1.0 / (i + 1) ** 0.7 for i in range(len(values))]
    for i, v in enumerate(values):
        lv = v.lower()
        if lv in _NEGATIVE_STATES:
            w[i] *= 0.25
    for i, v in enumerate(values):
        if v.lower() in _POSITIVE_STATES:
            w[i] = max(w[i], sum(w) * 1.3)
            break
    return w


_BOOL_LOW = {"fraud", "recall", "hold", "blocked", "block", "lock", "locked", "dispute", "disputed",
             "reversal", "reversed", "hazard", "hazardous", "hazmat", "deviation", "overpayment", "short",
             "exempt", "exemption", "override", "deleted", "suspended", "out", "merged", "rework",
             "cancelled", "error", "failed", "damaged", "deceased", "statistical", "intercompany",
             "breach", "quarantine", "expired", "rejected", "gift", "ccpa", "minor", "parental",
             "allergen", "flammable", "licensed", "seasonal", "dangerous", "special", "manual",
             "dsr", "subject", "deduction", "retention", "write", "obsolete", "critical", "partial"}
_BOOL_HIGH = {"certified", "enabled", "active", "allowed", "verified", "compliant", "compliance",
              "complete", "integrated", "approved", "eligible", "consent", "gdpr", "valid", "recyclable",
              "sustainable", "edi", "capable", "display", "trail", "sox", "backflush", "current",
              "planning", "tracking", "required", "controlled", "managed", "available", "posting",
              "qualified", "released", "leading", "opt", "in", "default", "primary", "shipping"}


def bool_probability(name):
    s = set(tokens(name))
    if "opt" in s and "out" in s:
        return 0.06
    if s & _BOOL_LOW:
        return 0.07
    if s & _BOOL_HIGH:
        return 0.82
    return 0.35


# (token set, lo, hi, decimals) - first rule whose tokens intersect the column tokens wins
_NUM_RULES = [
    ({"latitude"}, 54.5, 69.0, 6),
    ({"longitude"}, 5.5, 28.5, 6),
    ({"nps"}, 0, 10, 0),
    ({"oee"}, 58.0, 88.0, 2),
    ({"ph"}, 3.5, 9.0, 2),
    ({"accuracy", "efficiency", "otif", "osa", "fill"}, 62.0, 98.5, 2),
    ({"utilization", "utilisation"}, 50.0, 95.0, 2),
    ({"bias"}, 0.5, 12.0, 2),
    ({"yield"}, 90.0, 99.5, 2),
    ({"percent", "percentage", "pct"}, 0.5, 35.0, 2),
    ({"probability", "confidence", "likelihood"}, 0.55, 0.99, 4),
    ({"multiplier", "factor"}, 1.0, 2.5, 2),
    ({"score", "rating", "index"}, 40.0, 98.0, 1),
    ({"temperature", "celsius"}, 2.0, 25.0, 1),
    ({"humidity"}, 30.0, 70.0, 1),
    ({"voltage"}, 230.0, 690.0, 0),
    ({"crew"}, 2, 8, 0),
    ({"kwh", "energy"}, 50.0, 250000.0, 2),
    ({"kw", "power"}, 2.0, 650.0, 2),
    ({"sqft", "footage", "square", "area"}, 8000.0, 420000.0, 2),
    ({"weight", "kg", "mass"}, 0.2, 1800.0, 3),
    ({"ml", "volume", "litres", "liters"}, 30.0, 2000.0, 2),
    ({"length", "width", "height", "depth", "meters", "metres", "distance", "km"}, 0.5, 120.0, 2),
    ({"speed"}, 600.0, 36000.0, 2),
    ({"capacity"}, 200.0, 60000.0, 2),
    ({"headcount", "employees", "fte"}, 12, 650, 0),
    ({"mtbf", "between"}, 250.0, 4200.0, 2),
    ({"mttr", "repair"}, 0.5, 8.0, 2),
    ({"usage"}, 800.0, 42000.0, 2),
    ({"days"}, 2, 120, 0),
    ({"hours"}, 1.0, 24.0, 2),
    ({"minutes"}, 5.0, 240.0, 2),
    ({"seconds"}, 5, 3600, 0),
    ({"years"}, 3, 20, 0),
    ({"points"}, 0.0, 12000.0, 2),
    ({"price", "msrp", "rsp"}, 0.8, 45.0, 2),
    ({"rate"}, 0.5, 15.0, 4),
    ({"quantity", "qty", "units", "pieces", "cases", "pallets"}, 10.0, 4800.0, 0),
    ({"count", "number", "num", "doors", "lines", "positions"}, 1, 40, 0),
    ({"cost"}, 15.0, 45000.0, 2),
    ({"amount", "value", "total", "revenue", "balance", "spend", "budget", "limit", "acv", "sales",
      "fee", "charge", "payment", "liability", "accrual", "deduction", "exposure", "cltv", "income",
      "margin", "profit", "loss", "variance", "impact"}, 50.0, 85000.0, 2),
    ({"discount", "tax", "vat", "rebate", "allowance"}, 0.0, 4500.0, 2),
    ({"level", "rank", "priority", "sequence", "seq", "position", "item", "version", "tier", "order",
      "step", "stage"}, 1, 9, 0),
]


def numeric_rule(col, table=None):
    t = tokens(col.name)
    s = set(t)
    # fractions declared as decimals (0-1)
    frac = col.base == "DECIMAL" and (col.precision - col.scale) <= 1
    desc = col.description.lower()
    if frac or "as a decimal" in desc or "0.0000 to 1.0000" in desc or "(0-1)" in desc:
        if s & {"percent", "percentage", "pct", "rate", "share", "probability", "confidence", "score",
                "ratio", "likelihood", "propensity"}:
            return 0.02, 0.6 if (s & {"rate", "discount"}) else 0.98, 4
    if s & {"exchange"} and s & {"rate"}:
        return 0.08, 1.2, 6
    if t and (t[-1] == "year" or s & {"fiscal"} and "year" in s):
        return "YEAR"
    if "period" in s or (t and t[-1] == "month"):
        return "MONTH"
    if t and t[-1] in ("week",):
        return 1, 52, 0
    if t and t[-1] in ("day",) and col.base in ("INT", "BIGINT"):
        return 1, 28, 0
    if "per" in s and s & {"kwh", "energy"}:
        return 2.0, 150.0, 4
    for rule_tokens, lo, hi, dec in _NUM_RULES:
        if s & rule_tokens:
            return lo, hi, dec
    if col.base in ("INT", "BIGINT"):
        if "code" in s or "id" in s or "key" in s:
            return 100000, 999999, 0
        return 1, 100, 0
    return 1.0, 1000.0, 2


def _clamp_hi(col, hi):
    if col.base == "DECIMAL":
        return min(hi, float(col.max_abs) * 0.98)
    if col.base == "INT":
        return min(hi, 2_000_000_000)
    return hi


# --------------------------------------------------------------------------------------
# string semantics
# --------------------------------------------------------------------------------------

_PERSON_NAME_TOKENS = {"contact", "person", "supervisor", "manager", "owner", "inspector", "approver",
                       "buyer", "planner", "auditor", "analyst", "operator", "technician", "driver",
                       "rep", "representative", "author", "signatory", "recipient", "customer",
                       "requester", "requestor", "reviewer", "coordinator", "lead", "responsible",
                       "assignee", "investigator", "champion", "sponsor", "complainant", "maker",
                       "requisitioner", "assistant", "approved", "submitted", "employee", "reporter",
                       "initiator", "originator", "caller", "picker", "checker", "verified", "released",
                       "inspected", "signed", "witness", "agent", "consumer", "shopper"}
_JOB_TITLES = ["Category Manager", "Senior Buyer", "Buyer", "Head of Purchasing", "Supply Chain Manager",
               "Logistics Coordinator", "Key Account Manager", "Store Operations Manager", "Replenishment Planner",
               "Commercial Director", "Assortment Manager", "Quality Manager", "Pricing Analyst"]
_QA_TITLES = ["QA Manager", "Quality Control Supervisor", "Head of Quality Assurance", "Laboratory Manager",
              "Qualified Person (QP)"]
_TEXT_TOKENS = {"description", "comment", "comments", "notes", "note", "remark", "remarks", "summary",
                "justification", "instruction", "instructions", "narrative", "text", "message",
                "observation", "observations", "findings", "details", "detail", "statement", "rationale"}
_REASON_TOKENS = {"reason", "cause", "explanation"}
_CODE_TOKENS = {"code", "cd", "ref", "reference", "number", "no", "num", "id", "key", "tag", "identifier",
                "nbr", "barcode", "serial", "lot", "batch", "sku"}


def _domain_of(table):
    return table.domain if table.domain in texts.NOTES else "product"


def _title(table):
    return table.name.replace("_", " ").title()


def make_string_fn(col, table, reg):
    """Return f(ctx) -> str for a STRING column without enum."""
    t = tokens(col.name)
    s = set(t)
    last = t[-1] if t else ""
    dom = _domain_of(table)
    pattern = col.pattern
    desc = col.description.lower()

    def check(fn):
        if pattern is None:
            return fn
        rx = pattern

        def wrapped(ctx):
            v = fn(ctx)
            if v is not None and rx.fullmatch(v):
                return v
            for _ in range(3):
                v = regexgen.generate(col.regex, ctx.rnd)
                if rx.fullmatch(v):
                    return v
            return v
        return wrapped

    qualified = "%s.%s" % (table.name, col.name)
    if col.name in texts.CODE_VALUES and pattern is not None:
        vals = [v for v in texts.CODE_VALUES[col.name] if pattern.fullmatch(v)]
        if vals:
            return lambda ctx: ctx.rnd.choice(vals)
    for key in (qualified, col.name):
        if key in texts.PHRASES:
            vals = [v for v in texts.PHRASES[key] if pattern is None or pattern.fullmatch(v)]
            if vals:
                return lambda ctx, vals=vals: ctx.rnd.choice(vals)

    if "email" in s:
        person = (bool(s & {"primary", "contact", "personal", "person", "responsible"}) or table.domain == "consumer"
                  or "contact" in table.name or table.name == "rep")

        def f(ctx):
            if person:
                fn_, ln_ = ctx.person
                return email_for(fn_, ln_, ctx.rnd)
            box = ctx.rnd.choice(["orders", "info", "finance", "quality", "planning", "logistics", "service"])
            return "%s.%s@example.com" % (box, ascii_fold(ctx.city[0]).lower().replace(" ", ""))
        return check(f)

    if s & {"phone", "fax", "mobile", "telephone", "tel"}:
        e164 = bool(pattern is not None and " " not in col.regex and "\\s" not in col.regex)
        return check(lambda ctx: phone(ctx.country, ctx.rnd, e164=e164))

    if s & {"url", "website", "uri", "link", "homepage"}:
        return check(lambda ctx: "https://www.%s/%s/%s" % (world.WEBSHOP, table.name.replace("_", "-"),
                                                            ctx.rnd.randint(1000, 99999)))

    if "ip" in s and ("address" in s or last == "ip"):
        return check(lambda ctx: ctx.rnd.choice(["192.0.2.", "198.51.100.", "203.0.113."]) + str(ctx.rnd.randint(1, 254)))

    if "given" in s or ("first" in s and "name" in s):
        return check(lambda ctx: ctx.person[0])
    if "family" in s or "surname" in s or ("last" in s and "name" in s):
        return check(lambda ctx: ctx.person[1])
    if last == "name" and s & {"full", "display"}:
        # the row's own person, consistent with first_name / last_name / e-mail
        return check(lambda ctx: "%s %s" % ctx.person)
    if last == "name" and s & _PERSON_NAME_TOKENS:
        # another person in a role (approver, complainant, decision maker ...)
        return check(lambda ctx: person_name(ctx.country, ctx.rnd))
    if last == "title" and s & {"job", "position"}:
        return check(lambda ctx: ctx.rnd.choice(_JOB_TITLES))
    if last == "title" and s & {"signatory", "authorized", "authorised"}:
        return check(lambda ctx: ctx.rnd.choice(_QA_TITLES))
    if last == "by" or (last == "user" and s & {"by", "created", "modified", "changed", "approved"}) or \
            s & {"userid", "username"} or (last in ("user",) and len(t) > 1):
        if pattern is not None or "user" in s or s & {"created", "modified", "changed"}:
            return check(lambda ctx: user_id(ctx.person[0], ctx.person[1], ctx.rnd)
                         if ctx.rnd.random() < 0.85 else ctx.rnd.choice(texts.USERS))
        return check(lambda ctx: "%s %s" % ctx.person)

    if (s & {"address", "street"} and s & {"line", "1", "street", "line1"} and "2" not in s and "3" not in s
            and "line2" not in s and "line3" not in s) or (t[:2] == ["line", "1"]) or last == "street":
        return check(lambda ctx: street_address(ctx.country, ctx.rnd))
    if (s & {"address", "line"} and ("2" in s or "line2" in s)) or t[:2] == ["line", "2"]:
        return check(lambda ctx: None if ctx.rnd.random() < 0.7 else ctx.rnd.choice(
            ["Floor 2", "Floor 3", "Building B", "Unit 4", "Apt 12", "c/o Reception", "Dock 3"]))
    if (s & {"address", "line"} and ("3" in s or "line3" in s)) or t[:2] == ["line", "3"]:
        return check(lambda ctx: None if ctx.rnd.random() < 0.9 else "Gate %d" % ctx.rnd.randint(1, 9))
    if "address" in s and not s & {"email", "ip", "code", "id", "type", "status", "flag", "line", "1", "2", "3",
                                    "line1", "line2", "line3", "same", "validated", "verified", "score"}:
        return check(lambda ctx: "%s, %s %s" % (street_address(ctx.country, ctx.rnd), postal_code(ctx.city[4], ctx.rnd),
                                                ctx.city[0]))
    if "standardized" in s and "address" in s:
        return check(lambda ctx: "%s, %s %s, %s" % (street_address(ctx.country, ctx.rnd),
                                                    postal_code(ctx.city[4], ctx.rnd), ctx.city[0],
                                                    world.COUNTRY_NAMES.get(ctx.country, "Sweden")))
    if s & {"city", "town", "municipality"}:
        return check(lambda ctx: ctx.city[0])
    if s & {"postal", "zip", "postcode", "zipcode"}:
        return check(lambda ctx: postal_code(ctx.city[4], ctx.rnd))
    if s & {"state", "province"} or (("region" in s or "subdivision" in s) and "code" in s and pattern is None):
        return check(lambda ctx: ctx.city[1])
    if "region" in s or ("geographic" in s and "code" not in s):
        return check(lambda ctx: {"SWE": "Nordics", "NOR": "Nordics", "DNK": "Nordics", "FIN": "Nordics",
                                  "DEU": "DACH", "NLD": "Benelux", "POL": "CEE"}.get(ctx.country, "Nordics"))
    if s & {"country", "jurisdiction", "nationality", "origin", "market"} and (
            "code" in s or pattern is not None or "origin" in s or "jurisdiction" in s):
        return check(lambda ctx: ctx.country)
    if "country" in s:
        return check(lambda ctx: world.COUNTRY_NAMES.get(ctx.country, "Sweden"))
    if "currency" in s:
        return check(lambda ctx: world.COUNTRY_CCY.get(ctx.country, "EUR"))
    if s & {"language", "locale", "lang"}:
        two = pattern is not None and "{2}$" in col.regex and "-" not in col.regex
        return check(lambda ctx: world.COUNTRY_LANG.get(ctx.country, "sv-SE")[:2] if two
                     else world.COUNTRY_LANG.get(ctx.country, "sv-SE"))
    if s & {"timezone", "tz"} or ("time" in s and "zone" in s):
        return check(lambda ctx: world.COUNTRY_TZ.get(ctx.country, "Europe/Stockholm"))
    if s & {"gtin", "ean"}:
        return check(lambda ctx: world.gtin13("7350099", ctx.rnd.randint(1000, 99999)))
    if "gln" in s:
        return check(lambda ctx: world.gtin13("7350098", ctx.rnd.randint(1000, 99999)))
    if "sscc" in s:
        return check(lambda ctx: "37350099" + "%010d" % ctx.rnd.randint(0, 9999999999))
    if "duns" in s:
        return check(lambda ctx: "%09d" % ctx.rnd.randint(100000000, 999999999))
    if "upc" in s:
        return check(lambda ctx: "%012d" % ctx.rnd.randint(10 ** 10, 10 ** 12 - 1))
    if s & {"uom", "unit"} and not s & {"business", "price", "cost"}:
        return check(lambda ctx: ctx.rnd.choice(["EA", "EA", "EA", "CS", "KG", "L", "PAL"]))
    if s & {"carrier"}:
        if last == "name":
            # the carrier's name matches the carrier code of the same row
            return check(lambda ctx: texts.CARRIER_NAMES.get(ctx.row.get("carrier_code"),
                                                             texts.CARRIER_NAMES[ctx.rnd.choice(texts.CARRIERS)]))
        return check(lambda ctx: ctx.rnd.choice(texts.CARRIERS))
    if s & {"manufacturer", "vendor", "make", "oem"} and not s & _CODE_TOKENS:
        return check(lambda ctx: ctx.rnd.choice(texts.MANUFACTURERS))
    if "supplier" in s and "name" in s:
        return check(lambda ctx: ctx.rnd.choice(texts.SUPPLIERS))
    if "department" in s:
        return check(lambda ctx: ctx.rnd.choice(texts.DEPARTMENTS))
    if "plc" in s:
        return check(lambda ctx: ctx.rnd.choice(texts.PLC_TYPES))
    if "safety" in s and "certification" in s:
        return check(lambda ctx: ctx.rnd.choice(texts.CERTS))
    if s & _REASON_TOKENS and not s & _CODE_TOKENS:
        bank = texts.REASONS[dom]
        return check(lambda ctx: ctx.rnd.choice(bank))
    if s & _TEXT_TOKENS:
        bank = texts.NOTES[dom]
        nullp = 0.0 if "description" in s else 0.35

        def f(ctx):
            if nullp and ctx.rnd.random() < nullp:
                return None
            return ctx.rnd.choice(bank)
        return check(f)
    if col.enum_candidates:
        vals = col.enum_candidates
        w = enum_weights(vals)
        return check(lambda ctx: ctx.rnd.choices(vals, weights=w)[0])
    if s & {"material"} and last in ("name", "description", "material"):
        return check(lambda ctx: ctx.rnd.choice(texts.MATERIALS))
    if last in ("name", "title", "label") or "name" in s:
        return check(lambda ctx: _entity_name(table, ctx))
    if s & _CODE_TOKENS or last in ("code", "number", "ref", "reference"):
        prefix = "".join(p[0] for p in t if p not in _CODE_TOKENS)[:4].upper() or table.name[:3].upper()

        def f(ctx):
            return "%s%06d" % (prefix, ctx.rnd.randint(1, 999999))
        if pattern is not None:
            return check(smart_code_fn(prefix, col.regex, pattern))
        return check(f)
    if s & {"type", "category", "class", "classification", "segment", "group", "kind", "method", "mode",
            "status", "level", "stage", "channel", "source", "format", "frequency", "policy", "basis"}:
        vocab = _vocab_for(t)
        return check(lambda ctx: ctx.rnd.choice(vocab))
    if pattern is not None:
        return lambda ctx: regexgen.generate(col.regex, ctx.rnd)
    words = " ".join(p for p in t).title()
    return lambda ctx: "%s %s" % (words, ctx.rnd.choice(["A", "B", "C", "Standard", "Premium", "Basic"]))


def smart_code_fn(prefix, regex, pattern):
    """Prefer readable codes (prefix + running digits) when the regex allows them."""
    lo, hi = regexgen.length_bounds(regex)
    hi = hi if hi is not None else lo + 10
    target = max(lo, min(hi, len(prefix) + 6))
    n_digits = target - len(prefix)
    use_prefix = n_digits >= 3 and pattern.fullmatch(prefix + "1" * n_digits) is not None
    if not use_prefix:
        n_digits = target
        if pattern.fullmatch("1" * n_digits) is None:
            return lambda ctx: regexgen.generate(regex, ctx.rnd)

    def f(ctx):
        num = "".join(str(ctx.rnd.randint(0, 9)) for _ in range(n_digits))
        return (prefix + num) if use_prefix else num
    return f


_VOCABS = {
    "status": ["active", "inactive", "pending", "completed", "on_hold"],
    "type": ["standard", "special", "seasonal", "promotional", "recurring"],
    "category": ["food", "beverage", "personal_care", "packaging", "services"],
    "channel": ["retail", "ecommerce", "dtc", "wholesale", "foodservice"],
    "source": ["SAP_S4", "SALESFORCE", "MANUAL", "EDI", "WMS"],
    "frequency": ["daily", "weekly", "monthly", "quarterly", "annual"],
    "method": ["standard", "manual", "automatic", "electronic"],
    "level": ["low", "medium", "high"],
    "segment": ["core", "growth", "premium", "value"],
}


def _vocab_for(t):
    for tok in reversed(t):
        if tok in _VOCABS:
            return _VOCABS[tok]
        if tok in ("class", "classification", "kind", "group", "mode", "format", "policy", "basis", "stage"):
            return _VOCABS["type"]
    return _VOCABS["type"]


def _entity_name(table, ctx):
    n = table.name
    rnd = ctx.rnd
    if n in ("supplier",):
        return rnd.choice(texts.SUPPLIERS)
    if n == "supplier_site":
        return "%s - %s" % (rnd.choice(texts.SUPPLIERS), ctx.city[0])
    if n == "retail_store":
        ta = rnd.choice(world.TRADE)
        return "%s %s %s" % (ta["dba"], ctx.city[0], rnd.choice(texts.STORE_SUFFIX))
    if n == "territory":
        return rnd.choice(texts.TERRITORIES)
    if n in ("trade_promotion", "event", "funding_agreement", "trade_calendar"):
        b = rnd.choice(world.BRANDS)
        return "%s %s %d" % (b["name"], rnd.choice(texts.PROMO_THEMES), ctx.anchor.year)
    if n in ("material", "formulation_ingredient", "bom_line"):
        return rnd.choice(texts.MATERIALS)
    if n in ("formulation", "packaging_spec", "label_spec", "product_bom", "gtin_registry", "specification",
             "inspection_plan"):
        sku = rnd.choice(world.SKUS)
        return "%s - %s" % (sku["full_name"], _title(table))
    if n in ("network_node", "storage_location", "distribution_facility"):
        dc = rnd.choice(world.DCS)
        return "%s %s" % (dc["name"], rnd.choice(["Zone A", "Zone B", "Ambient", "Chilled", "Bulk", "Pick face"]))
    if n == "price_list":
        return "%s price list %d" % (rnd.choice(["Nordic grocery", "DACH drugstore", "Foodservice", "Benelux",
                                                 "Export", "Key accounts"]), ctx.anchor.year)
    if n == "rep":
        return "%s %s" % ctx.person
    if n in ("demand_plan", "forecast_version"):
        return "%s %d-%02d %s" % ("Demand plan" if n == "demand_plan" else "Forecast",
                                  ctx.anchor.year, ctx.anchor.month,
                                  rnd.choice(["consensus", "statistical", "budget", "S&OP final"]))
    if n == "sop_cycle":
        return "S&OP cycle %s" % ctx.anchor.strftime("%b %Y")
    if n == "network_lane":
        a, b = rnd.sample(world.DCS, 2)
        return "%s - %s %s" % (a["city"], b["city"], rnd.choice(["road", "road", "intermodal"]))
    if n == "pricing_agreement":
        ta = rnd.choice(world.TRADE)
        return "%s price agreement %d" % (ta["dba"], ctx.anchor.year)
    if n in ("promoted_price",):
        b = rnd.choice(world.BRANDS)
        return "%s %s %d" % (b["name"], rnd.choice(texts.PROMO_THEMES), ctx.anchor.year)
    if n in ("hierarchy",):
        return rnd.choice([s[1] for s in world.SUBCATEGORIES] + [c[1] for c in world.TOP_CATEGORIES])
    if n == "spend_category":
        return rnd.choice(["Raw materials - grains", "Raw materials - fruit", "Packaging - plastics",
                           "Packaging - paper", "Chemicals", "Logistics services", "Maintenance & spares",
                           "Marketing services", "Energy", "IT services"])
    return "%s %d-%03d" % (_title(table), ctx.anchor.year, ctx.i + 1)


# --------------------------------------------------------------------------------------
# table generator
# --------------------------------------------------------------------------------------

class TableGen(object):
    """Compiled column plan for one table."""

    def __init__(self, reg, table):
        self.reg = reg
        self.table = table
        self.is_master = not table.is_transactional
        self.temporal = [c.name for c in table.columns if c.base in ("DATE", "TIMESTAMP")]
        self.roles = dict((n, date_role(n)) for n in self.temporal)
        self.tplan = temporal_plan(self.temporal)
        self.coltype = dict((c.name, c.base) for c in table.columns)
        self.fns = []
        for col in table.columns:
            if col.is_pk:
                continue
            self.fns.append((col.name, self._compile(col)))
        self._plan_coherence()

    # ---- compile -----------------------------------------------------------------
    def _compile(self, col):
        table = self.table
        nullable = bool(_NULLABLE_RX.search(col.description))
        if col.fk and not col.is_pk:
            return self._fk_fn(col)
        if col.base in ("DATE", "TIMESTAMP"):
            return self._date_fn(col, nullable)
        if col.base == "BOOLEAN":
            p = bool_probability(col.name)
            return lambda ctx: ctx.rnd.random() < p
        if col.base in ("INT", "BIGINT", "DECIMAL", "DOUBLE", "FLOAT"):
            return self._num_fn(col, nullable)
        if col.enum:
            vals = col.enum
            w = enum_weights(vals)
            cum = []
            acc = 0.0
            for x in w:
                acc += x
                cum.append(acc)
            nullp = 0.5 if nullable else 0.0
            if nullp:
                return lambda ctx: None if ctx.rnd.random() < nullp else ctx.rnd.choices(vals, cum_weights=cum)[0]
            return lambda ctx: ctx.rnd.choices(vals, cum_weights=cum)[0]
        fn = make_string_fn(col, table, self.reg)
        if nullable and not col.pattern:
            return lambda ctx: None if ctx.rnd.random() < 0.55 else fn(ctx)
        return fn

    def _fk_fn(self, col):
        parent = col.fk_table
        selfref = parent == self.table.fqn
        t = set(tokens(col.name))
        optional = bool(t & {"parent", "predecessor", "merged", "reversal", "referral", "previous", "next",
                             "converted", "replaced", "replacement", "alternate", "alternative", "secondary",
                             "original", "substitute", "superseded", "successor", "reversed", "related",
                             "duplicate", "linked"})
        nullable = bool(_NULLABLE_RX.search(col.description))
        null_p = 0.7 if selfref else (0.55 if optional else (0.25 if nullable else 0.0))
        reg = self.reg

        def f(ctx):
            if null_p and ctx.rnd.random() < null_p:
                return None
            pool = reg.pools.get(parent)
            if not pool:
                return None
            if selfref:
                if ctx.i <= 0:
                    return None
                return pool[ctx.rnd.randrange(0, min(ctx.i, len(pool)))]
            return pool[ctx.rnd.randrange(len(pool))]
        return f

    def _date_fn(self, col, nullable):
        role = self.roles[col.name]
        is_ts = col.base == "TIMESTAMP"
        master = self.is_master

        def f(ctx):
            rnd = ctx.rnd
            a = ctx.anchor
            if role == "birth":
                v = datetime.datetime(1950, 1, 1) + datetime.timedelta(days=rnd.randint(0, 20800))
            elif role == "created":
                v = a if master else a - datetime.timedelta(minutes=rnd.randint(0, 2880))
            elif role == "modified":
                hi = world.EXTRACT_TS if master else min(world.EXTRACT_TS, a + datetime.timedelta(days=40))
                lo = a
                if master:
                    # recent edits are more likely
                    span = (hi - lo).total_seconds()
                    v = lo + datetime.timedelta(seconds=int(span * (rnd.random() ** 0.5)))
                else:
                    v = rand_dt(rnd, lo, hi)
            elif role == "start":
                v = a - datetime.timedelta(days=rnd.randint(0, 60)) if master else \
                    a - datetime.timedelta(days=rnd.randint(0, 20))
            elif role == "end":
                if master and rnd.random() < 0.8:
                    return None
                if not master and nullable and rnd.random() < 0.5:
                    return None
                v = a + datetime.timedelta(days=rnd.randint(7, 900 if master else 60))
                if v > world.EXTRACT_TS:
                    return None
            elif role == "future":
                if nullable and rnd.random() < 0.4:
                    return None
                if master:
                    # next/due/expiry dates of master data are relative to the extract date
                    v = world.EXTRACT_TS + datetime.timedelta(days=rnd.randint(-45, 420), minutes=rnd.randint(0, 900))
                    if v < a:
                        v = a + datetime.timedelta(days=rnd.randint(30, 400))
                else:
                    v = a + datetime.timedelta(days=rnd.randint(14, 420))
            elif role == "past":
                if master:
                    v = world.EXTRACT_TS - datetime.timedelta(days=rnd.randint(1, 400), minutes=rnd.randint(0, 900))
                    if v < a:
                        v = rand_dt(rnd, a, world.EXTRACT_TS)
                else:
                    v = a - datetime.timedelta(days=rnd.randint(0, 90))
            else:
                if nullable and rnd.random() < 0.45:
                    return None
                if master:
                    v = rand_dt(rnd, a, min(world.EXTRACT_TS, a + datetime.timedelta(days=700)))
                else:
                    v = a + datetime.timedelta(days=rnd.randint(-2, 12), minutes=rnd.randint(0, 600))
            v = clamp_role(v, role)
            if is_ts:
                return v.replace(microsecond=0)
            return v.date()
        return f

    def _num_fn(self, col, nullable):
        rule = numeric_rule(col, self.table)
        base = col.base
        scale = col.scale if base == "DECIMAL" else 0
        nullp = 0.4 if nullable else 0.0

        if rule == "YEAR":
            def f(ctx):
                return ctx.anchor.year
            return f
        if rule == "MONTH":
            def f(ctx):
                return ctx.anchor.month if base != "DECIMAL" else Decimal(ctx.anchor.month)
            return f
        toks = set(tokens(col.name))
        if toks & {"gtin", "ean", "upc"}:
            # barcode numbers typed as numbers in the model: a valid GTIN-13 / UPC-A, never an amount
            upc = "upc" in toks

            def f(ctx):
                if upc:
                    body = "0%010d" % ctx.rnd.randint(0, 10 ** 10 - 1)
                    code = body + world._check_digit(body)
                else:
                    code = world.gtin13("7350099", ctx.rnd.randint(1000, 99999))
                return Decimal(code) if base == "DECIMAL" else int(code)
            return f
        lo, hi, dec = rule
        hi = _clamp_hi(col, hi)
        lo = min(lo, hi)
        if base in ("INT", "BIGINT"):
            ilo, ihi = int(round(lo)), int(round(hi))

            def f(ctx):
                if nullp and ctx.rnd.random() < nullp:
                    return None
                return ctx.rnd.randint(ilo, max(ilo, ihi))
            return f
        places = min(dec, scale) if base == "DECIMAL" else dec
        # skew towards the lower part of wide ranges (amounts are log-normal-ish)
        wide = hi / max(lo, 0.01) > 50

        def f(ctx):
            if nullp and ctx.rnd.random() < nullp:
                return None
            r = ctx.rnd.random()
            if wide:
                v = lo + (hi - lo) * (r ** 2.2)
            else:
                v = lo + (hi - lo) * r
            if base == "DECIMAL":
                return q(round(v, places), scale)
            return round(v, places)
        return f

    # ---- rows -----------------------------------------------------------------------
    def anchor_for(self, rnd):
        if self.is_master:
            return rand_dt(rnd, world.MASTER_START, datetime.date(2023, 12, 31))
        return rand_dt(rnd, world.TXN_START, world.TXN_END)

    def row(self, i, rnd, fixed=None, anchor=None, country=None):
        """Build one row: ``fixed`` values are kept, every other column is generated."""
        fixed = fixed or {}
        if anchor is None:
            anchor = self.anchor_for(rnd)
        elif not isinstance(anchor, datetime.datetime):
            anchor = datetime.datetime.combine(anchor, datetime.time(rnd.randint(6, 20), rnd.randint(0, 59),
                                                                     rnd.randint(0, 59)))
        ctx = RowCtx(rnd, i, anchor, self.is_master, country or fixed.get("country_code"), fixed, self.table)
        row = {}
        ctx.row = row
        pk = self.table.pk
        if pk in fixed:
            row[pk] = fixed[pk]
        for name, fn in self.fns:
            if name in fixed:
                row[name] = fixed[name]
            else:
                row[name] = fn(ctx)
        ctx.row = row
        self.enforce_order(row, fixed, rnd)
        if self.coherence:
            self.cohere(row, fixed, rnd)
        return row

    # ---- numeric coherence for generic rows ---------------------------------------
    def _plan_coherence(self):
        names = [c.name for c in self.table.columns]
        num = set(c.name for c in self.table.columns if c.base in ("DECIMAL", "INT", "BIGINT") and not c.fk)
        pairs = []
        for n in names:
            for a, b in (("_min", "_max"), ("min_", "max_"), ("_lower", "_upper"), ("lower_", "upper_"),
                         ("minimum_", "maximum_")):
                if a in n:
                    other = n.replace(a, b)
                    if other in num and n in num:
                        pairs.append((n, other))
        qty = []
        for first in ("ordered_quantity", "quantity_ordered", "order_quantity", "requested_quantity", "planned_quantity",
                      "expected_quantity", "quantity"):
            if first in num:
                for second in ("shipped_quantity", "quantity_shipped", "delivered_quantity", "received_quantity",
                               "quantity_received", "confirmed_quantity", "picked_quantity", "actual_quantity"):
                    if second in num:
                        qty.append((first, second))
                break
        money = None
        if "subtotal_amount" in num and "total_amount" in num:
            money = ("subtotal_amount", "total_amount")
        elif "gross_amount" in num and "net_amount" in num:
            money = ("gross_amount", "net_amount")
        self.coherence = {"pairs": pairs, "qty": qty, "money": money, "num": num}
        if not (pairs or qty or money):
            self.coherence = None

    def cohere(self, row, fixed, rnd):
        c = self.coherence
        col = self.table.col
        for lo_name, hi_name in c["pairs"]:
            a, b = row.get(lo_name), row.get(hi_name)
            if a is not None and b is not None and a > b and lo_name not in fixed and hi_name not in fixed:
                row[lo_name], row[hi_name] = b, a
        for first, second in c["qty"]:
            a, b = row.get(first), row.get(second)
            if a is not None and b is not None and b > a and second not in fixed:
                row[second] = a if col[second].base != "DECIMAL" else q(Decimal(str(a)) * Decimal("0.98"), col[second].scale)
        if c["money"]:
            base_name, total_name = c["money"]
            if any(n in fixed for n in (base_name, total_name)):
                return
            base = row.get(base_name)
            if base is None:
                return
            base = Decimal(str(base))
            scale = col[total_name].scale or 2

            def put(name, value):
                if name in col and name not in fixed and col[name].base == "DECIMAL":
                    row[name] = q(value, col[name].scale)
                    return row[name]
                return None
            if base_name == "subtotal_amount":
                disc = put("discount_amount", base * Decimal(str(round(rnd.uniform(0.0, 0.12), 4)))) or Decimal(0)
                freight = put("freight_amount", base * Decimal(str(round(rnd.uniform(0.0, 0.04), 4)))) or Decimal(0)
                tax = put("tax_amount", (base - disc) * Decimal("0.20")) or Decimal(0)
                put("cogs_amount", (base - disc) * Decimal(str(round(rnd.uniform(0.42, 0.6), 4))))
                if row.get("cogs_amount") is not None and "gross_margin_amount" in col:
                    put("gross_margin_amount", base - disc - Decimal(str(row["cogs_amount"])))
                row[total_name] = q(base - disc + freight + tax, scale)
            else:
                net = put("net_amount", base * Decimal(str(round(rnd.uniform(0.86, 0.98), 4))))
                tax = put("tax_amount", net * Decimal("0.20")) if net is not None else None
                if tax is not None and "total_amount" in col and "total_amount" not in fixed:
                    put("total_amount", net + tax)

    def enforce_order(self, row, fixed, rnd):
        for name, preds in self.tplan:
            v = row.get(name)
            if v is None:
                continue
            for p in preds:
                pv = row.get(p)
                if pv is None:
                    continue
                dv, dpv = as_dt(v), as_dt(pv)
                if self.coltype[name] == "DATE" and dv.date() >= dpv.date():
                    continue
                if dv >= dpv:
                    continue
                if name not in fixed:
                    nv = dpv + datetime.timedelta(days=rnd.randint(0, 30), minutes=rnd.randint(1, 600))
                    nv = clamp_role(nv, self.roles[name])
                    if nv < dpv:
                        nv = dpv
                    v = nv if self.coltype[name] == "TIMESTAMP" else nv.date()
                    row[name] = v
                elif p not in fixed:
                    nv = dv - datetime.timedelta(days=rnd.randint(0, 20), minutes=rnd.randint(1, 600))
                    row[p] = nv if self.coltype[p] == "TIMESTAMP" else nv.date()

    def rows(self, n, rnd=None, fixed_fn=None):
        """Generate ``n`` generic rows using the allocated key pool."""
        rnd = rnd or self.reg.rng("generic", self.table.fqn)
        pool = self.reg.pools[self.table.fqn]
        out = []
        for i in range(n):
            fixed = {self.table.pk: pool[i]}
            if fixed_fn:
                fixed.update(fixed_fn(i, rnd) or {})
            country = fixed.pop("_country", None)
            anchor = fixed.pop("_anchor", None)
            out.append(self.row(i, rnd, fixed, anchor=anchor, country=country))
        return out


def clamp_role(v, role):
    if role == "future":
        hi = datetime.datetime.combine(world.FUTURE_MAX, datetime.time(23, 59, 59))
    else:
        hi = world.EXTRACT_TS
    if v > hi:
        return hi
    return v


def ensure_filled(reg, table, rows, allow_empty=()):
    """Give every column at least one value (generic fallback for tiny tables)."""
    if not rows:
        return
    gen = reg.gen(table.fqn)
    rnd = reg.rng("fill", table.fqn)
    for col in table.columns:
        if col.name in allow_empty:
            continue
        if any(r.get(col.name) is not None for r in rows):
            continue
        fn = dict(gen.fns).get(col.name)
        if fn is None:
            continue
        for attempt in range(25):
            r0 = rows[attempt % len(rows)]
            ctx = RowCtx(rnd, attempt + 1, as_dt(gen.anchor_for(rnd)), gen.is_master, None, {}, table)
            v = fn(ctx)
            if v is not None:
                r0[col.name] = v
                break
