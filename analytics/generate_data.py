"""
Synthetic purchase-order and master-data history for the Lives Group case.

The brief ships no dataset, so this builds a simulated one with known ground truth:
- ~170 real customer accounts across 5 countries, some of them saved in SAP B1 more than once
  (a different business entity or a re-created record), which is the duplicate problem in the brief
- 45 months of monthly purchase orders (Jan 2023 - Sep 2026) for Products A, B and C
- country holiday and budget-cycle effects, a few customers drifting away, and patterns
  such as fast Product B growth in Vietnam that the regional view should surface
- monthly inbound volumes split into purchase orders, enquiries and MDM setup requests

Every pattern is planted on purpose and listed in PLANTED below, so the analysis can be
checked against the truth. Run: python3 analytics/generate_data.py
"""
import csv
import hashlib
import json
import os
import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
rng = np.random.default_rng(2026)

COUNTRIES = ["SG", "MY", "TH", "VN", "PH"]
PRODUCTS = ["A", "B", "C"]
# Assumed average selling price per unit, SGD. Labelled as an assumption in the app.
PRICE = {"A": 180.0, "B": 420.0, "C": 95.0}
# Which entity normally sells which product line (entities serve different product lines, brief s2)
ENTITY_FOR = {"A": "SPD", "B": "QTS", "C": "QTG"}

MONTHS = [f"{y}-{m:02d}" for y in (2023, 2024, 2025, 2026) for m in range(1, 13)][:45]  # Jan 2023 .. Sep 2026
IDX = {m: i for i, m in enumerate(MONTHS)}

# ---------------------------------------------------------------- calendar effects
CNY = {"2023-01", "2024-02", "2025-01", "2026-02"}            # Chinese New Year / Tet month
PRE_CNY = {"2024-01", "2024-12", "2026-01"}         # (Dec 2022 is before the data)        # stock-up month before it
RAYA = {"2023-04", "2024-04", "2025-03", "2026-03"}           # Hari Raya Aidilfitri
HOLY_WEEK = {"2023-04", "2024-03", "2025-04", "2026-04"}      # Philippines


def calendar(country, month):
    """Known-in-advance calendar flags for a country-month. Shared with the forecasting model."""
    mm = int(month[5:])
    return {
        "cny": int(month in CNY and country in ("SG", "MY", "VN")),
        "pre_cny": int(month in PRE_CNY and country in ("SG", "MY", "VN")),
        "tet": int(month in CNY and country == "VN"),
        "raya": int(month in RAYA and country == "MY"),
        "songkran": int(mm == 4 and country == "TH"),
        "holy_week": int(month in HOLY_WEEK and country == "PH"),
        "fy_flush": int((country == "SG" and mm == 3) or (country == "TH" and mm == 9)),
        "year_end": int(mm in (11, 12) and country in ("MY", "VN", "PH")),
    }


def season_mult(country, month):
    c = calendar(country, month)
    m = 1.0
    m *= 0.72 if c["cny"] else 1.0
    m *= 1.15 if c["pre_cny"] else 1.0
    m *= 0.80 if c["tet"] else 1.0           # Vietnam: CNY and Tet stack, bigger dip
    m *= 0.78 if c["raya"] else 1.0
    m *= 0.72 if c["songkran"] else 1.0
    m *= 0.85 if c["holy_week"] else 1.0
    m *= 1.30 if c["fy_flush"] else 1.0
    m *= 1.18 if c["year_end"] else 1.0
    return m


# ---------------------------------------------------------------- names
CITIES = {
    "SG": ["Singapore", "Jurong", "Tampines", "Novena", "Bukit Timah", "Woodlands", "Outram", "Changi"],
    "MY": ["Kuala Lumpur", "Klang", "Penang", "Johor Bahru", "Ipoh", "Kuching", "Shah Alam", "Melaka"],
    "TH": ["Bangkok", "Chiang Mai", "Khon Kaen", "Phuket", "Hat Yai", "Nonthaburi", "Udon Thani", "Pattaya"],
    "VN": ["Hanoi", "Saigon", "Da Nang", "Hai Phong", "Can Tho", "Hue", "Nha Trang", "Bien Hoa"],
    "PH": ["Manila", "Cebu", "Davao", "Makati", "Quezon City", "Iloilo", "Baguio", "Pasig"],
}
DESC = ["General", "Specialist", "Medical", "Central", "United", "Regional", "Women's & Children's",
        "Heart", "Cancer", "Community", "Eastern", "Sunrise", "Pacific", "Mercy", "Riverside"]
TYPES = {"hospital": ["Hospital", "Medical Centre"], "lab": ["Laboratory", "Diagnostics", "Pathology Lab"],
         "clinic": ["Clinic", "Polyclinic", "Health Centre"]}
SUFFIX = {"SG": "Pte Ltd", "MY": "Sdn Bhd", "TH": "Co., Ltd.", "VN": "JSC", "PH": "Inc."}
ABBR = [("National", "Natl"), ("University", "Univ"), ("Hospital", "Hosp"), ("Medical", "Med"),
        ("Laboratory", "Lab"), ("Centre", "Ctr"), ("General", "Gen"), ("Diagnostics", "Diag"),
        ("Specialist", "Spec"), ("International", "Intl")]

# Accounts that also appear in the hub's demo SAP B1 mirror, so both halves of the prototype agree
FIXED = [
    ("C10012", "National University Hospital", "SG", "hospital"),
    ("C10145", "Chiang Mai Medical Laboratory", "TH", "lab"),
    ("C10230", "Klang Valley Pathology Lab", "MY", "lab"),
    ("C10311", "Manila Central Clinical Lab", "PH", "lab"),
    ("C10402", "Hanoi Biomedical Centre", "VN", "lab"),
    ("C10233", "Penang Specialist Hospital", "MY", "hospital"),
]
FIXED_CODES = {f[0] for f in FIXED}


def tax_id(code, country):
    """Deterministic business registration / tax number per account (no RNG, so the rest of the data is unchanged)."""
    h = int(hashlib.md5(code.encode()).hexdigest(), 16)
    if country == "SG":
        return f"{198000000 + h % 30000000}{'ABCDEGHJKLMNRSWZ'[h % 16]}"     # UEN style
    if country == "MY":
        return f"{2000 + h % 24}01{h % 1000000:06d}"                          # SSM style
    if country == "TH":
        return f"0105{h % 10**9:09d}"
    if country == "VN":
        return f"03{h % 10**8:08d}"
    return f"{h % 1000:03d}-{h // 1000 % 1000:03d}-{h // 10**6 % 1000:03d}-000"  # PH TIN


def variant(name, country):
    """A plausible second spelling of the same customer, as a different person would key it."""
    words = name
    for full, short in ABBR:
        if full in words and rng.random() < 0.7:
            words = words.replace(full, short)
    if words == name or rng.random() < 0.6:
        words = words + " " + SUFFIX[country]
    if rng.random() < 0.25:
        words = words.upper()
    return words


def make_customers():
    used, out = set(), []
    for code, name, ctry, seg in FIXED:
        used.add(name)
        out.append({"cust": code, "name": name, "country": ctry, "segment": seg})
    target = {"SG": 30, "MY": 36, "TH": 34, "VN": 34, "PH": 34}
    n = 10500
    for ctry in COUNTRIES:
        have = sum(1 for c in out if c["country"] == ctry)
        while have < target[ctry]:
            seg = rng.choice(["hospital", "lab", "clinic"], p=[0.35, 0.40, 0.25])
            name = f"{rng.choice(CITIES[ctry])} {rng.choice(DESC)} {rng.choice(TYPES[seg])}"
            if name in used:
                continue
            used.add(name)
            n += int(rng.integers(3, 9))
            out.append({"cust": f"C{n}", "name": name, "country": ctry, "segment": str(seg)})
            have += 1
    return out


# ---------------------------------------------------------------- demand
def build():
    customers = make_customers()
    T = len(MONTHS)
    PLANTED = {"churners": [], "dups": [], "new_vn_b": []}

    size_by_seg = {"hospital": 1.6, "lab": 1.0, "clinic": 0.45}
    adopt = {  # chance a customer buys each product, by segment
        "hospital": {"A": 0.95, "B": 0.70, "C": 0.65},
        "lab": {"A": 0.85, "B": 0.60, "C": 0.45},
        "clinic": {"A": 0.80, "B": 0.25, "C": 0.30},
    }
    base_units = {"A": 22, "B": 7, "C": 30}

    # Planted stories
    # Malaysia: six established hospital/lab accounts drift away (e.g. to a competitor) from late 2025
    my_big = [c for c in customers if c["country"] == "MY" and c["segment"] != "clinic" and c["cust"] not in FIXED_CODES]
    churn_ids = [c["cust"] for c in rng.choice(my_big, 6, replace=False)]
    others = [c for c in customers if c["country"] != "MY" and c["cust"] not in churn_ids]
    churn_ids += [c["cust"] for c in rng.choice(others, 4, replace=False)]

    rows = []  # true demand by canonical customer
    for c in customers:
        seg, ctry = c["segment"], c["country"]
        size = size_by_seg[seg] * float(rng.lognormal(0, 0.45))
        c["size"] = size
        buys = {p: rng.random() < adopt[seg][p] for p in PRODUCTS}
        if ctry == "PH":                       # Product C under-sold in the Philippines
            buys["C"] = rng.random() < 0.18
        if not any(buys.values()):
            buys["A"] = True
        c["true_products"] = [p for p in PRODUCTS if buys[p]]

        start = 0
        if c["cust"] in FIXED_CODES:             # long-standing accounts in the hub's demo mirror
            pass
        elif ctry == "VN" and rng.random() < 0.30:   # wave of new Vietnamese labs onboarding
            start = int(rng.integers(26, 40))
            buys["B"] = True
            c["true_products"] = [p for p in PRODUCTS if buys[p]]
            PLANTED["new_vn_b"].append(c["cust"])
        elif rng.random() < 0.06:
            start = int(rng.integers(6, 38))
        c["start"] = start

        churn_from = None
        if c["cust"] in churn_ids:
            if ctry == "MY":
                size *= 1.8; c["size"] = size; buys["A"] = True
            churn_from = int(rng.integers(34, 38)) if ctry == "MY" else int(rng.integers(36, 40))
            floor = float(rng.choice([0.0, 0.15, 0.3]))
            c["churn"] = {"from": MONTHS[churn_from], "floor": floor}
            PLANTED["churners"].append(c["cust"])

        p_order = {"hospital": 0.93, "lab": 0.88, "clinic": 0.72}[seg]
        for p in PRODUCTS:
            if not buys[p]:
                continue
            trend = 0.0
            if ctry == "VN" and p == "B":
                trend = 0.022
            elif ctry == "SG" and p == "C":
                trend = 0.008
            elif ctry == "TH":
                trend = 0.004
            elif ctry == "PH" and p == "A":
                trend = 0.006
            for t in range(start, T):
                if rng.random() > p_order:
                    continue
                level = base_units[p] * size * (1 + trend) ** (t - 12)
                if churn_from is not None and t >= churn_from:
                    k = t - churn_from
                    level *= max(c["churn"]["floor"], 0.75 ** (k + 1))
                if start and t - start < 3:                 # ramp-up for new accounts
                    level *= 0.5 + 0.17 * (t - start)
                units = level * season_mult(ctry, MONTHS[t]) * float(rng.lognormal(0, 0.22))
                units = int(round(units))
                if units > 0:
                    rows.append({"canon": c["cust"], "country": ctry, "product": p, "month": MONTHS[t], "units": units})

    # ------------------------------------------------------------ duplicate records in SAP B1
    # 'split': the account was set up again by another entity, which books that entity's product line on it
    # 'switch': the account was re-created later (rename, new address) and orders moved to the new record
    records = []
    for c in customers:
        entity = ENTITY_FOR[c["true_products"][0]]
        records.append({"code": c["cust"], "name": c["name"], "country": c["country"], "entity": entity,
                        "segment": c["segment"], "canon": c["cust"]})
    route = {}  # (canon, product) -> record code ; (canon, 'switch') -> (code, from_idx)
    eligible = [c for c in customers if len(c["true_products"]) >= 2 and c["start"] == 0 and c["cust"] not in churn_ids]
    split = rng.choice(eligible, 20, replace=False)
    next_code = 20001
    for c in split:
        p2 = c["true_products"][1]
        code = f"C{next_code}"; next_code += int(rng.integers(2, 6))
        records.append({"code": code, "name": variant(c["name"], c["country"]), "country": c["country"],
                        "entity": ENTITY_FOR[p2], "segment": c["segment"], "canon": c["cust"]})
        for p in c["true_products"][1:]:
            route[(c["cust"], p)] = code
        PLANTED["dups"].append({"canon": c["cust"], "dup": code, "kind": "split"})
    pool = [c for c in customers if c["start"] == 0 and c["cust"] not in churn_ids and c not in list(split)]
    for c in rng.choice(pool, 9, replace=False):
        code = f"C{next_code}"; next_code += int(rng.integers(2, 6))
        frm = int(rng.integers(36, 41))
        records.append({"code": code, "name": variant(c["name"], c["country"]), "country": c["country"],
                        "entity": ENTITY_FOR[c["true_products"][0]], "segment": c["segment"], "canon": c["cust"]})
        route[(c["cust"], "switch")] = (code, frm)
        PLANTED["dups"].append({"canon": c["cust"], "dup": code, "kind": "switch", "from": MONTHS[frm]})
    # Two duplicates written as acronyms: name matching alone will not catch these
    for canon, acr in (("C10012", "NUH"),):
        code = f"C{next_code}"; next_code += 3
        records.append({"code": code, "name": acr, "country": "SG", "entity": "QTS", "segment": "hospital", "canon": canon})
        route[(canon, "B")] = code
        PLANTED["dups"].append({"canon": canon, "dup": code, "kind": "split", "note": "acronym"})

    # Tax IDs: every account has one. Duplicate records copy it, except about half of the older duplicates,
    # which were keyed without it (legacy). The acronym duplicate keeps it, so a tax-ID check can catch it.
    for r in records:
        canon_ctry = next(c["country"] for c in customers if c["cust"] == r["canon"])
        tid = tax_id(r["canon"], canon_ctry)
        if r["code"] != r["canon"] and r["name"] != "NUH" and int(r["code"][1:]) % 2 == 1:
            tid = ""
        r["tax_id"] = tid

    orders = []
    for r in rows:
        code = r["canon"]
        if (r["canon"], r["product"]) in route:
            code = route[(r["canon"], r["product"])]
        sw = route.get((r["canon"], "switch"))
        if sw and IDX[r["month"]] >= sw[1]:
            code = sw[0]
        orders.append({"record": code, **r, "value": round(r["units"] * PRICE[r["product"]], 2)})

    # ------------------------------------------------------------ inbound traffic by type
    # POs = one per customer per month with an order; enquiries and MDM setup requests modelled separately.
    inbound = []
    po_count = {}
    for o in orders:
        po_count.setdefault((o["country"], o["month"]), set()).add(o["record"])
    for ctry in COUNTRIES:
        for m in MONTHS:
            pos = len(po_count.get((ctry, m), ()))
            enq = int(rng.poisson(0.42 * pos + 3))
            setup = int(rng.poisson(5 + (3 if ctry == "VN" and IDX[m] >= 26 else 0)))
            inbound.append({"country": ctry, "month": m, "purchase_orders": pos, "enquiries": enq, "mdm_setup_requests": setup})

    # POs from customers who were not yet set up in SAP B1: the first order of every new account
    blocked = []
    for c in customers:
        if c["start"]:
            first = [o for o in orders if o["canon"] == c["cust"] and IDX[o["month"]] == c["start"]]
            if first:
                wait = float(np.clip(rng.lognormal(np.log(13), 0.35), 6, 30))  # email-era setup time, days
                blocked.append({"canon": c["cust"], "country": c["country"], "month": MONTHS[c["start"]],
                                "value": round(sum(o["value"] for o in first), 2), "wait_days": round(wait, 1)})

    # Orders from prospects who are not yet customers in SAP B1 (they wait for MDM setup)
    for ctry in COUNTRIES:
        for m in MONTHS:
            for _ in range(int(rng.poisson(1.1 if ctry != "VN" else 1.8))):
                wait = float(np.clip(rng.lognormal(np.log(13), 0.35), 5, 30))
                blocked.append({"canon": "prospect", "country": ctry, "month": m,
                                "value": round(float(rng.lognormal(np.log(2600), 0.5)), 2), "wait_days": round(wait, 1)})

    os.makedirs(OUT, exist_ok=True)

    def dump(name, data):
        with open(os.path.join(OUT, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader(); w.writerows(data)

    dump("customer_records.csv", [{k: r[k] for k in ("code", "name", "country", "entity", "segment", "tax_id")} for r in records])
    dump("orders.csv", [{k: o[k] for k in ("record", "country", "product", "month", "units", "value")} for o in orders])
    dump("inbound_monthly.csv", inbound)
    dump("orders_waiting_on_setup.csv", blocked)
    # Ground truth: kept apart so the analysis can be scored against it, never read by the cleanup itself
    with open(os.path.join(OUT, "ground_truth.json"), "w") as f:
        json.dump({"record_to_account": {r["code"]: r["canon"] for r in records}, **PLANTED,
                   "churn_detail": {c["cust"]: c["churn"] for c in customers if "churn" in c}}, f, indent=1)
    print(f"{len(customers)} accounts, {len(records)} SAP records, {len(orders)} order lines, "
          f"{len(PLANTED['dups'])} planted duplicates, {len(PLANTED['churners'])} planted drop-offs")


if __name__ == "__main__":
    build()
