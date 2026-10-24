"""Wind equivalent: same PV, CO2 and Cu within 1%; interpolation, no extrapolation."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


def wind_equivalent(data, wind=300., pv=500., variant="V2green", copper_tolerance=.01):
    cols = ["wind_mw", "pv_mwp", "co2_adj_kt", "cu_adj_t"]
    if data[cols].isna().any().any() or not all(math.isfinite(float(v)) for v in data[cols].to_numpy().flat):
        raise ValueError("Sizing contains non-finite values")
    if data.duplicated(["wind_mw", "pv_mwp", "variant"]).any():
        raise ValueError("Duplicate sizing configurations")
    target = data[(data.wind_mw == wind) & (data.pv_mwp == pv) & (data.variant == variant)]
    base = data[(data.pv_mwp == pv) & (data.variant == "V0")].sort_values("wind_mw")
    out = dict(wind_mw=wind, pv_mwp=pv, variant=variant, copper_tolerance_pct=copper_tolerance*100,
               status="unavailable", equivalent_wind_mw=None)
    if len(target) != 1 or len(base) < 2:
        return {**out, "reason": "Недостаточно сопоставимых точек"}
    target = target.iloc[0]
    if target.cu_adj_t <= 0:
        return {**out, "reason": "Нет выпуска меди"}
    out.update(target_co2_kt=float(target.co2_adj_kt), target_cu_t=float(target.cu_adj_t))
    # Do not pass off reduced copper production as saved wind construction.
    for i in range(len(base)-1):
        a,b = base.iloc[i],base.iloc[i+1]
        if not a.co2_adj_kt > b.co2_adj_kt or not b.co2_adj_kt <= target.co2_adj_kt <= a.co2_adj_kt:
            continue
        if max(abs(a.cu_adj_t/target.cu_adj_t-1), abs(b.cu_adj_t/target.cu_adj_t-1)) > copper_tolerance:
            continue
        fraction = (a.co2_adj_kt-target.co2_adj_kt)/(a.co2_adj_kt-b.co2_adj_kt)
        required = a.wind_mw+fraction*(b.wind_mw-a.wind_mw)
        cu_base = a.cu_adj_t + fraction*(b.cu_adj_t-a.cu_adj_t)
        return {**out, "status": "ok", "required_baseline_wind_mw": float(required),
                "copper_change_pct": float(100*(target.cu_adj_t/cu_base-1)),
                "equivalent_wind_mw": float(required-wind), "grid_step_equivalent_mw": float((a.wind_mw if fraction == 0 else b.wind_mw)-wind),
                "bracket_wind_mw": [float(a.wind_mw),float(b.wind_mw)],
                "bracket_co2_kt": [float(a.co2_adj_kt),float(b.co2_adj_kt)],
                "bracket_cu_t": [float(a.cu_adj_t),float(b.cu_adj_t)],
                "method": "linear interpolation; fixed PV; Cu within tolerance; no extrapolation"}
    return {**out, "reason": "Нет интервала CO2 при сопоставимом выпуске меди; экстраполяция запрещена"}


def analyze(path, wind=300., pv=500., copper_tolerance=.01):
    result = wind_equivalent(pd.read_csv(path), wind, pv, copper_tolerance=copper_tolerance)
    metadata = path.with_suffix(".json")
    meta = json.loads(metadata.read_text(encoding="utf-8")) if metadata.exists() else {}
    digest = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    if meta.get("csv_sha256") and meta["csv_sha256"] != digest:
        raise ValueError("Sizing metadata checksum mismatch")
    result.update(source=path.name, csv_sha256=digest,
                  model_version=meta.get("model_version", "legacy-aggregate-v1"),
                  archived=not meta.get("model_version", "").startswith("physics-v4"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA/"sizing.csv")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--wind", type=float, default=300)
    parser.add_argument("--pv", type=float, default=500)
    parser.add_argument("--copper-tolerance-pct", type=float, default=1.0)
    args = parser.parse_args()
    result = analyze(args.input, args.wind, args.pv, args.copper_tolerance_pct/100)
    if result["status"] == "ok":
        print(f"Тыныс: эквивалент {result['equivalent_wind_mw']:.1f} МВт ВЭС по CO2 "
              f"({result['grid_step_equivalent_mw']:.0f} МВт по сетке расчёта)")
    else:
        print("Эквивалент ВЭС не определён: " + result["reason"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
