#!/usr/bin/env python3
"""Generate the single-domain samples in bootcamp_domain/ from the Lakehouse Industry Data Model.

Each sample is a self-contained bundle folder for ONE business domain - the same lab as bootcamp/, cut
down to one domain, one Genie Agent and one router app:

  bootcamp_domain/<sample>/
    pipeline/<domain>/01_bronze.sql, 02_silver.sql, 03_gold.sql   bronze -> silver -> gold
    metric_views/industry/<domain>.sql                             the model's metric views (main domain)
    metric_views/curated/<name>.sql                                copies of bootcamp/metric_views/curated/
    model_tags/<domain>.json                                       the model's dbx_* tags
    data/manifest.json                                             subset of bootcamp/data/manifest.json
    genie/<template>.json                                          copy of the bootcamp Genie Agent template
    app/glossary/glossary.csv, pages/*.md                          the domain's glossary (router glossary tool)
    LICENSE.md, NOTICE.md                                          copies of tools/model/

A sample builds its main domain completely plus a few REFERENCE tables of other domains that its curated
metric views, Genie Agent or governance need (for example finance.company_code for the consumer sample).
Foreign keys into tables that a sample does not build are omitted, like the bootcamp omits keys into
domains it does not build. The SQL is written by tools/generate_lakehouse.py's own functions, so a sample's
pipeline is the bootcamp pipeline restricted to the sample's tables. Nothing in bootcamp/ or tools/ is
written: the CSV files stay in bootcamp/data/ (the repository's 40 MB data budget allows no copies) and the
samples' setup notebooks read them from there.

Usage (from the repo root, standard library only):

  python3 -I bootcamp_domain/tools/build_domain_samples.py           # write all files
  python3 -I bootcamp_domain/tools/build_domain_samples.py --check   # exit 1 if a file is missing or stale
"""
import copy
import csv
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import generate_lakehouse as gl  # noqa: E402  (the bootcamp generator: model loading and SQL writers)

SCRIPT = "bootcamp_domain/tools/build_domain_samples.py"
gl.SCRIPT = SCRIPT   # the "GENERATED FILE - regenerate with ..." headers name this script

SAMPLES_DIR = "bootcamp_domain"

# sample -> {domain: tables (None = every table of the domain)}. The first domain is the sample's main
# domain: it gets the industry metric views, the curated metric views and the Genie Agent.
SAMPLES = {
    "finance": {
        "finance": None,
    },
    "consumer": {
        "consumer": None,
        # dtc_sales_metrics: entity (company_code), brand (profit_center), EUR rate (journal_entry_line);
        # governance resolves the company codes through finance.company_code.
        "finance": ("company_code", "profit_center", "journal_entry", "journal_entry_line"),
    },
    "manufacturing": {
        "manufacturing": None,
        # production_performance_metrics: EUR rate of each plant currency (journal_entry_line).
        "finance": ("company_code", "journal_entry", "journal_entry_line"),
    },
}

# Genie Agent template of each sample's main domain (bootcamp/genie/, copied verbatim).
GENIE_TEMPLATES = {
    "finance": "fjallmark_finance_analyst.json",
    "consumer": "fjallmark_consumer_analyst.json",
    "manufacturing": "fjallmark_manufacturing_analyst.json",
}

BOOTCAMP_MANIFEST = "bootcamp/data/manifest.json"
BOOTCAMP_CURATED = "bootcamp/metric_views/curated"
BOOTCAMP_GENIE = "bootcamp/genie"
BOOTCAMP_CONTEXT = "bootcamp/context"
BOOTCAMP_GLOSSARY = "bootcamp/context/glossary.csv"

# Foreign keys into a table of a domain the sample builds only partly are re-pointed at this marker
# domain before the SQL is written: tools/generate_lakehouse.py then treats them as "not in scope" (it
# scopes whole domains), and the marker is replaced by the real domain name in the generated text.
NOT_BUILT = "__not_built__"


def sample_model(model, scope):
    """A copy of the model with only the sample's domains and tables; FKs into tables the sample does not
    build point at the NOT_BUILT marker domain."""
    built = {(d, p["table_name"]) for dm in model["domains"] if (d := dm["name"]) in scope
             for p in dm["products"] if scope[d] is None or p["table_name"] in scope[d]}
    domains = []
    for d in scope:   # sample order: the main domain first
        dm = copy.deepcopy(next(x for x in model["domains"] if x["name"] == d))
        dm["products"] = [p for p in dm["products"] if (d, p["table_name"]) in built]
        missing = set(scope[d] or ()) - {p["table_name"] for p in dm["products"]}
        if missing:
            raise ValueError("%s: tables not in the model: %s" % (d, sorted(missing)))
        for p in dm["products"]:
            for a in p["attributes"]:
                fk = a.get("foreign_key_to")
                if fk:
                    rd, rt, rc = fk.split(".")
                    if rd in scope and (rd, rt) not in built:
                        a["foreign_key_to"] = "%s%s.%s.%s" % (NOT_BUILT, rd, rt, rc)
        domains.append(dm)
    return dict(model, domains=domains), built


def sample_text(text, sample, scope):
    """Turn the bootcamp wording of a generated file into the sample's."""
    tables = ", ".join("%s (%s)" % (d, "all" if t is None else ", ".join(t)) for d, t in scope.items())
    text = re.sub(re.escape(NOT_BUILT) + r"(\w+)\.", r"\1.", text)
    text = text.replace("(table not in the bootcamp scope)", "(table not built by this sample)")
    text = text.replace("BOOTCAMP variant (bootcamp bundle).",
                        "SAMPLE variant (bootcamp_domain/%s bundle)." % sample)
    text = re.sub(r"-- Identical to full_model/src/pipeline/(\w+)/03_gold\.sql except that FOREIGN KEYs to tables\n"
                  r"-- outside the bootcamp domains \([^)]*\) are omitted: this bundle does not build\n",
                  lambda m: ("-- Identical to full_model/src/pipeline/%s/03_gold.sql except that FOREIGN KEYs to tables\n"
                             "-- this sample does not build are omitted (it builds %s); this bundle does not build\n"
                             % (m.group(1), tables)), text)
    text = text.replace("column mask (bootcamp lab step 3: consumer.shopper, consumer.dtc_order, finance.ar_invoice) cannot be",
                        "column mask (step 3 of this sample, notebooks/03_governance.py) cannot be")
    text = re.sub(r"the policies are attached, every update recomputes those gold tables from silver \(11 of the 36\n"
                  r"-- bootcamp gold tables\)",
                  "the policies are attached, every update recomputes those gold tables from silver\n"
                  "-- (the gold tables whose build-order hint reads a governed table)", text)
    return text


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def build(model):
    files = {}
    stats = {}
    manifest = json.loads(read(BOOTCAMP_MANIFEST))
    for sample, scope in SAMPLES.items():
        base = "%s/%s" % (SAMPLES_DIR, sample)
        paths = {"mv_notebook": "notebooks/job_tasks/02a_create_metric_views.py",
                 "tag_notebook": "notebooks/job_tasks/02b_apply_model_tags.py"}
        smodel, built = sample_model(model, scope)
        order = gl.gold_build_order(smodel, tuple(scope))
        main = next(iter(scope))
        st = {"tables": 0, "fks": 0, "metric_views": 0, "tags": 0}
        for dm in smodel["domains"]:
            d = dm["name"]
            pdir = "%s/pipeline/%s/" % (base, d)
            files[pdir + "01_bronze.sql"] = sample_text(gl.gen_bronze(dm), sample, scope)
            files[pdir + "02_silver.sql"] = sample_text(gl.gen_silver(dm), sample, scope)
            files[pdir + "03_gold.sql"] = sample_text(gl.gen_gold(dm, tuple(scope), order), sample, scope)
            nfk = files[pdir + "03_gold.sql"].count("` FOREIGN KEY (`")   # constraint lines only
            text, ntags = gl.gen_tags(dm, paths["tag_notebook"], nfk)
            files["%s/model_tags/%s.json" % (base, d)] = text
            if d == main:
                text, nmv = gl.gen_metric_views(model, dm, paths["mv_notebook"])
                files["%s/metric_views/industry/%s.sql" % (base, d)] = sample_text(text, sample, scope)
                st["metric_views"] += nmv
            st["tables"] += len(dm["products"])
            st["fks"] += nfk
            st["tags"] += ntags
        # curated metric views of the main domain: bootcamp/metric_views/curated/<main>_*.sql, verbatim
        for name in sorted(os.listdir(os.path.join(ROOT, BOOTCAMP_CURATED))):
            if name.startswith(main + "_") and name.endswith(".sql"):
                text = read("%s/%s" % (BOOTCAMP_CURATED, name))
                for ref in set(re.findall(r"\$\{catalog\}\.(\w+)\.(\w+)", text)):
                    if ref not in built and not ref[1].endswith("_metrics"):
                        raise ValueError("%s reads %s.%s, which sample %s does not build" % (name, *ref, sample))
                files["%s/metric_views/curated/%s" % (base, name)] = text
                st["metric_views"] += 1
        # data manifest: the sample's tables; "file" stays relative to the repository root (bootcamp/data)
        sub = {"_notice": ("GENERATED FILE - do not edit by hand; regenerate with python3 -I %s. Subset of "
                           "%s for the tables of this sample (the CSV files stay in bootcamp/data/). "
                           "Original notice: %s" % (SCRIPT, BOOTCAMP_MANIFEST, manifest["_notice"]))}
        for d, tables in scope.items():
            sub[d] = {t: meta for t, meta in manifest[d].items() if (d, t) in built}
            if len(sub[d]) != len([1 for x in built if x[0] == d]):
                raise ValueError("%s: manifest misses tables of %s" % (sample, d))
        files["%s/data/manifest.json" % base] = json.dumps(sub, indent=1, ensure_ascii=False) + "\n"
        # Genie Agent template of the main domain, verbatim (its sources must all be built here)
        tpl = GENIE_TEMPLATES[sample]
        text = read("%s/%s" % (BOOTCAMP_GENIE, tpl))
        for ref in set(re.findall(r"__CATALOG__\.(\w+)\.(\w+)", text)):
            if ref not in built and not ref[1].endswith("_metrics"):
                raise ValueError("%s reads %s.%s, which sample %s does not build" % (tpl, *ref, sample))
        files["%s/genie/%s" % (base, tpl)] = text
        # the router app's glossary tool: the main domain's index rows and pages (the app is deployed from
        # app/ alone, so it cannot read bootcamp/context/ at runtime)
        rows = list(csv.reader(io.StringIO(read(BOOTCAMP_GLOSSARY))))
        mine = [r for r in rows[1:] if r[rows[0].index("domain")].lower() == main]
        out = io.StringIO()
        csv.writer(out, lineterminator="\n").writerows([rows[0]] + mine)
        files["%s/app/glossary/glossary.csv" % base] = out.getvalue()
        pages = "%s/domains/%s/pages" % (BOOTCAMP_CONTEXT, main)
        for name in sorted(os.listdir(os.path.join(ROOT, pages))):
            if name.endswith(".md"):
                files["%s/app/glossary/pages/%s" % (base, name)] = read("%s/%s" % (pages, name))
        if len(mine) != len([f for f in files if f.startswith("%s/app/glossary/pages/" % base)]):
            raise ValueError("%s: glossary rows and pages differ" % sample)
        for name in gl.LICENSE_FILES:
            files["%s/%s" % (base, name)] = read("tools/model/%s" % name)
        stats[sample] = st
    return files, stats


def unexpected_files(files):
    """Files below the generated folders of the samples that this script does not write."""
    out = []
    for sample in SAMPLES:
        for key in ("pipeline", "metric_views", "model_tags", "genie", "app/glossary"):
            top = os.path.join(ROOT, SAMPLES_DIR, sample, key)
            for dirpath, _, names in os.walk(top):
                for n in names:
                    rel = os.path.relpath(os.path.join(dirpath, n), ROOT).replace(os.sep, "/")
                    if rel not in files and not n.endswith(".md") and n != ".DS_Store":
                        out.append(rel)
    return sorted(out)


def main(argv):
    check = "--check" in argv
    files, stats = build(gl.load_model())
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
    for sample, st in stats.items():
        print("  %-14s: %d tables, %d FKs, %d metric views, %d tags"
              % (sample, st["tables"], st["fks"], st["metric_views"], st["tags"]))
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
