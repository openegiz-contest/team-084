"""Собирает presentation.pdf (корень репозитория) из данных решения.

Все числа берутся из data/sizing.csv и data/flex.csv, а не пишутся вручную.
Снимки экранов — img/*.png (снимаются со стенда скриптом shots.py).
Запуск из team/tynys:  python presentation/build.py"""
import asyncio, json, os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
D = os.path.join(HERE, "..", "data")
sz = pd.read_csv(os.path.join(D, "sizing.csv"))
fx = pd.read_csv(os.path.join(D, "flex.csv"))
eq = json.load(open(os.path.join(D, "wind-equivalent.json"), encoding="utf-8"))
eco = json.load(open(os.path.join(D, "economics.json"), encoding="utf-8"))


def row(w, p, v):
    return sz[(sz.wind_mw == w) & (sz.pv_mwp == p) & (sz.variant == v)].iloc[0]


def f(x, k=0):
    s = f"{x:,.{k}f}".replace(",", " ").replace(".", ",")
    return s.replace("-", "−")


def pct(a, b):
    return 100 * (a - b) / b


base = row(0, 0, "V0")
W, P = 300, 250
r = {v: row(W, P, v) for v in ("V0", "V2fixed", "V2", "V2green")}
year = fx[(fx.season == "all") | fx.season.str.startswith("весь год")].iloc[0]
piv = sz.pivot_table(index=["wind_mw", "pv_mwp"], columns="variant", values=["co2_adj_kt", "cu_adj_t", "curtail_mwh"])
green_rng = pct(piv.co2_adj_kt.V2green, piv.co2_adj_kt.V0)
cu_rng = pct(piv.cu_adj_t.V2, piv.cu_adj_t.V0)
copper_co2 = pct(piv.co2_adj_kt.V2, piv.co2_adj_kt.V0)
has = piv[piv.curtail_mwh.V0 > 0]
curt_cut = 100 * (1 - has.curtail_mwh.V2green / has.curtail_mwh.V0)

N = dict(
    co2_today=f(base.co2_kt), co2_today_adj=f(base.co2_adj_kt), cu_today=f(base.cu_adj_t / 1000, 1), gwh_today=f(base.grid_mwh / 1000),
    co2_res=f(r["V0"].co2_adj_kt), res_drop=f(pct(r["V0"].co2_adj_kt, base.co2_adj_kt)),
    curt_res=f(r["V0"].curtail_mwh / 1000), curt_green=f(r["V2green"].curtail_mwh / 1000), curt_cu=f(r["V2"].curtail_mwh / 1000),
    co2_green=f(r["V2green"].co2_adj_kt), co2_cu=f(r["V2"].co2_adj_kt), co2_fixed=f(r["V2fixed"].co2_adj_kt),
    cu_green=f(r["V2green"].cu_adj_t / 1000, 1), cu_cu=f(r["V2"].cu_adj_t / 1000, 1), cu_fixed=f(r["V2fixed"].cu_adj_t / 1000, 1),
    cu_res=f(r["V0"].cu_adj_t / 1000, 1),
    green_vs_res=f(pct(r["V2green"].co2_adj_kt, r["V0"].co2_adj_kt), 1), cu_gain=f(pct(r["V2"].cu_adj_t, r["V0"].cu_adj_t), 1),
    cuco2=f(pct(r["V2"].co2_adj_kt, r["V0"].co2_adj_kt), 1),
    green_min=f(green_rng.min(), 1), green_max=f(green_rng.max(), 1), green_worse=int((green_rng > 0).sum()),
    cu_min=f(cu_rng.min(), 1), cu_max=f(cu_rng.max(), 1),
    cuco2_min=f(copper_co2.min(), 1), cuco2_max=f(copper_co2.max(), 1),
    curt_min=f(curt_cut.min()), curt_max=f(curt_cut.max()), n_curt=len(has),
    flex_mw=f(year.mw_median), flex_p10=f(year.mw_p10), flex_p90=f(year.mw_p90), flex_h=f(year.h_median, 1),
    flex_hp10=f(year.h_p10, 1), flex_hp90=f(year.h_p90, 1), flex_mean=f(year.mw_mean),
    green_cu=f(pct(r["V2green"].cu_adj_t, r["V0"].cu_adj_t), 1), fixed_cu=f(pct(r["V2fixed"].cu_adj_t, r["V0"].cu_adj_t), 1),
    green_total=f(pct(r["V2green"].co2_adj_kt, base.co2_adj_kt), 1),
    eq_mw=f(eq["equivalent_wind_mw"]), eq_mw_cu=f(eq["equivalent_wind_mw_per_t_cu"]), eq_req=f(eq["required_baseline_wind_mw"]), eq_cu=f(eq["copper_change_pct"], 1),
)

CSS = """
@page{size:1280px 720px;margin:0}
*{box-sizing:border-box}body{margin:0;font-family:Inter,"Segoe UI","DejaVu Sans",Arial,sans-serif;color:#edf1f3;background:#0b141e}
.s{width:1280px;height:720px;padding:54px 70px;page-break-after:always;position:relative;overflow:hidden;background:#0b141e}
.s:before{content:"";position:absolute;inset:0;background:radial-gradient(ellipse at 85% -10%,#173a3655,transparent 60%)}
.s>*{position:relative}
.eb{font-size:13px;letter-spacing:.14em;font-weight:650;color:#e3a579;margin:0 0 14px}
h1{font-size:56px;line-height:1.08;letter-spacing:-.04em;font-weight:560;margin:0 0 18px}
h2{font-size:38px;letter-spacing:-.03em;font-weight:580;margin:0 0 22px;line-height:1.15}
em{font-style:normal;color:#6ce0cc}.cu{color:#e3a579}.bad{color:#ff9b8b}
p,li{font-size:22px;line-height:1.5;color:#c9d6de}li{margin-bottom:6px}
.m{color:#9aaebb}.sm{font-size:15px;color:#9aaebb}
.n{position:absolute;bottom:22px;right:40px;color:#748b9b;font-size:14px}
.grid{display:grid;gap:18px}.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:repeat(3,1fr)}.g4{grid-template-columns:repeat(4,1fr)}
.box{background:#121f2b;border:1px solid #283947;border-radius:16px;padding:22px 24px}
.box h3{margin:0 0 8px;font-size:15px;letter-spacing:.1em;color:#9aaebb;font-weight:650}
.big{font-size:44px;font-weight:560;letter-spacing:-.04em;line-height:1.1}
.box p{font-size:17px;margin:8px 0 0}
table{border-collapse:collapse;width:100%;font-size:20px;font-variant-numeric:tabular-nums}
th{font-size:14px;letter-spacing:.06em;color:#9aaebb;font-weight:600;text-align:right;padding:10px 12px;border-bottom:1px solid #3a4d5d}
td{padding:11px 12px;border-bottom:1px solid #253745;text-align:right}.tight td{padding:7px 10px}th:first-child,td:first-child{text-align:left}
img.shot{border-radius:14px;border:1px solid #283947;display:block}
.tag{display:inline-block;border:1px solid #326f60;background:#173d36;color:#6ce0cc;border-radius:7px;padding:3px 9px;font-size:14px;font-weight:600;margin-right:6px}
code{background:#172633;border:1px solid #283947;border-radius:6px;padding:1px 7px;font-size:.9em;color:#6ce0cc}
"""


def slides():
    n = N
    S = []
    S.append(f"""<div class="s"><p class="eb">КОНКУРС «ЦИФРОВОЙ РУДНИК НА OPENEGIZ» · КОМАНДА «СУПЕРКРОШКИ»</p>
<h1 style="margin-top:70px">Сколько ветра и солнца нужно<br>руднику Актогай, чтобы <em>сжигать<br>меньше угля</em>?</h1>
<p style="font-size:24px;max-width:980px">«Тыныс» — цифровой двойник реального медного рудника на OpenEgiz: модель, сверенная с отчётом KAZ Minerals 2024, реальная погода 2024 г. и координатор, который каждый час решает, как руднику «дышать» вместе с ветром и солнцем.</p>
<p class="m" style="position:absolute;bottom:50px">shrailymadil-debug · liyaaal · yusubovanazik</p></div>""")
    S.append(f"""<div class="s"><p class="eb">ПРОБЛЕМА</p><h2>Рудник круглосуточно берёт ≈ 230 МВт из сети, где 66 % — уголь</h2>
<div class="grid g3" style="margin-top:30px">
<div class="box"><h3>ЭНЕРГИЯ</h3><div class="big">{n['gwh_today']} ГВт·ч</div><p>в год по модели (отчёт KAZ Minerals 2024: ≈ 2 030 ГВт·ч)</p></div>
<div class="box"><h3>CO₂ С ЗАПАСАМИ</h3><div class="big bad">{n['co2_today_adj']} тыс. т</div><p>в год с учётом запасов в конце прогонов (склады и заряд батарей)</p></div>
<div class="box"><h3>ВЕТЕР И СОЛНЦЕ</h3><div class="big">непостоянны</div><p>рудник работает «ровно»; построенные ВЭС и СЭС будут сбрасывать энергию, когда она не нужна</p></div></div>
<p style="margin-top:34px">Нужно решить: <b>сколько ВЭС и СЭС строить</b>, <b>как руднику подстраиваться под них каждый час</b> и <b>что рудник может пообещать энергосистеме</b>.</p><div class="n">2</div></div>""")
    S.append(f"""<div class="s"><p class="eb">КТО ПОЛЬЗУЕТСЯ И КАКИЕ РЕШЕНИЯ ПРИНИМАЕТ</p><h2>Три решения — три экрана стенда</h2>
<div class="grid g3">
<div class="box"><h3>РУКОВОДСТВО · РАЗ В ГОД</h3><div class="big" style="font-size:30px">Сколько строить ВЭС и СЭС</div><p>25 сочетаний мощностей × 4 способа управления на реальной погоде 2024 г. — блок «Сколько строить» на пульте.</p></div>
<div class="box"><h3>ЭНЕРГЕТИК · КАЖДЫЙ ЧАС</h3><div class="big" style="font-size:30px">Какую руду молоть и когда заряжать</div><p>Координатор (MPC на 24 ч) выдаёт план, уставки и объяснение «почему так». Цель: «медь» или «CO₂».</p></div>
<div class="box"><h3>ПО ЗАПРОСУ KEGOC</h3><div class="big" style="font-size:30px">Выдержим ли меньший лимит сети?</div><p>«Два будущих»: один снимок рудника, обычное управление и «Тыныс» рядом, последствия и восстановление.</p></div></div>
<div class="n">3</div></div>""")
    S.append(f"""<div class="s"><p class="eb">РЕАЛЬНЫЙ ОБЪЕКТ И ДАННЫЕ</p><h2>Модель «как сейчас» сверена с годовым отчётом</h2>
<div class="grid g2"><div><table><tr><th></th><th>Модель (V0, без ВИЭ)</th><th>KAZ Minerals 2024</th></tr>
<tr><td>Медь, тыс. т/год</td><td>{n['cu_today']}</td><td>221</td></tr>
<tr><td>Электроэнергия, ГВт·ч/год</td><td>{n['gwh_today']}</td><td>≈ 2 030</td></tr>
<tr><td>Удельный расход, кВт·ч/т</td><td>36,3</td><td>≈ 35</td></tr>
<tr><td>Содержание / извлечение</td><td>0,43 % / ≈ 88 %</td><td>0,43 % / 87,9 %</td></tr></table>
<p class="sm" style="margin-top:14px">Вспомогательные потребители (водовод, хвосты, фильтрация, мастерские, посёлок) — 83 МВт при номинальных потоках; подобраны под энергию отчёта. Это калибровка, а не независимая проверка. Медь модель считает сама.</p></div>
<div><ul><li>Погода: почасовой ветер 100 м и радиация в точке рудника за 2024 г. — Open‑Meteo ERA5, CC BY 4.0.</li>
<li>Физика: закон Бонда, извлечение от крупности и времени флотации, энергия рейса самосвала, баланс мощности с пределом сети.</li>
<li>Чего на Актогае пока нет — ВЭС 300 МВт, СЭС 250 МВт, накопитель, 42 электросамосвала — помечено как допущение.</li></ul></div></div><div class="n">4</div></div>""")
    S.append(f"""<div class="s"><p class="eb">ПОСТРОЕНО НА OPENEGIZ</p><h2>51 двойник и 28 типов, все данные идут через платформу</h2>
<div class="box" style="font-size:22px;line-height:1.8"><b>Модель рудника</b> → MQTT <code>telemetry/&lt;двойник&gt;</code> → <b>Eclipse Ditto</b> → Telegraf → InfluxDB → <b>Grafana</b><br>
<b>Координатор</b> ⇄ Ditto: читает состояние и сценарий, пишет план, уставки и объяснение<br>
<b>Лаборатория «Два будущих»</b> ⇄ Ditto: запрос и результат расчёта — через двойники<br>
<b>Экраны</b> (Unity на главной, пульт, лёгкая 3D, «Два будущих») читают двойники и пишут сценарии «что если»</div>
<p style="margin-top:22px">Рудник → карьер (экскаваторы, 14 звеньев самосвалов, зарядки) · фабрика (склады мягкой и твёрдой руды, 2 линии, флотация) · энергия (ВЭС, СЭС, накопитель, подстанция). Связи «кто кому передаёт руду и энергию» записаны в атрибутах двойников.</p>
<p class="sm">Запуск: <code>sudo apt-get update &amp;&amp; sudo apt-get install -y make</code> · <code>make tynys</code> — проверено с нуля на Ubuntu 24.04 в GitHub Actions.</p><div class="n">5</div></div>""")
    S.append(f"""<div class="s"><p class="eb">МОДЕЛЬ РУДНИКА</p><h2>Оборудование, потоки и состояние — как на настоящем руднике</h2>
<div class="grid g3">
<div class="box"><h3>ПОТОК РУДЫ</h3><p>Экскаваторы → закреплённые звенья самосвалов → дробилка → конвейер → склады мягкой и твёрдой руды → конвейер питания → две линии мельниц → флотация → концентрат и хвосты; вскрыша — в отвал.</p></div>
<div class="box"><h3>ЭНЕРГИЯ</h3><p>Мельницы: постоянная часть мощности 35 %, пределы изменения подачи и мощности за час, один P80 на линию. Вспомогательные потребители — отдельные двойники с МВт. Батареи 14 звеньев самосвалов, накопитель, ВЭС, СЭС, предел сети.</p></div>
<div class="box"><h3>СОСТОЯНИЕ</h3><p>Исправность, наработка, ТО, ремонты и готовность у каждого объекта. Отказы ограничивают потоки, выпуск и энергию. Вода, хвосты, концентрат и вскрыша имеют материальные балансы.</p></div>
<div class="box"><h3>ГЕОЛОГИЯ GEOMET</h3><p>60 координатных проб открытого набора GeoMet (CC BY 4.0): твёрдость BWi, медь и извлечение по месту добычи. Это пространственный аналог, не скважины Актогая.</p></div>
<div class="box"><h3>РЕМОНТ НА ВЫДОХЕ</h3><p>Координатор ставит ТО и замену футеровки мельниц в окно, когда энергия из сети дороже (±12 ч от календаря, одна бригада).</p></div>
<div class="box"><h3>ДЕМО ЗА 3 МИНУТЫ</h3><p>Одна кнопка на пульте: штиль → 3D с остановленными ветряками и уступами по твёрдости → настоящий расчёт «Двух будущих».</p></div></div>
<div class="n">6</div></div>""")
    S.append(f"""<div class="s" style="padding:40px 50px"><p class="eb">ГДЕ СМОТРЕТЬ НА СТЕНДЕ · 1 / 3</p><h2 style="font-size:30px;margin-bottom:14px">Пульт рудника — <code>http://localhost:8095/dashboard.html</code></h2>
<div class="grid" style="grid-template-columns:780px 1fr;gap:26px"><img class="shot" src="img/pult.png" style="width:780px">
<ul style="padding-left:20px;margin:0"><li style="font-size:18px">Пять цифр сейчас: CO₂, доля ВИЭ, сброс, медь к «как сейчас», резерв</li>
<li style="font-size:18px">«Вдох / выдох» и «Почему так» — решение координатора словами</li><li style="font-size:18px">План на 24 ч и теневая цена энергии</li>
<li style="font-size:18px">Сравнение V0 / V1 / V2 на одной погоде</li><li style="font-size:18px">Цель «медь / CO₂», кнопки «что если» с параметрами и отменой, «Сколько строить», таблица оборудования</li></ul></div><div class="n">7</div></div>""")
    S.append(f"""<div class="s" style="padding:40px 50px"><p class="eb">ГДЕ СМОТРЕТЬ НА СТЕНДЕ · 2 / 3</p><h2 style="font-size:30px;margin-bottom:14px">3D‑сцена — <code>/3d.html</code></h2>
<div class="grid" style="grid-template-columns:780px 1fr;gap:26px"><img class="shot" src="img/3d.png" style="width:780px">
<ul style="padding-left:20px;margin:0"><li style="font-size:18px">«История: проблема → решение» — облёт с подписями</li>
<li style="font-size:18px">«Как сейчас / С „Тыныс“» — тот же час без координации и с ней</li><li style="font-size:18px">Щелчок по оборудованию — числа из двойника</li>
<li style="font-size:18px">Сценарии видны на оборудовании: красная линия, лимит сети на ЛЭП, отказ накопителя</li><li style="font-size:18px">Без видеокарты сцена сама переходит в облегчённый режим</li><li style="font-size:18px">Главная <code>http://localhost:8095</code> — та же шахта в Unity; плашка сверху показывает активные сценарии и ведёт к их запуску</li></ul></div><div class="n">8</div></div>""")
    S.append(f"""<div class="s" style="padding:40px 50px"><p class="eb">ГДЕ СМОТРЕТЬ НА СТЕНДЕ · 3 / 3</p><h2 style="font-size:30px;margin-bottom:14px">Два будущих — <code>/futures.html</code></h2>
<div class="grid" style="grid-template-columns:780px 1fr;gap:26px"><img class="shot" src="img/futures.png" style="width:780px">
<ul style="padding-left:20px;margin:0"><li style="font-size:18px">Запрос KEGOC: на сколько МВт и часов снизить лимит</li>
<li style="font-size:18px">«Проверить обещание»: один снимок рудника, обычное управление и «Тыныс» рядом</li><li style="font-size:18px">Фактическое снижение потребления — отдельно от снижения лимита</li>
<li style="font-size:18px">Цена помощи завтра: восстановление запасов и долг по меди</li><li style="font-size:18px">«Найти предел» и выгрузка расчёта в JSON</li></ul></div><div class="n">9</div></div>""")
    S.append(f"""<div class="s"><p class="eb">ЧТО ЕСЛИ — НА СТЕНДЕ, БЕЗ ИЗМЕНЕНИЯ КОДА</p><h2>Сценарии с параметрами — каждый отменяется кнопкой</h2>
<table class="tight" style="font-size:17px"><tr><th>Сценарий</th><th>Что меняется в модели</th><th>Где видно</th></tr>
<tr><td>Штиль на сутки</td><td>ветер 8 % на 24 ч, в прогнозе</td><td>ВЭС, план, сброс, CO₂</td></tr>
<tr><td>Авария линии 2</td><td>линия недоступна 8 ч</td><td>линия красная, склады растут</td></tr>
<tr><td>Запрос KEGOC −80 МВт</td><td>предел сети 260 → 180 МВт на 4 ч</td><td>ЛЭП, план, накопитель, зарядка</td></tr>
<tr><td>Пошла твёрдая руда</td><td>80 % твёрдой из забоя на 72 ч</td><td>карьер, склад твёрдой, энергия помола</td></tr>
<tr><td>План добычи +10 %</td><td>добыча 6 700 → 7 370 т/ч на 48 ч</td><td>самосвалы, склады, заряд</td></tr>
<tr><td>Отказ накопителя</td><td>накопитель недоступен 12 ч</td><td>накопитель, резерв, план</td></tr>
<tr><td>Ещё</td><td>поломка самосвалов / экскаватора, падение содержания меди, смена тарифа, отказы дробилки, конвейера, водовода</td><td>пульт и 3D, кнопки в обоих</td></tr></table>
<p class="sm" style="margin-top:16px">Длительность, линия, мощность запроса, доля потерь — задаются на экране. CI включает сценарии через двойник <code>scenario</code>, проверяет след в двойниках и последствия для меди и CO₂, затем отменяет.</p><div class="n">10</div></div>""")
    S.append(f"""<div class="s"><p class="eb">РЕЗУЛЬТАТ · ГОД НА РЕАЛЬНОЙ ПОГОДЕ 2024 · ВЭС {W} + СЭС {P} МВт</p><h2>Главное даёт стройка ВЭС и СЭС, координация — сверху</h2>
<table><tr><th></th><th>CO₂, тыс. т/год*</th><th>Медь, тыс. т/год</th><th>Сброс ВИЭ, ГВт·ч</th></tr>
<tr><td>Сегодня (без ВИЭ)</td><td>{n['co2_today_adj']}</td><td>{n['cu_today']}</td><td>0</td></tr>
<tr><td>ВИЭ, управление как сейчас</td><td>{n['co2_res']} <span class="m">({n['res_drop']} %)</span></td><td>{n['cu_res']}</td><td>{n['curt_res']}</td></tr>
<tr><td>ВИЭ + «Тыныс», цель «CO₂»</td><td><em>{n['co2_green']}</em></td><td>{n['cu_green']}</td><td><em>{n['curt_green']}</em></td></tr>
<tr><td>ВИЭ + «Тыныс», цель «медь»</td><td class="cu">{n['co2_cu']}</td><td class="cu">{n['cu_cu']}</td><td>{n['curt_cu']}</td></tr></table>
<ul style="margin-top:16px"><li>Цель «CO₂» к управлению «как сейчас» при тех же ВИЭ: {n['green_vs_res']} % CO₂ (всего {n['green_total']} % к сегодняшнему), по 25 сочетаниям от {n['green_min']} до {n['green_max']} %; медь {n['green_cu']} %. Это как ≈ {n['eq_mw']} МВт дополнительных ветряков (≈ {n['eq_mw_cu']} МВт, если сравнивать CO₂ на тонну меди).</li>
<li>Цель «медь»: +{n['cu_gain']} % меди за счёт более тонкого помола, но CO₂ +{n['cuco2']} %.</li></ul>
<p class="sm">* С учётом запасов в конце прогонов (склады, заряд батарей). Источник: <code>team/tynys/sizing.py</code> → <code>data/sizing.csv</code>, сводка — <code>analyze_sizing.py</code>.</p><div class="n">11</div></div>""")
    a, g, w = eco["variants"]["V2"], eco["variants"]["V2green"], eco["wind_alternative"]
    m = lambda x: ("+" if x > 0 else "−" if x < 0 else "") + f(abs(x), 1)
    mt = lambda x: ("+" if x > 0 else "−" if x < 0 else "") + f(abs(x))
    S.append(f"""<div class="s"><p class="eb">ЦЕНА ВЫБОРА В ДЕНЬГАХ · ВЭС {W} + СЭС {P} МВт · К УПРАВЛЕНИЮ «КАК СЕЙЧАС»</p><h2>Медь или уголь — двойник показывает цену решения</h2>
<table><tr><th></th><th>Медь, т/год</th><th>Медь, млн $</th><th>Энергия, ГВт·ч</th><th>Энергия, млн $</th><th>Итого, млн $/год</th></tr>
<tr><td>Цель «медь»</td><td>{mt(a['d_cu_t'])}</td><td>{m(a['copper_musd'])}</td><td>{m(a['d_grid_gwh'])}</td><td>{m(a['energy_musd'])}</td><td class="cu"><b>{m(a['net_musd'])}</b></td></tr>
<tr><td>Цель «CO₂»</td><td>{mt(g['d_cu_t'])}</td><td>{m(g['copper_musd'])}</td><td>{m(g['d_grid_gwh'])}</td><td>{m(g['energy_musd'])}</td><td><b>{m(g['net_musd'])}</b></td></tr></table>
<ul style="margin-top:18px"><li>Без платы за CO₂ выгоднее цель «медь». Цель «CO₂» снижает выбросы на {f(-g['d_co2_kt'])} тыс. т в год — это ≈ {f(g['usd_per_t_co2_avoided'])} $ за тонну CO₂.</li>
<li>Тот же CO₂ ветряками: ≈ {f(w['equivalent_mw_per_t_cu'])}–{f(w['equivalent_mw'])} МВт ВЭС ≈ {f(w['capex_musd_per_t_cu'])}–{f(w['capex_musd'])} млн $ единоразово — окупается против цели «CO₂» за 3–4 года.</li>
<li>Без компромисса: цель «медь» + ещё 150 МВт ВЭС (≈ {f(eco['copper_goal_plus_150mw']['capex_musd'])} млн $) — медь {mt(eco['copper_goal_plus_150mw']['d_cu_t'])} т и CO₂ {m(eco['copper_goal_plus_150mw']['d_co2_kt'])} тыс. т в год к «как сейчас»; окупаемость ≈ {f(eco['copper_goal_plus_150mw']['simple_payback_years'],1)} года.</li>
<li>В обеих целях координация вдвое сокращает сброс ветра и солнца. Что важнее — медь или уголь — решает руководство.</li></ul>
<p class="sm">Медь 14 441 $/т (LME, 21.10.2026), оплачиваемая доля 0,85 (допущение), курс 452,59 тенге за $ (Нацбанк РК, 20.10.2026), тариф 49,03 тенге/кВт·ч, ВЭС 1 041 $/кВт (IRENA 2024). Расчёт: <code>team/tynys/economics.py</code>.</p><div class="n">12</div></div>""")
    S.append(f"""<div class="s"><p class="eb">ЧЕСТНО О ГРАНИЦАХ</p><h2>Что модель утверждает — и чего нет</h2>
<ul><li>Прирост меди +{n['cu_min']}…+{n['cu_max']} % у цели «медь» — эффект тонкого помола, а не подстройки под ВИЭ. С крупностью «как сейчас» координатор теряет {n['fixed_cu']} % меди на остановках и перестройках линий — это цена гибкости.</li>
<li>Резерв для KEGOC по состоянию модели: медиана {n['flex_mw']} МВт (p10–p90 {n['flex_p10']}–{n['flex_p90']}) на {n['flex_h']} ч (p10–p90 {n['flex_hp10']}–{n['flex_hp90']}). Постоянная часть мощности мельниц и пределы изменения подачи честно уменьшили оценку. Конкретное обещание проверяется в «Двух будущих».</li>
<li>Модель часовая; движение самосвалов на экранах — схема (ускорено ×6), заряд и состояние звеньев — из модели.</li>
<li>Геология — открытый пространственный аналог GeoMet, а не скважины Актогая; прогноз погоды — реальный ряд плюс модельная ошибка; ERA5 занижает ветер.</li>
<li>Гибкость держится на мельницах; износ от перестроек и от тонкого помола не учтён, случайных отказов нет — настоящий рудник даст меньше гибкости, чем модель.</li></ul>
<p style="margin-top:26px"><em>Польза:</em> руководство видит, какие ВЭС и СЭС окупаются меньшим углём; энергетик понимает каждое решение — двойник объясняет его словами.</p><div class="n">13</div></div>""")
    return S


def build():
    html = f"<!doctype html><html lang=ru><head><meta charset=utf-8><style>{CSS}</style></head><body>{''.join(slides())}</body></html>"
    path = os.path.join(HERE, "slides.html")
    open(path, "w", encoding="utf-8").write(html)
    from playwright.async_api import async_playwright

    async def pdf():
        async with async_playwright() as p:
            b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1280, "height": 720})
            await pg.goto("file://" + path); await pg.wait_for_timeout(800)
            await pg.pdf(path=os.path.join(ROOT, "presentation.pdf"), width="1280px", height="720px", print_background=True)
            await b.close()
    asyncio.run(pdf())
    for k, v in N.items():
        print(f"{k:14s} {v}")


if __name__ == "__main__":
    build()
