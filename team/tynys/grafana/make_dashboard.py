"""Генерирует grafana/tynys.json — дашборд Grafana поверх InfluxDB платформы."""
import json, os
DS = {"type": "influxdb", "uid": "opentwins-influxdb"}


def q(ref, thing, feat, alias):
    return {"refId": ref, "datasource": DS, "query":
            f'from(bucket: "default")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
            f'  |> filter(fn: (r) => r.thingId == "kz.tynys:{thing}" and r._field == "value_{feat}_properties_value")\n'
            f'  |> keep(columns: ["_time", "_value"])\n  |> set(key: "_field", value: "{alias}")'}


def panel(i, title, series, x, y, w=12, h=8, unit="none", kind="timeseries"):
    refs = "ABCDEFGH"
    return {"id": i, "type": kind, "title": title, "datasource": DS, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "fieldConfig": {"defaults": {"unit": unit, "custom": {"lineWidth": 2, "fillOpacity": 8}}, "overrides": []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "reduceOptions": {"calcs": ["lastNotNull"]}},
            "targets": [q(refs[k], *s) for k, s in enumerate(series)]}


P = [
    panel(1, "Энергобаланс, МВт", [("energy", "load_mw", "нагрузка"), ("energy", "renew_mw", "ВИЭ"),
                                   ("energy", "grid_mw", "сеть"), ("energy", "curtail_mw", "сброс ВИЭ")], 0, 0),
    panel(2, "CO₂ с учётом запасов, т: V0 / V1 / V2", [("shadow-v0", "co2_adj_t", "V0 как сейчас"), ("shadow-v1", "co2_adj_t", "V1 правила"),
                                                     ("site", "co2_adj_t", "V2 Тыныс")], 12, 0),
    panel(3, "Медь с учётом склада, т", [("shadow-v0", "cu_adj_t", "V0"), ("shadow-v1", "cu_adj_t", "V1"), ("site", "cu_adj_t", "V2")], 0, 8),
    panel(4, "Склады руды, % заполнения", [("pile-soft", "fill_pct", "мягкая"), ("pile-hard", "fill_pct", "твёрдая")], 12, 8, unit="percent"),
    panel(5, "Помол: питание, т/ч", [("plant", "feed_soft_tph", "мягкая"), ("plant", "feed_hard_tph", "твёрдая")], 0, 16),
    panel(6, "Крупность P80, мкм и извлечение, %", [("plant", "p80_um", "P80"), ("flotation", "recovery", "извлечение")], 12, 16),
    panel(7, "Теневая цена энергии, ₸/кВт·ч", [("coordinator", "shadow_kzt_kwh", "теневая цена")], 0, 24),
    panel(8, "Тыныс‑резерв для KEGOC, МВт", [("substation", "flex_down_mw", "можно снизить"), ("substation", "grid_cap_mw", "предел сети")], 12, 24),
    panel(9, "Накопитель и зарядка самосвалов", [("bess", "soc", "АКБ, %"), ("energy", "charge_mw", "зарядка, МВт")], 0, 32),
    panel(10, "Ветер и солнце, МВт", [("wind", "power_mw", "ВЭС"), ("pv", "power_mw", "СЭС")], 12, 32),
]
d = {"uid": "tynys-aktogay", "title": "Тыныс · Актогай", "tags": ["tynys", "contest"], "timezone": "browser",
     "schemaVersion": 39, "version": 1, "refresh": "5s", "time": {"from": "now-30m", "to": "now"},
     "description": "Дышащий рудник Актогай: энергия, склады, помол, CO₂ — V0/V1/V2. Данные из двойников kz.tynys:*.",
     "panels": P}
json.dump(d, open(os.path.join(os.path.dirname(__file__), "tynys.json"), "w"), ensure_ascii=False, indent=1)
