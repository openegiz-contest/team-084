# Доказательства проверки (GitHub Actions)

Копия результата workflow `.github/workflows/tynys-e2e.yml` на `main`
(коммит и номер запуска — в последней строке `ci.log`). CI после каждого
запуска на `main` кладёт те же файлы в ветку `ci-screens`.

- `ci.log` — окружение (Ubuntu 24.04, 2 CPU, 7 ГБ), запуск с нуля по README до
  `SMOKE OK` с временем, последствия сценариев для меди и CO₂, включение и отмена
  what-if через двойник `scenario`, функциональная проверка 3D без GPU.
- `screen3d.png` — лёгкая 3D на живых двойниках стенда (SwiftShader).
- `screen2d.png` — пульт `/dashboard.html` на живых двойниках.
