#!/usr/bin/env python3
"""Проверка what-if на стенде: каждый сценарий включается через двойник scenario
(как кнопкой на экране), проверяется его след в двойниках, затем отменяется.
Запуск: python3 team/tynys/scripts/whatif_check.py (читает deploy/compose/.env)."""
import base64, json, os, sys, time, urllib.request
env = dict(l.strip().split("=", 1) for l in open("deploy/compose/.env") if "=" in l and not l.startswith("#"))
URL = f"http://127.0.0.1:{env.get('DITTO_PORT', '8080')}/api/2/things/kz.tynys:"
AUTH = "Basic " + base64.b64encode(f"ditto:{env['DITTO_PASSWORD']}".encode()).decode()


def req(method, path, body=None):
    r = urllib.request.Request(URL + path, method=method, data=None if body is None else json.dumps(body).encode(),
                               headers={"Authorization": AUTH, "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=10) as x:
        raw = x.read(); return json.loads(raw) if raw else None


val = lambda thing, f: req("GET", f"{thing}/features/{f}/properties/value")


def set_events(events):
    rev = (val("scenario", "rev") or 0) + 1
    req("PUT", "scenario/features", {"events": {"properties": {"value": json.dumps(events)}}, "rev": {"properties": {"value": rev}},
                                     "goal": {"properties": {"value": val("scenario", "goal") or "green"}}})
    return rev


def wait(cond, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if cond(): return True
        except Exception:
            pass
        time.sleep(1)
    return False


CHECKS = {
    "line_trip": lambda: val("line-2", "available") is False,
    "kegoc": lambda: val("substation", "grid_cap_mw") < 200,
    "bess_fault": lambda: val("bess", "available") is False,
    "hard_ore": lambda: val("pit", "hard_frac") > 0.65,
    "plan_up": lambda: val("pit", "ore_plan_tph") > 7000,
    "lull": lambda: val("wind", "cf_pct") <= 9.5,
}
ok = True
for kind, check in CHECKS.items():
    h = val("site", "sim_hour")
    rev = set_events([{"kind": kind, "t0": h + 1, "dur": 24, "id": 1}])
    applied = wait(lambda: val("site", "scenario_rev") == rev and val("coordinator", "scenario_rev") == rev)
    seen = applied and wait(check)
    rev2 = set_events([])
    undone = wait(lambda: val("site", "scenario_rev") == rev2 and val("coordinator", "scenario_rev") == rev2)
    if kind in ("line_trip", "kegoc", "bess_fault", "plan_up"):   # след детерминирован — проверяем, что исчез
        undone = undone and wait(lambda: not check())
    print(f"{kind:11s} принят={applied} след_в_двойниках={seen} отменён={undone}")
    ok &= applied and seen and undone
print("WHATIF OK" if ok else "WHATIF FAIL")
sys.exit(0 if ok else 1)
