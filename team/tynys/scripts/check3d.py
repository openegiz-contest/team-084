"""Check the actual 3D scene in Chromium with software WebGL.

Usage remains: python check3d.py URL out.png
--mode all (default) checks functionality and gates performance. functional
checks the live UI and records FPS without gating it; performance only measures
the renderer on a separately hosted replay. --expect-source rejects fallback.
CHROME_PATH selects an installed Chrome executable (including Windows).
TYNYS_3D_ARTIFACT_DIR overrides the output directory.
TYNYS_MIN_FPS is the required median of one-second rendered-frame windows
(default 10, not a claim of 60 fps on every CPU). Every mode reports whether
that threshold was met; functional mode explicitly marks it as non-gating.
TYNYS_FPS_SECONDS defaults to 10 and TYNYS_FPS_WARMUP_SECONDS to 3.

The performance run uses the requested page and its actual source. A separate
browser-route fixture tests scenario display/cancellation without changing the
running mine. That fixture is explicitly identified in the JSON report.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright


VIEWPORT = {"width": 1400, "height": 850}
GL_ARGS = ["--use-gl=angle", "--use-angle=swiftshader",
           "--enable-unsafe-swiftshader", "--disable-background-timer-throttling",
           "--disable-renderer-backgrounding"]

READ_METRICS = """() => {
  const a = window.__tynys, r = a.renderer, gl = r.getContext();
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  return {
    now: performance.now(), renderedFrames: a.renderedFrames,
    frameTimes: Array.from(a.frameTimes || []),
    rendererFrame: r.info.render.frame,
    drawCalls: r.info.render.calls, triangles: r.info.render.triangles,
    points: r.info.render.points, lines: r.info.render.lines,
    pixelRatio: r.getPixelRatio(), low: a.low, softGL: a.softGL,
    glRenderer: String(gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER)),
    glVendor: String(gl.getParameter(ext ? ext.UNMASKED_VENDOR_WEBGL : gl.VENDOR)),
    glVersion: String(gl.getParameter(gl.VERSION)),
    drawingBuffer: [gl.drawingBufferWidth, gl.drawingBufferHeight],
    mergeStats: a.mergeStats || null,
    lightingHour: a.lightingHour,
    browser: navigator.userAgent, hardwareConcurrency: navigator.hardwareConcurrency
  };
}"""


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def low_url(url):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["q"] = "low"
    # The default-day assertion must not inherit a caller's night override.
    query.pop("h", None)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


async def ready(page, url):
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_function(
        "() => window.__tynys && window.__tynys.renderer && "
        "Number.isFinite(window.__tynys.renderedFrames) && "
        "window.__tynys.renderedFrames > 2", timeout=60000)
    skip = page.locator("#skip")
    if await skip.is_visible():
        await skip.click()
    await page.wait_for_function(
        "() => document.querySelector('#clock').textContent.trim() !== '—' && "
        "document.querySelector('#src').textContent.trim().length > 0",
        timeout=30000)
    await page.wait_for_timeout(500)


async def rendered_fps(page, seconds, warmup):
    """Count renderer completions, not requestAnimationFrame callbacks."""
    await page.wait_for_timeout(warmup * 1000)
    initial = await page.evaluate(READ_METRICS)
    require(finite(initial["renderedFrames"]), "Scene has no real rendered-frame counter")
    samples, timestamps = [], set()
    start = initial["now"]
    while True:
        await page.wait_for_timeout(250)
        sample = await page.evaluate(READ_METRICS)
        samples.append(sample)
        timestamps.update(t for t in sample["frameTimes"] if finite(t) and t >= start)
        if sample["now"] - start >= seconds * 1000:
            break
    last = samples[-1]
    elapsed = (last["now"] - start) / 1000
    frames = last["renderedFrames"] - initial["renderedFrames"]
    require(frames > 0, "No frames were actually rendered during measurement")
    require(all(sample["drawCalls"] > 0 and sample["triangles"] > 0 for sample in samples),
            "Renderer reported no draw calls or triangles")
    # A capped frameTimes ring is collected every 250 ms, so high FPS cannot
    # silently discard the early part of the measurement.
    require(abs(len(timestamps) - frames) <= 2,
            "Rendered-frame timestamps and completion counter disagree")
    windows = math.floor(elapsed)
    require(windows >= 5, "At least five complete one-second windows are required")
    bins = [sum(start + i * 1000 <= t < start + (i + 1) * 1000
                for t in timestamps) for i in range(windows)]
    draw_calls = [s["drawCalls"] for s in samples]
    triangles = [s["triangles"] for s in samples]
    return {
        "method": "completed renderer.render calls; full one-second windows",
        "warmup_seconds": warmup, "elapsed_seconds": round(elapsed, 3),
        "rendered_frames": frames, "timestamp_count": len(timestamps),
        "average_fps": round(frames / elapsed, 2),
        "median_fps": round(statistics.median(bins), 2),
        "p10_fps": round(percentile(bins, .1), 2), "min_fps": min(bins),
        "one_second_fps": bins,
        "draw_calls": {"min": min(draw_calls), "median": statistics.median(draw_calls), "max": max(draw_calls)},
        "triangles": {"min": min(triangles), "median": statistics.median(triangles), "max": max(triangles)},
        "environment": {k: last[k] for k in (
            "glRenderer", "glVendor", "glVersion", "pixelRatio", "low", "softGL",
            "drawingBuffer", "browser", "hardwareConcurrency", "mergeStats")},
    }


async def click_moving_label(page, object_id):
    """Use a real mouse at the current hit-tested rectangle of a CSS2D label.

    CSS2D labels can keep moving by subpixels while OrbitControls damping settles.
    Locator.click's stable-box requirement is unsuitable for that animation; the
    hit test and selected-object assertion still require the intended real target.
    """
    label = page.locator('.lbl[data-object="' + object_id + '"]')
    await label.wait_for(state="visible", timeout=15000)
    for attempt in range(1, 5):
        point = await label.evaluate("""el => {
          const rect = el.getBoundingClientRect();
          for (const [fx, fy] of [[.5,.5],[.35,.5],[.65,.5],[.5,.3],[.5,.7]]) {
            const x = rect.left + rect.width * fx, y = rect.top + rect.height * fy;
            if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
            const hit = document.elementFromPoint(x, y);
            if (hit && el.contains(hit)) return {x, y};
          }
          return null;
        }""")
        if point:
            await page.mouse.click(point["x"], point["y"])
            try:
                await page.wait_for_function(
                    "id => window.__tynys.selected === id",
                    arg=object_id, timeout=1200)
                return {"attempt": attempt, "x": point["x"], "y": point["y"]}
            except PlaywrightTimeoutError:
                pass
        await page.wait_for_timeout(150)
    raise AssertionError("A real mouse click could not select the visible " + object_id + " label")


async def check_controls(page):
    require(await page.locator("#light-hour").count() == 1, "Lighting slider missing")
    require(await page.locator("#compass").is_visible(), "Compass missing")
    before = await page.locator("#compass-arrow").evaluate(
        "el => getComputedStyle(el).transform")
    # Drag on bare terrain: with many equipment labels a fixed point may land on
    # a DOM label, which (correctly) does not rotate the camera.
    start = await page.evaluate("""() => {
      const canvas = document.querySelector('canvas');
      for (const y of [430, 520, 600, 360, 660]) for (const x of [700, 560, 840, 460, 960]) {
        const ok = [[0,0],[120,30],[60,15]].every(([dx,dy]) => document.elementFromPoint(x+dx, y+dy) === canvas);
        if (ok) return {x, y};
      }
      return {x: 700, y: 430};
    }""")
    await page.mouse.move(start["x"], start["y"])
    await page.mouse.down()
    await page.mouse.move(start["x"] + 120, start["y"] + 30, steps=10)
    await page.mouse.up()
    await page.wait_for_timeout(800)
    after = await page.locator("#compass-arrow").evaluate(
        "el => getComputedStyle(el).transform")
    require(before != after, "Compass did not respond to camera rotation")
    await page.locator("#reset").click()
    await page.wait_for_timeout(500)
    meters = await page.locator(".mini-bar[role=meter]").evaluate_all(
        """els => els.map(el => ({
          value: el.hasAttribute('aria-valuenow') ? Number(el.getAttribute('aria-valuenow')) : null,
          min: Number(el.getAttribute('aria-valuemin') || 0),
          max: Number(el.getAttribute('aria-valuemax') || 100)
        }))""")
    require(len(meters) >= 3, "Equipment labels lack status meters")
    supplied_meters = [meter for meter in meters if meter["value"] is not None]
    require(len(supplied_meters) >= 3, "Fewer than three meters have actual twin values")
    require(all(finite(m["value"]) and m["min"] <= m["value"] <= m["max"] for m in supplied_meters),
            "Status meter has out-of-range values")
    click = await click_moving_label(page, "bess")
    require(await page.evaluate("window.__tynys.selected === 'bess'"),
            "The click selected a different piece of equipment")
    require(await page.locator("#selection-panel").is_visible(), "Equipment selection panel did not open")
    require(await page.locator("#selection-name").inner_text() == "Накопитель",
            "Selection panel title does not belong to BESS")
    require("kz.tynys:bess" in await page.locator("#selection-source").inner_text(),
            "Selection panel source does not belong to the BESS twin")
    await page.wait_for_function("""() => {
      if (window.__tynys.selected !== 'bess') return false;
      const twin = window.__tynys.data.bess || {};
      const rows = new Map(Array.from(document.querySelectorAll('#selection-values dt'),
        el => [el.textContent.trim(), el.nextElementSibling?.textContent.trim()]));
      const fields = [
        ['soc','Заряд','%'], ['power_mw','Мощность','МВт'],
        ['energy_mwh','Энергия','МВт·ч'], ['available','Доступен','']
      ].filter(([key]) => Object.prototype.hasOwnProperty.call(twin, key));
      return fields.length >= 2 && fields.every(([key, title, unit]) => {
        const raw = twin[key];
        const value = typeof raw === 'boolean' ? (raw ? 'да' : 'нет')
          : Number(raw).toLocaleString('ru-RU', {maximumFractionDigits:1});
        return rows.get(title) === (value + ' ' + unit).trim();
      });
    }""", timeout=5000)
    selection = {
        "name": await page.locator("#selection-name").inner_text(),
        "values": await page.locator("#selection-values").inner_text(),
        "source": await page.locator("#selection-source").inner_text(),
        "values_match_bess_twin": True, "mouse_click": click,
    }
    await page.locator("#selection-close").click()
    require(not await page.locator("#selection-panel").is_visible(), "Selection panel did not close")
    return {"compass_rotates": True, "status_meters": len(meters),
            "meters_with_twin_values": len(supplied_meters), "selection": selection}


async def set_hour(page, hour):
    await page.locator("#light-hour").evaluate(
        "(el, h) => { el.value = String(h); el.dispatchEvent(new Event('input', {bubbles:true})); }",
        hour)
    await page.wait_for_function(
        "h => Math.abs(window.__tynys.lightingHour - h) < .05", arg=hour)
    # Allow the scene's smooth lighting interpolation to settle.
    await page.wait_for_timeout(1800)


async def scenario_fixture(context, url, errors, screenshot_path):
    """UI/protocol test only: no scenario PUT reaches the live stand."""
    response = await context.request.get(urljoin(url, "trace.json"))
    require(response.ok, "Scenario UI fixture requires the repository's trace.json")
    trace = await response.json()
    require(isinstance(trace, list) and len(trace) > 0, "Trace fixture is empty")
    snapshot = copy.deepcopy(trace[0])
    hour = snapshot.get("site", {}).get("sim_hour", 0)
    events = [
        {"id": "qa-lull", "kind": "lull", "t0": hour, "dur": 24},
        {"id": "qa-line", "kind": "line_trip", "t0": hour, "dur": 8},
        {"id": "qa-grid", "kind": "kegoc", "t0": hour, "dur": 4},
        {"id": "qa-bess", "kind": "bess_fault", "t0": hour, "dur": 12},
        {"id": "qa-hard", "kind": "hard_ore", "t0": hour, "dur": 72},
        {"id": "qa-plan", "kind": "plan_up", "t0": hour, "dur": 48},
    ]
    snapshot.setdefault("scenario", {}).update(events=json.dumps(events), rev=100, goal="copper")
    snapshot.setdefault("line-1", {}).update(available=True, feed_tph=4000, load_pct=120.1)
    snapshot.setdefault("line-2", {}).update(available=False, feed_tph=0, load_pct=0)
    snapshot.setdefault("bess", {}).update(available=False)
    snapshot.setdefault("wind", {}).update(power_mw=0, cf_pct=0)
    snapshot.setdefault("substation", {}).update(grid_cap_mw=180, grid_nominal_mw=260, grid_mw=176)
    snapshot.setdefault("energy", {}).update(grid_mw=176)
    snapshot.setdefault("pit", {}).update(ore_tph=7370, ore_plan_tph=7370, hard_frac=.8)
    writes = []

    async def route_request(route):
        request = route.request
        if request.method == "PUT":
            require(request.url.split("?")[0].endswith("/kz.tynys:scenario/features"),
                    "Scenario cancellation used an unexpected write endpoint")
            body = request.post_data_json
            writes.append(body)
            for key, value in body.items():
                snapshot["scenario"][key] = value["properties"]["value"]
            await route.fulfill(status=204, body="")
        elif request.method == "GET":
            things = [{"thingId": "kz.tynys:" + name,
                       "features": {key: {"properties": {"value": value}}
                                    for key, value in values.items()}}
                      for name, values in snapshot.items()]
            await route.fulfill(status=200, content_type="application/json",
                                body=json.dumps(things, ensure_ascii=False))
        else:
            await route.abort()

    page = await context.new_page()
    page.on("pageerror", lambda error: errors.append("scenario fixture: " + str(error)))
    await page.route("**/ditto/api/2/**", route_request)
    try:
        await ready(page, url)
        await page.wait_for_function(
            "() => document.querySelectorAll('#scenario-banner .scenario-row').length === 6")
        kinds = await page.locator(".scenario-row").evaluate_all(
            "els => els.map(el => el.dataset.kind)")
        require(set(kinds) == {"lull", "line_trip", "kegoc", "bess_fault", "hard_ore", "plan_up"},
                "Scenario banner omitted an active event")
        line1_meter = await page.locator(
            '.lbl[data-object="line-1"] .mini-bar[role=meter]').evaluate("""el => ({
              value: el.hasAttribute('aria-valuenow') ? Number(el.getAttribute('aria-valuenow')) : null,
              min: Number(el.getAttribute('aria-valuemin')),
              max: Number(el.getAttribute('aria-valuemax')),
              text: el.getAttribute('aria-valuetext')
            })""")
        require(all(finite(line1_meter[key]) for key in ("value", "min", "max"))
                and line1_meter["min"] <= line1_meter["value"] <= line1_meter["max"],
                "Above-nominal line load breaks the declared accessible meter bounds")
        require("120.1" in (line1_meter["text"] or "").replace(",", "."),
                "Accessible value text discarded the actual 120.1% line load")
        unavailable_meters = {}
        for object_id in ("line-2", "bess"):
            await page.evaluate("id => window.__tynys.selectObject(id)", object_id)
            label = page.locator('.lbl[data-object="' + object_id + '"]')
            await label.wait_for(state="visible")
            meter = await label.locator(".mini-bar[role=meter]").evaluate("""el => ({
              status: el.dataset.status,
              warning: el.dataset.warning,
              caution: el.dataset.caution,
              color: getComputedStyle(el.querySelector('i')).backgroundColor,
              rgb: getComputedStyle(el.querySelector('i')).backgroundColor.match(/[\\d.]+/g).slice(0,3).map(Number)
            })""")
            require(meter["status"] == "unavailable" and meter["warning"] == "true"
                    and meter["caution"] == "false",
                    object_id + " does not explicitly mark its unavailable state")
            require(meter["rgb"] == [255, 138, 107],
                    object_id + " unavailable meter does not render the red warning color")
            unavailable_meters[object_id] = meter
        await page.evaluate("window.__tynys.clearSelection()")
        before = await page.evaluate(
            "() => ({...window.__tynys.scenarioVisuals, renderedFrames:window.__tynys.renderedFrames})")
        require(before.get("windLull") is True, "Wind lull visual is not active")
        angles = before.get("windAngles")
        require(isinstance(angles, list) and len(angles) > 0 and all(finite(a) for a in angles),
                "Scene exposes no rotor angles for an actual stopped-wind check")
        # ждём хотя бы один новый кадр (на медленном программном рендере кадр бывает дольше 0,6 с)
        await page.wait_for_function("n => window.__tynys.renderedFrames > n",
                                     arg=before["renderedFrames"], timeout=15000)
        await page.wait_for_timeout(600)
        visuals = await page.evaluate(
            "() => ({...window.__tynys.scenarioVisuals, renderedFrames:window.__tynys.renderedFrames})")
        require(visuals["renderedFrames"] > before["renderedFrames"],
                "Scenario scene did not render during the rotor check")
        require(all(abs(a - b) < 1e-7 for a, b in zip(angles, visuals["windAngles"])),
                "Wind rotors kept turning during the zero-power lull")
        require(visuals.get("line2Speed") == 0, "Failed line 2 is still animated")
        require(visuals.get("bessColor") == 0xff3d31, "Failed BESS is not red")
        require(visuals.get("hardOreHighlighted") is True, "Hard-ore highlight is absent")
        require(await page.locator('.lbl[data-object="pile-hard"].event-on').count() == 1,
                "Hard-ore label does not indicate its active scenario")
        grid_label = await page.locator("#l-grid").inner_text()
        require("180 / 260" in grid_label and "предел" in grid_label.lower() and "176" in grid_label,
                "Grid label must distinguish the constrained cap, nominal cap and actual import")
        require(visuals.get("gridLimited") is True and visuals.get("capMw") == 180,
                "The active grid scenario is not reflected in the scene")
        # Observe actual rendered material changes; neither a hidden fixture flag
        # nor a single sample in the pulse's dark phase proves the wire blinks.
        wire_samples = []
        for color in (0xffa23d, 0x3a3f44):
            previous_frame = wire_samples[-1]["rendered_frame"] if wire_samples else -1
            handle = await page.wait_for_function("""({color, after}) => {
              const a = window.__tynys, visual = a.scenarioVisuals;
              return visual.gridLimited && visual.gridWireColor === color && a.renderedFrames > after
                ? {color:visual.gridWireColor, rendered_frame:a.renderedFrames} : false;
            }""", arg={"color": color, "after": previous_frame}, polling="raf", timeout=15000)
            wire_samples.append(await handle.json_value())
        pit_label = await page.locator("#l-pit").inner_text()
        digits = "".join(character for character in pit_label if character.isdigit())
        require("7370" in digits and "80" in digits,
                "Pit label does not display the supplied higher production and hard-ore share")
        await page.screenshot(path=str(screenshot_path))
        await page.locator('.scenario-cancel[data-id="qa-line"]').click()
        await page.wait_for_function(
            "() => document.querySelectorAll('#scenario-banner .scenario-row').length === 5")
        require(len(writes) == 1, "Cancel must issue one scoped scenario write")
        written = writes[0]
        remaining = json.loads(written["events"]["properties"]["value"])
        require({event["id"] for event in remaining} == {"qa-lull", "qa-grid", "qa-bess", "qa-hard", "qa-plan"},
                "Cancel removed unrelated scenario events")
        require(written["rev"]["properties"]["value"] == 101, "Cancel did not increment revision")
        require(written["goal"]["properties"]["value"] == "copper", "Cancel changed controller goal")
        return {
            "transport": "browser-route fixture from repository trace; no live scenario mutation",
            "banner_kinds": kinds, "cancel_preserves_other_events": True,
            "cancel_increments_revision": True, "cancel_preserves_goal": True,
            "visuals": visuals, "grid_label": grid_label, "pit_label": pit_label,
            "grid_wire_rendered_samples": wire_samples,
            "above_nominal_line_meter": line1_meter,
            "unavailable_meters": unavailable_meters,
            "screenshot": str(screenshot_path),
        }
    except Exception:
        await page.screenshot(path=str(screenshot_path.with_name(
            screenshot_path.stem + "-failure" + screenshot_path.suffix)))
        raise
    finally:
        await page.close()


def git_revision():
    """The CI checkout SHA, or the local checkout HEAD when available."""
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        repo = Path(__file__).resolve().parents[3]
        return subprocess.check_output(
            ["git", "-c", "safe.directory=" + repo.as_posix(), "rev-parse", "HEAD"], cwd=repo,
            text=True, stderr=subprocess.DEVNULL, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def verify_source(actual, expected):
    if expected:
        require(actual == expected, f"Expected {expected} data, but the scene uses {actual}")


async def main(url, out, threshold, seconds, warmup, mode="all", expect_source=None):
    target = Path(out)
    artifact_dir = os.environ.get("TYNYS_3D_ARTIFACT_DIR")
    if artifact_dir:
        target = Path(artifact_dir) / target.name
    target.parent.mkdir(parents=True, exist_ok=True)
    night_path = target.with_name(target.stem + "-night" + target.suffix)
    scenario_path = target.with_name(target.stem + "-scenarios" + target.suffix)
    report_path = target.with_suffix(".json")
    functional = mode != "performance"
    performance_gated = mode != "functional"
    artifacts = {"day": str(target)}
    if functional:
        artifacts.update(night=str(night_path), scenarios=str(scenario_path))
    report = {"status": "FAIL", "mode": mode, "url": url, "viewport": VIEWPORT,
              "git_sha": git_revision(), "expected_source": expect_source,
              "functional_status": "PENDING" if functional else "NOT_RUN",
              "host": {"platform": platform.platform(), "logical_cpus": os.cpu_count()},
              "minimum_median_fps": threshold, "errors": [], "launch_args": GL_ARGS,
              "artifacts": artifacts}
    try:
        report["playwright_version"] = version("playwright")
    except PackageNotFoundError:
        report["playwright_version"] = None
    failure = None
    async with async_playwright() as playwright:
        launch = {"headless": True, "args": GL_ARGS}
        if os.environ.get("CHROME_PATH"):
            launch["executable_path"] = os.environ["CHROME_PATH"]
        browser = await playwright.chromium.launch(**launch)
        report["browser_version"] = browser.version
        try:
            context = await browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
            page = await context.new_page()
            page.on("pageerror", lambda error: report["errors"].append(str(error)))
            run_url = low_url(url)
            await ready(page, run_url)
            first = await page.evaluate(READ_METRICS)
            require("swiftshader" in first["glRenderer"].lower(),
                    "Software WebGL was not confirmed by UNMASKED_RENDERER_WEBGL: " + first["glRenderer"])
            require(first["low"] and first["softGL"], "SwiftShader did not select LOW mode")
            require(.85 <= first["pixelRatio"] <= 1, "LOW pixel ratio must remain between 0.85 and 1.0")
            require(6 <= first["lightingHour"] <= 18, "Scene did not start in daylight")
            report["source"] = await page.locator("#src").inner_text()
            report["source_mode"] = await page.evaluate("window.__tynys.source")
            verify_source(report["source_mode"], expect_source)
            if report["source_mode"] == "replay":
                trace_response = await context.request.get(urljoin(run_url, "trace.json"))
                require(trace_response.ok, "Cannot fingerprint the replay trace")
                report["replay"] = {
                    "kind": "repository trace replay; no live backend",
                    "sha256": hashlib.sha256(await trace_response.body()).hexdigest(),
                    "snapshot_count": len(await trace_response.json()),
                }
            clock_before = await page.locator("#clock").inner_text()
            await set_hour(page, 12)
            # Benchmark the untouched initial camera. Interaction failures later
            # still leave actual CPU/rendering evidence in the failure report.
            report["performance"] = await rendered_fps(page, seconds, warmup)
            report["performance"].update(
                gated=performance_gated, threshold_median_fps=threshold,
                meets_threshold=report["performance"]["median_fps"] >= threshold)
            verify_source(await page.evaluate("window.__tynys.source"), expect_source)
            report["clock"] = {"before": clock_before, "after": await page.locator("#clock").inner_text()}
            require(report["clock"]["before"] != report["clock"]["after"], "Model/replay clock did not advance")
            if functional:
                report["controls"] = await check_controls(page)
                await page.locator("#reset").click()
                await set_hour(page, 12)
                day = await page.screenshot(path=str(target))
                await set_hour(page, 22)
                night_visuals = await page.evaluate("window.__tynys.scenarioVisuals")
                require(night_visuals.get("headlights", 0) > 0, "Truck headlights did not appear at night")
                report["night_visuals"] = night_visuals
                night = await page.screenshot(path=str(night_path))
                require(day != night, "Day and night screenshots are identical")
                await page.locator("#light-auto").click()
                require(await page.evaluate("window.__tynys.lightingOverride === null"),
                        "Automatic lighting did not restore model time")
                verify_source(await page.evaluate("window.__tynys.source"), expect_source)
                # Close the first scene before the isolated scenario fixture.
                await page.close()
                report["scenarios"] = await scenario_fixture(context, run_url, report["errors"], scenario_path)
            else:
                await page.screenshot(path=str(target))
                await page.close()
            require(not report["errors"], "JavaScript errors: " + "; ".join(report["errors"]))
            if functional:
                report["functional_status"] = "PASS"
            if performance_gated:
                require(report["performance"]["meets_threshold"],
                        "Median software-rendered FPS is below the configured threshold; see CPU and renderer in report")
            report["status"] = "PASS"
        except Exception as error:
            failure = error
            if report["functional_status"] == "PENDING":
                report["functional_status"] = "FAIL"
            report["failure"] = f"{type(error).__name__}: {error}"
            if "page" in locals() and not page.is_closed():
                await page.screenshot(path=str(target.with_name(target.stem + "-failure.png")))
        finally:
            await browser.close()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    performance = report.get("performance", {})
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write(
                f"\n### 3D: {mode}, source {report.get('source_mode', 'unknown')}\n\n"
                f"- Result: **{report['status']}**; functional checks: **{report['functional_status']}**.\n"
                f"- Actual rendered FPS: median **{performance.get('median_fps', 'not measured')}**, "
                f"p10 **{performance.get('p10_fps', 'not measured')}**, "
                f"average **{performance.get('average_fps', 'not measured')}**.\n"
                f"- Required median: **{threshold}**; meets threshold: "
                f"**{performance.get('meets_threshold', 'not measured')}**; "
                f"FPS gates this job: **{performance_gated}**.\n"
                f"- Commit: `{report['git_sha']}`; report: `{report_path}`.\n")
            if report.get("replay"):
                summary.write(f"- Trace SHA256: `{report['replay']['sha256']}` (recorded data, no live backend).\n")
            if report.get("failure"):
                summary.write(f"- Failure: {report['failure']}\n")
    print(json.dumps({
        "status": report["status"], "mode": mode, "functional_status": report["functional_status"],
        "performance_gated": performance_gated, "meets_threshold": performance.get("meets_threshold"),
        "renderer": performance.get("environment", {}).get("glRenderer"),
        "median_fps": performance.get("median_fps"), "p10_fps": performance.get("p10_fps"),
        "min_fps": performance.get("min_fps"), "draw_calls": performance.get("draw_calls"),
        "triangles": performance.get("triangles"), "source": report.get("source"),
        "report": str(report_path), "failure": report.get("failure"),
    }, ensure_ascii=False))
    print(f"3D {mode.upper()} {'FAIL' if failure else 'OK'}")
    return 0 if not failure else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("out", help="Day screenshot; also writes NAME-night.png and NAME.json")
    parser.add_argument("--mode", choices=("all", "functional", "performance"), default="all")
    parser.add_argument("--expect-source", choices=("live", "replay"))
    arguments = parser.parse_args()
    min_fps = float(os.environ.get("TYNYS_MIN_FPS", "10"))
    sample_seconds = float(os.environ.get("TYNYS_FPS_SECONDS", "10"))
    warmup_seconds = float(os.environ.get("TYNYS_FPS_WARMUP_SECONDS", "3"))
    if not all(math.isfinite(value) for value in (min_fps, sample_seconds, warmup_seconds)) or min_fps <= 0 or sample_seconds < 5 or warmup_seconds < 0:
        parser.error("FPS settings must be finite; threshold > 0, warmup >= 0 and duration >= 5 seconds")
    sys.exit(asyncio.run(main(arguments.url, arguments.out, min_fps, sample_seconds, warmup_seconds,
                             arguments.mode, arguments.expect_source)))
