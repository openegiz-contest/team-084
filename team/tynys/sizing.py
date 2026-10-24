"""Решение руководства: сколько ВЭС и СЭС строить у Актогая.

Для каждой комбинации мощностей прогоняются на реальной погоде 2024 г.
(4 сезона × 14 суток) четыре варианта управления:
  V0      — как сейчас (без координации), P80 150 мкм;
  V2      — координатор, цель «медь» (P80 120–250 мкм);
  V2green — координатор, цель «CO₂» (P80 не тоньше 150 мкм; каждый МВт·ч из сети
            стоит одинаково — минимизируется объём из сети, а не счёт по зонам суток);
  V2fixed — координатор с P80 = 150 мкм, как у V0: отделяет эффект
            адаптации к ВИЭ от эффекта более тонкого помола. Результат —
data/sizing.csv с метаданными (sizing.json). Архив прежней модели — data/archive/.
"""
import itertools, os, sys, argparse, json, hashlib
from pathlib import Path
from dataclasses import replace
import pandas as pd
from tynys.params import aktogay
from tynys.sim import Scenario, run
from tynys.controllers import V0Traditional, V2Tynys
from tynys.metrics import summarize

GREEN = (150, 200, 250)   # «зелёная» цель: не молоть тоньше обычного

SEASONS = (15, 105, 196, 288)
DAYS = 14


def evaluate(p, ctl):
    agg = {}
    for doy in SEASONS:
        r = pd.DataFrame(run(p, Scenario(start_doy=doy, days=DAYS), ctl, 7))
        s = summarize(p, r, p.pile_cap_t * p.pile_init_frac)
        for k in ("cu_adj_t", "cu_t", "grid_mwh", "co2_adj_t", "curtail_mwh", "renew_share_pct"):
            agg[k] = agg.get(k, 0) + s[k] / len(SEASONS) * (1 if k == "renew_share_pct" else 365 / DAYS)
    agg["co2_kt"] = agg["grid_mwh"] * p.grid_co2_t_mwh / 1000
    # CO₂ с учётом запасов в конце прогонов (склады, заряд самосвалов и накопителя), см. metrics.grid_adjusted
    agg["co2_adj_kt"] = agg.pop("co2_adj_t") / 1000
    return agg


def main():
    rows = []
    parser = argparse.ArgumentParser()
    parser.add_argument("variants", nargs="*")
    parser.add_argument("--winds", nargs="+", type=float, default=[0,150,300,450,600])
    parser.add_argument("--pvs", nargs="+", type=float, default=[0,125,250,375,500])
    parser.add_argument("--output", type=Path, default=Path(__file__).parent/"data/sizing.csv")
    args = parser.parse_args()
    only, winds, pvs = args.variants, args.winds, args.pvs
    solver = {"time_limit": None, "node_limit": 16, "mip_rel_gap": .01}
    for w, s in itertools.product(winds, pvs):
        p = replace(aktogay(), wind_mw=w, pv_mwp=s)
        for name, ctl in (("V0", V0Traditional()), ("V2", V2Tynys(solver_options=solver)),
                          ("V2green", V2Tynys(grind_modes=GREEN, flat_price=True, solver_options=solver)),
                          ("V2fixed", V2Tynys(elastic_grind=False, solver_options=solver))):
            if only and name not in only:
                continue
            a = evaluate(p, ctl)
            rows.append({"wind_mw": w, "pv_mwp": s, "variant": name, **{k: round(v, 1) for k, v in a.items()}})
            print(rows[-1], flush=True)
    out = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, lineterminator="\n")
    meta = dict(model_version="physics-v4-geomet-maintenance", seasons=SEASONS, days=DAYS,
                seed=7, solver=solver, wind_mw=winds, pv_mwp=pvs,
                variants=sorted(out.variant.unique()), geomet="10.5281/zenodo.7051975",
                csv_sha256=hashlib.sha256(args.output.read_bytes().replace(b'\r\n', b'\n')).hexdigest())
    args.output.with_suffix(".json").write_text(json.dumps(meta, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
