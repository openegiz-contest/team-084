# Данные и их лицензии

| Файл / величины | Источник | Лицензия | Как попадает в решение |
|---|---|---|---|
| `team/tynys/data/openmeteo_aktogay_2024.csv` — почасовые скорость ветра на 100 м, суммарная радиация, температура, 46,95° с. ш. 79,86° в. д., 2024 г. | Open‑Meteo Historical Weather API (реанализ ERA5 / ERA5‑Land, Copernicus) — https://open-meteo.com | CC BY 4.0 (атрибуция: «Weather data by Open‑Meteo.com», содержит модифицированные данные Copernicus Climate Change Service) | В репозитории; скачан workflow `.github/workflows/fetch-data.yml` |
| Переработка 58,3 Мт, содержание 0,43 %, извлечение 87,9 %, медь 221 кт, электроэнергия 7,32 ПДж (2024) | KAZ Minerals, Annual Report and Accounts 2024 (публичный отчёт) | отдельные числовые факты из открытой публикации, со ссылкой | Числа в `team/tynys/tynys/params.py` с пометкой SRC |
| Углеродоёмкость сети Казахстана 0,79 т CO₂/МВт·ч | расчёт по Agora Energiewende (2025): 92,6 Мт CO₂ / 117,9 ТВт·ч, 2023 | числовой факт со ссылкой | `params.py` |
| Тариф 49,03 ₸/кВт·ч | РЭК «Рудный», тариф для юрлиц с 01.10.2026 | публичный тариф | `params.py` |
| Батарея 2,6 МВт·ч и зарядка 6 МВт электросамосвала | публикации о Fortescue / Liebherr T264 (2026) | числовой факт со ссылкой | `params.py` |
| `team/tynys/data/sizing.csv` | расчёт команды: `team/tynys/sizing.py` на данных выше | MIT (как всё решение) | В репозитории |
| `team/tynys/data/geomet/*.csv`, `source.json` | Hoffimann et al., GeoMet v4, DOI 10.5281/zenodo.7051975 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | CSV без изменений; [атрибуция, контрольные суммы и все преобразования](team/tynys/data/geomet/README.md). Пространственный аналог, не данные Актогая |
| `sizing-physics-v4.csv`, `flex-physics-v4.csv`, `wind-equivalent-*.json` | Модель команды с GeoMet и ERA5 | Код расчёта MIT; GeoMet CC BY 4.0 сохраняет атрибуцию | Версия и параметры рядом в JSON; [границы выводов](team/tynys/MODULES_V4.md) |

Конфиденциальных данных организаций и персональных данных в решении нет.
