#!/usr/bin/env bash
# Проверка «из конца в конец»: двойники созданы, поле публикует через MQTT→Ditto,
# координатор отвечает, экран отдаёт данные через свой прокси к Ditto.
set -euo pipefail
cd "$(dirname "$0")/../../.."
set -a; . deploy/compose/.env; set +a
D="http://127.0.0.1:${DITTO_PORT:-8080}/api/2/things"
U="http://127.0.0.1:${TYNYS_UI_PORT:-8095}"
auth=(-u "ditto:${DITTO_PASSWORD}")
val() { curl -fsS "${auth[@]}" "$D/kz.tynys:$1/features/$2/properties/value" 2>/dev/null || echo null; }
for i in $(seq 1 90); do
  h=$(val site sim_hour); c=$(val coordinator for_t)
  if [[ "$h" =~ ^[0-9]+$ && "$c" =~ ^[0-9]+$ && "$h" -ge 3 ]]; then break; fi
  sleep 2
done
[[ "$h" =~ ^[0-9]+$ && "$h" -ge 3 ]] || { echo "SMOKE FAIL: рудник не публикует (sim_hour=$h)"; exit 1; }
[[ "$c" =~ ^[0-9]+$ ]] || { echo "SMOKE FAIL: координатор молчит"; exit 1; }
src=$(val plant decision_source)
[[ "$(curl -fsS "$U/")" == *"Тыныс"* ]] || { echo "SMOKE FAIL: экран :8095 не отвечает"; exit 1; }
[[ "$(curl -fsS "$U/dashboard.html")" == *'id="map"'* ]] || { echo "SMOKE FAIL: пульт рудника /dashboard.html"; exit 1; }
[[ "$(curl -fsS "$U/3d.html")" == *"scene3d.js"* ]] || { echo "SMOKE FAIL: 3D-сцена"; exit 1; }
curl -fsS "$U/vendor/three.module.js" -o /dev/null || { echo "SMOKE FAIL: three.js"; exit 1; }
[[ "$(curl -fsS "$U/ditto/api/2/things/kz.tynys:site")" == *sim_hour* ]] || { echo "SMOKE FAIL: прокси экрана к Ditto"; exit 1; }
python3 team/tynys/scripts/check_stand.py "$U"
echo "SMOKE OK: модельный час $h, координатор решил час $c, источник решений $src"
