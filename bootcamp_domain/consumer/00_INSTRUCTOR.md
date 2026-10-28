# Instructor guide - Consumer sample

For instructors who run the **Consumer sample** ([`README.md`](README.md)) as a workshop. The sample's instructor
notebook prepares **the Consumer domain only**; everything else a workshop needs is listed in section 1 with where it
comes from. Background: the bootcamp's [`INSTRUCTOR.md`](../../bootcamp/INSTRUCTOR.md).

> **Not yet rehearsed.** Run the notebook once with `dry_run = true` on the event workspace first.

## 1. Pre-event checklist

| item | where | done by |
|---|---|---|
| governed tags, the domain **Consumer** with its subdomains (published), `ASSIGN` for the participants group | [`00_instructor_setup.py`](00_instructor_setup.py) (section 2) | you |
| the account group `cpg_bootcamp_participants` (and `cpg_bootcamp_admins`) with the participants in it | the bootcamp instructor notebook, step 4, or your IdP | workspace admin |
| **CAN USE** on a SQL warehouse for every participant (Genie runs its SQL there) | the bootcamp instructor notebook, step 3.3, or the warehouse's *Permissions* | workspace admin |
| catalogs `cpg_consumer_<short name>`, or `CREATE CATALOG` | participants create them in notebook 01, or the bootcamp instructor notebook with `catalog_prefix = cpg_consumer_` | metastore admin |
| serverless, the repository as a Git folder, GitHub MCP | bootcamp INSTRUCTOR.md 1.1-1.2 | admins |
| one rehearsal of steps 1-6 as a **non-admin** participant | this sample's README | you |

## 2. Running `00_instructor_setup.py`

Attach to **Serverless** and **Run all**.

| widget | default | meaning |
|---|---|---|
| `mode` | `setup` | `teardown_domain` after the event (section 4) |
| `dry_run` | **`false`** | Run all makes the changes; `true` = check only |
| `confirm_teardown` | blank | teardown deletes only when this equals `teardown_domain` |
| `apply_grants` | `true` | `false` = report the ASSIGN permissions, change nothing |
| `participants_group` | `cpg_bootcamp_participants` | gets ASSIGN on the domain tags; the notebook does not create it |
| `warehouse_id` | blank = first serverless warehouse | the warehouse step 6 runs its tag queries on |
| `tag_prefix` | blank | `zz_test_` when testing |
| `create_subdomains` / `publish_domains` | `true` / `true` | |

What it does:

| step | what |
|---|---|
| 2 | admin check, account id |
| 3.1 | Domains API reachable; the previews *Discover* and *tags on Genie Agents* |
| 3.3 | resolves the **SQL warehouse id** (widget, or the first serverless warehouse). It does **not** check or grant warehouse permissions |
| 4 | the governed tag `Consumer` and one per subdomain (`Consumer/<Subdomain>`), the domain and its subdomains, published |
| 5 | ASSIGN on those tags for the participants group |
| 6 | **all tags of the domain**: a table of definitions (tag, domain state, origin, ASSIGN), and - through SQL on the warehouse - where the tags are applied (`system.information_schema.schema_tags` / `table_tags`) |
| 7 | summary |

Re-running is safe, and useful during the workshop: step 6 then shows which participants' schemas and tables
already carry the domain tags (only for catalogs you can see).

## 3. During the workshop

| symptom | fix |
|---|---|
| notebook 05: "governed tags missing" | this notebook has not run (or ran with `dry_run = true` or a `tag_prefix`) |
| notebook 05: no permission to assign a tag | the participant is not in `cpg_bootcamp_participants`, or step 5 reported `ACTION` (group missing) - fix and re-run |
| everything else | the sample README's troubleshooting table, then bootcamp INSTRUCTOR.md section 4 |

The optional ABAC step of notebook 03 needs ASSIGN on another tag (`class.name`, or the manufacturing sample's
`abac_tag`); that is not a domain tag, so this notebook leaves it alone.

## 4. After the workshop

1. Participants run `01_notebooks/99_cleanup.py` (dropping a catalog removes its tags).
2. Run this notebook with `mode = teardown_domain`. The first run is a dry run; set
   `confirm_teardown = teardown_domain` and run again to delete.

It deletes only the tags and domains **this** notebook created (marker
`[created by genie_bootcamp/bootcamp_domain/consumer/00_instructor_setup]`). A Consumer domain the bootcamp's instructor
notebook created, or one that existed before, is reused during setup and **kept** by teardown.
