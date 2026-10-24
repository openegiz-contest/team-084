"""A daylight start must select actual model hour 9, not relabel midnight."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services")]
from field import start_clock, Totals
from tynys.live import build_env, state_to_dict
from tynys.sim import init_state, step
from tynys.controllers import V1Reactive


class StartClockTests(unittest.TestCase):
    def test_date_and_hour_are_independent_and_validated(self):
        self.assertEqual(start_clock({"START_DOY": "100"}), (100, 9))
        self.assertEqual(start_clock({"START_DOY": "200", "START_HOUR": "0"}), (200, 0))
        for settings in ({"START_HOUR": "24"}, {"START_HOUR": "-1"}, {"START_DOY": "0"}):
            with self.assertRaises(ValueError):
                start_clock(settings)

    def test_first_daylight_step_has_no_prior_production(self):
        day, hour = start_clock({"START_DOY": "180"})
        p, env = build_env([], day, 7)
        state = init_state(p)
        totals = Totals()
        self.assertEqual((totals.hours, totals.cu, totals.grid), (0, 0, 0))
        self.assertGreater(env.w["pv_pu"][hour], 0)
        before = state_to_dict(state)
        decision = V1Reactive().decide(p, env, state, hour)
        record = step(p, env, state, hour, decision, False)
        totals.add(p, record, state)
        self.assertEqual(totals.hours, 1)
        self.assertEqual(totals.cu, record["cu_t"])
        self.assertNotEqual(before, state_to_dict(state))


if __name__ == "__main__":
    unittest.main()
