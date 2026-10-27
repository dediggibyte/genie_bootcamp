---
title: Company Code
domain: Finance
subdomain: Organizational Accounting
synonyms:
  - legal entity
  - entity
  - company
  - subsidiary
  - bolag
  - Buchungskreis
  - SE01
  - DE01
description: "A company code is one of Fjällmark's six legal entities (SE01, NO01, DK01, FI01, DE01, PL01). Every transaction belongs to exactly one company code, which also determines its local currency and the data an analyst is allowed to see."
owner: Group Financial Controller (role)
related_assets:
  - <catalog>.finance.company_code
  - <catalog>.finance.journal_entry_line
  - <catalog>.finance.ar_invoice
  - <catalog>.consumer.dtc_order
  - <catalog>.consumer.address
  - <catalog>.consumer.subscription
sources:
  - Fjällmark legal entity register (fictional)
  - bootcamp/context/company_profile.md
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: finance.company_code"
---

# Company Code

## Definition

A **company code** is the accounting identifier of a legal entity. Fjällmark has six:

| `company_code.code` | Legal entity (`legal_name`) | Country | `currency_code` | DTC markets |
|---|---|---|---|---|
| SE01 | Fjällmark Consumer Goods AB (parent) | SWE | SEK | Sweden |
| NO01 | Fjällmark Norge AS | NOR | NOK | Norway |
| DK01 | Fjällmark Danmark A/S | DNK | DKK | Denmark |
| FI01 | Fjällmark Suomi Oy | FIN | EUR | Finland |
| DE01 | Fjällmark Deutschland GmbH | DEU | EUR | Germany **and Netherlands** |
| PL01 | Fjällmark Polska Sp. z o.o. | POL | PLN | — (plant and local B2B) |

## Business rules

1. Facts carry the **surrogate key** `company_code_id`; the business code is `company_code.code`.
   Join: `<fact>.company_code_id = company_code.company_code_id`. Tables with `company_code_id`:
   `finance.journal_entry`, `journal_entry_line`, `ar_invoice`, `ar_payment`, `consumer.dtc_order`,
   `consumer.subscription`, and more.
2. `company_code.currency_code` is the entity's **local currency**; `parent_company_code_id` points to
   SE01 for all subsidiaries (SE01 is the group parent).
3. A **market** (the order's ship-to country, `dtc_order.ship_to_address_id` → `consumer.address.country_code`,
   = `shopper.country_code` for registered shoppers) is not the same as a company code: Dutch webshop
   orders (`NLD`) are booked by **DE01** in EUR, so neither the company code nor the currency identifies
   the Netherlands.
4. **Row-level security:** analysts are entitled to company codes (governance mapping
   `governance.user_company_access`). If you see only SE01 rows, that is the row filter working —
   not missing data. State this when results look incomplete.
5. "Group" or "total" = all six company codes, amounts in EUR.

## How to calculate (SQL)

```sql
-- The company codes with their local currency and parent
SELECT c.code, c.legal_name, c.country_code, c.currency_code, p.code AS parent_code
FROM finance.company_code c
LEFT JOIN finance.company_code p ON p.company_code_id = c.parent_company_code_id
ORDER BY c.code;
```

```sql
-- DTC orders per company code and market = ship-to country (shows that NLD is booked by DE01)
SELECT cc.code                                                      AS company_code,
       coalesce(a.country_code, sh.country_code, 'Unknown (guest)') AS market,
       o.currency_code,
       COUNT(*)                                                     AS orders
FROM consumer.dtc_order o
JOIN finance.company_code cc ON cc.company_code_id = o.company_code_id
LEFT JOIN consumer.address a  ON a.address_id  = o.ship_to_address_id
LEFT JOIN consumer.shopper sh ON sh.shopper_id = o.shopper_id
WHERE lower(o.order_status) <> 'cancelled'
GROUP BY ALL
ORDER BY company_code, market;
```

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Filtering `company_code_id = 'SE01'` | `company_code_id` is a numeric key; filter `company_code.code = 'SE01'`. |
| "Netherlands revenue = 0 because there is no NL company code" | NL is a DTC market of DE01. |
| Market derived from `company_code` or `currency_code` | DE01 / EUR contains Germany **and** the Netherlands; use the ship-to country. |
| Treating PL01 as a sales market | PL01 runs the Poznań plant and some local B2B; it has no webshop. |

## Example questions

* Which legal entities does Fjällmark have and what are their currencies?
* Net revenue by company code for 2026.
* Which company code books the Dutch webshop orders?
