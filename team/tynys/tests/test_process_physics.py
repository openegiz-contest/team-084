"""Physical feasibility tests, independent of economic headline metrics."""
import copy
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tynys import physics as ph
from tynys.controllers import V0Traditional, V2Tynys
from tynys.params import aktogay, DOMAINS, P80_MODES
from tynys.sim import Env, Scenario, init_state, step, flexibility
from tynys.live import state_to_dict, state_from_dict
from tynys.futures import _snapshot, validate_request


def model(**kw):
    p = replace(aktogay(), **{**dict(wind_mw=0, pv_mwp=0, bwi_noise_sd=0,
                                    equipment_wear_per_h=0, mpc_horizon_h=6), **kw})
    return p, Env(p, Scenario(days=15), 7), init_state(p)


def decision(p, q, mode=150):
    x = np.zeros((p.n_lines, 2, len(P80_MODES)))
    x[:, :, P80_MODES.index(mode)] = q/2
    return dict(x=x.tolist(), charge_mw=35, bess_mw=0)


def test_mill_draw_has_rotating_floor_and_preserves_reference_nominal():
    p = aktogay()
    bwi = np.mean(list(p.bwi.values()))
    nom = ph.mill_power_mw(p, p.line_q_nom, bwi, 150)
    assert nom == pytest.approx(p.line_q_nom*ph.bond_kwh_t(p, bwi, 150)/1000)
    assert ph.mill_power_mw(p, 0, bwi, 150) == pytest.approx(.35*nom)
    assert ph.mill_power_mw(p, p.line_q_nom/2, bwi, 150) == pytest.approx(.675*nom)
    assert ph.mill_power_mw(p, 0, bwi, 150, running=False) == 0


def test_physical_feed_and_power_ramps_include_mode_changes_and_controlled_stop():
    p, env, st = model()
    previous_q = np.asarray(st.line_x).sum(axis=(1,2))
    previous_mw = np.array(st.line_mw)
    for t in range(18):
        target = p.line_q_max if t < 4 else 0 if t < 14 else p.line_q_max
        r = step(p, env, st, t, decision(p, target, 120 if t < 4 else 250), True)
        for l in range(p.n_lines):
            a = r['assets'][f'line-{l+1}']
            q, mw = a['feed_tph'], a['mill_mw']
            if q and previous_q[l]:
                assert abs(q-previous_q[l]) <= p.line_q_nom*p.line_q_ramp_fraction+1e-6
                assert abs(mw-previous_mw[l]) <= p.line_p_max_mw*p.line_power_ramp_fraction+1e-6
            elif q:
                assert q <= p.line_q_min+1e-6
            elif previous_q[l] and a['stop_reason'] == 'controlled_stop':
                assert previous_q[l] <= p.line_q_min+p.line_q_nom*p.line_q_ramp_fraction+1e-6
            assert a['p80_um'] == 0 or any(abs(a['p80_um']-mode) < 1e-6 for mode in P80_MODES)
            previous_q[l], previous_mw[l] = q, mw
    assert r['feed'] > 0


def test_simulator_rejects_simultaneous_grind_modes():
    p, env, st = model()
    dec = decision(p, 3330)
    dec['x'][0][0][0] = 10
    with pytest.raises(ValueError, match='one P80'):
        step(p, env, st, 0, dec, True)


def test_stock_clipping_cannot_bypass_power_ramp_by_changing_mix():
    p, env, st = model()
    soft = ph.mill_variable_mwh_t(p, p.bwi['soft'], 250)
    hard = ph.mill_variable_mwh_t(p, p.bwi['hard'], 250)
    requested_mw = ph.mill_idle_mw(p)+p.line_q_nom*(soft+hard)/2
    st.line_mw = [requested_mw+p.line_p_max_mw*p.line_power_ramp_fraction-.1]*2
    # Removing this much hard ore satisfies the old throughput floor, but
    # removes >0.1 MW and violates the actual metered-power lower bound.
    shortage_per_line = .101/hard
    st.pile['hard'] = p.line_q_nom-2*shortage_per_line
    st.pile_cu['hard'] = st.pile['hard']*p.cu_grade['hard']
    st.pile_bwi_mass['hard'] = st.pile['hard']*p.bwi['hard']
    st.pile_recovery_cu['hard'] = st.pile_cu['hard']*p.r150['hard']
    r = step(p, env, st, 0, decision(p, p.line_q_nom, 250), True)
    assert r['trips'] == 2
    assert all(r['assets'][f'line-{l+1}']['stop_reason'] == 'stockout_trip' for l in range(2))


def test_emergency_outage_can_trip_but_cannot_masquerade_as_ramped_operation():
    p, env, st = model()
    env.grid_cap[0] = 0
    env.bess_avail[0] = False
    r = step(p, env, st, 0, decision(p, 3330), True)
    assert r['feed'] == 0 and r['trips'] == 2
    assert all(r['assets'][f'line-{l+1}']['stop_reason'] == 'power_trip' for l in range(2))
    assert all(st.line_lock)


def test_mpc_whole_horizon_has_one_mode_direction_and_ramp_limits():
    p, env, st = model()
    ctl = V2Tynys(explain=True, solver_options={'time_limit': None, 'node_limit': 64})
    ctl.decide(p, env, st, 0)
    assert not ctl.last_fallback
    plan = ctl.last_plan
    assert all(min(c,d) < 1e-6 for c,d in zip(plan['bess_charge_mw'], plan['bess_discharge_mw']))
    for l in range(p.n_lines):
        last_q, last_mw = p.line_q_nom, st.line_mw[l]
        for h in range(p.mpc_horizon_h):
            modes = np.array(plan['line_mode_feed_tph'][l][h])
            assert np.count_nonzero(modes > 1e-5) <= 1
            q, mw = plan['line_feed_tph'][l][h], plan['line_mw'][l][h]
            if q > 1e-5 and last_q > 1e-5:
                assert abs(q-last_q) <= p.line_q_nom*p.line_q_ramp_fraction+1e-5
                assert abs(mw-last_mw) <= p.line_p_max_mw*p.line_power_ramp_fraction+1e-5
            elif q > 1e-5:
                assert q <= p.line_q_min+1e-5
            last_q, last_mw = q, mw


def test_grade_variability_and_copper_inventory_conserve_actual_mined_metal():
    p, env, st = model()
    initial_cu = sum(st.pile_cu.values())
    mined_cu = product_cu = 0
    grades = []
    for t in range(96):
        r = step(p, env, st, t, decision(p, 3330), True)
        mined_cu += r['mined_cu_t']
        product_cu += r['cu_t']
        grades.append(r['grade_soft'])
        assert initial_cu+mined_cu == pytest.approx(sum(st.pile_cu.values())+product_cu+st.materials['tailings_cu_t'])
        assert all(0 <= st.pile_cu[d] <= st.pile[d] for d in DOMAINS)
    assert np.std(grades) > 1e-6
    assert not np.array_equal(env.grade_true['soft'], env.grade_true['hard'])
    assert np.array_equal(env.grade_true['soft'], Env(p, env.sc, 7).grade_true['soft'])


def test_default_calendar_contains_staggered_line_and_crusher_downtime():
    p, env, st = model()
    stops = {n: [] for n in ('line-1', 'line-2', 'crusher')}
    for t in range(250):
        r = step(p, env, st, t, V0Traditional().decide(p, env, st, t), False)
        for name in stops:
            if r['assets'][name]['state'] == 'maintenance':
                stops[name].append(t)
        if 72 <= t < 76:
            assert r['line0'] == 0 and r['line1'] > 0
        if 240 <= t < 244:
            assert r['mine'] == 0
    assert set(range(72,76)) <= set(stops['line-1'])
    assert set(range(156,160)) <= set(stops['line-2'])
    assert set(range(240,244)) <= set(stops['crusher'])


def test_full_stores_no_haulage_energy_for_rejected_ore():
    p, env, st = model(pile_init_frac=1)
    env.sc.equipment_down['water'] = [(0,2)]
    before = st.fleet_e
    r = step(p, env, st, 0, decision(p, 3330), True)
    assert r['mine'] == r['feed'] == 0
    assert st.fleet_e == pytest.approx(before+r['charge']*p.eta_charge)
    assert sum(st.fleet.ore_tph) == 0


def test_process_history_roundtrip_and_validation():
    p, env, st = model()
    step(p, env, st, 0, decision(p, 4000, 200), True)
    saved = state_to_dict(st)
    snap = dict(state=saved, sim_hour=1, start_doy=15, seed=7, scenario_rev=0)
    checked = _snapshot(snap, validate_request({}), p)
    restored = state_from_dict(checked['state'])
    assert step(p, env, st, 1, decision(p, 0), True) == step(p, env, restored, 1, decision(p, 0), True)
    forged = copy.deepcopy(snap)
    forged['state']['pile_cu']['soft'] = 1e9
    with pytest.raises(ValueError):
        _snapshot(forged, validate_request({}), p)


def test_reserve_is_incremental_and_never_exceeds_current_import():
    p, env, st = model()
    r = step(p, env, st, 0, decision(p, 3330), True)
    r.update(grid=1, bess=60)
    assert flexibility(p, st, r)[0] <= 1
    r['grid'] = 0
    assert flexibility(p, st, r) == (0,0)
    r.update(grid=260, charge=0, bess=p.bess_mw)
    # Already discharging at full converter power adds no reserve.
    for l in range(p.n_lines):
        r['assets'][f'line-{l+1}']['feed_tph'] = p.line_q_min
    assert flexibility(p, st, r)[0] == 0
