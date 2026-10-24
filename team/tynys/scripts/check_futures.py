#!/usr/bin/env python3
"""End-to-end experiment through the same Ditto proxy used by the browser."""
import json
import os
from pathlib import Path
import time
import uuid
from urllib.request import Request, urlopen

base = os.environ.get("TYNYS_URL", "http://127.0.0.1:8095").rstrip("/")
api = base + "/ditto/api/2/things/kz.tynys:"


def http(url, value=None):
    raw = None if value is None else json.dumps(value).encode()
    with urlopen(Request(url, data=raw, method="GET" if value is None else "PUT",
                         headers={"Content-Type": "application/json"}), timeout=15) as res:
        body = res.read()
        return json.loads(body) if body else None


def prop(thing, key, default=None):
    return thing.get("features", {}).get(key, {}).get("properties", {}).get("value", default)


def main():
    for filename in ("futures.html", "futures.js", "futures.css", "future-scene.js"):
        with urlopen(base + "/" + filename, timeout=10) as response:
            assert response.status == 200 and len(response.read()) > 100, filename
    request = {
        "id": str(uuid.uuid4()), "mode": "evaluate", "reduction_mw": 0,
        "duration_h": 1, "lead_h": 0, "recovery_h": 24,
        "max_copper_loss_pct": 1, "lull": False, "bess_fault": False, "hard_ore": False,
    }
    http(api + "future-request/features/request_json/properties/value",
         json.dumps(request))
    deadline = time.monotonic() + 720
    last_status = None
    while time.monotonic() < deadline:
        thing = http(api + "future-result")
        status = prop(thing, "status")
        if prop(thing, "request_id") != request["id"]:
            time.sleep(2)
            continue
        if status != last_status:
            print("experiment:", status, flush=True)
            last_status = status
        if status == "error":
            raise AssertionError(prop(thing, "error"))
        if status == "done":
            result = json.loads(prop(thing, "result_json"))
            assert result["request"]["id"] == request["id"]
            assert result["schema_version"] == 1
            assert len(result["frames"]) == 25
            assert all(all(k in frame for k in ("baseline", "tynys", "reference"))
                       for frame in result["frames"])
            assert result["snapshot"]["source"].startswith("OpenEgiz")
            assert abs(result["summary"]["recovery"]["copper_debt_end_t"]) < 1e-5
            assert abs(result["summary"]["recovery"]["energy_debt_end_mwh"]) < 1e-5
            out = Path(os.environ.get("TYNYS_REPORT", "futures-e2e-report.json"))
            out.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            print("FUTURES E2E OK: request → Ditto → solver → MQTT → Ditto; report:", out)
            return
        time.sleep(2)
    raise TimeoutError("Experiment did not finish through the platform in 12 minutes.")


if __name__ == "__main__":
    main()
