"""Параметры рудника «Тыныс».

Каждый параметр помечен источником (SRC) или как допущение (ASSUMPTION).
Изменяйте здесь — все варианты (V0/V1/V2) читают одни и те же значения,
поэтому сравнение всегда идёт при одинаковых исходных условиях.
"""
from dataclasses import dataclass, field
from typing import Dict, Tuple

DOMAINS: Tuple[str, str] = ("soft", "hard")
P80_MODES: Tuple[int, ...] = (120, 150, 200, 250)  # мкм, варианты крупности помола


@dataclass
class Params:
    dt_h: float = 1.0

    # ---------- площадка ----------
    lat: float = 49.8      # Карагандинская обл. (условная площадка)
    lon: float = 73.1

    # ---------- руда (два геометаллургических домена) ----------
    # ASSUMPTION: типичный диапазон BWi порфировой меди 11–17 кВт·ч/т.
    bwi: Dict[str, float] = field(default_factory=lambda: {"soft": 11.5, "hard": 16.0})
    cu_grade: Dict[str, float] = field(default_factory=lambda: {"soft": 0.0040, "hard": 0.0042})
    # Извлечение при P80=150 мкм (ASSUMPTION, типично для сульфидной порфировой меди)
    r150: Dict[str, float] = field(default_factory=lambda: {"soft": 0.89, "hard": 0.88})
    # Потеря извлечения на каждые +100 мкм P80 (ASSUMPTION, проверяется анализом чувствительности)
    recovery_slope_per_100um: float = 0.06
    F80_um: float = 120_000.0   # питание мельниц после первичного дробления (ASSUMPTION)
    sag_ef: float = 1.15        # поправка на неэффективность ПСИ/SAG к закону Бонда (ASSUMPTION)
    # Внутридоменная изменчивость твёрдости, которую контроллер заранее не знает
    bwi_noise_sd: float = 0.04
    bwi_noise_phi: float = 0.98
    grade_noise_sd: float = 0.10   # ASSUMPTION: relative within-domain Cu variability
    grade_noise_phi: float = 0.98
    geomet: bool = False  # GeoMet spatial analogue; enabled for Aktogay scenario

    # ---------- флотация ----------
    k_flot_per_min: float = 0.25   # константа кинетики 1-го порядка (ASSUMPTION)
    tau_nom_min: float = 16.0      # время пребывания при номинальной нагрузке линии
    flot_kwh_t: float = 3.5        # ячейки флотации и доизмельчение, кВт·ч/т (ASSUMPTION)

    # ---------- линии измельчения (2 параллельные SABC) ----------
    n_lines: int = 2
    line_q_nom: float = 850.0
    line_q_min: float = 425.0      # 50 % номинала — нижняя граница устойчивой работы (ASSUMPTION)
    line_q_max: float = 1100.0     # объёмное ограничение
    line_p_max_mw: float = 15.0
    mill_speed_rpm: float = 10.5  # ASSUMPTION: постоянная скорость привода при работе
    # ASSUMPTIONS, not Aktogay commissioning measurements. Nominal reference
    # power is retained; unloading removes only the variable component.
    mill_idle_fraction: float = 0.35
    line_q_ramp_fraction: float = 0.10  # nominal throughput per hour
    line_power_ramp_fraction: float = 0.10  # installed power per hour
    restart_cost_kzt: float = 5.0e6   # износ + потери при повторном пуске (ASSUMPTION)
    trip_lockout_h: int = 1           # после аварийного отключения линия 1 ч недоступна

    # ---------- дробление, база ----------
    crush_kwh_t: float = 0.4
    auxiliary_nominal_mw: float = 3.0  # сумма паспортных нагрузок assets.py, не постоянная нагрузка
    # ASSUMPTION: часовая модель; паспортные мощности/ресурс требуют данных АСУ ТП.
    shovel_capacity_factor: float = 1.2  # суммарная погрузка / план горной массы
    crusher_capacity_factor: float = 1.2
    conveyor_capacity_factor: float = 1.2
    concentrate_grade: float = 0.25     # массовая доля Cu в сухом концентрате
    process_water_m3_t: float = 1.8
    recycle_water_fraction: float = 0.65
    service_interval_h: float = 720.0   # моточасы между ТО
    service_duration_h: int = 4
    equipment_wear_per_h: float = 0.00001
    planned_stops: bool = True  # staggered 4 h weekly line / fortnightly crusher stops
    flexible_maintenance: bool = False
    maintenance_window_h: int = 12  # nominal start +/-12 h; one mill crew
    liner_duration_h: int = 12     # ASSUMPTION: replacement every fourth service

    # ---------- склады ----------
    pile_cap_t: float = 60_000.0   # живая ёмкость КАЖДОГО из двух складов (soft/hard)
    pile_init_frac: float = 0.5

    # ---------- добыча ----------
    mine_ore_tph: float = 1700.0
    strip_ratio: float = 1.5
    hard_frac_base: float = 0.5
    hard_frac_amp: float = 0.15    # медленная смена блоков в забое
    hard_frac_period_d: float = 5.0

    # ---------- аккумуляторные самосвалы (уровень B: Fortescue/Liebherr T264, 2,6 МВт·ч, 6 МВт, 2026) ----------
    n_trucks: int = 14
    truck_payload_t: float = 240.0
    truck_tare_t: float = 190.0
    truck_tph: float = 411.0       # производительность 1 самосвала, т/ч (цикл ~35 мин)
    truck_batt_mwh: float = 2.6    # SRC: thedriven.io 25.05.2026
    charger_n: int = 4
    charger_mw: float = 6.0        # SRC: там же
    eta_charge: float = 0.95
    fleet_soc_min: float = 0.20
    fleet_soc_max: float = 0.90
    ore_lift_m: float = 200.0
    ore_haul_km: float = 4.0
    waste_lift_m: float = 150.0
    waste_haul_km: float = 3.0
    crr: float = 0.025
    eta_drive: float = 0.85
    eta_regen: float = 0.60
    haul_aux_factor: float = 1.05

    # ---------- энергетика ----------
    wind_mw: float = 50.0
    pv_mwp: float = 40.0
    bess_mw: float = 15.0
    bess_mwh: float = 30.0
    bess_eta_rt: float = 0.88
    bess_soc_min: float = 0.10
    bess_soc_max: float = 0.95
    grid_cap_mw: float = 30.0
    tariff_kzt_kwh: float = 49.03  # SRC: rek-rudny.kz, юрлица, с 01.10.2026, без НДС
    # множители по зонам суток (ASSUMPTION: дифференцированный тариф)
    tou_night: float = 0.6   # 23–07
    tou_peak: float = 1.5    # 07–10, 18–23
    grid_co2_t_mwh: float = 0.79   # SRC: расчёт по Agora Energiewende 2025 (92,6 Мт / 117,9 ТВт·ч, 2023)

    # ---------- экономика ----------
    cu_price_usd_t: float = 9500.0  # ASSUMPTION
    usd_kzt: float = 480.0          # ASSUMPTION
    cu_payable: float = 0.85        # ASSUMPTION: доля оплачиваемой меди в концентрате

    # ---------- MPC ----------
    mpc_horizon_h: int = 24
    # Внутренняя цена CO₂ (тг/т), которую планировщик добавляет к цене сети.
    # 0 = «максимум меди»; больше = «зелёный» режим. Ручка для границы Парето.
    co2_price_kzt_t: float = 0.0

    # ===== производные величины =====
    @property
    def cu_value_kzt_t(self) -> float:
        return self.cu_price_usd_t * self.usd_kzt * self.cu_payable

    @property
    def fleet_e_max(self) -> float:
        return self.n_trucks * self.truck_batt_mwh * self.fleet_soc_max

    @property
    def fleet_e_min(self) -> float:
        return self.n_trucks * self.truck_batt_mwh * self.fleet_soc_min

    @property
    def charge_mw_max(self) -> float:
        return self.charger_n * self.charger_mw

    @property
    def bess_e_min(self) -> float:
        return self.bess_mwh * self.bess_soc_min

    @property
    def bess_e_max(self) -> float:
        return self.bess_mwh * self.bess_soc_max

    def tou(self, hour_of_day: int) -> float:
        h = hour_of_day % 24
        if h >= 23 or h < 7:
            return self.tou_night
        if 7 <= h < 10 or 18 <= h < 23:
            return self.tou_peak
        return 1.0

    def price_kzt_mwh(self, hour_of_day: int) -> float:
        return self.tariff_kzt_kwh * 1000.0 * self.tou(hour_of_day)


def aktogay() -> Params:
    """Масштаб реального рудника Актогай (KAZ Minerals, обл. Абай).

    SRC: KAZ Minerals, Annual Report 2024 — переработано 58,3 Мт руды
    (Сульфидная‑1 28,7 Мт + Сульфидная‑2 29,6 Мт), содержание 0,43 %,
    извлечение 87,9 %, 221 кт меди; электроэнергия 7,32 ПДж ≈ 2 030 ГВт·ч
    (≈ 230 МВт в среднем, ≈ 35 кВт·ч/т).
    Две фабрики моделируются как две линии по ~3 330 т/ч.
    ВЭС, СЭС, накопитель и электросамосвалы на Актогае пока НЕТ — это
    ASSUMPTION (сценарий «Тыныс»), их размеры — ручки what-if.
    """
    return Params(
        geomet=True, flexible_maintenance=True,
        lat=46.95, lon=79.86,                              # SRC: координаты карьера
        cu_grade={"soft": 0.0042, "hard": 0.0044},          # SRC: среднее 0,43 %
        r150={"soft": 0.885, "hard": 0.875},                # SRC: факт 87,9 % (калибровка)
        line_q_nom=3330.0, line_q_min=1665.0, line_q_max=4000.0,
        line_p_max_mw=65.0,
        restart_cost_kzt=2.0e7,
        crush_kwh_t=0.6,
        # ASSUMPTION/калибровка: вспомогательные потребители (водовод с Балхаша, насосы,
        # хвостовое хозяйство, фильтрация, мастерские, посёлок) при номинальных потоках.
        # 83 МВт подобраны так, чтобы V0 без ВИЭ на погоде 2024 брал из сети ≈ 2 030 ГВт·ч
        # в год, как в отчёте (с постоянной частью мощности мельниц и ремонтами); regress.py.
        auxiliary_nominal_mw=83.0,
        pile_cap_t=200_000.0,
        mine_ore_tph=6700.0, strip_ratio=1.2,
        n_trucks=42, charger_n=12,
        wind_mw=300.0, pv_mwp=250.0,
        bess_mw=60.0, bess_mwh=120.0,
        grid_cap_mw=260.0,                                   # ASSUMPTION: предел присоединения 220 кВ (выше средней нагрузки 230 МВт)
    )
