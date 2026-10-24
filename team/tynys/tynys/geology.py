"""GeoMet v4 spatial analogue. No claim that these are Aktogay drillholes.

Measured comminution tests define 60 representative locations, NOT reserve
blocks. Nearest spatial assays supply chemistry/LCT, with distances retained.
Mining sequence, support volumes and LCT at P80=150 are explicit assumptions.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

SOURCE = "https://doi.org/10.5281/zenodo.7051975"
DATA = Path(__file__).resolve().parents[1] / "data" / "geomet"


def bond_work_index(frame):
    # Hoffimann et al. 2022, equation 12; M g/rev, A/F80/P80 micrometres.
    return 49.0 / (frame.A**.23 * frame.M**.82 * (10/np.sqrt(frame.P80)-10/np.sqrt(frame.F80)))


@lru_cache(maxsize=1)
def model():
    meta = json.loads((DATA / "source.json").read_text(encoding="utf-8"))
    for f in meta["files"]:
        digest = hashlib.md5((DATA/f["key"]).read_bytes()).hexdigest()
        if f["checksum"] != "md5:"+digest:
            raise ValueError("GeoMet checksum mismatch: " + f["key"])
    c = pd.read_csv(DATA/"comminution.csv")
    d = pd.read_csv(DATA/"drillholes.csv").dropna(subset=["X", "Y", "Z", "Cu ppm"])
    f = pd.read_csv(DATA/"flotation.csv").dropna(subset=["X", "Y", "Z", "LCT"])
    xyz = c[["X", "Y", "Z"]].to_numpy()
    dd, di = cKDTree(d[["X", "Y", "Z"]]).query(xyz)
    fd, fi = cKDTree(f[["X", "Y", "Z"]]).query(xyz)
    bwi = bond_work_index(c).to_numpy()
    # Preserve spatial grade contrast but calibrate the analogue's mean to
    # Aktogay 0.43%; winsorize extreme assays before scaling (documented).
    raw_grade = d["Cu ppm"].to_numpy()[di]/1e6
    proxy = np.clip(raw_grade, *np.quantile(raw_grade, [.1, .9]))
    grade = proxy/proxy.mean()*.0043
    lo, hi = xyz.min(axis=0), xyz.max(axis=0)
    scaled = (xyz-lo)/(hi-lo)
    cells = []
    for i, row in c.iterrows():
        cells.append(dict(id=f"GM-{i+1:03d}", hole_id=int(row.HOLEID),
            x_m=float(row.X), y_m=float(row.Y), z_m=float(row.Z),
            # Schematic pit coordinates: uniform XY scaling, depth rescaling.
            u=float((row.X-(lo[0]+hi[0])/2)/max(hi[:2]-lo[:2])*1.7),
            v=float((row.Y-(lo[1]+hi[1])/2)/max(hi[:2]-lo[:2])*1.7),
            depth=float(1-scaled[i,2]), bwi=float(bwi[i]),
            grade_fraction=float(grade[i]), raw_grade_ppm=float(raw_grade[i]*1e6),
            lct=float(f.iloc[fi[i]].LCT), assay_distance_m=float(dd[i]),
            flotation_distance_m=float(fd[i]),
            domain="hard" if bwi[i] >= np.median(bwi) else "soft"))
    return dict(source=SOURCE, license="CC BY 4.0", version="GeoMet-v4",
        analogue=True, method="60 comminution locations; nearest XYZ Cu and valid LCT; calibrated Cu",
        drillhole_samples=len(d), comminution_samples=len(c), flotation_samples=len(f), cells=cells)


def install(env):
    """Deterministic two-face mining plan, 12 h per location; no random BWi."""
    cells = model()["cells"]
    n = env.sc.n()
    env.geology_ids = {}
    env.recovery_true = {}
    for domain in ("soft", "hard"):
        subset = sorted([c for c in cells if c["domain"] == domain], key=lambda c: (-c["z_m"], c["x_m"], c["id"]))
        indices = (np.arange(n)//12 + env.sc.start_doy*2) % len(subset)
        chosen = [subset[i] for i in indices]
        if domain == "hard":
            hard = max(subset, key=lambda c: c["bwi"])
            base = env.p.hard_frac_base
            for t in range(n):
                base = env.sc.hard_frac_shift.get(t, base)
                if base > env.p.hard_frac_base+.1:
                    chosen[t] = hard
        env.geology_ids[domain] = [c["id"] for c in chosen]
        env.bwi_true[domain] = np.array([c["bwi"] for c in chosen])
        env.grade_true[domain] = np.array([c["grade_fraction"] for c in chosen]) * env.grade_mult
        env.recovery_true[domain] = np.array([c["lct"] for c in chosen])


def telemetry(env, t):
    if not env.p.geomet:
        return {"source": "synthetic", "active_soft": "", "active_hard": ""}
    out = {"source": SOURCE, "analogue": True}
    for d in ("soft", "hard"):
        out.update({f"active_{d}": env.geology_ids[d][t], f"bwi_{d}": float(env.bwi_true[d][t]),
                    f"recovery_{d}_pct": float(env.recovery_true[d][t]*100),
                    f"grade_{d}_pct": float(env.grade_true[d][t]*100)})
    return out
