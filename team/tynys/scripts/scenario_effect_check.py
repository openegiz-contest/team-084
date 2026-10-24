#!/usr/bin/env python3
"""Детерминированная проверка последствий what-if для меди, CO₂ и операционных KPI."""
import math

from tynys.controllers import V0Traditional
from tynys.live import scenario_from_events
from tynys.params import aktogay
from tynys.sim import Scenario, run

SEED = 271828
p = aktogay()
# Изолируем вклад диспетчеризации и событий: в этом smoke-тесте сеть углеродная,
# чтобы изменение нагрузки было видно в метрике CO₂ при любой погоде.
p.wind_mw = 0.0
p.pv_mwp = 0.0
controller = V0Traditional()


def measure(events=None):
    if events:
        sc = scenario_from_events(p, events, start_doy=15)
        sc.days = 2
    else:
        sc = Scenario(start_doy=15, days=2)
    rows = run(p, sc, controller, seed=SEED)
    return {
        "cu_t": sum(r["cu_t"] for r in rows),
        "co2_t": sum(r["grid"] * p.grid_co2_t_mwh for r in rows),
        "mine0": rows[0]["mine"],
        "grid0": rows[0]["grid"],
        "price0": rows[0]["price"],
        "cap0": rows[0]["grid_cap"],
        "plan0": rows[0]["mine_plan"],
    }

base = measure()
cases = {
    "line_trip": {"kind": "line_trip", "line": 1, "t0": 0, "dur": 24},
    "kegoc": {"kind": "kegoc", "grid_drop_mw": 80, "t0": 0, "dur": 24},
    "plan_up": {"kind": "plan_up", "mine_mult": 1.10, "t0": 0, "dur": 24},
    "truck_failure": {"kind": "truck_failure", "loss_pct": 50, "t0": 0, "dur": 24},
    "excavator_failure": {"kind": "excavator_failure", "loss_pct": 50, "t0": 0, "dur": 24},
    "grade_drop": {"kind": "grade_drop", "drop_pct": 50, "t0": 0, "dur": 24},
    "tariff_change": {"kind": "tariff_change", "change_pct": 50, "t0": 0, "dur": 24},
}
results = {name: measure([event]) for name, event in cases.items()}

assert results["grade_drop"]["cu_t"] < base["cu_t"], "падение содержания не уменьшило выпуск меди"
assert results["line_trip"]["cu_t"] < base["cu_t"], "авария линии не изменила выпуск меди"
assert results["line_trip"]["co2_t"] < base["co2_t"], "авария линии не изменила выбросы CO₂ сети"
assert results["kegoc"]["cap0"] == base["cap0"] - 80, "сценарий KEGOC не применил заданное ограничение"
assert results["plan_up"]["plan0"] > base["plan0"], "план +10 % не изменил план добычи"
assert results["truck_failure"]["mine0"] < base["mine0"], "поломка самосвала не ограничила вывоз"
assert results["excavator_failure"]["mine0"] < base["mine0"], "поломка экскаватора не ограничила добычу"
assert results["tariff_change"]["price0"] > base["price0"], "смена тарифа не изменила цену энергии"
for name, result in results.items():
    assert math.isfinite(result["cu_t"]) and math.isfinite(result["co2_t"]), f"{name}: нет KPI меди/CO₂"
    print(f"{name:18s} Δмедь={result['cu_t'] - base['cu_t']:+.2f} т; ΔCO₂={result['co2_t'] - base['co2_t']:+.2f} т")
print("SCENARIO EFFECTS OK")
