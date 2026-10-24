"""Configurable events survive snapshot replay and affect causal state."""
import copy
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tynys.params import aktogay, DOMAINS
from tynys.sim import Env, Scenario, init_state, step
from tynys.controllers import V0Traditional, V2Tynys
from tynys.live import scenario_from_events, state_to_dict
from tynys.futures import _snapshot, _environment, validate_request


def test_event_parameters_survive_counterfactual_snapshot():
    p = aktogay()
    events = [
        dict(kind="line_trip", line=1, t0=0, dur=4),
        dict(kind="line_trip", line=1, t0=8, dur=4),
        dict(kind="kegoc", grid_drop_mw=125, t0=0, dur=4),
        dict(kind="plan_up", mine_mult=1.3, t0=0, dur=4),
        dict(kind="truck_failure", loss_pct=100, t0=0, dur=4),
        dict(kind="excavator_failure", loss_pct=75, t0=0, dur=4),
        dict(kind="grade_drop", drop_pct=50, t0=0, dur=4),
        dict(kind="tariff_change", change_pct=-20, t0=0, dur=4),
    ]
    source = dict(sim_hour=0, start_doy=15, seed=7, scenario_rev=0,
                  state=state_to_dict(init_state(p)), events=events)
    request = validate_request({"hard_ore": True, "lead_h": 0})
    snap = _snapshot(source, request, p)
    assert snap["events"] == events
    env = _environment(p, snap, request)
    base = Env(p, Scenario(), 7)
    assert not env.line_avail[0, :4].any() and not env.line_avail[0, 8:12].any()
    assert env.line_avail[1, :12].all()
    assert env.grid_cap[0] == p.grid_cap_mw-125
    assert env.mine_plan[0] == pytest.approx(p.mine_ore_tph*1.3)
    assert env.truck_mult[0] == 0 and env.shovel_mult[0] == .25
    assert env.tariff_mult[0] == .8
    # hard-ore reinstall must not drop the grade scenario.
    assert env.grade_true["soft"][0] == pytest.approx(base.grade_true["soft"][0]*.5)
    invalid = copy.deepcopy(source)
    invalid["events"][0]["line"] = 3
    with pytest.raises(ValueError):
        _snapshot(invalid, request, p)


@pytest.mark.parametrize("geomet", [False, True])
def test_grade_event_changes_new_ore_not_existing_stock(geomet):
    p = aktogay()
    p.geomet = geomet
    base = Env(p, Scenario(days=2), 7)
    sc = scenario_from_events(p, [dict(kind="grade_drop", drop_pct=50, t0=0, dur=24)], 15)
    sc.days = 2
    changed = Env(p, sc, 7)
    a, b = init_state(p), init_state(p)
    old_cu = sum(b.pile_cu.values())
    controller = V0Traditional()
    ra = step(p, base, a, 0, controller.decide(p, base, a, 0), False)
    rb = step(p, changed, b, 0, controller.decide(p, changed, b, 0), False)
    assert ra["feed_cu_t"] == pytest.approx(rb["feed_cu_t"])
    assert ra["cu_t"] == pytest.approx(rb["cu_t"])
    assert rb["mined_cu_t"] == pytest.approx(ra["mined_cu_t"]*.5)
    assert sum(b.pile_cu.values()) == pytest.approx(old_cu+rb["mined_cu_t"]-rb["feed_cu_t"])
    for d in DOMAINS:
        assert np.allclose(changed.grade_true[d][:24], base.grade_true[d][:24]*.5)


def test_failed_fleet_cannot_haul_or_charge_and_tariff_is_metered():
    p = aktogay()
    events = [dict(kind="truck_failure", loss_pct=100, t0=0, dur=24),
              dict(kind="tariff_change", change_pct=50, t0=0, dur=24)]
    sc = scenario_from_events(p, events, 15)
    sc.days = 2
    env, st = Env(p, sc, 7), init_state(p)
    p.mpc_horizon_h = 4
    ctrl = V2Tynys()
    dec = ctrl.decide(p, env, st, 0)
    assert dec["charge_mw"] < 1e-6
    rec = step(p, env, st, 0, dec, True)
    assert rec["mine"] == 0 and rec["charge"] == 0
    assert not any(st.fleet.available)
    assert rec["price"] == pytest.approx(p.price_kzt_mwh(0)*1.5)
    assert rec["assets"]["substation"]["price_kzt_mwh"] == rec["price"]
