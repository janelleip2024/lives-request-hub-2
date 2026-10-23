"""
Regional business view for the Lives Group case: reads analytics/data/*.csv and writes
analytics/regional.json, which the prototype's "Regional view" tab renders.

Steps
1. Clean master data: find customer records that are the same account (same fuzzy matcher as the request form).
2. Regional volumes and growth for Products A, B, C x 5 countries over Oct 2025 - Sep 2026.
3. Forecast backtest: today's rolling 6- and 12-month averages vs a seasonal model and a
   gradient-boosted model that knows each country's holiday and budget calendar.
4. Account-level signals (drop-off, cross-sell), computed before and after the cleanup, so the effect
   of duplicate records on what Sales is told to do is visible.
5. Purchase orders vs enquiries vs MDM setup requests, and orders that waited on customer setup.

Run: python3 analytics/analyze.py   (after generate_data.py)
"""
import json
import os
import re
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from generate_data import COUNTRIES, PRODUCTS, MONTHS, PRICE, calendar

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

WINDOW = MONTHS[-12:]            # Oct 2025 - Sep 2026: the stated 12-month period
PRIOR = MONTHS[-24:-12]          # Oct 2024 - Sep 2025
BACKTEST = MONTHS[-12:]          # Oct 2025 - Sep 2026: each month forecast using only data before it
FUTURE = ["2026-10", "2026-11", "2026-12"]
CNAME = {"SG": "Singapore", "MY": "Malaysia", "TH": "Thailand", "VN": "Vietnam", "PH": "Philippines"}

records = pd.read_csv(os.path.join(DATA, "customer_records.csv"), dtype={"tax_id": str}).fillna({"tax_id": ""})
orders = pd.read_csv(os.path.join(DATA, "orders.csv"))
inbound = pd.read_csv(os.path.join(DATA, "inbound_monthly.csv"))
waiting = pd.read_csv(os.path.join(DATA, "orders_waiting_on_setup.csv"))
truth = json.load(open(os.path.join(DATA, "ground_truth.json")))
true_acct = truth["record_to_account"]          # used ONLY to score results, never to make them
churners = set(truth["churners"])

# ============================================================ 1. duplicate matching
# Same normalisation and bigram (Dice) similarity as the request form in app.html
ABBR = {"natl": "national", "nat": "national", "univ": "university", "uni": "university", "hosp": "hospital",
        "med": "medical", "ctr": "centre", "center": "centre", "lab": "laboratory", "labs": "laboratory",
        "laboratories": "laboratory", "intl": "international", "gen": "general", "diag": "diagnostics",
        "diagnostic": "diagnostics", "spec": "specialist"}
STOP = {"pte", "ltd", "sdn", "bhd", "co", "inc", "the", "company", "limited", "plc", "jsc", "corp",
        "corporation", "llc", "tbk", "pt", "of"}


def norm(s):
    words = re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip().split(" ")
    return " ".join(ABBR.get(w, w) for w in words if w and ABBR.get(w, w) not in STOP and w not in STOP)


def dice(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    def grams(s):
        g = defaultdict(int)
        for i in range(len(s) - 1):
            g[s[i:i + 2]] += 1
        return g
    A, B = grams(a), grams(b)
    hit = sum(min(v, B[k]) for k, v in A.items() if k in B)
    return 2 * hit / (sum(A.values()) + sum(B.values()))


MERGE_AT = 0.92   # auto-suggest a merge at this score; MDM confirms in the hub
parent = {c: c for c in records.code}


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


pairs = []
for ctry, grp in records.groupby("country"):                 # only compare records in the same country
    rs = grp.to_dict("records")
    for i in range(len(rs)):
        for j in range(i + 1, len(rs)):
            s = dice(rs[i]["name"], rs[j]["name"])
            if s >= MERGE_AT:
                pairs.append((rs[i]["code"], rs[j]["code"], s))
                parent[find(rs[j]["code"])] = find(rs[i]["code"])

# Second pass: exact tax-ID match catches what names can't (acronyms, renamed entities)
by_name = {tuple(sorted((a, b))) for a, b, _ in pairs}
tax_pairs = []
for tid, grp in records[records.tax_id != ""].groupby("tax_id"):
    codes = list(grp.code)
    for c in codes[1:]:
        if tuple(sorted((codes[0], c))) not in by_name and find(c) != find(codes[0]):
            tax_pairs.append((codes[0], c))
        parent[find(c)] = find(codes[0])

# Account id = oldest code in the cluster (lowest number)
clusters = defaultdict(list)
for c in records.code:
    clusters[find(c)].append(c)
acct_of = {}
for members in clusters.values():
    keep = sorted(members, key=lambda c: int(c[1:]))[0]
    for m in members:
        acct_of[m] = keep
name_of = dict(zip(records.code, records.name))
seg_of = dict(zip(records.code, records.segment))
ctry_of = dict(zip(records.code, records.country))

# Score against the planted truth
true_pairs = {tuple(sorted((r, true_acct[r]))) for r in records.code if true_acct[r] != r}
found_pairs = {tuple(sorted((r, acct_of[r]))) for r in records.code if acct_of[r] != r}
caught = true_pairs & found_pairs
false_merge = found_pairs - true_pairs
missed = true_pairs - found_pairs
dup_clusters = [sorted(m, key=lambda c: int(c[1:])) for m in clusters.values() if len(m) > 1]
dedup = {
    "records": int(len(records)),
    "accounts_after": int(len(set(acct_of.values()))),
    "true_accounts": int(len(set(true_acct.values()))),
    "planted": len(true_pairs), "caught": len(caught), "false_merges": len(false_merge), "missed": len(missed),
    "missed_examples": [{"record": a if a != true_acct[a] else b, "name": name_of[a if a != true_acct[a] else b],
                         "is_really": name_of[true_acct[a if a != true_acct[a] else b]]} for a, b in sorted(missed)],
    "threshold": MERGE_AT,
    "by_tax": [{"record": b, "name": name_of[b], "matches": a, "matches_name": name_of[a]} for a, b in tax_pairs],
    "examples": [{"keep": m[0], "keep_name": name_of[m[0]], "others": [{"code": x, "name": name_of[x],
                  "score": round(dice(name_of[m[0]], name_of[x]), 2)} for x in m[1:]]} for m in dup_clusters[:6]],
}

orders["account"] = orders.record.map(acct_of)

# ============================================================ 2. regional volumes and growth
def units(df, months):
    return df[df.month.isin(months)].units.sum()


cells = []
for ctry in COUNTRIES:
    for p in PRODUCTS:
        d = orders[(orders.country == ctry) & (orders["product"] == p)]
        cur, prev = units(d, WINDOW), units(d, PRIOR)
        cur3, prev3 = units(d, MONTHS[-3:]), units(d, MONTHS[-15:-12])
        cells.append({
            "country": ctry, "product": p,
            "units": int(cur), "value": round(float(d[d.month.isin(WINDOW)].value.sum())),
            "growth": round((cur - prev) / prev, 4) if prev else None,
            "growth_3m": round((cur3 - prev3) / prev3, 4) if prev3 else None,
            "buyers": int(d[d.month.isin(WINDOW)].account.nunique()),
        })

monthly = orders.groupby(["country", "product", "month"]).units.sum().unstack("month").reindex(columns=MONTHS).fillna(0)
tot_cur = orders[orders.month.isin(WINDOW)]
tot_prev = orders[orders.month.isin(PRIOR)]
regional = {
    "units": int(tot_cur.units.sum()), "value": round(float(tot_cur.value.sum())),
    "growth": round(tot_cur.units.sum() / tot_prev.units.sum() - 1, 4),
    "value_growth": round(tot_cur.value.sum() / tot_prev.value.sum() - 1, 4),
    "by_product": {p: {"units": int(tot_cur[tot_cur["product"] == p].units.sum()),
                       "growth": round(tot_cur[tot_cur["product"] == p].units.sum() / tot_prev[tot_prev["product"] == p].units.sum() - 1, 4)} for p in PRODUCTS},
    "by_country": {c: {"value": round(float(tot_cur[tot_cur.country == c].value.sum())),
                       "growth": round(tot_cur[tot_cur.country == c].value.sum() / tot_prev[tot_prev.country == c].value.sum() - 1, 4)} for c in COUNTRIES},
}

# ============================================================ 3. forecasting backtest
CAL_KEYS = list(calendar("SG", "2024-01").keys())


def features(hist, ctry, p, month):
    """Features for forecasting `month` from `hist` (values for all months strictly before it)."""
    h = np.asarray(hist, float)
    L = h[-12:].mean() or 1.0
    f = {"lag1": h[-1] / L, "lag2": h[-2] / L, "lag3": h[-3] / L, "lag12": h[-12] / L,
         "r3": h[-3:].mean() / L, "r6": h[-6:].mean() / L, "month": int(month[5:])}
    cal = calendar(ctry, month)
    lastyear = MONTHS[MONTHS.index(month) - 12] if month in MONTHS else f"{int(month[:4]) - 1}{month[4:]}"
    cal_ly = calendar(ctry, lastyear)
    for k in CAL_KEYS:
        f[k] = cal[k]
        f[k + "_ly"] = cal_ly[k]          # was this effect in the same month last year? (moving holidays)
    for c in COUNTRIES:
        f["c_" + c] = int(ctry == c)
    for q in PRODUCTS:
        f["p_" + q] = int(p == q)
    return f, L


def gbm_model():
    return GradientBoostingRegressor(n_estimators=400, max_depth=3, learning_rate=0.03, subsample=0.8,
                                     min_samples_leaf=4, loss="huber", random_state=7)


def train_rows(upto_idx):
    X, y = [], []
    for (ctry, p), row in monthly.iterrows():
        v = row.values
        for t in range(12, upto_idx):
            f, L = features(v[:t], ctry, p, MONTHS[t])
            X.append(f); y.append(v[t] / L)
    return pd.DataFrame(X), np.array(y)


def holt_winters(hist):
    try:
        m = ExponentialSmoothing(np.asarray(hist, float) + 1, trend="add", damped_trend=True,
                                 seasonal="mul", seasonal_periods=12, initialization_method="estimated").fit()
        return float(m.forecast(1)[0]) - 1
    except Exception:
        return float(np.mean(hist[-12:]))


METHODS = ["avg6", "avg12", "hw", "gbm", "ens"]
preds = {m: {} for m in METHODS}
for month in BACKTEST:
    t = MONTHS.index(month)
    X, y = train_rows(t)
    model = gbm_model().fit(X, y)
    for (ctry, p), row in monthly.iterrows():
        hist = row.values[:t]
        f, L = features(hist, ctry, p, month)
        g = float(model.predict(pd.DataFrame([f])[X.columns])[0]) * L
        hw = holt_winters(hist)
        key = (ctry, p, month)
        preds["avg6"][key] = hist[-6:].mean()
        preds["avg12"][key] = hist[-12:].mean()
        preds["hw"][key] = hw
        preds["gbm"][key] = g
        preds["ens"][key] = 0.5 * g + 0.5 * hw


def wape(method, keys):
    a = sum(monthly.loc[(c, p), m] for c, p, m in keys)
    e = sum(abs(monthly.loc[(c, p), m] - preds[method][(c, p, m)]) for c, p, m in keys)
    return e / a


all_keys = list(preds["avg6"].keys())
accuracy = {m: round(wape(m, all_keys), 4) for m in METHODS}
per_series = {}
for ctry in COUNTRIES:
    for p in PRODUCTS:
        ks = [(ctry, p, m) for m in BACKTEST]
        per_series[f"{ctry}-{p}"] = {m: round(wape(m, ks), 4) for m in METHODS}
best_baseline = min(("avg6", "avg12"), key=lambda m: accuracy[m])
wins = sum(1 for s in per_series.values() if s["gbm"] < min(s["avg6"], s["avg12"]))

# Final model on everything up to Sep 2026, then forecast Oct-Dec recursively
X, y = train_rows(len(MONTHS))
final = gbm_model().fit(X, y)
imp = dict(zip(X.columns, final.feature_importances_))
groups = {
    "Recent months' orders": [k for k in imp if k in ("lag1", "lag2", "lag3", "r3", "r6")],
    "Same month last year": ["lag12"],
    "Holiday and budget calendar": [k for k in imp if k in CAL_KEYS or k.endswith("_ly")],
    "Time of year": ["month"],
    "Country and product": [k for k in imp if k.startswith("c_") or k.startswith("p_")],
}
importance = sorted(({"driver": g, "share": round(float(sum(imp[k] for k in ks)), 3)} for g, ks in groups.items()),
                    key=lambda d: -d["share"])

future = {}
for (ctry, p), row in monthly.iterrows():
    hist = list(row.values)
    out = []
    for month in FUTURE:
        f, L = features(hist, ctry, p, month)
        v = max(0.0, float(final.predict(pd.DataFrame([f])[X.columns])[0]) * L)
        out.append(round(v, 1)); hist.append(v)
    future[f"{ctry}-{p}"] = {"model": out, "avg12": [round(float(np.mean(row.values[-12:])), 1)] * 3}

series = {}
for (ctry, p), row in monthly.iterrows():
    k = f"{ctry}-{p}"
    series[k] = {
        "actual": [int(x) for x in row.values[-24:]],                     # Oct 2024 - Sep 2026
        "bt": {m: [round(float(preds[m][(ctry, p, mo)]), 1) for mo in BACKTEST] for m in ("avg6", "avg12", "gbm")},
        "future": future[k]["model"],
        "wape": per_series[k],
    }

# ============================================================ 4. account-level signals, before vs after cleanup
def entity_monthly(col):
    v = orders.groupby([col, "month"]).value.sum().unstack("month").reindex(columns=MONTHS).fillna(0)
    return v


def dropoffs(col):
    v = entity_monthly(col)
    prior = v[MONTHS[-24:-12]].mean(axis=1)     # their monthly average a year earlier (Oct 2024 - Sep 2025)
    recent = v[MONTHS[-3:]].mean(axis=1)        # Jul - Sep 2026
    hit = v[(prior >= 1500) & (recent < 0.5 * prior)]
    out = []
    for code in hit.index:
        real = true_acct[code] in churners
        prods = orders[(orders[col] == code) & orders.month.isin(MONTHS[-24:-12])]["product"].unique().tolist()
        out.append({"code": code, "name": name_of[code], "country": ctry_of[code], "products": sorted(prods),
                    "prior_month": round(float(prior[code])), "recent_month": round(float(recent[code])),
                    "at_risk_year": round(float((prior[code] - recent[code]) * 12)), "real": bool(real),
                    "trend": [round(float(x)) for x in v.loc[code, MONTHS[-12:]].values]})
    return sorted(out, key=lambda d: -d["at_risk_year"])


def ghosts(col):
    """Codes whose first order falls in the last 12 months although the account has bought for longer."""
    first = orders.groupby(col).month.min()
    acct_first = orders.groupby(orders[col].map(true_acct)).month.min()
    newish = first[first >= WINDOW[0]]
    return int(sum(1 for code, m in newish.items() if acct_first[true_acct[code]] < WINDOW[0]))


def cross_sell(col):
    w = orders[orders.month.isin(WINDOW)]
    mat = w.groupby([col, "product"]).value.sum().unstack("product").reindex(columns=PRODUCTS).fillna(0)
    true_buys = orders[orders.month.isin(WINDOW)].assign(acc=lambda d: d.record.map(true_acct)) \
        .groupby("acc")["product"].unique().apply(set).to_dict()
    gaps = []
    for code, row in mat.iterrows():
        have = {p for p in PRODUCTS if row[p] > 0}
        peers = mat[[seg_of[c] == seg_of[code] for c in mat.index]]
        peers = peers[(peers[list(have)] > 0).all(axis=1)] if have else peers
        peers = peers.drop(index=code, errors="ignore")
        if len(peers) < 8:
            continue
        for p in PRODUCTS:
            if p in have:
                continue
            buyers = peers[peers[p] > 0]
            prop = len(buyers) / len(peers)
            if prop < 0.5:
                continue
            own = row[list(have)].sum() if have else 0
            peer_own = peers.loc[buyers.index, list(have)].sum(axis=1).median() if have else 1
            scale = float(np.clip(own / peer_own, 0.4, 2.0)) if peer_own else 1.0
            est = prop * float(buyers[p].median()) * scale
            false = p in true_buys.get(true_acct[code], set())
            gaps.append({"code": code, "name": name_of[code], "country": ctry_of[code], "segment": seg_of[code],
                         "product": p, "peers": int(len(peers)), "peer_share": round(prop, 2),
                         "est_year": round(est), "false": bool(false), "buys": sorted(have)})
    return sorted(gaps, key=lambda d: -d["est_year"])


before = {"drop": dropoffs("record"), "xs": cross_sell("record"), "ghost": ghosts("record"),
          "customers": int(orders[orders.month.isin(WINDOW)].record.nunique())}
after = {"drop": dropoffs("account"), "xs": cross_sell("account"), "ghost": ghosts("account"),
         "customers": int(orders[orders.month.isin(WINDOW)].account.nunique())}


def summarise(x):
    return {"customers": x["customers"], "drop_alerts": len(x["drop"]), "drop_false": sum(not d["real"] for d in x["drop"]),
            "xs_gaps": len(x["xs"]), "xs_false": sum(d["false"] for d in x["xs"]),
            "xs_value": round(sum(d["est_year"] for d in x["xs"] if not d["false"])),
            "xs_value_all": round(sum(d["est_year"] for d in x["xs"])), "ghost_new": x["ghost"]}


cleanup = {"before": summarise(before), "after": summarise(after)}
churn_caught = len({true_acct[d["code"]] for d in after["drop"] if d["real"]})

# ============================================================ 5. orders vs enquiries vs setup requests
inb = inbound[inbound.month.isin(WINDOW)]
traffic = {
    "by_country": {c: {"po": int(g.purchase_orders.sum()), "enq": int(g.enquiries.sum()), "setup": int(g.mdm_setup_requests.sum())}
                   for c, g in inb.groupby("country")},
    "monthly": {k: [int(x) for x in inb.groupby("month")[col].sum().reindex(WINDOW).values]
                for k, col in (("po", "purchase_orders"), ("enq", "enquiries"), ("setup", "mdm_setup_requests"))},
}
wt = waiting[waiting.month.isin(WINDOW)]
HUB_DAYS = 4.0
traffic["waiting"] = {
    "orders": int(len(wt)), "value": round(float(wt.value.sum())), "avg_wait": round(float(wt.wait_days.mean()), 1),
    "hub_target": HUB_DAYS, "by_country": {c: int(n) for c, n in wt.groupby("country").size().items()},
}

# ============================================================ actions
cell_by = {(c["country"], c["product"]): c for c in cells}
grow = max(cells, key=lambda c: c["growth"])
fall = min(cells, key=lambda c: c["growth"])
risk = sum(d["at_risk_year"] for d in after["drop"])
real_xs = [d for d in after["xs"] if not d["false"]]
xs_by_c = defaultdict(float)
for d in real_xs:
    xs_by_c[(d["country"], d["product"])] += d["est_year"]
top_xs = max(xs_by_c.items(), key=lambda kv: kv[1])
drop_c = defaultdict(float)
for d in after["drop"]:
    drop_c[d["country"]] += d["at_risk_year"]
risk_c = max(drop_c, key=drop_c.get)
fall_drop = [d for d in after["drop"] if d["country"] == risk_c]
risk_cells = sorted([c for c in cells if c["country"] == risk_c], key=lambda c: c["growth"])
nxt = {p: round(sum(future[f"{c}-{p}"]["model"][0] for c in COUNTRIES)) for p in PRODUCTS}


def pct(x):
    return f"{x * 100:+.0f}%"


actions = [
    {"who": "Regional Sales, " + CNAME[risk_c], "title": f"Win back {len(fall_drop)} {CNAME[risk_c]} accounts before year-end",
     "body": f"{CNAME[risk_c]} is the only country shrinking: Product {risk_cells[0]['product']} {pct(risk_cells[0]['growth'])}, "
             f"Product {risk_cells[1]['product']} {pct(risk_cells[1]['growth'])} on last year. "
             f"{len(fall_drop)} accounts there now order less than half of what they did a year ago. "
             f"Across the region, {len(after['drop'])} accounts are on the drop-off list, about SGD {risk / 1000:,.0f}k a year at risk.",
     "metric": f"SGD {risk / 1000:,.0f}k/yr at risk"},
    {"who": "Supply chain and QTS", "title": f"Plan stock for Product {grow['product']} growth in {CNAME[grow['country']]}",
     "body": f"Product {grow['product']} in {CNAME[grow['country']]} is {pct(grow['growth'])} year on year, driven by newly onboarded labs. "
             f"A flat 12-month average under-forecasts a growing series every month. Use the model's October forecast "
             f"({round(future[grow['country'] + '-' + grow['product']]['model'][0])} units, vs {round(future[grow['country'] + '-' + grow['product']]['avg12'][0])} from the 12-month average) for replenishment.",
     "metric": f"{pct(grow['growth'])} YoY"},
    {"who": "Product managers", "title": f"Cross-sell Product {top_xs[0][1]} in {CNAME[top_xs[0][0]]}",
     "body": f"{len(real_xs)} account-product gaps where most similar customers already buy the product. "
             f"The largest pocket is Product {top_xs[0][1]} in {CNAME[top_xs[0][0]]} (SGD {top_xs[1] / 1000:,.0f}k a year). "
             f"The call list below is ranked by estimated value.",
     "metric": f"SGD {sum(d['est_year'] for d in real_xs) / 1000:,.0f}k/yr potential"},
    {"who": "MDM team", "title": "Merge the duplicate customer records first",
     "body": f"{dedup['caught']} duplicate records found and {dedup['records'] - dedup['accounts_after']} merges suggested. "
             f"Before merging, {cleanup['before']['drop_false']} of {cleanup['before']['drop_alerts']} drop-off alerts and "
             f"{cleanup['before']['xs_false']} cross-sell leads were false: the customer was still buying under another record.",
     "metric": f"{cleanup['before']['drop_false'] + cleanup['before']['xs_false']} false leads removed"},
]

# Before/after drop-off lists for the cleanup toggle: which pre-merge alerts disappear, and why
after_codes = {d["code"] for d in after["drop"]}
cluster_of = {c: members for members in clusters.values() for c in members}
last_order = orders.groupby("record").month.max().to_dict()
for d in before["drop"]:
    d["survives"] = acct_of[d["code"]] in after_codes
    others = [x for x in cluster_of[d["code"]] if x != d["code"]]
    active = [x for x in others if last_order.get(x, "") >= MONTHS[-3]]
    d["explain"] = (f"Still ordering as \"{name_of[active[0]]}\" ({active[0]})" if active
                    else f"Same customer as {', '.join(name_of[x] for x in others)}" if others else "")

# Commercial history per customer code, so the request form can say what a duplicate would split
w12 = orders[orders.month.isin(WINDOW)]
accounts = {}
for code, g in orders.groupby("account"):
    g12 = w12[w12.account == code]
    accounts[code] = {"value": round(float(g12.value.sum())), "products": sorted(g12["product"].unique().tolist()),
                      "last": g.month.max(), "records": len(clusters[find(code)]), "since": g.month.min()}
record_account = {r: a for r, a in acct_of.items() if r != a}

out = {
    "generated": pd.Timestamp.now(tz="Asia/Singapore").strftime("%d %b %Y"),
    "simulated": True,
    "period": {"from": WINDOW[0], "to": WINDOW[-1], "months": WINDOW, "chart_months": MONTHS[-24:],
               "backtest": BACKTEST, "future": FUTURE},
    "growth_definition": "Units ordered Oct 2025 - Sep 2026 vs the same 12 months a year earlier (Oct 2024 - Sep 2025). "
                         "Comparing the same months cancels out holidays and budget cycles. "
                         "The 3-month figure compares Jul - Sep 2026 with Jul - Sep 2025.",
    "price": PRICE, "countries": CNAME,
    "regional": regional, "cells": cells, "series": series,
    "accuracy": accuracy, "best_baseline": best_baseline, "wins": wins, "series_count": len(per_series),
    "importance": importance, "next_month": nxt,
    "dedup": dedup, "cleanup": cleanup, "churn_caught": churn_caught, "churn_planted": len(churners),
    "dropoffs": after["drop"], "dropoffs_before": before["drop"],
    "accounts": accounts, "record_account": record_account,
    "cross_sell": real_xs[:12],
    "traffic": traffic, "actions": actions,
    "assumptions": {"xs_conversion": 0.1, "forecast_days_per_country_month": 1, "hub_setup_days": HUB_DAYS,
                    "drop_rule": "Last 3 months (Jul - Sep 2026) average below half of the same account's monthly average a year earlier, "
                                 "for accounts that bought at least SGD 1.5k a month.",
                    "xs_rule": "Peers are customers in the same segment (hospital, lab, clinic) that buy everything this account buys. "
                               "A gap is flagged when at least half of those peers also buy the missing product; value = share of peers "
                               "x their median annual spend on it, scaled to the account's size."},
}
with open(os.path.join(HERE, "regional.json"), "w") as f:
    json.dump(out, f, separators=(",", ":"))

print(json.dumps({"accuracy": accuracy, "wins": wins, "dedup": {k: dedup[k] for k in ("records", "accounts_after", "planted", "caught", "false_merges", "missed")},
                  "cleanup": cleanup, "churn_caught": churn_caught, "growth": [(c["country"], c["product"], c["growth"]) for c in cells],
                  "importance": importance, "traffic_wait": traffic["waiting"], "regional": regional}, indent=1, default=str))
for a in actions:
    print("-", a["title"], "|", a["metric"])
print("size", os.path.getsize(os.path.join(HERE, "regional.json")))
