"""Reproducible physics-v4 reserve statistics; preserves prior CSV versions.

Run from team/tynys: python flex_stats.py
Four seasons x 14 days, seed 7, V2 with deterministic 16-node budget, as in
the counterfactual evaluator. The reserve is conditional next-hour reduction,
not certified ancillary service. CSV plus JSON provenance are written together.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import pandas as pd
from tynys.params import aktogay
from tynys.sim import Scenario, Env, init_state, step
from tynys.controllers import V2Tynys

SEASONS = {15: 'winter', 105: 'spring', 196: 'summer', 288: 'autumn'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=14)
    parser.add_argument('--output', type=Path, default=Path('data/flex.csv'))
    args = parser.parse_args()
    if not 1 <= args.days <= 30:
        parser.error('--days must be between 1 and 30')
    p = aktogay()
    options = {'time_limit': None, 'node_limit': 16, 'mip_rel_gap': .01}
    frames, diagnostics = [], []
    for doy, name in SEASONS.items():
        env, st = Env(p, Scenario(start_doy=doy, days=args.days), 7), init_state(p)
        ctl = V2Tynys(solver_options=options)
        records = []
        for t in range(args.days*24):
            r = step(p, env, st, t, ctl.decide(p, env, st, t), True)
            records.append({k:r[k] for k in ('flex_down_mw','flex_down_h','grid','feed','cu_t','trips')})
        frame = pd.DataFrame(records); frame['season'] = name; frames.append(frame)
        diagnostics.append(dict(season=name, fallback_steps=ctl.fallback_count,
                                limited_steps=ctl.limited_count, weather_source=env.w.get('source')))
        print(f'{name}: {len(records)} h; mean {frame.flex_down_mw.mean():.2f} MW; fallback {ctl.fallback_count}', flush=True)
    df = pd.concat(frames)
    rows = []
    for name, g in list(df.groupby('season', sort=False)) + [('all', df)]:
        rows.append(dict(season=name, mw_mean=g.flex_down_mw.mean(), mw_median=g.flex_down_mw.median(),
                         mw_p10=g.flex_down_mw.quantile(.1), mw_p90=g.flex_down_mw.quantile(.9),
                         h_mean=g.flex_down_h.mean(), h_median=g.flex_down_h.median(),
                         h_p10=g.flex_down_h.quantile(.1), h_p90=g.flex_down_h.quantile(.9)))
    out = pd.DataFrame(rows).round(2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    args.output.with_suffix('.json').write_text(json.dumps(dict(model_version='physics-v4-geomet-maintenance', seed=7,
        days_per_season=args.days, hours=len(df), solver_options=options, params=asdict(p),
        diagnostics=diagnostics, note='Includes zero-import hours. Duration is a resource ceiling at unchanged conditions.'),
        ensure_ascii=False, indent=2), encoding='utf-8')
    print(out.to_string(index=False))


if __name__ == '__main__':
    main()
