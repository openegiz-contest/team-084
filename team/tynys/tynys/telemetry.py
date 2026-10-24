"""Units survive every /features replacement, not only twin creation."""
from numbers import Number

UNITS = {
    "soc": "%", "recovery": "%", "progress": "%", "hard_frac": "1",
    "tonnes": "t", "bwi_est": "kWh/t", "bwi_true": "kWh/t",
    "sim_hour": "h", "elapsed_hours": "h", "for_t": "h", "start_hour": "h",
    "start_doy": "d", "co2_t_h": "t/h", "co2_per_t_cu": "t CO2/t Cu",
    "price_kzt_mwh": "KZT/MWh", "shadow_kzt_kwh": "KZT/kWh", "solve_ms": "ms",
    "bwi_soft": "kWh/t", "bwi_hard": "kWh/t", "x_m": "m", "y_m": "m", "z_m": "m",
    "grid_cost_mkzt": "million KZT", "rate_tph": "t/h", "route_pos": "1",
}


def unit_for(name):
    if name in UNITS:
        return UNITS[name]
    for suffix, unit in (("_m3_h", "m3/h"), ("_m3", "m3"), ("_tph", "t/h"),
                         ("_mwh", "MWh"), ("_mw", "MW"), ("_pct", "%"),
                         ("_rpm", "rpm"), ("_um", "um"), ("_kt", "kt"),
                         ("_t", "t"), ("_h", "h")):
        if name.endswith(suffix):
            return unit
    return "1"


def features(values):
    out = {}
    for name, value in values.items():
        props = dict(value) if isinstance(value, dict) else {"value": value}
        if isinstance(props.get("value"), Number):
            props.setdefault("unit", unit_for(name))
        out[name] = {"properties": props}
    return out


CONDITION = {"state": "idle", "available": True, "health_pct": 100.0,
             "availability_pct": 100.0, "operating_h": 0.0,
             "repair_remaining_h": 0, "maintenance_count": 0}

KIND_FEATURES = {
    "shovel": {"rate_tph": 0., "ore_tph": 0., "waste_tph": 0., "capacity_tph": 0.},
    "truck": {"soc": 60., "energy_mwh": 0., "payload_t": 0., "route_pos": 0.,
              "ore_tph": 0., "waste_tph": 0., "charge_mw": 0., "assigned_shovel": "", "assigned_charger": ""},
    "charger": {"capacity_mw": 0., "groups_served": 0},
    "crusher": {"throughput_tph": 0., "capacity_tph": 0.},
    "conveyor": {"throughput_tph": 0.},
    "waste_dump": {"inflow_tph": 0., "tonnes": 0.},
    "water_pipeline": {"flow_m3_h": 0., "fresh_m3_h": 0., "recycle_m3_h": 0., "fresh_water_m3": 0.},
    "tailings": {"inflow_tph": 0., "tonnes": 0., "cu_tph": 0., "cu_t": 0., "retained_water_m3": 0.},
    "concentrate": {"inflow_tph": 0., "tonnes": 0., "cu_tph": 0., "grade_pct": 25.},
    "mill_line": {"feed_tph": 0., "mill_mw": 0., "p80_um": 0., "cu_tph": 0.,
                  "idle_mw": 0., "stop_reason": "",
                  "maintenance_start_h": -1, "maintenance_deadline_h": -1,
                  "maintenance_kind": "", "maintenance_strategy": "", "liner_remaining_pct": 100., "liner_replacements": 0,
                  "running": False, "lock_h": 0, "load_pct": 0., "speed_rpm": 0.},
    "flotation": {"feed_tph": 0., "recovery": 0., "cu_tph": 0., "feed_cu_tph": 0.},
    "wind_farm": {"capacity_mw": 0., "cf_pct": 0.}, "pv_farm": {"capacity_mw": 0.},
    "bess": {"soc": 50.}, "substation": {"grid_mw": 0., "grid_cap_mw": 0., "grid_nominal_mw": 0.,
        "price_kzt_mwh": 0., "co2_t_h": 0., "flex_down_mw": 0., "flex_down_h": 0.},
}


def initial_features(kind):
    return {**CONDITION, "power_mw": 0., **KIND_FEATURES.get(kind, {})}
