"""Reproducible, bounded counterfactual experiments from one Ditto snapshot.

The request lowers a CONNECTION LIMIT, not a promised demand response. Three
worlds share the same actual weather, ore and equipment events. Only the
reference has no additional grid restriction. Results are model checks, not
physical guarantees; a failed full request can have a separately tested half
request, and duration scans never claim to find a global maximum.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

import numpy as np

from .controllers import V1Reactive, V2Tynys
from .live import DAYS, EVENTS, scenario_from_events, state_from_dict
from .params import DOMAINS, aktogay
from .sim import Env, step
from .assets import asset_specs, Equipment
from .fleet import N_GROUPS, group_caps
from dataclasses import asdict

SCHEMA_VERSION = 1
MPC_HORIZON_H = 12
ENERGY_TOLERANCE_MWH = 1.0
COPPER_NUMERIC_TOLERANCE_T = 0.1
MINE_TOLERANCE_T = 1.0
DURATION_POINTS = (1, 2, 4, 6, 8, 12)
DEFAULT_REQUEST = {
    "id": "experiment", "reduction_mw": 80.0, "duration_h": 4,
    "lead_h": 2, "recovery_h": 24, "max_copper_loss_pct": 2.0,
    "lull": False, "bess_fault": False, "hard_ore": False, "mode": "evaluate",
}


class EvaluationCancelled(Exception):
    """The owning job was cancelled; no result must be published."""


def _number(value, name, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: требуется число")
    if not math.isfinite(value) or value < low or value > high:
        raise ValueError(f"{name}: допустимо от {low} до {high}")
    if integer and value != int(value):
        raise ValueError(f"{name}: требуется целое число")
    return int(value) if integer else float(value)


def validate_request(request):
    """Return a fresh normalized request; reject coercions, NaN and excess work."""
    if not isinstance(request, dict):
        raise ValueError("request: требуется объект")
    unknown = set(request) - set(DEFAULT_REQUEST)
    if unknown:
        raise ValueError("Неизвестные поля запроса: " + ", ".join(sorted(unknown)))
    out = {**DEFAULT_REQUEST, **request}
    if not isinstance(out["id"], str) or not 1 <= len(out["id"]) <= 80:
        raise ValueError("id: строка длиной 1–80 символов")
    if any(ord(c) < 32 for c in out["id"]):
        raise ValueError("id: управляющие символы запрещены")
    for k, lo, hi, integer in (
        ("reduction_mw", 0, 200, False), ("duration_h", 1, 12, True),
        ("lead_h", 0, 6, True), ("recovery_h", 24, 48, True),
        ("max_copper_loss_pct", 0, 10, False),
    ):
        out[k] = _number(out[k], k, lo, hi, integer)
    for k in ("lull", "bess_fault", "hard_ore"):
        if not isinstance(out[k], bool):
            raise ValueError(f"{k}: требуется true или false")
    if out["mode"] not in ("evaluate", "limit"):
        raise ValueError("mode: evaluate или limit")
    return out


def _snapshot(snapshot, request, p):
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot: требуется объект состояния")
    out = {}
    for k, lo, hi in (
        ("sim_hour", 0, DAYS * 24 - 1), ("start_doy", 1, 366),
        ("seed", 0, 2**31 - 1), ("scenario_rev", 0, 2**31 - 1),
    ):
        out[k] = _number(snapshot.get(k), k, lo, hi, True)
    out["goal"] = snapshot.get("goal", "green")
    if out["goal"] not in ("copper", "green"):
        raise ValueError("snapshot.goal: copper или green")
    duration = 12 if request["mode"] == "limit" else request["duration_h"]
    if out["sim_hour"] + request["lead_h"] + duration + request["recovery_h"] + MPC_HORIZON_H > DAYS * 24:
        raise ValueError("Горизонт выходит за модельный год; повторите после годового сброса стенда")
    events = snapshot.get("events", [])
    if not isinstance(events, list) or len(events) > 64:
        raise ValueError("snapshot.events: не более 64 событий")
    out["events"] = []
    for ev in events:
        if not isinstance(ev, dict) or ev.get("kind") not in EVENTS:
            raise ValueError("snapshot.events: неизвестное событие")
        k = ev["kind"]
        out["events"].append({
            "kind": k, "t0": _number(ev.get("t0"), "event.t0", 0, DAYS * 24, True),
            "dur": _number(ev.get("dur", EVENTS[k]["dur"]), "event.dur", 1, DAYS * 24, True),
        })
        limits = {
            "line_trip": ("line", 1, p.n_lines, True),
            "kegoc": ("grid_drop_mw", 0, p.grid_cap_mw, False),
            "plan_up": ("mine_mult", 0, 3, False),
            "truck_failure": ("loss_pct", 0, 100, False),
            "excavator_failure": ("loss_pct", 0, 100, False),
            "grade_drop": ("drop_pct", 0, 100, False),
            "tariff_change": ("change_pct", -90, 500, False),
        }
        if k in limits:
            key, lo, hi, integer = limits[k]
            out["events"][-1][key] = _number(ev.get(key, EVENTS[k][key]), "event."+key, lo, hi, integer)
    d = snapshot.get("state")
    if not isinstance(d, dict):
        raise ValueError("snapshot.state: требуется состояние из Ditto")
    try:
        state = {
            "pile": {k: _number(d["pile"][k], f"pile.{k}", 0, p.pile_cap_t) for k in DOMAINS},
            "fleet_e": _number(d["fleet_e"], "fleet_e", 0, p.n_trucks * p.truck_batt_mwh),
            "bess_e": _number(d["bess_e"], "bess_e", 0, p.bess_mwh),
            "bwi_est": {k: _number(d["bwi_est"][k], f"bwi_est.{k}", 1, 100) for k in DOMAINS},
            "line_on": list(d["line_on"]), "line_lock": list(d["line_lock"]),
        }
    except (KeyError, TypeError) as exc:
        raise ValueError("snapshot.state: неполное состояние") from exc
    if len(state["line_on"]) != p.n_lines or any(type(x) is not bool for x in state["line_on"]):
        raise ValueError("line_on: по одному bool на линию")
    if len(state["line_lock"]) != p.n_lines:
        raise ValueError("line_lock: по одному счётчику на линию")
    state["line_lock"] = [_number(x, "line_lock", 0, 24, True) for x in state["line_lock"]]
    process_fields = {"pile_cu", "line_x", "line_mw"}
    if process_fields & set(d):
        if not process_fields <= set(d):
            raise ValueError("process state: неполная история процесса")
        from .params import P80_MODES
        try:
            state["pile_cu"] = {k: _number(d["pile_cu"][k], f"pile_cu.{k}", 0, state["pile"][k]) for k in DOMAINS}
            a = np.asarray(d["line_x"], dtype=float)
            if a.shape != (p.n_lines, len(DOMAINS), len(P80_MODES)) or not np.isfinite(a).all() or np.any(a < 0):
                raise ValueError("line_x: неверная история подачи")
            if np.any(a.sum(axis=(1,2)) > p.line_q_max+1e-6) or np.any((a.sum(axis=1) > 1e-5).sum(axis=1) > 1):
                raise ValueError("line_x: несколько P80 или превышение подачи")
            if list(a.sum(axis=(1,2)) > 0) != state["line_on"]:
                raise ValueError("line_x: несовместимо с line_on")
            if len(d["line_mw"]) != p.n_lines:
                raise ValueError("line_mw: неверное число линий")
            state["line_x"] = a.tolist()
            state["line_mw"] = [_number(v, "line_mw", 0, p.line_p_max_mw) for v in d["line_mw"]]
            if any(bool(v > 0) != state["line_on"][l] for l,v in enumerate(state["line_mw"])):
                raise ValueError("line_mw: несовместимо с line_on")
        except (KeyError, TypeError) as exc:
            raise ValueError("process state: неполная история процесса") from exc
    # Preserve and validate all causal state. Dropping equipment or group
    geo_fields = {"pile_bwi_mass", "pile_recovery_cu"}
    if geo_fields & set(d):
        if not geo_fields <= set(d):
            raise ValueError("geology: incomplete stock assays")
        try:
            state["pile_bwi_mass"] = {k: _number(d["pile_bwi_mass"][k], f"pile_bwi_mass.{k}", 0, state["pile"][k]*100) for k in DOMAINS}
            state["pile_recovery_cu"] = {k: _number(d["pile_recovery_cu"][k], f"pile_recovery_cu.{k}", 0, state["pile_cu"][k]) for k in DOMAINS}
        except (KeyError, TypeError) as exc:
            raise ValueError("geology: incomplete stock assays") from exc
    if "maintenance" in d:
        from .maintenance import validate_plan
        state["maintenance"] = validate_plan(p, d["maintenance"])
    # batteries here would silently repair the counterfactual mine on replay.
    if "equipment" in d:
        if not isinstance(d["equipment"], dict) or set(d["equipment"]) - set(asset_specs(p)):
            raise ValueError("equipment: неизвестное оборудование")
        state["equipment"] = {}
        defaults = asdict(Equipment())
        for name, values in d["equipment"].items():
            if not isinstance(values, dict) or set(values) - set(defaults) or set(defaults)-{"liner_operating_h", "liner_replacements"}-set(values):
                raise ValueError("equipment: неполное состояние оборудования")
            values = {**defaults, **values}  # v3 snapshot migration
            checked = {k: _number(v, f"{name}.{k}", 0, 1 if k == "health" else 1e9,
                                   k in ("repair_remaining_h", "maintenance_count", "liner_replacements")) for k, v in values.items()}
            if checked["available_h"] > checked["elapsed_h"] or checked["operating_h"] > checked["available_h"]:
                raise ValueError("equipment: несовместимые счётчики часов")
            state["equipment"][name] = checked
    if "materials" in d:
        allowed = {"waste_t", "tailings_t", "concentrate_t", "tailings_cu_t", "fresh_water_m3", "retained_water_m3"}
        if not isinstance(d["materials"], dict) or set(d["materials"]) - allowed:
            raise ValueError("materials: неизвестный запас")
        state["materials"] = {k: _number(v, k, 0, 1e15) for k, v in d["materials"].items()}
    if "fleet" in d:
        state["fleet"] = None
        if d["fleet"] is not None:
            fleet = d["fleet"]
            fields = {"e", "charging", "starved", "util", "charge_mw", "ore_tph", "waste_tph", "available"}
            if not isinstance(fleet, dict) or set(fleet) != fields:
                raise ValueError("fleet: неполное состояние звеньев")
            checked = {"util": _number(fleet["util"], "fleet.util", 0, 1)}
            for key in fields - {"util"}:
                if not isinstance(fleet[key], list) or len(fleet[key]) != N_GROUPS:
                    raise ValueError("fleet: ожидается 14 звеньев")
                if key in ("charging", "starved", "available"):
                    if any(type(v) is not bool for v in fleet[key]):
                        raise ValueError("fleet: требуется bool")
                    checked[key] = list(fleet[key])
                else:
                    hi = group_caps(p)[1] if key == "e" else 1e9
                    checked[key] = [_number(v, f"fleet.{key}", 0, hi) for v in fleet[key]]
            if abs(sum(checked["e"]) - state["fleet_e"]) > 1e-6:
                raise ValueError("fleet: сумма энергии звеньев не равна энергии парка")
            state["fleet"] = checked
    out["state"] = state
    for key in ("source", "captured_at"):
        if key in snapshot:
            if not isinstance(snapshot[key], str) or len(snapshot[key]) > 240:
                raise ValueError(f"snapshot.{key}: требуется короткая строка")
            out[key] = snapshot[key]
    return out


def _environment(p, snapshot, request):
    env = Env(p, scenario_from_events(p, snapshot["events"], snapshot["start_doy"]), snapshot["seed"])
    # The live event schema can contain several equipment failures. Preserve
    # the union instead of letting Scenario's single interval hide an earlier one.
    for ev in snapshot["events"]:
        a, b = ev["t0"], ev["t0"] + ev["dur"]
        if ev["kind"] == "bess_fault":
            env.bess_avail[a:b] = False
        elif ev["kind"] == "line_trip":
            env.line_avail[ev.get("line", 2)-1, a:b] = False
    a = snapshot["sim_hour"] + request["lead_h"]
    if request["lull"]:
        env.w["wind_pu"][a:a + 24] *= 0.08
        env.wind_mult[a:a + 24] *= 0.08
    if request["bess_fault"]:
        env.bess_avail[a:a + 12] = False
    if request["hard_ore"]:
        env.hard_frac[a:a + 72] = np.clip(env.hard_frac[a:a + 72] + 0.3, 0.05, 0.95)
        env.sc.hard_frac_shift.update({a: .8, a+72: p.hard_frac_base})
        if p.geomet:
            from .geology import install
            install(env)
    return env


def _restricted(env, p, snapshot, request):
    changed = copy.copy(env)
    changed.grid_cap = env.grid_cap.copy()
    a = snapshot["sim_hour"] + request["lead_h"]
    b = a + request["duration_h"]
    # Existing KEGOC events may already impose a lower limit. Never relax them.
    changed.grid_cap[a:b] = np.minimum(changed.grid_cap[a:b], p.grid_cap_mw - request["reduction_mw"])
    return changed


def _phase(h, request):
    if h < request["lead_h"]:
        return "prepare"
    if h < request["lead_h"] + request["duration_h"]:
        return "request"
    return "recovery"


def _controller(goal):
    # A deterministic node budget is reproducible across repeated evaluations;
    # a wall-clock cutoff could choose different incumbent plans under load.
    return V2Tynys(
        grind_modes=(150, 200, 250) if goal == "green" else None,
        flat_price=goal == "green",
        solver_options={"time_limit": None, "node_limit": 16, "mip_rel_gap": 0.01},
    )


def _check_cancelled(cancelled):
    if cancelled is not None and cancelled():
        raise EvaluationCancelled("Расчёт отменён")


def _run(p, env, snapshot, request, controller, progress, cancelled, label):
    state = state_from_dict(copy.deepcopy(snapshot["state"]))
    n = request["lead_h"] + request["duration_h"] + request["recovery_h"]
    records = []
    copper = 0.0
    for h in range(n):
        _check_cancelled(cancelled)
        t = snapshot["sim_hour"] + h
        decision = controller.decide(p, env, state, t)
        raw = step(p, env, state, t, decision, controller.segregated)
        copper += raw["cu_t"]
        explanations = [
            {"object": "substation", "text": f"Предел {raw['grid_cap']:.0f} МВт; фактическое потребление сети {raw['grid']:.1f} МВт."},
            {"object": "charger", "text": f"Зарядка {raw['charge']:.1f} МВт; флот {state.fleet_e:.1f} МВт·ч."},
        ]
        for name, item in state.maintenance.items():
            if item["start"] <= t < item["start"]+item["duration"]:
                job = "замена футеровки" if item["kind"] == "liner" else "плановое ТО"
                explanations.append({"object": name, "text": f"{job}: окно {item['start']}–{item['start']+item['duration']}, линия недоступна."})
        if not env.bess_avail[t]:
            explanations.append({"object": "bess", "text": "Накопитель недоступен: заряд и разряд равны нулю."})
        elif abs(raw["bess"]) > 0.5:
            explanations.append({"object": "bess", "text": f"Накопитель {'отдаёт' if raw['bess'] > 0 else 'принимает'} {abs(raw['bess']):.1f} МВт."})
        if raw["trips"]:
            explanations.append({"object": "plant", "text": f"Аварийных отключений за час: {raw['trips']}."})
        if raw["spilled"] > 0.1:
            explanations.append({"object": "pile-hard", "text": f"Не размещено на складах {raw['spilled']:.0f} т руды."})
        if raw["unserved"] > 0.01:
            explanations.append({"object": "substation", "text": f"Не обеспечено {raw['unserved']:.1f} МВт оставшейся нагрузки."})
        if getattr(controller, "last_fallback", False):
            explanations.append({"object": "coordinator", "text": "MPC не нашёл допустимый план в бюджете: применено правило V1."})
        rec = {
            "hour": h, "simulation_hour": t, "phase": _phase(h, request),
            "grid_mw": raw["grid"], "cap_mw": raw["grid_cap"],
            "wind_mw": raw["wind"], "pv_mw": raw["pv"], "load_mw": raw["load"],
            "cu_t": raw["cu_t"], "cumulative_cu_t": copper, "feed_tph": raw["feed"],
            "mine_tph": raw["mine"], "mine_plan_tph": raw["mine_plan"],
            "pile_soft_t": raw["pile_soft"], "pile_hard_t": raw["pile_hard"],
            "bess_mwh": raw["bess_e"], "fleet_mwh": raw["fleet_e"],
            "bess_mw": raw["bess"], "charge_mw": raw["charge"],
            "line1_tph": raw["line0"], "line2_tph": raw["line1"],
            "unserved_mw": raw["unserved"], "trips": raw["trips"],
            "spilled_t": raw["spilled"], "explanations": explanations,
            "waste_tph": raw["waste_tph"], "tailings_tph": raw["tailings_tph"],
            "concentrate_tph": raw["concentrate_tph"], "fresh_water_m3_h": raw["fresh_water_m3_h"],
            "fallback": bool(getattr(controller, "last_fallback", False)),
        }
        # No NaN from p80 (undefined for stopped lines) is exposed by this API.
        records.append({k: float(v) if isinstance(v, np.floating) else int(v) if isinstance(v, np.integer) else v for k, v in rec.items()})
        if progress:
            progress({"stage": label, "completed_h": h + 1, "total_h": n})
    summary = {
        "copper_t": copper, "grid_mwh": sum(r["grid_mw"] for r in records),
        "co2_t": sum(r["grid_mw"] for r in records) * p.grid_co2_t_mwh,
        "ore_mined_t": sum(r["mine_tph"] for r in records),
        "unserved_mwh": sum(r["unserved_mw"] for r in records),
        "trips": sum(r["trips"] for r in records),
        "spilled_t": sum(r["spilled_t"] for r in records),
        "fallback_steps": getattr(controller, "fallback_count", 0),
        "solver_limited_steps": getattr(controller, "limited_count", 0),
    }
    return records, summary


def _reason(code, object_id, title, hour, detail):
    return {"code": code, "object": object_id, "title": title, "hour": hour, "detail": detail}


def _assessment(p, request, records, reference, summary, reference_summary):
    start, end = request["lead_h"], request["lead_h"] + request["duration_h"]
    window = records[start:end]
    actual_saved = sum(ref["grid_mw"] - rec["grid_mw"] for rec, ref in zip(window, reference[start:end]))
    cap_excess = sum(max(0, r["grid_mw"] - r["cap_mw"]) for r in window)
    delivery = {
        "requested_cap_mw": p.grid_cap_mw - request["reduction_mw"],
        "window_h": request["duration_h"], "actual_grid_reduction_mwh": actual_saved,
        "actual_grid_reduction_avg_mw": actual_saved / request["duration_h"],
        "cap_excess_mwh": cap_excess,
    }
    debt_cu = max(0.0, reference_summary["copper_t"] - summary["copper_t"])
    copper_loss_pct = 100 * debt_cu / max(reference_summary["copper_t"], 1e-9)
    last, ref_last = records[-1], reference[-1]
    bess_debt = max(0.0, ref_last["bess_mwh"] - last["bess_mwh"])
    fleet_debt = max(0.0, ref_last["fleet_mwh"] - last["fleet_mwh"])
    copper_allowance = max(COPPER_NUMERIC_TOLERANCE_T, reference_summary["copper_t"] * request["max_copper_loss_pct"] / 100)
    recovered = None
    # "Recovered" means the debt remains within tolerance through the endpoint,
    # not merely a single lucky crossing followed by renewed borrowing.
    for h in range(len(records) - 1, end - 1, -1):
        a, b = records[h], reference[h]
        energy = max(0, b["bess_mwh"] - a["bess_mwh"]) + max(0, b["fleet_mwh"] - a["fleet_mwh"])
        if energy > ENERGY_TOLERANCE_MWH or b["cumulative_cu_t"] - a["cumulative_cu_t"] > COPPER_NUMERIC_TOLERANCE_T:
            break
        recovered = h + 1
    recovery = {
        "copper_debt_end_t": debt_cu, "copper_loss_pct": copper_loss_pct,
        "energy_debt_end_mwh": bess_debt + fleet_debt,
        "bess_debt_end_mwh": bess_debt, "fleet_debt_end_mwh": fleet_debt,
        "extra_grid_mwh": sum(r["grid_mw"] - q["grid_mw"] for r, q in zip(records[end:], reference[end:])),
        "recovered_at_hour": recovered, "recovery_h": request["recovery_h"],
        "allowed_copper_debt_t": copper_allowance,
        "ore_debt_end_t": max(0.0, reference_summary["ore_mined_t"] - summary["ore_mined_t"]),
    }
    reasons = []
    checks = (
        ("unserved", "substation", "Не обеспечена нагрузка", "unserved_mw", 0.01, "МВт"),
        ("trip", "plant", "Аварийный останов линии", "trips", 0, "отключений"),
        ("overflow", "pile-hard", "Переполнение складов", "spilled_t", 0.1, "т"),
    )
    for code, obj, title, key, tolerance, unit in checks:
        match = next((r for r in records if r[key] > tolerance), None)
        if match:
            reasons.append(_reason(code, obj, title, match["hour"], f"За час {match['hour']}: {match[key]:.2f} {unit}."))
    if cap_excess > 0.01:
        reasons.append(_reason("grid_cap", "substation", "Превышен предел сети", start, f"Превышение {cap_excess:.3f} МВт·ч."))
    if recovery["ore_debt_end_t"] > MINE_TOLERANCE_T:
        reasons.append(_reason("mining_debt", "pit", "Не восстановлена добыча", len(records) - 1,
                               f"К концу горизонта добыто на {recovery['ore_debt_end_t']:.1f} т меньше, чем без нового ограничения."))
    if debt_cu > copper_allowance:
        reasons.append(_reason("copper_loss", "flotation", "Потеря меди выше допуска", len(records) - 1,
                               f"Долг {debt_cu:.2f} т ({copper_loss_pct:.2f} %); допуск {request['max_copper_loss_pct']:.2f} %."))
    if bess_debt + fleet_debt > ENERGY_TOLERANCE_MWH:
        reasons.append(_reason("energy_debt", "bess" if bess_debt >= fleet_debt else "charger", "Не восстановлен запас энергии",
                               len(records) - 1, f"Долг накопителя {bess_debt:.2f}, флота {fleet_debt:.2f} МВт·ч относительно контрольного будущего."))
    reasons.sort(key=lambda r: (r["hour"], r["code"]))
    verdict = {
        "status": "refused" if reasons else "feasible",
        "title": "Запрос не прошёл проверку" if reasons else "Запрос выполним в этом модельном сценарии",
        "reasons": reasons, "tested_reduction_mw": request["reduction_mw"], "alternative": None,
    }
    return verdict, delivery, recovery


def evaluate(request, snapshot, progress=None, cancelled=None):
    """Compute independent futures. No network, global RNG or snapshot mutation.

    progress receives {stage, completed_h, total_h}; cancelled is a zero-argument
    predicate. Computation is bounded by the input horizon and MILP node budget.
    """
    request = validate_request(request)
    p = aktogay()
    p.mpc_horizon_h = MPC_HORIZON_H
    snapshot = _snapshot(snapshot, request, p)
    env = _environment(p, snapshot, request)
    restricted = _restricted(env, p, snapshot, request)
    baseline, baseline_summary = _run(p, restricted, snapshot, request, V1Reactive(), progress, cancelled, "baseline")
    reference, reference_summary = _run(p, env, snapshot, request, _controller(snapshot["goal"]), progress, cancelled, "reference")
    if np.array_equal(restricted.grid_cap, env.grid_cap):
        tynys, tynys_summary = copy.deepcopy(reference), copy.deepcopy(reference_summary)
    else:
        tynys, tynys_summary = _run(p, restricted, snapshot, request, _controller(snapshot["goal"]), progress, cancelled, "tynys")
    verdict, delivery, recovery = _assessment(p, request, tynys, reference, tynys_summary, reference_summary)
    if verdict["status"] == "refused" and request["reduction_mw"] > 0 and request["mode"] == "evaluate":
        smaller = {**request, "reduction_mw": request["reduction_mw"] / 2}
        alternative, alt_summary = _run(p, _restricted(env, p, snapshot, smaller), snapshot, smaller,
                                        _controller(snapshot["goal"]), progress, cancelled, "alternative")
        alt_verdict, _, alt_recovery = _assessment(p, smaller, alternative, reference, alt_summary, reference_summary)
        if alt_verdict["status"] == "feasible":
            verdict["status"] = "partial"
            verdict["title"] = "Полный запрос не прошёл; проверен меньший вариант"
            verdict["alternative"] = {
                "reduction_mw": smaller["reduction_mw"], "cap_mw": p.grid_cap_mw - smaller["reduction_mw"],
                "status": "feasible", "title": f"Проверено снижение предела на {smaller['reduction_mw']:.1f} МВт",
                "recovery": alt_recovery,
            }
    boundary = []
    if request["mode"] == "limit":
        for duration in DURATION_POINTS:
            _check_cancelled(cancelled)
            varied = {**request, "duration_h": duration}
            if duration == request["duration_h"]:
                point_verdict, point_recovery = verdict, recovery
            else:
                ref, ref_total = _run(p, env, snapshot, varied, _controller(snapshot["goal"]), progress, cancelled, f"limit_reference_{duration}")
                case, case_total = _run(p, _restricted(env, p, snapshot, varied), snapshot, varied,
                                        _controller(snapshot["goal"]), progress, cancelled, f"limit_{duration}")
                point_verdict, _, point_recovery = _assessment(p, varied, case, ref, case_total, ref_total)
            boundary.append({
                "duration_h": duration, "status": point_verdict["status"], "reasons": point_verdict["reasons"],
                "copper_loss_pct": point_recovery["copper_loss_pct"],
                "energy_debt_end_mwh": point_recovery["energy_debt_end_mwh"],
            })
    first_failed = next((x for x in boundary if x["status"] != "feasible"), None)
    n = len(tynys)
    t0 = snapshot["sim_hour"]
    fingerprint = hashlib.sha256()
    for a in (env.w["wind_pu"], env.w["pv_pu"], env.hard_frac, env.mine_plan, env.bess_avail,
              env.truck_mult, env.shovel_mult, env.tariff_mult):
        fingerprint.update(np.asarray(a[t0:t0 + n]).tobytes())
    fingerprint.update(env.line_avail[:,t0:t0+n].tobytes())
    for d in DOMAINS:
        fingerprint.update(env.grade_true[d][t0:t0+n].tobytes())
        fingerprint.update(env.bwi_true[d][t0:t0+n].tobytes())
        fingerprint.update(env.recovery_true[d][t0:t0+n].tobytes())
    fingerprint.update(json.dumps({d:ids[t0:t0+n] for d,ids in env.geology_ids.items()}, sort_keys=True).encode())
    fingerprint.update(json.dumps([env.sc.equipment_down, env.sc.equipment_maintenance],
                                  sort_keys=True, separators=(",",":")).encode())
    result = {
        "schema_version": SCHEMA_VERSION, "model_version": "physics-v4-geomet-maintenance", "request": request,
        "snapshot": {**copy.deepcopy(snapshot),
                     "weather_source": env.w.get("source", "Синтетическая погода"),
                     "disturbance_sha256": fingerprint.hexdigest()},
        "limits": {
            "line_nominal_tph": p.line_q_nom, "mine_nominal_tph": p.mine_ore_tph,
            "grid_base_mw": p.grid_cap_mw, "requested_cap_mw": p.grid_cap_mw - request["reduction_mw"],
            "model_horizon_h": n, "step_h": 1, "mpc_horizon_h": MPC_HORIZON_H,
            "claim": "Проверено на этом модельном сценарии",
            "request_semantics": "Снижение предела подключения; фактическое снижение потребления вычисляется отдельно.",
            "copper_loss_tolerance_pct": request["max_copper_loss_pct"],
            "energy_debt_tolerance_mwh": ENERGY_TOLERANCE_MWH,
            "copper_debt_tolerance_t": COPPER_NUMERIC_TOLERANCE_T,
            "added_stress_duration_h": {"lull": 24, "bess_fault": 12, "hard_ore": 72},
            "solver": {"name": "SciPy HiGHS MILP", "node_limit": 16, "mip_rel_gap": 0.01},
            "capacities": {"pile_t": p.pile_cap_t, "bess_mwh": p.bess_mwh,
                           "fleet_mwh": p.n_trucks * p.truck_batt_mwh,
                           "wind_mw": p.wind_mw, "pv_mw": p.pv_mwp},
            "pile_capacity_t": p.pile_cap_t, "bess_capacity_mwh": p.bess_mwh,
            "fleet_capacity_mwh": p.n_trucks * p.truck_batt_mwh,
        },
        "verdict": verdict,
        "frames": [{"hour": h, "phase": _phase(h, request), "baseline": baseline[h], "tynys": tynys[h], "reference": reference[h]} for h in range(n)],
        "summary": {"baseline": baseline_summary, "tynys": tynys_summary, "reference": reference_summary,
                    "delivery": delivery, "recovery": recovery},
        "boundary": boundary, "first_failed": first_failed,
    }
    # Validate the public wire format before the job can be marked successful.
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    _check_cancelled(cancelled)
    return result
