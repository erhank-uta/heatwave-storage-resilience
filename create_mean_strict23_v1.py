#!/usr/bin/env python3
"""
Create a probability-weighted deterministic "mean_strict23" scenario from the
exact strict23 NPZ inputs consumed by TX123BT V7.4.

Outputs:
  mean_strict23_loads.npz
  mean_strict23_renewables.npz
  mean_strict23_manifest.csv
  nearest_strict23_scenarios.csv

The mean preserves the full 168-hour x 123-bus spatial/temporal structure:
    mean_load[t,b] = sum_s p_s load[s,t,b]
    mean_renew[t,b] = sum_s p_s renewable[s,t,b]

No optimization is run here. This is Step 1 only.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


EXP_REL = Path(
    "AORC_TX123BT/IBMWeatherGen/experiments/"
    "continuous_stationary_v6b_100members_seed12345"
)

LOAD_REL = (
    EXP_REL
    / "hybrid_selected_heatwave_week_loads_v1"
    / "optimization_input_primary_23_strict_hybrid.npz"
)

REN_REL = (
    EXP_REL
    / "renewable_selected_heatwave_week_hourly_v1"
    / "optimization_input_primary_23_strict_renewables.npz"
)


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--drive-root",
        type=Path,
        default=Path("data"),
        help="Root containing AORC_TX123BT (default: ./data)",
    )
    p.add_argument("--load-npz", type=Path, default=None)
    p.add_argument("--renewable-npz", type=Path, default=None)
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "data/AORC_TX123BT/IBMWeatherGen/experiments/"
            "continuous_stationary_v6b_100members_seed12345/"
            "mean_strict23_v1"
        ),
    )
    return p.parse_args()


def require(path: Path, label: str) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def probabilities(npz, n: int) -> np.ndarray:
    if "probability" in npz.files:
        p = np.asarray(npz["probability"], dtype=float).reshape(-1)
        if len(p) != n:
            raise ValueError(
                f"probability length {len(p)} does not match scenario count {n}"
            )
        if np.any(~np.isfinite(p)) or np.any(p < 0) or p.sum() <= 0:
            raise ValueError("Invalid scenario probabilities")
        return p / p.sum()
    return np.full(n, 1.0 / n, dtype=float)


def scenario_ids(npz, n: int) -> np.ndarray:
    if "scenario_id" in npz.files:
        ids = np.asarray(npz["scenario_id"]).astype(str).reshape(-1)
        if len(ids) != n:
            raise ValueError("scenario_id length does not match scenario count")
        return ids
    return np.array([f"STRICT_{i+1:03d}" for i in range(n)])


def single_scenario_payload(npz, data_key: str, mean_data: np.ndarray) -> dict:
    """
    Preserve metadata expected by V7.4. Any array whose first dimension equals
    the original scenario count is reduced to one scenario. Scenario-specific
    metadata is replaced conservatively; common metadata is copied unchanged.
    """
    n = npz[data_key].shape[0]
    out = {}

    for key in npz.files:
        value = np.asarray(npz[key])

        if key == data_key:
            out[key] = mean_data[np.newaxis, ...].astype(np.float32)

        elif key == "probability":
            out[key] = np.array([1.0], dtype=float)

        elif key == "scenario_id":
            # Unicode array: safe with allow_pickle=False.
            out[key] = np.array(["MEAN_STRICT23"])

        elif value.ndim >= 1 and value.shape[0] == n:
            # V7.4 may expect scenario-aligned metadata. For the synthetic mean
            # scenario, keep a one-row placeholder based on the first entry.
            # These fields are not averaged unless they are the actual load /
            # renewable arrays.
            out[key] = value[:1].copy()

        else:
            out[key] = value.copy()

    # Add required keys if originals omitted them.
    if "probability" not in out:
        out["probability"] = np.array([1.0], dtype=float)
    if "scenario_id" not in out:
        out["scenario_id"] = np.array(["MEAN_STRICT23"])

    return out


def weighted_mean(x: np.ndarray, p: np.ndarray) -> np.ndarray:
    return np.tensordot(p, x, axes=(0, 0))


def normalized_rms_distance(x: np.ndarray, mean: np.ndarray) -> np.ndarray:
    """
    RMS distance for each scenario divided by RMS magnitude of the mean.
    This makes load and renewable distances dimensionless before combining.
    """
    diff_rms = np.sqrt(np.mean((x - mean[None, ...]) ** 2, axis=(1, 2)))
    scale = np.sqrt(np.mean(mean ** 2))
    if scale <= 0:
        return diff_rms
    return diff_rms / scale


def main():
    a = cli()
    drive = a.drive_root.expanduser().resolve()

    load_path = require(
        a.load_npz.expanduser().resolve()
        if a.load_npz is not None
        else drive / LOAD_REL,
        "strict23 load NPZ",
    )
    ren_path = require(
        a.renewable_npz.expanduser().resolve()
        if a.renewable_npz is not None
        else drive / REN_REL,
        "strict23 renewable NPZ",
    )

    outdir = a.output_dir.expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    load_npz = np.load(load_path, allow_pickle=False)
    ren_npz = np.load(ren_path, allow_pickle=False)

    if "load_mw" not in load_npz.files:
        raise KeyError(f"{load_path} has no load_mw array")
    if "bus_generation_mw" not in ren_npz.files:
        raise KeyError(f"{ren_path} has no bus_generation_mw array")

    load = np.asarray(load_npz["load_mw"], dtype=float)
    ren = np.asarray(ren_npz["bus_generation_mw"], dtype=float)

    if load.shape != ren.shape:
        raise ValueError(
            f"Load/renewable shapes differ: {load.shape} vs {ren.shape}"
        )
    if load.ndim != 3:
        raise ValueError(f"Expected scenario x hour x bus arrays, got {load.shape}")
    if load.shape[0] != 23:
        raise ValueError(f"Expected strict23, found {load.shape[0]} scenarios")

    if "bus_id" not in load_npz.files or "bus_id" not in ren_npz.files:
        raise KeyError("Both NPZ files must contain bus_id")
    buses_l = np.asarray(load_npz["bus_id"]).astype(int)
    buses_r = np.asarray(ren_npz["bus_id"]).astype(int)
    if not np.array_equal(buses_l, buses_r):
        raise ValueError("Load and renewable bus_id arrays do not align")

    p_load = probabilities(load_npz, 23)
    p_ren = probabilities(ren_npz, 23)
    if not np.allclose(p_load, p_ren, atol=1e-12, rtol=0):
        raise ValueError("Load and renewable scenario probabilities differ")
    p = p_load

    ids_l = scenario_ids(load_npz, 23)
    ids_r = scenario_ids(ren_npz, 23)
    if not np.array_equal(ids_l, ids_r):
        raise ValueError("Load and renewable scenario_id arrays do not align")
    ids = ids_l

    mean_load = weighted_mean(load, p)
    mean_ren = weighted_mean(ren, p)

    # Fundamental consistency checks.
    weighted_total_load = float(np.dot(p, load.sum(axis=(1, 2))))
    weighted_total_ren = float(np.dot(p, ren.sum(axis=(1, 2))))
    if not np.isclose(mean_load.sum(), weighted_total_load, rtol=1e-10, atol=1e-4):
        raise RuntimeError("Mean load total fails expectation check")
    if not np.isclose(mean_ren.sum(), weighted_total_ren, rtol=1e-10, atol=1e-4):
        raise RuntimeError("Mean renewable total fails expectation check")
    if np.any(mean_load < -1e-8) or np.any(mean_ren < -1e-8):
        raise RuntimeError("Mean scenario contains materially negative values")

    mean_load = np.maximum(mean_load, 0.0)
    mean_ren = np.maximum(mean_ren, 0.0)

    load_out = outdir / "mean_strict23_loads.npz"
    ren_out = outdir / "mean_strict23_renewables.npz"

    np.savez_compressed(
        load_out,
        **single_scenario_payload(load_npz, "load_mw", mean_load),
    )
    np.savez_compressed(
        ren_out,
        **single_scenario_payload(ren_npz, "bus_generation_mw", mean_ren),
    )

    # ------------------------------------------------------------------
    # Find actual strict23 scenarios closest to the synthetic mean.
    # Report separate and joint normalized distances rather than hiding
    # the metric choice.
    # ------------------------------------------------------------------
    d_load = normalized_rms_distance(load, mean_load)
    d_ren = normalized_rms_distance(ren, mean_ren)

    # Equal importance to the two dimensionless profile distances.
    d_joint = np.sqrt(0.5 * d_load**2 + 0.5 * d_ren**2)

    nearest = pd.DataFrame({
        "scenario_index": np.arange(23, dtype=int),
        "scenario_id": ids,
        "probability": p,
        "normalized_rms_load_distance": d_load,
        "normalized_rms_renewable_distance": d_ren,
        "joint_normalized_rms_distance": d_joint,
        "weekly_total_load_mwh": load.sum(axis=(1, 2)),
        "weekly_total_renewable_available_mwh": ren.sum(axis=(1, 2)),
    }).sort_values(
        ["joint_normalized_rms_distance", "scenario_index"]
    )

    nearest["joint_rank"] = np.arange(1, len(nearest) + 1)
    nearest.to_csv(outdir / "nearest_strict23_scenarios.csv", index=False)

    manifest = pd.DataFrame([{
        "scenario_id": "MEAN_STRICT23",
        "source_scenarios": 23,
        "hours": load.shape[1],
        "buses": load.shape[2],
        "probability_sum": p.sum(),
        "probabilities_equal": bool(np.allclose(p, np.full(23, 1/23))),
        "mean_weekly_load_mwh": mean_load.sum(),
        "mean_weekly_renewable_available_mwh": mean_ren.sum(),
        "source_load_npz": str(load_path),
        "source_renewable_npz": str(ren_path),
        "source_load_sha256": sha256(load_path),
        "source_renewable_sha256": sha256(ren_path),
        "mean_load_npz": str(load_out),
        "mean_renewable_npz": str(ren_out),
        "nearest_actual_scenario_joint": nearest.iloc[0]["scenario_id"],
        "nearest_actual_scenario_index": int(nearest.iloc[0]["scenario_index"]),
        "nearest_joint_distance": nearest.iloc[0]["joint_normalized_rms_distance"],
    }])
    manifest.to_csv(outdir / "mean_strict23_manifest.csv", index=False)

    print("=" * 72)
    print("MEAN STRICT23 CREATED")
    print("=" * 72)
    print("Source load:", load_path)
    print("Source renewable:", ren_path)
    print("Shape:", load.shape, "(scenario, hour, bus)")
    print("Probability sum:", p.sum())
    print("Equal probabilities:", np.allclose(p, np.full(23, 1/23)))
    print()
    print("Mean weekly load MWh:", f"{mean_load.sum():,.3f}")
    print("Mean weekly renewable available MWh:", f"{mean_ren.sum():,.3f}")
    print()
    print("Wrote:")
    print(" ", load_out)
    print(" ", ren_out)
    print(" ", outdir / "mean_strict23_manifest.csv")
    print(" ", outdir / "nearest_strict23_scenarios.csv")
    print()
    print("Five actual scenarios closest to the mean (joint metric):")
    print(
        nearest[
            [
                "joint_rank",
                "scenario_index",
                "scenario_id",
                "normalized_rms_load_distance",
                "normalized_rms_renewable_distance",
                "joint_normalized_rms_distance",
            ]
        ].head(5).to_string(index=False)
    )


if __name__ == "__main__":
    main()
