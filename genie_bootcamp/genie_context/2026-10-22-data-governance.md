# 🔐 Nordhem Retail Group — Data Governance and Access

> **🎯 Purpose:** explains who can see which data, so Genie One can tell a user *why* an answer covers only part of
> the company. Access is enforced by Unity Catalog row filters and column masks on `retail_bootcamp.gold`,
> set up by `notebooks/2026-10-22-05-governance.py`.

### ⚡ At a glance

| | 👑 Admin | 👤 User |
|---|---|---|
| 🌍 Regions | All | Only the regions granted to them |
| 🏷️ Product categories | All | Only the categories granted to them **+ 🎁 Services & Gifts** |
| 👥 Customer name, email, phone | Visible | `***` |
| 💶 Finance (P&L, budget) | Visible | Hidden |
| 🛒 Web sessions and conversion | Visible | Hidden |
| 🚚 Shipments and delivery | Visible | Hidden |

> ✅ Rows a user is not entitled to are **removed**, not masked. To that user, the data simply does not exist.
> 🚫 A user with no entitlement sees nothing at all.

---

## 1. 🪪 How access is granted [POLICY]

- Access is stored in `governance.user_entitlements`: **one row per user × region × category**. `ALL` means every
  region or every category.
- Access is granted **only by running notebook 05** (widgets: user, regions, categories, admin). Nobody edits the
  table by hand.
- Region and category are matched **on the same row**. A user granted *Scandinavia West × Toys* and
  *Scandinavia East × Home Appliances* does **not** see Home Appliances in the West.
- The person who runs notebook 05 is always an admin.

**Example entitlements (demo users):**

| User | Region | Category | Admin |
|---|---|---|---|
| anna.west@example.com | Scandinavia West | Toys | no |
| erik.east@example.com | Scandinavia East | Home Appliances | no |
| erik.east@example.com | Scandinavia East | Outdoor Apparel | no |

> 💡 Anna asks "What are our net sales?" and gets **LEGO + Services & Gifts in Norwegian stores only**.
> Electrolux, Helly Hansen, Sweden, Denmark and online do not exist for her.

---

## 2. 🎁 The common category — Services & Gifts [DATA after notebook 05]

| Product | Name | Brand | List price |
|---|---|---|---|
| P016 | Nordhem Gift Card | Nordhem (house brand) | 50.00 EUR |
| P017 | Nordhem Care & Protection Plan | Nordhem (house brand) | 39.00 EUR |

- Sold as an extra line on orders of **every brand, in every store and online**.
- ✅ **Every user sees it** in the regions they are granted. It is the shared category that connects all teams.
- It exists only after notebook 05 has run. It is **not** in the README's validated values or in the [DATA]
  figures of the other Genie One documents.

---

## 3. 📋 What each table shows a normal user

| Gold table | Rule | Why |
|---|---|---|
| `fact_order_line`, `fact_returns`, `fact_inventory_daily` | Their region(s) **and** their category(ies) + Services & Gifts | Has store and product |
| `dim_store` | Their region(s) | Has region |
| `dim_product` | Their category(ies) + Services & Gifts | Has category |
| `dim_customer` | All rows, but name, email and phone show `***` | Customers shop across regions; personal data is protected |
| `fact_finance_monthly` | Hidden (admin-only) | GL revenue mixes all categories, so it would reveal other categories |
| `fact_web_session`, `fact_shipment` | Hidden (admin-only) | No product column, so they can't be split by category |
| 📐 `kpi_metrics` (metric view) | Follows the tables above | Online Conversion is empty for non-admins |
| `dim_date`, `dim_promotion`, `dim_supplier` | Open | Reference data, nothing sensitive |

---

## 4. 💬 How Genie One should answer under governance

| Situation | ✅ Answer like this |
|---|---|
| A user's total is lower than a company figure in these documents | "Your answer covers only the data you are entitled to (your regions and categories). Company-wide figures are visible to admins." |
| A user asks about a brand or region they can't see | "That data is outside your access. Ask a data admin to grant it through notebook 05." Never guess or estimate it. |
| A user asks for P&L, budget, conversion or delivery | "Finance, web-session and shipment data are admin-only." |
| A user sees `***` for customer names | "Customer personal data is masked for non-admin users." |
| A user asks why gift cards appear in their data | "Services & Gifts is the common category, visible to everyone in their regions." |

> ⚠️ **The Genie One documents themselves are not filtered.** The [DATA] figures in the other documents
> (e.g. Electrolux ≈ 404,000 EUR, region totals) are **company-wide reference values** that every reader of this
> space can see. For strict governance, keep the detailed documents in an **admin-only Genie One space** and give
> regional users a space with only the policy and methodology content.

---

## 5. 🧪 Test questions (run them as each user)

| # | Question | 👑 Admin | 👤 anna.west@example.com |
|---|---|---|---|
| 1 | "What are our net sales by brand?" | Electrolux, Helly Hansen, LEGO, Nordhem | LEGO and Nordhem only, West stores only |
| 2 | "Which regions do we sell in?" | East, West, South | Scandinavia West |
| 3 | "What is our operating profit vs budget?" | Answer from `fact_finance_monthly` | No data (admin-only) |
| 4 | "Show the top 5 customers by spend." | Names visible | Names show `***` |
| 5 | "How much did we sell in Services & Gifts?" | All regions | West only |
