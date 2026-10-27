---
title: Plant
domain: Manufacturing
subdomain: Asset Configuration
synonyms:
  - manufacturing facility
  - factory
  - site
  - production site
  - fabrik
  - Werk
  - Lund
  - Norrköping
  - Tampere
  - Poznań
description: "One of Fjällmark's four manufacturing facilities — Lund (SE-LUN), Norrköping (SE-NKP), Tampere (FI-TMP) and Poznań (PL-POZ) — stored in manufacturing.manufacturing_facility and referenced by every production fact."
owner: Head of Manufacturing Excellence (role)
related_assets:
  - <catalog>.manufacturing.manufacturing_facility
  - <catalog>.manufacturing.production_line
  - <catalog>.manufacturing.production_order
  - <catalog>.manufacturing.manufacturing_facility_metrics
sources:
  - Fjällmark site register (fictional)
  - bootcamp/context/company_profile.md
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: manufacturing.manufacturing_facility"
---

# Plant

## Definition

A **plant** is a manufacturing facility (`manufacturing.manufacturing_facility`). Fjällmark has four:

| Plant ID (`erp_plant_code`) | `facility_name` | City / country | Company code | Brand / products | Lines | Since |
|---|---|---|---|---|---|---|
| SE-LUN | Lund Food Plant | Lund, SWE | SE01 | Björkö Pantry — crispbread, granola, porridge, jam, bars | 4 | 2011 |
| SE-NKP | Norrköping Beverage Plant | Norrköping, SWE | SE01 | Kallkälla — sparkling water, juices | 4 | 2013 |
| FI-TMP | Tampere Oat Drink Plant | Tampere, FIN | FI01 | Kallkälla — oat drinks | 3 | **April 2025** |
| PL-POZ | Poznań Personal Care Plant | Poznań, POL | PL01 | Mjuk Care — hair, body, oral, skin care, deodorants | 5 | 2016 |

Each plant also has a short internal code in `plant_code` (e.g. `POZN`), which is the code used on
production orders (`production_order.plant_code`).

## Business rules

1. Label plants with `erp_plant_code` (SE-LUN, SE-NKP, FI-TMP, PL-POZ) or `facility_name`; join facts on
   `manufacturing_facility_id`.
2. Plant ≠ company code: plants belong to the producing entity (SE01, FI01, PL01); revenue of their
   products is booked by the selling entities.
3. Tampere is new (commissioned April 2025): compare it with other plants only after its ramp-up
   (OEE from about 55 % in 2025 to its 78 % target in June 2026 — Q2 2026 78.4 %, Q3 2026 78.9 %).
4. `commissioning_date`, `operational_status`, `number_of_production_lines` and certification flags
   (`gmp_certified`, `iso_9001_certified`, ...) describe the plant itself.

## How to calculate (SQL)

```sql
-- Plants with their lines and production volume in 2026
SELECT f.erp_plant_code,
       f.facility_name,
       f.commissioning_date,
       COUNT(DISTINCT pl.production_line_id)  AS lines,
       ROUND(SUM(po.confirmed_quantity), 0)   AS confirmed_qty_2026
FROM manufacturing.manufacturing_facility f
LEFT JOIN manufacturing.production_line  pl ON pl.manufacturing_facility_id = f.manufacturing_facility_id
LEFT JOIN manufacturing.production_order po ON po.production_line_id        = pl.production_line_id
                                            AND po.actual_finish_timestamp >= DATE'2026-01-01'
GROUP BY ALL
ORDER BY f.erp_plant_code;
```

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Filtering `plant_code = 'PL-POZ'` | `plant_code` holds the short code (`POZN`); the `PL-POZ` style ID is `erp_plant_code`. |
| Treating distribution centres (Jönköping, Oslo, Odense, Vantaa, Hamburg) as plants | They are warehouses (distribution domain), not manufacturing facilities. |
| Comparing Tampere's 2025 performance with mature plants without context | Ramp-up year. |

## Example questions

* Which plants does Fjällmark have and what do they make?
* How many production lines does each plant have?
* When did the Tampere plant start production?
