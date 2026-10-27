---
title: Production Line
domain: Manufacturing
subdomain: Asset Configuration
synonyms:
  - line
  - manufacturing line
  - filling line
  - packaging line
  - PL-POZ-L2
  - produktionslinje
  - Linie
description: "A physical production line inside a plant (16 in total, e.g. PL-POZ-L2 = Poznań liquid filling for shampoo and body wash), stored in manufacturing.production_line with its type, design speed, OEE and scrap targets."
owner: Head of Manufacturing Excellence (role)
related_assets:
  - <catalog>.manufacturing.production_line
  - <catalog>.manufacturing.manufacturing_facility
  - <catalog>.manufacturing.production_order
  - <catalog>.manufacturing.yield_record
  - <catalog>.manufacturing.production_line_metrics
sources:
  - Fjällmark site register, line list (fictional)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: manufacturing.production_line"
---

# Production Line

## Definition

A **production line** is a set of connected equipment that makes one family of products. People on
the shop floor call lines `<plant>-L<n>`; in the data the line is identified by `line_code`:

| Shop-floor name | `line_code` | Plant | What it makes | `line_type` |
|---|---|---|---|---|
| SE-LUN-L1 … L4 | LUNDL1 … LUNDL4 | Lund | crispbread; granola; porridge; jam and muesli bars | packaging / blending / packaging / filling |
| SE-NKP-L1 … L4 | NKPGL1 … NKPGL4 | Norrköping | PET 1.5 L; cans 0.33 L; juice cartons; multipacks | filling ×3, palletizing |
| FI-TMP-L1 … L3 | TMPRL1 … TMPRL3 | Tampere | oat base processing; 1 L cartons; small formats/crates | blending / filling / packaging |
| PL-POZ-L1 … L5 | POZNL1 … POZNL5 | Poznań | bulk mixing; **liquid filling (shampoo, body wash)**; tubes (toothpaste, hand cream); deodorants; gift sets | blending / filling ×3 / assembly |

So **PL-POZ-L2 = `line_code` `POZNL2`**. The shop-floor name is also stored in `mes_asset_tag`
(`PL-POZ-L2`), and `line_name` starts with it (e.g. "PL-POZ-L2 Liquid filling - shampoo and body wash").

## Business rules

1. Join facts on `production_line_id`; label with `line_code` (and plant via
   `manufacturing_facility_id`).
2. Targets per line: `nominal_oee_target_percent`, `scrap_rate_target_percent`,
   `changeover_time_standard_minutes`, `design_speed_units_per_hour`.
3. Compare lines of the same `line_type`; a palletising line and a filling line have different
   normal performance.
4. **Known event:** PL-POZ-L2 (`POZNL2`) had worn filler nozzles in March 2026 — yield ~87 %, scrap
   ×3, high downtime, late orders; fixed 4 April 2026.

## How to calculate (SQL)

```sql
-- Lines with plant, type and targets
SELECT f.erp_plant_code,
       pl.line_code,
       pl.line_name,
       pl.line_type,
       pl.design_speed_units_per_hour,
       pl.nominal_oee_target_percent,
       pl.scrap_rate_target_percent
FROM manufacturing.production_line pl
JOIN manufacturing.manufacturing_facility f
  ON f.manufacturing_facility_id = pl.manufacturing_facility_id
ORDER BY f.erp_plant_code, pl.line_code;
```

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| `WHERE line_code = 'PL-POZ-L2'` | The code is `POZNL2`; the dashed form is in `mes_asset_tag`. |
| Using `work_center` as "line" | Work centres are machines/stations *within* a line. |

## Example questions

* What does line PL-POZ-L2 produce, and what is its OEE target?
* Which lines does the Norrköping plant have?
* Which line had the lowest yield in March 2026?
