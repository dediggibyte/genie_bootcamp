"""Curated manufacturing domain: four plants, 16 lines, work centres, equipment, routings,
BOMs and the production execution trail (planned orders -> production orders ->
confirmations, batch records and yield records).

Story hooks
-----------
S3  Poznań line PL-POZ-L2 (``line_code`` POZNL2, liquid filling of shampoo / body wash):
    worn filler nozzles in March 2026 -> yield 97 % -> ~87 %, scrap x3, downtime spike,
    late orders, ``yield_loss_reason_code = 'EQMALF'`` (equipment malfunction). Fixed by
    maintenance on 2026-04-04 (``world.REPAIR_DATE``). The cost of the extra scrap shows up as
    production variance on PL01 in March 2026 (finance).
S4  Tampere oat-drink plant commissioned April 2025: OEE ramps from ~55 % to the 78 % target,
    reached by June 2026.

Volumes: every plant produces one month ahead of demand - the standard cost of the goods it
makes in a month equals the standard cost of goods sold (B2B + DTC, all group companies) of the
following month, so finished-goods stock stays at about one month of sales.

Quantities are in EA (consumer units). Costs are in the plant's company-code currency
(SEK for Lund/Norrköping, EUR for Tampere, PLN for Poznań). ``yield_percentage`` =
confirmed_quantity / order_quantity * 100.
"""
import datetime
import math
from decimal import Decimal, ROUND_HALF_UP

from . import engine, texts, world
from .curated_consumer import std_cost_factor
from .curated_finance import PLANT_PC, plant_demand_eur

D = Decimal

PLANT_CC = {"LUND": ("SE01PLUN", "SE01MLUN", None), "NKPG": ("SE01PNKP", "SE01MNKP", None),
            "TMPR": ("FI01PTMP", "FI01MTMP", "FI01QTMP"), "POZN": ("PL01PPOZ", "PL01MPOZ", "PL01QPOZ")}
LINE_SUBCAT = {"LUNDL1": "CRISPBREAD", "LUNDL2": "GRANOLA", "LUNDL3": "PORRIDGE", "LUNDL4": "JAM",
               "NKPGL1": "SPARKLING", "NKPGL2": "SPARKLING", "NKPGL3": "JUICE", "NKPGL4": "SPARKLING",
               "TMPRL1": "OATDRINK", "TMPRL2": "OATDRINK", "TMPRL3": "OATDRINK", "POZNL1": "HAIRCARE",
               "POZNL2": "HAIRCARE", "POZNL3": "ORALCARE", "POZNL4": "DEODORANT", "POZNL5": "GIFTSET"}
WC_TYPES = {"filling": ["filling_machine", "capper", "labeler"],
            "blending": ["mixing_vessel", "mixing_vessel", "packaging_line"],
            "packaging": ["packaging_line", "labeler", "palletizer"],
            "palletizing": ["packaging_line", "palletizer", "labeler"],
            "assembly": ["packaging_line", "labeler", "palletizer"]}
WC_LABEL = {"filling_machine": "Filler", "capper": "Capper", "labeler": "Labeler", "mixing_vessel": "Mixing vessel",
            "packaging_line": "Packer", "palletizer": "Palletizer"}
EQUIP = {"filling_machine": [("Rotary filler 12-head", 14000), ("Filler nozzle set", 1800), ("Product buffer tank", 6500)],
         "capper": [("Servo capper", 7200), ("Cap sorter", 2400), ("Torque tester", 900)],
         "labeler": [("Label applicator", 3800), ("Vision inspection camera", 1500), ("Checkweigher", 2600)],
         "mixing_vessel": [("Mixing tank 5000 L", 21000), ("High-shear homogeniser", 9800), ("CIP skid", 7600)],
         "packaging_line": [("Case erector", 5200), ("Flow wrapper", 6100), ("Conveyor section", 1200)],
         "palletizer": [("Robot palletizer", 18000), ("Stretch wrapper", 4800), ("Pallet label printer", 600)]}
PLANT_CODE_SHORT = {"LUND": "L", "NKPG": "N", "TMPR": "T", "POZN": "P"}

_CUR = {"LUND": "SEK", "NKPG": "SEK", "TMPR": "EUR", "POZN": "PLN"}


def plant_currency(plant):
    return _CUR[plant]


def unit_cost_local(sku, year, plant):
    cur = _CUR[plant]
    return (sku["std_cost_eur"] * std_cost_factor(year) / D(str(world.FX_BASE[cur]))).quantize(D("0.0001"))


def _ts(d, h=8, m=0, s=0):
    return datetime.datetime.combine(d, datetime.time(h, m, s))


def _q(x, places="0.01"):
    return x.quantize(D(places), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------------------
# facilities (needed by product.sku) and other masters
# --------------------------------------------------------------------------------------

def facilities(reg):
    fqn = "manufacturing.manufacturing_facility"
    pool = reg.alloc(fqn, len(world.PLANTS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    rows = []
    for i, p in enumerate(world.PLANTS):
        ids[p["code"]] = pool[i]
        n_lines = sum(1 for ln in world.LINES if ln[1] == p["code"])
        created = _ts(p["commissioned"] - datetime.timedelta(days=200))
        last_audit = datetime.date(2026, 2, 10) + datetime.timedelta(days=i * 23)
        fixed = {
            "manufacturing_facility_id": pool[i], "cost_center_id": reg.ctx["cc"][PLANT_CC[p["code"]][0]],
            "profit_center_id": reg.ctx["pc"][PLANT_PC[p["code"]]],
            "address_line_1": p["street"], "address_line_2": None, "city": p["city"],
            "commissioning_date": p["commissioned"], "country_code": p["country"], "created_timestamp": created,
            "email_address": "plant.%s@example.com" % p["code"].lower(),
            "energy_consumption_kwh_per_year": D(str(4200000 + 950000 * n_lines)),
            "epa_site_number": None, "erp_plant_code": p["erp"], "facility_name": p["name"],
            "facility_type": p["type"], "fda_establishment_number": None,
            "gmp_certification_date": max(p["commissioned"], datetime.date(2023, 5, 15)) + datetime.timedelta(days=i * 17),
            "gmp_certified": True,
            "gmp_expiration_date": max(p["commissioned"], datetime.date(2023, 5, 15)) + datetime.timedelta(days=i * 17 + 3 * 365),
            "iso_14001_certified": p["code"] != "TMPR", "iso_22716_compliance_tier": "tier_1" if p["code"] == "POZN" else None,
            "iso_9001_certified": True, "last_audit_date": last_audit,
            "last_modified_timestamp": _ts(datetime.date(2026, 4, 6) if p["code"] == "POZN" else datetime.date(2026, 7, 1) + datetime.timedelta(days=i), 9),
            "latitude": D(str(p["lat"])).quantize(D("0.0000001")), "longitude": D(str(p["lon"])).quantize(D("0.0000001")),
            "mes_system_integrated": True, "next_audit_date": last_audit + datetime.timedelta(days=365),
            "number_of_production_lines": n_lines, "operational_status": "active", "osha_establishment_number": None,
            "ownership_type": "owned", "phone_number": engine.phone(p["country"], rnd), "plant_code": p["code"],
            "postal_code": p["postal"], "primary_product_category": world.BRAND[p["brand"]]["category_name"],
            "production_capacity_units_per_day": D(str(int(sum(ln[5] for ln in world.LINES if ln[1] == p["code"])
                                                           * world.SHIFT_HOURS_PER_DAY))),
            "shift_pattern": "two_shift",
            "square_footage": D(str(180000 + 40000 * n_lines)), "state_province": p["region"],
            "sustainability_rating": "gold" if p["code"] in ("LUND", "NKPG") else ("silver" if p["code"] == "POZN" else "not_rated"),
            "time_zone": world.COUNTRY_TZ[p["country"]],
            "water_consumption_cubic_meters_per_year": D(str(38000 + 21000 * n_lines)), "workforce_headcount": p["headcount"],
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=p["country"]))
    reg.ctx["plant_id"] = ids
    reg.rows[fqn] = rows


def line_skus(line_code):
    if line_code == "TMPRL1":
        return [s for s in world.SKUS if s["plant"] == "TMPR"]
    if line_code == "POZNL1":
        return [s for s in world.SKUS if s["line"] == "POZNL2"]
    return [s for s in world.SKUS if s["line"] == line_code]


def masters(reg):
    _lines(reg)
    _work_centers(reg)
    _equipment(reg)
    _routings_and_boms(reg)


def _lines(reg):
    fqn = "manufacturing.production_line"
    pool = reg.alloc(fqn, len(world.LINES))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = {}
    rows = []
    for i, (code, plant, tag, name, ltype, speed) in enumerate(world.LINES):
        ids[code] = pool[i]
        p = world.PLANT[plant]
        comm = p["commissioned"] + datetime.timedelta(days=(i % 4) * 9)
        incident = code == world.INCIDENT_LINE
        notes = None
        overhaul = comm + datetime.timedelta(days=365 * 5) if comm < datetime.date(2020, 1, 1) else None
        if incident:
            notes = ("Filler nozzle set replaced %s after wear-related under-fills and leaks in March 2026 "
                     "(yield dropped to about 87 percent). Nozzle inspection moved to a weekly checklist."
                     % world.REPAIR_DATE.isoformat())
            overhaul = world.REPAIR_DATE
        if plant == "TMPR":
            notes = "Commissioned April 2025; ramp-up programme to reach 78 percent OEE by mid-2026."
        fixed = {
            "production_line_id": pool[i], "cost_center_id": reg.ctx["cc"][PLANT_CC[plant][0]],
            "manufacturing_facility_id": reg.ctx["plant_id"][plant],
            "product_category_id": reg.ctx["category_id"][LINE_SUBCAT[code]],
            "allergen_handling_flag": plant == "LUND",
            "allergen_types": ("gluten, sesame, nuts" if code in ("LUNDL1", "LUNDL2") else "gluten, nuts" if code == "LUNDL4"
                               else "gluten" if code == "LUNDL3" else None),
            "asset_tag_number": tag, "automation_level": "fully_automated" if plant in ("NKPG", "TMPR") else "semi_automated",
            "changeover_time_standard_minutes": D(str(25 + (i % 5) * 10)),
            "cleaning_validation_protocol": "CVP-%s-v%d" % (tag, 2 + i % 3), "commissioning_date": comm,
            "created_timestamp": _ts(comm - datetime.timedelta(days=30)), "crew_size_standard": 3 + i % 4,
            "depreciation_method": "straight_line", "design_speed_units_per_hour": D(str(speed)),
            "energy_consumption_kwh_per_unit": D("0.0120") + D(str(i % 5)) / 1000,
            "environmental_control_required": plant == "POZN",
            "gmp_classification": "gmp_b" if plant == "POZN" else "gmp_c",
            "humidity_range_percent": "35-60" if plant == "LUND" else "40-65",
            "installed_power_kw": D(str(120 + 35 * (i % 6))), "last_major_overhaul_date": overhaul,
            "last_modified_timestamp": _ts(datetime.date(2026, 4, 4) if incident else datetime.date(2026, 6, 1) + datetime.timedelta(days=i), 14),
            "line_code": code, "line_length_meters": D(str(35 + 6 * (i % 7))),
            "line_name": "%s %s" % (tag, name), "line_type": ltype,
            "mean_time_between_failures_hours": D("190.00") if incident else D(str(420 + 37 * (i % 9))),
            "mean_time_to_repair_hours": D("3.40") if incident else D(str(1.2 + 0.3 * (i % 5))),
            "mes_asset_tag": tag, "next_scheduled_maintenance_date": datetime.date(2026, 10, 20) + datetime.timedelta(days=7 * (i % 6)),
            "nominal_oee_target_percent": D("78.00") if plant == "TMPR" else D(str(p["oee"] + 4)),
            "notes": notes, "operational_status": "active", "quality_inspection_frequency": "per_batch" if plant == "POZN" else "hourly",
            "record_source_system": "Siemens Opcenter MES", "scada_integration_enabled": True,
            "scrap_rate_target_percent": D("2.50"), "shift_pattern": "two_shift",
            "temperature_range_celsius": "18-25", "useful_life_years": 15,
        }
        rows.append(gen.row(i, rnd, fixed, anchor=_ts(comm), country=p["country"]))
    reg.ctx["line_id"] = ids
    reg.rows[fqn] = rows


def _work_centers(reg):
    fqn = "manufacturing.work_center"
    specs = []
    for (code, plant, tag, name, ltype, speed) in world.LINES:
        types = WC_TYPES[ltype]
        for j, wt in enumerate(types):
            specs.append((code, plant, tag, wt, j, speed))
    pool = reg.alloc(fqn, len(specs))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    rows = []
    reg.ctx["wc_by_line"] = {}
    for i, (code, plant, tag, wt, j, speed) in enumerate(specs):
        p = world.PLANT[plant]
        comm = p["commissioned"] + datetime.timedelta(days=j * 3)
        wid = pool[i]
        reg.ctx["wc_by_line"].setdefault(code, []).append(wid)
        fixed = {
            "work_center_id": wid, "cost_center_id": reg.ctx["cc"][PLANT_CC[plant][0]],
            "manufacturing_facility_id": reg.ctx["plant_id"][plant], "production_line_id": reg.ctx["line_id"][code],
            "available_capacity_hours_per_day": D("15.00"),
            "capacity_unit": "units_per_hour", "category": "machine",
            "code": "%sWC%d" % (code, j + 1), "commissioning_date": comm,
            "created_timestamp": _ts(comm - datetime.timedelta(days=10)), "decommissioning_date": None,
            "description": "%s %s on line %s (%s)" % (WC_LABEL[wt], j + 1, tag, p["name"]),
            "gmp_qualification_status": "fully_qualified",
            "maintenance_class": "critical" if wt in ("filling_machine", "mixing_vessel") else "high",
            "maintenance_strategy": "preventive" if plant != "TMPR" else "condition_based",
            "mes_equipment_code": "%s-WC%d" % (tag, j + 1), "name": "%s %s" % (tag, WC_LABEL[wt]),
            "operator_skill_level_required": "advanced" if wt in ("filling_machine", "mixing_vessel") else "intermediate",
            "rated_capacity": D(str(speed)), "standard_cycle_time_minutes": _q(D(60) / D(speed) * 100, "0.01"),
            "utilization_rate_percent": D(str(26 + (i % 9))), "work_center_status": "active", "work_center_type": wt,
            "crew_size": 1 if wt in ("labeler", "capper", "palletizer") else 2,
            "energy_consumption_kwh_per_hour": D(str(18 + 9 * (i % 7))) + D("0.5000"),
            "clean_room_class": "ISO 8" if plant == "POZN" and wt in ("filling_machine", "mixing_vessel") else None,
            "hazardous_area_classification": "ATEX Zone 2" if (plant == "POZN" and code == "POZNL4") else None,
            "humidity_controlled_flag": plant in ("LUND", "POZN"), "temperature_controlled_flag": plant in ("TMPR", "POZN"),
            "last_calibration_date": datetime.date(2026, 9, 15) - datetime.timedelta(days=(i * 11) % 170),
            "calibration_due_date": datetime.date(2026, 9, 15) - datetime.timedelta(days=(i * 11) % 170) + datetime.timedelta(days=180),
            "qualification_date": max(comm + datetime.timedelta(days=30), datetime.date(2024, 3, 1) + datetime.timedelta(days=(i * 13) % 300)),
            "requalification_due_date": max(comm + datetime.timedelta(days=30), datetime.date(2024, 3, 1) + datetime.timedelta(days=(i * 13) % 300)) + datetime.timedelta(days=3 * 365),
            "setup_time_minutes": D(str(15 + 5 * (i % 6))), "teardown_time_minutes": D(str(10 + 5 * (i % 4))),
            "shift_pattern": "two_shift",
            "modified_timestamp": _ts(datetime.date(2026, 4, 4) if code == world.INCIDENT_LINE else datetime.date(2026, 5, 1) + datetime.timedelta(days=i), 10),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=_ts(comm), country=p["country"]))
    reg.rows[fqn] = rows


def _equipment(reg):
    fqn = "manufacturing.equipment"
    specs = []
    for (code, plant, tag, name, ltype, speed) in world.LINES:
        specs.append((code, plant, tag, None, "line", "Line control cabinet", 9500, 0))
        for j, wt in enumerate(WC_TYPES[ltype]):
            for k, (ename, cost_eur) in enumerate(EQUIP[wt]):
                specs.append((code, plant, tag, j, wt, ename, cost_eur, k + 1))
    pool = reg.alloc(fqn, len(specs))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    rows = []
    parent = None
    for i, (code, plant, tag, wc_j, wt, ename, cost_eur, k) in enumerate(specs):
        p = world.PLANT[plant]
        cur = _CUR[plant]
        if wt == "line":
            parent = pool[i]
        inst = p["commissioned"] + datetime.timedelta(days=5 + i % 20)
        nozzle = code == world.INCIDENT_LINE and ename == "Filler nozzle set"
        last_maint = world.REPAIR_DATE if nozzle else (datetime.date(2026, 9, 1) - datetime.timedelta(days=(i * 7) % 80))
        freq = 30 if nozzle else (60 if wt in ("filling_machine", "mixing_vessel") else 90)
        oee_t = D("80.00") if plant != "TMPR" else D("78.00")
        oee_a = D(str(round(p["oee"] + (i % 5) - 2 + (2 if plant == "TMPR" else 0), 2)))
        fixed = {
            "equipment_id": pool[i], "cost_center_id": reg.ctx["cc"][PLANT_CC[plant][1]],
            "gl_account_id": reg.ctx["gl"][(p["company"], "1290")], "manufacturing_facility_id": reg.ctx["plant_id"][plant],
            "parent_equipment_id": None if wt == "line" else parent, "production_line_id": reg.ctx["line_id"][code],
            "work_center_id": None if wt == "line" else reg.ctx["wc_by_line"][code][wc_j],
            "acquisition_cost": _q(D(cost_eur) * 10 / D(str(world.FX_BASE[cur])) if cur != "EUR" else D(cost_eur) * 10),
            "asset_tag": "%s-E%02d" % (tag, k), "capacity_units": "units_per_hour", "capacity_value": D(str(world.LINE[code][5])),
            "compliance_gmp": True, "currency": cur, "department": "Maintenance",
            "depreciation_start_date": inst, "depreciation_end_date": inst + datetime.timedelta(days=365 * 10),
            "depreciation_method": "straight_line",
            "description": ("%s on %s. Replaced %s after nozzle wear caused under-fills in March 2026."
                            % (ename, tag, world.REPAIR_DATE.isoformat())
                            if nozzle else "%s on %s (%s)" % (ename, tag, p["name"])),
            "equipment_status": "active", "equipment_type": wt,
            "hazard_classification": "medium" if wt in ("mixing_vessel", "palletizer") else "low",
            "installation_date": inst, "last_maintenance_date": last_maint,
            "location_code": plant, "maintenance_frequency_days": freq, "manufacturer": rnd.choice(texts.MANUFACTURERS),
            "name": "%s %s" % (tag, ename), "next_maintenance_due": last_maint + datetime.timedelta(days=freq),
            "oee_actual": oee_a, "oee_target": oee_t, "purchase_date": inst - datetime.timedelta(days=60),
            "warranty_start_date": inst, "warranty_end_date": inst + datetime.timedelta(days=730),
            "weight_kg": D(str({"line": 350, "filling_machine": 2400, "capper": 650, "labeler": 420,
                                "mixing_vessel": 3800, "packaging_line": 900, "palletizer": 1600}[wt] + 37 * k)),
            "voltage": D("400.00"), "power_rating_kw": D(str({"line": 4, "filling_machine": 45, "capper": 11,
                                                             "labeler": 6, "mixing_vessel": 75, "packaging_line": 15,
                                                             "palletizer": 22}[wt] + k)),
            "safety_rating": "PL d" if wt in ("palletizer", "filling_machine", "mixing_vessel") else "PL c",
            "last_calibration_date": last_maint - datetime.timedelta(days=(i * 7) % 60),
            "calibration_due_date": last_maint - datetime.timedelta(days=(i * 7) % 60) + datetime.timedelta(days=365),
            "total_usage_hours": D(str(max(200, (world.EXTRACT_DATE - inst).days * 4))),
            "mtbf_hours": D("190.00") if nozzle else D(str(600 + 40 * (i % 15))),
            "mttr_hours": D("3.40") if nozzle else D(str(round(0.8 + 0.2 * (i % 9), 2))),
            "maintenance_cost": _q(D(cost_eur) * D("0.04") / D(str(world.FX_BASE[cur]))),
            "energy_consumption_kwh": D(str(max(500, (world.EXTRACT_DATE - inst).days * (8 + 3 * (i % 5))))),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=_ts(inst), country=p["country"]))
    reg.rows[fqn] = rows


def _routings_and_boms(reg):
    fq_r, fq_b = "manufacturing.routing", "manufacturing.manufacturing_bom"
    specs = []
    for i, s in enumerate(world.SKUS):
        specs.append((s, 1, True))
    alt = [s for i, s in enumerate(world.SKUS) if i % 3 == 0][:31]
    for s in alt:
        specs.append((s, 2, False))
    rpool = reg.alloc(fq_r, len(specs))
    bpool = reg.alloc(fq_b, len(specs))
    rgen, bgen = reg.gen(fq_r), reg.gen(fq_b)
    rrnd, brnd = reg.rng(fq_r), reg.rng(fq_b)
    rrows, brows = [], []
    reg.ctx["routing_of"] = {}
    reg.ctx["bom_of"] = {}
    for i, (s, version, primary) in enumerate(specs):
        plant = s["plant"]
        p = world.PLANT[plant]
        cur = _CUR[plant]
        valid_from = max(s["launch"] - datetime.timedelta(days=45), p["commissioned"] - datetime.timedelta(days=30))
        if not primary:
            valid_from = s["launch"] + datetime.timedelta(days=400)
            if valid_from > datetime.date(2026, 6, 1):
                valid_from = datetime.date(2026, 6, 1)
        created = _ts(valid_from - datetime.timedelta(days=14), 10)
        speed = world.LINE[s["line"]][5]
        base_qty = D("1000.000")
        machine_min = _q(D(1000) / D(speed) * 60)
        unit_cost = unit_cost_local(s, 2026, plant)
        status_r = "active" if primary else ("inactive" if i % 2 else "under_review")
        if primary:
            reg.ctx["routing_of"][s["code"]] = rpool[i]
            reg.ctx["bom_of"][s["code"]] = bpool[i]
        rfixed = {
            "routing_id": rpool[i], "manufacturing_facility_id": reg.ctx["plant_id"][plant],
            "product_bom_id": reg.ctx["product_bom_id"][s["code"]], "sku_id": reg.ctx["sku_id"][s["code"]],
            "approval_status": "approved" if primary else "pending", "approved_timestamp": created + datetime.timedelta(days=7) if primary else None,
            "base_quantity": base_qty, "base_unit_of_measure": "EA", "changeover_time_minutes": D(str(25 + i % 30)),
            "cost_currency_code": cur, "created_timestamp": created,
            "description": "%s routing v%d for %s on %s" % ("Standard" if primary else "Alternative", version, s["full_name"], world.LINE[s["line"]][2]),
            "expected_scrap_percentage": D("2.40"), "expected_yield_percentage": D("97.10"),
            "gmp_critical_flag": plant == "POZN", "ipc_checkpoint_count": 3 if plant == "POZN" else 2,
            "lot_size_restriction": "minimum", "maximum_lot_size": D("400000.000"), "minimum_lot_size": D("5000.000"),
            "operation_sequence": "0010 Prepare and mix | 0020 Fill or form | 0030 Pack and palletize",
            "production_scheduler_code": "FWD" + PLANT_CODE_SHORT[plant] + "01",
            "routing_number": "RT%s%06d%02d" % (PLANT_CODE_SHORT[plant], s["index"] + 1, version),
            "routing_status": status_r, "routing_type": "standard" if primary else "alternative",
            "standard_cost_amount": _q(unit_cost * base_qty), "total_labor_time_minutes": _q(machine_min * D("1.4")),
            "total_machine_time_minutes": machine_min, "total_setup_time_minutes": D(str(25 + i % 30)),
            "total_standard_lead_time_hours": _q((machine_min + D(60)) / 60 + 4),
            "valid_from_date": valid_from,
            "valid_to_date": (min(valid_from + datetime.timedelta(days=180), datetime.date(2026, 9, 30))
                              if status_r == "inactive" else None), "version": str(version),
        }
        rrows.append(rgen.row(i, rrnd, rfixed, anchor=created, country=p["country"]))
        bfixed = {
            "manufacturing_bom_id": bpool[i], "manufacturing_facility_id": reg.ctx["plant_id"][plant],
            "primary_manufacturing_sku_id": reg.ctx["sku_id"][s["code"]],
            "product_bom_id": rfixed["product_bom_id"], "allergen_flag": plant == "LUND",
            "approval_date": valid_from, "base_quantity": D("1000.000000"), "base_unit_of_measure": "EA",
            "bom_number": "BOM-%s-%02d" % (s["code"], version), "bom_status": "active" if primary else "pending",
            "bom_type": "production", "component_effective_start_date": valid_from, "component_effective_end_date": None,
            "component_item_category": "stock", "component_item_number": 10,
            "cost_allocation_percentage": D("45.00"), "created_timestamp": created,
            "effective_start_date": valid_from, "effective_end_date": None,
            "hazardous_material_flag": s["form"] == "spray",
            "inci_name": "Sodium Laureth Sulfate" if s["subcat"] in ("HAIRCARE", "BODYCARE") else None,
            "lead_time_days": 7 + i % 14, "scrap_factor_percentage": D("2.40"),
            "version": "%d.0" % version, "alternative_item_group": None if primary else "ALT%02d" % (i % 20),
            "alternative_item_priority": 1 if primary else 2,
            "sustainability_certification": {"FOOD": "EU Organic (oats)", "BEVERAGE": "FSC (cartons)",
                                             "PERSONAL_CARE": "RSPO mass balance"}[s["category"]],
            "regulatory_compliance_notes": ("Allergen control: contains gluten (oats, rye)" if plant == "LUND" else
                                            "EU Cosmetics Regulation 1223/2009 - PIF reference on file" if plant == "POZN"
                                            else None),
        }
        brows.append(bgen.row(i, brnd, bfixed, anchor=created, country=p["country"]))
    reg.rows[fq_r] = rrows
    reg.rows[fq_b] = brows


# --------------------------------------------------------------------------------------
# production execution
# --------------------------------------------------------------------------------------

def _oee(plant, line, day, rnd):
    if plant == "TMPR":
        span = (world.TAMPERE_RAMP_END - world.TAMPERE_START).days
        x = min(1.0, max(0.0, (day - world.TAMPERE_START).days / float(span)))
        base = world.TAMPERE_OEE_START + (world.TAMPERE_OEE_TARGET - world.TAMPERE_OEE_START) * (x ** 0.9)
        return base + rnd.gauss(0, 2.0 if x < 1 else 1.1)
    if line == world.INCIDENT_LINE and world.INCIDENT_START <= day < world.INCIDENT_END:
        return 57.0 + rnd.gauss(0, 2.5)
    return world.PLANT[plant]["oee"] + rnd.gauss(0, 2.6)


def _loss_rates(plant, line, day, rnd):
    """(scrap rate, other shortfall rate)."""
    if line == world.INCIDENT_LINE and world.INCIDENT_START <= day < world.INCIDENT_END:
        return max(0.06, rnd.gauss(0.074, 0.006)), max(0.04, rnd.gauss(0.0545, 0.005))
    if plant == "TMPR":
        span = (world.TAMPERE_RAMP_END - world.TAMPERE_START).days
        x = min(1.0, max(0.0, (day - world.TAMPERE_START).days / float(span)))
        return max(0.008, rnd.gauss(0.05 - 0.026 * x, 0.004)), max(0.0, rnd.gauss(0.02 - 0.015 * x, 0.002))
    return max(0.006, rnd.gauss(0.024, 0.005)), max(0.0, rnd.gauss(0.005, 0.0015))


_LOSS_CODES = [("CHGOVR", "Changeover losses at start-up of run"), ("MATSHT", "Material shortage interrupted run"),
               ("LBLERR", "Label misalignment rejects"), ("FILLWT", "Fill weight adjustments at start-up"),
               ("CARTJM", "Carton feed jams")]


def production(reg):
    """planned_order, production_order, production_confirmation, batch_record, yield_record."""
    rnd = reg.rng("manufacturing", "production")
    orders = []
    for (code, plant, tag, name, ltype, speed) in world.LINES:
        skus_all = line_skus(code)
        for (y, m) in world.MONTHS:
            ms, me = world.month_start(y, m), world.month_end(y, m)
            if plant == "TMPR" and ms < world.TAMPERE_START:
                continue
            skus = [s for s in skus_all if world.sku_available(s, me) or world.sku_available(s, ms)]
            if not skus:
                continue
            n = rnd.choice([3, 4, 4, 4, 5, 5])
            slot = (me - ms).days / float(n)
            for j in range(n):
                s = rnd.choice(skus)
                day = ms + datetime.timedelta(days=int(slot * j + rnd.uniform(0, max(1.0, slot - 2))))
                orders.append((day, code, plant, s))
    orders.sort(key=lambda o: (o[0], o[1]))
    # volume plan: each plant produces next month's demand (standard cost of goods sold in EUR)
    demand = plant_demand_eur(reg)
    n_po = {}
    for (day, code, plant, s) in orders:
        n_po[(plant, day.year, day.month)] = n_po.get((plant, day.year, day.month), 0) + 1

    def target_eur(plant, y, m):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        if (ny, nm) > (world.TXN_END.year, world.TXN_END.month) or (plant, ny, nm) not in demand:
            ny, nm = y, m
        return float(demand.get((plant, ny, nm), 0))

    fq = "manufacturing.production_order"
    pool = reg.alloc(fq, len(orders))
    gen = reg.gen(fq)
    prnd = reg.rng(fq)
    srnd = reg.rng(fq, "schedule")
    po_rows = []
    supervisors = {}
    for plant in world.PLANT:
        c = world.PLANT[plant]["country"]
        supervisors[plant] = ["%s %s" % (prnd.choice(world.FIRST_NAMES[c]), prnd.choice(world.LAST_NAMES[c])) for _ in range(4)]
    as_of = datetime.datetime.combine(world.AS_OF_DATE, datetime.time(23, 59, 59))
    for i, (day, code, plant, s) in enumerate(orders):
        cur = _CUR[plant]
        unit = unit_cost_local(s, day.year, plant)
        speed = world.LINE[code][5]
        noise = 0.8 + 0.4 * (prnd.uniform(9000, 30000) - 9000) / 21000.0
        value_eur = target_eur(plant, day.year, day.month) / n_po[(plant, day.year, day.month)] * noise
        unit_eur = float(s["std_cost_eur"] * std_cost_factor(day.year))
        qty = max(500, int(round(value_eur / unit_eur / 100.0)) * 100)
        oee = max(35.0, min(92.0, _oee(plant, code, day, prnd)))
        scrap_r, short_r = _loss_rates(plant, code, day, prnd)
        incident = code == world.INCIDENT_LINE and world.INCIDENT_START <= day < world.INCIDENT_END
        downtime = prnd.randint(180, 320) if incident else (
            prnd.randint(50, 160) if plant == "TMPR" and day < datetime.date(2025, 12, 1) else prnd.randint(10, 60))
        changeover = prnd.randint(20, 60)
        std_hours = qty / (speed * 0.80)
        act_hours = qty / (speed * oee / 100.0) + downtime / 60.0 + changeover / 60.0
        sched_start = day
        sched_finish = day + datetime.timedelta(days=max(0, int(math.ceil((std_hours + 4) / 16.0)) - 1))
        created = _ts(day - datetime.timedelta(days=prnd.randint(5, 12)), prnd.randint(7, 16), prnd.randint(0, 59))
        released = created + datetime.timedelta(days=prnd.randint(1, 3), hours=prnd.randint(0, 6))
        a_start = _ts(day, 6) + datetime.timedelta(minutes=prnd.randint(-60, 360))
        # planned start of the first operation: the crew normally starts within -20..+50 minutes of plan
        p_start = a_start - datetime.timedelta(minutes=srnd.randint(-20, 50))
        if incident:
            # line stopped for troubleshooting before the run could start
            a_start += datetime.timedelta(hours=prnd.randint(20, 52))
        elif prnd.random() < 0.04:
            a_start += datetime.timedelta(hours=prnd.randint(16, 30))
        a_finish = a_start + datetime.timedelta(hours=act_hours)
        scrap = int(round(qty * scrap_r))
        confirmed = int(round(qty * (1 - scrap_r - short_r)))
        planned_cost = _q(D(qty) * unit)
        progress = 1.0
        if a_start > as_of:
            status = "REL" if released <= as_of else "CRTD"
            progress = 0.0
        elif a_finish > as_of:
            status = "PCNF"
            progress = max(0.1, (as_of - a_start).total_seconds() / max(1.0, (a_finish - a_start).total_seconds()))
        else:
            age = (world.AS_OF_DATE - a_finish.date()).days
            status = (prnd.choice(["CNF", "DLV", "TECO"]) if age < 25 else
                      ("CLSD" if prnd.random() < 0.82 else prnd.choice(["TECO", "DLV"])))
        if status == "CRTD":
            released = None
        if progress < 1.0:
            scrap = int(scrap * progress)
            confirmed = int(confirmed * progress)
        variance_unit = (D(str(scrap_r - 0.024)) + D(str(short_r - 0.005))) if progress > 0 else D(0)
        if incident:
            variance_unit += D("0.06")      # overtime, rework labour and expedited nozzle parts
        noise = D(str(round(prnd.gauss(0, 0.012), 4)))
        actual_cost = _q(planned_cost * D(str(progress)) * (1 + noise + variance_unit)) if progress > 0 else D("0.00")
        late = a_finish.date() > sched_finish if progress >= 1.0 else False
        yield_pct = _q(D(confirmed) / D(qty) * 100) if progress >= 1.0 else (
            _q(D(confirmed) / (D(qty) * D(str(progress))) * 100) if progress > 0 else None)
        note = None
        if incident:
            note = "Under-fills and cap leaks on PL-POZ-L2 filler; nozzle wear suspected. Extra checkweigher rejects."
        elif late:
            note = "Finished after scheduled date due to downtime."
        last_mod = (a_finish if progress >= 1.0 else (as_of if progress > 0 else (released or created)))
        last_mod = last_mod + datetime.timedelta(hours=prnd.randint(1, 30))
        if last_mod > world.EXTRACT_TS:
            last_mod = world.EXTRACT_TS
        order_type = "PP10" if code in ("TMPRL1", "POZNL1") else ("PP03" if prnd.random() < 0.02 else "PP01")
        mto_order = mto_account = None
        if order_type == "PP01" and prnd.random() < 0.06:
            # make-to-order: customer-specific promotional pack for a key account
            keys = [t["key"] for t in world.TRADE if t["tier"] == "tier_1_national"]
            mto_account = reg.ctx["trade_id"][prnd.choice(keys)]
            mto_order = reg.pick("sales.order", prnd)
        sup = supervisors[plant][i % 4]
        fn_, ln_ = sup.split(" ", 1)
        batch_no = "B%s%s%04d" % (PLANT_CODE_SHORT[plant], day.strftime("%y%m%d"), i % 10000)
        fixed = {
            "production_order_id": pool[i], "cost_center_id": reg.ctx["cc"][PLANT_CC[plant][0]],
            "gl_account_id": reg.ctx["gl"][(world.PLANT[plant]["company"], "1420")],
            "inspection_plan_id": reg.pick("quality.inspection_plan", prnd),
            "manufacturing_bom_id": reg.ctx["bom_of"][s["code"]], "manufacturing_facility_id": reg.ctx["plant_id"][plant],
            "product_category_id": reg.ctx["category_id"][s["subcat"]], "production_line_id": reg.ctx["line_id"][code],
            "routing_id": reg.ctx["routing_of"][s["code"]], "sales_order_id": mto_order, "sku_id": reg.ctx["sku_id"][s["code"]],
            "trade_account_id": mto_account,
            "actual_cost": actual_cost if progress > 0 else None,
            "actual_finish_timestamp": a_finish.replace(microsecond=0) if progress >= 1.0 else None,
            "actual_start_timestamp": a_start if progress > 0 else None, "batch_number": batch_no,
            "changeover_time_minutes": changeover, "confirmed_quantity": D(confirmed) if progress > 0 else D(0),
            "cost_object": "OR%010d" % (1000000 + i), "created_timestamp": created, "currency_code": cur,
            "downtime_minutes": int(downtime * progress), "gmp_compliance_flag": True,
            "inspection_lot_number": "IL%09d" % (300000000 + i), "last_modified_timestamp": last_mod,
            "material_number": "FG%06d" % (s["index"] + 1), "mrp_controller": PLANT_CODE_SHORT[plant] + "01",
            "notes": note, "oee_percentage": _q(D(str(oee))) if progress > 0 else None,
            "order_number": "10%08d" % (i + 1), "order_quantity": D(qty), "order_status": status,
            "order_type": order_type, "planned_cost": planned_cost, "plant_code": plant,
            "priority": "2" if incident else prnd.choice(["3", "3", "3", "4", "2"]),
            "production_supervisor": sup, "production_version": "0001", "quality_inspection_required": True,
            "released_by": engine.user_id(fn_, ln_.split(" ")[-1], prnd) if released else None,
            "released_timestamp": released, "scheduled_finish_date": sched_finish, "scheduled_start_date": sched_start,
            "scrap_quantity": D(scrap) if progress > 0 else D(0), "settlement_rule": "FUL", "unit_of_measure": "EA",
            "yield_percentage": yield_pct, "created_by": "SVC_MRP" if prnd.random() < 0.7 else engine.user_id(fn_, ln_, prnd),
        }
        row = gen.row(i, prnd, fixed, anchor=created, country=world.PLANT[plant]["country"])
        row["_meta"] = {"sku": s, "plant": plant, "line": code, "day": day, "progress": progress, "oee": oee,
                        "scrap_r": scrap_r, "short_r": short_r, "incident": incident, "unit": unit,
                        "a_start": a_start, "a_finish": a_finish, "downtime": downtime, "changeover": changeover,
                        "created": created, "p_start": p_start,
                        "std_span": datetime.timedelta(hours=std_hours + changeover / 60.0)}
        po_rows.append(row)
    reg.rows[fq] = po_rows
    _planned_orders(reg, po_rows)
    _batches_yields_confirmations(reg, po_rows)


def _planned_orders(reg, po_rows):
    fq = "manufacturing.planned_order"
    rnd = reg.rng(fq)
    specs = []
    for po in po_rows:
        specs.append(("conv", po))
    n_extra = 400
    for k in range(n_extra):
        if k < 300:
            ym = world.MONTHS[rnd.randrange(len(world.MONTHS))]
            day = world.month_start(*ym) + datetime.timedelta(days=rnd.randint(0, 27))
            specs.append(("cancel", day))
        else:
            day = datetime.date(2026, 10, 1) + datetime.timedelta(days=rnd.randint(0, 8))
            specs.append(("open", day))
    def sort_key(sp):
        if sp[0] == "conv":
            return sp[1]["_meta"]["created"] - datetime.timedelta(days=7)
        return _ts(sp[1], 3)
    specs.sort(key=sort_key)
    pool = reg.alloc(fq, len(specs))
    gen = reg.gen(fq)
    rows = []
    for i, (kind, x) in enumerate(specs):
        if kind == "conv":
            meta = x["_meta"]
            s, plant, line = meta["sku"], meta["plant"], meta["line"]
            created = meta["created"] - datetime.timedelta(days=rnd.randint(4, 12), hours=rnd.randint(0, 12))
            start, finish = x["scheduled_start_date"], x["scheduled_finish_date"]
            qty = x["order_quantity"]
            status, conv_status, conv_date = "CONVERTED", "FULLY_CONVERTED", meta["created"].date()
            firm = created.date() + datetime.timedelta(days=1)
            po_id = x["production_order_id"]
        else:
            day = x
            plant = rnd.choice(list(world.PLANT))
            if plant == "TMPR" and day < world.TAMPERE_START:
                plant = "POZN"
            cands = [sk for sk in world.SKUS if sk["plant"] == plant and world.sku_available(sk, day)] or \
                    [sk for sk in world.SKUS if sk["plant"] == plant]
            s = rnd.choice(cands)
            line = s["line"]
            created = _ts(day - datetime.timedelta(days=rnd.randint(5, 14)), rnd.randint(1, 5))
            start = day
            finish = min(day + datetime.timedelta(days=rnd.randint(0, 2)), world.EXTRACT_DATE)
            qty = D(max(500, int(round(rnd.uniform(9000, 28000) / float(s["std_cost_eur"]) / 100.0)) * 100))
            po_id, conv_date = None, None
            if kind == "cancel":
                status = rnd.choice(["CANCELLED", "DELETED"])
                conv_status, firm = "NOT_CONVERTED", None
            else:
                status = rnd.choice(["DRAFT", "FIRMED", "RELEASED"])
                conv_status = "NOT_CONVERTED"
                firm = created.date() + datetime.timedelta(days=1) if status != "DRAFT" else None
        ex = None
        if kind == "cancel":
            ex = rnd.choice(["EX03", "EX02"])
        elif kind == "conv" and rnd.random() < 0.08:
            ex = "EX01"
        fixed = {
            "planned_order_id": pool[i], "converted_production_order_id": po_id,
            "manufacturing_bom_id": reg.ctx["bom_of"][s["code"]], "manufacturing_facility_id": reg.ctx["plant_id"][plant],
            "product_category_id": reg.ctx["category_id"][s["subcat"]], "routing_id": reg.ctx["routing_of"][s["code"]],
            "sku_id": reg.ctx["sku_id"][s["code"]],
            "target_distribution_facility_id": reg.ctx["dc_id"][rnd.choice(world.DCS)["code"]],
            "trade_account_id": x["trade_account_id"] if kind == "conv" else None,
            "trade_promotion_id": reg.pick("promotion.trade_promotion", rnd) if rnd.random() < 0.08 else None,
            "availability_date": min(finish + datetime.timedelta(days=1), world.EXTRACT_DATE) if kind == "open" else finish + datetime.timedelta(days=1),
            "conversion_date": conv_date, "conversion_status": conv_status,
            "created_by_user": "SVC_MRP", "created_timestamp": created,
            "demand_source_reference": "FC-%s-%s" % (s["code"], start.strftime("%Y%m")),
            "demand_source_type": ("CUSTOMER_ORDER" if (kind == "conv" and x["trade_account_id"]) else
                                   "PROMOTION" if _promo_demand(rnd) else "FORECAST"),
            "exception_message_code": ex,
            "exception_message_text": {"EX01": "Reschedule in - demand earlier than planned", "EX02": "Reschedule out - excess coverage",
                                       "EX03": "Cancel - no longer required"}.get(ex),
            "firming_date": firm, "firming_indicator": firm is not None, "gmp_compliance_flag": plant == "POZN",
            "ibp_plan_version": "IBP-%s" % start.strftime("%Y%m"),
            "last_modified_timestamp": min(world.EXTRACT_TS, created + datetime.timedelta(days=rnd.randint(1, 10))),
            "lot_size_key": "EX", "mrp_controller": PLANT_CODE_SHORT[plant] + "01", "mrp_run_code": int(created.strftime("%Y%m%d")),
            "order_number": "PL%08d" % (i + 1), "order_status": status, "order_type": "MRP",
            "planned_quantity": qty, "planning_period": "%d-M%02d" % (start.year, start.month),
            "planning_strategy_group": "10", "priority_code": "HIGH" if ex == "EX01" else "NORMAL",
            "procurement_type": "IN_HOUSE", "production_version": "0001",
            "reorder_point_quantity": _q(qty * D("0.6"), "0.001"), "safety_stock_quantity": _q(qty * D("0.25"), "0.001"),
            "schedule_version": "V%03d" % (1 + (start.month % 12)), "scheduled_finish_date": finish,
            "scheduled_start_date": start, "sop_cycle_reference": "SOP-%d-M%02d" % (start.year, start.month),
            "unit_of_measure": "EA",
            "notes": ("Rescheduled by MRP run" if ex in ("EX01", "EX02") else "Demand covered by earlier order"
                      if ex == "EX03" else None),
        }
        if fixed["last_modified_timestamp"] < created:
            fixed["last_modified_timestamp"] = created
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=world.PLANT[plant]["country"]))
    reg.rows[fq] = rows


def _promo_demand(rnd):
    """About 10 % of planned orders are driven by a trade promotion."""
    return rnd.random() < 0.1


def _batches_yields_confirmations(reg, po_rows):
    fq_b, fq_y, fq_c = "manufacturing.batch_record", "manufacturing.yield_record", "manufacturing.production_confirmation"
    started = [po for po in po_rows if po["_meta"]["progress"] > 0]
    bpool = reg.alloc(fq_b, len(started))
    ypool = reg.alloc(fq_y, len(started))
    bgen, ygen, cgen = reg.gen(fq_b), reg.gen(fq_y), reg.gen(fq_c)
    brnd, yrnd, crnd = reg.rng(fq_b), reg.rng(fq_y), reg.rng(fq_c)
    brows, yrows, cspecs = [], [], []
    for i, po in enumerate(started):
        m = po["_meta"]
        s, plant, line = m["sku"], m["plant"], m["line"]
        p = world.PLANT[plant]
        done = m["progress"] >= 1.0
        qty = po["order_quantity"]
        conf = po["confirmed_quantity"]
        scrap = po["scrap_quantity"]
        rework = D(int(int(qty) * (0.006 if not m["incident"] else 0.02)))
        mfg_date = m["a_start"].date()
        shelf = world.SHELF_LIFE_DAYS[s["subcat"]]
        if done:
            status = "released"
            if m["incident"] and brnd.random() < 0.3:
                status = "quarantine" if brnd.random() < 0.6 else "rejected"
            if po["order_status"] in ("CNF",) and brnd.random() < 0.2:
                status = "quarantine"
        else:
            status = "in_process"
        rel_ts = (m["a_finish"] + datetime.timedelta(hours=brnd.randint(12, 60))).replace(microsecond=0) if status == "released" else None
        if rel_ts and rel_ts > world.EXTRACT_TS:
            rel_ts, status = None, "quarantine"
        dev = brnd.randint(1, 3) if m["incident"] else (1 if brnd.random() < 0.04 else 0)
        last_mod = rel_ts or (m["a_finish"].replace(microsecond=0) if done else world.EXTRACT_TS - datetime.timedelta(days=10))
        bfixed = {
            "batch_record_id": bpool[i], "cost_center_id": po["cost_center_id"],
            "formulation_id": reg.ctx["formulation_id"][s["code"]],
            "goods_receipt_id": reg.pick("procurement.goods_receipt", brnd),
            "manufacturing_bom_id": po["manufacturing_bom_id"], "manufacturing_facility_id": po["manufacturing_facility_id"],
            "production_line_id": po["production_line_id"], "production_order_id": po["production_order_id"],
            "routing_id": po["routing_id"], "sku_id": po["sku_id"],
            "actual_cost_amount": _q(po["actual_cost"] / conf, "0.01") if conf else None,
            "batch_number": po["batch_number"], "batch_size_actual": conf, "batch_size_planned": qty, "batch_status": status,
            "bom_version": "1.0", "changeover_minutes": m["changeover"],
            "created_timestamp": m["a_start"] - datetime.timedelta(minutes=brnd.randint(5, 50)),
            "currency_code": po["currency_code"], "downtime_minutes": po["downtime_minutes"],
            "electronic_signature_count": 4 + dev * 2, "expiry_date": mfg_date + datetime.timedelta(days=shelf),
            "gmp_deviation_count": dev, "gmp_deviation_flag": dev > 0, "last_modified_timestamp": last_mod,
            "lot_genealogy_complete_flag": done, "manufacturing_date": mfg_date,
            "manufacturing_end_timestamp": m["a_finish"].replace(microsecond=0) if done else None,
            "manufacturing_start_timestamp": m["a_start"], "oee_percentage": po["oee_percentage"],
            "quality_release_flag": status == "released", "quality_release_timestamp": rel_ts,
            "recall_flag": False, "recall_initiated_date": None, "record_locked_flag": status == "released",
            "regulatory_hold_flag": status == "quarantine", "rework_quantity": rework if done else D(0),
            "routing_version": "1", "scrap_quantity": scrap, "shelf_life_days": shelf,
            "standard_cost_amount": _q(m["unit"], "0.01") if m["unit"] >= D("0.005") else D("0.01"),
            "unit_of_measure": "EA",
            "veeva_vault_document_reference": "VV%s%08d" % (plant, 10000000 + i),
            "yield_percentage": po["yield_percentage"],
        }
        brows.append(bgen.row(i, brnd, bfixed, anchor=m["a_start"], country=p["country"]))
        # yield record: input = order quantity, output = good quantity
        inp = qty if done else D(int(int(qty) * m["progress"]))
        out = conf
        act = _q(out / inp * 100) if inp else D(0)
        theo = D("97.10")
        var = act - theo
        impact = _q((theo - act) / 100 * inp * m["unit"])
        reason = None
        if m["incident"]:
            reason = (world.INCIDENT_REASON_CODE, world.INCIDENT_REASON_TEXT)
        elif plant == "TMPR" and var < D("-1.5"):
            reason = ("RAMPUP", "Start-up losses during Tampere plant ramp-up (enzymatic step and carton sealing)")
        elif var < D("-1.0"):
            reason = _LOSS_CODES[yrnd.randrange(len(_LOSS_CODES))]
        meas = (m["a_finish"] if done else world.EXTRACT_TS - datetime.timedelta(days=14)).replace(microsecond=0)
        yfixed = {
            "yield_record_id": ypool[i], "batch_record_id": bpool[i],
            "gl_account_id": reg.ctx["gl"][(p["company"], "4100")], "manufacturing_facility_id": po["manufacturing_facility_id"],
            "production_line_id": po["production_line_id"], "production_order_id": po["production_order_id"],
            "sku_id": po["sku_id"], "work_center_id": reg.ctx["wc_by_line"][line][0],
            "actual_yield_percentage": act,
            "comments": (reason[1] if reason else None), "cost_center_code": PLANT_CC[plant][0],
            "created_timestamp": meas + datetime.timedelta(minutes=5), "currency_code": po["currency_code"],
            "erp_document_number": "49%010d" % (i + 1), "gmp_compliance_flag": True,
            "input_quantity": inp.quantize(D("0.0001")), "last_modified_timestamp": meas + datetime.timedelta(hours=1),
            "measurement_timestamp": meas, "mes_transaction_reference": "MESY%s%08d" % (plant, i + 1),
            "operation_end_timestamp": meas, "operation_start_timestamp": m["a_start"],
            "output_quantity": out.quantize(D("0.0001")), "quality_inspection_lot_number": po["inspection_lot_number"],
            "rework_quantity": (rework if done else D(0)).quantize(D("0.0001")), "routing_operation_number": "0020",
            "scrap_quantity": scrap.quantize(D("0.0001")),
            "shift_code": "SHIFT_%d" % (1 + (m["a_start"].hour // 8) % 3), "standard_cost_per_unit": m["unit"],
            "theoretical_yield_percentage": theo, "unit_of_measure": "EA",
            "yield_loss_reason_code": reason[0] if reason else None,
            "yield_loss_reason_description": reason[1] if reason else None,
            "yield_variance_cost_impact": impact, "yield_variance_percentage": _q(var),
        }
        yrows.append(ygen.row(i, yrnd, yfixed, anchor=m["a_start"], country=p["country"]))
        # confirmations: 3 operations on the line's three work centres
        n_ops = 3 if done else max(1, int(3 * m["progress"]))
        span = (m["a_finish"] - m["a_start"]) if done else (datetime.datetime.combine(world.AS_OF_DATE, datetime.time(22)) - m["a_start"])
        for op in range(n_ops):
            cspecs.append((po, op, n_ops, done, span))
    reg.rows[fq_b] = brows
    reg.rows[fq_y] = yrows
    cspecs.sort(key=lambda c: (c[0]["actual_start_timestamp"], c[1]))
    cpool = reg.alloc(fq_c, len(cspecs))
    crows = []
    for i, (po, op, n_ops, done, span) in enumerate(cspecs):
        m = po["_meta"]
        plant, line = m["plant"], m["line"]
        frac_s = op / 3.0
        frac_e = (op + 1) / 3.0
        st = m["a_start"] + span * (frac_s if done else op / float(n_ops))
        en = m["a_start"] + span * (frac_e if done else (op + 1) / float(n_ops))
        # schedule: planned start of the order + the standard duration of the operations
        sched_s = m["p_start"] + m["std_span"] * frac_s
        sched_e = m["p_start"] + m["std_span"] * frac_e
        last = (op == n_ops - 1)
        conf = po["confirmed_quantity"]
        scrap = po["scrap_quantity"]
        op_scrap = (scrap * D("0.7") if op == 1 else scrap * D("0.15")).quantize(D("0.001"))
        op_yield = (conf + scrap - op_scrap * 0 if not last else conf).quantize(D("0.001"))
        if not last:
            op_yield = (conf + (scrap - op_scrap) / 2).quantize(D("0.001"))
        oee = m["oee"] / 100.0
        qual = max(0.80, float(conf) / max(1.0, float(conf + scrap)))
        avail = max(0.55, min(0.99, 1 - (m["downtime"] + m["changeover"]) / max(60.0, span.total_seconds() / 60.0)))
        perf = max(0.5, min(0.995, oee / (avail * qual)))
        if perf >= 0.995:
            avail = min(0.99, oee / (perf * qual))
        dur_min = D(str(round((en - st).total_seconds() / 60.0, 2)))
        dt = D(m["downtime"]) / 3
        fixed = {
            "production_confirmation_id": cpool[i], "batch_record_id": None,
            "cost_center_id": po["cost_center_id"], "gl_account_id": reg.ctx["gl"][(world.PLANT[plant]["company"], "1420")],
            "manufacturing_facility_id": po["manufacturing_facility_id"], "production_order_id": po["production_order_id"],
            "routing_id": po["routing_id"], "sales_order_id": po["sales_order_id"], "sku_id": po["sku_id"],
            "work_center_id": reg.ctx["wc_by_line"][line][op],
            "activity_type": ["SETUP", "MACH", "LABOR"][op], "actual_end_datetime": en.replace(microsecond=0),
            "actual_labor_time_minutes": _q(dur_min * D("1.3")), "actual_machine_time_minutes": _q(dur_min - dt) if dur_min > dt else dur_min,
            "actual_setup_time_minutes": D(m["changeover"]) if op == 0 else D("0.00"),
            "actual_start_datetime": st.replace(microsecond=0),
            "confirmation_notes": po["notes"] if (m["incident"] and op == 1) else None,
            "confirmation_timestamp": (en + datetime.timedelta(minutes=crnd.randint(2, 45))).replace(microsecond=0),
            "confirmation_type": "final" if (last and done) else "partial",
            "confirmed_scrap_quantity": op_scrap, "confirmed_yield_quantity": op_yield,
            "downtime_minutes": _q(dt), "gmp_compliance_flag": True,
            "last_modified_timestamp": (en + datetime.timedelta(hours=1)).replace(microsecond=0),
            "mes_transaction_reference": "MES%s%010d" % (plant, i + 1),
            "oee_availability_percent": _q(D(str(avail * 100))), "oee_performance_percent": _q(D(str(perf * 100))),
            "oee_quality_percent": _q(D(str(qual * 100))), "operation_number": "%04d" % ((op + 1) * 10),
            "operation_status": "completed" if (done or not last) else "in_progress", "posting_date": en.date(),
            "quality_inspection_required_flag": op == 2, "reversal_flag": False, "reversal_reason_code": None,
            "rework_flag": False, "scheduled_end_datetime": sched_e.replace(microsecond=0),
            "scheduled_start_datetime": sched_s.replace(microsecond=0),
            "shift_code": "SHIFT_%d" % (1 + (st.hour // 8) % 3), "source_system_code": "OPCENTER_MES",
            "unit_of_measure": "EA", "variance_reason_code": "EQMALF" if m["incident"] else None,
            "work_order_number": "WO%010d" % (int(po["order_number"]) * 10 + op),
        }
        crows.append(cgen.row(i, crnd, fixed, anchor=st, country=world.PLANT[plant]["country"]))
    # link confirmations to batch records
    batch_of = dict((b["production_order_id"], b["batch_record_id"]) for b in brows)
    for c in crows:
        c["batch_record_id"] = batch_of.get(c["production_order_id"])
    reg.rows[fq_c] = crows


# loaded annual cost of one plant employee (EUR) - used to size the workforce from the plant labour cost
_COST_PER_FTE_EUR = {"SWE": 62000.0, "FIN": 58000.0, "POL": 24000.0}


def size_facilities(reg):
    """Workforce and capacity of each plant follow its production volume (after ``production``).

    ``workforce_headcount`` = plant labour cost of the last 12 months (labour + fixed-overhead share of
    the actual production cost, as settled in finance) / loaded cost per employee;
    ``production_capacity_units_per_day`` = sum of the lines' design speeds x shift hours per day.
    """
    from .curated_finance import cost_shares, production_cost_by_month
    prod = production_cost_by_month(reg)
    lo = (world.TXN_END.year - 1, world.TXN_END.month + 1)
    for row in reg.rows["manufacturing.manufacturing_facility"]:
        plant = row["plant_code"]
        p = world.PLANT[plant]
        labour = sum((a[1] for (pl, y, m), a in prod.items() if pl == plant and (y, m) >= lo), D(0))
        eur = float(labour * cost_shares(plant)[1]) * world.FX_BASE[_CUR[plant]]
        row["workforce_headcount"] = max(6, int(round(eur / _COST_PER_FTE_EUR[p["country"]])))
        hours = world.SHIFT_HOURS_PER_DAY
        row["production_capacity_units_per_day"] = D(str(int(sum(ln[5] for ln in world.LINES if ln[1] == plant) * hours)))
        p["headcount"] = row["workforce_headcount"]
