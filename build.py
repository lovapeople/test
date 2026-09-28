"""
SharkNinja AU weekly snapshot builder.

Pulls this month's data from Salesforce using the same filters as the
"Weekly Snapshot SharkAU" report, then fills template.html and writes site/index.html.

  Customer = SharkNinja AU, Business Unit = Demo, Actual Start Date = every Mon-Sun week (Sydney)
  that ends in the same month as last week, e.g. Sep 2026 = WE 6, 13, 20 and 27 Sep
  Units = "No of Sales", Revenue = "Value", only the retailers listed in RETAILERS

Environment variables (GitHub secrets):
  SF_INSTANCE_URL   e.g. https://meshcircle.my.salesforce.com
  SF_CLIENT_ID      Connected App consumer key
  SF_CLIENT_SECRET  Connected App consumer secret

Optional: WEEK_ENDING=2026-09-27 to rebuild the month up to a specific week.
Test without Salesforce: python build.py --fixture fixture.json
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
API = "v66.0"
CUSTOMER = "SharkNinja AU"
BUSINESS_UNIT = "Demo"
RETAILERS = ["Harvey Norman", "The Good Guys"]   # other retailers (e.g. Bing Lee) are left out
CATS = ["Coffee Machine", "Cooking", "Floor Care", "Frozen", "Beauty", "Other Products"]


def month_range():
    """Every Mon-Sun week that ends in the same month as the latest week, up to that week."""
    if os.environ.get("WEEK_ENDING"):
        end = dt.date.fromisoformat(os.environ["WEEK_ENDING"])
    else:
        today = dt.datetime.now(ZoneInfo("Australia/Sydney")).date()
        end = today - dt.timedelta(days=today.weekday() + 1)   # last Sunday
    first = end.replace(day=1)
    first_sunday = first + dt.timedelta(days=(6 - first.weekday()) % 7)
    return first_sunday - dt.timedelta(days=6), end


def week_label(d):
    sun = d + dt.timedelta(days=6 - d.weekday())
    return f"WE {sun.day} {sun.strftime('%b')}"


def sf_query_all(queries):
    import requests
    base = os.environ["SF_INSTANCE_URL"].strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    tok = requests.post(f"{base}/services/oauth2/token", data={
        "grant_type": "client_credentials",
        "client_id": os.environ["SF_CLIENT_ID"],
        "client_secret": os.environ["SF_CLIENT_SECRET"]}, timeout=30)
    if tok.status_code != 200:
        sys.exit(f"Salesforce login failed ({tok.status_code}): {tok.text}")
    hdr = {"Authorization": "Bearer " + tok.json()["access_token"]}
    results = []
    for q in queries:
        url, params, rows = f"{base}/services/data/{API}/query", {"q": q}, []
        while url:
            r = requests.get(url, headers=hdr, params=params, timeout=60)
            if r.status_code != 200:
                sys.exit(f"Salesforce query failed ({r.status_code}): {r.text}")
            body = r.json(); rows += body["records"]
            url = base + body["nextRecordsUrl"] if body.get("nextRecordsUrl") else None
            params = None
        results.append(rows)
    return results


def rel(rec, path):
    for p in path.split("."):
        rec = (rec or {}).get(p)
    return rec


def title_store(name):
    t = " ".join(w.capitalize() for w in name.lower().split())
    return t.replace("O'connor", "O'Connor").replace("Mcg", "McG")


def fmt_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b %Y')}"


def main():
    start, end = month_range()
    where = (f"RB_Customer__r.Name = '{CUSTOMER}' AND RB_Business_Unit__r.Name = '{BUSINESS_UNIT}' "
             f"AND RB_Actual_Start_Date__c >= {start} AND RB_Actual_Start_Date__c <= {end}")
    q_ts = ("SELECT Id, State__c, RB_Customer_Store__r.Name, Employee_Name__r.Name, RB_Actual_Start_Date__c, "
            f"Shift_Duration_Hours__c, Retailer__c FROM Timesheet__c WHERE {where}")
    q_ps = ("SELECT Timesheet__c, RB_Customer_Product__r.Name, Product_Family__c, Product_Category__c, "
            f"Product_Group1__c, noofsales__c, Value__c FROM Product_Sale__c WHERE "
            + where.replace("RB_", "Timesheet__r.RB_"))

    if "--fixture" in sys.argv:
        fx = json.loads(Path(sys.argv[sys.argv.index("--fixture") + 1]).read_text())
        timesheets, sales = fx["timesheets"], fx["sales"]
        start, end = dt.date.fromisoformat(fx["start"]), dt.date.fromisoformat(fx["end"])
    else:
        timesheets, sales = sf_query_all([q_ts, q_ps])

    ts = {}
    skipped = []
    for t in timesheets:
        ret = t.get("Retailer__c") or ""
        store = title_store(rel(t, "RB_Customer_Store__r.Name") or "Unknown")
        if ret not in RETAILERS:
            skipped.append(f"{store} {t['RB_Actual_Start_Date__c']}")
            continue
        ts[t["Id"][:15]] = dict(state=t.get("State__c") or "", store=store,
                               emp=rel(t, "Employee_Name__r.Name") or "Unknown",
                               date=t["RB_Actual_Start_Date__c"], hrs=float(t.get("Shift_Duration_Hours__c") or 0),
                               ret=ret, lines=[])
    if not ts:
        sys.exit(f"No Demo shifts found for {start} to {end}; nothing published.")
    for p in sales:
        k = p["Timesheet__c"][:15]
        if k not in ts:
            continue
        cat = p.get("Product_Family__c") if p.get("Product_Family__c") in CATS else "Other Products"
        ts[k]["lines"].append(dict(n=rel(p, "RB_Customer_Product__r.Name") or "Unknown product", cat=cat,
                                   sub=p.get("Product_Category__c") or cat, grp=p.get("Product_Group1__c") or "Other",
                                   u=int(p.get("noofsales__c") or 0), v=float(p.get("Value__c") or 0)))

    dates_iso = sorted({t["date"] for t in ts.values()})
    dates = [fmt_date(d) for d in dates_iso]
    dmap = dict(zip(dates_iso, dates))

    R = []
    for t in ts.values():
        cu = [0] * 6
        for l in t["lines"]:
            cu[CATS.index(l["cat"])] += l["u"]
        R.append([t["state"], t["store"], t["emp"], dmap[t["date"]], 1, t["hrs"],
                  sum(l["u"] for l in t["lines"]), round(sum(l["v"] for l in t["lines"]), 2), t["ret"]] + cu)
    R.sort(key=lambda r: (dates.index(r[3]), r[1], r[2]))

    stores = sorted({t["store"] for t in ts.values()})
    emps = sorted({t["emp"] for t in ts.values()})
    prods = sorted({l["n"] for t in ts.values() for l in t["lines"]})
    rows, agg = [], {}
    for t in ts.values():
        per = {}
        for l in t["lines"]:
            e = per.setdefault((l["n"], l["cat"]), [0, 0.0]); e[0] += l["u"]; e[1] += l["v"]
            a = agg.setdefault(l["n"], dict(n=l["n"], cat=l["cat"], sub=l["sub"], grp=l["grp"], u=0, rv=0.0))
            a["u"] += l["u"]; a["rv"] += l["v"]
        for (n, c), (u, v) in per.items():
            rows.append([stores.index(t["store"]), emps.index(t["emp"]), dates_iso.index(t["date"]),
                         CATS.index(c), prods.index(n), u, round(v, 2)])
    PR = dict(stores=stores, emps=emps, cats=CATS, prods=prods, dates=dates, rows=rows)
    PRODUCTS = {c: sorted([dict(n=a["n"], sub=a["sub"], u=a["u"], rv=round(a["rv"], 2))
                           for a in agg.values() if a["cat"] == c], key=lambda x: -x["u"]) for c in CATS}
    PRODUCT_GROUP = {a["n"]: a["grp"] for a in agg.values()}
    DAY_LABEL = {dmap[d]: dt.date.fromisoformat(d).strftime("%A") for d in dates_iso}
    WEEK_MAP = {}
    for d in dates_iso:
        WEEK_MAP.setdefault(week_label(dt.date.fromisoformat(d)), []).append(dmap[d])
    month = end.strftime("%B %Y")
    MONTH_MAP = {month: dates}
    months = [month]
    we = end.strftime(f"{end.day} %b %Y")
    META = dict(monthLabel=month, states=sorted({r[0] for r in R}), retailers=sorted({r[8] for r in R}),
                stores=stores, dates=dates, months=months)

    d0, d1 = start, end
    rng = (f"{d0.day} &ndash; {d1.day} {d1.strftime('%B %Y')}" if d0.month == d1.month
           else f"{d0.day} {d0.strftime('%B')} &ndash; {d1.day} {d1.strftime('%B %Y')}")
    if d0 == d1:
        rng = f"{d1.day} {d1.strftime('%B %Y')}"

    j = lambda o: json.dumps(o, ensure_ascii=True, separators=(",", ":"))
    page = (ROOT / "template.html").read_text()
    for k, v in dict(R=R, META=META, PR=PR, PRODUCTS=PRODUCTS, PRODUCT_GROUP=PRODUCT_GROUP, DAY_LABEL=DAY_LABEL,
                     WEEK_MAP=WEEK_MAP, MONTH_MAP=MONTH_MAP).items():
        page = page.replace(f"__{k}__", j(v).replace("</", "<\\/"))
    page = (page.replace("__MONTH_LABEL__", month).replace("__WE_LABEL__", "WE " + we)
            .replace("__RANGE_LABEL__", rng))

    out = ROOT / "site"; out.mkdir(exist_ok=True)
    (out / "index.html").write_text(page)
    (out / ".nojekyll").write_text("")
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    for wk, wdates in WEEK_MAP.items():
        wr = [r for r in R if r[3] in wdates]
        print(f"  {wk}: {len(wr)} shifts, {sum(r[6] for r in wr)} units, ${sum(r[7] for r in wr):,.2f}")
    print(f"{month} to WE {we}: {len(R)} shifts, {sum(r[5] for r in R):.2f} hours, {sum(r[6] for r in R)} units, "
          f"${sum(r[7] for r in R):,.2f}")
    if skipped:
        print("Left out (not " + " / ".join(RETAILERS) + "): " + "; ".join(skipped))


if __name__ == "__main__":
    main()
