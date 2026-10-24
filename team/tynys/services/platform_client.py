"""Минимальный клиент платформы OpenEgiz: Ditto HTTP API и MQTT (telemetry/<twin>)."""
import base64, json, os, time, urllib.request, urllib.error
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tynys.telemetry import features as feature_document

NS = "kz.tynys"
DITTO_URL = os.environ.get("DITTO_URL", "http://localhost:8080").rstrip("/")
AUTH = "Basic " + base64.b64encode(
    f"{os.environ.get('DITTO_USER', 'ditto')}:{os.environ.get('DITTO_PASSWORD', 'ditto')}".encode()).decode()


def http(method, path, body=None, timeout=10):
    req = urllib.request.Request(DITTO_URL + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": AUTH, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None)


def get_things(names, fields="thingId,features"):
    ids = ",".join(f"{NS}:{n}" for n in names)
    _, data = http("GET", f"/api/2/things?ids={ids}&fields={fields}")
    return {t["thingId"].split(":", 1)[1]: t for t in data}


def prop(thing, feature, default=None):
    try:
        return thing["features"][feature]["properties"]["value"]
    except (KeyError, TypeError):
        return default


def modify(name, features):
    """Ditto-протокол: заменить все свойства двойника (как в Примере рудника)."""
    return {"topic": f"{NS}/{name}/things/twin/commands/modify", "path": "/features",
            "value": feature_document(features)}


class Bus:
    def __init__(self, client_id):
        import paho.mqtt.client as mqtt
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        host, port = os.environ.get("MQTT_HOST", "localhost"), int(os.environ.get("MQTT_PORT", "1883"))
        for i in range(60):
            try:
                self.c.connect(host, port, 30); break
            except OSError:
                time.sleep(2)
        self.c.loop_start()

    def send(self, name, features):
        self.c.publish(f"telemetry/{name}", json.dumps(modify(name, features), ensure_ascii=False, default=lambda o: o.item()), qos=1)


def wait_ditto(tries=120):
    for _ in range(tries):
        try:
            http("GET", f"/api/2/things/{NS}:site")
            return True
        except Exception:
            time.sleep(3)
    return False
