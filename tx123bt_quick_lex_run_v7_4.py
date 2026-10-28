#!/usr/bin/env python3
"""Small local launcher for one-off TX123BT v7.4 lexicographic experiments.

Example:
  python tx123bt_quick_lex_run.py --id pi_s04_all123_m40_d4 \
      --scenarios 4 --candidates all --modules 40 --duration-hours 4

The launcher refuses to overwrite an existing result directory and records the
resolved command before starting the solver.  Extra model options can be placed
after ``--`` and are passed to the v7.2 model unchanged.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


CANDIDATE_SETS = {
    "screened9": "2,40,53,55,58,75,87,104,120",
    "pi18": "2,30,40,42,43,44,48,49,53,55,58,75,76,87,101,104,114,120",
    "all": "all",
}


def cli() -> tuple[argparse.Namespace, list[str]]:
    p = argparse.ArgumentParser(
        description="Launch one TX123BT v7.4 lexicographic run without editing experiment_plan.json"
    )
    p.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent)
    p.add_argument("--id", required=True, help="Unique result-directory name")
    p.add_argument("--scenario-set", choices=("primary23", "expanded48"), default="primary23")
    p.add_argument("--load-npz", type=Path, default=None,
                   help="Optional load NPZ override")
    p.add_argument("--renewable-npz", type=Path, default=None,
                   help="Optional renewable NPZ override")
    p.add_argument("--scenarios", default="all", help="all or comma-separated zero-based indices")
    p.add_argument("--candidates", default="screened9",
                   help="screened9, pi18, all, or comma-separated bus numbers")
    p.add_argument("--modules", type=int, default=40)
    p.add_argument("--max-modules-per-bus", type=int, default=0,
                   help="Uniform per-bus storage cap in modules; 0 disables")
    p.add_argument("--duration-hours", type=float, default=4.0)
    p.add_argument("--thermal-pmin", action="store_true",
                   help="Enforce dispatchable-generator Pmin values")
    p.add_argument("--phase-angle-bound-radians", type=float, default=0.0,
                   help="Symmetric absolute bus-angle bound; 0 disables it")
    p.add_argument("--mip-start", default="", help="Optional complete start; entries must sum to --modules")
    p.add_argument("--time-limit-per-level", "--time-limit-per-stage", dest="time_limit_per_level", type=float, default=28800.0)
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--level1-method", type=int, choices=(-1, 0, 1, 2, 3, 4, 5), default=3)
    p.add_argument("--level2-method", type=int, choices=(-1, 0, 1, 2, 3, 4, 5), default=3)
    p.add_argument("--level1-concurrent-method", type=int, choices=(-1, 0, 1, 2, 3), default=-1)
    p.add_argument("--level2-concurrent-method", type=int, choices=(-1, 0, 1, 2, 3), default=-1)
    p.add_argument("--level1-bar-homogeneous", type=int, choices=(-1, 0, 1), default=-1)
    p.add_argument("--level2-bar-homogeneous", type=int, choices=(-1, 0, 1), default=-1)
    p.add_argument("--level2-bar-order", type=int, choices=(-1, 0, 1), default=-1)
    p.add_argument("--level2-bar-correctors", type=int, default=-1)
    p.add_argument("--level2-bar-conv-tol", type=float, default=1e-8)
    p.add_argument("--level2-aggregate", type=int, choices=(0, 1, 2), default=1)
    p.add_argument("--level2-numeric-focus", type=int, choices=(0, 1, 2, 3), default=1)
    p.add_argument("--level2-scale-flag", type=int, choices=(-1, 0, 1, 2, 3), default=-1)
    p.add_argument("--level2-crossover-basis", type=int, choices=(-1, 0, 1), default=-1)
    p.add_argument("--level2-lp-warm-start", type=int, choices=(-1, 0, 1, 2), default=0)
    p.add_argument("--level2-probability-scaling", choices=("auto", "off"), default="auto")
    p.add_argument("--level2-abs-gap-dollars", type=float, default=1000.0)
    p.add_argument("--renewable-variable-cost-per-mwh", type=float, default=0.0)
    p.add_argument("--level3-cap-mode", "--stage3-cap-mode", dest="level3_cap_mode", choices=("scenario", "expected"), default="scenario")
    p.add_argument("--run-level3", "--run-stage3", dest="run_level3", action="store_true",
                   help="Opt in to throughput cleanup; default stops after Level 2")
    p.add_argument("--save-diagnostics", action="store_true",
                   help="Write detailed Level-2 hourly diagnostic tables")
    p.add_argument("--diagnostic-active-threshold-mwh", type=float, default=1.0)
    p.add_argument("--no-solver-log", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate arguments and print the resolved solver command without creating results or running Gurobi")
    return p.parse_known_args()


def main() -> None:
    a, extra = cli()
    if extra and extra[0] == "--":
        extra = extra[1:]
    root = a.project_root.expanduser().resolve()
    python = root / ".venv" / "bin" / "python"
    model = root / "tx123bt_gurobi_lexicographic_v7_4.py"
    data = root / "data"
    output = root / "results" / a.id
    for path in (python, model, data):
        if not path.exists():
            raise FileNotFoundError(path)
    if output.exists() and not a.dry_run:
        raise FileExistsError(f"Refusing to overwrite existing experiment: {output}")
    candidates = CANDIDATE_SETS.get(a.candidates, a.candidates)
    if a.mip_start:
        try:
            start_total = sum(float(item.split(":", 1)[1]) for item in a.mip_start.split(","))
        except (ValueError, IndexError) as exc:
            raise ValueError("--mip-start must use bus:value,bus:value syntax") from exc
        if abs(start_total-a.modules) > 1e-9:
            raise ValueError(
                f"MIP start violates exact budget: supplied {start_total:g}, required {a.modules}"
            )
    command = [
        str(python), str(model),
        "--drive-root", str(data),
        "--scenario-set", a.scenario_set,
        "--scenarios", a.scenarios,
        "--candidate-buses", candidates,
        "--modules", str(a.modules),
        "--max-modules-per-bus", str(a.max_modules_per_bus),
        "--duration-hours", str(a.duration_hours),
        "--phase-angle-bound-radians", str(a.phase_angle_bound_radians),
        "--time-limit-per-level", str(a.time_limit_per_level),
        "--threads", str(a.threads),
        "--level1-method", str(a.level1_method),
        "--level2-method", str(a.level2_method),
        "--level1-concurrent-method", str(a.level1_concurrent_method),
        "--level2-concurrent-method", str(a.level2_concurrent_method),
        "--level1-bar-homogeneous", str(a.level1_bar_homogeneous),
        "--level2-bar-homogeneous", str(a.level2_bar_homogeneous),
        "--level2-bar-order", str(a.level2_bar_order),
        "--level2-bar-correctors", str(a.level2_bar_correctors),
        "--level2-bar-conv-tol", str(a.level2_bar_conv_tol),
        "--level2-aggregate", str(a.level2_aggregate),
        "--level2-numeric-focus", str(a.level2_numeric_focus),
        "--level2-scale-flag", str(a.level2_scale_flag),
        "--level2-crossover-basis", str(a.level2_crossover_basis),
        "--level2-lp-warm-start", str(a.level2_lp_warm_start),
        "--level2-probability-scaling", a.level2_probability_scaling,
        "--level2-abs-gap-dollars", str(a.level2_abs_gap_dollars),
        "--renewable-variable-cost-per-mwh", str(a.renewable_variable_cost_per_mwh),
        "--level3-cap-mode", a.level3_cap_mode,
        "--diagnostic-active-threshold-mwh", str(a.diagnostic_active_threshold_mwh),
        "--output-dir", str(output),
    ]
    if a.mip_start:
        command.extend(["--mip-start", a.mip_start])
    if a.load_npz:
        command.extend(["--load-npz", str(a.load_npz.expanduser().resolve())])
    if a.renewable_npz:
        command.extend(["--renewable-npz", str(a.renewable_npz.expanduser().resolve())])
    if a.thermal_pmin:
        command.append("--thermal-pmin")
    if a.save_diagnostics:
        command.append("--save-diagnostics")
    if not a.no_solver_log:
        command.append("--solver-log")
    if a.run_level3:
        command.append("--run-level3")
    command.extend(extra)
    if a.dry_run:
        print("Validated command:", " ".join(command))
        return
    output.mkdir(parents=True)
    launch = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": a.id,
        "candidate_argument": a.candidates,
        "resolved_candidate_buses": candidates,
        "resolved_command": command,
        "v7_4_settings": {
            "level1_method": a.level1_method, "level2_method": a.level2_method, "level3_method": 0,
            "level1_abs_gap_mwh": 1.0,
            "level2_abs_gap_dollars": a.level2_abs_gap_dollars,
            "renewable_variable_cost_per_mwh": a.renewable_variable_cost_per_mwh,
            "level3_abs_gap_mwh": 0.0, "level_relative_gap": 0.0,
            "level3_cap_mode": a.level3_cap_mode,
            "level2_probability_scaling": a.level2_probability_scaling,
            "level2_numeric_focus": a.level2_numeric_focus,
            "level2_scale_flag": a.level2_scale_flag,
            "level2_crossover_basis": a.level2_crossover_basis,
            "level1_bar_homogeneous": a.level1_bar_homogeneous,
            "level2_bar_homogeneous": a.level2_bar_homogeneous,
            "level2_bar_order": a.level2_bar_order,
            "level2_bar_correctors": a.level2_bar_correctors,
            "level2_bar_conv_tol": a.level2_bar_conv_tol,
            "level2_aggregate": a.level2_aggregate,
            "level3_executed": bool(a.run_level3),
            "thermal_pmin": bool(a.thermal_pmin),
            "phase_angle_bound_radians": a.phase_angle_bound_radians,
            "max_modules_per_bus": a.max_modules_per_bus,
            "save_diagnostics": bool(a.save_diagnostics),
            "diagnostic_active_threshold_mwh": a.diagnostic_active_threshold_mwh,
        },
    }
    (output / "quick_launch_manifest.json").write_text(
        json.dumps(launch, indent=2), encoding="utf-8"
    )
    print("Running:", " ".join(command), flush=True)
    completed = subprocess.run(command)
    if completed.returncode:
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
