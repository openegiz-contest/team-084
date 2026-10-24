#!/usr/bin/env python3
"""Создаёт двойники рудника Актогай в Eclipse Ditto (идемпотентные PUT).

Иерархия (attributes._parents): site → pit / plant / energy → оборудование.
"""
import sys, time
from platform_client import http, NS, wait_ditto  # noqa
from tynys.telemetry import features as feature_document

SITE = "Актогай (KAZ Minerals), обл. Абай — режим «Тыныс»"


def t(name, title, kind, parent=None, feats=None, **attrs):
    a = {"name": title, "kind": kind, "_isType": False, **attrs}
    if parent:
        a["_parents"] = f"{NS}:{parent}"
    return name, {"policyId": "default:basic_policy", "attributes": a,
                  "features": feature_document(feats or {})}


def twins():
    from tynys.params import aktogay
    from tynys.assets import asset_specs, shovel_for, charger_for, auxiliary_coefficients
    from tynys.telemetry import initial_features
    p = aktogay()
    out = [
        t("site", SITE, "mine", None, {"sim_hour": 0, "cu_t": 0.0}, lat=p.lat, lon=p.lon,
          source="KAZ Minerals Annual Report 2024; Open-Meteo ERA5; GeoMet v4 analogue", model_version="physics-v4-geomet-maintenance"),
        t("pit", "Карьер Актогай", "pit", "site", {"ore_tph": 0., "waste_tph": 0., "hard_frac": .5}),
        t("plant", "Обогатительные фабрики", "plant", "site", {"feed_tph": 0.}),
        t("energy", "Энергосистема рудника", "energy", "site", {"load_mw": 0.}),
        t("coordinator", "Координатор «Тыныс» (MPC 24 ч)", "coordinator", "site", {"for_t": -1}),
        t("scenario", "Сценарии what-if", "scenario", "site", {"events": "[]", "rev": 0, "goal": "green"}),
        t("future-request", "Запрос проверки обещания", "experiment_request", "site", {"request_json": ""}),
        t("future-result", "Два будущих: результат расчёта", "experiment_result", "site",
          {"status": "idle", "request_id": "", "progress": 0, "stage": "", "result_json": "", "error": "", "updated_at": ""}),
        t("shadow-v0", "Тень V0: как сейчас", "shadow", "site", {"cu_t": 0.}),
        t("shadow-v1", "Тень V1: простые правила", "shadow", "site", {"cu_t": 0.}),
    ]
    for name, (kind, title, parent) in asset_specs(p).items():
        attrs = {"assumption": "Часовая агрегированная модель; параметры не являются паспортами оборудования Актогая",
                 "service_interval_h": p.service_interval_h, "service_duration_h": p.service_duration_h}
        if name in auxiliary_coefficients(p):
            a, b, c = auxiliary_coefficients(p)[name]
            attrs["load_model"] = {"fixed_mw": a, "mw_per_ore_tph": b, "mw_per_feed_tph": c}
        if kind == "truck":
            i = int(name.split('-')[1])-1
            attrs.update(assigned_shovel=f"{NS}:{shovel_for(i)}", assigned_charger=f"{NS}:{charger_for(i)}",
                         trucks_per_group=p.n_trucks/14, payload_per_truck_t=p.truck_payload_t)
        if kind == "mill_line":
            from tynys.physics import mill_idle_mw
            attrs.update(idle_mw=mill_idle_mw(p), q_ramp_tph_h=p.line_q_nom*p.line_q_ramp_fraction,
                         power_ramp_mw_h=p.line_p_max_mw*p.line_power_ramp_fraction)
        out.append(t(name, title, kind, parent, initial_features(kind), **attrs))
    for domain in ("soft", "hard"):
        out.append(t(f"pile-{domain}", f"Склад руды {domain}", "stockpile", "plant",
                     {"tonnes": 0., "fill_pct": 0., "cu_t": 0., "grade_pct": 100*p.cu_grade[domain],
                      "bwi_est": p.bwi[domain], "bwi_true": p.bwi[domain]},
                     domain=domain, capacity_t=p.pile_cap_t))
    d = dict(out)
    from tynys.geology import model
    _, d["geology"] = t("geology", "Геология GeoMet — пространственный аналог", "geology", "pit",
        {"active_soft": "", "active_hard": "", "analogue": True,
         "bwi_soft": p.bwi["soft"], "bwi_hard": p.bwi["hard"],
         "grade_soft_pct": 100*p.cu_grade["soft"], "grade_hard_pct": 100*p.cu_grade["hard"],
         "recovery_soft_pct": 100*p.r150["soft"], "recovery_hard_pct": 100*p.r150["hard"]}, model=model(),
        source="https://doi.org/10.5281/zenodo.7051975", license="CC BY 4.0",
        assumption="GeoMet не является геологией Актогая; XYZ отображены в схематическом карьере")
    ref = lambda *names: [f"{NS}:{name}" for name in names]
    links = {
        **{f"shovel-{j}": {"loads": ref(*[f"truck-{i+1:02d}" for i in range(14) if shovel_for(i) == f"shovel-{j}"])} for j in (1,2)},
        **{f"truck-{i+1:02d}": {"loaded_by": ref(shovel_for(i)), "charged_by": ref(charger_for(i)),
                                 "ore_to": ref("crusher"), "waste_to": ref("waste-dump")} for i in range(14)},
        "crusher": {"feeds": ref("conveyor-crushed")},
        "conveyor-crushed": {"feeds": ref("pile-soft", "pile-hard")},
        "pile-soft": {"feeds": ref("conveyor-feed")}, "pile-hard": {"feeds": ref("conveyor-feed")},
        "conveyor-feed": {"feeds": ref(*[f"line-{i+1}" for i in range(p.n_lines)])},
        **{f"line-{i+1}": {"feeds": ref("flotation")} for i in range(p.n_lines)},
        "flotation": {"concentrate_to": ref("concentrate"), "tailings_to": ref("tailings"), "water_from": ref("water")},
        "tailings": {"returns_water_to": ref("water")}, "water": {"supplies": ref("flotation")},
        "wind": {"supplies": ref("substation")}, "pv": {"supplies": ref("substation")},
        "bess": {"exchanges_with": ref("substation")},
        "coordinator": {"sets_points_for": ref("line-1", "line-2", "charger-1", "charger-2", "charger-3", "charger-4", "bess")},
        "geology": {"assays_for": ref("pit", "pile-soft", "pile-hard"), "informs": ref("coordinator")},
    }
    consumers = [name for name, (kind, _, _) in asset_specs(p).items()
                 if kind not in ("truck", "wind_farm", "pv_farm", "bess", "substation", "waste_dump")]
    links["substation"] = {"grid": "KEGOC 220 кВ", "supplies": ref(*consumers)}
    for name in consumers:
        links.setdefault(name, {})["powered_by"] = ref("substation")
    for name, rel in links.items():
        d[name]["attributes"]["links"] = rel
    # OpenTwins uses attributes.type to associate instances with reusable types.
    types = {}
    import copy
    for name, body in d.items():
        kind = body["attributes"]["kind"]
        type_name = f"type-{kind}"
        body["attributes"]["type"] = f"{NS}:{type_name}"
        if type_name not in types:
            types[type_name] = {"policyId": "default:basic_policy",
                                "attributes": {"name": f"Тип: {kind}", "kind": kind, "_isType": True},
                                "features": copy.deepcopy(body["features"])}
        else:
            types[type_name]["features"].update(copy.deepcopy(body["features"]))
    # Текущие предрасчёты (data/sizing.csv, data/flex.csv) — на той же физике, что стенд;
    # результаты прежней агрегированной модели доступны отдельно как архив.
    from pathlib import Path
    import json
    data_dir = Path(__file__).resolve().parents[1]/"data"
    def report(name):
        path = data_dir/name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    current = report("wind-equivalent.json")
    d["energy"]["attributes"].update(
        sizing=sizing(), sizing_model=report("sizing.json").get("model_version", "unknown"),
        sizing_archive=csv_rows("archive/sizing-legacy-v1.csv"),
        wind_equivalent=current if current.get("status") == "ok" else report("archive/wind-equivalent-legacy-v1.json"),
        wind_equivalent_current=current)
    d["substation"]["attributes"].update(flex_stats=csv_rows("flex.csv"),
        flex_stats_model=report("flex.json").get("model_version", "unknown"))
    return {**types, **d}


def csv_rows(name):
    import csv, os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", name)
    if not os.path.exists(path):
        return []
    return [{k: (float(v) if k not in ("variant", "season") else v) for k, v in r.items()} for r in csv.DictReader(open(path))]


def sizing():
    """Результаты расчёта «сколько строить» (team/tynys/sizing.py → data/sizing.csv)."""
    import csv, os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sizing.csv")
    if not os.path.exists(path):
        return []
    return [{k: (v if k == "variant" else float(v)) for k, v in r.items()} for r in csv.DictReader(open(path))]


def main():
    for name, body in twins().items():
        for attempt in range(40):
            try:
                st, _ = http("PUT", f"/api/2/things/{NS}:{name}", body)
                print(("created " if st == 201 else "updated ") + name); break
            except Exception as e:
                if attempt == 39:
                    print("FAILED", name, e, file=sys.stderr); return 1
                time.sleep(3)
    print(len(twins()), "twins ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
