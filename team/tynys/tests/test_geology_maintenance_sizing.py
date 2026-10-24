import copy
from dataclasses import replace
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tynys.geology import model, bond_work_index, DATA
from tynys.params import aktogay, DOMAINS
from tynys.sim import Env, Scenario, init_state, step
from tynys.controllers import V0Traditional, V2Tynys
from tynys.live import state_to_dict, state_from_dict
from tynys.futures import _snapshot, validate_request
from tynys.maintenance import schedule, validate_plan, accept_plan, task
from analyze_sizing import wind_equivalent, analyze


def test_geomet_source_formula_coordinates_and_reproducibility():
    m = model()
    assert m['comminution_samples'] == 60 and m['flotation_samples'] == 52
    assert m['drillhole_samples'] > 1000 and m['analogue']
    row = pd.read_csv(DATA/'comminution.csv').iloc[0]
    expected = 49/(row.A**.23*row.M**.82*(10/row.P80**.5-10/row.F80**.5))
    assert m['cells'][0]['bwi'] == pytest.approx(expected)
    assert m['cells'][0]['x_m'] == pytest.approx(row.X)
    assert np.mean([c['grade_fraction'] for c in m['cells']]) == pytest.approx(.0043)
    p = aktogay()
    a,b = Env(p,Scenario(days=5),7),Env(p,Scenario(days=5),999)
    assert np.array_equal(a.bwi_true['hard'], b.bwi_true['hard'])  # no seed-dependent hardness
    hard = Env(p,Scenario(days=5,hard_frac_shift={12:.8,24:.5}),7)
    assert hard.geology_ids['hard'][12] == max(m['cells'],key=lambda c:c['bwi'])['id']


def test_spatial_ore_properties_conserve_through_stock_and_replay():
    p = replace(aktogay(), planned_stops=False)
    env,st = Env(p,Scenario(days=3),7),init_state(p)
    for t in range(30):
        before = copy.deepcopy(st)
        r = step(p,env,st,t,V0Traditional().decide(p,env,st,t),False)
        for d in DOMAINS:
            fraction = r['hard_frac'] if d == 'hard' else 1-r['hard_frac']
            mined, fed = r['mine']*fraction,r[f'feed_{d}']
            assert st.pile_bwi_mass[d] == pytest.approx(before.pile_bwi_mass[d]*(1-fed/before.pile[d])+mined*env.bwi_true[d][t])
            assert st.pile_recovery_cu[d] == pytest.approx(before.pile_recovery_cu[d]*(1-fed/before.pile[d])+mined*env.grade_true[d][t]*env.recovery_true[d][t])
            assert 0 <= st.pile_recovery_cu[d] <= st.pile_cu[d]
        assert r['cu_t'] <= r['feed_cu_t']+1e-8
    snap = dict(sim_hour=30,start_doy=15,seed=7,scenario_rev=0,state=state_to_dict(st))
    validated = _snapshot(snap,validate_request({}),p)
    restored = state_from_dict(validated['state'])
    for state in (st,restored):
        dec = V0Traditional().decide(p,env,state,30)
        step(p,env,state,30,dec,False)
    assert state_to_dict(st) == state_to_dict(restored)


def test_coordinator_moves_service_into_lull_and_commits_window(monkeypatch):
    p = aktogay()
    env = Env(p,Scenario(days=30),7)
    t = 52
    def forecast(w, now, horizon, seed):
        wind = np.ones(horizon)
        wind[max(0,78-now):max(0,83-now)] = 0
        return wind, np.zeros(horizon)
    monkeypatch.setattr('tynys.maintenance.wx.forecast',forecast)
    fixed,flex = init_state(p),init_state(p)
    schedule(p,env,fixed,t,False)
    chosen = schedule(p,env,flex,t,True)
    assert fixed.maintenance['line-1']['start'] == 72
    assert 78 <= chosen['line-1']['start'] <= 79
    assert chosen['line-1']['forecast_grid_value_kzt'] > fixed.maintenance['line-1']['forecast_grid_value_kzt']
    assert schedule(p,env,flex,60,True) == chosen
    invalid = copy.deepcopy(chosen)
    invalid['line-1']['start'] += 1
    with pytest.raises(ValueError,match='committed'):
        accept_plan(p,flex,invalid,60)
    invalid['line-1']['start'] = invalid['line-1']['deadline']+1
    with pytest.raises(ValueError,match='deadline'):
        validate_plan(p,invalid)


def test_liner_service_stops_line_resets_wear_and_roundtrips():
    p = aktogay()
    env, st = Env(p,Scenario(days=30),7),init_state(p)
    item = task(p,0,3)
    start = item['nominal']
    st.maintenance = {'line-1': {**item,'start':start,'strategy':'calendar','forecast_grid_value_kzt':0.}}
    st.equipment['line-1'].liner_operating_h = 600
    checked = _snapshot(dict(sim_hour=start,start_doy=15,seed=7,scenario_rev=0,state=state_to_dict(st)),validate_request({}),p)
    restored = state_from_dict(checked['state'])
    assert restored.maintenance == st.maintenance
    for t in range(start,start+item['duration']):
        r = step(p,env,st,t,V0Traditional().decide(p,env,st,t),False)
        assert r['assets']['line-1']['state'] == 'maintenance'
        assert r['line0'] == 0
        assert r['assets']['line-2']['state'] != 'maintenance'
    assert st.equipment['line-1'].liner_replacements == 1
    assert st.equipment['line-1'].liner_operating_h == 0


def test_wind_equivalent_archive_and_no_false_savings():
    path = DATA.parent/'archive'/'sizing-legacy-v1.csv'
    result = analyze(path, pv=500., copper_tolerance=.01)
    assert result['archived']
    assert result['equivalent_wind_mw'] == pytest.approx((778.5-723.8)/(778.5-715.7)*150)
    assert result['grid_step_equivalent_mw'] == 150
    data = pd.read_csv(path)
    # Lost output, target below observed range, other PV: no fake equivalent.
    for cu,co2 in [(100,723.8),(222000,1)]:
        changed = data.copy()
        mask = (changed.variant=='V2green') & (changed.wind_mw==300) & (changed.pv_mwp==500)
        changed.loc[mask,['cu_adj_t','co2_adj_kt']] = [cu,co2]
        assert wind_equivalent(changed, pv=500., copper_tolerance=.01)['status'] == 'unavailable'
    assert wind_equivalent(data,pv=501)['status'] == 'unavailable'
    with pytest.raises(ValueError,match='Duplicate'):
        wind_equivalent(pd.concat([data,data.iloc[:1]]), pv=500.)


def test_wind_equivalent_current_defaults():
    result = analyze(DATA.parent/'sizing.csv')
    assert result['status'] == 'ok' and not result['archived']
    assert result['pv_mwp'] == 250 and result['copper_tolerance_pct'] == pytest.approx(1.5)
    assert result['equivalent_wind_mw'] == pytest.approx(89.3, abs=0.1)
    assert 0 < result['equivalent_wind_mw_per_t_cu'] < result['equivalent_wind_mw']


def test_demo_wind_effect_compares_identical_hour_and_setpoints():
    p = aktogay()
    t = 10
    env = Env(p,Scenario(days=2,wind_mult={(t,t+24):.08}),7)
    st = init_state(p)
    r = step(p,env,st,t,V0Traditional().decide(p,env,st,t),False)
    from tynys.weather import wind_power_pu
    base_wind = float(wind_power_pu(np.array([env.w['wind_v'][t]]))[0])*p.wind_mw
    expected = min(r['grid_cap'],max(0.,r['load']-r['pv']-base_wind-r['bess']))
    assert r['grid_no_lull_mw'] == pytest.approx(expected)
    assert r['lull_grid_delta_mw'] == pytest.approx(r['grid']-expected)
    assert r['lull_grid_delta_mw'] >= 0
