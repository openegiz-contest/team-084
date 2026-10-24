"""Часовая диспетчеризация 14 звеньев с собственными батареями.

Звенья закреплены за экскаватором и зарядной группой. Ограничения энергии,
времени зарядки, исправности и производительности применяются до добычи.
Энергия парка — сумма звеньев; остаток не распределяется искусственно.
"""
from dataclasses import dataclass, field
from typing import List

N_GROUPS = 14


@dataclass
class Fleet:
    e: List[float]                      # МВт·ч в каждом звене
    charging: List[bool] = field(default_factory=lambda: [False] * N_GROUPS)
    starved: List[bool] = field(default_factory=lambda: [False] * N_GROUPS)
    util: float = 1.0                   # загрузка хода самосвалов, 0..1
    charge_mw: List[float] = field(default_factory=lambda: [0.0] * N_GROUPS)
    ore_tph: List[float] = field(default_factory=lambda: [0.0] * N_GROUPS)
    waste_tph: List[float] = field(default_factory=lambda: [0.0] * N_GROUPS)
    available: List[bool] = field(default_factory=lambda: [True] * N_GROUPS)

    @classmethod
    def from_total(cls, total):
        return cls(e=[total / N_GROUPS] * N_GROUPS)


def group_caps(p):
    k = p.n_trucks / N_GROUPS
    cap = k * p.truck_batt_mwh
    return k, cap, cap * p.fleet_soc_min, cap * p.fleet_soc_max


def step_fleet(p, fl: Fleet, prev_total, rec, new_total):
    """Compatibility adapter for consumers of sim.step records."""
    import copy
    fl.__dict__.update(copy.deepcopy(rec["fleet"]))
    return fl


def group_view(p, fl: Fleet, i, phase):
    """Состояние звена для двойника. phase — только анимационная фаза рейса (0..1)."""
    k, cap, lo, hi = group_caps(p)
    if not fl.available[i]:
        state = "unavailable"
    elif fl.charging[i]:
        state = "charging"
    elif fl.starved[i]:
        state = "waiting"           # заряд на минимуме — ждёт зарядки
    elif fl.ore_tph[i] + fl.waste_tph[i] <= 1e-9:
        state = "idle"
    else:
        state = "loaded" if phase < 0.5 else "empty"
    haul_time = max(1e-9, 1-fl.charge_mw[i]/(k*p.charger_mw))
    utilization = min(1, (fl.ore_tph[i]+fl.waste_tph[i])/(k*p.truck_tph*haul_time))
    payload = k * p.truck_payload_t * utilization if state == "loaded" else 0.0
    from .assets import shovel_for, charger_for
    return {"state": state, "soc": round(100 * fl.e[i] / cap, 1), "energy_mwh": round(fl.e[i], 3),
            "payload_t": round(payload, 1), "route_pos": round(phase, 3),
            "ore_tph": fl.ore_tph[i], "waste_tph": fl.waste_tph[i],
            "charge_mw": fl.charge_mw[i], "assigned_shovel": shovel_for(i),
            "assigned_charger": charger_for(i), "available": fl.available[i]}


def dispatch(p, fl, factors, charge_request, mine_limit, haul_mwh_t):
    """Pure hourly dispatch: station -> assigned groups -> assigned shovel.

    No residual energy is invented or spread after the fact. A group spends
    charging energy/rated power hours charging and the rest hauling. Each
    group's own battery reserve bounds its ore and waste movements.
    """
    import copy
    from .assets import shovel_for, charger_for, N_CHARGER_GROUPS
    out = copy.deepcopy(fl)
    k, cap, lo, hi = group_caps(p)
    powers = [0.0] * N_GROUPS
    station_left = {f"charger-{j+1}": p.charge_mw_max / N_CHARGER_GROUPS * factors[f"charger-{j+1}"]
                    for j in range(N_CHARGER_GROUPS)}
    remaining = max(0.0, charge_request)
    for i in sorted(range(N_GROUPS), key=lambda i: fl.e[i]):
        if factors[f"truck-{i+1:02d}"] <= 0:
            continue
        station = charger_for(i)
        power = min(remaining, station_left[station], k * p.charger_mw * factors[f"truck-{i+1:02d}"],
                    max(0.0, hi - fl.e[i]) / p.eta_charge)
        powers[i] = power
        station_left[station] -= power
        remaining -= power
    capacities = []
    for i in range(N_GROUPS):
        f = factors[f"truck-{i+1:02d}"]
        time_hauling = max(0.0, 1 - powers[i] / (k * p.charger_mw))
        capacity = k * p.truck_tph * f * time_hauling / (1 + p.strip_ratio)
        energy = max(0.0, fl.e[i] + powers[i] * p.eta_charge - lo)
        capacities.append(min(capacity, energy / haul_mwh_t))
    for shovel in ("shovel-1", "shovel-2"):
        group = [i for i in range(N_GROUPS) if shovel_for(i) == shovel]
        total = sum(capacities[i] for i in group)
        limit = p.mine_ore_tph * p.shovel_capacity_factor / 2 * factors[shovel]
        scale = min(1.0, limit / total) if total else 0.0
        for i in group:
            capacities[i] *= scale
    total = sum(capacities)
    scale = min(1.0, max(0.0, mine_limit) / total) if total else 0.0
    out.ore_tph = [q * scale for q in capacities]
    out.waste_tph = [q * p.strip_ratio for q in out.ore_tph]
    out.charge_mw = powers
    out.available = [factors[f"truck-{i+1:02d}"] > 0 for i in range(N_GROUPS)]
    out.e = [fl.e[i] + powers[i] * p.eta_charge - out.ore_tph[i] * haul_mwh_t for i in range(N_GROUPS)]
    out.charging = [power > 1e-6 for power in powers]
    out.starved = [out.available[i] and out.e[i] <= lo + 1e-6 and out.ore_tph[i] < capacities[i] + 1e-6
                   for i in range(N_GROUPS)]
    out.util = min(1.0, sum(out.ore_tph) * (1 + p.strip_ratio) / (p.n_trucks * p.truck_tph))
    return out
