"""Model checks use the actual simulator and SciPy controller, not UI fixtures."""
import copy
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tynys.controllers import V2Tynys
from tynys.futures import EvaluationCancelled, evaluate, validate_request, _environment
from tynys.live import state_to_dict
from tynys.params import aktogay
from tynys.sim import init_state, flexibility


def snapshot():
    return {
        "state": state_to_dict(init_state(aktogay())),
        "sim_hour": 0, "start_doy": 293, "seed": 7, "scenario_rev": 0,
        "goal": "copper", "events": [], "source": "unit-test snapshot",
        "captured_at": "2026-10-20T00:00:00Z",
    }


class FuturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zero = evaluate({"reduction_mw": 0, "duration_h": 1, "lead_h": 0}, snapshot())
        cls.stressed = evaluate(
            {"reduction_mw": 200, "duration_h": 12, "lead_h": 0, "lull": True, "bess_fault": True},
            snapshot(),
        )

    def test_zero_request_is_exact_reference_and_has_no_delivery_claim(self):
        r = self.zero
        self.assertEqual(len(r["frames"]), 25)
        for f in r["frames"]:
            self.assertEqual(f["tynys"], f["reference"])
        self.assertEqual(r["summary"]["delivery"]["actual_grid_reduction_mwh"], 0)
        self.assertEqual(r["summary"]["recovery"]["copper_debt_end_t"], 0)
        self.assertEqual(r["summary"]["recovery"]["energy_debt_end_mwh"], 0)
        self.assertEqual(r["limits"]["grid_base_mw"], 260)
        self.assertEqual(r["limits"]["requested_cap_mw"], 260)

    def test_state_and_event_input_are_never_mutated(self):
        s = snapshot()
        s["events"] = [{"kind": "lull", "t0": 2, "dur": 12}]
        before = copy.deepcopy(s)
        evaluate({"reduction_mw": 0, "duration_h": 1, "lead_h": 0}, s)
        self.assertEqual(s, before)

    def test_repeat_is_deterministic_including_solver_status(self):
        r = evaluate({"reduction_mw": 0, "duration_h": 1, "lead_h": 0}, snapshot())
        self.assertEqual(r, self.zero)

    def test_impossible_low_cap_is_not_accepted(self):
        r = self.stressed
        self.assertNotEqual(r["verdict"]["status"], "feasible")
        self.assertTrue(r["verdict"]["reasons"])
        self.assertIn("copper_loss", {v["code"] for v in r["verdict"]["reasons"]})
        self.assertEqual(r["limits"]["requested_cap_mw"], 60)
        # Flow-dependent auxiliaries shut down with production. A 60 MW cap
        # need not cause unserved fixed load, but cannot preserve copper output.
        self.assertGreater(r["summary"]["reference"]["copper_t"], r["summary"]["tynys"]["copper_t"])

    def test_failed_battery_cannot_supply_or_absorb_energy(self):
        for f in self.stressed["frames"][:12]:
            for variant in ("baseline", "tynys", "reference"):
                self.assertEqual(f[variant]["bess_mw"], 0)
                self.assertEqual(f[variant]["bess_mwh"], 60)

    def test_all_worlds_have_identical_actual_disturbances(self):
        for f in self.stressed["frames"]:
            for key in ("wind_mw", "pv_mw", "mine_plan_tph"):
                self.assertEqual(f["baseline"][key], f["tynys"][key])
                self.assertEqual(f["reference"][key], f["tynys"][key])
            self.assertEqual(f["baseline"]["cap_mw"], f["tynys"]["cap_mw"])

    def test_json_is_strict_without_nan_or_infinity(self):
        for r in (self.zero, self.stressed):
            raw = json.dumps(r, ensure_ascii=False, allow_nan=False)
            self.assertIsInstance(json.loads(raw), dict)

    def test_snapshot_is_replayable_and_contains_actual_inputs(self):
        self.assertEqual(self.zero["snapshot"]["state"], snapshot()["state"])
        self.assertEqual(self.zero["snapshot"]["events"], [])
        self.assertEqual(self.zero["snapshot"]["source"], "unit-test snapshot")
        self.assertEqual(len(self.zero["snapshot"]["disturbance_sha256"]), 64)

    def test_request_bounds_and_types(self):
        bad = [
            {"duration_h": 13}, {"duration_h": 0}, {"duration_h": 1.5},
            {"reduction_mw": 201}, {"reduction_mw": -1}, {"reduction_mw": math.nan},
            {"recovery_h": 23}, {"recovery_h": 49}, {"lead_h": 7},
            {"max_copper_loss_pct": 11}, {"max_copper_loss_pct": math.inf},
            {"duration_h": True}, {"lull": "false"}, {"mode": "boundary"},
            {"surprise": 1}, {"id": ""}, {"id": "\n"},
        ]
        for req in bad:
            with self.subTest(req=req), self.assertRaises(ValueError):
                validate_request(req)

    def test_year_horizon_and_invalid_state_rejected_before_calculation(self):
        s = snapshot()
        s["sim_hour"] = 8750
        with self.assertRaisesRegex(ValueError, "год"):
            evaluate({}, s)
        s = snapshot()
        s["state"]["bess_e"] = math.nan
        with self.assertRaises(ValueError):
            evaluate({}, s)

    def test_cancelled_job_returns_no_result(self):
        with self.assertRaises(EvaluationCancelled):
            evaluate({}, snapshot(), cancelled=lambda: True)

    def test_progress_reports_actual_completed_hours(self):
        progress = []
        evaluate({"reduction_mw": 0, "duration_h": 1, "lead_h": 0}, snapshot(), progress=progress.append)
        self.assertTrue(progress)
        self.assertEqual(progress[-1]["completed_h"], progress[-1]["total_h"])

    def test_duration_scan_reports_tested_points_without_assuming_monotonicity(self):
        r = evaluate({"mode": "limit", "reduction_mw": 0, "duration_h": 1, "lead_h": 0}, snapshot())
        self.assertEqual([p["duration_h"] for p in r["boundary"]], [1, 2, 4, 6, 8, 12])
        self.assertTrue(all(p["status"] == "feasible" for p in r["boundary"]))
        self.assertIsNone(r["first_failed"])
        self.assertNotIn("max_duration_h", r)

    def test_existing_fault_intervals_are_combined(self):
        s = snapshot()
        s["events"] = [{"kind": "bess_fault", "t0": 0, "dur": 2},
                       {"kind": "bess_fault", "t0": 6, "dur": 2}]
        env = _environment(aktogay(), s, validate_request({}))
        self.assertFalse(env.bess_avail[0])
        self.assertTrue(env.bess_avail[3])
        self.assertFalse(env.bess_avail[6])

    def test_wind_forecast_multiplier_applied_exactly_once(self):
        s = snapshot()
        env = _environment(aktogay(), s, validate_request({"lull": True, "lead_h": 0}))
        from tynys import weather
        wf, _ = weather.forecast(env.w, 0, 12, env.seed)
        self.assertAlmostEqual(wf[0] * env.wind_mult[0], env.w["wind_pu"][0], places=12)

    def test_reserve_duration_is_bounded_by_battery_energy(self):
        p = aktogay()
        st = init_state(p)
        st.bess_e = p.bess_e_min + 1
        rec = {"line0": 3330, "line1": 3330, "mill_mw": 100, "feed": 6660,
               "charge": 0, "mine": 6700, "bess_available": True, "bess": 0,
               "grid": 260, "unserved": 0, "feed_soft": 3330, "feed_hard": 3330,
               "hard_frac": .5, "assets": {f"line-{l+1}": {"feed_tph": 3330, "mill_mw": st.line_mw[l]} for l in range(2)}}
        power, duration = flexibility(p, st, rec)
        self.assertGreater(power, 0)
        self.assertLessEqual(duration, 1.000001)
        rec["bess_available"] = False
        power_without_battery, _ = flexibility(p, st, rec)
        self.assertAlmostEqual(power - power_without_battery, math.sqrt(p.bess_eta_rt))

    def test_fallback_is_counted_and_does_not_fake_a_successful_mpc_plan(self):
        from types import SimpleNamespace
        p = aktogay()
        st = init_state(p)
        env = _environment(p, snapshot(), validate_request({}))
        ctl = V2Tynys()
        ctl.last_plan = {"stale": True}
        with patch("tynys.controllers.milp", return_value=SimpleNamespace(status=1, x=None)):
            d = ctl.decide(p, env, st, 0)
        self.assertEqual(ctl.fallback_count, 1)
        self.assertEqual(ctl.limited_count, 1)
        self.assertTrue(ctl.last_fallback)
        self.assertIsNone(ctl.last_plan)
        self.assertGreater(np.asarray(d["x"])[:, 1, :].sum(), 0)


if __name__ == "__main__":
    unittest.main()
