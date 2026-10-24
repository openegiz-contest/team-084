"""Conservation and causal failures, including actual MQTT publications."""
import copy
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services")]
from tynys.params import aktogay, DOMAINS
from tynys.sim import Env, Scenario, init_state, step
from tynys.controllers import V0Traditional, V1Reactive, V2Tynys
from tynys.live import state_to_dict, state_from_dict, scenario_from_events
from tynys.assets import asset_specs, auxiliary_coefficients, shovel_for, charger_for
from tynys.fleet import group_caps
from tynys.futures import _snapshot, validate_request
from field import publish_hour
from platform_client import modify
from setup_twins import twins


def model(**kwargs):
    p = replace(aktogay(), **kwargs)
    return p, Env(p, Scenario(days=3), 7), init_state(p)


def assert_balances(p, before, st, r):
    assert r["load"] == pytest.approx(r["grid"] + r["renew"] - r["curtail"] + r["bess"] + r["unserved"])
    consumers = [n for n, (kind, _, _) in asset_specs(p).items()
                 if kind not in ("truck", "wind_farm", "pv_farm", "bess", "substation")]
    assert sum(r["assets"][n]["power_mw"] for n in consumers) == pytest.approx(r["load"])
    for d in DOMAINS:
        fraction = r["hard_frac"] if d == "hard" else 1-r["hard_frac"]
        assert st.pile[d] == pytest.approx(before.pile[d] + r["mine"]*fraction - r[f"feed_{d}"])
        assert -1e-7 <= st.pile[d] <= p.pile_cap_t+1e-7
    assert r["waste_tph"] == pytest.approx(p.strip_ratio*r["mine"])
    assert r["feed"] == pytest.approx(r["tailings_tph"] + r["concentrate_tph"])
    assert r["feed_cu_t"] == pytest.approx(r["cu_t"] + r["assets"]["tailings"]["cu_tph"])
    assert r["cu_t"] == pytest.approx(r["concentrate_tph"]*p.concentrate_grade)
    w = r["assets"]["water"]
    assert w["flow_m3_h"] == pytest.approx(w["fresh_m3_h"] + w["recycle_m3_h"])
    assert sum(st.fleet.e) == pytest.approx(st.fleet_e)
    assert sum(st.fleet.charge_mw) == pytest.approx(r["charge"])
    assert sum(r["assets"][f"charger-{j}"]["power_mw"] for j in range(1,5)) == pytest.approx(r["charge"])
    assert sum(st.fleet.ore_tph) == pytest.approx(r["mine"])
    assert sum(st.fleet.waste_tph) == pytest.approx(r["waste_tph"])
    assert sum(r["assets"][f"line-{l+1}"]["mill_mw"] for l in range(p.n_lines)) == pytest.approx(r["mill_mw"])
    for i in range(14):
        assert group_caps(p)[2]-1e-7 <= st.fleet.e[i] <= group_caps(p)[3]+1e-7
    for name in st.equipment:
        f = r["assets"][name]
        assert 0 <= f["availability_pct"] <= 100
        if not f["available"]:
            assert f.get("power_mw", 0) == pytest.approx(0)


@pytest.mark.parametrize("controller", [V0Traditional, V1Reactive, V2Tynys])
def test_conservation_with_failures_storage_and_power_limits(controller):
    p, env, st = model(mpc_horizon_h=4, pile_cap_t=5000, equipment_wear_per_h=0)
    env.grid_cap[5:12] = 20
    env.bess_avail[5:12] = False
    env.w["wind_pu"][5:12] = 0
    env.w["pv_pu"][5:12] = 0
    env.sc.equipment_down = {"crusher": [(14,18)], "water": [(20,22)], "charger-1": [(3,9)]}
    ctl = controller()
    # Segregated balances are stricter; keep all controllers' decisions feasible
    # for those stores by testing the physical model in that mode.
    for t in range(30):
        before = copy.deepcopy(st)
        r = step(p, env, st, t, ctl.decide(p, env, st, t), True)
        assert_balances(p, before, st, r)
        if 14 <= t < 18:
            assert r["mine"] == 0
        if 20 <= t < 22:
            assert r["feed"] == 0


@pytest.mark.parametrize("asset", ["crusher", "conveyor-crushed", "waste-dump", "dewatering"])
def test_upstream_failure_stops_mining_but_stored_ore_feeds_plant(asset):
    p, env, st = model()
    env.sc.equipment_down[asset] = [(0,2)]
    r = step(p, env, st, 0, V0Traditional().decide(p, env, st, 0), False)
    assert r["mine"] == 0
    assert r["feed"] > 0
    assert r["assets"][asset]["state"] == "fault"


@pytest.mark.parametrize("asset", ["water", "tailings", "concentrate", "conveyor-feed", "flotation"])
def test_downstream_failure_stops_processing_without_inventing_product(asset):
    p, env, st = model()
    env.sc.equipment_down[asset] = [(0,2)]
    dec = V0Traditional().decide(p, env, st, 0)
    # Even stale, positive setpoints must be rejected by the physical plant.
    dec["x"][0][0][1] = p.line_q_nom
    r = step(p, env, st, 0, dec, False)
    assert r["feed"] == r["cu_t"] == r["tailings_tph"] == 0
    assert r["mine"] > 0


def test_shovel_routes_and_charger_allocation_are_causal():
    p, env, st = model()
    k, cap, lo, hi = group_caps(p)
    st.fleet.e = [hi if charger_for(i) != "charger-2" else lo for i in range(14)]
    st.fleet_e = sum(st.fleet.e)
    env.sc.equipment_down["shovel-1"] = [(0,2)]
    dec = V0Traditional().decide(p, env, st, 0)
    dec["charge_mw"] = 50
    r = step(p, env, st, 0, dec, False)
    assert r["assets"]["charger-2"]["power_mw"] > 0
    for j in (1,3,4):
        assert r["assets"][f"charger-{j}"]["power_mw"] == 0
    for i in range(14):
        if shovel_for(i) == "shovel-1":
            assert st.fleet.ore_tph[i] == st.fleet.waste_tph[i] == 0
    assert r["assets"]["shovel-1"]["rate_tph"] == 0
    assert r["mine"] < p.mine_ore_tph


def test_service_health_and_snapshot_roundtrip():
    p, env, st = model(service_interval_h=2, service_duration_h=2)
    for t in range(3):
        r = step(p, env, st, t, V0Traditional().decide(p, env, st, t), False)
    assert r["assets"]["crusher"]["state"] == "maintenance"
    assert r["assets"]["crusher"]["availability_pct"] == pytest.approx(200/3)
    assert r["mine"] == 0
    saved = json.loads(json.dumps(state_to_dict(st)))
    replay = state_from_dict(saved)
    for t in (3,4):
        dec = V0Traditional().decide(p, env, st, t)
        a = step(p, env, st, t, dec, False)
        b = step(p, env, replay, t, dec, False)
        assert a == b
    assert a["assets"]["crusher"]["available"]
    assert a["mine"] > 0
    assert st.equipment["crusher"].maintenance_count == 1


def test_no_current_hour_phantom_feed_or_negative_inventory():
    p, env, st = model(pile_init_frac=0)
    dec = V0Traditional().decide(p, env, st, 0)
    r = step(p, env, st, 0, dec, False)
    assert r["feed"] == r["cu_t"] == 0
    assert sum(st.pile.values()) == pytest.approx(r["mine"])


@pytest.mark.parametrize("asset", ["workshops", "camp", "wind", "pv", "substation", "line-1", "truck-01", "charger-1"])
def test_failed_assets_do_not_consume_or_generate_power(asset):
    p, env, st = model()
    env.sc.equipment_down[asset] = [(0,2)]
    before = copy.deepcopy(st)
    r = step(p, env, st, 0, V0Traditional().decide(p, env, st, 0), False)
    assert_balances(p, before, st, r)
    assert r["assets"][asset]["health_pct"] == 0


def test_auxiliary_loads_and_units_survive_actual_publishing():
    p, env, st = model()
    d = twins()
    kinds = {name: body["attributes"]["kind"] for name,body in d.items()}
    instances = {n:b for n,b in d.items() if not b["attributes"]["_isType"]}
    for name, body in instances.items():
        typ = body["attributes"]["type"].split(":")[1]
        assert d[typ]["attributes"]["_isType"]
        for key, targets in body["attributes"].get("links", {}).items():
            if isinstance(targets, list):
                assert all(target.split(":")[1] in instances for target in targets)
    assert set(instances["shovel-1"]["attributes"]["links"]["loads"]).isdisjoint(instances["shovel-2"]["attributes"]["links"]["loads"])
    nominal = sum(a+b*p.mine_ore_tph+c*p.n_lines*p.line_q_nom for a,b,c in auxiliary_coefficients(p).values())
    assert nominal == pytest.approx(p.auxiliary_nominal_mw)
    r = step(p, env, st, 0, V0Traditional().decide(p, env, st, 0), False)
    class Bus:
        def __init__(self): self.messages = {}
        def send(self, name, values): self.messages[name] = modify(name, values)
    bus = Bus()
    publish_hour(bus, p, env, st, r, 0, "test", st.fleet)
    assert set(asset_specs(p)) <= set(bus.messages)
    for name, message in bus.messages.items():
        assert name in instances
        for feature in message["value"].values():
            if isinstance(feature["properties"]["value"], (int,float,bool)):
                assert feature["properties"]["unit"]
    assert bus.messages["crusher"]["value"]["throughput_tph"]["properties"]["unit"] == "t/h"
    assert bus.messages["line-1"]["value"]["speed_rpm"]["properties"]["unit"] == "rpm"


def test_overlapping_equipment_events_and_explicit_maintenance():
    p = aktogay()
    sc = scenario_from_events(p, [{"kind":"crusher_fault","t0":0,"dur":3},
                                  {"kind":"crusher_fault","t0":2,"dur":3},
                                  {"kind":"crusher_service","t0":6,"dur":2}], 15)
    assert sc.equipment_down["crusher"] == [(0,3),(2,5)]
    assert sc.equipment_maintenance["crusher"] == [(6,8)]


def test_futures_rejects_forged_group_energy():
    p, env, st = model()
    snapshot = dict(state=state_to_dict(st), sim_hour=0, start_doy=15, seed=7, scenario_rev=0)
    snapshot["state"]["fleet"]["e"][0] += 1
    with pytest.raises(ValueError, match="сумма энергии"):
        _snapshot(snapshot, validate_request({}), p)
