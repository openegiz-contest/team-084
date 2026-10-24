"""Воспроизводимые эксперименты «Тыныс». Запуск: python3 experiments.py [--quick]

Все варианты получают одинаковые: погоду (seed), план горных работ, руду,
оборудование, ВИЭ, накопитель и подключение к сети. Различаются только
архитектура (раздельные склады, эластичный помол) и управление.
"""
import sys, json, time, itertools
from dataclasses import replace
from multiprocessing import Pool
import pandas as pd
from tynys.params import Params
from tynys.sim import Scenario, run
from tynys.metrics import summarize
from tynys.controllers import V0Traditional, V1Reactive, V2Tynys

QUICK = "--quick" in sys.argv
OUT = "results"


def make_ctrl(key):
    return {
        "V0": lambda: V0Traditional(),
        "V1": lambda: V1Reactive(),
        "V2a": lambda: V2Tynys(segregation=False, elastic_grind=False, name="V2a: только MPC+прогноз"),
        "V2b": lambda: V2Tynys(segregation=True, elastic_grind=False, name="V2b: +арбитраж твёрдости"),
        "V2": lambda: V2Tynys(name="V2 Тыныс (полный)"),
        "V2naive": lambda: V2Tynys(use_forecast=False, name="V2 без прогноза погоды"),
    }[key]()


def scenarios():
    d = 14
    return {
        "base_winter": Scenario("base_winter", start_doy=15, days=30),
        "base_summer": Scenario("base_summer", start_doy=196, days=30),
        "S1_wind_lull": Scenario("S1_wind_lull", start_doy=15, days=d, wind_mult={(96, 168): 0.15}),
        "S2_line_loss": Scenario("S2_line_loss", start_doy=15, days=d, line_down={1: (120, 156)}),
        "S3_kegoc_dr": Scenario("S3_kegoc_dr", start_doy=15, days=d,
                                grid_cap={(24 * k + 17, 24 * k + 22): 12.0 for k in range(3, 8)}),
        "S4_harder_ore": Scenario("S4_harder_ore", start_doy=15, days=d, hard_frac_shift={72: 0.75}),
        "S5_combined": Scenario("S5_combined", start_doy=15, days=d, wind_mult={(96, 168): 0.15},
                                line_down={1: (120, 156)}, hard_frac_shift={72: 0.75}),
        "S6_plus10": Scenario("S6_plus10", start_doy=15, days=d, mine_mult={(0, 24 * d): 1.10}),
    }


def job(args):
    tag, sc, ckey, seed, overrides = args
    p = replace(Params(), **overrides)
    c = make_ctrl(ckey)
    t0 = time.time()
    df = pd.DataFrame(run(p, sc, c, seed))
    m = summarize(p, df, p.pile_cap_t * p.pile_init_frac)
    m.update(tag=tag, scenario=sc.name, ctrl=ckey, ctrl_name=c.name, seed=seed,
             overrides=json.dumps(overrides, ensure_ascii=False), runtime_s=time.time() - t0)
    if seed == 1 and not overrides:
        df.to_csv(f"{OUT}/ts_{sc.name}_{ckey}.csv", index=False)
    return m


def build_jobs():
    S = scenarios()
    seeds_main = [1, 2, 3] if QUICK else [1, 2, 3, 4, 5]
    seeds = [1, 2] if QUICK else [1, 2, 3]
    jobs = []
    for sc in ("base_winter", "base_summer"):
        for ck in ("V0", "V1", "V2a", "V2b", "V2", "V2naive"):
            for s in seeds_main:
                jobs.append(("main", S[sc], ck, s, {}))
    for sc in ("S1_wind_lull", "S2_line_loss", "S3_kegoc_dr", "S4_harder_ore", "S5_combined", "S6_plus10"):
        for ck in ("V0", "V1", "V2"):
            for s in seeds:
                jobs.append(("whatif", S[sc], ck, s, {}))
    short = replace(S["base_winter"], days=14)
    for gc in (20.0, 25.0, 40.0, 50.0):
        for ck in ("V0", "V1", "V2"):
            for s in seeds:
                jobs.append(("gridcap", short, ck, s, {"grid_cap_mw": gc}))
    for co2 in (20_000.0, 50_000.0, 100_000.0, 200_000.0):
        for s in seeds:
            jobs.append(("pareto", short, "V2", s, {"co2_price_kzt_t": co2}))
    for ov in ({"recovery_slope_per_100um": 0.03}, {"recovery_slope_per_100um": 0.10},
               {"pile_cap_t": 30_000.0}, {"pile_cap_t": 90_000.0}, {"bess_mwh": 0.0, "bess_mw": 0.0}):
        for ck in ("V1", "V2"):
            for s in seeds:
                jobs.append(("sens", short, ck, s, ov))
    # опорные точки 14-дневного окна без изменений (для gridcap/pareto/sens)
    for ck in ("V0", "V1", "V2"):
        for s in seeds:
            jobs.append(("ref14", short, ck, s, {}))
    return jobs


if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    jobs = build_jobs()
    # тяжёлые (V2, 30 дней) — первыми, для равномерной загрузки
    jobs.sort(key=lambda j: -(j[1].days * (10 if j[2].startswith("V2") else 1)))
    print(len(jobs), "прогонов")
    t0 = time.time()
    rows = []
    with Pool(2) as pool:
        for i, m in enumerate(pool.imap_unordered(job, jobs)):
            rows.append(m)
            if i % 10 == 0:
                print(f"{i+1}/{len(jobs)}  {time.time()-t0:.0f}s", flush=True)
                pd.DataFrame(rows).to_csv(f"{OUT}/runs.csv", index=False)
    pd.DataFrame(rows).to_csv(f"{OUT}/runs.csv", index=False)
    print("готово", time.time() - t0)
