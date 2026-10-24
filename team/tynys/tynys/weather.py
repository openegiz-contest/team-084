"""Погода и прогнозы для рудника Актогай.

Основной источник (так работают стенд, sizing.py и flex_stats.py): реальный
почасовой ряд 2024 г. в точке рудника — data/openmeteo_aktogay_2024.csv
(Open-Meteo, реанализ ERA5, CC BY 4.0): скорость ветра на 100 м и суммарная
радиация; мощность ВЭС — по типовой кривой ВЭУ, СЭС — по радиации (load_real).

Запасной вариант — синтетика: используется, если файла нет (или вызвать
generate(..., real=False) / задать TYNYS_WEATHER_CSV на другой путь); с ней
seed меняет и погоду, а с реальным рядом — только ошибку прогноза. Солнце: геометрия
Солнца + модель ясного неба Хаурвица + марковская облачность; ветер: Вейбулл
с AR(1)-корреляцией. Прогноз (forecast) в обоих случаях — фактический ряд плюс
модельная ошибка, растущая с горизонтом; это не архив настоящих прогнозов.
"""
import math
import os
import numpy as np
from scipy.stats import norm
from .params import Params


def _solar_elev_sin(lat, lon, doy, hour_utc):
    decl = math.radians(23.44) * math.sin(2 * math.pi * (284 + doy) / 365.0)
    solar_time = hour_utc + lon / 15.0
    ha = math.radians(15.0 * (solar_time - 12.0))
    la = math.radians(lat)
    return math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)


def _season(doy):
    """1 = середина зимы, 0 = середина лета."""
    return 0.5 * (1 + math.cos(2 * math.pi * (doy - 15) / 365.0))


def wind_power_pu(v):
    """Типовая кривая мощности: пуск 3 м/с, номинал 12 м/с, отсечка 25 м/с; потери 10 %."""
    v = np.asarray(v, dtype=float)
    pu = np.where(v < 3, 0.0, np.where(v < 12, ((v - 3) / 9.0) ** 3, np.where(v < 25, 1.0, 0.0)))
    return pu * 0.90


REAL_CSV = os.environ.get("TYNYS_WEATHER_CSV", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "openmeteo_aktogay_2024.csv"))


def load_real(p: Params, start_doy: int, days: int, path: str = REAL_CSV):
    """Реальная почасовая погода в точке Актогая за 2024 г. (Open-Meteo ERA5, CC BY 4.0):
    скорость ветра на 100 м и суммарная радиация на горизонтальную площадку.
    Индекс t — местное время (UTC+5), год зацикливается."""
    import pandas as pd
    d = pd.read_csv(path, skiprows=3)
    v_all = d.iloc[:, 1].to_numpy(float)
    ghi_all = d.iloc[:, 2].to_numpy(float)
    N = len(v_all)
    idx = (np.arange(days * 24) + (start_doy - 1) * 24 - 5) % N
    v, ghi = v_all[idx], ghi_all[idx]
    kt = np.zeros_like(ghi)
    pv_pu = np.zeros_like(ghi)
    for t in range(len(ghi)):
        doy = (start_doy + t // 24 - 1) % 366 + 1
        sh = _solar_elev_sin(p.lat, p.lon, doy, t % 24 + 0.5 - 5)
        if sh <= 0.01 or ghi[t] <= 0:
            continue
        ghi_clear = 1098.0 * sh * math.exp(-0.057 / sh)
        kt[t] = float(np.clip(ghi[t] / ghi_clear, 0.05, 1.0))
        tilt_gain = 1.0 + 0.35 * (1 - sh)
        pv_pu[t] = min(1.0, ghi[t] / 1000.0 * tilt_gain * 0.93)
    return {"wind_v": v, "wind_pu": wind_power_pu(v), "pv_pu": pv_pu, "kt": kt, "source": "Open-Meteo ERA5 2024"}


def generate(p: Params, start_doy: int, days: int, seed: int, real: bool = None):
    """Погода для сценария. real=None: реальный ряд, если файл есть (так работает стенд),
    иначе синтетика. Эксперименты с разными seed используют синтетику (real=False)."""
    if real is None:
        real = os.path.exists(REAL_CSV)
    if real:
        return load_real(p, start_doy, days)
    rng = np.random.default_rng(seed)
    n = days * 24
    # ---- ветер ----
    phi = 0.97
    z = np.empty(n)
    z[0] = rng.standard_normal()
    for t in range(1, n):
        z[t] = phi * z[t - 1] + math.sqrt(1 - phi ** 2) * rng.standard_normal()
    u = norm.cdf(z)
    k = 2.2
    v = np.empty(n)
    for t in range(n):
        doy = start_doy + t // 24
        hour = t % 24
        c = 8.3 + 2.0 * _season(doy)                      # масштаб Вейбулла, м/с (зимой выше)
        c *= 1.0 + 0.06 * math.sin(2 * math.pi * (hour - 9) / 24)  # слабый суточный ход
        v[t] = c * (-math.log(1 - min(u[t], 0.999999))) ** (1 / k)
    wind_pu = wind_power_pu(v)

    # ---- солнце ----
    # дневная облачность: марковская цепь {ясно, переменно, пасмурно}
    states_kt = np.array([0.95, 0.60, 0.25])
    kt_day = np.empty(days)
    s = 0
    for d in range(days):
        w = _season(start_doy + d)
        p_clear = 0.55 - 0.20 * w
        p_over = 0.15 + 0.20 * w
        stay = 0.5
        if rng.random() > stay:
            r = rng.random()
            s = 0 if r < p_clear else (2 if r > 1 - p_over else 1)
        kt_day[d] = states_kt[s]
    pv_pu = np.zeros(n)
    kt = np.zeros(n)
    tz = 5  # UTC+5
    for t in range(n):
        doy = start_doy + t // 24
        hour_local = t % 24 + 0.5
        sh = _solar_elev_sin(p.lat, p.lon, doy, hour_local - tz)
        if sh <= 0.01:
            continue
        ghi_clear = 1098.0 * sh * math.exp(-0.057 / sh)    # модель Хаурвица, Вт/м²
        kt[t] = float(np.clip(kt_day[t // 24] + 0.08 * rng.standard_normal(), 0.1, 1.0))
        tilt_gain = 1.0 + 0.35 * (1 - sh)                  # фикс. наклон помогает при низком Солнце
        pv_pu[t] = min(1.0, ghi_clear * kt[t] / 1000.0 * tilt_gain * 0.93)
    return {"wind_v": v, "wind_pu": wind_pu, "pv_pu": pv_pu, "kt": kt}


def forecast(weather, t0: int, horizon: int, seed: int):
    """Прогноз на horizon часов вперёд, выданный в момент t0.
    Ошибка растёт с горизонтом: σ_v = 0,6 + 0,08·h м/с; σ_kt = 0,05 + 0,01·h.
    Генератор детерминирован по (seed, t0) — эксперименты воспроизводимы."""
    rng = np.random.default_rng(seed * 100_003 + t0)
    n = len(weather["wind_v"])
    idx = np.minimum(np.arange(t0, t0 + horizon), n - 1)
    h = np.arange(horizon)
    # коррелированная по горизонту ошибка (случайное блуждание)
    ev = np.cumsum(rng.standard_normal(horizon)) * 0.25 + rng.standard_normal(horizon) * 0.3
    ev = ev * (0.6 + 0.08 * h) / (0.6 + 0.08 * h).mean()
    v_f = np.clip(weather["wind_v"][idx] + ev * 0.9, 0, None)
    v_f[0] = weather["wind_v"][idx[0]]  # текущий час измерен
    wind_f = wind_power_pu(v_f)
    ek = rng.standard_normal(horizon) * (0.05 + 0.01 * h)
    pv_true = weather["pv_pu"][idx]
    kt_true = weather["kt"][idx]
    scale = np.where(kt_true > 0, np.clip(kt_true + ek, 0.1, 1.0) / np.maximum(kt_true, 1e-6), 0)
    pv_f = np.clip(pv_true * scale, 0, 1)
    pv_f[0] = pv_true[0]
    return wind_f, pv_f


def calibrate(p: Params, seed: int = 0):
    """Годовой КИУМ синтетических ВЭС и СЭС (для раздела «Данные и допущения»)."""
    w = generate(p, 1, 365, seed)
    return float(w["wind_pu"].mean()), float(w["pv_pu"].mean()), float(w["pv_pu"].sum())
