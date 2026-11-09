"""
SharkNinja AU all-time sales dashboard builder.

Pulls every SharkNinja AU Demo and Event shift (Timesheet__c) and sale (Product_Sale__c) from Salesforce,
for all retailers and dates, and writes site/all/ (index.html, data.json, version.json).
The page itself does the filtering (dates, business unit, state, retailer, category, store, staff,
product), so one data file covers everything.

Environment variables (GitHub secrets): SF_INSTANCE_URL, SF_CLIENT_ID, SF_CLIENT_SECRET (as build.py).

  --cache FILE      keep the last pull in FILE and only pull again when Salesforce has changed
                    (row counts or last-modified time). The watcher uses this so a check costs
                    2 small API calls instead of a full pull.
  --fixture FILE    build from a JSON file {"timesheets": [...], "sales": [...]} instead of Salesforce.
"""
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from build import CATS, CUSTOMER, rel, sf_query_all, title_store

ROOT = Path(__file__).parent
BUSINESS_UNITS = ["Demo", "Event"]   # other units (Training, Field Rep/Merch, ...) are left out
WHERE_TS = (f"RB_Customer__r.Name = '{CUSTOMER}' AND RB_Actual_Start_Date__c != null "
            f"AND RB_Business_Unit__r.Name IN ({', '.join(repr(b) for b in BUSINESS_UNITS)})")
WHERE_PS = WHERE_TS.replace("RB_", "Timesheet__r.RB_")
Q_FINGERPRINT = [
    f"SELECT COUNT(Id) n, MAX(LastModifiedDate) lm FROM Timesheet__c WHERE {WHERE_TS}",
    f"SELECT COUNT(Id) n, MAX(LastModifiedDate) lm FROM Product_Sale__c WHERE {WHERE_PS}",
]
Q_DATA = [
    ("SELECT Id, State__c, RB_Customer_Store__r.Name, Employee_Name__r.Name, RB_Actual_Start_Date__c, "
     f"Shift_Duration_Hours__c, Retailer__c, RB_Business_Unit__r.Name FROM Timesheet__c WHERE {WHERE_TS}"),
    ("SELECT Timesheet__c, RB_Customer_Product__r.Name, Product_Family__c, Product_Category__c, "
     f"Product_Group1__c, noofsales__c, Value__c FROM Product_Sale__c WHERE {WHERE_PS}"),
]


def pull(cache):
    """Return (timesheets, sales), using the cache when Salesforce hasn't changed since the last pull."""
    fp = None
    if cache:
        fp = json.dumps([[{k: r.get(k) for k in ("n", "lm")} for r in rows]
                         for rows in sf_query_all(Q_FINGERPRINT)], sort_keys=True)
        if cache.exists():
            old = json.loads(cache.read_text())
            if old.get("fingerprint") == fp:
                return old["timesheets"], old["sales"]
    timesheets, sales = sf_query_all(Q_DATA)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(dict(fingerprint=fp, timesheets=timesheets, sales=sales)))
    return timesheets, sales


def shape(timesheets, sales):
    """Turn Salesforce rows into the compact, index-based data file the page reads."""
    dims = {k: {} for k in ("dates", "states", "rets", "bus", "stores", "emps")}

    def ix(dim, value):
        return dims[dim].setdefault(value, len(dims[dim]))

    shifts, sid = [], {}
    for t in sorted(timesheets, key=lambda t: (t["RB_Actual_Start_Date__c"], t["Id"])):
        sid[t["Id"][:15]] = len(shifts)
        shifts.append([ix("dates", t["RB_Actual_Start_Date__c"]), ix("states", t.get("State__c") or "Unknown"),
                       ix("rets", t.get("Retailer__c") or "Other"),
                       ix("bus", rel(t, "RB_Business_Unit__r.Name") or "Other"),
                       ix("stores", title_store(rel(t, "RB_Customer_Store__r.Name") or "Unknown")),
                       ix("emps", rel(t, "Employee_Name__r.Name") or "Unknown"),
                       round(float(t.get("Shift_Duration_Hours__c") or 0), 2)])

    prods, lines, groups = {}, {}, {}
    for p in sales:
        s = sid.get((p.get("Timesheet__c") or "")[:15])
        if s is None:
            continue
        cat = p.get("Product_Family__c") if p.get("Product_Family__c") in CATS else "Other Products"
        name = rel(p, "RB_Customer_Product__r.Name") or "Unknown product"
        grp = groups.setdefault(p.get("Product_Group1__c") or "Other", len(groups))
        pi = prods.setdefault(name, [len(prods), CATS.index(cat), p.get("Product_Category__c") or cat, grp])[0]
        e = lines.setdefault((s, pi), [s, pi, 0, 0.0])
        e[2] += int(p.get("noofsales__c") or 0)
        e[3] += float(p.get("Value__c") or 0)
    L = sorted([s, pi, u, round(v, 2)] for s, pi, u, v in lines.values())
    P = [[n, c, sub, g] for n, (_, c, sub, g) in sorted(prods.items(), key=lambda kv: kv[1][0])]
    return dict(D={k: list(v) for k, v in dims.items()}, cats=CATS, groups=list(groups), S=shifts, L=L, P=P)


def assets():
    """Logo, Chart.js (+ datalabels plugin) and password hash come from template.html so both pages stay in step."""
    tpl = (ROOT / "template.html").read_text()
    chart = re.search(r"<script>(/\*!\s*\n \* Chart\.js.*?)</script>", tpl, re.S).group(1)
    labels = re.search(r"<script>(/\*!\s*\n \* chartjs-plugin-datalabels.*?)</script>", tpl, re.S).group(1)
    logo = re.search(r'src="(data:image/[^"]+)"', tpl).group(1)
    pw = re.search(r"if \(hash === '([0-9a-f-]+)'\)", tpl).group(1)
    return chart + "\n" + labels, logo, pw


def main():
    if "--fixture" in sys.argv:
        fx = json.loads(Path(sys.argv[sys.argv.index("--fixture") + 1]).read_text())
        timesheets, sales = fx["timesheets"], fx["sales"]
    else:
        cache = Path(sys.argv[sys.argv.index("--cache") + 1]) if "--cache" in sys.argv else None
        timesheets, sales = pull(cache)
    data = shape(timesheets, sales)
    if not data["S"]:
        sys.exit("No SharkNinja AU shifts found; nothing published.")

    j = lambda o: json.dumps(o, ensure_ascii=True, separators=(",", ":"))
    version = hashlib.sha256(j(data).encode()).hexdigest()[:12]
    out = ROOT / "site" / "all"
    out.mkdir(parents=True, exist_ok=True)
    old = out / "version.json"
    now = dt.datetime.now(ZoneInfo("Australia/Sydney"))
    updated = now.strftime(f"%a {now.day} %b, {now.hour % 12 or 12}:%M ") + ("am" if now.hour < 12 else "pm")
    if old.exists() and json.loads(old.read_text()).get("version") == version:
        updated = json.loads(old.read_text())["updated"]   # unchanged data keeps its "last change" time
    stamp = dict(version=version, updated=updated)

    chart, logo, pw = assets()
    page = (ROOT / "template_all.html").read_text()
    page = (page.replace("__CHARTJS__", chart.replace("</", "<\\/")).replace("__LOGO__", logo)
            .replace("__PW_HASH__", pw).replace("__VERSION__", version).replace("__UPDATED__", updated))
    (out / "index.html").write_text(page)
    (out / "data.json").write_text(j(dict(data, **stamp)))
    (out / "version.json").write_text(j(stamp))

    S, L = data["S"], data["L"]
    dates = data["D"]["dates"]
    print(f"All-time data version {version}: {len(S)} shifts, {len(L)} product lines, "
          f"{sum(l[2] for l in L):,} units, ${sum(l[3] for l in L):,.2f} "
          f"({min(dates)} to {max(dates)})")


if __name__ == "__main__":
    main()
