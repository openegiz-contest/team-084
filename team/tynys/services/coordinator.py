#!/usr/bin/env python3
"""«Мозг» Тыныс: координатор с прогнозирующей моделью (MPC, горизонт 24 ч).

Читает состояние рудника и сценарий из двойников Ditto, каждый модельный час
решает задачу смешанного целочисленного программирования (HiGHS через SciPy):
сколько и какой руды молоть на каждой линии и с какой крупностью, когда
заряжать самосвалы и накопитель, — и пишет план, уставки, теневую цену
энергии и объяснение «почему» обратно в двойник kz.tynys:coordinator.
"""
import json, logging, os, sys, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tynys.live import build_env, dumps, state_from_dict
from tynys.controllers import V2Tynys
from platform_client import Bus, get_things, prop, wait_ditto

log = logging.getLogger("coord")


def explain(p, st, dec, plan, t):
    """Короткое объяснение решения на человеческом языке."""
    sh = plan["shadow_kzt_mwh"][0]
    tariff = p.tariff_kzt_kwh * 1000
    renew0 = plan["renew_mw"][0]
    ren_next = float(np.mean(plan["renew_mw"][1:13])) if len(plan["renew_mw"]) > 1 else renew0
    x = np.array(dec["x"])                      # [линия][домен][P80]
    hard = float(x[:, 1, :].sum()); soft = float(x[:, 0, :].sum()); feed = hard + soft
    p80 = plan["p80_um"][0] or 0
    cheap = sh is not None and not np.isnan(sh) and sh < 0.8 * tariff
    mode = "вдох" if cheap else "выдох"
    why = [f"Энергия {'дешёвая' if cheap else 'дорогая'}: лишний кВт·ч сейчас стоит {max(0.0, sh / 1000):.0f} ₸ "
           f"(ВИЭ {renew0:.0f} МВт) — {'«вдыхаем»' if cheap else '«выдыхаем»'}."]
    if feed > 1:
        dom = "твёрдую" if hard > 0.55 * feed else "мягкую" if soft > 0.55 * feed else "смесь"
        why.append(f"Мелем {dom} руду: твёрдой {hard:.0f}, мягкой {soft:.0f} т/ч.")
        for l, values in enumerate(plan.get("line_p80_um", [])):
            if values[0] is not None:
                why.append(f"Линия {l+1}: P80 {values[0]:.0f} мкм.")
        if dom == "мягкую":
            why.append("Твёрдую копим на складе до дешёвой энергии.")
    why.append(f"Самосвалы заряжаются {dec['charge_mw']:.0f} МВт." if dec["charge_mw"] > 5 else "Самосвалы ездят на заряде батарей.")
    if dec["bess_mw"] > 5:
        why.append(f"Накопитель отдаёт {dec['bess_mw']:.0f} МВт.")
    elif dec["bess_mw"] < -5:
        why.append(f"Накопитель заряжается {-dec['bess_mw']:.0f} МВт.")
    if ren_next > renew0 * 1.5 and ren_next > 100:
        why.append(f"Через несколько часов ждём ветер/солнце ~{ren_next:.0f} МВт — готовимся.")
    elif ren_next < renew0 * 0.5 and renew0 > 100:
        why.append(f"По прогнозу ВИЭ упадут до ~{ren_next:.0f} МВт — запасаемся сейчас.")
    if min(plan["grid_cap_mw"]) < p.grid_cap_mw - 1:
        h = int(np.argmin(plan["grid_cap_mw"]))
        why.append(f"Через {h} ч сеть ограничена до {min(plan['grid_cap_mw']):.0f} МВт (KEGOC) — план учитывает.")
    if not any(st.line_lock) and sum(plan["lines_on"][l][0] for l in range(p.n_lines)) < p.n_lines:
        why.append("В плане есть остановленная линия; учитываются доступность, ремонт и ограничения подачи.")
    for line, item in dec.get("maintenance", {}).items():
        if item["start"]+item["duration"] > t:
            title = "замена футеровки" if item["kind"] == "liner" else "плановое ТО"
            why.append(f"Ремонт на выдохе: {line}, {title} с часа {item['start']} на {item['duration']} ч; крайний старт {item['deadline']}. Окно выбрано по прогнозу стоимости сети.")
    return mode, " ".join(why)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s coord %(message)s")
    wait_ditto()
    bus = Bus("tynys-coordinator")
    ctls = {"copper": V2Tynys(explain=True),
            "green": V2Tynys(explain=True, grind_modes=(150, 200, 250), flat_price=True)}   # не тоньше обычного; минимум МВт·ч из сети
    cache = {}
    last_t = None
    while True:
        try:
            th = get_things(["site", "scenario"])
        except Exception as e:
            log.warning("ditto read: %s", e); time.sleep(1); continue
        site, sc = th.get("site"), th.get("scenario")
        t = prop(site, "sim_hour"); sj = prop(site, "state_json")
        rev_site = prop(site, "scenario_rev", 0); rev = prop(sc, "rev", 0)
        if t is None or sj is None or t == last_t or rev_site != rev:
            time.sleep(0.2); continue
        key = (rev, prop(site, "start_doy"), prop(site, "seed"))
        if key not in cache:
            cache.clear()
            cache[key] = build_env(json.loads(prop(sc, "events", "[]") or "[]"), key[1], key[2])
        p, env = cache[key]
        st = state_from_dict(json.loads(sj))
        t0 = time.time()
        goal = prop(sc, "goal", "green")
        ctl = ctls.get(goal, ctls["green"])
        dec = ctl.decide(p, env, st, t)
        plan = ctl.last_plan or {}
        ms = (time.time() - t0) * 1000
        mode, why = explain(p, st, dec, plan, t) if plan else ("выдох", "MILP не решилась — правило V1")
        r = lambda a, k=1: [None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), k) for v in a]
        compact = {k: r(plan[k]) for k in ("renew_mw", "grid_cap_mw", "feed_tph", "hard_tph", "p80_um", "charge_mw",
                                         "bess_mw", "grid_mw", "curtail_mw", "fleet_mwh", "bess_mwh")} if plan else {}
        if plan:
            for key in ("line_p80_um", "line_feed_tph", "line_mw"):
                compact[key] = [r(line) for line in plan[key]]
            for key in ("bess_charge_mw", "bess_discharge_mw"):
                compact[key] = r(plan[key])
            compact["shadow_kzt_kwh"] = r(np.array(plan["shadow_kzt_mwh"], float) / 1000, 2)
            compact["pile_soft_kt"] = r(np.array(plan["pile_soft_t"]) / 1000)
            compact["pile_hard_kt"] = r(np.array(plan["pile_hard_t"]) / 1000)
        sh0 = compact.get("shadow_kzt_kwh", [None])[0]
        bus.send("coordinator", {"for_t": t, "scenario_rev": rev, "x_json": dumps(dec["x"]),
                                 "charge_mw": round(dec["charge_mw"], 2), "bess_mw": round(dec["bess_mw"], 2),
                                 "maintenance_json": dumps(dec.get("maintenance", {})),
                                 "mode": mode, "why": why, "goal": goal, "shadow_kzt_kwh": sh0 if sh0 is not None else 0.0,
                                 "solve_ms": round(ms), "plan_json": dumps(compact),
                                 "feed_plan_tph": round(sum(map(sum, map(lambda l: map(sum, l), dec["x"]))))})
        log.info("t=%s %s %.0f ms  %s", t, mode, ms, why[:90])
        last_t = t


if __name__ == "__main__":
    main()
