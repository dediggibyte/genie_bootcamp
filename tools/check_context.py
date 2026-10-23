#!/usr/bin/env python3
"""Validate the bootcamp's business-context folder (``bootcamp/context/``) against the industry data model.

Only the three bootcamp domains (consumer, finance, manufacturing) count: a reference to a table of
another domain (e.g. ``product.sku``) is an error, because the bootcamp catalog does not have it.

What it checks (static, no Databricks needed):

1. Every page (``bootcamp/context/domains/<domain>/pages/*.md``) has YAML front matter with the keys
   title, domain, subdomain, synonyms, description, owner, related_assets, sources; the domain
   matches its folder and the subdomain is a subdomain of that domain in the model.
2. Every ``related_assets`` entry is ``<catalog>.<schema>.<object>`` where the object is a gold
   table of that schema in the model or a known metric view (industry ``<table>_metrics`` or a
   curated bootcamp metric view).
3. Every column referenced in the SQL blocks (``alias.column`` with aliases resolved from
   ``FROM/JOIN <schema>.<table> <alias>``) exists in that table in the model.
4. Every ``table.column`` / ``schema.table.column`` written in backticks in the prose exists.
5. Every other backticked lower-case identifier is a known table, column, enum value or
   documented literal (warning only, to catch typos).
6. ``bootcamp/context/glossary.csv`` rows point to existing pages and valid assets.
7. No e-mail address other than ``@example.com`` appears anywhere in ``bootcamp/context/`` (no PII).
8. ``_domain.md`` / ``_subdomain.md`` cover every subdomain of the three bootcamp domains, and there is
   no folder for a domain outside the bootcamp.
9. At least ``MIN_PAGES_PER_DOMAIN`` pages per domain, and every curated bootcamp metric view is named by
   at least one page (the governed way to get the number).
10. Repository paths are written from the repository root (``bootcamp/context/...``) - the GitHub MCP and
    the Pages importer resolve paths from the root, so a bare ``context/domains/...`` would not be found.
11. The Genie text instruction (``genie/agent_instructions.md``, the ```text block) only names tables and
    columns that exist in the bootcamp domains.

Optional live check (needs the Databricks CLI and a SQL warehouse):

    python3 -I tools/check_context.py --run-sql --catalog cpg_<you> --warehouse <id> --profile <p>

runs every SQL block of every page (and the agent instructions) against your gold tables with
the Statement Execution API and reports failures and row counts.

Exit code 0 = no errors (warnings allowed), 1 = errors found.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(ROOT, "tools", "model", "consumer_goods_v2_mvm.json")
CONTEXT = os.path.join(ROOT, "bootcamp", "context")
SCOPE = ("consumer", "finance", "manufacturing")   # the bootcamp domains
OTHER_DOMAINS = ("distribution", "procurement", "product", "promotion", "quality", "sales", "supply")
DOMAIN_TITLE = {d: d.capitalize() for d in SCOPE}
MIN_PAGES_PER_DOMAIN = 8
REPO_PREFIX = "bootcamp/context/"
PAGE_KEYS = ("title", "domain", "subdomain", "synonyms", "description", "owner", "related_assets", "sources")
LIST_KEYS = ("synonyms", "related_assets", "sources")
CURATED_METRIC_VIEWS = {
    ("consumer", "dtc_sales_metrics"),
    ("finance", "net_revenue_metrics"),
    ("finance", "receivables_metrics"),
    ("manufacturing", "production_performance_metrics"),
}
# literal values that are legitimately written in backticks without being model columns/enums
EXTRA_LITERALS = {
    # data values generated for the fictional company (not regex enums in the model)
    "posted", "cancelled", "delivered", "returned", "shipped", "pending", "confirmed", "processing",
    "revenue", "fulfilled", "unfulfilled", "partially_fulfilled", "refunded", "authorized", "captured",
    "open", "partially_paid", "paid", "cleared", "written_off", "disputed",
    "picking",
    # SQL / notation helpers used in prose
    "true", "false", "null", "sum", "count", "avg", "date_trunc", "datediff", "year", "month",
    "lower", "upper", "coalesce", "use", "catalog",
    # placeholders and folder names
    "catalog", "context", "pages", "genie", "domains", "main",
}
SQL_KEYWORDS = {
    "select", "from", "join", "left", "right", "inner", "outer", "full", "cross", "on", "where",
    "group", "by", "order", "having", "as", "and", "or", "not", "in", "is", "null", "case", "when",
    "then", "else", "end", "with", "union", "all", "distinct", "limit", "between", "like", "ilike",
    "using", "lateral", "values", "desc", "asc", "true", "false", "interval", "date", "timestamp",
    "over", "partition", "rows", "range", "any_value", "filter",
}


# --------------------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------------------

def load_model():
    with open(MODEL, encoding="utf-8") as fh:
        m = json.load(fh)["model"]
    tables = {}          # (schema, table) -> {column: attr}
    subdomains = {}      # schema -> {title: model_name}
    enums = set()
    for d in m["domains"]:
        if d["name"] not in SCOPE:      # tables of other domains are not in the bootcamp catalog
            continue
        subdomains[d["name"]] = {sd["name"].replace("_", " ").title(): sd["name"] for sd in d["subdomains"]}
        for p in d["products"]:
            cols = {}
            for a in p["attributes"]:
                cols[a["column_name"]] = a
                rx = a.get("value_regex") or ""
                if rx and "|" in rx and not rx.startswith("^"):
                    enums.update(v.strip() for v in rx.split("|"))
                desc = a.get("description") or ""
                mm = re.search(r"ENUM-REF-CANDIDATE:\s*([A-Za-z0-9_|\- ]+)", desc)
                if mm:
                    enums.update(v.strip() for v in mm.group(1).split("|"))
            tables[(d["name"], p["table_name"])] = cols
    metric_views = set(CURATED_METRIC_VIEWS)
    for v in m["metric_views"]:
        if v["owner_domain"] in SCOPE:
            metric_views.add((v["owner_domain"], v["owner_product"] + "_metrics"))
    return tables, subdomains, enums, metric_views


# --------------------------------------------------------------------------------------
# front matter (small YAML subset: "key: value", "key:" + "  - item" lists, quoted strings)
# --------------------------------------------------------------------------------------

def parse_front_matter(text, path, errors):
    if not text.startswith("---\n"):
        errors.append(f"{path}: missing YAML front matter")
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        errors.append(f"{path}: front matter not closed with ---")
        return {}, text
    block, body = text[4:end], text[end + 4:]
    data, key = {}, None
    for ln, line in enumerate(block.splitlines(), 2):
        if not line.strip():
            continue
        if line.startswith("  - "):
            if key is None or not isinstance(data.get(key), list):
                errors.append(f"{path}:{ln}: list item without a list key")
                continue
            data[key].append(_unquote(line[4:].strip()))
            continue
        mm = re.match(r"^([a-z_]+):(.*)$", line)
        if not mm:
            errors.append(f"{path}:{ln}: cannot parse front matter line: {line!r}")
            continue
        key, val = mm.group(1), mm.group(2).strip()
        if key in data:
            errors.append(f"{path}:{ln}: duplicate key {key}")
        if val == "":
            data[key] = []
        else:
            if ": " in val and not (val.startswith('"') and val.endswith('"')):
                errors.append(f"{path}:{ln}: value of '{key}' contains ': ' and must be double-quoted")
            data[key] = _unquote(val)
    return data, body


def _unquote(v):
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


# --------------------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------------------

ASSET_RX = re.compile(r"^<catalog>\.([a-z_]+)\.([a-z0-9_]+)$")


def check_asset(asset, where, tables, metric_views, errors):
    mm = ASSET_RX.match(asset)
    if not mm:
        errors.append(f"{where}: related asset '{asset}' is not '<catalog>.<schema>.<object>'")
        return
    schema, obj = mm.groups()
    if schema not in SCOPE:
        errors.append(f"{where}: related asset '{asset}' is outside the bootcamp scope {SCOPE}")
    elif (schema, obj) not in tables and (schema, obj) not in metric_views:
        errors.append(f"{where}: related asset '{asset}' is neither a model table nor a known metric view")


FROM_RX = re.compile(r"\b(?:from|join)\s+([a-z_]+)\.([a-z0-9_]+)(?:\s+(?:as\s+)?([a-z][a-z0-9_]*))?", re.I)
COLREF_RX = re.compile(r"\b([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)\b")


def sql_blocks(body):
    return [b for b in re.findall(r"```sql\n(.*?)```", body, re.S)]


def check_sql(sql, where, tables, errors, warnings):
    # strip comments and string literals
    clean = re.sub(r"--[^\n]*", "", sql)
    clean = re.sub(r"'[^']*'", "''", clean)
    aliases = {}
    for schema, table, alias in FROM_RX.findall(clean):
        schema, table = schema.lower(), table.lower()
        if (schema, table) not in tables:
            errors.append(f"{where}: SQL references unknown table {schema}.{table}")
            continue
        aliases[table] = (schema, table)
        if alias and alias.lower() not in SQL_KEYWORDS:
            aliases[alias.lower()] = (schema, table)
    # CTE names, aliases of CTEs and of sub-queries are not model tables: collect them to skip
    ctes = {c.lower() for c in re.findall(r"(?:with|,)\s*([a-z_][a-z0-9_]*)\s+as\s*\(", clean, re.I)}
    for name, alias in re.findall(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)\s+(?:as\s+)?([a-z][a-z0-9_]*)", clean, re.I):
        if name.lower() in ctes and alias.lower() not in SQL_KEYWORDS:
            ctes.add(alias.lower())
    ctes |= {c.lower() for c in re.findall(r"\)\s*(?:as\s+)?([a-z_][a-z0-9_]*)\s+on\b", clean, re.I)}
    n_refs = 0
    for qual, col in COLREF_RX.findall(clean):
        q = qual.lower()
        if q in SCOPE:
            continue  # schema.table part of FROM
        if q in aliases:
            schema, table = aliases[q]
            if col.lower() not in tables[(schema, table)]:
                errors.append(f"{where}: column {table}.{col} (alias '{qual}') does not exist in the model")
            n_refs += 1
        elif q in ctes:
            continue
        else:
            warnings.append(f"{where}: cannot resolve qualifier '{qual}' in '{qual}.{col}'")
    return n_refs


def check_prose_refs(body, where, tables, enums, errors, warnings):
    """Backticked identifiers in the prose (not in code blocks)."""
    prose = re.sub(r"```.*?```", "", body, flags=re.S)
    all_columns = set()
    by_table = {}
    for (schema, table), cols in tables.items():
        if schema in SCOPE:
            all_columns |= set(cols)
            by_table.setdefault(table, []).append(schema)
    n = 0
    for token in re.findall(r"`([^`\n]+)`", prose):
        # pull dotted identifiers out of small expressions such as `a.b = 'x'`
        for ident in re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", token):
            parts = ident.split(".")
            if parts[0] in ("<catalog>",) or ident.endswith(".md") or ident.endswith(".csv") or ident.endswith(".py") or ident.endswith(".json"):
                continue
            if len(parts) == 3 and parts[0] in SCOPE:
                schema, table, col = parts
                if (schema, table) in tables and col not in tables[(schema, table)]:
                    errors.append(f"{where}: `{ident}` — column {col} not in {schema}.{table}")
                n += 1
            elif len(parts) == 2 and parts[0] in SCOPE:
                if (parts[0], parts[1]) not in tables and not parts[1].endswith("_metrics"):
                    errors.append(f"{where}: `{ident}` — unknown table")
                n += 1
            elif len(parts) == 2 and parts[0] in by_table:
                table, col = parts
                if not any(col in tables[(s, table)] for s in by_table[table]):
                    errors.append(f"{where}: `{ident}` — column {col} not in table {table}")
                n += 1
            elif len(parts) == 2 and parts[0].endswith("_metrics"):
                continue  # <metric_view>.<measure>: measures are owned by the metric-view stream
            elif parts[0] in OTHER_DOMAINS:
                errors.append(f"{where}: `{ident}` — domain {parts[0]} is not part of the bootcamp")
            elif parts[0] in ("system", "governance"):
                continue  # objects outside the gold model scope (documented as such)
            else:
                warnings.append(f"{where}: cannot classify `{ident}`")
        bare = token.strip()
        if re.fullmatch(r"[a-z][a-z0-9_]*", bare) and "_" in bare:
            if bare not in all_columns and bare not in by_table and bare not in enums \
                    and bare not in EXTRA_LITERALS and not bare.endswith("_metrics") and bare not in SCOPE:
                warnings.append(f"{where}: `{bare}` is not a known column/table/enum value")
    return n


def check_pages(tables, subdomains, enums, metric_views, errors, warnings, stats):
    pages = {}
    for dom in SCOPE:
        pdir = os.path.join(CONTEXT, "domains", dom, "pages")
        if not os.path.isdir(pdir):
            errors.append(f"missing folder {pdir}")
            continue
        for fn in sorted(os.listdir(pdir)):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(pdir, fn)
            rel = os.path.relpath(path, ROOT)
            text = open(path, encoding="utf-8").read()
            fm, body = parse_front_matter(text, rel, errors)
            pages[os.path.relpath(path, CONTEXT)] = fm
            for k in PAGE_KEYS:
                if k not in fm:
                    errors.append(f"{rel}: front matter key '{k}' missing")
            for k in LIST_KEYS:
                if k in fm and (not isinstance(fm[k], list) or not fm[k]):
                    errors.append(f"{rel}: '{k}' must be a non-empty list")
            if fm.get("domain") != DOMAIN_TITLE[dom]:
                errors.append(f"{rel}: domain '{fm.get('domain')}' does not match folder '{dom}'")
            if fm.get("subdomain") not in subdomains.get(dom, {}):
                errors.append(f"{rel}: subdomain '{fm.get('subdomain')}' is not a subdomain of {dom} "
                              f"({', '.join(subdomains.get(dom, {}))})")
            for a in fm.get("related_assets", []) or []:
                check_asset(a, rel, tables, metric_views, errors)
            for sec in ("## Definition", "## Business rules", "## How to calculate (SQL)",
                        "## Pitfalls and common wrong answers", "## Example questions"):
                if sec not in body:
                    errors.append(f"{rel}: section '{sec}' missing")
            blocks = sql_blocks(body)
            if not blocks:
                errors.append(f"{rel}: no ```sql block")
            for i, b in enumerate(blocks, 1):
                stats["sql_blocks"] += 1
                stats["sql_column_refs"] += check_sql(b, f"{rel} [sql #{i}]", tables, errors, warnings)
            stats["prose_refs"] += check_prose_refs(body, rel, tables, enums, errors, warnings)
            stats["pages"] += 1
    return pages


def check_structure(subdomains, errors, stats):
    ddir = os.path.join(CONTEXT, "domains")
    for extra in sorted(set(os.listdir(ddir)) - set(SCOPE) if os.path.isdir(ddir) else []):
        if os.path.isdir(os.path.join(ddir, extra)):
            errors.append(f"{os.path.relpath(os.path.join(ddir, extra), ROOT)}: domain folder outside the bootcamp scope")
    for dom in SCOPE:
        dpath = os.path.join(CONTEXT, "domains", dom, "_domain.md")
        if not os.path.isfile(dpath):
            errors.append(f"missing {os.path.relpath(dpath, ROOT)}")
        else:
            fm, _ = parse_front_matter(open(dpath, encoding="utf-8").read(), os.path.relpath(dpath, ROOT), errors)
            if fm.get("domain") != DOMAIN_TITLE[dom]:
                errors.append(f"{os.path.relpath(dpath, ROOT)}: domain must be {DOMAIN_TITLE[dom]}")
            if "Databricks" not in str(fm.get("license", "")):
                errors.append(f"{os.path.relpath(dpath, ROOT)}: front matter 'license' (industry-model notice) missing")
            stats["domains"] += 1
        for title, name in subdomains[dom].items():
            spath = os.path.join(CONTEXT, "domains", dom, name, "_subdomain.md")
            if not os.path.isfile(spath):
                errors.append(f"missing {os.path.relpath(spath, ROOT)}")
                continue
            fm, _ = parse_front_matter(open(spath, encoding="utf-8").read(), os.path.relpath(spath, ROOT), errors)
            if fm.get("subdomain") != title or fm.get("subdomain_tag") != f"{DOMAIN_TITLE[dom]}/{title}":
                errors.append(f"{os.path.relpath(spath, ROOT)}: subdomain/subdomain_tag must be "
                              f"'{title}' / '{DOMAIN_TITLE[dom]}/{title}'")
            if "Databricks" not in str(fm.get("license", "")):
                errors.append(f"{os.path.relpath(spath, ROOT)}: front matter 'license' (industry-model notice) missing")
            stats["subdomains"] += 1


def check_glossary(pages, tables, metric_views, errors, stats):
    path = os.path.join(CONTEXT, "glossary.csv")
    if not os.path.isfile(path):
        errors.append("missing bootcamp/context/glossary.csv")
        return
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    want = ["term", "synonyms", "domain", "subdomain", "short_definition", "page_path", "related_assets"]
    if rows and list(rows[0].keys()) != want:
        errors.append(f"glossary.csv: header must be {want}")
    seen = set()
    for i, r in enumerate(rows, 2):
        where = f"context/glossary.csv:{i}"
        pp = r.get("page_path", "")
        if not pp.startswith(REPO_PREFIX):
            errors.append(f"{where}: page_path '{pp}' must start with {REPO_PREFIX} (path from the repository root)")
        rel = pp[len(REPO_PREFIX):] if pp.startswith(REPO_PREFIX) else pp
        if rel not in pages:
            errors.append(f"{where}: page_path '{pp}' does not exist")
        else:
            fm = pages[rel]
            if fm.get("title") != r["term"] or fm.get("domain") != r["domain"] or fm.get("subdomain") != r["subdomain"]:
                errors.append(f"{where}: term/domain/subdomain differ from the page front matter")
        for a in [x.strip() for x in r.get("related_assets", "").split(";") if x.strip()]:
            check_asset(a, where, tables, metric_views, errors)
        if r["term"] in seen:
            errors.append(f"{where}: duplicate term {r['term']}")
        seen.add(r["term"])
        stats["glossary_rows"] += 1
    missing = set(pages) - {r["page_path"][len(REPO_PREFIX):] for r in rows}
    for m in sorted(missing):
        errors.append(f"glossary.csv: no row for page {m}")


def check_pii(errors):
    for dirpath, _, files in os.walk(CONTEXT):
        for fn in files:
            path = os.path.join(dirpath, fn)
            text = open(path, encoding="utf-8").read()
            for mail in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
                if not mail.lower().endswith("@example.com"):
                    errors.append(f"{os.path.relpath(path, ROOT)}: e-mail address '{mail}' (no PII allowed)")


BARE_PATH_RX = re.compile(r"(?<![\w/.\-])context/(?:domains|glossary|genie|company_profile)")


def check_repo_paths(errors):
    """Paths must be written from the repository root: bootcamp/context/..."""
    for dirpath, _, files in os.walk(CONTEXT):
        for fn in files:
            path = os.path.join(dirpath, fn)
            for ln, line in enumerate(open(path, encoding="utf-8"), 1):
                if BARE_PATH_RX.search(line):
                    errors.append(f"{os.path.relpath(path, ROOT)}:{ln}: write the path from the repository root "
                                  f"({REPO_PREFIX}...), not 'context/...'")


def check_coverage(pages, errors, stats):
    per_domain = {d: 0 for d in SCOPE}
    for rel in pages:
        per_domain[rel.split("/")[1]] += 1
    for d, n in per_domain.items():
        if n < MIN_PAGES_PER_DOMAIN:
            errors.append(f"domain {d}: {n} pages - at least {MIN_PAGES_PER_DOMAIN} required")
    stats["pages_per_domain"] = "/".join(str(per_domain[d]) for d in SCOPE)
    texts = ""
    for dom in SCOPE:
        pdir = os.path.join(CONTEXT, "domains", dom, "pages")
        for fn in sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []:
            texts += open(os.path.join(pdir, fn), encoding="utf-8").read()
    for schema, view in sorted(CURATED_METRIC_VIEWS):
        if f"{schema}.{view}" not in texts:
            errors.append(f"curated metric view {schema}.{view} is not named by any page")


DOTTED_RX = re.compile(r"\b([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)(?:\.([a-z][a-z0-9_]*))?\b")


def check_text_instruction(body, where, tables, errors, stats):
    """Plain-text table/column names in the ```text block of the agent instructions."""
    by_table = {}
    for (schema, table) in tables:
        by_table.setdefault(table, []).append(schema)
    for block in re.findall(r"```text\n(.*?)```", body, re.S):
        for a, b, c in DOTTED_RX.findall(block):
            if a in OTHER_DOMAINS:
                errors.append(f"{where}: '{a}.{b}' - domain {a} is not part of the bootcamp")
            elif a in SCOPE and c:
                if (a, b) not in tables or c not in tables[(a, b)]:
                    errors.append(f"{where}: '{a}.{b}.{c}' does not exist in the model")
            elif a in SCOPE:
                if (a, b) not in tables and (a, b) not in CURATED_METRIC_VIEWS and not b.endswith("_metrics"):
                    errors.append(f"{where}: '{a}.{b}' is not a bootcamp table or metric view")
            elif a in by_table:
                if not any(b in tables[(s, a)] for s in by_table[a]):
                    errors.append(f"{where}: '{a}.{b}' - column {b} not in table {a}")
            else:
                continue   # prose such as 'e.g' or file names
            stats["instruction_refs"] += 1


# --------------------------------------------------------------------------------------
# optional live SQL run
# --------------------------------------------------------------------------------------

def run_sql_blocks(catalog, warehouse, profile, errors, stats):
    files = []
    for dom in SCOPE:
        pdir = os.path.join(CONTEXT, "domains", dom, "pages")
        files += [os.path.join(pdir, f) for f in sorted(os.listdir(pdir)) if f.endswith(".md")]
    files.append(os.path.join(CONTEXT, "genie", "agent_instructions.md"))
    for path in files:
        if not os.path.isfile(path):
            continue
        body = open(path, encoding="utf-8").read()
        for i, sql in enumerate(sql_blocks(body), 1):
            where = f"{os.path.relpath(path, ROOT)} [sql #{i}]"
            stmt = sql.strip().rstrip(";").replace("<catalog>.", f"{catalog}.")
            payload = {"warehouse_id": warehouse, "catalog": catalog, "statement": stmt,
                       "wait_timeout": "50s", "on_wait_timeout": "CANCEL", "disposition": "INLINE",
                       "format": "JSON_ARRAY"}
            cmd = ["databricks", "api", "post", "/api/2.0/sql/statements", "--json", json.dumps(payload)]
            if profile:
                cmd += ["-p", profile]
            out = subprocess.run(cmd, capture_output=True, text=True)
            if out.returncode != 0:
                errors.append(f"{where}: CLI error {out.stderr.strip()[:300]}")
                continue
            res = json.loads(out.stdout)
            state = res.get("status", {}).get("state")
            if state != "SUCCEEDED":
                msg = res.get("status", {}).get("error", {}).get("message", state)
                errors.append(f"{where}: {state}: {msg[:400]}")
                continue
            n = res.get("manifest", {}).get("total_row_count", 0)
            rows = res.get("result", {}).get("data_array", [])[:3]
            stats["sql_ok"] += 1
            print(f"  OK   {where}: {n} rows; first: {rows[:2]}")
            if n == 0:
                errors.append(f"{where}: query returned 0 rows")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-sql", action="store_true", help="execute every SQL block against a live catalog")
    ap.add_argument("--catalog", help="catalog with the gold tables (for --run-sql)")
    ap.add_argument("--warehouse", help="SQL warehouse id (for --run-sql)")
    ap.add_argument("--profile", help="Databricks CLI profile (for --run-sql)")
    ap.add_argument("--quiet-warnings", action="store_true")
    args = ap.parse_args()

    tables, subdomains, enums, metric_views = load_model()
    errors, warnings = [], []
    stats = dict(pages=0, domains=0, subdomains=0, sql_blocks=0, sql_column_refs=0, prose_refs=0,
                 glossary_rows=0, instruction_refs=0, sql_ok=0)
    check_structure(subdomains, errors, stats)
    pages = check_pages(tables, subdomains, enums, metric_views, errors, warnings, stats)
    check_glossary(pages, tables, metric_views, errors, stats)
    check_pii(errors)
    check_repo_paths(errors)
    check_coverage(pages, errors, stats)
    ai = os.path.join(CONTEXT, "genie", "agent_instructions.md")
    if os.path.isfile(ai):
        body = open(ai, encoding="utf-8").read()
        for i, b in enumerate(sql_blocks(body), 1):
            stats["sql_blocks"] += 1
            stats["sql_column_refs"] += check_sql(b, f"bootcamp/context/genie/agent_instructions.md [sql #{i}]", tables, errors, warnings)
        stats["prose_refs"] += check_prose_refs(body, "bootcamp/context/genie/agent_instructions.md", tables, enums, errors, warnings)
        check_text_instruction(body, "bootcamp/context/genie/agent_instructions.md", tables, errors, stats)
    else:
        errors.append("missing bootcamp/context/genie/agent_instructions.md")
    if args.run_sql:
        if not (args.catalog and args.warehouse):
            ap.error("--run-sql needs --catalog and --warehouse")
        print(f"Running SQL blocks against catalog {args.catalog} ...")
        run_sql_blocks(args.catalog, args.warehouse, args.profile, errors, stats)

    print("check_context:", ", ".join(f"{k}={v}" for k, v in stats.items()))
    if warnings and not args.quiet_warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print("  WARN ", w)
    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors:
            print("  ERROR", e)
        return 1
    print("\nOK — no errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
