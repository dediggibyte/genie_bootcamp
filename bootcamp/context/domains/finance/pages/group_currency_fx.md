---
title: Group Currency & FX
domain: Finance
subdomain: General Ledger
synonyms:
  - group currency
  - reporting currency
  - EUR
  - euro
  - FX
  - exchange rate
  - currency conversion
  - local currency
  - company code currency
description: "EUR is Fjällmark's group reporting currency. Amounts in different currencies (SEK, NOK, DKK, PLN, EUR) may only be added after conversion to EUR; the general ledger stores the EUR amount on every line."
owner: Group Financial Controller (role)
related_assets:
  - <catalog>.finance.journal_entry_line
  - <catalog>.finance.journal_entry
  - <catalog>.finance.company_code
  - <catalog>.finance.net_revenue_metrics
  - <catalog>.consumer.dtc_order
  - <catalog>.finance.ar_invoice
sources:
  - Fjällmark Group Accounting Manual, chapter 2 "Currencies and translation" (fictional policy document)
  - bootcamp/context/company_profile.md
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: finance.journal_entry_line amount columns"
---

# Group Currency & FX

## Definition

* **Group currency** = **EUR**. All consolidated (cross-entity) figures are reported in EUR.
* **Local currency / company code currency** = the currency a legal entity keeps its books in:
  SE01 SEK, NO01 NOK, DK01 DKK, FI01 EUR, DE01 EUR, PL01 PLN (`company_code.currency_code`).
* **Transaction / document currency** = the currency of the individual document (an order, an
  invoice).
* **FX rate** = EUR per one unit of local currency. Finance uses a **monthly average rate**
  (roughly SEK 0.087, NOK 0.085, DKK 0.134, PLN 0.232; it moves within about ±2 % month to month).

## Business rules

1. **Never add amounts in different currencies.** A total over more than one company code or
   market must be in EUR.
2. In the general ledger use **`journal_entry_line.amount_group_currency`** — it is already EUR
   (= `amount_company_code_currency` × the month's rate). The rate itself is stored on every line in
   `journal_entry_line.exchange_rate` (EUR per unit of the company-code currency). The currency codes
   are on the line: `transaction_currency_code`, `company_code_currency_code`, `group_currency_code`
   (always EUR).
3. Operational tables carry **local amounts only**:
   * `consumer.dtc_order` / `dtc_order_line` — amounts in `currency_code` (market currency:
     SEK for Sweden, NOK Norway, DKK Denmark, EUR Finland, Germany, Netherlands);
   * `finance.ar_invoice` — amounts in `currency_code` (the selling entity's currency);
   * `consumer.subscription` — `currency_code`;
   * `manufacturing.production_order` and `finance.standard_cost` — `currency_code` of the plant /
     costing (SEK, EUR, PLN). They carry **no company code**, so key the FX table by currency
     (`journal_entry_line.company_code_currency_code` + year + period) instead of `company_code_id`
     (example on the *Production Cost Variance* page).
   Group them **by currency**, or convert them with the GL rate of the same company code (or currency)
   and month (query below) before adding.
4. Balances at a closing date (e.g. open receivables at 2026-09-30) are translated with the rate of
   the closing month (September 2026).
5. Ratios inside one entity (DSO, margin %, return rate) do not need conversion.

## How to calculate (SQL)

```sql
-- Monthly FX rate (EUR per unit of local currency) used by finance, per company code
SELECT cc.code                                   AS company_code,
       cc.currency_code                          AS local_currency,
       je.fiscal_year,
       je.fiscal_period,
       ROUND(AVG(jel.exchange_rate), 6)          AS eur_per_local_unit,
       ROUND(SUM(jel.amount_group_currency) / SUM(jel.amount_company_code_currency), 6) AS check_from_amounts
FROM finance.journal_entry_line jel
JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
JOIN finance.company_code cc ON cc.company_code_id  = jel.company_code_id
WHERE je.posting_status = 'posted'
GROUP BY ALL
ORDER BY company_code, je.fiscal_year, je.fiscal_period;
```

```sql
-- Convert DTC webshop net merchandise value to EUR with the finance rate of the same entity and month
WITH fx AS (
  SELECT jel.company_code_id, je.fiscal_year, je.fiscal_period, AVG(jel.exchange_rate) AS eur_rate
  FROM finance.journal_entry_line jel
  JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
  WHERE je.posting_status = 'posted'
  GROUP BY ALL
)
SELECT date_trunc('MONTH', o.order_date)                         AS order_month,
       ROUND(SUM((o.subtotal_amount - o.discount_amount) * fx.eur_rate), 2) AS dtc_net_merchandise_eur
FROM consumer.dtc_order o
JOIN fx ON fx.company_code_id = o.company_code_id
       AND fx.fiscal_year     = year(o.order_date)
       AND fx.fiscal_period   = month(o.order_date)
WHERE lower(o.order_status) <> 'cancelled'
GROUP BY ALL
ORDER BY order_month;
```

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `SUM(amount_company_code_currency)` over all company codes | Adds SEK, NOK, DKK, PLN and EUR — the "total" is meaningless (SEK numbers dominate). |
| `SUM(dtc_order.order_total_amount)` for "total webshop sales" | Mixes SEK/NOK/DKK with EUR; also includes VAT and shipping. |
| Converting with a single fixed rate for all months | Finance uses monthly rates; small differences to the GL will appear. Use `journal_entry_line.exchange_rate` of the same company code and month. |
| Converting FI01 / DE01 amounts | They are already EUR (rate 1.0). |
| Using `journal_entry.exchange_rate` (header) | It is the document → local rate (e.g. ≈ 11.5 SEK per EUR on a few EUR-denominated documents) and NULL on most documents. The EUR rate is `journal_entry_line.exchange_rate`. |
| Joining `journal_entry_line` directly to orders or invoices to pick up a rate | Every order row is multiplied by all GL lines of the entity (fan-out). Build a one-row-per-company-and-month FX table first (query above). |

## Example questions

* What was total Net Revenue in EUR across all entities last quarter?
* Which exchange rate did finance use for SEK in March 2026?
* Show webshop sales by market in EUR.
