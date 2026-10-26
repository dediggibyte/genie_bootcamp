# Instructor guide: Genie, Governed

For the instructors of **"Genie, Governed: From impressive demo to trusted business application"**, Diggibyte,
Kungsgatan 60, Stockholm, **29 October 2026, 14:00-18:00** (hands-on lab 15:35-17:35). Speakers: Nivethan
Venkatachalam (Databricks MVP) and Kashif Ahmed (Databricks Solutions Architect Champion).

The participant guide is [README.md](README.md). This guide covers what has to be true *before* participants
arrive, how to get a stuck participant going again, and the two demo moments.

---

## 1. Pre-event checklist

Work through it a week before the event and again the day before. Run
[`instructor/00_instructor_setup.py`](instructor/00_instructor_setup.py) with `dry_run = true` on the morning of
the event as the final check: it verifies most of these items in code and prints **OK / ACTION / DRY-RUN** lines.

### 1.1 Repository

- [ ] **Merge the bootcamp branch into `main`.** The participant guide, the Pages bulk-import prompt and the
      GitHub MCP descriptions all point to branch `main` of `dediggibyte/genie_bootcamp`.
- [ ] **Decide the repository visibility.** It is **private** today, and two different readers need access:

      | reader | private repository needs | public repository |
      |---|---|---|
      | participants' **Git folder** (step 0) | GitHub read access for every participant **and** a Git credential in Databricks (user icon > **Settings** > **Linked accounts** > **Add Git credential**) | nothing |
      | **GitHub MCP** `system.ai.github` (Pages bulk import, Agent mode) | a GitHub organisation admin installs the [Databricks GitHub connector app](https://github.com/apps/databricks-github-connector) and grants it this repository | nothing (the connector reads public repositories by default) |

      The simplest event setup is a **public** repository. The data is synthetic and contains no personal data.
      Notebook 00, section 8, checks the visibility anonymously.

### 1.2 Workspace and account settings

| check | where | verified by 00 |
|---|---|---|
| Serverless compute for notebooks, jobs and pipelines | Admin settings > Previews / compute settings (`serverless_compute`) | yes |
| Managed MCP servers (`system.ai.*`) | Admin settings > **Previews** (`managed_mcp_servers`) | yes |
| **MCP tools in Genie Agents** | Admin settings > **Previews** (`mcp_tools_in_genie_agents`) | yes |
| Agent mode API for Genie Agents | Admin settings > **Previews** (`genie_spaces_agentic_api`) | yes |
| Discover page (Domains, Pages) | Admin settings > **Previews** (`discover_page`) | yes |
| Tags on Genie Agents (domain tag on the agent, notebook 05) | Admin settings > **Previews** (`enable_lakeview_tags`) | yes |
| **Pages** (Beta, account level) | account console > **Previews** | no: no public API, check by hand |
| Domains API (Beta) reachable | `/api/2.0/domains` | yes |
| `system.ai.github` exists, participants have `USE CATALOG system`, `USE SCHEMA` and `EXECUTE` on `system.ai` | Catalog Explorer > `system.ai` | yes, and grants them if missing |
| Agent mode and Unity Gateway available in the workspace region | Databricks docs (Designated Services) | no |
| **Databricks Apps** enabled, room for one app per participant (`router-<short name>`, lab step 6) | workspace admin settings / Apps quota | no |
| Bootcamp **Lakebase** project `fjallmark-genie-bootcamp`, participants **CAN USE** (one branch per participant) | notebook 00 section 8b | yes, and creates it |
| Serving endpoint `databricks-claude-sonnet-5-5` (router model; notebook 06 falls back to another Claude Sonnet) | Serving | no |

The names in brackets are the settings keys notebook 00 reads through `/api/2.1/settings/<name>`. It reports
missing ones as ACTION and never switches them on itself.

### 1.3 People and permissions

- [ ] Every participant is a **user of the account** and of the event workspace, with the **Workspace access**
      and **Databricks SQL access** entitlements. MCP tools do not work for consumer-only or SQL-only users.
- [ ] Account groups `cpg_bootcamp_participants` (all participants) and `cpg_bootcamp_admins` (instructors).
      Notebook 00 creates them through the workspace identity proxy API, or reports them as ACTION with
      `create_groups = false` when they come from your IdP. **Keep the names**: notebook 03 uses them, and
      members of `cpg_bootcamp_admins` bypass every lab policy (so instructors cannot demo governance with
      their own login).
- [ ] A **serverless SQL warehouse** with **CAN USE** for the participants group. Notebook 04 picks the first
      serverless warehouse a user can use, preferring *Serverless Starter Warehouse*.
- [ ] **ASSIGN** on the domain governed tags for the participants group (notebook 00, section 7). Without it
      notebook 05 cannot tag schemas.
- [ ] Participants may **create Databricks Apps** and **CAN USE** the bootcamp Lakebase project (notebook 00,
      section 8b), so notebook 06 can create their app and their Lakebase branch.

### 1.4 Catalog strategy (Default Storage)

Every participant works in their own catalog `cpg_<short name>`. On a metastore that uses **Default Storage**,
`CREATE CATALOG` from SQL or the API fails ("Metastore storage root URL does not exist"). Choose one strategy
with the `catalog_strategy` widget of notebook 00:

| strategy | what notebook 00 does | participant experience |
|---|---|---|
| `precreate` (recommended) | `CREATE CATALOG cpg_<short> MANAGED LOCATION '<managed_location>'` for each participant and makes the participant the **owner** | notebook 01 finds the catalog and continues |
| `grant_create_catalog` | `GRANT CREATE CATALOG ON METASTORE` to the participants group | notebook 01 creates the catalog; this needs a `managed_location` with `CREATE MANAGED STORAGE` on its external location |
| `none` | nothing | participants create the catalog in **Catalog** > **+** > **Create a catalog** (default storage) before notebook 01 |

Ownership matters: the owner creates schemas, functions, row filters, masks and tags, and can drop the catalog
in notebook 99. On the test workspace the working managed location was the shared root of the existing
catalogs (`s3://<bucket>/unity-catalog/<workspace id>`).

### 1.5 Rehearsal

- [ ] **Do one full participant run with a non-admin test user** (not in `cpg_bootcamp_admins`): Git folder,
      notebook 01, **bundle deploy from the workspace UI**, job, notebooks 03, 04, 05 and 06 (router app: one
      single-domain and one cross-domain question in the chat UI), GitHub MCP in Agent mode, a draft Page,
      notebook 99. On the test workspace notebook 06 ran as a workspace admin only: confirm that **CAN USE** on
      the Lakebase project is enough for a participant to create their branch.
- [ ] **Dry-run the workspace-UI bundle deploy once** with that non-admin user: Git folder >
      `bootcamp/databricks.yml` > deployments icon > target `dev` > **Deploy** > run `cpg_lakehouse_job` from
      **Bundle resources**. On the test workspace the bundle was deployed with the CLI only, so this path has
      never been executed. Correct the click path in README step 2 from what you see, and check that the CLI
      fallback in step 2 (Web Terminal: `cd bootcamp && databricks bundle deploy -t dev && databricks bundle run
      cpg_lakehouse_job -t dev`) works for a non-admin user too.
- [ ] **Test sharing with a second non-admin user:** run notebook 03 with `buddy_email` set, let the buddy query
      `finance.ar_invoice`, `consumer.dtc_order_line` and `consumer.shopper`, share the Finance Analyst (**CAN RUN**)
      and let the buddy ask it a question. Then document the grants that were really needed in README step 4.
- [ ] Build **your own** instructor catalog `cpg_<your short name>` the participant way. It is your demo
      catalog, the catalog you put into the Pages' related assets, and the recovery checkpoint
      (section 4). Keep it **ungoverned** (run notebook 03 with `rollback = true`) if participants may read it.

---

## 2. Running `00_instructor_setup`

Admins only, once per event. Attach **Serverless** and **Run all**.

1. First run with the defaults `mode = setup`, `dry_run = true`: it only checks and prints what it *would*
   change.
2. Fill in `participants` (e-mails, separated by commas, semicolons or new lines), `instructors`,
   `catalog_strategy` and `managed_location`. Review the summary.
3. Set `dry_run = false` and run again. It creates or changes only what is missing; existing objects are
   reported as **OK** and reused.

| widget | default | notes |
|---|---|---|
| `mode` | `setup` | after the event: `teardown_domains_and_tags` or `teardown_everything` (section 7) |
| `dry_run` | `true` | `false` makes the changes |
| `apply_grants` | `true` | `false` = never change permissions, report only |
| `participants`, `instructors` | blank | e-mail lists |
| `participants_group`, `admins_group` | `cpg_bootcamp_participants`, `cpg_bootcamp_admins` | keep the names |
| `create_groups` | `true` | `false` when the groups come from SCIM |
| `warehouse_id` | blank = first serverless warehouse | warehouse that gets **CAN USE** |
| `catalog_strategy`, `catalog_prefix`, `managed_location` | `precreate`, `cpg_`, blank | section 1.4 |
| `domain_names` | `Consumer,Finance,Manufacturing` | the three bootcamp domains (= governed tag keys) |
| `tag_prefix` | blank | use `zz_test_` only when testing |
| `create_subdomains`, `publish_domains` | `true`, `true` | subdomains from the industry model; published so everybody sees them |
| `github_repo` | `dediggibyte/genie_bootcamp` | checked for visibility in section 8 |
| `lakebase_project` | `fjallmark-genie-bootcamp` | the router app's Lakebase project (section 8b); blank = do not prepare step 6 |

What it sets up: the prerequisite checks (section 1.2), account groups and members, catalogs or the
`CREATE CATALOG` grant, governed tags and the domains `Consumer`, `Finance` and `Manufacturing` with their
subdomains (names and descriptions from [`context/domains/**/_domain.md`](context/domains/) and
`_subdomain.md`), `ASSIGN` on those tags (plus `class.name` for the optional ABAC exercise), MCP grants,
**CAN USE** on the warehouse, and the Lakebase project for the router app with **CAN USE** for the participants. Domains and governed tags are **account-level**: every workspace of the account
sees them.

Every catalog, governed tag and domain it creates carries the marker
`[created by genie_bootcamp/00_instructor_setup]`, and the groups it creates go into a ledger file in your home
folder (as does the Lakebase project). Teardown removes only those.

---

## 3. Bulk-import the business glossary as Pages (once per event)

There is no Pages API, so this is a UI step with Genie Code. The full instructions and the import prompt are in
[`context/README.md`](context/README.md), step A. In short:

1. Prerequisites: the domains are **published** (notebook 00), the account preview **Pages** is on, and the
   GitHub MCP can read the repository (section 1.1).
2. **Discover** > **Pages** > **Create page**, open the **Genie Code** pane, click **Bulk import pages**.
3. In the chat box, click **+** > **Connections** and select the GitHub connection (`system.ai.github`). Sign in
   to GitHub if asked.
4. Ask Genie Code to import every file in `bootcamp/context/domains/*/pages/` (27 pages, 9 per domain) using the
   YAML front matter. Replace `<catalog>` in `related_assets` with your instructor catalog.
5. Review the proposed list (duplicates, low-confidence flags, the domain or subdomain of each page). The pages
   are created as **drafts**: review them (**Discover** > **Pages** > **State** > **Draft**) and **Publish**.

Fallback when the GitHub connection is not available: **Attach files** and upload the `pages/*.md` files of one
domain at a time.

Pages are account-level and shared. Participants only create **draft** Pages of their own (README step 5c).

---

## 4. Recovery checkpoints: getting a participant unstuck

**First rule: re-run the step.** Every notebook and the job only add what is missing, so a second run is cheap
and safe. Never full-refresh the pipeline and never drop tables by hand.

| participant is stuck at | do this |
|---|---|
| **Step 0**: cannot create the Git folder | Private repository: check their **Linked accounts** credential and their GitHub access. Quick fallback: make the repository public. |
| **Step 1**: catalog cannot be created | Create it for them (notebook 00 with `catalog_strategy = precreate` and only their e-mail in `participants`), or let them use **Catalog** > **+** > **Create a catalog**. Then re-run 01. |
| **Step 1**: "databricks.yml not found" | They opened a copy of the notebook outside the Git folder. Open `bootcamp/notebooks/01_setup_catalog.py` in the Git folder. |
| **Step 2**: no **dev** target or no deployments icon | They are not on `bootcamp/databricks.yml` in their Git folder. |
| **Step 2**: the UI deploy fails or looks different | CLI fallback (README step 2): Web Terminal, `cd bootcamp && databricks bundle deploy -t dev && databricks bundle run cpg_lakehouse_job -t dev`. The participant deploys as themselves (step 3 needs them to own the tables). |
| **Step 2**: `validate` red after step 3 | Not caused by the policies any more: `validate` counts silver. Read the problem list; "foreign keys registered" or "differ from their silver table" = **Run now** again. |
| **Step 2**: they used another catalog name | Set `variables.catalog.default` in their `databricks.yml` and deploy again. |
| **Step 2**: "FAILED unexpectedly" on the pipeline page | Expected on the first run; the automatic retry finishes. Tell everybody up front (section 6). |
| **Step 2**: job red after both pipeline attempts | **Run now** on the job: it is incremental and loads no data twice. If it fails again, read the pipeline event log. |
| **Step 2 is too slow** (late joiner, about 10 minutes left before step 3) | Let them continue on the instructor checkpoint below, and let their own job finish in the background. |
| **Step 3**: still sees everything | Check `is_account_group_member('cpg_bootcamp_admins')` (instructors bypass), the `company_code` widget, `rollback`. |
| **Step 4**: agent creation fails | Missing tables (job not finished) or no warehouse access (set the `warehouse` widget, grant **CAN USE**). |
| **Step 4**: they broke an agent in the UI | Re-run notebook 04 with `force_update = true` and `domains = <that domain>`: the agent is reset to its template in place (same ID and link). |
| **Step 6**: "Genie Agents not found" | Notebook 04 did not finish, or ran with another catalog. |
| **Step 6**: Lakebase branch cannot be created | The project is missing or the participant lacks **CAN USE** (notebook 00, section 8b). |
| **Step 6**: the app crashes right after the deployment | App → **Logs**. "permission ... experiment" = grants still propagating: re-run notebook 06. A Lakebase "permission denied" after somebody removed and re-added the app's `postgres` resource: delete the participant's branch `router-<short name>` and re-run notebook 06 (it creates a fresh branch). |
| **Step 6**: the router says every analyst is "not available" | HTTP 403 from the Genie MCP servers in the app's logs: the app lost its `genie-*` resources (for example after a manual edit). Re-run notebook 06. |
| **Step 5**: governed tags missing | The domains have not been created (notebook 00). Continue with 5b and 5c. |
| **Step 5**: GitHub MCP cannot read the repository | Private repository without the connector app; or the participant is in Chat mode or has not signed in under **Configure**. |

**Instructor checkpoint (fallback, not rehearsed).** Your own ungoverned catalog `cpg_<instructor>` (section 1.5)
can stand in for a participant's catalog:

* Grant read access: `GRANT USE CATALOG ON CATALOG cpg_<instructor> TO cpg_bootcamp_participants` and
  `GRANT USE SCHEMA, SELECT ON SCHEMA cpg_<instructor>.<consumer|finance|manufacturing> TO cpg_bootcamp_participants`.
* The participant runs notebook 04 with `catalog = cpg_<instructor>`. They get their own three agents
  "Fjällmark … Analyst (cpg_\<instructor\>)" on your data.
* Limits: governance (step 3) needs an owned catalog, so the participant cannot attach policies there. And if
  *you* attach policies to the checkpoint catalog, participants who are not in its mapping table see **no rows**.
  Notebook 99 refuses to drop a catalog the participant does not own, which is what you want.
* Lighter alternative: share your own agents (or your router app, *Can use*) with the participants group so they can at least
  explore Genie.

---

## 5. Timings

### Event

| time | block |
|---|---|
| 14:00 | welcome, talks, **opening demo** (section 6.1) |
| 15:35 | hands-on lab (participant guide, steps 0-5 and the exercise) |
| 17:35 | **"prove it works"** demo slot (section 6.2) |
| 18:00 | end |

### Lab (participant guide schedule)

| time | step | measured run time on the test workspace |
|---|---|---|
| 15:35 | 0 Git folder | - |
| 15:45 | 1 notebook 01 | 64 s (fresh catalog); re-run 57 s |
| 15:50 | 2 bundle deploy + job | first run 524 s (pipeline 374 s, metric views 104 s, tags 113 s, validate 35 s); re-run 247 s; re-run after step 3: 276-283 s (11 gold tables recomputed from silver) |
| 16:10 | 3 notebook 03 | 4-5 min (*Run all*, 226-276 s) |
| 16:35 | 4 notebook 04 | about 6 min for the three agents (330-350 s, benchmarks of the three agents in parallel); one agent re-built 169 s |
| 17:00 | 5 notebook 05 | about 1 min (74 s first run: 65 tags on 3 schemas + 62 objects; re-run 61 s, 0 statements) |
| 17:10 | 6 notebook 06 | about 4 min (232 s: app creation, Lakebase branch, deployment), then 1-2 min for the app's first start; a question to one analyst 30-50 s, a cross-domain question 60-90 s |
| 17:25 | exercise and governance checklist | - |
| after | notebook 99 | about 1 min (44-58 s) |

All runs were serverless one-time notebook runs or job runs (they include serverless start-up). Expect more on
a crowded workspace: 30+ people start the job within the same few minutes.

---

## 6. Demo scripts

### 6.1 Opening: "the impressive demo is not the trusted one"

Goal: show *why* every step of the lab exists. Use your instructor catalog (replace `<catalog>`). The SQL below
was run on the test catalog; the values are from the current data.

1. **The trap.** In the SQL editor:

   ```sql
   -- the naive "revenue": webshop order totals, all currencies added up
   SELECT ROUND(SUM(order_total_amount), 0) AS naive_webshop_revenue_mixed_currencies
   FROM <catalog>.consumer.dtc_order
   WHERE year(order_date) = 2025;                      -- 961,742 (SEK + NOK + DKK + EUR, incl. VAT)

   -- the official definition: finance Net Revenue in EUR
   SELECT ROUND(MEASURE(net_revenue_eur), 0) AS net_revenue_eur
   FROM <catalog>.finance.net_revenue_metrics
   WHERE fiscal_year = 2025;                           -- 20,814,527 EUR

   -- the currency trap: the same revenue lines in company-code currency vs group currency (EUR)
   SELECT ROUND(SUM(CASE WHEN l.debit_credit_indicator = 'C' THEN l.amount_company_code_currency
                         ELSE -l.amount_company_code_currency END), 0) AS mixed_local_currencies,
          ROUND(SUM(CASE WHEN l.debit_credit_indicator = 'C' THEN l.amount_group_currency
                         ELSE -l.amount_group_currency END), 0) AS group_currency_eur
   FROM <catalog>.finance.journal_entry_line l
   JOIN <catalog>.finance.gl_account ga ON ga.gl_account_id = l.gl_account_id
   WHERE ga.account_group = 'REVENUE';                 -- 399,600,534 (meaningless) vs 56,416,937 EUR
   ```

   An agent that only sees `consumer.dtc_order` answers "what was our revenue?" with a number that is wrong
   three ways: webshop only (about 0.5 % of revenue), incl. VAT, and in mixed currencies.
2. **The trusted agent.** Ask your curated *Fjällmark Finance Analyst* "What was our total revenue in 2025?"
   and show the SQL: it uses `finance.net_revenue_metrics` and answers 20,814,527 EUR (benchmark 1).
3. **Why it is right:** the four inputs from the architecture diagram: data (industry model, keys, metric
   views), governance, Genie curation (instruction, examples, benchmarks), context (glossary). Then hand over to
   the lab.

Genie is a language model: rehearse the questions on the day, and show the benchmark score rather than one lucky
answer.

### 6.2 17:35 "prove it works"

Ask two or three participants to share their screen and walk through the governance checklist in
[README.md](README.md#governance-checklist-for-the-1735-prove-it-works-slot). If nobody volunteers, show it on a
test participant login (not an instructor login: instructors bypass the policies).

1. **Trust in numbers:** the latest benchmark evaluation of each agent (**Benchmarks** > **Evaluations**). A
   participant mapped to SE01 (the step 3 default) scores 23 of 24 over the three agents (Consumer 8/8, Finance
   8/9, Manufacturing 7/7): "How much of DE01's open receivables is overdue, in EUR?" returns an empty result
   because the DE01 rows are filtered out, which is governance working as intended. Open one Bad question and
   show **Model output** vs **Ground truth**.
2. **Governance in Genie:** "Net revenue by company code in 2026" as Anna (SE01): one row, SE01, 4,614,311 EUR.
   Switch the persona to the CFO (notebook 03, `company_code = ALL`, re-run: only the mapping changes) and ask
   again: six rows. No agent change and no pipeline run.
3. **PII:** "List shopper e-mails" is refused, or answered in aggregate. In SQL the masked values look like
   `n***@example.com`.
4. **Auditable:** `information_schema.row_filters` and `column_masks` for the catalog.
5. **Context:** Agent mode with the GitHub MCP: "According to our glossary, how is DSO defined, and what is SE01's
   DSO?" (35.8 days; the group is 39.2, DE01 65.7). Ask about SE01: with the step 3 defaults the participant is
   Anna (SE01 only), so a DE01 question returns no rows. Ask about DE01 only on a login mapped to `ALL` or `DE01`. Then **Discover** > **Domains** > *Finance* with the participant's tables
   and Finance Analyst.
6. **One entry point:** in the participant's router app ask "Compare webshop net sales with the DTC net revenue
   booked in finance for 2025, in EUR. Why do they differ?". The router asks the Consumer and the Finance Analyst,
   compares in EUR and explains the gap with returns; as SE01 (measured): 37,633.94 vs 35,662.59 EUR, webshop
   returns 1,971.40 EUR. Show the **Sources** line and the trace in the app's MLflow experiment.

---

## 7. Cleanup after the event

1. **Participants** run [`notebooks/99_cleanup.py`](notebooks/99_cleanup.py) (dry run, then type the catalog name
   into `confirm`). It trashes their three bootcamp agents, deletes their router app with its Lakebase branch
   and MLflow experiment, removes their policies and drops their catalog. They delete
   the job and pipeline in **Jobs & Pipelines** (or `databricks bundle destroy -t dev --var catalog=<catalog>`
   from the `bootcamp` folder) and their draft Pages.
2. **Leftover jobs and pipelines**: search **Jobs & Pipelines** for `cpg_lakehouse_job` and
   `cpg_lakehouse_pipeline` and delete the ones of participants who left early. Deleting a pipeline also deletes
   the tables it owns.
3. **Notebook 00 teardown** (`dry_run = true` first, then `false`):
   * `teardown_domains_and_tags`: the domains, subdomains and governed tags it created,
   * `teardown_everything`: the above, plus the catalogs whose name starts with `catalog_prefix` *and* carry its
     marker (`DROP CATALOG ... CASCADE`), plus the two account groups and the router app's Lakebase project
     (with every participant branch in it) if its ledger says it created them.

   Objects without the marker are reported as **KEEP** and left alone. Teardown stops the notebook after the
   teardown cell: it never re-creates anything.
4. **Pages:** delete the imported Pages in **Discover** > **Pages** if they should not stay in the account.
5. **GitHub:** set the repository back to private if you opened it for the event, and remove the connector app's
   access to it if you granted it.

---

## 8. Known limitations to mention

* **First pipeline update fails, retry completes.** The first run of every fresh catalog shows one
  "FAILED unexpectedly" update; the retry registers the keys. A single successful first update was not
  achievable for 123 foreign keys (evidence: [`pipeline/README.md`](pipeline/README.md)).
* **Job re-runs after step 3 recompute 11 gold tables.** Re-runs stay safe and read no files, but while the
  step 3 policies are attached every pipeline update rebuilds the 11 gold tables whose build-order hint reads
  a governed table (from silver, same rows). `validate` stays green: it counts the ungoverned silver tables.
* **Benchmarks under a row filter.** The expected values in [`genie/README.md`](genie/README.md) are for a user
  who sees all companies. Mapped to SE01 (the step 3 default), the three agents scored 23 of 24 (notebook 04 runs
  885108537636627 and 892014947463966): the DE01 overdue benchmark returns an empty result (`EMPTY_RESULT`), as
  governance intends.
* **The router app answers as its service principal, not as each user.** The app's chat UI calls the agent server
  without the signed-in user's token, and with a forwarded user token (scopes `genie`, `mcp.genie`,
  `dashboards.genie`) the managed Genie MCP endpoint answered HTTP 403 (tested 2026-10-26). Notebook 06 therefore
  governs the app's service principal like a user: `SELECT` on the gold schemas only, the participant's own
  company codes in `governance.user_company_access`, no PII. Everybody who uses a shared app gets that mapping.
* **Claude reasoning blocks.** `databricks-claude-sonnet-5-5` returns reasoning content around tool calls that the
  OpenAI Agents SDK cannot read; the router sets `thinking: between_tools` (the endpoint's "thinking off"). If you
  switch the router model, keep or adapt that setting in `app/agent_server/agent.py`.
* **Sharing with a second user is untested.** Notebook 03 section 13 (buddy grants) and sharing the agent with a
  second, non-admin user have not been run on the test workspace; README step 4 and section 13 are written as
  instructions. The documented grant set is: **CAN RUN** on the agent, **CAN USE** on the warehouse, `USE CATALOG`
  on the catalog, `USE SCHEMA` + `SELECT` on `consumer`, `finance` and `manufacturing` (tables and metric views),
  nothing on `silver` or `governance`. It relies on Unity Catalog evaluating row filters and column masks with the
  table owner's rights (the `dtc_order_line` filter reads `silver.consumer_dtc_order` and the mapping tables).
  Rehearse it (section 1.5) before you promise it.
* **Workspace-UI bundle deploy is unrehearsed.** README step 2 gives a CLI fallback (Web Terminal:
  `cd bootcamp && databricks bundle deploy -t dev && databricks bundle run cpg_lakehouse_job -t dev`). The
  participant must deploy as themselves: step 3 attaches the policies as the table owner.
* **Genie is not deterministic.** One question can flip between runs; judge the whole benchmark.
* **Product is not in the bootcamp.** Product names and brands are carried on `consumer.dtc_order_line`,
  `finance.profit_center` and `finance.standard_cost`. Manufacturing has no product names (`material_number` is
  `FG...`). B2B customer names (for example "Alpina Drogerie", storyline S6) are in `sales.trade_account`, which
  only the [full model](../full_model/README.md) builds; the bootcamp has `trade_account_id`.
* **Entity matching** is set on 53 / 40 / 28 columns of the Consumer / Finance / Manufacturing Analyst. The
  platform limit is believed to be about 120 per agent (not confirmed), so add new ones sparingly.
* The industry view `consumer.consent_record_metrics` reports a double opt-in rate of 0 for most consent types.
  That comes from the industry model's definition.
