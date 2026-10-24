"""Собирает demo.html — автономную 3D‑сцену (без стенда) на записи trace.json.
three.js берётся с jsDelivr. Запуск: python build_demo.py"""
import os
import re
here = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(here, "3d.html"), encoding="utf-8").read()
js = open(os.path.join(here, "scene3d.js"), encoding="utf-8").read()
details = open(os.path.join(here, "scene-details.js"), encoding="utf-8").read()
trace = open(os.path.join(here, "trace.json"), encoding="utf-8").read()
CDN = "https://cdn.jsdelivr.net/npm/three@0.160.0"
# Keep the custom module in the single-file demo. The closure preserves its
# private names; only the two public entry points are used by scene3d.js.
details = details.replace("import * as THREE from 'three';", "")
details = details.replace("import { mergeGeometries } from './vendor/BufferGeometryUtils.js';", "")
details = details.replace("export function ", "function ")
js = js.replace("import { installSceneDetails, mergeStaticMeshes } from './scene-details.js';",
                f"import {{ mergeGeometries }} from '{CDN}/examples/jsm/utils/BufferGeometryUtils.js';\n"
                + "const { installSceneDetails, mergeStaticMeshes } = (() => {\n"
                + details + "\nreturn { installSceneDetails, mergeStaticMeshes };\n})();")
js = js.replace("'./vendor/OrbitControls.js'", f"'{CDN}/examples/jsm/controls/OrbitControls.js'")
js = js.replace("'./vendor/CSS2DRenderer.js'", f"'{CDN}/examples/jsm/renderers/CSS2DRenderer.js'")
html = html.replace('{"imports":{"three":"./vendor/three.module.js"}}', '{"imports":{"three":"%s/build/three.module.js"}}' % CDN)
# A single-file replay has no sibling Unity, dashboard or experiment pages.
html = re.sub(r'<a class="btn" href="(?:\./|\./dashboard\.html|futures\.html)"(?: id="[^"]+")?>[^<]+</a>', '', html)
html = html.replace('<a style="color:#5fe3a1" href="./dashboard.html">2D‑схему рудника</a>', '2D‑схему на стенде')
html = html.replace('<script src="demo.js"></script>', '')  # live-only guided demo
tag = re.search(r'<script type="module" src="scene3d\.js(?:\?[^"]*)?"></script>', html)
if not tag:
    raise SystemExit("3d.html: scene3d.js script tag not found")
html = html[:tag.start()] + '<script>window.TYNYS_TRACE=' + trace + ';</script>\n<script type="module">\n' + js + '\n</script>' + html[tag.end():]
open(os.path.join(here, "demo.html"), "w", encoding="utf-8").write(html)
print("demo.html", len(html) // 1024, "KB")
