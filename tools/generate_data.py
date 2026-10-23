#!/usr/bin/env python3
"""Generate the synthetic Fjällmark Consumer Goods data set.

Usage (from the repository root)::

    python3 -I tools/generate_data.py [--seed 20261029]

Writes one CSV per table of the Lakehouse Industry Data Model (Consumer Goods v2, MVM) - every file
exactly once - into the two bundle folders:

* ``bootcamp/data/<domain>/<table>.csv`` for the bootcamp domains (consumer, finance, manufacturing;
  36 tables) plus ``bootcamp/data/manifest.json`` and ``bootcamp/data/README.md`` (bootcamp scope);
* ``full_model/data/<domain>/<table>.csv`` for the other 7 domains (80 tables) plus
  ``full_model/data/manifest.json`` (all 116 tables, with each file's repository-relative path - the
  bootcamp domains point to ``bootcamp/data``) and ``full_model/data/README.md``.

Standard library only; deterministic for a given seed (running it twice produces byte-identical
files).
"""
import argparse
import os
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from datagen import build, readme  # noqa: E402
from datagen.model import CORE_DOMAINS  # noqa: E402

DEFAULT_SEED = 20261029
BOOTCAMP_DATA = os.path.join("bootcamp", "data")
FULL_DATA = os.path.join("full_model", "data")


def folder_bytes(path):
    return sum(os.path.getsize(os.path.join(root, f)) for root, _, files in os.walk(path) for f in files)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=REPO,
                    help="repository root to write into (default: this repository); the data lands in "
                         "<root>/bootcamp/data and <root>/full_model/data")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (default: %d)" % DEFAULT_SEED)
    ap.add_argument("--no-readme", action="store_true", help="skip the README.md files and the KPI snapshot")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    bootcamp_dir = os.path.join(root, BOOTCAMP_DATA)
    full_dir = os.path.join(root, FULL_DATA)

    def locate(domain):
        rel = BOOTCAMP_DATA if domain in CORE_DOMAINS else FULL_DATA
        return os.path.join(root, rel, domain), "%s/%s" % (rel.replace(os.sep, "/"), domain)

    t0 = time.time()
    print("Generating Fjällmark Consumer Goods data (seed %d) ..." % args.seed)
    reg = build.generate(args.seed)
    problems = build.validate(reg)
    if problems:
        print("Validation of the clean rows failed:")
        for p in problems[:80]:
            print("  - " + p)
        return 1
    print("  writing CSV files to %s (bootcamp domains) and %s (other domains) ..." % (BOOTCAMP_DATA, FULL_DATA))
    manifest, dqlog = build.write(reg, locate)
    bootcamp_manifest = dict((d, t) for d, t in manifest.items() if d in CORE_DOMAINS)
    build.write_manifest(bootcamp_manifest, os.path.join(bootcamp_dir, "manifest.json"))
    build.write_manifest(manifest, os.path.join(full_dir, "manifest.json"))
    if not args.no_readme:
        import verify_data
        report = verify_data.run([bootcamp_dir, full_dir], quiet=True)
        readme.write(os.path.join(bootcamp_dir, "README.md"), reg, bootcamp_manifest, report, args.seed, "bootcamp")
        readme.write(os.path.join(full_dir, "README.md"), reg, manifest, report, args.seed, "full")
        if report["errors"]:
            print("verify_data reported %d problem(s); run tools/verify_data.py for details" % len(report["errors"]))
    total = sum(t["bytes"] for d in manifest.values() for t in d.values())
    rows = sum(t["rows"] for d in manifest.values() for t in d.values())
    print("Done: %d tables, %d rows, %.1f MB in %.1f s" % (sum(len(d) for d in manifest.values()), rows,
                                                          total / 1e6, time.time() - t0))
    # size budget (build spec section 3): all data folders together - CSVs, manifests and READMEs - must
    # stay below 40 MB; fail at the guard so growth is noticed before the hard limit is reached
    size_b, size_f = folder_bytes(bootcamp_dir), folder_bytes(full_dir)
    print("data folders: bootcamp %.2f MB + full_model %.2f MB = %.2f MB (guard %.1f MB, budget 40 MB)"
          % (size_b / 1e6, size_f / 1e6, (size_b + size_f) / 1e6, readme.SIZE_GUARD_MB))
    if size_b + size_f >= readme.SIZE_GUARD_MB * 1e6:
        print("ERROR: the data folders are above the %.1f MB guard - reduce row counts before adding data"
              % readme.SIZE_GUARD_MB)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
