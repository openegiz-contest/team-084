"""Local UI test only: actual model + fake Ditto transport, no MQTT claim."""
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services")]
from futures_service import Jobs, decode_request
from tynys.live import state_to_dict
from tynys.params import aktogay
from tynys.sim import init_state

state = {"status": "idle", "request_id": "", "progress": 0, "result_json": ""}
request_value = ""
state_lock = threading.Lock()


def publish(name, features):
    assert name == "future-result"
    with state_lock:
        state.clear()
        state.update(features)


jobs = Jobs(publish)
snapshot = {
    "state": state_to_dict(init_state(aktogay())), "sim_hour": 0,
    "start_doy": 105, "seed": 7, "scenario_rev": 0, "events": [],
    "goal": "copper", "source": "Локальный тест: модель настоящая, транспорт Ditto имитирован",
    "captured_at": "2026-10-20T00:00:00+00:00",
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "ui"), **kwargs)

    def log_message(self, *args):
        pass

    def answer(self, value, status=200):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path.endswith("/things/kz.tynys:future-result"):
            with state_lock:
                thing = {"thingId": "kz.tynys:future-result",
                         "features": {k: {"properties": {"value": v}} for k, v in state.items()}}
            self.answer(thing)
        elif path.endswith("/things/kz.tynys:future-request"):
            self.answer({"thingId": "kz.tynys:future-request",
                         "features": {"request_json": {"properties": {"value": request_value}}}})
        elif path.endswith("/things/kz.tynys:future-request/features/request_json/properties/value"):
            self.answer(request_value)
        elif path.startswith("/ditto/"):
            self.answer({"error": "Only future-result is provided by this test fixture."}, 404)
        else:
            super().do_GET()

    def do_PUT(self):
        global request_value
        path = unquote(urlparse(self.path).path)
        if not path.endswith("/things/kz.tynys:future-request/features/request_json/properties/value"):
            return self.answer({}, 404)
        try:
            raw = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            request = decode_request(raw)
            request_value = raw
            jobs.submit(request, snapshot)
            self.answer(None)
        except (ValueError, TypeError) as error:
            self.answer({"error": str(error)}, 400)


def main():
    def poll():
        while True:
            jobs.poll()
            time.sleep(0.05)
    threading.Thread(target=poll, daemon=True).start()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18097
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"UI TEST FIXTURE http://127.0.0.1:{port}/futures.html", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        jobs.close()


if __name__ == "__main__":
    main()
