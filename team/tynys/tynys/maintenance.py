"""Committed maintenance windows, separate from the hourly operating MILP.

One crew, fixed workload/deadline; V2 picks a forecast window with the largest
avoided grid purchase. V0/V1 keep nominal dates. This is a bounded scheduling
heuristic, not a claim of globally optimal maintenance or measured liner life.
"""
import copy
import math
import numpy as np
from . import weather as wx


def task(p, line, cycle):
    nominal = 72 + 84*line + 168*cycle
    liner = (cycle+1) % 4 == 0
    return {"nominal": nominal, "earliest": nominal-p.maintenance_window_h,
            "deadline": nominal+p.maintenance_window_h,
            "duration": p.liner_duration_h if liner else p.service_duration_h,
            "kind": "liner" if liner else "inspection"}


def validate_plan(p, plan):
    if not isinstance(plan, dict) or set(plan)-{f"line-{l+1}" for l in range(p.n_lines)}:
        raise ValueError("maintenance: unknown line")
    intervals = []
    for name, item in plan.items():
        if not isinstance(item, dict):
            raise ValueError("maintenance: invalid task")
        line = int(name.split("-")[1])-1
        nominal = item.get("nominal")
        if isinstance(nominal, bool) or not isinstance(nominal, int) or not 0 <= nominal <= 9000:
            raise ValueError("maintenance: invalid nominal hour")
        cycle = (nominal-72-84*line)/168
        if not isinstance(cycle, (int, float)) or not math.isfinite(cycle) or cycle < 0 or cycle != int(cycle):
            raise ValueError("maintenance: invalid cycle")
        expected = task(p, line, int(cycle))
        if any(item.get(k) != v for k,v in expected.items()):
            raise ValueError("maintenance: invalid window")
        start = item.get("start")
        if isinstance(start, bool) or not isinstance(start, int) or not expected["earliest"] <= start <= expected["deadline"]:
            raise ValueError("maintenance: deadline violation")
        if item.get("strategy") not in ("calendar", "forecast") or set(item) != set(expected)|{"start", "strategy", "forecast_grid_value_kzt"}:
            raise ValueError("maintenance: invalid strategy")
        value = item["forecast_grid_value_kzt"]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise ValueError("maintenance: invalid forecast value")
        end = start+item["duration"]
        if any(start < b and end > a for a,b in intervals):
            raise ValueError("maintenance: one crew cannot service two lines")
        intervals.append((start, end))
    return copy.deepcopy(plan)


def accept_plan(p, st, plan, t):
    checked = validate_plan(p, plan)
    for name, old in st.maintenance.items():
        if old["start"]+old["duration"] > t and checked.get(name) != old:
            raise ValueError("maintenance: cannot alter a committed task")
    st.maintenance = checked


def schedule(p, env, st, t, coordinated):
    if not p.planned_stops or not p.flexible_maintenance:
        return st.maintenance
    # Plan early enough to unload from maximum feed before the earliest start.
    lead = math.ceil((p.line_q_max-p.line_q_min)/max(p.line_q_nom*p.line_q_ramp_fraction, 1))+1
    for l in range(p.n_lines):
        name = f"line-{l+1}"
        old = st.maintenance.get(name)
        if old and old["start"]+old["duration"] > t:
            continue
        cycle = max(0, (t-(72+84*l+p.maintenance_window_h+p.liner_duration_h))//168+1)
        if old:
            cycle = max(cycle, (old["nominal"]-72-84*l)//168+1)
        item = task(p, l, cycle)
        if t < item["earliest"]-lead:
            continue
        # Include a whole task in the forecast. wx.forecast has deterministic,
        # horizon-dependent error; never rank windows by future actual weather.
        horizon = min(env.sc.n()-t, item["deadline"]+item["duration"]-t)
        if horizon < item["duration"]:
            continue
        wf, pf = wx.forecast(env.w, t, horizon, env.seed)
        renew = wf*env.wind_mult[t:t+horizon]*p.wind_mw+pf*p.pv_mwp
        nominal_load = p.n_lines*p.line_p_max_mw+p.auxiliary_nominal_mw
        avoided = np.minimum(p.line_p_max_mw, np.maximum(0., nominal_load-renew))
        prices = np.array([p.price_kzt_mwh((t+h)%24) for h in range(horizon)]) * env.tariff_mult[t:t+horizon]
        candidates = []
        for start in range(max(t, item["earliest"]), min(item["deadline"], t+horizon-item["duration"])+1):
            end = start+item["duration"]
            busy = any(other != name and start < v["start"]+v["duration"] and end > v["start"] for other,v in st.maintenance.items())
            busy |= any(start < b and end > a for other, periods in env.sc.equipment_maintenance.items()
                        if other.startswith("line-") and other != name for a,b in periods)
            if busy:
                continue
            value = float(np.sum(avoided[start-t:end-t]*prices[start-t:end-t]))
            candidates.append((start, value))
        if not candidates:
            raise ValueError("maintenance: no feasible window with one crew")
        start, value = (max(candidates, key=lambda v: (v[1], -v[0])) if coordinated else
                        min(candidates, key=lambda v: (abs(v[0]-item["nominal"]), v[0])))
        st.maintenance[name] = {**item, "start": int(start), "strategy": "forecast" if coordinated else "calendar",
                                "forecast_grid_value_kzt": value}
    return copy.deepcopy(st.maintenance)


def stop(st, name, t):
    item = st.maintenance.get(name)
    if item and item["start"] <= t < item["start"]+item["duration"]:
        return "maintenance", item["start"]+item["duration"]-t
    return "", 0


def feed_limit(p, st, name, t):
    item = st.maintenance.get(name)
    if not item or t >= item["start"]:
        return p.line_q_max
    return min(p.line_q_max, p.line_q_min+max(0, item["start"]-t-1)*p.line_q_nom*p.line_q_ramp_fraction)
