"""Показатели, которые модель действительно может вычислить корректно."""
import numpy as np
import pandas as pd
from .params import Params, DOMAINS


def grid_adjusted(p: Params, grid_mwh, feed_t, d_pile_t, d_fleet_mwh, d_bess_mwh):
    """Энергия из сети с поправкой на запасы в конце прогона (как «медь с учётом склада»).
    Прогоны заканчиваются с разными складами и зарядами батарей: руда, оставшаяся на складе,
    ещё потребует энергии на переработку, а заряд сверх начального уже куплен из сети.
      + Δсклад × (энергия из сети на тонну в этом прогоне)
      − Δзаряд самосвалов / КПД зарядки
      − Δзаряд накопителя / √КПД цикла
    Положительные Δ — запасы в конце больше, чем в начале."""
    e_t = grid_mwh / max(feed_t, 1e-9)
    return grid_mwh + d_pile_t * e_t - d_fleet_mwh / p.eta_charge - d_bess_mwh / np.sqrt(p.bess_eta_rt)


def summarize(p: Params, df: pd.DataFrame, init_pile: float) -> dict:
    """Сводка прогона. Изменение запасов на складах пересчитано в «медь в запасе»,
    чтобы вариант не выглядел лучше просто за счёт того, что съел склад."""
    end = {"soft": df.pile_soft.iloc[-1], "hard": df.pile_hard.iloc[-1]}
    d_inv_cu = sum(df[f"pile_recovery_cu_{d}"].iloc[-1] - init_pile*p.cu_grade[d]*p.r150[d]
                   if p.geomet and f"pile_recovery_cu_{d}" in df else
                   (df[f"pile_cu_{d}"].iloc[-1] - init_pile*p.cu_grade[d]) * p.r150[d]
                   if f"pile_cu_{d}" in df else (end[d]-init_pile)*p.cu_grade[d]*p.r150[d]
                   for d in DOMAINS)
    cu = df.cu_t.sum()
    load = df.load.sum()
    renew_used = (df.renew - df.curtail).sum()
    grid = df.grid.sum()
    cost = (df.grid * df.price).sum()
    feed = df.feed.sum()
    return {
        "cu_t": cu,
        "cu_adj_t": cu + d_inv_cu,
        "d_inventory_t": sum(end.values()) - 2 * init_pile,
        "ore_fed_kt": feed / 1000,
        "ore_mined_kt": df.mine.sum() / 1000,
        "mining_lost_kt": (df.mine_plan - df.mine).sum() / 1000,
        "recovery_pct": 100 * cu / max(df.feed_cu_t.sum(), 1e-9),
        "p80_mean_um": float(np.nanmean(np.where(df.feed > 0, df.p80, np.nan))),
        "grid_mwh": grid,
        "grid_cost_mkzt": cost / 1e6,
        "co2_t": grid * p.grid_co2_t_mwh,
        "co2_adj_t": grid_adjusted(p, grid, feed, sum(end.values()) - 2 * init_pile,
                                   df.fleet_e.iloc[-1] - 0.6 * p.n_trucks * p.truck_batt_mwh,
                                   df.bess_e.iloc[-1] - 0.5 * p.bess_mwh) * p.grid_co2_t_mwh,
        "curtail_mwh": df.curtail.sum(),
        "renew_share_pct": 100 * renew_used / max(load, 1e-9),
        "kwh_per_t_ore": 1000 * load / max(feed, 1e-9),
        "grid_mwh_per_t_cu": grid / max(cu, 1e-9),
        "trips": int(df.trips.sum()),
        "restarts": int(df.restarts.sum()),
        "shed_charge_mwh": df.shed_charge.sum(),
        "flex_down_mw_mean": df.flex_down_mw.mean(),
    }
