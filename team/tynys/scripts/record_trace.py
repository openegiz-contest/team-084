"""Записать ui/trace.json — 96 модельных часов стенда без Docker.

Та же модель, координатор V2 (MPC) и тени V0/V1, что в services/field.py и
services/coordinator.py; публикация идёт теми же функциями publish_hour и
explain, только вместо MQTT/Ditto — словарь двойников. Запись нужна лёгкой 3D,
когда Ditto недоступен (страница открыта отдельно, demo.html, проверка FPS).

    PYTHONPATH=team/tynys:team/tynys/services python team/tynys/scripts/record_trace.py
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services")]

from setup_twins import twins                                   # noqa: E402
from field import publish_hour, Totals                          # noqa: E402
from coordinator import explain                                 # noqa: E402
from tynys.params import aktogay                                # noqa: E402
from tynys.sim import Env, Scenario, init_state, step           # noqa: E402
from tynys.controllers import V0Traditional, V1Reactive, V2Tynys  # noqa: E402

SKIP = {"state_json", "x_json", "plan_json", "maintenance_json"}   # тяжёлые поля 3D не читает


def plain(v):
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float):
        return round(v, 3)
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    return v


class Store:
    def __init__(self):
        self.things = {}
        for name, thing in twins().items():
            self.things[name] = {k: f.get("properties", {}).get("value")
                                 for k, f in thing.get("features", {}).items()}

    def send(self, name, values):
        self.things.setdefault(name, {}).update({k: plain(v) for k, v in values.items() if k not in SKIP})

    def snapshot(self):
        # Типовые двойники и запросы экспериментов 3D не рисует.
        keep = {k: v for k, v in self.things.items() if not k.startswith(("type-", "future-"))}
        return json.loads(json.dumps(keep))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-doy", type=int, default=105)
    ap.add_argument("--start-hour", type=int, default=9)
    ap.add_argument("--hours", type=int, default=96)
    ap.add_argument("--record-from", type=int, default=190,
                    help="модельный час начала записи; часы до него — разгон с start-hour, итоги копятся с него")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--output", type=Path, default=ROOT / "ui" / "trace.json")
    a = ap.parse_args()
    p = aktogay()
    first = max(a.start_hour, a.record_from)
    env = Env(p, Scenario(start_doy=a.start_doy, days=(first + a.hours) // 24 + 2), a.seed)
    st = {k: init_state(p) for k in ("v0", "v1", "v2")}
    tot = {k: Totals() for k in st}
    ctl = {"v0": V0Traditional(), "v1": V1Reactive()}
    # Цель по умолчанию на стенде — «CO₂» (services/setup_twins.py, coordinator.py)
    v2 = V2Tynys(explain=True, grind_modes=(150, 200, 250), flat_price=True)
    bus, frames, last = Store(), [], {}
    for t in range(a.start_hour, first + a.hours):
        sim_time = dt.datetime(2026, 1, 1) + dt.timedelta(days=a.start_doy - 1, hours=t)
        bus.send("site", {"sim_hour": t, "sim_time": sim_time.strftime("%Y-%m-%d %H:00"),
                          "start_doy": a.start_doy, "start_hour": a.start_hour,
                          "elapsed_hours": int(tot["v2"].hours), "seed": a.seed, "scenario_rev": 0,
                          **tot["v2"].feats()})
        for k in ("v0", "v1"):
            bus.send(f"shadow-{k}", {**tot[k].feats(), **last.get(k, {})})
        dec = v2.decide(p, env, st["v2"], t)
        if v2.last_plan:
            mode, why = explain(p, st["v2"], dec, v2.last_plan, t)
        else:
            mode, why = "выдох", "Решение по запасному правилу V1."
        bus.send("coordinator", {"for_t": t, "scenario_rev": 0, "charge_mw": round(dec["charge_mw"], 2),
                                 "bess_mw": round(dec["bess_mw"], 2), "mode": mode, "why": why, "goal": "green",
                                 "feed_plan_tph": round(sum(sum(sum(d) for d in line) for line in dec["x"]))})
        rec = step(p, env, st["v2"], t, dec, True)
        tot["v2"].add(p, rec, st["v2"])
        for k in ("v0", "v1"):
            r = step(p, env, st[k], t, ctl[k].decide(p, env, st[k], t), ctl[k].segregated)
            tot[k].add(p, r, st[k])
            last[k] = {"grid_mw": round(r["grid"], 1), "curtail_mw": round(r["curtail"], 1), "feed_tph": round(r["feed"]),
                       "feed_soft_tph": round(r["feed_soft"]), "feed_hard_tph": round(r["feed_hard"]),
                       "pile_soft_t": round(st[k].pile["soft"]), "pile_hard_t": round(st[k].pile["hard"]),
                       "pile_soft_fill_pct": round(100 * st[k].pile["soft"] / p.pile_cap_t, 1),
                       "pile_hard_fill_pct": round(100 * st[k].pile["hard"] / p.pile_cap_t, 1),
                       "line1_tph": round(r["line0"]), "line2_tph": round(r["line1"]),
                       "mill_mw": round(r["mill_mw"], 1), "charge_mw": round(r["charge"], 1)}
        publish_hour(bus, p, env, st["v2"], rec, t, "coordinator", st["v2"].fleet)
        if t >= first:
            frames.append(bus.snapshot())
        if (t - a.start_hour) % 24 == 23:
            print(f"t={t}: Cu V2 {tot['v2'].cu:.0f} t, V0 {tot['v0'].cu:.0f} t", flush=True)
    a.output.write_text(json.dumps(frames, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{a.output}: {len(frames)} h, {a.output.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
