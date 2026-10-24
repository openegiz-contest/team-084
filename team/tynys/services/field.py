#!/usr/bin/env python3
"""«Поле»: имитация реального рудника Актогай в ускоренном времени.

Каждый модельный час:
  1. публикует состояние рудника в двойники (MQTT telemetry/<twin> → Ditto);
  2. ждёт уставки от координатора — читает двойник kz.tynys:coordinator из Ditto;
     если координатор не ответил, работает по простому правилу V1 (как АСУ при
     потере связи) и честно пишет это в двойник;
  3. применяет уставки к ФАКТИЧЕСКОЙ погоде и твёрдости руды (модель sim.step);
  4. параллельно считает два «теневых» рудника — V0 (как сейчас) и V1
     (простые правила) — на той же погоде, чтобы экран показывал разницу.
Сценарии what-if приходят только через двойник kz.tynys:scenario.
"""
import copy, datetime as dt, json, logging, math, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tynys.live import build_env, dumps, state_to_dict
from tynys.sim import init_state, step
from tynys.controllers import V0Traditional, V1Reactive
from tynys.params import P80_MODES
from tynys import physics as ph
from tynys.metrics import grid_adjusted
from platform_client import Bus, get_things, prop, wait_ditto

HOUR_S = float(os.environ.get("HOUR_SECONDS", "6"))      # реальных секунд на модельный час
DECIDE_TIMEOUT = float(os.environ.get("DECIDE_TIMEOUT", "4"))
SEED = int(os.environ.get("SIM_SEED", "7"))
log = logging.getLogger("field")


def start_clock(environ=None):
    """Use the same hour index for model weather, controllers and the clock."""
    settings = os.environ if environ is None else environ
    day = int(settings.get("START_DOY", dt.date.today().timetuple().tm_yday))
    hour = int(settings.get("START_HOUR", "9"))
    if not 1 <= day <= 366 or not 0 <= hour <= 23:
        raise ValueError("START_DOY must be 1..366; START_HOUR must be 0..23")
    return day, hour


class Totals:
    def __init__(self):
        self.cu = self.grid = self.co2 = self.curt = self.renew = self.cost = self.feed = self.hours = self.cu_adj = self.co2_adj = 0.0
        self.pile0 = None

    def add(self, p, r, st=None):
        if st is not None:
            if self.pile0 is None:
                self.pile0 = {d: p.pile_cap_t * p.pile_init_frac for d in st.pile}   # все варианты стартуют с init_state
            self.cu_adj = self.cu + r["cu_t"] + sum((st.pile_recovery_cu[d] if p.geomet else st.pile_cu[d]*p.r150[d]) - self.pile0[d]*p.cu_grade[d]*p.r150[d] for d in st.pile)
        self.cu += r["cu_t"]; self.grid += r["grid"]; self.co2 += r["grid"] * p.grid_co2_t_mwh
        self.curt += r["curtail"]; self.renew += r["renew"] - r["curtail"]; self.cost += r["grid"] * r["price"]
        self.feed += r["feed"]; self.hours += 1
        if st is not None:   # CO₂ с учётом запасов: склады и заряд батарей в сравнении с началом (metrics.grid_adjusted)
            d_pile = sum(st.pile[d] - self.pile0[d] for d in st.pile)
            self.co2_adj = grid_adjusted(p, self.grid, self.feed, d_pile,
                                         st.fleet_e - 0.6 * p.n_trucks * p.truck_batt_mwh,
                                         st.bess_e - 0.5 * p.bess_mwh) * p.grid_co2_t_mwh

    def feats(self):
        return {"cu_t": round(self.cu, 1), "cu_adj_t": round(self.cu_adj, 1), "grid_mwh": round(self.grid, 1), "co2_t": round(self.co2, 1), "co2_adj_t": round(self.co2_adj, 1),
                "curtail_mwh": round(self.curt, 1), "renew_used_mwh": round(self.renew, 1),
                "grid_cost_mkzt": round(self.cost / 1e6, 2), "ore_fed_kt": round(self.feed / 1000, 2),
                "co2_per_t_cu": round(self.co2_adj / self.cu_adj, 3) if self.cu_adj else 0.0}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s field %(message)s")
    wait_ditto()
    bus = Bus("tynys-field")
    start_doy, start_hour = start_clock()
    events, ev_rev = [], None
    p, env = build_env(events, start_doy, SEED)
    st = {k: init_state(p) for k in ("v2", "v0", "v1")}
    ctl = {"v0": V0Traditional(), "v1": V1Reactive()}
    tot = {k: Totals() for k in st}
    # Fresh inventories at 09:00 by default. No production is invented for
    # hours before startup; all three controllers use this same weather index.
    t, last = start_hour, {}
    while True:
        t_hour0 = time.time()
        if t >= env.sc.n():   # год прошёл — начинаем заново
            t, st, tot = start_hour, {k: init_state(p) for k in st}, {k: Totals() for k in st}
        # --- сценарий из двойника ---
        try:
            sc = get_things(["scenario"])["scenario"]
            rev = prop(sc, "rev", 0)
            if rev != ev_rev:
                events = json.loads(prop(sc, "events", "[]") or "[]")
                p, env = build_env(events, start_doy, SEED)
                ev_rev = rev
                log.info("scenario rev %s: %s", rev, [e["kind"] for e in events])
        except Exception as e:
            log.warning("scenario read failed: %s", e)
        # --- 1. состояние → двойник site, запрос решения ---
        sim_time = dt.datetime(2026, 1, 1) + dt.timedelta(days=start_doy - 1, hours=t)
        bus.send("site", {"sim_hour": t, "sim_time": sim_time.strftime("%Y-%m-%d %H:00"),
                          "start_doy": start_doy, "start_hour": start_hour, "elapsed_hours": int(tot["v2"].hours),
                          "seed": SEED, "scenario_rev": ev_rev or 0,
                          "state_json": dumps(state_to_dict(st["v2"])), **tot["v2"].feats()})
        # Итоги теней и V2 охватывают одни часы: start_hour..t-1.
        for k in ("v0", "v1"):
            bus.send(f"shadow-{k}", {**tot[k].feats(), **last.get(k, {})})
        # --- 2. ждём координатора ---
        dec, source = None, "fallback_v1"
        deadline = time.time() + DECIDE_TIMEOUT
        while time.time() < deadline:
            try:
                c = get_things(["coordinator"])["coordinator"]
                if prop(c, "for_t") == t and prop(c, "scenario_rev") == (ev_rev or 0):
                    dec = {"x": json.loads(prop(c, "x_json")), "charge_mw": float(prop(c, "charge_mw")),
                           "bess_mw": float(prop(c, "bess_mw")), "maintenance": json.loads(prop(c, "maintenance_json", "{}"))}
                    source = "coordinator"; break
            except Exception:
                pass
            time.sleep(0.25)
        if dec is None:
            dec = V1Reactive().decide(p, env, st["v2"], t)
            log.warning("t=%d: no coordinator decision, V1 fallback", t)
        # --- 3. шаг «правды» и теней ---
        rec = step(p, env, st["v2"], t, dec, source != "fallback_v1")
        tot["v2"].add(p, rec, st["v2"])
        for k in ("v0", "v1"):
            r = step(p, env, st[k], t, ctl[k].decide(p, env, st[k], t), ctl[k].segregated)
            tot[k].add(p, r, st[k])
            last[k] = {"grid_mw": round(r["grid"], 1), "curtail_mw": round(r["curtail"], 1), "feed_tph": round(r["feed"]),
                       # Состояние тени для 3D «Как сейчас»: свои склады, линии и мельницы
                       "feed_soft_tph": round(r["feed_soft"]), "feed_hard_tph": round(r["feed_hard"]),
                       "pile_soft_t": round(st[k].pile["soft"]), "pile_hard_t": round(st[k].pile["hard"]),
                       "pile_soft_fill_pct": round(100 * st[k].pile["soft"] / p.pile_cap_t, 1),
                       "pile_hard_fill_pct": round(100 * st[k].pile["hard"] / p.pile_cap_t, 1),
                       "line1_tph": round(r["line0"]), "line2_tph": round(r["line1"]),
                       "mill_mw": round(r["mill_mw"], 1), "charge_mw": round(r["charge"], 1)}
        publish_hour(bus, p, env, st["v2"], rec, t, source, st["v2"].fleet)
        # --- 4. ждём конца модельного часа ---
        # Самосвалы публикуются раз в час вместе с остальными двойниками: их заряд,
        # состояние и груз меняются по часовой модели, а движение по дороге экраны
        # анимируют сами. Это снимает с Ditto ~70 лишних сообщений в час.
        time.sleep(max(0.0, HOUR_S - (time.time() - t_hour0)))
        t += 1


def publish_hour(bus, p, env, st, r, t, source, fleet):
    from tynys.geology import telemetry
    bus.send("geology", telemetry(env, t))
    bus.send("pit", {"ore_tph": round(r["mine"]), "ore_plan_tph": round(r["mine_plan"]),
                     "hard_frac": round(r["hard_frac"], 3), "spilled_tph": round(r["spilled"], 1), "waste_tph": r["waste_tph"]})
    bus.send("plant", {"feed_tph": round(r["feed"]), "feed_soft_tph": round(r["feed_soft"]),
                       "feed_hard_tph": round(r["feed_hard"]), "p80_um": round(r["p80"], 1) if r["feed"] > 0 else 0,
                       "cu_tph": round(r["cu_t"], 2), "mill_mw": round(r["mill_mw"], 1),
                       "decision_source": source})
    for d in ("soft", "hard"):
        bus.send(f"pile-{d}", {"tonnes": round(st.pile[d]), "fill_pct": round(100 * st.pile[d] / p.pile_cap_t, 1),
                               "cu_t": st.pile_cu[d], "grade_pct": 100*st.pile_cu[d]/st.pile[d] if st.pile[d] > 0 else 0,
                               "bwi_est": round(st.bwi_est[d], 2), "bwi_true": st.pile_bwi_mass[d]/st.pile[d] if st.pile[d] else p.bwi[d],
                               "recovery_pct": 100*st.pile_recovery_cu[d]/st.pile_cu[d] if st.pile_cu[d] else 0})
    for name, features in r["assets"].items():
        bus.send(name, features)
    bus.send("energy", {"load_mw": round(r["load"], 1), "renew_mw": round(r["renew"], 1),
                        "grid_no_lull_mw": r["grid_no_lull_mw"], "lull_grid_delta_mw": r["lull_grid_delta_mw"],
                        "curtail_mw": round(r["curtail"], 1), "grid_mw": round(r["grid"], 1),
                        "charge_mw": round(r["charge"], 1), "unserved_mw": round(r["unserved"], 1),
                        "renew_share_pct": round(100 * (r["renew"] - r["curtail"]) / max(r["load"], 1e-6), 1)})


if __name__ == "__main__":
    main()
