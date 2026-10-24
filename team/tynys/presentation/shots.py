"""Снимки экранов для презентации (img/*.png) без Docker.

Пульт и 3D получают двойники из последнего часа ui/trace.json (запись той же модели,
MPC и функций публикации, что стенд: scripts/record_trace.py) и атрибуты из
setup_twins (предрасчёты sizing/flex, эквивалент ВЭС). «Два будущих» снимается на
tests/serve_mine_fixture.py — настоящая модель и настоящий расчёт futures.

    python presentation/shots.py          # из team/tynys; нужен Python Playwright
"""
import asyncio
import json
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT), str(ROOT / "services")]
from setup_twins import twins  # noqa: E402

NS = "kz.tynys"
FRAME = json.loads((ROOT / "ui" / "trace.json").read_text(encoding="utf-8"))[-1]
TW = twins()


def thing(name):
    feats = dict(FRAME.get(name, {}))
    return {"thingId": f"{NS}:{name}", "attributes": TW.get(name, {}).get("attributes", {}),
            "features": {k: {"properties": {"value": v}} for k, v in feats.items()}}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT / "ui"), **k)

    def log_message(self, *a):
        pass

    def answer(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        if "/api/2/things" not in path:
            return super().do_GET()
        suffix = path.split("/api/2/things", 1)[1].strip("/")
        if not suffix:
            ids = parse_qs(url.query).get("ids", [""])[0].split(",")
            return self.answer([thing(i.split(":", 1)[1]) for i in ids if ":" in i])
        parts = suffix.split("/")
        value = thing(parts[0].split(":", 1)[1])
        for part in parts[1:]:
            value = value.get(part) if isinstance(value, dict) else None
        return self.answer(value, 200 if value is not None else 404)

    def do_PUT(self):
        self.answer(None, 204)


async def shoot():
    from playwright.async_api import async_playwright
    srv = ThreadingHTTPServer(("127.0.0.1", 18111), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    fx = subprocess.Popen([sys.executable, str(ROOT / "tests" / "serve_mine_fixture.py"), "18112"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            pg = await b.new_page(viewport={"width": 1440, "height": 900})
            await pg.goto("http://127.0.0.1:18111/dashboard.html")
            await pg.wait_for_timeout(6000)
            await pg.screenshot(path=str(HERE / "img" / "pult.png"))
            await pg.goto("http://127.0.0.1:18111/3d.html")
            await pg.wait_for_timeout(8000)
            if await pg.locator("#skip").is_visible():
                await pg.locator("#skip").click()
            await pg.wait_for_timeout(5000)
            await pg.screenshot(path=str(HERE / "img" / "3d.png"))
            for _ in range(60):
                try:
                    await pg.goto("http://127.0.0.1:18112/futures.html")
                    break
                except Exception:
                    time.sleep(0.5)
            await pg.wait_for_timeout(4000)
            await pg.get_by_role("button", name="Проверить обещание").first.click()
            await pg.wait_for_function("() => document.body.innerText.includes('Расчёт завершён')", timeout=240000)
            await pg.wait_for_timeout(3000)
            await pg.screenshot(path=str(HERE / "img" / "futures.png"))
            await b.close()
    finally:
        fx.terminate()
        srv.shutdown()


if __name__ == "__main__":
    asyncio.run(shoot())
    print("img/pult.png, img/3d.png, img/futures.png")
