"""Curated consumer domain: the Fjällmark webshop (fjallmark.example) and the
"Fjällmark Friends" loyalty programme.

Story hooks
-----------
S1  DTC order amounts are *gross* (``order_total_amount`` = subtotal - discount +
    shipping + VAT, in the market's local currency). Finance books net revenue in EUR,
    excluding VAT and shipping and after returns (see curated_finance).
S2  ``currency_code`` differs by market (SEK, NOK, DKK, EUR) - summing amounts across
    markets mixes currencies.
S5  Gold/Platinum members order ~3x as often and spend ~2.3x more per order than
    non-members; ``cltv_segment = 'at_risk'`` shoppers have no order in the last 180 days.
S7  ``shopper`` / ``address`` carry PII (names, e-mail, phone, birth date, postal code).

Arithmetic invariants (exact at 4 decimals)
-------------------------------------------
line_subtotal = quantity_ordered * unit_price;  line_discount_amount = line_subtotal *
line_discount_pct / 100;  line_net_amount = subtotal - discount;  tax_amount = line_net *
VAT;  line_total_amount = net + tax.  Order header: subtotal / discount / tax = sum over
lines; order_total_amount = subtotal - discount + shipping + tax (shipping is a flat,
VAT-inclusive fee). unit_price is the shelf price excluding VAT.
"""
import datetime
import heapq
import math
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP

from . import engine, world
from .curated_finance import BRAND_PC

D = Decimal
Q4 = D("0.0001")
Q2 = D("0.01")

N_SHOPPERS = 3000
N_HOUSEHOLDS = 1800
N_ORDERS = 8000
N_SUBSCRIPTIONS = 520
MEMBER_SHARE = 0.63
# monthly order propensity by segment (relative)
LAMBDA = {None: 1.0, "Bronze": 1.25, "Silver": 1.7, "Gold": 3.25, "Platinum": 3.45}
# mean number of lines per regular order by segment
LINES_MEAN = {None: 1.45, "Bronze": 1.75, "Silver": 2.1, "Gold": 3.4, "Platinum": 3.6}
QTY_BOOST = {None: 1.0, "Bronze": 1.08, "Silver": 1.15, "Gold": 1.50, "Platinum": 1.60}
ADDON_P = {None: 0.10, "Bronze": 0.15, "Silver": 0.25, "Gold": 0.45, "Platinum": 0.50}
CHURN_P = {None: 0.30, "Bronze": 0.27, "Silver": 0.20, "Gold": 0.10, "Platinum": 0.08}

CHANNELS = [("brand_website", 0.55), ("mobile_app", 0.36), ("social_commerce", 0.07), ("voice_commerce", 0.02)]
LINE_CHANNEL = {"brand_website": "DTC_WEB", "mobile_app": "DTC_APP", "social_commerce": "DTC_SOCIAL",
                "voice_commerce": "DTC_WEB", "dtc_subscription": "DTC_SUBSCRIPTION"}
RETURN_REASONS = ["DAMAGED_IN_TRANSIT", "WRONG_ITEM", "NOT_AS_DESCRIBED", "CHANGED_MIND", "QUALITY_ISSUE",
                  "LATE_DELIVERY", "LEAKING_PACKAGING"]
# subscription boxes: one box SKU per plan, 4-10 consumer units (or 2-3 crates/trays) per delivery,
# i.e. about 25-40 EUR per delivery incl. VAT after the 10 % subscription discount
SUB_PLANS = [  # (sku code, plan name, type, quantity choices, earliest start)
    ("BP-GRAN-LING-450", "Björkö Granola Box", "subscription_box", (5, 6, 7), None),
    ("BP-GRAN-HONEY-450", "Björkö Granola Box", "subscription_box", (5, 6, 7), None),
    ("BP-OATS-JUMBO-1KG", "Björkö Oat Refill", "auto_replenishment", (8, 10), None),
    ("KK-OAT-ORIG-6X1L", "Kallkälla Oat Drink Crate", "auto_replenishment", (2, 3), datetime.date(2025, 4, 22)),
    ("KK-OAT-BARI-6X1L", "Kallkälla Oat Drink Crate", "auto_replenishment", (2, 3), datetime.date(2025, 4, 22)),
    ("KK-SPK-LEM-24X033", "Kallkälla Sparkling Subscription", "auto_replenishment", (1, 2, 2), None),
    ("MC-SHP-REFILL-750", "Mjuk Care Refill", "auto_replenishment", (4, 5), None),
    ("MC-BW-REFILL-750", "Mjuk Care Refill", "auto_replenishment", (4, 5), None),
    ("MC-HS-REFILL-750", "Mjuk Care Refill", "auto_replenishment", (4, 5), None),
]
SUB_FIRST_START = datetime.date(2020, 1, 1)   # subscriptions sold since 2020, new sales grow 18 % a year
SUB_MEAN_LIFETIME_MONTHS = 13.0
SUB_TIER_WEIGHT = {None: 0.4, "Bronze": 0.8, "Silver": 1.4, "Gold": 2.2, "Platinum": 2.6}
# loyalty economics (100 points = 1 EUR)
BONUS_POINTS = {"account_registration": 100, "birthday_bonus": 50, "referral": 200, "product_review": 25}
REDEEM_MIN_BALANCE = 200
REDEEM_P = 0.20
REDEEM_MAX_SHARE = D("0.30")      # points may pay at most 30 % of the merchandise value
FREQ_DAYS = {"weekly": 7, "bi_weekly": 14, "monthly": 30, "bi_monthly": 61, "quarterly": 91}


def q4(x):
    return x.quantize(Q4, rounding=ROUND_HALF_UP)


def q2(x):
    return x.quantize(Q2, rounding=ROUND_HALF_UP)


def _ts(d, h=9, m=0, s=0):
    return datetime.datetime.combine(d, datetime.time(h, m, s))


def _d(x):
    return x.date() if isinstance(x, datetime.datetime) else x


def std_cost_factor(year):
    return {2024: D("1.00"), 2025: D("1.03"), 2026: D("1.05")}.get(year, D("1.00"))


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------

def generate(reg):
    rnd = reg.rng("consumer", "plan")
    _loyalty_program(reg)
    _loyalty_tiers(reg)
    people = _plan_shoppers(reg, rnd)
    households = _plan_households(reg, people, rnd)
    _addresses(reg, people, households, rnd)
    _consents(reg, people, rnd)
    subs = _plan_subscriptions(reg, people, rnd)
    planned = _plan_orders(reg, people, subs, rnd)
    members = _plan_accounts(reg, people)
    ledger = Ledger(reg.rng("consumer.loyalty_transaction", "ledger"))
    ledger.schedule_bonuses(members, planned)
    _write_orders(reg, people, planned, ledger)
    ledger.finish(members)
    orders = reg.rows["consumer.dtc_order"]
    _requalify_tiers(reg, members, ledger)
    _segment_shoppers(reg, people)
    _loyalty_transactions(reg, ledger)
    _loyalty_accounts(reg, members, ledger)
    _subscriptions(reg, people, subs, orders)
    _finalise_shoppers(reg, people, orders)
    _households(reg, people, households)
    _preferences(reg, people, households, rnd)
    _finalise_program(reg)


# --------------------------------------------------------------------------------------
# loyalty programme and tiers
# --------------------------------------------------------------------------------------

def _loyalty_program(reg):
    fqn = "consumer.loyalty_program"
    pool = reg.alloc(fqn, 1)
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    p = world.LOYALTY_PROGRAM
    fixed = {
        "loyalty_program_id": pool[0], "brand_id": None, "company_code_id": reg.ctx["company_id"]["SE01"],
        "predecessor_loyalty_program_id": None, "cltv_estimate": D("412.50"), "consent_status": "granted",
        "currency_code": "EUR", "effective_from": p["launched"], "effective_until": None,
        "enrollment_channel": "web", "enrollment_date": p["launched"], "loyalty_program_status": "active",
        "nps_score": 47, "points_expiration_date": None, "privacy_opt_in": True, "program_code": p["code"],
        "program_description": ("Fjällmark Friends is the group-wide loyalty programme of the webshop %s. "
                                "Members earn 1 point per EUR of net merchandise value (x tier multiplier), "
                                "100 points = 1 EUR. Tiers: Bronze, Silver, Gold, Platinum." % world.WEBSHOP),
        "program_name": p["name"], "program_type": "points",
        "record_audit_created": _ts(p["launched"] - datetime.timedelta(days=40)),
        "record_audit_updated": _ts(datetime.date(2026, 1, 8), 10), "reward_rate": D("1.00"),
        "tier_level": "Bronze, Silver, Gold, Platinum",
    }
    reg.rows[fqn] = [gen.row(0, rnd, fixed, anchor=fixed["record_audit_created"], country="SWE")]
    reg.ctx["program_id"] = pool[0]


def _loyalty_tiers(reg):
    fqn = "consumer.loyalty_tier"
    pool = reg.alloc(fqn, len(world.TIERS))
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    ids = dict((t["name"], pool[i]) for i, t in enumerate(world.TIERS))
    rows = []
    benefits = {
        "Bronze": "1 point per EUR, birthday bonus, member newsletter",
        "Silver": "1.25 points per EUR, 2 percent member discount, early access to seasonal ranges",
        "Gold": "1.5 points per EUR, 5 percent member discount, free shipping, exclusive offers",
        "Platinum": "2 points per EUR, 8 percent member discount, free shipping, priority support, gift at Christmas",
    }
    for i, t in enumerate(world.TIERS):
        nxt = world.TIERS[i + 1]["name"] if i + 1 < len(world.TIERS) else None
        created = _ts(world.LOYALTY_PROGRAM["launched"] - datetime.timedelta(days=30))
        fixed = {
            "loyalty_tier_id": pool[i], "loyalty_program_id": reg.ctx["program_id"],
            "next_loyalty_tier_id": ids[nxt] if nxt else None, "benefits_description": benefits[t["name"]],
            "created_timestamp": created, "discount_percent": t["discount_pct"],
            "effective_from": world.LOYALTY_PROGRAM["launched"], "effective_until": None,
            "eligibility_criteria": ("Default tier on enrolment" if t["rank"] == 1 else
                                     "Keep the tier with %d lifetime points or %s EUR qualifying spend (excl. VAT) "
                                     "in the last 12 months" % (t["required_points"], t["required_spend"])),
            "exclusive_offers": t["rank"] >= 3, "expiration_policy": "Reviewed every 12 months; one tier down if not re-qualified",
            "free_shipping": t["free_shipping"], "is_default": t["rank"] == 1, "loyalty_tier_status": "active",
            "max_points_per_year": 50000 * t["rank"], "points_multiplier": t["multiplier"],
            "priority_support": t["rank"] == 4, "promotional_code": "FRIENDS" + t["code"][:4],
            "required_points": t["required_points"], "required_spend_usd": t["required_spend"],
            "reward_points_per_dollar": t["multiplier"], "spend_multiplier": t["multiplier"],
            "tier_code": t["code"], "tier_name": t["name"], "tier_rank": t["rank"],
            "tier_type": "points_based", "updated_timestamp": _ts(datetime.date(2025, 11, 3), 9),
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country="SWE"))
    reg.ctx["tier_id"] = ids
    reg.rows[fqn] = rows


# --------------------------------------------------------------------------------------
# shoppers (plan first; rows are finalised after orders exist)
# --------------------------------------------------------------------------------------

class Person(object):
    __slots__ = ("idx", "id", "market", "country", "first", "last", "gender", "birth", "acq", "member",
                 "tier", "enrolled", "churn", "email", "phone", "household", "address_id", "addresses",
                 "fav_brand", "fav_subcat", "fav_sku", "consent_marketing_id", "consents", "account_id",
                 "orders", "nps", "channel", "lifecycle", "segment", "last_purchase", "balance", "referred_by",
                 "acq_channel", "opt_in_email", "opt_in_sms", "opt_in_push", "data_sharing", "tier_before")


def _weighted(rnd, pairs):
    total = sum(w for _, w in pairs)
    x = rnd.random() * total
    acc = 0.0
    for v, w in pairs:
        acc += w
        if x <= acc:
            return v
    return pairs[-1][0]


def _plan_shoppers(reg, rnd):
    pool = reg.alloc("consumer.shopper", N_SHOPPERS)
    markets = [(m["country"], m["share"]) for m in world.MARKETS]
    tiers = [(t["name"], t["share"]) for t in world.TIERS]
    people = []
    window_days = (datetime.date(2026, 8, 31) - world.TXN_START).days
    for i in range(N_SHOPPERS):
        p = Person()
        p.idx = i
        p.id = pool[i]
        p.country = _weighted(rnd, markets)
        p.market = world.MARKET[p.country]
        p.gender = _weighted(rnd, [("female", 0.54), ("male", 0.42), ("non_binary", 0.015),
                                   ("prefer_not_to_say", 0.02), ("other", 0.005)])
        # given name from the pool matching the gender; non-binary / undisclosed: any name
        names = {"female": world.FIRST_NAMES_F, "male": world.FIRST_NAMES_M}.get(p.gender, world.FIRST_NAMES)
        p.first = rnd.choice(names[p.country])
        p.last = rnd.choice(world.LAST_NAMES[p.country])
        p.birth = datetime.date(1946, 1, 1) + datetime.timedelta(days=rnd.randint(0, 21000))
        if p.birth > datetime.date(2006, 9, 1):
            p.birth -= datetime.timedelta(days=3650)
        # acquisition: 35 % before the transaction window, then growing intake
        if rnd.random() < 0.35:
            p.acq = datetime.date(2019, 3, 1) + datetime.timedelta(days=rnd.randint(0, 1765))
        else:
            # growth-weighted: later dates more likely
            x = rnd.random() ** 0.85
            p.acq = world.TXN_START + datetime.timedelta(days=int(window_days * x))
        if (p.acq - p.birth).days < 16 * 366:
            # shoppers are at least 16 years old when they register (GDPR consent age)
            p.birth = datetime.date(p.acq.year - 17, p.birth.month, min(p.birth.day, 28))
        p.member = rnd.random() < (MEMBER_SHARE + (0.08 if p.acq < world.TXN_START else -0.04))
        p.tier = _weighted(rnd, tiers) if p.member else None
        if p.member:
            delay = 0 if rnd.random() < 0.55 else rnd.randint(1, 400)
            p.enrolled = max(p.acq + datetime.timedelta(days=delay), world.LOYALTY_PROGRAM["launched"])
            if p.enrolled > datetime.date(2026, 9, 25):
                p.enrolled = p.acq
        else:
            p.enrolled = None
        p.churn = None
        if rnd.random() < CHURN_P[p.tier]:
            lo = max(p.acq + datetime.timedelta(days=60), datetime.date(2023, 3, 1))
            if lo < datetime.date(2026, 9, 1):
                p.churn = lo + datetime.timedelta(days=rnd.randint(0, (datetime.date(2026, 9, 30) - lo).days))
        p.email = engine.email_for(p.first, p.last, rnd, 1000 + i)
        p.phone = engine.phone(p.country, rnd, e164=True)
        p.fav_brand = _weighted(rnd, [("BJORKO", 0.40), ("KALLKALLA", 0.33), ("MJUKCARE", 0.27)])
        cands = [s for s in world.SKUS if s["brand"] == p.fav_brand and s["season"] is None]
        fav = rnd.choice(cands)
        p.fav_sku = fav["code"]
        p.fav_subcat = fav["subcat"]
        p.orders = []
        p.addresses = []
        p.consents = []
        p.nps = max(0, min(10, int(round(rnd.gauss(8.2 if p.tier in ("Gold", "Platinum") else 7.0, 1.8)))))
        p.channel = _weighted(rnd, CHANNELS)
        p.acq_channel = _weighted(rnd, [("organic_search", 0.30), ("paid_social", 0.22), ("referral", 0.12),
                                        ("newsletter", 0.10), ("influencer", 0.08), ("retail_qr_code", 0.10),
                                        ("marketplace", 0.08)])
        p.opt_in_email = rnd.random() < (0.85 if p.member else 0.55)
        p.opt_in_sms = rnd.random() < (0.45 if p.member else 0.2)
        p.opt_in_push = p.channel == "mobile_app" and rnd.random() < 0.7
        p.data_sharing = rnd.random() < 0.18
        p.household = None
        p.account_id = None
        p.referred_by = None
        p.balance = D(0)
        p.tier_before = None
        people.append(p)
    reg.ctx["people"] = people
    return people


def _plan_households(reg, people, rnd):
    """1 800 households: 1 200 single-shopper and 600 two-shopper households."""
    pool = reg.alloc("consumer.household", N_HOUSEHOLDS)
    order = list(range(len(people)))
    rnd.shuffle(order)
    households = []
    k = 0
    by_country = {}
    for i in order:
        by_country.setdefault(people[i].country, []).append(i)
    pairs_needed = 600
    singles_needed = N_HOUSEHOLDS - pairs_needed
    for country in sorted(by_country):
        idxs = by_country[country]
        share = len(idxs) / float(len(people))
        n_pairs = int(round(pairs_needed * share))
        j = 0
        for _ in range(n_pairs):
            if j + 1 >= len(idxs):
                break
            households.append([idxs[j], idxs[j + 1]])
            j += 2
        rest = idxs[j:]
        n_single = int(round(singles_needed * share))
        for x in rest[:n_single]:
            households.append([x])
    households = households[:N_HOUSEHOLDS]
    while len(households) < N_HOUSEHOLDS:
        # top up with singles from shoppers without household
        used = set(i for h in households for i in h)
        for i in range(len(people)):
            if i not in used:
                households.append([i])
                break
    out = []
    for h_i, members in enumerate(households):
        hid = pool[h_i]
        members = sorted(members, key=lambda i: people[i].acq)
        for i in members:
            people[i].household = hid
        out.append({"id": hid, "members": members})
    return out


def _addresses(reg, people, households, rnd):
    fqn = "consumer.address"
    gen = reg.gen(fqn)
    arnd = reg.rng(fqn)
    specs = []
    # shared street address per household
    street_of = {}
    for h in households:
        p0 = people[h["members"][0]]
        city = rnd.choice(world.CITIES[p0.country])
        street_of[h["id"]] = (engine.street_address(p0.country, rnd), city, engine.postal_code(city[4], rnd))
    for p in people:
        if p.household is not None:
            line1, city, postal = street_of[p.household]
        else:
            city = rnd.choice(world.CITIES[p.country])
            line1, postal = engine.street_address(p.country, rnd), engine.postal_code(city[4], rnd)
        specs.append((p, "shipping", True, line1, city, postal, p.acq))
    extra = 3150 - len(specs)
    for k in range(extra):
        p = people[rnd.randrange(len(people))]
        kind = _weighted(rnd, [("billing", 0.35), ("work", 0.30), ("home", 0.2), ("preferred", 0.15)])
        city = rnd.choice(world.CITIES[p.country])
        when = p.acq + datetime.timedelta(days=rnd.randint(0, max(1, (datetime.date(2026, 9, 1) - p.acq).days)))
        specs.append((p, kind, False, engine.street_address(p.country, rnd), city,
                      engine.postal_code(city[4], rnd), when))
    pool = reg.alloc(fqn, len(specs))
    rows = []
    for i, (p, kind, primary, line1, city, postal, when) in enumerate(specs):
        aid = pool[i]
        p.addresses.append(aid)
        if primary:
            p.address_id = aid
        created = _ts(when, arnd.randint(7, 22), arnd.randint(0, 59))
        status = "active" if primary or arnd.random() < 0.8 else "inactive"
        lat = D(str(city[2] + arnd.uniform(-0.05, 0.05))).quantize(D("0.0000001"))
        lon = D(str(city[3] + arnd.uniform(-0.08, 0.08))).quantize(D("0.0000001"))
        fixed = {
            "address_id": aid, "household_id": p.household if kind in ("shipping", "home") else None,
            "shopper_id": p.id, "address_status": status, "address_type": kind, "carrier_route": None,
            "census_tract": None, "city": city[0], "consent_captured": True, "consent_date": _d(created),
            "country_code": p.country, "created_timestamp": created, "data_residency_region": "EU",
            "deliverability_score": D(str(round(arnd.uniform(86, 99.8), 2))), "dma_code": None,
            "do_not_mail": arnd.random() < 0.12, "dpv_confirmation": None,
            "effective_date": _d(created), "expiry_date": None if status == "active" else
            min(world.EXTRACT_DATE, _d(created) + datetime.timedelta(days=arnd.randint(90, 700))),
            "format_type": "domestic", "geocoding_accuracy": _weighted(arnd, [("rooftop", 0.7), ("range_interpolated", 0.2), ("geometric_center", 0.1)]),
            "is_default_billing": primary, "is_default_shipping": primary, "is_primary": primary,
            "latitude": lat, "line_1": line1, "line_2": None if arnd.random() < 0.75 else "lgh %d" % arnd.randint(1001, 1504),
            "line_3": None, "longitude": lon, "plus4_code": None, "postal_code": postal,
            "residential_indicator": "commercial" if kind == "work" else "residential",
            "sales_territory_code": p.country + "-DTC", "source": "webshop_checkout" if primary else "account_settings",
            "source_system_code": "SFCC-ADR-%07d" % (i + 1), "source_system_name": "dtc_platform",
            "standardized_address": "%s, %s %s, %s" % (line1, postal, city[0], world.COUNTRY_NAMES[p.country]),
            "state_province": city[1], "timezone": world.COUNTRY_TZ[p.country],
            "validation_provider": "Nordic Address Check (fictional)", "validation_status": "validated" if arnd.random() < 0.9 else "corrected",
        }
        if fixed["expiry_date"] is not None and fixed["expiry_date"] < fixed["effective_date"]:
            fixed["expiry_date"] = fixed["effective_date"]
        rows.append(gen.row(i, arnd, fixed, anchor=created, country=p.country))
    reg.rows[fqn] = rows


def _consents(reg, people, rnd):
    fqn = "consumer.consent_record"
    gen = reg.gen(fqn)
    crnd = reg.rng(fqn)
    specs = []
    for p in people:
        types = ["marketing_email"]
        if p.opt_in_sms:
            types.append("sms")
        if p.opt_in_push:
            types.append("push_notification")
        if crnd.random() < 0.08:
            types.append("cookies")
        if p.member and crnd.random() < 0.15:
            types.append("profiling")
        if p.data_sharing:
            types.append("data_sharing")
        for t in types:
            granted = {"marketing_email": p.opt_in_email, "sms": p.opt_in_sms,
                       "push_notification": p.opt_in_push, "data_sharing": p.data_sharing}.get(t, True)
            changed = (not granted and crnd.random() < 0.35) or crnd.random() < 0.04
            if not granted and not changed:
                # never confirmed (double opt-in not completed)
                specs.append((p, t, "pending", p.acq + datetime.timedelta(days=crnd.randint(0, 3)), 1, True, "none"))
            elif changed:
                # history: an earlier grant, then the current state
                first = p.acq
                second = first + datetime.timedelta(days=crnd.randint(30, 600))
                if second > datetime.date(2026, 10, 10):
                    second = datetime.date(2026, 10, 10)
                specs.append((p, t, "granted" if granted else "withdrawn", second, 2, True, "granted"))
                specs.append((p, t, "granted", first, 1, False, "none"))
            else:  # current grant without history
                specs.append((p, t, "granted", p.acq, 1, True, "none"))
    specs.sort(key=lambda s: (s[3], s[0].idx, s[1], s[4]))
    pool = reg.alloc(fqn, len(specs))
    rows = []
    for i, (p, ctype, status, day, version, current, prior) in enumerate(specs):
        cid = pool[i]
        cap = _ts(day, crnd.randint(8, 22), crnd.randint(0, 59), crnd.randint(0, 59))
        if ctype == "marketing_email" and current:
            p.consent_marketing_id = cid
        p.consents.append(cid)
        withdrawn = status == "withdrawn"
        fixed = {
            "consent_record_id": cid, "brand_id": None, "loyalty_program_id": reg.ctx["program_id"] if p.member else None,
            "shopper_id": p.id, "capture_method": "mobile_app" if p.channel == "mobile_app" else "web_form",
            "capture_timestamp": cap, "change_trigger": "consumer_action",
            "consent_language_code": p.market["lang"], "consent_proof_reference": "CP%08d" % (i + 1),
            "consent_scope": "global", "consent_status": status,
            "consent_text_snapshot": "notice-%s-%s" % ("3.1" if day >= datetime.date(2024, 5, 1) else "2.4", p.market["lang"][:2]),
            "consent_type": ctype, "consent_version": "3.1" if day >= datetime.date(2024, 5, 1) else "2.4",
            "cookie_consent_categories": "functional,analytics" + (",marketing" if crnd.random() < 0.5 else "")
            if ctype == "cookies" else None,
            "country_code": p.country, "created_timestamp": cap + datetime.timedelta(seconds=crnd.randint(5, 600)),
            "device_type": "mobile" if p.channel == "mobile_app" else _weighted(crnd, [("desktop", 0.55), ("mobile", 0.35), ("tablet", 0.1)]),
            "double_opt_in_flag": ctype == "marketing_email" and status == "granted",
            "double_opt_in_timestamp": cap + datetime.timedelta(minutes=crnd.randint(1, 240))
            if ctype == "marketing_email" and status == "granted" else None,
            "effective_from": _d(cap), "expiry_date": None,
            "ip_address": ("%s%d" % (crnd.choice(["192.0.2.", "198.51.100.", "203.0.113."]), crnd.randint(1, 254))
                           if crnd.random() < 0.7 else None),
            "is_current_record": current, "legal_basis": "consent", "minor_age_threshold": 16,
            "parental_consent_flag": False, "prior_consent_status": prior if version > 1 else "none",
            "processing_agent": "SFCC_CONSENT_SVC", "profiling_consent_flag": ctype == "profiling" and not withdrawn,
            "re_consent_deadline": (datetime.date(2026, 12, 31) if (current and status == "granted" and
                                                                    day < datetime.date(2024, 5, 1) and ctype == "marketing_email") else None),
            "re_consent_required_flag": bool(current and status == "granted" and day < datetime.date(2024, 5, 1)
                                             and ctype == "marketing_email"),
            "record_version": version,
            "regulatory_jurisdiction": "GDPR", "retention_period_days": 1095,
            "third_party_sharing_flag": ctype == "data_sharing" and not withdrawn,
            "updated_timestamp": cap + datetime.timedelta(minutes=crnd.randint(11, 40)),
            "withdrawal_method": ("email_link" if crnd.random() < 0.6 else "web_form") if withdrawn else None,
            "withdrawal_timestamp": cap if withdrawn else None,
        }
        rows.append(gen.row(i, crnd, fixed, anchor=cap, country=p.country))
    # every shopper has a marketing consent id (current marketing_email record)
    reg.rows[fqn] = rows


# --------------------------------------------------------------------------------------
# subscriptions and orders (plan)
# --------------------------------------------------------------------------------------

def _plan_subscriptions(reg, people, rnd):
    """Subscriptions sold since 2022 (new sales +18 % a year), each running for an exponentially
    distributed lifetime (mean ~13 months) - the active base therefore grows steadily instead of
    piling up, and the subscription share of webshop orders stays around a third."""
    pool = reg.alloc("consumer.subscription", N_SUBSCRIPTIONS)
    sale_months = world.months(SUB_FIRST_START, datetime.date(2026, 8, 31))
    month_w = [1.16 ** (k / 12.0) for k in range(len(sale_months))]
    # deterministic number of new subscriptions per month (cumulative rounding of the growth curve)
    start_months, cum, done = [], 0.0, 0
    for ym, w in zip(sale_months, month_w):
        cum += N_SUBSCRIPTIONS * w / sum(month_w)
        n = int(round(cum)) - done
        start_months += [ym] * n
        done += n
    brand_prefix = {"BJORKO": "BP", "KALLKALLA": "KK", "MJUKCARE": "MC"}
    subs = []
    used = set()
    for k, ym in enumerate(start_months[:N_SUBSCRIPTIONS]):
        ms = world.month_start(*ym)
        me = min(world.month_end(*ym), datetime.date(2026, 8, 31))
        start = ms + datetime.timedelta(days=rnd.randint(0, (me - ms).days))
        cands = [p for p in people if p.acq <= start and p.idx not in used
                 and (p.churn is None or p.churn > start + datetime.timedelta(days=45))]
        if not cands:
            cands = [p for p in people if p.acq <= start] or people
        p = rnd.choices(cands, weights=[SUB_TIER_WEIGHT[c.tier] for c in cands])[0]
        used.add(p.idx)
        start = max(start, p.acq)
        plans = [sp for sp in SUB_PLANS if sp[0].split("-")[0] == brand_prefix[p.fav_brand]
                 and (sp[4] is None or sp[4] <= start)] or [sp for sp in SUB_PLANS if sp[4] is None]
        plan = rnd.choice(plans)
        sku = world.SKU[plan[0]]
        freq = _weighted(rnd, [("monthly", 0.55), ("bi_monthly", 0.27), ("quarterly", 0.13), ("bi_weekly", 0.05)])
        # exponential lifetime from a low-discrepancy sequence (well spread, no clustering by chance)
        u = (k * 0.6180339887498949 + 0.31) % 1.0
        life_days = int(-math.log(1.0 - u) * SUB_MEAN_LIFETIME_MONTHS * 30.4) + FREQ_DAYS[freq]
        end = start + datetime.timedelta(days=life_days)
        if end > world.TXN_END:
            end = None
            status = "paused" if rnd.random() < 0.08 else "active"
        else:
            status = "cancelled" if rnd.random() < 0.86 else "expired"
        if p.churn and (end is None or end > p.churn):
            end = min(max(start + datetime.timedelta(days=FREQ_DAYS[freq]), p.churn), world.TXN_END)
            status = "cancelled"
        pause = None
        if status == "paused":
            # paused at the extract date (open-ended pause that started in summer 2026)
            lo = max(start + datetime.timedelta(days=FREQ_DAYS[freq]), datetime.date(2026, 6, 1))
            if lo < datetime.date(2026, 9, 20):
                pause = (lo + datetime.timedelta(days=rnd.randint(0, (datetime.date(2026, 9, 20) - lo).days)),
                         world.EXTRACT_DATE)
            else:
                status = "active"
        elif status == "active" and rnd.random() < 0.06:
            # an earlier holiday pause
            ps = max(start, world.TXN_START) + datetime.timedelta(days=rnd.randint(30, 400))
            if ps < datetime.date(2026, 6, 1):
                pause = (ps, ps + datetime.timedelta(days=rnd.randint(30, 75)))
        qty = rnd.choice(plan[3])
        subs.append({"id": pool[k], "person": p, "sku": sku, "plan": plan, "start": start, "freq": freq,
                     "status": status, "end": end, "pause": pause, "qty": qty, "orders": []})
    subs.sort(key=lambda s: s["id"])
    return subs


def _month_of(d):
    return (d.year, d.month)


def _plan_orders(reg, people, subs, rnd):
    """Return the list of planned orders (dicts) in chronological order."""
    orders = []
    # 1. subscription orders on schedule
    for s in subs:
        day = s["start"]
        step = FREQ_DAYS[s["freq"]]
        while day <= world.TXN_END:
            if s["end"] and day > s["end"]:
                break
            if s["pause"] and s["pause"][0] <= day <= s["pause"][1]:
                day += datetime.timedelta(days=step)
                continue
            if day >= world.TXN_START:
                orders.append({"person": s["person"], "day": day, "kind": "subscription", "sub": s})
            day += datetime.timedelta(days=step)
    # 2. welcome orders (acquisition inside the window = first order)
    for p in people:
        if world.TXN_START <= p.acq <= world.TXN_END:
            orders.append({"person": p, "day": p.acq, "kind": "welcome", "sub": None})
    # 3. regular orders to reach the monthly targets (seasonality x growth)
    mw = [(ym, world.order_season(ym[1]) * world.dtc_growth(*ym)) for ym in world.MONTHS]
    total_w = sum(w for _, w in mw)
    fixed_per_month = {}
    for o in orders:
        ym = _month_of(o["day"])
        fixed_per_month[ym] = fixed_per_month.get(ym, 0) + 1
    for ym, w in mw:
        target = int(round(N_ORDERS * w / total_w))
        n = max(0, target - fixed_per_month.get(ym, 0))
        ms, me = world.month_start(*ym), world.month_end(*ym)
        active = [p for p in people if p.acq <= me and (p.churn is None or p.churn >= ms)]
        if not active or n == 0:
            continue
        cum = []
        acc = 0.0
        for p in active:
            acc += LAMBDA[p.tier]
            cum.append(acc)
        for _ in range(n):
            p = rnd.choices(active, cum_weights=cum)[0]
            lo = max(ms, p.acq)
            hi = me if p.churn is None else min(me, p.churn)
            if hi < lo:
                hi = lo
            day = lo + datetime.timedelta(days=rnd.randint(0, (hi - lo).days))
            orders.append({"person": p, "day": day, "kind": "regular", "sub": None})
    orders.sort(key=lambda o: (o["day"], o["person"].idx, o["kind"]))
    return orders


# --------------------------------------------------------------------------------------
# orders and lines (rows)
# --------------------------------------------------------------------------------------

_PROMOS = {1: "NEWYEAR10", 2: "WINTER10", 3: "SPRING15", 4: "EASTER15", 5: "SPRING15", 6: "SUMMER15",
           7: "SUMMER15", 8: "SUMMER10", 9: "AUTUMN10", 10: "AUTUMN10", 11: "BLACKWEEK20", 12: "XMAS20"}


def _pick_skus(p, day, n, rnd):
    avail = [s for s in world.SKUS if world.sku_available(s, day)]
    weights = []
    for s in avail:
        w = world.category_season(s["category"], day.month, s["season"])
        if s["brand"] == p.fav_brand:
            w *= 2.2
        if s["code"] == p.fav_sku:
            w *= 4.0
        if s["code"].endswith("24X033"):
            w *= 0.15
        weights.append(w)
    chosen = []
    for _ in range(n * 3):
        s = rnd.choices(avail, weights=weights)[0]
        if s["code"] not in [c["code"] for c in chosen]:
            chosen.append(s)
        if len(chosen) == n:
            break
    return chosen


def _n_lines(tier, rnd):
    mean = LINES_MEAN[tier]
    # 1 + Poisson(mean - 1)
    lam = mean - 1.0
    k, pk = 0, math.exp(-lam)
    x = rnd.random()
    acc = pk
    while x > acc and k < 8:
        k += 1
        pk *= lam / k
        acc += pk
    return 1 + k


def _write_orders(reg, people, planned, ledger):
    fq_o, fq_l = "consumer.dtc_order", "consumer.dtc_order_line"
    gen_o, gen_l = reg.gen(fq_o), reg.gen(fq_l)
    orng, lrng = reg.rng(fq_o), reg.rng(fq_l)
    opool = reg.alloc(fq_o, len(planned))
    orders, lines = [], []
    tier_pct = dict((t["name"], t["discount_pct"]) for t in world.TIERS)
    last_odt = {}
    for k, po in enumerate(planned):
        p = po["person"]
        mk = p.market
        cur = mk["currency"]
        vat = mk["vat"]
        day = po["day"]
        hour = _weighted(orng, [(h, w) for h, w in zip(range(24), [1, 1, 1, 1, 1, 2, 4, 6, 7, 7, 7, 7, 8, 7, 7, 7,
                                                                      8, 9, 10, 12, 13, 12, 8, 4])])
        odt = _ts(day, hour, orng.randint(0, 59), orng.randint(0, 59))
        prev_odt = last_odt.get(p.id)
        if prev_odt is not None and odt <= prev_odt:
            # a second order of the same shopper on the same day comes after the first one
            odt = prev_odt + datetime.timedelta(minutes=17 + (k % 70))
        last_odt[p.id] = odt
        sub = po["sub"]
        member = p.member and (p.enrolled is not None and p.enrolled <= day)
        tier = p.tier if member else None
        basket_tier = p.tier          # heavy buyers buy big baskets, enrolled or not
        # basket
        if po["kind"] == "subscription":
            skus = [sub["sku"]]
            qtys = [sub["qty"]]
            if orng.random() < ADDON_P[basket_tier]:
                for extra in _pick_skus(p, day, orng.randint(1, 2), orng):
                    if extra["code"] != sub["sku"]["code"]:
                        skus.append(extra)
                        target = orng.uniform(9.0, 20.0) * QTY_BOOST[basket_tier]
                        qtys.append(max(1, min(12, int(round(target / float(extra["rsp_eur"]))))))
            channel = "dtc_subscription"
        else:
            n = _n_lines(basket_tier, orng)
            skus = _pick_skus(p, day, n, orng)
            qtys = []
            for s in skus:
                unit_eur = float(s["rsp_eur"])
                target = orng.uniform(14.0, 28.0) * QTY_BOOST[basket_tier]
                qtys.append(max(1, min(12, int(round(target / unit_eur)))))
            channel = p.channel if orng.random() < 0.8 else _weighted(orng, CHANNELS)
        promo = None
        promo_pct = D(0)
        if po["kind"] == "welcome":
            promo, promo_pct = "WELCOME10", D("10")
        elif po["kind"] == "subscription":
            promo, promo_pct = "SUBSCRIBE10", D("10")
        elif orng.random() < 0.17:
            promo = _PROMOS[day.month]
            promo_pct = D(promo[-2:])
        pct = promo_pct + (tier_pct[tier] if tier else D(0))
        status = "delivered"
        cancelled = orng.random() < 0.016
        if cancelled:
            status = "cancelled"
        elif day >= datetime.date(2026, 9, 29):
            status = _weighted(orng, [("pending", 0.3), ("confirmed", 0.4), ("processing", 0.3)])
        elif day >= datetime.date(2026, 9, 23):
            status = "shipped"
        redeem_points = 0
        wants_redeem = False
        bal_now = D(0)
        if member:
            ledger.advance(p, odt)
            bal_now = ledger.balance.get(p.id, D(0))
            wants_redeem = (status != "cancelled" and bal_now >= REDEEM_MIN_BALANCE and orng.random() < REDEEM_P)
        # line math (redemption converted to an extra discount percentage)
        prices = [world.local_price_excl_vat(s, mk) for s in skus]
        subtotal_pre = sum(q4(D(q) * pr) for q, pr in zip(qtys, prices))
        if wants_redeem and subtotal_pre:
            # points pay for part of the basket (100 points = 1 EUR, at most 30 % of the merchandise)
            cap_pts = subtotal_pre * D(str(world.FX_BASE[cur])) * REDEEM_MAX_SHARE / world.POINT_VALUE_EUR
            redeem_points = int((min(bal_now, cap_pts) // 100) * 100)
        if redeem_points:
            value_local = (D(redeem_points) * world.POINT_VALUE_EUR) / D(str(world.FX_BASE[cur]))
            red_pct = (value_local / subtotal_pre * 100).quantize(D("0.01"), rounding=ROUND_FLOOR) if subtotal_pre else D(0)
            red_pct = min(red_pct, D("30.00"))
            if red_pct < D("1"):
                redeem_points, red_pct = 0, D(0)
            pct += red_pct
        pct = min(pct, D("40"))
        shipped = status in ("shipped", "delivered")
        ship_date = day + datetime.timedelta(days=1 if hour < 14 else 2) if shipped else None
        promised = day + datetime.timedelta(days=orng.randint(2, 4))
        late = orng.random() < 0.07
        delivery = (ship_date + datetime.timedelta(days=orng.randint(1, 3) + (orng.randint(2, 4) if late else 0))
                    if status == "delivered" else None)
        if delivery and delivery > world.TXN_END + datetime.timedelta(days=5):
            delivery = world.TXN_END + datetime.timedelta(days=2)
        oid = opool[k]
        o_lines = []
        for ln_no, (s, qty, price) in enumerate(zip(skus, qtys, prices), start=1):
            sub_amt = q4(D(qty) * price)
            disc = q4(sub_amt * pct / 100)
            net = sub_amt - disc
            tax = q4(net * vat)
            cogs = q4(D(qty) * s["std_cost_eur"] * std_cost_factor(day.year) / D(str(world.FX_BASE[cur])))
            returned = (status == "delivered" and orng.random() < 0.056)
            o_lines.append({"sku": s, "qty": qty, "price": price, "subtotal": sub_amt, "disc": disc, "net": net,
                            "tax": tax, "total": net + tax, "cogs": cogs, "returned": returned, "line_no": ln_no})
        if status == "delivered" and o_lines and all(l["returned"] for l in o_lines):
            status = "returned"
        subtotal = sum(l["subtotal"] for l in o_lines)
        discount = sum(l["disc"] for l in o_lines)
        tax_total = sum(l["tax"] for l in o_lines)
        gross_incl = (subtotal - discount) + tax_total
        free_ship = (tier is not None and world.TIER[tier]["free_shipping"]) or gross_incl >= mk["free_ship_over"] \
            or po["kind"] == "subscription"
        shipping = D(0) if free_ship else mk["ship_fee"]
        total = subtotal - discount + shipping + tax_total
        mult = world.TIER[tier]["multiplier"] if tier else D(0)
        earned_total = 0
        for l in o_lines:
            if tier and status != "cancelled":
                net_eur = l["net"] * D(str(world.FX_BASE[cur]))
                l["points"] = int((net_eur * mult).to_integral_value(rounding=ROUND_FLOOR))
            else:
                l["points"] = 0
            earned_total += l["points"]
        any_return = any(l["returned"] for l in o_lines)
        pay_status = ("refunded" if status in ("cancelled", "returned") else
                      "partially_refunded" if any_return else
                      "authorized" if status in ("pending", "confirmed", "processing") else "captured")
        ful = ("cancelled" if status == "cancelled" else "fulfilled" if shipped or status == "returned" else "unfulfilled")
        last_change = odt + datetime.timedelta(minutes=orng.randint(2, 50))
        if delivery:
            last_change = _ts(delivery, orng.randint(9, 19), orng.randint(0, 59))
        if any_return and delivery:
            last_change = _ts(delivery + datetime.timedelta(days=orng.randint(4, 14)), orng.randint(9, 17), orng.randint(0, 59))
        if last_change > world.EXTRACT_TS:
            last_change = world.EXTRACT_TS - datetime.timedelta(hours=orng.randint(1, 48))
        device = ("mobile" if channel in ("mobile_app", "social_commerce") else "voice_assistant" if channel == "voice_commerce"
                  else _weighted(orng, [("desktop", 0.55), ("mobile", 0.35), ("tablet", 0.10)]))
        carrier = orng.choice(mk["carrier"])
        shipment_id = reg.pick("distribution.shipment", orng) if shipped or status == "returned" else None
        outbound_id = reg.pick("distribution.outbound_order", orng) if shipped or status == "returned" else None
        dc_id = reg.ctx["dc_id"][mk["dc"]]
        fixed = {
            "dtc_order_id": oid, "company_code_id": reg.ctx["company_id"][mk["company"]],
            "cost_center_id": reg.ctx["cc"][mk["company"] + "DTC"], "distribution_facility_id": dc_id,
            "loyalty_account_id": None,  # set after accounts exist
            "order_id": None, "outbound_order_id": outbound_id, "primary_dtc_procurement_purchase_order_id": None,
            "ship_to_address_id": p.address_id, "shipment_id": shipment_id, "shopper_id": p.id,
            "sku_id": reg.ctx["sku_id"][o_lines[0]["sku"]["code"]], "subscription_id": sub["id"] if sub else None,
            "trade_account_id": None, "actual_delivery_date": delivery,
            "billing_address_same_flag": orng.random() < 0.88, "carrier_code": carrier,
            "channel_code": channel, "created_timestamp": odt + datetime.timedelta(seconds=orng.randint(3, 90)),
            "currency_code": cur, "device_type": device, "discount_amount": discount,
            "fulfillment_ref": "WMS-%s-%07d" % (mk["dc"][2:], k + 1) if shipped or status == "returned" else None,
            "fulfillment_status": ful, "gift_order_flag": day.month == 12 and orng.random() < 0.12,
            "ip_country_code": p.country if orng.random() < 0.97 else "SWE",
            "loyalty_points_earned": earned_total if status != "cancelled" else 0,
            "loyalty_points_redeemed": redeem_points, "order_date": odt, "order_status": status,
            "order_total_amount": total, "payment_method": _weighted(orng, [("credit_card", 0.38), ("debit_card", 0.22), ("paypal", 0.12), ("apple_pay", 0.14), ("google_pay", 0.09), ("gift_card", 0.05)]),
            "payment_status": pay_status, "payment_transaction_ref": "PSP-%012d" % (orng.getrandbits(40)),
            "promised_delivery_date": promised, "promotion_code": promo, "return_flag": any_return,
            "return_reason_code": next((l["reason"] for l in o_lines if l.get("reason")), None),
            "ship_to_name": "%s %s" % (p.first, p.last), "shipped_date": ship_date, "shipping_amount": shipping,
            "source_system_order_ref": "SFCC-%s-%08d" % (p.country[:2], 10000000 + k),
            "subscription_order_flag": sub is not None, "subtotal_amount": subtotal, "tax_amount": tax_total,
            "tracking_number": ("%s%010d" % (carrier[:2], orng.getrandbits(32))) if shipment_id else None,
            "updated_timestamp": last_change,
        }
        for l in o_lines:
            if l["returned"]:
                l["reason"] = orng.choice(RETURN_REASONS)
        fixed["return_reason_code"] = next((l["reason"] for l in o_lines if l.get("reason")), None)
        if member:
            fixed["loyalty_account_id"] = p.account_id
        orow = gen_o.row(k, orng, fixed, anchor=odt, country=p.country)
        orow["_tier"] = tier
        if member:
            if redeem_points:
                ledger.debit(p, odt, D(redeem_points), "redeem", "purchase", orow)
            if earned_total:
                when = _ts(delivery, 6) if delivery else odt + datetime.timedelta(hours=2)
                ledger.schedule(p, when, "purchase", D(earned_total), orow)
            if status in ("delivered", "returned") and orng.random() < 0.05:
                rv = odt + datetime.timedelta(days=orng.randint(8, 30))
                if rv.date() <= world.TXN_END:
                    ledger.schedule(p, rv, "product_review", D(BONUS_POINTS["product_review"]), orow)
        orders.append(orow)
        p.orders.append(orow)
        if sub:
            sub["orders"].append(orow)
        ev = reg.pick("promotion.event", lrng) if promo and po["kind"] == "regular" else None
        for l in o_lines:
            s = l["sku"]
            lstat = ("cancelled" if status == "cancelled" else "delivered" if status in ("delivered", "returned")
                     else "shipped" if status == "shipped" else
                     {"pending": "pending", "confirmed": "confirmed", "processing": "picking"}[status])
            lfixed = {
                "distribution_facility_id": dc_id, "dtc_order_id": oid, "event_id": ev,
                "outbound_order_line_id": None,
                "profit_center_id": reg.ctx["pc"][BRAND_PC[s["brand"]][0]], "shipment_id": shipment_id,
                "shopper_id": p.id, "sku_id": reg.ctx["sku_id"][s["code"]],
                "subscription_id": sub["id"] if sub and s["code"] == sub["sku"]["code"] else None,
                "supply_atp_record_id": reg.pick("supply.atp_record", lrng) if lrng.random() < 0.4 else None,
                "actual_delivery_date": delivery, "actual_ship_date": ship_date,
                "brand_code": s["brand"], "channel_code": LINE_CHANNEL[channel], "cost_of_goods_sold": l["cogs"],
                "created_timestamp": fixed["created_timestamp"] + datetime.timedelta(milliseconds=0, seconds=l["line_no"]),
                "currency_code": cur, "fulfillment_status": lstat, "gift_flag": fixed["gift_order_flag"],
                "gtin": s["gtin"], "hazmat_flag": s["form"] == "spray", "is_returned": l["returned"],
                "line_discount_amount": l["disc"], "line_discount_pct": pct, "line_net_amount": l["net"],
                "line_number": l["line_no"], "line_subtotal": l["subtotal"], "line_total_amount": l["total"],
                "loyalty_points_earned": l["points"],
                "loyalty_points_redeemed": 0,
                "product_category_code": s["subcat"], "product_name": s["full_name"],
                "promised_delivery_date": promised, "promised_ship_date": day + datetime.timedelta(days=1),
                "promotion_code": promo, "quantity_cancelled": l["qty"] if status == "cancelled" else 0,
                "quantity_ordered": l["qty"], "quantity_shipped": l["qty"] if (shipped or status == "returned") else 0,
                "regulatory_hold_flag": False, "return_reason_code": l.get("reason"),
                "subscription_flag": sub is not None, "tax_amount": l["tax"], "unit_of_measure": "EA",
                "unit_price": l["price"], "updated_timestamp": last_change,
            }
            lines.append((lfixed, odt, p.country))
        # distribute redeemed points over lines (integer split, remainder on line 1)
        if redeem_points:
            share = redeem_points // len(o_lines)
            rem = redeem_points - share * len(o_lines)
            for j, (lf, _, _) in enumerate(lines[-len(o_lines):]):
                lf["loyalty_points_redeemed"] = share + (rem if j == 0 else 0)
    lpool = reg.alloc(fq_l, len(lines))
    lrows = []
    for i, (lf, odt, country) in enumerate(lines):
        lf["dtc_order_line_id"] = lpool[i]
        lrows.append(gen_l.row(i, lrng, lf, anchor=odt, country=country))
    reg.rows[fq_o] = orders
    reg.rows[fq_l] = lrows


# --------------------------------------------------------------------------------------
# loyalty accounts and point movements
# --------------------------------------------------------------------------------------

def _plan_accounts(reg, people):
    """Allocate one loyalty account per member (ordered by enrolment) and referrals."""
    members = [p for p in people if p.member]
    members.sort(key=lambda p: (p.enrolled, p.idx))
    apool = reg.alloc("consumer.loyalty_account", len(members))
    arnd = reg.rng("consumer.loyalty_account", "referral")
    for i, p in enumerate(members):
        p.account_id = apool[i]
        if i > 20 and arnd.random() < 0.10:
            p.referred_by = members[arnd.randrange(0, i)]
    return members


class Ledger(object):
    """Chronological points ledger per member (earn / redeem / adjust / expire).

    Orders call :meth:`advance` before deciding on a redemption, so a member can only
    redeem points that were already credited; every movement records the balance before
    and after, and account totals are derived from the movements.
    """

    def __init__(self, rnd):
        self.rnd = rnd
        self.pending = {}
        self.balance = {}
        self.tx = []
        self.stats = {}
        self.seq = 0
        self.people = {}

    def _st(self, p):
        if p.id not in self.stats:
            self.stats[p.id] = {"earned": D(0), "redeemed": D(0), "expired": D(0), "last_earn": None,
                                "last_redeem": None, "last_activity": None}
            self.balance[p.id] = D(0)
            self.people[p.id] = p
        return self.stats[p.id]

    def schedule(self, p, ts, kind, pts, order=None):
        self._st(p)
        self.seq += 1
        heapq.heappush(self.pending.setdefault(p.id, []), (ts, self.seq, kind, pts, order))

    def schedule_bonuses(self, members, planned):
        order_days = {}
        for po in planned:
            order_days.setdefault(po["person"].id, []).append(po["day"])
        for p in members:
            acc_ts = _ts(p.enrolled, 10, 0) + datetime.timedelta(minutes=p.idx % 600)
            self.schedule(p, acc_ts, "account_registration", D(BONUS_POINTS["account_registration"]))
            if p.referred_by is not None:
                self.schedule(p.referred_by, acc_ts + datetime.timedelta(days=1), "referral",
                              D(BONUS_POINTS["referral"]))
            days = order_days.get(p.id, [])
            for y in (2024, 2025, 2026):
                try:
                    bday = datetime.date(y, p.birth.month, p.birth.day)
                except ValueError:
                    bday = datetime.date(y, 2, 28)
                # birthday bonus only for members who ordered in the 12 months before their birthday
                active = any(bday - datetime.timedelta(days=365) <= d <= bday for d in days)
                if active and p.enrolled <= bday <= world.TXN_END and (p.churn is None or bday <= p.churn):
                    self.schedule(p, _ts(bday, 5, 30), "birthday_bonus", D(BONUS_POINTS["birthday_bonus"]))
            if self.rnd.random() < 0.03:
                when = rand_between(self.rnd, max(p.enrolled, world.TXN_START), world.TXN_END)
                self.schedule(p, _ts(when, 11), "goodwill", D(self.rnd.choice([50, 100, 150])))

    def _record(self, p, ts, ttype, direction, trig, pts, order, kind):
        st = self._st(p)
        before = self.balance[p.id]
        after = before + pts if direction == "credit" else before - pts
        self.balance[p.id] = after
        if direction == "credit":
            st["earned"] += pts
            st["last_earn"] = ts.date()
        elif ttype == "expire":
            st["expired"] += pts
        else:
            st["redeemed"] += pts
            st["last_redeem"] = ts.date()
        if ttype != "expire":
            st["last_activity"] = ts.date()
        self.tx.append((ts, p, ttype, direction, trig, pts, before, after, order, kind))

    def advance(self, p, until):
        heap = self.pending.get(p.id)
        while heap and heap[0][0] <= until:
            ts, _, kind, pts, order = heapq.heappop(heap)
            if kind == "redeem_reward":
                pts = min(pts, (self.balance[p.id] // 100) * 100)
                if pts > 0:
                    self._record(p, ts, "redeem", "debit", "promotion_bonus", pts, None, kind)
                continue
            ttype = "adjust" if kind == "goodwill" else "earn"
            trig = "survey_completion" if kind == "goodwill" else kind
            self._record(p, ts, ttype, "credit", trig, pts, order, kind)
            if self.balance[p.id] >= 1000 and self.rnd.random() < 0.30:
                # gift card / free product reward
                rts = ts + datetime.timedelta(days=self.rnd.randint(1, 20))
                if rts.date() <= world.TXN_END:
                    self.schedule(p, rts, "redeem_reward", D(self.rnd.choice([500, 800, 1000])))

    def debit(self, p, ts, pts, ttype, trig, order):
        self._record(p, ts, ttype, "debit", trig, pts, order, "redeem_order")

    def finish(self, members):
        end = datetime.datetime.combine(world.TXN_END, datetime.time(23, 59, 59))
        for p in members:
            self._st(p)
            self.advance(p, end)
            st = self.stats[p.id]
            if st["last_activity"] and self.balance[p.id] > 0:
                exp_day = st["last_activity"] + datetime.timedelta(days=365)
                if exp_day <= world.TXN_END:
                    self._record(p, _ts(exp_day, 2), "expire", "debit", "promotion_bonus",
                                 self.balance[p.id], None, "expire")
        self.tx.sort(key=lambda t: (t[0], t[1].idx))
        for p in members:
            p.balance = self.balance[p.id]


def _loyalty_transactions(reg, ledger):
    fq_t = "consumer.loyalty_transaction"
    trnd = reg.rng(fq_t)
    tpool = reg.alloc(fq_t, len(ledger.tx))
    gen_t = reg.gen(fq_t)
    trows = []
    seq = {}
    for i, (ts, p, ttype, direction, trig, pts, before, after, o, kind) in enumerate(ledger.tx):
        seq[ts.year] = seq.get(ts.year, 0) + 1
        mk = p.market
        tier = p.tier
        is_purchase = kind == "purchase"
        if o is not None and o.get("_tier"):
            tier = o["_tier"]          # tier at the time of the order (before a later tier review)
        spend_eur = None
        if is_purchase and o is not None:
            spend_eur = q2((o["subtotal_amount"] - o["discount_amount"]) * D(str(world.FX_BASE[mk["currency"]])))
        fixed = {
            "loyalty_transaction_id": tpool[i], "event_id": None,
            "gl_account_id": reg.ctx["gl"][(mk["company"], "2810")], "loyalty_account_id": p.account_id,
            "loyalty_program_id": reg.ctx["program_id"], "loyalty_tier_id": reg.ctx["tier_id"][tier],
            "order_id": None, "pos_transaction_id": None, "reversal_reference_loyalty_transaction_id": None,
            "shopper_id": p.id, "sku_id": o["sku_id"] if o is not None else None, "trade_promotion_id": None,
            "adjustment_notes": "Goodwill points after delayed delivery" if kind == "goodwill" else None,
            "adjustment_reason_code": "GOODWILL" if kind == "goodwill" else None,
            "bonus_multiplier": world.TIER[tier]["multiplier"],
            "channel": "mobile_app" if (o is not None and o["channel_code"] == "mobile_app") else "dtc_website",
            "consent_verified": True, "country_code": p.country, "created_timestamp": ts + datetime.timedelta(seconds=7),
            "currency_code": "EUR", "data_retention_flag": False,
            "earn_rate": world.TIER[tier]["multiplier"] if is_purchase else None, "fraud_flag": False,
            "fraud_review_status": "not_reviewed",
            "is_bonus_transaction": kind in ("birthday_bonus", "referral", "product_review", "account_registration"),
            "monetary_value": q2(pts * world.POINT_VALUE_EUR), "points_amount": pts,
            "points_balance_after": after, "points_balance_before": before, "points_direction": direction,
            "points_expiry_date": (ts.date() + datetime.timedelta(days=730)) if direction == "credit" else None,
            "points_liability_flag": True, "processing_timestamp": ts + datetime.timedelta(seconds=40),
            "program_year": ts.year, "qualifying_spend_amount": spend_eur,
            "redemption_value": q2(pts * world.POINT_VALUE_EUR) if ttype == "redeem" else None,
            "source_transaction_ref": "L%07d" % (i + 1),
            "transaction_number": "LT-%d-%08d" % (ts.year, seq[ts.year]), "transaction_status": "processed",
            "transaction_timestamp": ts, "transaction_type": ttype, "trigger_event": trig,
            "updated_timestamp": ts + datetime.timedelta(seconds=40),
        }
        trows.append(gen_t.row(i, trnd, fixed, anchor=ts, country=p.country))
    reg.rows[fq_t] = trows


def _loyalty_accounts(reg, members, ledger):
    fq_a = "consumer.loyalty_account"
    arnd = reg.rng(fq_a)
    gen_a = reg.gen(fq_a)
    arows = []
    prev_tier = {"Bronze": None, "Silver": "standard", "Gold": "silver", "Platinum": "gold"}
    for i, p in enumerate(members):
        st = ledger.stats[p.id]
        enrolled_ts = _ts(p.enrolled, 10) + datetime.timedelta(minutes=p.idx % 600)
        last_act = st["last_activity"] or p.enrolled
        tier_eff = max(p.enrolled, last_act - datetime.timedelta(days=arnd.randint(30, 300)))
        spend12 = _qualifying_spend(p)
        status = "active"
        opt_out = None
        fraud = arnd.random() < 0.006
        if fraud:
            status = "frozen"
        if fraud and last_act + datetime.timedelta(days=20) > world.TXN_END:
            last_act = world.TXN_END - datetime.timedelta(days=25)
        if p.churn and p.churn < datetime.date(2026, 3, 1) and arnd.random() < 0.35:
            status = "closed"
            opt_out = max(p.churn, last_act) + datetime.timedelta(days=arnd.randint(1, 60))
            if opt_out > world.TXN_END:
                opt_out = world.TXN_END
        fixed = {
            "loyalty_account_id": p.account_id, "consent_record_id": p.consent_marketing_id,
            "loyalty_program_id": reg.ctx["program_id"], "loyalty_tier_id": reg.ctx["tier_id"][p.tier],
            "pos_transaction_id": None,
            "referral_account_loyalty_account_id": p.referred_by.account_id if p.referred_by else None,
            "retail_store_id": reg.pick("sales.retail_store", arnd) if arnd.random() < 0.3 else None,
            "shopper_id": p.id, "account_number": "FF%010d" % (1000000000 + p.idx * 7919 % 1000000000),
            "account_status": status, "account_type": "individual",
            "cltv_segment": "lapsed" if p.segment == "churned" else p.segment,
            "communication_preference": "email" if p.opt_in_email else ("push" if p.opt_in_push else "none"),
            "consent_data_sharing": p.data_sharing, "consent_marketing": p.opt_in_email,
            "consent_timestamp": enrolled_ts, "country_code": p.country, "created_timestamp": enrolled_ts,
            "enrollment_channel": "mobile_app" if p.channel == "mobile_app" else "web",
            "enrollment_date": p.enrolled, "enrollment_source_code": "WELCOME-%d" % p.enrolled.year,
            "expiry_date": last_act + datetime.timedelta(days=730), "fraud_flag": fraud,
            "fraud_review_date": (last_act + datetime.timedelta(days=arnd.randint(2, 20))) if fraud else None,
            "language_code": p.market["lang"], "last_activity_date": st["last_activity"],
            "last_earn_date": st["last_earn"], "last_redemption_date": st["last_redeem"],
            "lifetime_points_earned": st["earned"], "lifetime_points_expired": st["expired"],
            "lifetime_points_redeemed": st["redeemed"], "nps_score": p.nps,
            "nps_survey_date": last_act if arnd.random() < 0.6 else None, "opt_out_date": opt_out,
            "points_balance": ledger.balance[p.id], "points_currency_code": "EUR",
            "points_expiry_policy": "rolling_12_months",
            "preferred_redemption_type": _weighted(arnd, [("discount", 0.6), ("free_product", 0.2), ("gift_card", 0.1), ("charity", 0.1)]),
            "previous_tier": ({"Bronze": "standard"}.get(p.tier_before, (p.tier_before or "").lower())
                              if p.tier_before else prev_tier[p.tier]),
            "source_system_code": "CUSTOM_CRM",
            "tier_effective_date": tier_eff, "tier_qualification_spend": q2(spend12),
            "tier_review_date": tier_eff + datetime.timedelta(days=365),
            "updated_timestamp": _ts(last_act, 6) + datetime.timedelta(hours=arnd.randint(1, 30)),
        }
        if fixed["updated_timestamp"] < enrolled_ts:
            fixed["updated_timestamp"] = enrolled_ts + datetime.timedelta(hours=1)
        if fixed["updated_timestamp"] > world.EXTRACT_TS:
            fixed["updated_timestamp"] = world.EXTRACT_TS
        arows.append(gen_a.row(i, arnd, fixed, anchor=enrolled_ts, country=p.country))
    reg.rows[fq_a] = arows


def _qualifying_spend(p):
    """Net merchandise value (EUR, excl. VAT) of the member's non-cancelled orders in the last 12 months."""
    return sum((((o["subtotal_amount"] - o["discount_amount"]) * D(str(world.FX_BASE[o["currency_code"]])))
                for o in p.orders if o["order_status"] != "cancelled"
                and o["order_date"].date() >= world.TXN_END - datetime.timedelta(days=365)), D(0))


def _requalify_tiers(reg, members, ledger):
    """Annual tier review: a member keeps the tier if lifetime points OR the qualifying spend (EUR,
    excl. VAT) of the last 12 months reach the tier's requirement; otherwise the member moves down to
    the highest tier he or she qualifies for (``loyalty_account.previous_tier`` keeps the old tier).
    The review never upgrades - upgrades come from campaigns at enrolment."""
    rank = dict((t["name"], t["rank"]) for t in world.TIERS)
    moved = 0
    for p in members:
        pts = ledger.stats[p.id]["earned"]
        spend = _qualifying_spend(p)
        best = "Bronze"
        for t in world.TIERS:
            if t["rank"] > 1 and (pts >= t["required_points"] or spend >= t["required_spend"]):
                best = t["name"]
        if rank[best] < rank[p.tier]:
            p.tier_before = p.tier
            p.tier = best
            moved += 1
    reg.ctx["tier_requalified"] = moved


def rand_between(rnd, a, b):
    if b <= a:
        return a
    return a + datetime.timedelta(days=rnd.randint(0, (b - a).days))


# --------------------------------------------------------------------------------------
# subscriptions (rows)
# --------------------------------------------------------------------------------------

def _subscriptions(reg, people, subs, orders):
    fqn = "consumer.subscription"
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    rows = []
    for i, s in enumerate(subs):
        p = s["person"]
        mk = p.market
        sku = s["sku"]
        price = q4(world.local_price_excl_vat(sku, mk) * s["qty"])
        rate = D("0.1000")
        fulfilled = [o for o in s["orders"] if o["order_status"] in ("delivered", "returned", "shipped")]
        last_o = max((o["order_date"].date() for o in s["orders"]), default=None)
        status = s["status"]
        nxt = None
        if status == "active":
            base = last_o or s["start"]
            nxt = base + datetime.timedelta(days=FREQ_DAYS[s["freq"]])
            if nxt > world.FUTURE_MAX:
                nxt = world.FUTURE_MAX
        created = _ts(s["start"] - datetime.timedelta(days=rnd.randint(0, 3)), rnd.randint(8, 21), rnd.randint(0, 59))
        cancel_date = s["end"] if status == "cancelled" else None
        trial = rnd.random() < 0.08 and s["start"] + datetime.timedelta(days=30) <= world.TXN_END
        fixed = {
            "subscription_id": s["id"], "company_code_id": reg.ctx["company_id"][mk["company"]],
            "delivery_address_id": p.address_id, "distribution_facility_id": reg.ctx["dc_id"][mk["dc"]],
            "event_id": reg.pick("promotion.event", rnd) if rnd.random() < 0.2 else None, "loyalty_program_id": reg.ctx["program_id"] if p.member else None,
            "shopper_id": p.id, "sku_id": reg.ctx["sku_id"][sku["code"]],
            "acquisition_source": _weighted(rnd, [("newsletter", 0.35), ("webshop_banner", 0.3), ("paid_social", 0.2), ("referral", 0.15)]),
            "auto_renew_flag": True, "billing_cycle_day": min(28, s["start"].day),
            "cancellation_date": cancel_date,
            "cancellation_reason": _weighted(rnd, [("no_longer_needed", 0.35), ("price_too_high", 0.25), ("found_alternative", 0.15), ("product_dissatisfaction", 0.1), ("financial_hardship", 0.05), ("other", 0.1)]) if cancel_date else None,
            "ccpa_opt_out_flag": False, "channel": "dtc_app" if p.channel == "mobile_app" else "dtc_web",
            "created_timestamp": created, "currency_code": mk["currency"], "discount_rate": rate,
            "end_date": s["end"] if status in ("cancelled", "expired") else None,
            "failed_payment_count": 0 if rnd.random() < 0.85 else rnd.randint(1, 3), "frequency": s["freq"],
            "gdpr_consent_flag": True, "last_order_date": last_o, "net_price": q4(price * (1 - rate)),
            "next_order_date": nxt, "nps_score": p.nps,
            "pause_end_date": s["pause"][1] if s["pause"] and status != "paused" else None,
            "pause_reason": _weighted(rnd, [("travel", 0.4), ("product_overstock", 0.4), ("other", 0.2)]) if s["pause"] else None,
            "pause_start_date": s["pause"][0] if s["pause"] else None,
            "payment_method_type": _weighted(rnd, [("credit_card", 0.55), ("debit_card", 0.25), ("digital_wallet", 0.2)]),
            "payment_token_reference": "tok_%016x" % rnd.getrandbits(64), "price": price,
            "promotion_code": "SUBSCRIBE10", "quantity": s["qty"], "start_date": s["start"],
            "subscription_number": "SUB-%s%08d" % (p.country[:2], 30000000 + i), "subscription_status": status,
            "subscription_type": s["plan"][2], "total_orders_fulfilled": len(fulfilled),
            "trial_end_date": (s["start"] + datetime.timedelta(days=30)) if trial else None, "trial_flag": trial,
            "updated_timestamp": max(created, _ts(last_o, 6) if last_o else created) + datetime.timedelta(hours=rnd.randint(1, 40)),
        }
        if fixed["updated_timestamp"] > world.EXTRACT_TS:
            fixed["updated_timestamp"] = world.EXTRACT_TS
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=p.country))
    reg.rows[fqn] = rows


# --------------------------------------------------------------------------------------
# shoppers, households, preferences (rows)
# --------------------------------------------------------------------------------------

def _segment_shoppers(reg, people):
    """last purchase date, CLTV segment and lifecycle status from the order history."""
    rnd = reg.rng("consumer.shopper", "segment")
    # spend for value segmentation (EUR, non-cancelled)
    spend = {}
    for p in people:
        spend[p.id] = sum(((o["order_total_amount"] * D(str(world.FX_BASE[o["currency_code"]])))
                           for o in p.orders if o["order_status"] != "cancelled"), D(0))
        if p.orders:
            p.last_purchase = max(o["order_date"].date() for o in p.orders)
        else:
            # history before the transaction window (or a churned shopper)
            hi = min(p.churn or datetime.date(2023, 12, 31), datetime.date(2023, 12, 31))
            if hi < p.acq:
                hi = p.acq
            p.last_purchase = rand_between(rnd, p.acq, hi)
    ranked = sorted([p for p in people if (world.EXTRACT_DATE - p.last_purchase).days <= 180],
                    key=lambda p: (-spend[p.id], p.idx))
    n = len(ranked)
    for k, p in enumerate(ranked):
        p.segment = "high_value" if k < n * 0.22 else ("mid_value" if k < n * 0.65 else "low_value")
    for p in people:
        days = (world.EXTRACT_DATE - p.last_purchase).days
        if days > 365:
            p.segment = "churned"
        elif days > 180:
            p.segment = "at_risk"
        p.lifecycle = "inactive" if p.segment == "churned" else "active"
        if p.lifecycle == "active" and rnd.random() < 0.02:
            p.lifecycle = "opted_out"


def _finalise_shoppers(reg, people, orders):
    fqn = "consumer.shopper"
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    rows = []
    banners = dict((c, [t["dba"] for t in world.RETAIL_BANNERS if t["country"] == c]) for c in world.MARKET)
    for p in people:
        created = _ts(p.acq, rnd.randint(7, 22), rnd.randint(0, 59), rnd.randint(0, 59))
        first = min((o["order_date"] for o in p.orders), default=None)
        if first is not None and first.date() == p.acq and created > first - datetime.timedelta(minutes=2):
            # account created at checkout, a few minutes before the first order
            created = max(_ts(p.acq, 0, 0), first - datetime.timedelta(minutes=rnd.randint(3, 40)))
        updated = max(created, _ts(p.last_purchase, 23, 0)) + datetime.timedelta(hours=rnd.randint(1, 72))
        if updated > world.EXTRACT_TS:
            updated = world.EXTRACT_TS
        ids_verified = rnd.random() < 0.4
        fixed = {
            "shopper_id": p.id, "loyalty_program_id": reg.ctx["program_id"] if p.member else None,
            "loyalty_tier_id": reg.ctx["tier_id"][p.tier] if p.member else None,
            "acquisition_channel": p.acq_channel, "acquisition_date": p.acq, "age_verified": False,
            "birth_date": p.birth, "ccpa_subject": False, "cltv_segment": p.segment,
            "consent_timestamp": created + datetime.timedelta(minutes=2), "consent_version": "3.1" if p.acq >= datetime.date(2024, 5, 1) else "2.4",
            "consumer_type": "loyalty_member" if p.member else ("household" if p.household and rnd.random() < 0.1 else "individual"),
            "country_code": p.country, "created_timestamp": created, "data_sharing_consent": p.data_sharing,
            "display_name": "%s %s." % (p.first, p.last[0]), "email_opt_in": p.opt_in_email,
            "family_name": p.last, "gdpr_subject": True, "gender": p.gender, "given_name": p.first,
            "identity_verification_date": p.acq if ids_verified else None, "identity_verified": ids_verified,
            "last_purchase_date": p.last_purchase, "lifecycle_status": p.lifecycle,
            "loyalty_enrollment_date": p.enrolled, "loyalty_points_balance": q4(p.balance) if p.member else None,
            "nps_score": p.nps if rnd.random() < 0.55 else None,
            "nps_survey_date": rand_between(rnd, p.acq, p.last_purchase) if rnd.random() < 0.55 else None,
            "postal_code": None, "preferred_currency": p.market["currency"], "preferred_language": p.market["lang"],
            "preferred_store_banner": rnd.choice(banners[p.country]),
            "primary_email": p.email, "primary_phone": p.phone, "push_notification_opt_in": p.opt_in_push,
            "registration_source_url": "https://www.%s/%s/register" % (world.WEBSHOP, p.market["lang"][:2]),
            "sms_opt_in": p.opt_in_sms, "source_system_consumer_ref": "SFCC-%s-%07d" % (p.country[:2], 1000000 + p.idx),
            "updated_timestamp": updated,
        }
        if fixed["nps_score"] is None:
            fixed["nps_survey_date"] = None
        rows.append(fixed)
    # postal code of the primary address
    addr = dict((a["address_id"], a) for a in reg.rows["consumer.address"])
    out = []
    for i, (p, fixed) in enumerate(zip(people, rows)):
        fixed["postal_code"] = addr[p.address_id]["postal_code"]
        out.append(gen.row(i, rnd, fixed, anchor=fixed["created_timestamp"], country=p.country))
    reg.rows[fqn] = out


def _households(reg, people, households):
    fqn = "consumer.household"
    gen = reg.gen(fqn)
    rnd = reg.rng(fqn)
    # ~1.5 % of single-shopper households were merged into another household of the same country
    merged_into_this, absorbed_by = {}, {}
    singles = [h for h in households if len(h["members"]) == 1]
    for k, h in enumerate(singles):
        if k > 0 and rnd.random() < 0.03:
            target = singles[k - 1]
            if target["id"] in absorbed_by or target["id"] in merged_into_this or h["id"] in absorbed_by:
                continue
            if people[target["members"][0]].country != people[h["members"][0]].country:
                continue
            merged_into_this[target["id"]] = h["id"]
            absorbed_by[h["id"]] = target["id"]
    addr = dict((a["address_id"], a) for a in reg.rows["consumer.address"])
    rows = []
    for i, h in enumerate(households):
        members = [people[k] for k in h["members"]]
        head = members[0]
        created = _ts(head.acq, 12)
        last_upd = max(_ts(p.last_purchase, 20) for p in members)
        enrol_ts = max((_ts(p.enrolled, 10) for p in members if p.enrolled), default=None)
        if enrol_ts and last_upd < enrol_ts:
            last_upd = enrol_ts + datetime.timedelta(hours=2)
        if last_upd < created:
            last_upd = created + datetime.timedelta(hours=3)
        member_tiers = [p.tier for p in members if p.tier]
        best = max(member_tiers, key=lambda t: world.TIER[t]["rank"]) if member_tiers else None
        merged = merged_into_this.get(h["id"])
        absorbed = h["id"] in absorbed_by
        size = len(members) + (rnd.randint(0, 2) if len(members) > 1 else (1 if rnd.random() < 0.25 else 0))
        active = any(p.segment not in ("churned",) for p in members)
        fixed = {
            "household_id": h["id"], "loyalty_program_id": reg.ctx["program_id"] if best else None,
            "loyalty_tier_id": reg.ctx["tier_id"][best] if best else None, "merged_from_household_id": merged,
            "shopper_id": head.id, "brand_affinity_flag": sum(len(p.orders) for p in members) >= 4,
            "ccpa_opt_out_flag": False, "children_present_flag": size >= 3,
            "cltv_band": ("very_high" if any(p.segment == "high_value" for p in members) and best in ("Gold", "Platinum")
                          else "high" if any(p.segment == "high_value" for p in members)
                          else "medium" if any(p.segment == "mid_value" for p in members) else "low"),
            "code": "HH-%s%08d" % (head.country, 10000000 + i),
            "consent_last_updated_timestamp": max(created + datetime.timedelta(minutes=3),
                                                  max((_ts(p.enrolled, 10) for p in members if p.enrolled), default=created)),
            "country_code": head.country, "created_timestamp": created, "data_source": "dtc_platform",
            "digital_engagement_flag": True,
            "dissolution_date": min(world.TXN_END, max(head.last_purchase, head.acq) + datetime.timedelta(days=rnd.randint(5, 60)))
            if absorbed else None, "dwelling_type": _weighted(rnd, [("apartment", 0.55), ("house", 0.35), ("townhouse", 0.10)]),
            "estimated_size": size, "formation_date": head.acq, "gdpr_consent_flag": True,
            "geographic_region": {"SWE": "Nordics", "NOR": "Nordics", "DNK": "Nordics", "FIN": "Nordics",
                                  "DEU": "DACH", "NLD": "Benelux"}[head.country],
            "household_status": "merged" if absorbed else ("active" if active else "inactive"),
            "household_type": "single" if size == 1 else ("couple" if size == 2 else "family"),
            "last_updated_timestamp": min(last_upd, world.EXTRACT_TS),
            "life_stage": ("young_adults" if head.birth.year >= 1995 else "family_with_children" if size >= 3
                           else "established_adults" if head.birth.year >= 1965 else "empty_nesters"),
            "loyalty_enrollment_date": min((p.enrolled for p in members if p.enrolled), default=None),
            "loyalty_points_balance": q2(sum((p.balance for p in members if p.member), D(0))) if best else None,
            "market_segment": "Nordic wellbeing" if head.fav_brand == "MJUKCARE" else "Everyday Nordic pantry",
            "marketing_opt_in_flag": any(p.opt_in_email for p in members), "name": "%s household" % head.last,
            "nps_score": head.nps, "nps_survey_date": head.last_purchase, "panel_member_flag": False,
            "pet_owner_flag": rnd.random() < 0.3, "postal_code": addr[head.address_id]["postal_code"],
            "preferred_language": head.market["lang"],
            "primary_channel": "dtc" if sum(len(p.orders) for p in members) >= 3 else "omnichannel",
            "primary_retailer_banner": rnd.choice([t["dba"] for t in world.RETAIL_BANNERS if t["country"] == head.country]),
            "private_label_buyer_flag": rnd.random() < 0.4,
            "purchase_frequency_band": ("very_frequent" if sum(len(p.orders) for p in members) >= 10 else
                                        "frequent" if sum(len(p.orders) for p in members) >= 5 else
                                        "regular" if sum(len(p.orders) for p in members) >= 2 else "occasional"),
            "tenure_type": "owner" if rnd.random() < 0.55 else "renter",
        }
        rows.append(gen.row(i, rnd, fixed, anchor=created, country=head.country))
    reg.rows[fqn] = rows


def _preferences(reg, people, households, rnd):
    """One preference profile per shopper with an order history or a declared preference (~2 500)."""
    fqn = "consumer.preference"
    prnd = reg.rng(fqn)
    with_pref = [p for p in people if p.orders or prnd.random() < 0.30]
    pool = reg.alloc(fqn, len(with_pref))
    gen = reg.gen(fqn)
    rows = []
    cltv = {None: "unclassified", "Bronze": "bronze", "Silver": "silver", "Gold": "gold", "Platinum": "platinum"}
    for i, p in enumerate(with_pref):
        sku = world.SKU[p.fav_sku]
        created = _ts(p.acq + datetime.timedelta(days=prnd.randint(0, 60)), prnd.randint(8, 22))
        if created > world.EXTRACT_TS:
            created = world.EXTRACT_TS - datetime.timedelta(days=1)
        inferred = prnd.random() < 0.6
        fixed = {
            "preference_id": pool[i], "brand_id": reg.ctx["brand_id"][p.fav_brand],
            "consent_record_id": p.consent_marketing_id, "household_id": p.household,
            "loyalty_program_id": reg.ctx["program_id"] if p.member else None,
            "product_category_id": reg.ctx["category_id"][p.fav_subcat], "shopper_id": p.id,
            "sku_id": reg.ctx["sku_id"][p.fav_sku], "brand_override_flag": False, "brand_override_reason": None,
            "category": "product_category", "cltv_tier": cltv[p.tier],
            "confidence_score": D(str(round(prnd.uniform(0.62, 0.97), 4))) if inferred else D("1.0000"),
            "consent_basis": "explicit_consent", "created_timestamp": created, "data_subject_request_flag": False,
            "effective_date": created.date(), "expiry_date": None, "flavor_fragrance_preference": sku["flavour"],
            "geographic_scope": p.country,
            "inference_basis": "purchase_history" if inferred else None,
            "inference_model_version": "pref-model-2.3" if inferred else None, "is_global_preference": False,
            "last_updated_timestamp": min(world.EXTRACT_TS, created + datetime.timedelta(days=prnd.randint(1, 500))),
            "notes": None, "nps_segment": "promoter" if p.nps >= 9 else ("passive" if p.nps >= 7 else "detractor"),
            "opt_in_status": p.opt_in_email,
            "pack_size_preference": "family_size" if p.household else ("subscription" if any(o["subscription_order_flag"] for o in p.orders) else "standard"),
            "preference_status": "active" if p.segment != "churned" else "inactive",
            "preferred_channel": "email" if p.opt_in_email else ("sms" if p.opt_in_sms else "none"),
            "preferred_contact_frequency": _weighted(prnd, [("weekly", 0.2), ("monthly", 0.6), ("quarterly", 0.2)]),
            "preferred_language": p.market["lang"],
            "preferred_time_of_day": _weighted(prnd, [("morning", 0.25), ("afternoon", 0.2), ("evening", 0.45), ("no_preference", 0.1)]),
            "preferred_timezone": world.COUNTRY_TZ[p.country], "rank": 1,
            "retail_channel_preference": "webshop" if len(p.orders) >= 3 else ("drugstore" if p.fav_brand == "MJUKCARE" else "grocery_store"),
            "sku_preference": p.fav_sku, "source": "inferred_ml" if inferred else "declared",
            "source_system_preference_ref": "SFCC-PRF-%07d" % (i + 1),
            "subcategory": dict((c[0], c[1]) for c in world.SUBCATEGORIES)[p.fav_subcat],
            "suppression_reason": None,
            "value": D(str(round(prnd.uniform(55, 99), 2))),
        }
        rows.append(gen.row(i, prnd, fixed, anchor=created, country=p.country))
    reg.rows[fqn] = rows


def _finalise_program(reg):
    accts = reg.rows["consumer.loyalty_account"]
    prog = reg.rows["consumer.loyalty_program"][0]
    prog["points_balance"] = q2(sum((a["points_balance"] for a in accts), D(0)))
    prog["points_earned"] = q2(sum((a["lifetime_points_earned"] for a in accts), D(0)))
    for o in reg.rows["consumer.dtc_order"]:
        o.pop("_tier", None)
        o.pop("_points_redeemed", None)
