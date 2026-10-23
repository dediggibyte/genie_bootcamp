"""CSV formatting.

Contract of every CSV file under ``bootcamp/data`` and ``full_model/data``:

* UTF-8, header row with the exact model column names in model order, ``\\n`` line ends;
* comma separated, RFC-4180 quoting (only fields containing a comma are quoted - values
  never contain double quotes, backslashes or line breaks, so Spark's CSV reader and
  any RFC-4180 reader agree);
* every value is text: dates ``yyyy-MM-dd``, timestamps ``yyyy-MM-dd HH:mm:ss``,
  decimals with ``.`` at the column's declared scale, booleans ``true``/``false``
  (except where ``dq`` injects ``Y``/``N`` or ``1``/``0``), NULL = empty field.
"""
import csv
import datetime
import io
from decimal import Decimal, ROUND_HALF_UP


class FormatError(ValueError):
    pass


def _clean_text(s):
    if '"' in s or "\n" in s or "\r" in s or "\\" in s:
        s = s.replace('"', "'").replace("\r", " ").replace("\n", " ").replace("\\", "/")
    return s


def format_value(value, col):
    """Format one Python value for ``col``; strings already formatted pass through."""
    if value is None:
        return ""
    base = col.base
    if isinstance(value, str) and base != "STRING":
        return value                      # pre-formatted (data-quality injection)
    if base == "STRING":
        return _clean_text(str(value))
    if base == "DATE":
        if isinstance(value, datetime.datetime):
            value = value.date()
        return value.isoformat()
    if base == "TIMESTAMP":
        if not isinstance(value, datetime.datetime):
            value = datetime.datetime.combine(value, datetime.time())
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if base == "BOOLEAN":
        return "true" if value else "false"
    if base in ("INT", "BIGINT"):
        return str(int(value))
    if base == "DECIMAL":
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        value = value.quantize(Decimal(1).scaleb(-col.scale), rounding=ROUND_HALF_UP)
        if abs(value) > col.max_abs:
            raise FormatError("%s value %s exceeds %s" % (col.name, value, col.type))
        text = format(value, "f")
        if text.startswith("-") and value == 0:
            text = text[1:]
        return text
    return _clean_text(str(value))


def format_rows(table, rows):
    """Dict rows -> list of string lists in model column order."""
    cols = table.columns
    out = []
    for r in rows:
        try:
            out.append([format_value(r.get(c.name), c) for c in cols])
        except FormatError as err:
            raise FormatError("%s: %s" % (table.fqn, err))
    return out


def to_csv_bytes(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")
