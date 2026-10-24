"""Цена выбора цели координатора в деньгах: медь против энергии и ветряков.

Берёт годовые итоги из data/sizing.csv (ВЭС 300 + СЭС 250, медь и CO₂ с учётом
запасов) и эквивалент ВЭС из data/wind-equivalent.json. Цены — внешние, с датой:

  медь   14 441 $/т  LME cash, 21.10.2026 (reporteminero.cl, по данным Cochilco)
  курс   452,59 ₸/$  Нацбанк РК, 20.10.2026
  тариф  49,03 ₸/кВт·ч  params.py (РЭК «Рудный», юрлица с 01.10.2026)
  ВЭС    1 041 $/кВт  IRENA, Renewable Power Generation Costs in 2024 (полная стоимость, мир)
  доля оплачиваемой меди 0,85 — допущение params.py

Энергия считается по CO₂ с учётом запасов: ΔМВт·ч = ΔCO₂ / углеродоёмкость сети.
Стоимость накопителя, самосвалов и самих ВЭС/СЭС 300/250 одинакова во всех
вариантах и в разницу не входит.

Отдельно: цель «медь» с ВЭС на 150 МВт больше против управления «как сейчас»
при 300/250 — больше меди и меньше CO₂ одновременно (простая окупаемость без
эксплуатации, финансирования и присоединения к сети).

    python economics.py              # из team/tynys; пишет data/economics.json
"""
from pathlib import Path
import json

import pandas as pd

from tynys.params import aktogay

DATA = Path(__file__).resolve().parent / "data"
PRICES = {
    "copper_usd_t": 14441.0, "copper_source": "LME cash 21.10.2026 (reporteminero.cl / Cochilco)",
    "usd_kzt": 452.59, "usd_kzt_source": "Нацбанк РК, 20.10.2026",
    "wind_capex_usd_kw": 1041.0, "wind_capex_source": "IRENA, Renewable Power Generation Costs in 2024 (2025)",
}


def economics(wind=300, pv=250):
    p = aktogay()
    d = pd.read_csv(DATA / "sizing.csv")
    rows = d[(d.wind_mw == wind) & (d.pv_mwp == pv)].set_index("variant")
    eq = json.loads((DATA / "wind-equivalent.json").read_text(encoding="utf-8"))
    cu_usd = PRICES["copper_usd_t"] * p.cu_payable
    tariff_usd_mwh = p.tariff_kzt_kwh * 1000 / PRICES["usd_kzt"]
    base = rows.loc["V0"]
    out = {"wind_mw": wind, "pv_mwp": pv, "prices": {**PRICES, "cu_payable": p.cu_payable,
           "tariff_kzt_kwh": p.tariff_kzt_kwh, "grid_co2_t_mwh": p.grid_co2_t_mwh}, "variants": {}}
    for variant, label in (("V2", "цель «медь»"), ("V2green", "цель «CO₂»")):
        r = rows.loc[variant]
        d_cu = float(r.cu_adj_t - base.cu_adj_t)
        d_co2_kt = float(r.co2_adj_kt - base.co2_adj_kt)
        d_mwh = d_co2_kt * 1000 / p.grid_co2_t_mwh
        cu_musd = d_cu * cu_usd / 1e6
        energy_musd = -d_mwh * tariff_usd_mwh / 1e6
        net = cu_musd + energy_musd
        out["variants"][variant] = {
            "label": label, "d_cu_t": round(d_cu, 1), "d_co2_kt": round(d_co2_kt, 1),
            "d_grid_gwh": round(d_mwh / 1000, 1), "copper_musd": round(cu_musd, 1),
            "energy_musd": round(energy_musd, 1), "net_musd": round(net, 1),
            "usd_per_t_co2_avoided": round(-net * 1e6 / (-d_co2_kt * 1000), 0) if d_co2_kt < 0 else None,
        }
    out["wind_alternative"] = {
        "equivalent_mw": round(eq["equivalent_wind_mw"], 1),
        "equivalent_mw_per_t_cu": round(eq.get("equivalent_wind_mw_per_t_cu") or 0, 1),
        "capex_musd": round(eq["equivalent_wind_mw"] * PRICES["wind_capex_usd_kw"] / 1000, 0),
        "capex_musd_per_t_cu": round((eq.get("equivalent_wind_mw_per_t_cu") or 0) * PRICES["wind_capex_usd_kw"] / 1000, 0),
    }
    # Без компромисса: цель «медь» плюс ещё 150 МВт ВЭС против V0 при 300/250.
    plus = d[(d.wind_mw == wind + 150) & (d.pv_mwp == pv) & (d.variant == "V2")].iloc[0]
    d_cu = float(plus.cu_adj_t - base.cu_adj_t)
    d_co2_kt = float(plus.co2_adj_kt - base.co2_adj_kt)
    d_mwh = d_co2_kt * 1000 / p.grid_co2_t_mwh
    annual = d_cu * cu_usd / 1e6 - d_mwh * tariff_usd_mwh / 1e6
    capex = 150 * PRICES["wind_capex_usd_kw"] / 1000
    out["copper_goal_plus_150mw"] = {
        "wind_mw": wind + 150, "co2_kt": float(plus.co2_adj_kt), "cu_t": float(plus.cu_adj_t),
        "d_cu_t": round(d_cu, 1), "d_co2_kt": round(d_co2_kt, 1), "curtail_gwh": round(float(plus.curtail_mwh) / 1000, 1),
        "annual_musd": round(annual, 1), "capex_musd": round(capex, 0),
        "simple_payback_years": round(capex / annual, 1) if annual > 0 else None,
    }
    return out


def main():
    result = economics()
    (DATA / "economics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for v in result["variants"].values():
        per_t = f"; ≈ {v['usd_per_t_co2_avoided']:.0f} $ за т CO₂" if v["usd_per_t_co2_avoided"] else ""
        print(f"{v['label']:12s} медь {v['d_cu_t']:+.0f} т = {v['copper_musd']:+.1f} млн $; энергия {v['d_grid_gwh']:+.1f} ГВт·ч = "
              f"{v['energy_musd']:+.1f} млн $; итого {v['net_musd']:+.1f} млн $/год{per_t}")
    w = result["wind_alternative"]
    print(f"Те же CO₂ ветряками: {w['equivalent_mw_per_t_cu']:.0f}–{w['equivalent_mw']:.0f} МВт ВЭС ≈ "
          f"{w['capex_musd_per_t_cu']:.0f}–{w['capex_musd']:.0f} млн $ единоразово")
    c = result["copper_goal_plus_150mw"]
    print(f"Цель «медь» + ВЭС {c['wind_mw']}: медь {c['d_cu_t']:+.0f} т, CO₂ {c['d_co2_kt']:+.1f} тыс. т к V0 при {result['wind_mw']}; "
          f"{c['annual_musd']:+.1f} млн $/год, 150 МВт ≈ {c['capex_musd']:.0f} млн $, простая окупаемость ≈ {c['simple_payback_years']} года")


if __name__ == "__main__":
    main()
