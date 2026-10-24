#!/usr/bin/env python3
"""Frozen-snapshot experiments: Ditto request → model → MQTT → Ditto result.

This service never changes production setpoints. Each report is a model
experiment from one explicitly recorded state, not a live operating guarantee.
"""
import copy
import datetime as dt
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tynys.futures import evaluate, validate_request
from platform_client import Bus, get_things, prop, wait_ditto

log = logging.getLogger("futures")


def capture_snapshot(things):
    """A site publication is atomic; reject a scenario from another revision."""
    site, scenario = things.get("site"), things.get("scenario")
    state = prop(site, "state_json")
    hour = prop(site, "sim_hour")
    if state is None or hour is None:
        raise ValueError("Ожидаем первое состояние рудника от поля.")
    revision = prop(scenario, "rev", 0)
    if prop(site, "scenario_rev", 0) != revision:
        raise ValueError("Поле ещё применяет изменённый сценарий. Повторяем чтение.")
    snapshot = {
        "state": json.loads(state), "sim_hour": int(hour),
        "seed": int(prop(site, "seed")), "start_doy": int(prop(site, "start_doy")),
        "scenario_rev": int(revision),
        "events": json.loads(prop(scenario, "events", "[]")),
        "goal": prop(scenario, "goal", "green"),
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "OpenEgiz / kz.tynys:site + kz.tynys:scenario",
    }
    return snapshot


def decode_request(raw):
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("Запрос должен быть строкой JSON не длиннее 16 КБ.")
    request = json.loads(raw)
    if not isinstance(request, dict):
        raise ValueError("Ожидается объект запроса.")
    request_id = request.get("id")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 80:
        raise ValueError("Запросу нужен уникальный id длиной до 80 символов.")
    if request.get("mode") == "cancel":
        return {"id": request_id, "mode": "cancel"}
    return validate_request(request)


class Jobs:
    """Single solver worker; newer requests cancel obsolete work cooperatively."""
    def __init__(self, publish, evaluator=evaluate):
        self.publish = publish
        self.evaluator = evaluator
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="futures")
        self.future = None
        self.cancel = threading.Event()
        self.request_id = ""
        self.features = {}
        self.lock = threading.Lock()
        self.dirty = False
        self.started = 0
        self.last_publish = 0

    def send(self, status, **values):
        with self.lock:
            self.features = {
                "status": status, "request_id": self.request_id,
                "progress": 0, "stage": "", "error": "", "result_json": "",
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(), **values,
            }
            payload = copy.deepcopy(self.features)
            self.dirty = False
        self.publish("future-result", payload)
        self.last_publish = time.monotonic()

    def confirm_delivery(self, remote, desired_request_id):
        """MQTT delivery alone is not confirmation that Ditto stored the report."""
        with self.lock:
            payload = copy.deepcopy(self.features)
        if (payload.get("status") not in ("done", "cancelled", "error") or
                payload.get("request_id") != desired_request_id):
            return
        matches = (prop(remote, "request_id") == payload["request_id"] and
                   prop(remote, "status") == payload["status"])
        if matches and payload["status"] == "done":
            matches = prop(remote, "result_json") == payload["result_json"]
        if not matches and time.monotonic() - self.last_publish >= 2:
            self.publish("future-result", payload)
            self.last_publish = time.monotonic()

    def submit(self, request, snapshot=None):
        self.cancel.set()
        if self.future:
            self.future.cancel()
        self.cancel = threading.Event()
        token = self.cancel
        self.request_id = request["id"]
        request_id = self.request_id
        if request["mode"] == "cancel":
            self.future = None
            self.send("cancelled", stage="Расчёт отменён. Состояние рудника не изменено.")
            return
        frozen = copy.deepcopy(snapshot)
        self.send("running", stage="Снимок зафиксирован. Считаем варианты управления.")
        self.started = time.monotonic()

        def progress(percent, stage=""):
            if token.is_set():
                return
            if isinstance(percent, dict):
                update = percent
                code = str(update.get("stage", ""))
                names = {"baseline": "Обычное управление", "reference": "Контрольный прогон",
                         "tynys": "План «Тыныс»", "alternative": "Меньший запрос"}
                stage = names.get(code, "Проверка длительности " + code.rsplit("_", 1)[-1] + " ч")
                completed, total = update.get("completed_h", 0), update.get("total_h", 1)
                stage += f": час {completed} из {total}"
                # Progress refers to the current named stage; it is not a fake ETA.
                percent = 100 * completed / max(1, total)
            with self.lock:
                if self.request_id == request_id:
                    self.features.update(progress=max(0, min(99, float(percent))),
                                         stage=str(stage),
                                         updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
                    self.dirty = True

        self.future = self.executor.submit(
            self.evaluator, copy.deepcopy(request), frozen,
            progress=progress, cancelled=token.is_set)

    def poll(self):
        if not self.future:
            return
        if self.future.done():
            future, self.future = self.future, None
            try:
                result = future.result()
                # Refuse non-standard JSON, including NaN and Infinity.
                encoded = json.dumps(result, ensure_ascii=False, allow_nan=False,
                                     separators=(",", ":"))
                if len(encoded.encode("utf-8")) > 800000:
                    raise ValueError("Отчёт превышает допустимые 800 КБ; сократите горизонт.")
                self.send("done", progress=100, stage="Расчёт завершён.", result_json=encoded)
            except Exception as error:
                log.exception("calculation failed")
                self.send("error", error=str(error)[:500],
                          stage="Расчёт не завершён; обещание не подтверждено.")
            return
        if time.monotonic() - self.started > 900:
            self.cancel.set()
            self.future = None
            self.send("error", error="Расчёт превысил 15 минут. Уменьшите горизонт или число условий.")
            return
        with self.lock:
            payload = copy.deepcopy(self.features) if self.dirty else None
            self.dirty = False
        if payload is not None:
            self.publish("future-result", payload)

    def close(self):
        self.cancel.set()
        if self.future:
            self.future.cancel()
        self.executor.shutdown(wait=True, cancel_futures=True)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s futures %(message)s")
    if not wait_ditto():
        raise RuntimeError("Ditto не запустился.")
    bus = Bus("tynys-futures")
    jobs = Jobs(bus.send)
    seen = None
    try:
        while True:
            jobs.poll()
            try:
                things = get_things(["future-request", "future-result", "site", "scenario"])
                raw = prop(things.get("future-request"), "request_json", "")
                if not raw:
                    time.sleep(0.5)
                    continue
                if raw == seen:
                    jobs.confirm_delivery(things.get("future-result"), jobs.request_id)
                    time.sleep(0.5)
                    continue
                request = decode_request(raw)
                previous = things.get("future-result")
                if (request["id"] == prop(previous, "request_id") and
                        prop(previous, "status") in ("done", "cancelled", "error")):
                    seen = raw
                    continue
                if request["mode"] == "cancel":
                    jobs.submit(request)
                else:
                    # Retry capture without consuming the request if revisions differ.
                    try:
                        snapshot = capture_snapshot(things)
                    except (ValueError, TypeError, KeyError) as error:
                        log.warning("snapshot: %s", error)
                        time.sleep(1)
                        continue
                    jobs.submit(request, snapshot)
                seen = raw
                log.info("accepted %s (%s)", request["id"], request["mode"])
            except (ValueError, TypeError, KeyError) as error:
                seen = raw
                jobs.cancel.set()
                if jobs.future:
                    jobs.future.cancel()
                    jobs.future = None
                try:
                    jobs.request_id = json.loads(raw).get("id", "")
                except (ValueError, AttributeError, TypeError):
                    jobs.request_id = ""
                jobs.send("error", error=str(error)[:500], stage="Проверьте параметры запроса.")
            except Exception as error:
                # A network failure must never create an invented offline result.
                log.warning("platform: %s", error)
            time.sleep(0.5)
    finally:
        jobs.close()


if __name__ == "__main__":
    main()
