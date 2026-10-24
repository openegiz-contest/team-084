"""Shared topology, equipment condition and named auxiliary loads.

All capacities, maintenance intervals and allocation of the calibrated auxiliary
budget are ASSUMPTIONS, not measured Aktogay equipment passports. One step = 1 h.
The same registry drives simulation, Ditto types/instances and telemetry.
"""
from dataclasses import dataclass, asdict

N_GROUPS = 14
N_CHARGER_GROUPS = 4


def shovel_for(i):
    return f"shovel-{i % 2 + 1}"


def charger_for(i):
    return f"charger-{i % N_CHARGER_GROUPS + 1}"


def asset_specs(p):
    specs = {
        "crusher": ("crusher", "Первичная дробилка", "plant"),
        "conveyor-crushed": ("conveyor", "Конвейер дроблёной руды", "plant"),
        "conveyor-feed": ("conveyor", "Конвейер питания фабрик", "plant"),
        "waste-dump": ("waste_dump", "Отвал вскрыши", "pit"),
        "water": ("water_pipeline", "Водовод и оборотная вода", "plant"),
        "tailings": ("tailings", "Хвостовое хозяйство", "plant"),
        "concentrate": ("concentrate", "Фильтрация и склад концентрата", "plant"),
        "dewatering": ("pump_station", "Водоотлив карьера", "pit"),
        "pit-services": ("auxiliary", "Освещение и службы карьера", "pit"),
        "workshops": ("auxiliary", "Ремонтные мастерские", "site"),
        "camp": ("auxiliary", "Вахтовый посёлок", "site"),
        "flotation": ("flotation", "Флотация", "plant"),
        "wind": ("wind_farm", "ВЭС (допущение)", "energy"),
        "pv": ("pv_farm", "СЭС (допущение)", "energy"),
        "bess": ("bess", "Накопитель (допущение)", "energy"),
        "substation": ("substation", "Подстанция 220 кВ", "energy"),
    }
    specs.update({f"shovel-{i}": ("shovel", f"Экскаватор {i}", "pit") for i in (1, 2)})
    specs.update({f"truck-{i+1:02d}": ("truck", f"Звено самосвалов {i+1:02d}", "pit") for i in range(N_GROUPS)})
    specs.update({f"charger-{i+1}": ("charger", f"Зарядная группа {i+1}", "pit") for i in range(N_CHARGER_GROUPS)})
    specs.update({f"line-{i+1}": ("mill_line", f"Линия измельчения {i+1}", "plant") for i in range(p.n_lines)})
    return specs


@dataclass
class Equipment:
    health: float = 1.0
    operating_h: float = 0.0
    since_service_h: float = 0.0
    elapsed_h: float = 0.0
    available_h: float = 0.0
    repair_remaining_h: int = 0
    maintenance_count: int = 0
    liner_operating_h: float = 0.0
    liner_replacements: int = 0


def equipment_state(p):
    return {name: Equipment() for name in asset_specs(p)}


def external_stop(env, name, t):
    for a, b in env.sc.equipment_down.get(name, []):
        if a <= t < b:
            return "fault", b - t
    for a, b in env.sc.equipment_maintenance.get(name, []):
        if a <= t < b:
            return "maintenance", b - t
    # Deterministic calendar shared by all controllers and counterfactuals.
    # No look-ahead into random failures: these are announced planned stops.
    if env.p.planned_stops:
        if name.startswith("line-") and not env.p.flexible_maintenance:
            phase = (t - 72 - 84*(int(name.split('-')[1])-1)) % 168
        elif name == "crusher":
            phase = (t - 240) % 336
        else:
            phase = 336
        if phase < env.p.service_duration_h:
            return "maintenance", env.p.service_duration_h - phase
    if name.startswith("line-") and not env.line_avail[int(name.split('-')[1])-1, t]:
        return "fault", 1
    if name == "bess" and not env.bess_avail[t]:
        return "fault", 1
    return "", 0


def capacity_factor(env, st, name, t, offset=0):
    """Known faults and remaining service time; used by both plant and controllers."""
    e = st.equipment.get(name, Equipment())
    from .maintenance import stop
    if external_stop(env, name, t)[0] or stop(st, name, t)[0] or e.repair_remaining_h > offset:
        return 0.0
    if e.since_service_h >= env.p.service_interval_h and offset < env.p.service_duration_h:
        return 0.0
    available = 1.0
    if name.startswith("truck-"):
        # Retain a deterministic subset of actual groups; no reassignment of
        # their stored energy to working trucks when a group fails.
        available = max(0., min(1., env.truck_mult[t]*N_GROUPS-(int(name.split("-")[1])-1)))
    elif name.startswith("shovel-"):
        available = env.shovel_mult[t]
    return max(0.0, min(1.0, e.health)) * available


def prepare_equipment(p, env, st, t):
    for name in asset_specs(p):
        e = st.equipment.setdefault(name, Equipment())
        if e.repair_remaining_h == 0 and (e.since_service_h >= p.service_interval_h or e.health <= 0):
            e.repair_remaining_h = p.service_duration_h
            e.maintenance_count += 1
    return {name: capacity_factor(env, st, name, t) for name in st.equipment}


def finish_equipment(p, env, st, t, telemetry, factors):
    from .maintenance import stop
    for name, e in st.equipment.items():
        f = telemetry.setdefault(name, {})
        reason, remaining = external_stop(env, name, t)
        if stop(st, name, t)[0]:
            reason, remaining = stop(st, name, t)
        if reason == "maintenance" and e.repair_remaining_h == 0 and (t == 0 or not (external_stop(env, name, t-1)[0] == "maintenance" or stop(st, name, t-1)[0])):
            e.maintenance_count += 1
        if e.repair_remaining_h:
            reason, remaining = "maintenance", max(remaining, e.repair_remaining_h)
        active = bool(f.get("active", False)) and factors[name] > 0
        e.elapsed_h += 1
        e.available_h += float(factors[name] > 0)
        if active:
            e.operating_h += 1
            e.since_service_h += 1
            e.liner_operating_h += float(name.startswith("line-"))
            e.health = max(0.0, e.health - p.equipment_wear_per_h)
        f.update(available=factors[name] > 0, health_pct=0.0 if reason == "fault" else 100 * e.health,
                 availability_pct=100 * e.available_h / e.elapsed_h,
                 operating_h=e.operating_h, repair_remaining_h=remaining,
                 maintenance_count=e.maintenance_count,
                 state=reason or ("running" if active else "idle"))
        f.pop("active", None)
        if e.repair_remaining_h:
            e.repair_remaining_h -= 1
            if not e.repair_remaining_h:
                e.health, e.since_service_h = 1.0, 0.0
        if reason == "maintenance" and remaining == 1:
            e.health, e.since_service_h = 1.0, 0.0
            if st.maintenance.get(name, {}).get("kind") == "liner":
                e.liner_operating_h = 0.
                e.liner_replacements += 1
        if name.startswith("line-"):
            item = st.maintenance.get(name, {})
            f.update(maintenance_start_h=item.get("start", -1), maintenance_deadline_h=item.get("deadline", -1),
                     maintenance_kind=item.get("kind", ""), maintenance_strategy=item.get("strategy", ""),
                     liner_remaining_pct=max(0., 100*(1-e.liner_operating_h/(4*168))),
                     liner_replacements=e.liner_replacements)


def auxiliary_coefficients(p, factors=None):
    """Per twin: (fixed MW, MW per t/h mined ore, MW per t/h mill feed).

    Sum at nominal flows = auxiliary_nominal_mw. Flow-dependent terms vanish
    at zero flow. Flotation's existing 3.5 kWh/t covers cells/regrinding only;
    water, tailings and filtration below are separate services.
    """
    m, q, b = p.mine_ore_tph, p.n_lines * p.line_q_nom, p.auxiliary_nominal_mw
    result = {
        "shovel-1": (0, .04*b/m, 0), "shovel-2": (0, .04*b/m, 0),
        "conveyor-crushed": (0, .03*b/m, 0), "conveyor-feed": (0, 0, .03*b/q),
        "water": (0, 0, .20*b/q), "tailings": (0, 0, .12*b/q),
        "concentrate": (0, 0, .06*b/q), "dewatering": (.14*b, 0, 0),
        "pit-services": (0, .10*b/m, 0), "workshops": (.06*b, .06*b/m, 0),
        "camp": (.12*b, 0, 0),
    }
    if factors is not None:
        result = {name: (fixed * (factors.get(name, 1) > 0),
                         cm * (name.startswith("shovel-") or factors.get(name, 1) > 0),
                         cq * (factors.get(name, 1) > 0))
                  for name, (fixed, cm, cq) in result.items()}
    return result


def load_coefficients(p, factors=None):
    co = list(auxiliary_coefficients(p, factors).values())
    return (sum(v[0] for v in co), p.crush_kwh_t/1000 + sum(v[1] for v in co),
            p.flot_kwh_t/1000 + sum(v[2] for v in co))


def process_factor(factors):
    return min(factors[n] for n in ("conveyor-feed", "water", "tailings", "concentrate", "flotation"))


def mining_capacity(p, factors):
    return min(p.mine_ore_tph * p.crusher_capacity_factor * factors["crusher"],
               p.mine_ore_tph * p.conveyor_capacity_factor * factors["conveyor-crushed"],
               p.mine_ore_tph * p.shovel_capacity_factor * factors["waste-dump"],
               p.mine_ore_tph * p.shovel_capacity_factor * factors["dewatering"])


def equipment_to_dict(st):
    return {k: asdict(e) for k, e in st.equipment.items()}
