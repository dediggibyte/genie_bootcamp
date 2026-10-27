# Instructor guide - Manufacturing sample

For instructors who run the **Manufacturing sample** ([`README.md`](README.md)) as a workshop. The sample's participant
notebooks are self-service, but a workshop for several people needs one admin run first: groups, warehouse
access, catalogs, the **Manufacturing** domain, GitHub MCP checks and the shared Lakebase project. The full background is in
the bootcamp's [`INSTRUCTOR.md`](../../bootcamp/INSTRUCTOR.md); this page lists only what differs.

> **Not yet rehearsed.** The notebook below runs the tested bootcamp instructor notebook, but not yet with the
> Manufacturing values. Do a dry run (`dry_run = true`) on the event workspace first.

## 1. Pre-event checklist

| item | where | done by |
|---|---|---|
| the repository is readable by every participant (public, or Git credentials) | bootcamp INSTRUCTOR.md 1.1 | GitHub org admin |
| serverless for notebooks, jobs and pipelines; the workspace previews (MCP in Genie, Discover, tags on Genie Agents) | bootcamp INSTRUCTOR.md 1.2, checked by the notebook | workspace admin |
| groups, warehouse **CAN USE**, catalogs `cpg_manufacturing_<short name>`, the **Manufacturing** domain with its subdomains, `ASSIGN` on the tags, `system.ai.github`, Lakebase project `fjallmark-manufacturing-sample` | [`instructor/00_instructor_setup.py`](instructor/00_instructor_setup.py) (section 2 below) | you |
| Default Storage metastores: a `managed_location` for pre-created catalogs | bootcamp INSTRUCTOR.md 1.4 | metastore admin |
| one rehearsal of steps 1-6 as a **non-admin** participant | this sample's README | you |

## 2. Running `instructor/00_instructor_setup.py`

The notebook does not copy the bootcamp instructor notebook: it **runs**
[`bootcamp/instructor/00_instructor_setup.py`](../../bootcamp/instructor/00_instructor_setup.py) with this sample's
values, so there is one tested notebook to maintain.

| widget | default here | why |
|---|---|---|
| `mode` | `setup` | `teardown_*` after the event (section 4) |
| `dry_run` | **`false`** | Run all makes the changes. Set `true` for a check-only run (the morning of the event, or on a new workspace) |
| `confirm_teardown` | blank | teardown modes stay a dry run until this equals the mode name |
| `participants`, `instructors` | blank | e-mails, comma separated; they become members of the groups |
| `catalog_prefix` | `cpg_manufacturing_` | the sample's catalogs are `cpg_manufacturing_<short name>` |
| `domain_names` | `Manufacturing` | the one domain of this sample, with its subdomains |
| `lakebase_project` | `fjallmark-manufacturing-sample` | the project notebook 06 of the sample uses; each participant gets a branch |
| every other widget | as in the bootcamp | see bootcamp INSTRUCTOR.md section 2 |

1. Attach to **Serverless**, fill in `participants` (and `instructors`), **Run all**.
2. Read the summary table at the end: every line should be `OK`, `CREATED`, `GRANTED` or `SKIP` with a reason.
   The full, section-by-section output is in the child run the cell links to.
3. Re-running is safe: what exists is reported, not created again.

**Groups.** The sample uses the bootcamp's groups `cpg_bootcamp_participants` and `cpg_bootcamp_admins`: notebook 03
of the sample exempts members of `cpg_bootcamp_admins` from the policies. Never put a participant in the admins
group.

## 3. During the workshop

| symptom | fix |
|---|---|
| a participant's catalog is missing | re-run this notebook with their e-mail in `participants`, or let them create it (`catalog_strategy = grant_create_catalog`) |
| notebook 05: "governed tags missing" | this notebook has not run with `domain_names = Manufacturing`, or `publish_domains = false` |
| notebook 06: no permission on the Lakebase project | the participant is not in `cpg_bootcamp_participants`; add them and re-run this notebook |
| everything else | the sample README's troubleshooting table, then bootcamp INSTRUCTOR.md section 4 |

**Pages.** Unlike the bootcamp, the sample has no instructor-side Pages import: each participant imports the
Manufacturing pages as drafts with the prompt notebook 05 prints. If you want *published* Pages for everyone, import
them once yourself the same way and publish them.

## 4. After the workshop

1. Participants run `notebooks/99_cleanup.py` (their agent, app, branch, policies, catalog).
2. Run this notebook with `mode = teardown_domains_and_tags` or `teardown_everything`. The first run is a dry run;
   type the mode name into `confirm_teardown` and run again to delete.

> **Shared objects.** Domains, governed tags and groups are account-level, and the bootcamp notebook marks
> everything it creates with one marker and one ledger per instructor. If the bootcamp or another sample still
> uses the workspace, do **not** tear down: `teardown_domains_and_tags` would also remove a **Manufacturing** domain the
> bootcamp created, and `teardown_everything` also removes the shared groups. Catalogs are only removed for the
> prefix `cpg_manufacturing_`, and only the Lakebase project `fjallmark-manufacturing-sample`.
