"""Service lifecycle tests, without network or production setpoint writes."""
import copy
import json
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services")]
from futures_service import Jobs, capture_snapshot, decode_request


def thing(**features):
    return {"features": {key: {"properties": {"value": value}}
                         for key, value in features.items()}}


class ServiceTests(unittest.TestCase):
    def test_snapshot_rejects_revision_mismatch(self):
        values = {
            "site": thing(state_json="{}", sim_hour=7, seed=9, start_doy=100, scenario_rev=2),
            "scenario": thing(rev=3, events="[]", goal="green"),
        }
        with self.assertRaises(ValueError):
            capture_snapshot(values)
        values["scenario"] = thing(rev=2, events="[]", goal="green")
        snap = capture_snapshot(values)
        self.assertEqual((snap["sim_hour"], snap["seed"], snap["goal"]), (7, 9, "green"))

    def test_invalid_envelope(self):
        for value in ("[]", "null", '{"mode":"evaluate"}', "x" * 16385):
            with self.assertRaises((ValueError, TypeError)):
                decode_request(value)
        self.assertEqual(decode_request('{"id":"stop","mode":"cancel"}')["mode"], "cancel")

    def test_single_snapshot_and_strict_result(self):
        writes = []
        source = {"state": {"energy": 30}}
        def evaluator(request, snapshot, progress, cancelled):
            snapshot["state"]["energy"] = 12
            progress(50, "Проверяем")
            return {"frames": [], "request": request, "snapshot": snapshot}
        jobs = Jobs(lambda name, payload: writes.append((name, payload)), evaluator)
        try:
            jobs.submit({"id": "a", "mode": "evaluate"}, source)
            jobs.future.result(timeout=2)
            jobs.poll()
            self.assertEqual(source["state"]["energy"], 30)
            self.assertEqual(writes[-1][1]["status"], "done")
            self.assertEqual(json.loads(writes[-1][1]["result_json"])["request"]["id"], "a")
            self.assertTrue(all(name == "future-result" for name, _ in writes))
        finally:
            jobs.close()

    def test_nonfinite_result_cannot_be_published_as_success(self):
        writes = []
        jobs = Jobs(lambda _, payload: writes.append(payload),
                    lambda *args, **kwargs: {"bad": float("nan")})
        try:
            jobs.submit({"id": "bad", "mode": "evaluate"}, {})
            jobs.future.result(timeout=2)
            with self.assertLogs("futures", level="ERROR"):
                jobs.poll()
            self.assertEqual(writes[-1]["status"], "error")
            self.assertEqual(writes[-1]["result_json"], "")
        finally:
            jobs.close()

    def test_cancel_ignores_old_progress_and_completion(self):
        entered, release = threading.Event(), threading.Event()
        writes = []
        def evaluator(request, snapshot, progress, cancelled):
            entered.set()
            release.wait(2)
            progress(90, "Старый расчёт")
            return {"old": True}
        jobs = Jobs(lambda _, payload: writes.append(copy.deepcopy(payload)), evaluator)
        try:
            jobs.submit({"id": "a", "mode": "evaluate"}, {})
            self.assertTrue(entered.wait(2))
            old = jobs.future
            jobs.submit({"id": "stop", "mode": "cancel"})
            release.set()
            old.result(timeout=2)
            jobs.poll()
            self.assertEqual(writes[-1]["status"], "cancelled")
            self.assertEqual(writes[-1]["request_id"], "stop")
            self.assertEqual(jobs.features["result_json"], "")
        finally:
            release.set()
            jobs.close()

    def test_terminal_report_retried_until_ditto_confirms_and_never_overwrites_new_request(self):
        writes = []
        jobs = Jobs(lambda _, payload: writes.append(copy.deepcopy(payload)),
                    lambda *args, **kwargs: {"ok": True})
        try:
            jobs.submit({"id": "a", "mode": "evaluate"}, {})
            jobs.future.result(timeout=2)
            jobs.poll()
            before = len(writes)
            jobs.last_publish = 0
            jobs.confirm_delivery(thing(status="running", request_id="a"), "a")
            self.assertEqual(len(writes), before + 1)
            self.assertEqual(writes[-1]["status"], "done")
            jobs.last_publish = 0
            jobs.confirm_delivery(thing(**writes[-1]), "a")
            self.assertEqual(len(writes), before + 1)
            jobs.confirm_delivery(thing(status="running", request_id="b"), "b")
            self.assertEqual(len(writes), before + 1)
        finally:
            jobs.close()


if __name__ == "__main__":
    unittest.main()
