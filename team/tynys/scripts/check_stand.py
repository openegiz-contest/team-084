"""Read-only release check: served UI, live CO2 and reference data must match.

Run after deployment: python team/tynys/scripts/check_stand.py [http://localhost:8095]
Uses the UI's Ditto proxy; no credentials or third-party packages are needed.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def validate_metrics(things, sizing):
    by_id = {t['thingId'].split(':')[-1]: t for t in things}
    for name in ('site', 'shadow-v0', 'shadow-v1'):
        features = by_id[name]['features']
        for key in ('co2_t', 'co2_adj_t', 'co2_per_t_cu'):
            value = features.get(key, {}).get('properties', {}).get('value')
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{name}.{key}: missing/invalid; rebuild and restart tynys-field')
    if not sizing:
        raise ValueError('Sizing data missing; refresh reference data')
    for row in sizing:
        for key in ('co2_kt', 'co2_adj_kt', 'cu_adj_t'):
            value = row.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'Sizing {key}: missing/invalid; refresh reference data')


def check(base):
    def get(path):
        with urllib.request.urlopen(base.rstrip('/') + '/' + path, timeout=30) as response:
            return response.read()
    # Check actual runtime assets, including the prebuilt Unity player.
    paths = ['index.html', 'dashboard.html', 'app.js', '3d.html', 'scene3d.js',
             'scene-details.js', 'futures.html', 'futures.js', 'futures.css',
             'future-scene.js', 'unity-shell.js', 'unity-shell.css', 'unity/index.html']
    paths += [p.relative_to(ROOT / 'ui').as_posix() for p in (ROOT / 'ui/unity/Build').iterdir() if p.is_file()]
    for path in paths:
        actual = hashlib.sha256(get(path)).digest()
        expected = hashlib.sha256((ROOT / 'ui' / path).read_bytes()).digest()
        if actual != expected:
            raise ValueError(f'UI differs from checkout: {path}')
    prefix = 'ditto/api/2/things'
    things = json.loads(get(prefix + '?ids=kz.tynys:site,kz.tynys:shadow-v0,kz.tynys:shadow-v1'))
    sizing = json.loads(get(prefix + '/kz.tynys:energy/attributes/sizing'))
    validate_metrics(things, sizing)
    with (ROOT / 'data/sizing.csv').open(encoding='utf-8') as source:
        expected = [{k: v if k == 'variant' else float(v) for k, v in row.items()} for row in csv.DictReader(source)]
    if sizing != expected:
        raise ValueError('Sizing differs from checkout; refresh reference data')
    print(f'STAND OK: {len(paths)} UI assets match; live CO2 for V0/V1/V2; {len(sizing)} sizing rows match')


if __name__ == '__main__':
    try:
        check(sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8095')
    except Exception as error:
        sys.exit(f'STAND FAIL: {error}')
