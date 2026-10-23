"""Generate strings that match the (simple) regular expressions used in the model.

Supported syntax - which covers every ``value_regex`` pattern in the vendored model:
anchors ``^``/``$``, top-level and grouped alternation, groups with quantifiers, character
classes with ranges, escapes and negation, ``\\d`` ``\\s`` ``.``, and the quantifiers
``{n}`` ``{n,m}`` ``+`` ``*`` ``?``.

The generator is deterministic for a given ``random.Random`` instance. Callers should
still verify the result with ``re.fullmatch`` (the engine does).
"""
import string

_DIGITS = string.digits
_UPPER = string.ascii_uppercase
_LOWER = string.ascii_lowercase
_WORDISH = _UPPER + _DIGITS
_ANY = _UPPER + _LOWER + _DIGITS
_SPACE = " \t"


class _Parser(object):
    def __init__(self, pattern):
        self.p = pattern
        self.i = 0

    def peek(self):
        return self.p[self.i] if self.i < len(self.p) else None

    def take(self):
        ch = self.p[self.i]
        self.i += 1
        return ch

    def parse_alt(self):
        branches = [self.parse_seq()]
        while self.peek() == "|":
            self.take()
            branches.append(self.parse_seq())
        return ("alt", branches) if len(branches) > 1 else branches[0]

    def parse_seq(self):
        items = []
        while self.peek() is not None and self.peek() not in "|)":
            atom = self.parse_atom()
            if atom is None:
                continue
            items.append(self.parse_quant(atom))
        return ("seq", items)

    def parse_quant(self, atom):
        ch = self.peek()
        if ch == "?":
            self.take()
            return ("rep", atom, 0, 1)
        if ch == "*":
            self.take()
            return ("rep", atom, 0, 4)
        if ch == "+":
            self.take()
            return ("rep", atom, 1, 6)
        if ch == "{":
            j = self.p.index("}", self.i)
            body = self.p[self.i + 1:j]
            self.i = j + 1
            if "," in body:
                lo, hi = body.split(",", 1)
                lo = int(lo or 0)
                hi = int(hi) if hi.strip() else lo + 6
            else:
                lo = hi = int(body)
            return ("rep", atom, lo, hi)
        return atom

    def parse_atom(self):
        ch = self.take()
        if ch in "^$":
            return None
        if ch == "(":
            if self.p.startswith("?:", self.i):
                self.i += 2
            node = self.parse_alt()
            if self.peek() == ")":
                self.take()
            return node
        if ch == "[":
            return self.parse_class()
        if ch == ".":
            return ("set", _ANY)
        if ch == "\\":
            return self.parse_escape(in_class=False)
        return ("lit", ch)

    def parse_escape(self, in_class):
        ch = self.take()
        if ch == "d":
            return ("set", _DIGITS) if not in_class else _DIGITS
        if ch == "s":
            return ("set", " ") if not in_class else _SPACE
        if ch == "w":
            return ("set", _ANY + "_") if not in_class else _ANY + "_"
        return ("lit", ch) if not in_class else ch

    def parse_class(self):
        negate = False
        if self.peek() == "^":
            self.take()
            negate = True
        chars = []
        first = True
        while True:
            ch = self.take()
            if ch == "]" and not first:
                break
            first = False
            if ch == "\\":
                chars.extend(self.parse_escape(in_class=True))
                continue
            if self.peek() == "-" and self.i + 1 < len(self.p) and self.p[self.i + 1] != "]":
                self.take()
                end = self.take()
                if end == "\\":
                    end = self.take()
                for code in range(ord(ch), ord(end) + 1):
                    chars.append(chr(code))
                continue
            chars.append(ch)
        if negate:
            excluded = set(chars)
            pool = "".join(c for c in _ANY if c not in excluded)
        else:
            # prefer upper-case letters and digits when the class allows them (reads like
            # an ERP code); keep punctuation available but rare
            pool = "".join(dict.fromkeys(chars))
        return ("set", pool)


def parse(pattern):
    """Parse ``pattern`` into a small AST."""
    parser = _Parser(pattern)
    node = parser.parse_alt()
    return node


def _gen(node, rnd, out):
    kind = node[0]
    if kind == "lit":
        out.append(node[1])
    elif kind == "set":
        pool = node[1]
        alnum = [c for c in pool if c.isalnum()]
        # punctuation such as '-', '_', '.', '%', '+' only occasionally
        if alnum and rnd.random() < 0.97:
            out.append(rnd.choice(alnum))
        else:
            out.append(rnd.choice(pool))
    elif kind == "seq":
        for item in node[1]:
            _gen(item, rnd, out)
    elif kind == "alt":
        _gen(rnd.choice(node[1]), rnd, out)
    elif kind == "rep":
        _, inner, lo, hi = node
        # bias towards the shorter end of the range (codes look more natural)
        span = hi - lo
        n = lo + (rnd.randint(0, min(span, 4)) if span > 0 else 0)
        for _ in range(n):
            _gen(inner, rnd, out)


def generate(pattern, rnd):
    """Return one random string matching ``pattern``."""
    out = []
    _gen(parse(pattern), rnd, out)
    return "".join(out)


def length_bounds(pattern):
    """(min, max) length of strings a pattern can match (max None = unbounded)."""
    def bounds(node):
        kind = node[0]
        if kind in ("lit", "set"):
            return 1, 1
        if kind == "seq":
            lo = hi = 0
            for item in node[1]:
                a, b = bounds(item)
                lo += a
                hi = None if (hi is None or b is None) else hi + b
            return lo, hi
        if kind == "alt":
            bs = [bounds(b) for b in node[1]]
            lo = min(b[0] for b in bs)
            hi = None if any(b[1] is None for b in bs) else max(b[1] for b in bs)
            return lo, hi
        if kind == "rep":
            a, b = bounds(node[1])
            return a * node[2], (None if b is None else b * node[3])
        return 0, 0
    return bounds(parse(pattern))
