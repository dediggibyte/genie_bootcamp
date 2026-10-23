<!--
All changes to `main` go through a pull request. Do not push directly to `main`:
create a branch (e.g. `feature/<topic>`), push it, and open a PR against `main`.
-->

## What does this PR change?

<!-- One or two sentences: what and why. Link the issue or discussion if there is one. -->

## Area

- [ ] `bootcamp/` (participant lab: data, pipeline, metric views, notebooks, Genie Agent, context)
- [ ] `full_model/` (complete 116-table industry model)
- [ ] `tools/` (generators / verifiers)
- [ ] Docs only (README, INSTRUCTOR, context pages)

## Checklist

- [ ] Generated files were changed through the generators, not by hand
      (`python3 -I tools/generate_lakehouse.py --check` passes)
- [ ] `python3 -I tools/verify_data.py` passes (if data or the data generator changed)
- [ ] `python3 -I tools/check_context.py` passes (if `bootcamp/context/` changed)
- [ ] `databricks bundle validate` passes for the bundle(s) touched
- [ ] Notebooks touched were run on a test catalog; re-running them is still a no-op (no data reload, no full refresh)
- [ ] No secrets, tokens or real personal data (all data is synthetic; emails use `example.com`)
- [ ] Files derived from the Lakehouse Industry Data Model keep their Databricks license notice

## How was this tested?

<!-- Workspace / catalog used, job or notebook run IDs, anything a reviewer should re-check. -->
