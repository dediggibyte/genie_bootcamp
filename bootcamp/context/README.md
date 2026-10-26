# `bootcamp/context/` — the business knowledge behind Fjällmark's data

A Genie Agent can only answer as well as it understands the business. Tables and metric
views tell it *what the data is*; this folder tells it *what the business means*:
which revenue is the official one, why you never add SEK to EUR, what "active shopper"
means, which production order statuses count as "completed".

Everything here is plain Markdown in Git, so business definitions are versioned,
reviewed in pull requests and reused in three places:

| Where | How it gets there | Who uses it |
|---|---|---|
| **Unity Catalog Semantics → Pages** (Discover) | Instructor bulk-imports the pages with Genie Code (step A) | Genie One, every Discover user |
| **Your Genie Agents** (Consumer, Finance and Manufacturing Analyst) | You attach the GitHub MCP as a source in Agent mode (step B) | You and the users of your agents |
| **Your own draft Page** | You draft a Page for your own business question (step C) | Only you, until it is published |

In the lab, steps B and C are step 5 of the participant guide ([`bootcamp/README.md`](../README.md#step-5-business-context-10-min));
step A is part of the instructor preparation ([`bootcamp/INSTRUCTOR.md`](../INSTRUCTOR.md#3-bulk-import-the-business-glossary-as-pages-once-per-event)).

> The company, its people, brands, plants and customers are **fictional**. There is no
> personal data in this folder — and there must never be: Pages are account-level and may be
> replicated globally.

---

## 1. What is in this folder

```text
bootcamp/context/
├── README.md                     ← you are here
├── company_profile.md            ← the company: entities, brands, plants, markets, calendar, known events
├── glossary.csv                  ← one row per business term (term, synonyms, domain, page path, assets)
├── genie/
│   └── agent_instructions.md     ← draft text instructions for the Genie Agent
└── domains/
    ├── consumer/                 ← DTC webshop, shoppers, loyalty, consent
    ├── finance/                  ← legal entities, general ledger, receivables, costing
    └── manufacturing/            ← plants, lines, production orders, yield, OEE
        ├── _domain.md            ← the domain: purpose, owner, key tables, key metrics
        ├── <subdomain>/_subdomain.md   ← one per subdomain: its tables, in business words
        └── pages/<term>.md       ← one business concept per file = one UC Semantics Page
```

The domain and subdomain structure follows the **Lakehouse Industry Data Model for
Consumer Goods (v2, MVM)** that the bootcamp pipeline builds (see `tools/model/` at the
repository root). The bootcamp covers three of its domains - consumer, finance and
manufacturing. Each domain is one gold schema in your catalog (`<catalog>.consumer`,
`<catalog>.finance`, `<catalog>.manufacturing`) and every table keeps its exact industry name.
Product attributes the questions need (product name, brand, category) are carried on the
bootcamp tables themselves (e.g. `consumer.dtc_order_line.brand_code`,
`finance.profit_center.brand_code`).

## 2. How the files map to UC Semantics

UC Semantics (Discover) has two building blocks:

* **Domains / subdomains** — a business-aligned grouping of data assets. Each domain *is*
  a governed tag; a subdomain is a governed tag named `<Domain>/<Subdomain>`. An asset
  belongs to a domain when it carries the tag (a tag on a schema is inherited by its tables).
  Domains are account-level, so the **instructor** creates them once (notebook
  `00_instructor_setup`); in notebook `05_business_context` **you** tag your own gold schemas,
  tables and Genie Agent.
* **Pages** — one governed definition of a business concept, filed under exactly one domain
  or subdomain. Genie One prioritises a published Page over what it infers from the data and
  cites it in its answer.

| This repo | UC Semantics |
|---|---|
| `domains/<domain>/_domain.md` | Domain (governed tag `Consumer`, `Finance`, `Manufacturing`) — subtitle, description, owners |
| `domains/<domain>/<subdomain>/_subdomain.md` | Subdomain (governed tag e.g. `Finance/General Ledger`) |
| `domains/<domain>/pages/<term>.md` | Page |

Every page file starts with YAML front matter whose keys map 1:1 to the Page fields:

| Front matter key | Page field | Notes |
|---|---|---|
| `title` | Page name | The business term, e.g. "Net Revenue" |
| `domain` + `subdomain` | **Domain** | File the page under the subdomain (`<domain>/<subdomain>`) |
| `owner` | **Owner** | A fictional *role*, never a person. In Discover the importer becomes the owner; reassign if needed |
| `synonyms` | **Synonyms** | Words people actually type ("sales", "turnover", "top line") |
| `description` | **Description** | One or two sentences |
| *(Markdown body)* | **Page body** | Definition, business rules, calculation SQL, pitfalls, example questions |
| `related_assets` | **Related assets** | Fully qualified UC names with a `<catalog>` placeholder — replace it with the instructor's catalog when importing, e.g. `cpg_<instructor_short_name>.finance.journal_entry_line` |
| `sources` | **Sources** | Where the definition comes from (policy, data model, this repo) |

Calculation SQL in the pages uses two-part names (`finance.journal_entry_line`) — run it after
`USE CATALOG cpg_<your_short_name>;` in the SQL editor or a notebook (Genie writes fully qualified
names itself). It runs against the **gold tables** so that you can read exactly what happens. The
**governed** way to use a KPI is its metric view
(`<catalog>.finance.net_revenue_metrics`, `<catalog>.consumer.dtc_sales_metrics`,
`<catalog>.finance.receivables_metrics`, `<catalog>.manufacturing.production_performance_metrics`)
— the pages say which one. The pages name the metric views but deliberately do not quote their
measure names (those may still change); the SQL against the gold tables is the reference that the
metric views must reproduce.

The numbers quoted in the pages (DSO, OEE, yield, AOV ratios, ...) come from the data in
`bootcamp/data/` - see `bootcamp/data/README.md` (storylines S1-S7) for the full list. The
definitions use the same semantics as that data dictionary: DTC amounts are local currency and
include VAT (`order_total_amount` also shipping), finance amounts are reported in EUR via
`amount_group_currency`, returns are booked to account 3050 in the order month, and the fiscal
year is the calendar year with one fiscal period per month (last closed period: September 2026).

---

## 3. Step A — Instructor: bulk-import the official Pages (once per event)

Prerequisites (instructor checklist):

1. Notebook `bootcamp/instructor/00_instructor_setup` has created the governed tags and the domains
   `Consumer`, `Finance`, `Manufacturing` with their subdomains (Discover → Domains).
   At least one domain must exist before any Page can be created.
2. The **Pages** preview (Beta) is enabled for the account (account console → Previews).
3. The GitHub managed MCP service `system.ai.github` exists and users have `EXECUTE` on it
   (`USE CATALOG system`, `USE SCHEMA system.ai` are inherited by account users).
4. **The repository must be readable by the GitHub MCP.**
   `https://github.com/dediggibyte/genie_bootcamp` is **private** today. The GitHub MCP can read
   only **public** repositories by default. Either make the repository public before the event,
   **or** have a GitHub organisation admin install the
   [Databricks GitHub connector app](https://github.com/apps/databricks-github-connector)
   and grant it access to this repository
   ([docs](https://docs.databricks.com/aws/en/agents/mcp-tools/built-in-mcp-services#enable-github-write-access-and-private-repository-access)).
   Every user who uses the connector signs in to GitHub with their own account (OAuth).

Import:

1. In the workspace, click **Discover → Pages → Create page**.
2. If the Genie Code pane is not open, click the **Genie Code** icon (upper right).
3. Click **Bulk import pages**.
4. Click **+** in the chat box → **Connections** → select the GitHub connection
   (`system.ai.github`) and sign in to GitHub if asked.
5. Tell Genie Code what to import, for example:

   > Import the business glossary for Fjällmark Consumer Goods from the GitHub repository
   > `dediggibyte/genie_bootcamp`, branch `main`, folder `bootcamp/context/domains/`. Create one Page
   > per file in every `pages/` folder. Use the YAML front matter: `title` = page name, file the
   > page under the domain `domain`/`subdomain` (domains Consumer, Finance, Manufacturing),
   > `synonyms` = synonyms, `description` = description, the Markdown body = page
   > body, `related_assets` = related assets (replace `<catalog>` with `cpg_<instructor_short_name>`),
   > `sources` = sources. Use `bootcamp/context/company_profile.md` and
   > `bootcamp/context/glossary.csv` only as background, do not create pages for them.

6. Genie Code proposes a de-duplicated list of Pages. Resolve conflict / duplicate /
   low-confidence flags, check that each page landed in the right (sub)domain, exclude
   anything you do not want.
7. Genie Code creates all Pages as **drafts**. Review them (Discover → Pages → **State** →
   **Draft**) and click **Publish**. Published Pages are used by every Genie One conversation.

> Tip: if the GitHub connection is not available yet, use **Attach files** in step 4 and
> upload the `pages/*.md` files of one domain at a time — the front matter works the same.

## 4. Step B — Participant: give your Genie Agents the business context (GitHub MCP)

Your three agents - "Fjällmark Consumer / Finance / Manufacturing Analyst" (created in notebook
`04_genie_agent`) - already have text instructions (from `bootcamp/context/genie/agent_instructions.md`:
the shared rules plus their domain's rules). In **Agent mode** an agent can also *look up* definitions in
this folder while it answers. Start with the Finance Analyst.

Prerequisites: the workspace preview **MCP tools in Genie Agents** is on (instructor),
you have the *Workspace access* and *Databricks SQL access* entitlements, and the repository
is readable (see step A, point 4).

1. Open your Genie Agent → **Sources** tab → **Add** → **MCP services** → select
   `system.ai.github` (GitHub).
2. In the source **Description**, paste:

   > Business glossary of Fjällmark Consumer Goods. Before you answer a question that uses a
   > business term (revenue, net revenue, GMV, margin, COGS, DSO, overdue, OEE, yield, scrap,
   > active shopper, AOV, loyalty tier, CLTV segment, consent, subscription, return rate,
   > plant, fiscal period, company code ...), read the matching file in the GitHub repository
   > `dediggibyte/genie_bootcamp`, folder `bootcamp/context/domains/<domain>/pages/` (index:
   > `bootcamp/context/glossary.csv`), and follow its business rules and calculation. Company facts
   > (entities, currencies, plants, fiscal calendar) are in `bootcamp/context/company_profile.md`.
   > Read only; never create issues, branches or pull requests.

3. Disable the write tools of the connector (keep search / get file contents).
4. In the chat box switch on **Agent mode**, open **Configure** and **sign in** to GitHub.
   Every tool call runs with *your* GitHub permissions.
5. Ask, for example: *"What was net revenue in Q2 2026 by company code? Use the official
   definition."* — watch the agent read `finance/pages/net_revenue.md` before it writes SQL.
   Read-only tools (search, fetch) run automatically; any write tool would pause for your
   approval (**Allow once / Always allow in this chat / Reject**).

MCP tools work only in Agent mode (not in Chat mode), and through the API only read tools work.

## 5. Step C — Participant: draft a Page for your own business question

1. **Discover → Pages → Create page** (or open the domain, e.g. *Finance*, and create it there
   so the **Domain** is pre-filled).
2. Pick a concept your business question depends on that is *not* defined yet — e.g.
   "Subscription churn rate", "Gold-member share of DTC revenue", "Line changeover loss".
3. Fill in **Synonyms**, **Description** and the **Page body** — copy the structure of any file
   in `domains/*/pages/` (definition → business rules → calculation SQL → pitfalls → example
   questions). Or let **Genie Code** draft it: attach `bootcamp/context/` via the GitHub connection,
   your gold table, and the metric view.
4. Add your tables / metric views under **Related assets** and this repository under **Sources**.
5. Click **Save as draft**. Drafts are visible only to you (and curators), and Genie One uses a
   draft **only in your own conversations** — ideal for testing a definition before asking the
   domain owner to publish it.
6. Ask Genie One your question and check that it cites your draft Page.

## 6. Contributing

* One concept per file, file name = `snake_case` of the term.
* Every column you mention must exist in the industry model — run
  `python3 -I tools/check_context.py` from the repository root (checks front matter,
  domains/subdomains, related assets and every `table.column` / SQL reference against the three
  bootcamp domains of `tools/model/consumer_goods_v2_mvm.json`).
* Never put personal data, real company names or credentials in this folder.

## 7. License and notice

The glossary pages, company profile and agent instructions are original bootcamp material about the fictional
company Fjällmark. The domain and subdomain files (`domains/<domain>/_domain.md`,
`domains/<domain>/<subdomain>/_subdomain.md`) and some page front matter use the domain, subdomain, table and
column names of the Databricks *Lakehouse Industry Data Model, Consumer Goods v2 (MVM)*, and several of them quote
its descriptions. That model is © Databricks, Inc. and licensed under the Databricks license: see
[`../LICENSE.md`](../LICENSE.md) and [`../NOTICE.md`](../NOTICE.md). Those files are modified for this bootcamp and
say so in a `license` line of their front matter and in a footer (`tools/check_context.py` checks the line).
