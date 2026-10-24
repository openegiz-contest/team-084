"""Keep live and offline carbon accounting consistent; reject stale deployments."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'services'), str(ROOT / 'scripts')]
import pandas as pd
from field import Totals
from tynys.live import build_env
from tynys.sim import init_state, step
from tynys.controllers import V0Traditional, V1Reactive, V2Tynys
from tynys.metrics import summarize
from platform_client import modify
from setup_twins import sizing
from check_stand import validate_metrics


class CarbonDeliveryTests(unittest.TestCase):
    def test_live_totals_match_offline_accounting_for_all_controllers(self):
        p, env = build_env([], 105, 7)
        for controller in (V0Traditional(), V1Reactive(), V2Tynys()):
            with self.subTest(controller=type(controller).__name__):
                state, totals, records = init_state(p), Totals(), []
                for hour in range(9, 21):
                    row = step(p, env, state, hour, controller.decide(p, env, state, hour), controller.segregated)
                    totals.add(p, row, state)
                    records.append(row)
                offline = summarize(p, pd.DataFrame(records), p.pile_cap_t * p.pile_init_frac)
                wire = modify('site', totals.feats())['value']
                for key in ('co2_t', 'co2_adj_t', 'cu_adj_t'):
                    self.assertAlmostEqual(wire[key]['properties']['value'], offline[key], delta=0.051)
                self.assertAlmostEqual(wire['co2_per_t_cu']['properties']['value'],
                                       offline['co2_adj_t'] / offline['cu_adj_t'], delta=0.00051)

    def test_release_check_rejects_old_field_or_old_reference_data(self):
        things = [{'thingId': 'kz.tynys:' + name, 'features': modify(name, Totals().feats())['value']}
                  for name in ('site', 'shadow-v0', 'shadow-v1')]
        rows = sizing()
        validate_metrics(things, rows)
        old = copy.deepcopy(things)
        del old[0]['features']['co2_adj_t']
        with self.assertRaisesRegex(ValueError, 'rebuild'):
            validate_metrics(old, rows)
        old_rows = copy.deepcopy(rows)
        del old_rows[0]['co2_adj_kt']
        with self.assertRaisesRegex(ValueError, 'refresh'):
            validate_metrics(things, old_rows)


if __name__ == '__main__':
    unittest.main()
