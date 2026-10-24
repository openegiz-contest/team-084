"""Versioned regression, not independent validation against mine measurements.

V0, no renewables, four 14-day seasons, seed 7. V4 adds the GeoMet spatial
analogue and maintenance windows; previous references remain available with
--physics-v3 and --legacy. These are regression checks, not mine calibration.
"""
import argparse
from dataclasses import replace
import json
import pandas as pd
from tynys.params import aktogay
from tynys.sim import Scenario, run
from tynys.controllers import V0Traditional
from tynys.metrics import summarize

LEGACY_REF = {"cu_adj_t": 222131.2, "grid_gwh": 2013.9, "kwh_t": 34.53}
PHYSICS_V3_REF = {"cu_adj_t": 214118.1, "grid_gwh": 1976.8, "kwh_t": 35.03}
# v4 откалибрована по энергии отчёта (вспомогательные потребители 83 МВт): 2 030 ГВт·ч
PHYSICS_V4_REF = {"cu_adj_t": 219068.3, "grid_gwh": 2030.9, "kwh_t": 36.3234}


def calculate(legacy=False, physics_v3=False):
    p = replace(aktogay(), wind_mw=0, pv_mwp=0)
    if legacy or physics_v3:
        p = replace(p, auxiliary_nominal_mw=100.0)   # прежние эталоны считались до калибровки v4
    if legacy:
        p = replace(p, mill_idle_fraction=0, line_q_ramp_fraction=1,
                    line_power_ramp_fraction=1, grade_noise_sd=0, planned_stops=False,
                    geomet=False, flexible_maintenance=False)
    elif physics_v3:
        p = replace(p, geomet=False, flexible_maintenance=False)
    cu = grid = load = feed = 0.0
    for doy in (15, 105, 196, 288):
        r = pd.DataFrame(run(p, Scenario(start_doy=doy, days=14), V0Traditional(), 7))
        cu += summarize(p, r, p.pile_cap_t*p.pile_init_frac)["cu_adj_t"]
        grid += r.grid.sum(); load += r.load.sum(); feed += r.feed.sum()
    return {"cu_adj_t": cu*365/56, "grid_gwh": grid*365/56/1000, "kwh_t": 1000*load/feed}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy', action='store_true')
    parser.add_argument('--physics-v3', action='store_true')
    args = parser.parse_args()
    out = calculate(args.legacy, args.physics_v3)
    reference = LEGACY_REF if args.legacy else PHYSICS_V3_REF if args.physics_v3 else PHYSICS_V4_REF
    deviations = {k: 100*(out[k]-v)/v for k,v in reference.items()}
    print(json.dumps({'version': 'legacy-comparison' if args.legacy else 'physics-v3' if args.physics_v3 else 'physics-v4-geomet-maintenance',
                      'metrics': out, 'reference_deviation_pct': deviations,
                      'legacy_deviation_pct': {k: 100*(out[k]-v)/v for k,v in LEGACY_REF.items()}}, indent=2))
    passed = all(abs(v) <= .5 for v in deviations.values())
    print('REGRESSION:', 'PASS (+/-0.5%)' if passed else 'FAIL')
    raise SystemExit(0 if passed else 1)
