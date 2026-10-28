#!/usr/bin/env python3
"""Analyze flat V7.1 near-event perfect-information result folders.

The script is read-only with respect to optimization folders and is safe to run
while a batch is still progressing. It builds a planned-run inventory, reports
missing/incomplete/failed cases, and analyzes every validated completed run.

Example:
  python analyze_near25_pi_v7_1.py --root results
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

RUN_RE = re.compile(
    r"^pi_near_s(?P<scenario>\d+)_all123_m(?P<modules>\d+)_d(?P<duration>\d+)_pcm_v7_1(?:.*)?$",
    re.I,
)


def integers(text: str) -> list[int]:
    return sorted(set(int(x.strip()) for x in text.split(",") if x.strip()))


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path("results"))
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--modules", default="20,40,60,80")
    p.add_argument("--durations", default="2,4,6,8")
    p.add_argument("--scenarios", default="23-47",
                   help="Inclusive range such as 23-47 or comma-separated indices")
    p.add_argument("--placement-threshold", type=float, default=1e-6)
    p.add_argument("--recurrent-min-scenarios", type=int, default=2)
    return p.parse_args()


def scenario_values(text: str) -> list[int]:
    if "-" in text and "," not in text:
        lo, hi = map(int, text.split("-", 1))
        return list(range(lo, hi + 1))
    return integers(text)


def read_csv(path: Path):
    try:
        return pd.read_csv(path), ""
    except Exception as exc:
        return None, f"{path.name}: {exc}"


def one_value(df, column, default=np.nan):
    if df is None or df.empty or column not in df:
        return default
    return df.iloc[0][column]


def expected_name(s: int, n: int, d: int) -> str:
    return f"pi_near_s{s:02d}_all123_m{n}_d{d}_pcm_v7_1"


def locate(root: Path) -> dict[tuple[int, int, int], Path]:
    found = {}
    if not root.is_dir():
        return found
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        match = RUN_RE.match(folder.name)
        if not match:
            continue
        key = tuple(int(match.group(k)) for k in ("scenario", "modules", "duration"))
        if key in found:
            raise RuntimeError(f"Duplicate folders for {key}: {found[key]} and {folder}")
        found[key] = folder
    return found


def scan(a):
    root = a.root.expanduser().resolve()
    modules, durations, scenarios = integers(a.modules), integers(a.durations), scenario_values(a.scenarios)
    found = locate(root)
    inventory, scenario_rows, placement_rows, level_rows = [], [], [], []
    for n in modules:
        for d in durations:
            for s in scenarios:
                key, target = (s, n, d), found.get((s, n, d))
                notes = []
                if target is None:
                    inventory.append(dict(modules=n, duration_hours=d, scenario=s,
                        expected_folder=expected_name(s, n, d), state="missing",
                        usable=False, warning="", path=""))
                    continue
                overall, w1 = read_csv(target / "overall_summary.csv")
                levels, w2 = read_csv(target / "lexicographic_level_summary.csv")
                placements, w3 = read_csv(target / "lexicographic_level_placements.csv")
                scenario_df, w4 = read_csv(target / "scenario_summary.csv")
                notes.extend(x for x in (w1, w2, w3, w4) if x)
                validation_path = target / "validation_report.json"
                validation = None
                if validation_path.is_file():
                    try:
                        validation = json.loads(validation_path.read_text())
                    except Exception as exc:
                        notes.append(f"validation_report.json: {exc}")
                else:
                    notes.append("missing validation_report.json")
                required = all(x is not None for x in (overall, levels, placements, scenario_df))
                passed = bool(validation and validation.get("passed") is True)
                usable = required and passed and len(scenario_df) == 1
                if not required:
                    state = "incomplete"
                elif not passed:
                    state = "failed_validation"
                elif len(scenario_df) != 1:
                    state = "unexpected_scenario_count"
                    notes.append(f"scenario_summary rows={len(scenario_df)}; expected 1")
                else:
                    state = "complete"
                inventory.append(dict(modules=n, duration_hours=d, scenario=s,
                    expected_folder=expected_name(s, n, d), state=state, usable=usable,
                    warning="; ".join(notes), path=str(target)))
                if not usable:
                    continue

                l1 = levels[pd.to_numeric(levels["level"], errors="coerce").eq(1)].iloc[0]
                l2 = levels[pd.to_numeric(levels["level"], errors="coerce").eq(2)].iloc[0]
                sr = scenario_df.iloc[0]
                row = dict(modules=n, duration_hours=d, scenario=s,
                    scenario_id=str(sr.get("scenario_id", f"NEAR_SEL_{s-22:03d}")),
                    level1_load_shed_mwh=float(l1["incumbent"]),
                    level1_bound_mwh=float(l1["best_bound"]),
                    level1_abs_gap_mwh=float(l1["absolute_gap"]),
                    level2_load_shed_mwh=float(sr["load_shed_mwh"]),
                    level2_variable_cost_dollars=float(l2["incumbent"]),
                    level2_cost_bound_dollars=float(l2["best_bound"]),
                    level2_abs_gap_dollars=float(l2["absolute_gap"]),
                    thermal_generation_mwh=float(sr["thermal_generation_mwh"]),
                    renewable_curtailed_mwh=float(sr["renewable_curtailed_mwh"]),
                    battery_throughput_mwh=float(sr["battery_throughput_mwh"]),
                    level1_seconds=float(l1["solve_seconds"]), level2_seconds=float(l2["solve_seconds"]),
                    total_seconds=float(one_value(overall, "total_solve_seconds")),
                    peak_memory_gib=float(one_value(overall, "peak_memory_gib")), path=str(target))
                scenario_rows.append(row)
                for lr in levels.to_dict("records"):
                    level_rows.append(dict(modules=n, duration_hours=d, scenario=s, **lr))
                for pr in placements.to_dict("records"):
                    value = float(pr.get("modules", 0))
                    if value > a.placement_threshold:
                        placement_rows.append(dict(modules=n, duration_hours=d, scenario=s,
                            scenario_id=row["scenario_id"], level=int(pr["level"]),
                            objective_name=pr.get("objective_name", ""), bus=int(pr["bus"]),
                            assigned_modules=value, path=str(target)))
    return (pd.DataFrame(inventory), pd.DataFrame(scenario_rows),
            pd.DataFrame(placement_rows), pd.DataFrame(level_rows), modules, durations, scenarios)


def summarize(inv, runs, placements, modules, durations, scenarios):
    rows = []
    for n in modules:
        for d in durations:
            planned = inv[(inv.modules == n) & (inv.duration_hours == d)]
            g = runs[(runs.modules == n) & (runs.duration_hours == d)]
            out = dict(modules=n, duration_hours=d, planned_runs=len(scenarios),
                       complete_runs=len(g), completion_pct=100 * len(g) / len(scenarios))
            if not g.empty:
                out.update(expected_pi_shed_mwh=g.level1_load_shed_mwh.mean(),
                    expected_level2_shed_mwh=g.level2_load_shed_mwh.mean(),
                    mean_variable_cost_dollars=g.level2_variable_cost_dollars.mean(),
                    zero_shed_scenarios=int((g.level1_load_shed_mwh <= 1e-4).sum()),
                    max_level1_gap_mwh=g.level1_abs_gap_mwh.max(),
                    max_level2_gap_dollars=g.level2_abs_gap_dollars.max(),
                    mean_total_seconds=g.total_seconds.mean(), total_compute_hours=g.total_seconds.sum()/3600,
                    level1_union_size=placements[(placements.modules==n)&(placements.duration_hours==d)&(placements.level==1)].bus.nunique() if not placements.empty else 0,
                    level2_union_size=placements[(placements.modules==n)&(placements.duration_hours==d)&(placements.level==2)].bus.nunique() if not placements.empty else 0)
            rows.append(out)
    return pd.DataFrame(rows)


def placement_frequency(placements, runs):
    if placements.empty:
        return pd.DataFrame(columns=["modules","duration_hours","level","bus","scenarios_used","completed_scenarios","frequency","total_assigned_modules","mean_modules_when_used"])
    denom = runs.groupby(["modules", "duration_hours"]).size().rename("completed_scenarios")
    x = placements.groupby(["modules", "duration_hours", "level", "bus"], as_index=False).agg(
        scenarios_used=("scenario", "nunique"), total_assigned_modules=("assigned_modules", "sum"),
        mean_modules_when_used=("assigned_modules", "mean"), max_modules=("assigned_modules", "max"))
    x = x.merge(denom, on=["modules", "duration_hours"], how="left")
    x["frequency"] = x.scenarios_used / x.completed_scenarios
    return x.sort_values(["modules","duration_hours","level","scenarios_used","total_assigned_modules"], ascending=[True,True,True,False,False])


def candidate_sets(freq, minimum):
    result = {"definitions": {"union": "positive assigned modules in any completed run",
        "recurrent": f"positive assigned modules in at least {minimum} completed scenarios"}, "by_design": {}}
    for (n, d, level), g in freq.groupby(["modules", "duration_hours", "level"]):
        key = f"n{int(n):03d}_d{int(d):02d}_level{int(level)}"
        union = sorted(map(int, g.bus))
        recurrent = sorted(map(int, g.loc[g.scenarios_used >= minimum, "bus"]))
        result["by_design"][key] = {"completed_scenarios": int(g.completed_scenarios.max()),
            "union": union, "union_size": len(union), "recurrent": recurrent,
            "recurrent_size": len(recurrent), "candidate_argument": ",".join(map(str, union))}
    return result


def movement(placements):
    if placements.empty:
        return pd.DataFrame()
    p = placements.pivot_table(index=["modules","duration_hours","scenario","scenario_id"],
        columns=["level","bus"], values="assigned_modules", fill_value=0)
    buses = sorted(set(b for _, b in p.columns))
    rows = []
    for idx, r in p.iterrows():
        a = np.array([r.get((1,b),0) for b in buses]); b = np.array([r.get((2,b),0) for b in buses])
        rows.append(dict(zip(["modules","duration_hours","scenario","scenario_id"],idx),
            modules_moved_level1_to_level2=float(np.abs(a-b).sum()/2),
            level1_placement=";".join(f"{bus}:{a[i]:g}" for i,bus in enumerate(buses) if a[i]>1e-6),
            level2_placement=";".join(f"{bus}:{b[i]:g}" for i,bus in enumerate(buses) if b[i]>1e-6)))
    return pd.DataFrame(rows)


def main():
    a = cli()
    inv, runs, placements, levels, modules, durations, scenarios = scan(a)
    out = (a.output or a.root / "near25_pi_analysis_v7_1").expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    design = summarize(inv, runs, placements, modules, durations, scenarios)
    freq = placement_frequency(placements, runs)
    moves = movement(placements)
    inv.to_csv(out / "pi_run_inventory.csv", index=False)
    runs.to_csv(out / "pi_scenario_results.csv", index=False)
    design.to_csv(out / "pi_design_summary.csv", index=False)
    placements.to_csv(out / "pi_placement_evidence.csv", index=False)
    freq.to_csv(out / "pi_bus_frequency.csv", index=False)
    moves.to_csv(out / "pi_level1_level2_movement.csv", index=False)
    levels.to_csv(out / "pi_solver_level_results.csv", index=False)
    sets = candidate_sets(freq, a.recurrent_min_scenarios)
    (out / "pi_candidate_sets.json").write_text(json.dumps(sets, indent=2))
    status = inv.state.value_counts().to_dict()
    report = {"root": str(a.root.expanduser().resolve()), "output": str(out),
              "planned_runs": len(inv), "usable_complete_runs": len(runs),
              "states": {str(k): int(v) for k,v in status.items()},
              "complete_by_design": design[["modules","duration_hours","complete_runs","planned_runs"]].to_dict("records")}
    (out / "analysis_manifest.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    complete_designs = design[design.complete_runs == design.planned_runs]
    if not complete_designs.empty:
        print("\nComplete design summaries:")
        print(complete_designs.to_string(index=False))
    print(f"\nAnalysis written to {out}")


if __name__ == "__main__":
    main()
