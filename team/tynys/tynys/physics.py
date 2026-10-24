"""Физические зависимости модели «Тыныс». Все формулы открыты и проверяемы."""
import math
import numpy as np
from .params import Params, DOMAINS, P80_MODES

G = 9.81


def ensure_process_state(p, st):
    """Explicit legacy-snapshot migration; new snapshots retain exact history."""
    if not st.pile_cu:
        st.pile_cu = {d: st.pile[d]*p.cu_grade[d] for d in DOMAINS}
    if not st.pile_bwi_mass:
        st.pile_bwi_mass = {d: st.pile[d]*st.bwi_est[d] for d in DOMAINS}
    if not st.pile_recovery_cu:
        st.pile_recovery_cu = {d: st.pile_cu[d]*p.r150[d] for d in DOMAINS}
    if not st.line_x:
        x = np.zeros((p.n_lines, len(DOMAINS), len(P80_MODES)))
        total = sum(st.pile.values())
        for l in range(p.n_lines):
            if st.line_on[l]:
                for di, d in enumerate(DOMAINS):
                    x[l, di, P80_MODES.index(150)] = p.line_q_nom*(st.pile[d]/total if total else .5)
        st.line_x = x.tolist()
    if not st.line_mw:
        e = np.array([[mill_variable_mwh_t(p, st.bwi_est[d], g) for g in P80_MODES] for d in DOMAINS])
        x = np.asarray(st.line_x)
        st.line_mw = ((x*e).sum(axis=(1,2)) + mill_idle_mw(p)*(x.sum(axis=(1,2)) > 0)).tolist()


def bond_kwh_t(p: Params, bwi: float, p80_um: float) -> float:
    """Удельная энергия измельчения по закону Бонда с поправкой на SAG.

    E = EF · 10 · Wi · (1/√P80 − 1/√F80), кВт·ч/т   (F. C. Bond, 1952)
    """
    return p.sag_ef * 10.0 * bwi * (1.0 / math.sqrt(p80_um) - 1.0 / math.sqrt(p.F80_um))


def mill_idle_mw(p: Params) -> float:
    """Fixed draw while rotating, calibrated at nominal 50/50 ore, P80=150.

    The 35% share is a sensitivity assumption, not a universal no-load law.
    Splitting the old nominal draw avoids counting Bond energy twice.
    """
    reference = sum(bond_kwh_t(p, bwi, 150) for bwi in p.bwi.values()) / len(p.bwi)
    return p.mill_idle_fraction * p.line_q_nom * reference / 1000


def mill_variable_mwh_t(p: Params, bwi: float, p80_um: float) -> float:
    return (1 - p.mill_idle_fraction) * bond_kwh_t(p, bwi, p80_um) / 1000


def mill_power_mw(p: Params, q: float, bwi: float, p80_um: float, running=True) -> float:
    return mill_idle_mw(p) + q * mill_variable_mwh_t(p, bwi, p80_um) if running else 0.0


def recovery_inf(p: Params, domain: str, p80_um: float, reference=None) -> float:
    """Предельное извлечение как функция крупности помола (линейная аппроксимация
    потери раскрытия минералов; наклон — параметр чувствительности)."""
    return max(0., min(.98, (p.r150[domain] if reference is None else reference) - p.recovery_slope_per_100um * (p80_um - 150.0) / 100.0))


def kinetic_factor(p: Params, q_line_tph: float) -> float:
    """Флотация 1-го порядка: R = R∞·(1 − e^(−kτ)); τ обратно пропорционально нагрузке.
    Возвращает поправку относительно номинальной нагрузки линии."""
    if q_line_tph <= 0:
        return 0.0
    tau = p.tau_nom_min * p.line_q_nom / q_line_tph
    nom = 1.0 - math.exp(-p.k_flot_per_min * p.tau_nom_min)
    return (1.0 - math.exp(-p.k_flot_per_min * tau)) / nom


def haul_kwh_per_t(p: Params, lift_m: float, haul_km: float) -> float:
    """Энергия рейса аккумуляторного самосвала на тонну груза.

    Гружёный подъём:  (m_груз+m_тары)·g·(h + Crr·L) / η_привода
    Порожний спуск:   m_тары·g·(Crr·L − h); если < 0 — рекуперация с η_рекуп
    """
    L = haul_km * 1000.0
    m_loaded = (p.truck_payload_t + p.truck_tare_t) * 1000.0
    m_empty = p.truck_tare_t * 1000.0
    e_up = m_loaded * G * (lift_m + p.crr * L) / p.eta_drive
    w_down = m_empty * G * (p.crr * L - lift_m)
    e_down = w_down / p.eta_drive if w_down > 0 else w_down * p.eta_regen
    joules = (e_up + e_down) * p.haul_aux_factor
    return joules / 3.6e6 / p.truck_payload_t


def haul_mwh_per_t_ore(p: Params) -> float:
    """Энергия перевозки на тонну РУДЫ с учётом вскрыши (коэффициент вскрыши)."""
    ore = haul_kwh_per_t(p, p.ore_lift_m, p.ore_haul_km)
    waste = haul_kwh_per_t(p, p.waste_lift_m, p.waste_haul_km)
    return (ore + p.strip_ratio * waste) / 1000.0


def trucks_needed(p: Params, ore_tph: float) -> float:
    return ore_tph * (1.0 + p.strip_ratio) / p.truck_tph
