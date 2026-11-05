"""Live checks against the production site: correctness and speed of the main features."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api-production-f372.up.railway.app"
WEB = "https://web-production-cbb1f5.up.railway.app"
q = urllib.parse.quote

# Seconds. A request slower than its budget is a speed bug (measured server-side when the
# API sends Server-Timing, so network jitter doesn't count).
BUDGETS = {
    "profile": 1.5,
    "profile_repeat": 0.6,
    "hypomating_suggest": 2.0,
    "hypomating_report": 2.0,
    "hip_cached": 0.5,
    "hip_list": 1.0,
    "stallion_list": 0.5,
    "sales_summary": 1.0,
    "web_page": 1.5,
}


class Result:
    def __init__(self, status, body, seconds, server_ms, steps):
        self.status, self.body, self.seconds, self.server_ms, self.steps = status, body, seconds, server_ms, steps


def call(path, body=None, base=API, timeout=120, parse=True):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json",
                                                          "User-Agent": "crossr-nightly"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw, status, timing = resp.read(), resp.status, resp.headers.get("Server-Timing", "")
    except urllib.error.HTTPError as exc:
        raw, status, timing = exc.read(), exc.code, exc.headers.get("Server-Timing", "") if exc.headers else ""
    seconds = time.perf_counter() - t0
    steps = {}
    for part in timing.split(","):
        name, _, dur = part.strip().partition(";dur=")
        if name and dur:
            try:
                steps[name] = float(dur)
            except ValueError:
                pass
    body_out = raw
    if parse:
        try:
            body_out = json.loads(raw or b"null")
        except ValueError:
            body_out = raw[:300]
    return Result(status, body_out, seconds, steps.pop("total", None), steps)


def slowest(steps, n=3):
    return ", ".join(f"{k} {v:.0f} ms" for k, v in sorted(steps.items(), key=lambda kv: -kv[1])[:n])


class Checker:
    def __init__(self, report):
        self.report = report

    def ok(self, cond, area, title, repro, expected, actual, files=()):
        if not cond:
            self.report.bug(area, title, repro, expected, actual, files)
        return cond

    def speed(self, res, budget_key, area, title, repro, files=()):
        took = (res.server_ms / 1000) if res.server_ms is not None else res.seconds
        self.report.timing(budget_key, took)
        if took > BUDGETS[budget_key]:
            self.report.bug(area, f"slow: {title}", repro, f"under {BUDGETS[budget_key]} s",
                            f"{took:.2f} s (slowest steps: {slowest(res.steps) or 'n/a'})", files, kind="speed")


def run(report, quick=False):
    c = Checker(report)
    n = 3 if quick else 8
    rng = random.Random()

    # --- site up
    h = call("/api/health")
    if not c.ok(h.status == 200 and (h.body or {}).get("ok"), "infra", "API health check fails",
                f"curl {API}/api/health", '{"ok": true}', f"HTTP {h.status}: {str(h.body)[:200]}", ["crossr_api/app.py"]):
        return
    for page in ("/", "/stallions", "/sales", "/hypomating", "/barn", "/horses/Curlin"):
        r = call(page, base=WEB, parse=False)
        c.ok(r.status == 200, "web", f"page {page} does not load", f"open {WEB}{page}", "HTTP 200", f"HTTP {r.status}",
             ["web/app"])
        c.speed(r, "web_page", "web", f"page {page}", f"curl -w '%{{time_total}}' {WEB}{page}", ["web/app"])

    # --- stallion registry
    r = call("/api/stallions")
    stallions = (r.body or {}).get("stallions", []) if r.status == 200 else []
    c.ok(len(stallions) >= 700, "stallions", "stallion directory is short or empty", f"curl {API}/api/stallions",
         "700+ stallions", f"{len(stallions)} (HTTP {r.status})", ["crossr_core/horses.py:build_stallion_roster"])
    c.speed(r, "stallion_list", "stallions", "stallion directory", f"curl {API}/api/stallions", ["crossr_core/horses.py"])
    names = {s["name"] for s in stallions}
    for off in ("War Front", "Frosted", "Wootton Bassett"):
        c.ok(off not in names, "stallions", f"pensioned/deceased stallion {off} is listed as standing",
             f"curl {API}/api/stallions | grep '{off}'", "not listed (stallion_status_overrides)", "listed",
             ["crossr_core/horses.py:_off_duty", "crossr_core/stallion_status.py"])
    junk = [s["name"] for s in stallions if "N/A" in str(s.get("rank")) or str(s.get("stud_fee", "")).startswith("$0")]
    c.ok(not junk, "stallions", "directory shows N/A rank or $0 fee", f"curl {API}/api/stallions", "no N/A / $0",
         ", ".join(junk[:8]), ["crossr_core/horses.py"])

    # --- profiles: identity rules and earnings
    expectations = [
        ("Curlin", lambda d: (d.get("classification") or {}).get("profile_type") == "stallion", "a stallion"),
        ("Zenyatta", lambda d: (d.get("classification") or {}).get("profile_type") == "broodmare", "a broodmare"),
        ("Englishman", lambda d: d.get("ambiguous") and {"2002", "2023"} <= set(d.get("years") or []),
         "ambiguous between 2002 and 2023"),
        ("War Front", lambda d: (d.get("classification") or {}).get("stallion_status") == "pensioned", "pensioned"),
        ("Frosted", lambda d: (d.get("classification") or {}).get("stallion_status") == "deceased", "deceased"),
    ]
    for name, test, expected in expectations:
        r = call(f"/api/horses/{q(name)}")
        c.ok(r.status == 200 and test(r.body or {}), "profiles", f"{name} profile is wrong",
             f"curl {API}/api/horses/{q(name)}", expected,
             f"HTTP {r.status}: classification={(r.body or {}).get('classification')}, years={(r.body or {}).get('years')}",
             ["crossr_core/identity.py", "crossr_core/horses.py:get_horse_profile"])
    sample = rng.sample(sorted(names), min(n, len(names)))
    for name in sample:
        r = call(f"/api/horses/{q(name)}")
        if not c.ok(r.status == 200, "profiles", f"stallion {name} from the directory has no profile",
                    f"curl {API}/api/horses/{q(name)}", "HTTP 200", f"HTTP {r.status}: {str(r.body)[:150]}",
                    ["crossr_core/horses.py:get_horse_profile"]):
            continue
        c.speed(r, "profile", "profiles", f"profile {name} (first open)", f"curl {API}/api/horses/{q(name)}",
                ["crossr_core/horses.py:get_horse_profile"])
        again = call(f"/api/horses/{q(name)}")
        c.speed(again, "profile_repeat", "profiles", f"profile {name} (repeat open)", f"curl {API}/api/horses/{q(name)}",
                ["crossr_core/horses.py:get_horse_profile"])
        d = r.body or {}
        for p in (d.get("top_progeny") or [])[:3]:
            if not p.get("earnings"):
                continue
            pd = call(f"/api/horses/{q(p['name'])}").body or {}
            seasons = sum(x.get("earnings") or 0 for x in pd.get("race_record") or [])
            c.ok(not seasons or abs(seasons - p["earnings"]) <= max(100, 0.01 * seasons), "data",
                 f"top progeny earnings for {p['name']} (by {name}) disagree with the race record",
                 f"curl {API}/api/horses/{q(name)} ; curl {API}/api/horses/{q(p['name'])}",
                 f"${seasons:,}", f"${p['earnings']:,}", ["crossr_core/horses.py:career_earnings"])
        for w in d.get("race_wins") or []:
            rn = (w.get("race_name") or "").lower()
            if ("(gr." in rn or "(grade" in rn) and w.get("class"):
                c.ok(False, "display", "race name repeats the grade", f"curl {API}/api/horses/{q(name)}",
                     "one grade label", f"{w.get('race_name')} + {w.get('class')}", ["crossr_core/horses.py:_win_class"])
                break

    # --- hypomating
    for mare in ("Zenyatta", "Beholder", "Songbird")[: 2 if quick else 3]:
        r = call("/api/hypomating/suggest", {"mare": mare})
        rows = (r.body or {}).get("suggestions") or (r.body or {}).get("rows") or (r.body or {}).get("results") or []
        c.ok(r.status == 200 and (rows or isinstance(r.body, dict)), "hypomating", f"suggestions for {mare} fail",
             f"curl -X POST {API}/api/hypomating/suggest -d '{{\"mare\":\"{mare}\"}}'", "HTTP 200 with suggestions",
             f"HTTP {r.status}: {str(r.body)[:150]}", ["hypomating_engine.py:suggest_matings"])
        c.speed(r, "hypomating_suggest", "hypomating", f"suggestions for {mare}",
                f"curl -X POST {API}/api/hypomating/suggest -d '{{\"mare\":\"{mare}\"}}'",
                ["hypomating_engine.py", "crossr_core/horses.py"])
    for sire, dam in (("Curlin", "Zenyatta"), ("Gun Runner", "Beholder"), ("Into Mischief", "Songbird"))[: 2 if quick else 3]:
        r = call("/api/hypomating/report", {"sire": sire, "dam": dam})
        body = r.body or {}
        c.ok(r.status == 200 and body.get("pedigree") is not None, "hypomating", f"report {sire} x {dam} fails",
             f"curl -X POST {API}/api/hypomating/report -d '{{\"sire\":\"{sire}\",\"dam\":\"{dam}\"}}'",
             "HTTP 200 with a pedigree", f"HTTP {r.status}: {str(body)[:150]}",
             ["hypomating_engine.py:build_hypo_report", "crossr_core/horses.py:enrich_hypofoal_report"])
        c.speed(r, "hypomating_report", "hypomating", f"report {sire} x {dam}",
                f"curl -X POST {API}/api/hypomating/report -d '{{\"sire\":\"{sire}\",\"dam\":\"{dam}\"}}'",
                ["crossr_core/horses.py:enrich_hypofoal_report"])

    # --- sales hub
    cats = (call("/api/sales/upcoming").body or {}).get("catalogs", [])
    c.ok(bool(cats), "sales", "no upcoming catalogs", f"curl {API}/api/sales/upcoming", "1+ catalogs", "none",
         ["crossr_core/upcoming.py"])
    for cat in cats:
        cid = q(cat["id"])
        r = call(f"/api/sales/upcoming/{cid}/lots")
        lots = (r.body or {}).get("lots", [])
        c.ok(r.status == 200 and lots, "sales", f"hip list for {cat['id']} fails", f"curl {API}/api/sales/upcoming/{cid}/lots",
             "HTTP 200 with lots", f"HTTP {r.status}, {len(lots)} lots", ["crossr_core/upcoming.py:list_lots"])
        c.speed(r, "hip_list", "sales", f"hip list {cat['id']}", f"curl {API}/api/sales/upcoming/{cid}/lots",
                ["crossr_core/upcoming.py"])
        for lot in rng.sample(lots, min(n, len(lots))):
            hip = lot["hip"]
            path = f"/api/sales/upcoming/{cid}/lots/{q(hip)}"
            first = call(path)
            if not c.ok(first.status == 200, "sales", f"hip {hip} of {cat['id']} fails", f"curl {API}{path}", "HTTP 200",
                        f"HTTP {first.status}: {str(first.body)[:150]}", ["crossr_api/app.py:sales_upcoming_lot"]):
                continue
            again = call(path)
            c.speed(again, "hip_cached", "sales", f"hip {hip} of {cat['id']} (stored page)", f"curl {API}{path}",
                    ["crossr_core/hip_cache.py"])
            ped = (first.body or {}).get("pedigree") or {}
            c.ok(bool((ped.get("sire") or {}).get("name")) and bool((ped.get("dam") or {}).get("name")), "data",
                 f"hip {hip} of {cat['id']} pedigree has no sire or dam", f"curl {API}{path}", "sire and dam named",
                 f"sire={(ped.get('sire') or {}).get('name')}, dam={(ped.get('dam') or {}).get('name')}",
                 ["crossr_core/horses.py:catalog_pedigree"])
            padded = hip.zfill(4) if hip.isdigit() and len(hip) < 4 else hip.lstrip("0") or hip
            if padded != hip:
                alt = call(f"/api/sales/upcoming/{cid}/lots/{q(padded)}")
                c.ok(alt.status == 200, "sales", f"hip {padded} (= {hip}) not found in {cat['id']}",
                     f"curl {API}/api/sales/upcoming/{cid}/lots/{q(padded)}", "HTTP 200", f"HTTP {alt.status}",
                     ["crossr_core/upcoming.py:hip_key"])
    for sire in rng.sample(sorted(names), min(2, len(names))):
        r = call(f"/api/sales/sire/{q(sire)}/summary")
        c.ok(r.status == 200, "sales", f"sire sales summary for {sire} fails", f"curl {API}/api/sales/sire/{q(sire)}/summary",
             "HTTP 200", f"HTTP {r.status}", ["crossr_core/sales.py:sire_sales_summary"])
        c.speed(r, "sales_summary", "sales", f"sire sales summary {sire}", f"curl {API}/api/sales/sire/{q(sire)}/summary",
                ["crossr_core/sales.py"])
    for kind in ("entries", "results"):
        r = call(f"/api/weekly/{kind}")
        c.ok(r.status == 200, "weekly", f"weekly {kind} endpoint fails", f"curl {API}/api/weekly/{kind}", "HTTP 200",
             f"HTTP {r.status}", ["crossr_core/weekly.py", "crossr_api/app.py:weekly_report"])
