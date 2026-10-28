#!/usr/bin/env python3
"""Two-level lexicographic TX123BT storage placement in gurobipy (v7.4).

Level 1 minimizes expected load shedding. Level 2 holds the best achieved load
shedding (plus a numerical feasibility tolerance) and minimizes expected
variable production cost.  The production-cost objective uses only the
``C1($/MWh)`` marginal-cost column in ``Generator_data.xlsx``.  It excludes
``C0`` and startup costs. Wind and solar default to zero variable cost; an
optional small renewable marginal cost is available as a dispatch tie-breaker.
Optional Level 3 holds both earlier objectives and minimizes
expected battery throughput. Placement remains free through Level 2 and is then
fixed before Level 3, so throughput cleans up dispatch but cannot choose sites.
Explicit nonnegative unserved-load variables make zero-shed cases numerically
stable. Operations remain continuous; no charge/discharge binaries are added.
Level-specific LP algorithms are exposed. After Level 2, fixed placement
variables can be converted to continuous variables so Level 3 is a pure LP.

V7.1 stops after Level 2 by default. The optional ``--run-level3`` cleanup adds
scenario-specific Level-3 caps. After Level 2, each scenario receives
its own load-shed and thermal-generation cap based on its Level-2 dispatch.
This removes cross-scenario operational trades during throughput cleanup.  With
placement fixed, the Level-3 constraint matrix is block separable by scenario.
The legacy expected-value caps remain available for controlled comparisons.
Small Level-2 checkpoint files are written before Level 3 starts.

V7.1 also rescales probability-weighted Level-2 expressions without changing the
mathematical problem.  For equal probabilities, this replaces 1/|S|
coefficients in the lexicographic cap by 1.  Reported objectives and certified
gaps remain in expected-MWh units.  MIP starts are empty by default and are
strictly validated against the placement budget when supplied.

V7.2 adds two opt-in formulation-parity controls. ``--thermal-pmin`` enforces
the workbook's ``Pmin (MW)`` values for dispatchable generators in every hour.
``--phase-angle-bound-radians`` applies symmetric absolute bounds to every bus
angle; its default of zero leaves angles unbounded, as in V7.1. Both controls
are disabled by default, so the V7.1 mathematical model is unchanged unless
they are requested explicitly.


V7.4 leaves the V7.2 mathematical formulation unchanged and adds opt-in
diagnostic output for forensic siting analysis. With ``--save-diagnostics``,
the solver writes gzip-compressed Level-2 hourly tables for installed-battery
operation, nodal balance quantities, transmission flows/utilization, generator
dispatch, and system totals, plus a battery-bus activity summary. The activity
summary uses ``--diagnostic-active-threshold-mwh`` (default 1 MWh) so surplus
installed modules can be distinguished from materially operated storage.
If Level 3 is requested, the same diagnostic tables are also written for the
Level-3 dispatch.


V7.4 additionally adds an opt-in uniform siting/interconnection cap through
``--max-modules-per-bus``. A value of zero (the default) disables the cap and
therefore exactly preserves the V7.3.1 feasible placement set. Positive values
set the upper bound of every candidate-bus placement variable to the specified
number of 50-MW modules. This is intended for controlled concentration
sensitivities, not as a claim that one universal interconnection limit applies
to every physical substation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
from pathlib import Path

import gurobipy as gp
import numpy as np
import pandas as pd
from gurobipy import GRB


EXP = Path("AORC_TX123BT/IBMWeatherGen/experiments/continuous_stationary_v6b_100members_seed12345")
FILES = {
    "primary23": (
        "renewable_selected_heatwave_week_hourly_v1/optimization_input_primary_23_strict_renewables.npz",
        "hybrid_selected_heatwave_week_loads_v1/optimization_input_primary_23_strict_hybrid.npz",
    ),
    "expanded48": (
        "renewable_selected_heatwave_week_hourly_v1/optimization_input_expanded_48_renewables.npz",
        "hybrid_selected_heatwave_week_loads_v1/optimization_input_expanded_48_hybrid.npz",
    ),
}


def stamp(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg, flush=True)


def mem_gib():
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / 1024**3 if sys.platform == "darwin" else raw / 1024**2


def ints(text):
    return sorted(set(int(x.strip()) for x in text.split(",") if x.strip()))


def mapping(text):
    out = {}
    if text:
        for item in text.split(","):
            key, value = item.strip().split(":")
            out[int(key)] = float(value)
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def cli():
    p = argparse.ArgumentParser(description="TX123BT lexicographic extensive form in gurobipy")
    p.add_argument("--drive-root", type=Path, default=Path("/content/gdrive/MyDrive"))
    p.add_argument("--scenario-set", choices=FILES, default="primary23")
    p.add_argument("--load-npz", type=Path, default=None,
                   help="Optional load NPZ override for controlled scenario experiments")
    p.add_argument("--renewable-npz", type=Path, default=None,
                   help="Optional renewable NPZ override for controlled scenario experiments")
    p.add_argument("--scenarios", default="all")
    p.add_argument(
        "--stop-after-level1",
        action="store_true",
        help="Stop cleanly after Level 1 and its checkpoint files are written",
    )
    p.add_argument("--candidate-buses", default="2,40,53,55,58,75,87,104,120")
    p.add_argument("--required-buses", default="")
    p.add_argument("--minimum-modules", default="", help="bus:min,bus:min")
    p.add_argument("--fixed-modules", default="", help="bus:value,bus:value")
    p.add_argument("--mip-start", default="", help="Optional complete placement start bus:value,bus:value; must satisfy the budget")
    p.add_argument("--placement-domain", choices=("integer", "continuous"), default="integer")
    p.add_argument("--modules", type=int, default=40)
    p.add_argument("--max-modules-per-bus", type=int, default=0,
                   help="Uniform candidate-bus storage cap in modules; 0 disables the cap")
    p.add_argument("--budget-sense", choices=("exact", "upper"), default="exact")
    p.add_argument("--base-mva", type=float, default=100.0)
    p.add_argument("--module-power-mw", type=float, default=50.0)
    p.add_argument("--module-charge-mw", type=float, default=50.0)
    p.add_argument("--module-discharge-mw", type=float, default=50.0)
    p.add_argument("--duration-hours", type=float, default=4.0)
    p.add_argument("--eta-charge", type=float, default=0.95)
    p.add_argument("--eta-discharge", type=float, default=0.95)
    p.add_argument("--initial-soc-fraction", type=float, default=0.5)
    p.add_argument("--terminal-soc-fraction", type=float, default=0.5)
    p.add_argument("--no-ramping", action="store_true")
    p.add_argument("--thermal-pmin", action="store_true",
                   help="Enforce Pmin (MW) for every dispatchable generator and hour")
    p.add_argument("--phase-angle-bound-radians", type=float, default=0.0,
                   help="Symmetric absolute bus-angle bound in radians; 0 disables it (V7.1 default)")
    p.add_argument("--level1-abs-gap", "--stage1-abs-gap", dest="level1_abs_gap", type=float, default=1.0, help="Certified expected-load-shed gap (MWh)")
    p.add_argument("--level2-abs-gap-dollars", "--level2-abs-gap", "--stage2-abs-gap",
                   dest="level2_abs_gap_dollars", type=float, default=1000.0,
                   help="Certified expected variable-production-cost gap ($); old option names remain aliases")
    p.add_argument("--level3-abs-gap", "--stage3-abs-gap", dest="level3_abs_gap", type=float, default=0.0, help="Placeholder for LP Level 3; MIP gaps do not govern LP termination")
    p.add_argument("--level-relative-gap", "--stage-relative-gap", dest="level_relative_gap", type=float, default=0.0, help="Set positive only if relative-gap stopping is desired")
    p.add_argument("--load-cap-feasibility-tolerance", type=float, default=0.1)
    p.add_argument("--zero-load-cap-tolerance", type=float, default=1e-4)
    p.add_argument("--zero-load-threshold", type=float, default=1e-4)
    p.add_argument("--production-cost-cap-feasibility-tolerance-dollars", type=float, default=10.0)
    p.add_argument("--renewable-variable-cost-per-mwh", type=float, default=0.0,
                   help="Wind/solar marginal cost in Level 2 ($/MWh); default 0")
    p.add_argument("--time-limit-per-level", "--time-limit-per-stage", dest="time_limit_per_level", type=float, default=28800.0)
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--presolve", type=int, choices=(-1, 0, 1, 2), default=2)
    p.add_argument("--level1-method", "--stage1-method", dest="level1_method", type=int, choices=(-1, 0, 1, 2, 3, 4, 5), default=3)
    p.add_argument("--level2-method", "--stage2-method", dest="level2_method", type=int, choices=(-1, 0, 1, 2, 3, 4, 5), default=3)
    p.add_argument("--level3-method", "--stage3-method", dest="level3_method", type=int, choices=(-1, 0, 1, 2, 3, 4, 5), default=0)
    p.add_argument("--level1-concurrent-method", type=int, choices=(-1, 0, 1, 2, 3), default=-1)
    p.add_argument("--level2-concurrent-method", type=int, choices=(-1, 0, 1, 2, 3), default=-1)
    p.add_argument("--level1-bar-homogeneous", type=int, choices=(-1, 0, 1), default=-1,
                   help="Homogeneous barrier at Level 1: -1 auto, 0 off, 1 on")
    p.add_argument("--level2-bar-homogeneous", type=int, choices=(-1, 0, 1), default=-1,
                   help="Homogeneous barrier at Level 2: -1 auto, 0 off, 1 on")
    p.add_argument("--level2-bar-order", type=int, choices=(-1, 0, 1), default=-1,
                   help="Barrier ordering at Level 2: -1 auto, 0 AMD, 1 nested dissection")
    p.add_argument("--level2-bar-correctors", type=int, default=-1,
                   help="Maximum central corrections at Level 2; -1 lets Gurobi choose")
    p.add_argument("--level2-bar-conv-tol", type=float, default=1e-8,
                   help="Barrier convergence tolerance at Level 2")
    p.add_argument("--level2-aggregate", type=int, choices=(0, 1, 2), default=1,
                   help="Presolve aggregation at Level 2: 0 off, 1 moderate, 2 aggressive")
    p.add_argument("--level2-numeric-focus", type=int, choices=(0, 1, 2, 3), default=1)
    p.add_argument("--level2-scale-flag", type=int, choices=(-1, 0, 1, 2, 3), default=-1)
    p.add_argument("--level2-crossover-basis", type=int, choices=(-1, 0, 1), default=-1)
    p.add_argument("--level2-lp-warm-start", type=int, choices=(-1, 0, 1, 2), default=0)
    p.add_argument("--level2-probability-scaling", choices=("auto", "off"), default="auto",
                   help="Scale Level-2 expected-value cap/objective by 1/max_s(p_s); reporting remains expected dollars")
    p.add_argument("--level3-cap-mode", "--stage3-cap-mode", dest="level3_cap_mode", choices=("scenario", "expected"), default="scenario",
                   help="Scenario-specific Level-2 caps (default) or legacy expected-value caps")
    p.add_argument("--run-level3", "--run-stage3", dest="run_level3", action="store_true",
                   help="Opt in to battery-throughput cleanup; default is to stop after Level 2")
    p.add_argument("--keep-stage3-integer-types", action="store_true",
                   help="Keep fixed placement variables typed as integer in stage 3")
    p.add_argument("--numeric-focus", type=int, choices=(0, 1, 2, 3), default=1)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--solver-log", action="store_true")
    p.add_argument("--write-model", action="store_true")
    p.add_argument("--activity-tolerance", type=float, default=1e-4)
    p.add_argument("--save-diagnostics", action="store_true",
                   help="Write detailed gzip-compressed hourly Level-2 diagnostic tables")
    p.add_argument("--diagnostic-active-threshold-mwh", type=float, default=1.0,
                   help="Battery-bus weekly throughput threshold used to label an installed bus active")
    p.add_argument("--output-dir", type=Path, required=True)
    return p.parse_args()


def load_inputs(a):
    if a.level2_bar_correctors < -1:
        raise ValueError("--level2-bar-correctors must be -1 or nonnegative")
    if not np.isfinite(a.level2_bar_conv_tol) or not 0 < a.level2_bar_conv_tol <= 1:
        raise ValueError("--level2-bar-conv-tol must be in (0,1]")
    if not np.isfinite(a.phase_angle_bound_radians) or a.phase_angle_bound_radians < 0:
        raise ValueError("--phase-angle-bound-radians must be finite and nonnegative")
    if not np.isfinite(a.diagnostic_active_threshold_mwh) or a.diagnostic_active_threshold_mwh < 0:
        raise ValueError("--diagnostic-active-threshold-mwh must be finite and nonnegative")
    if a.max_modules_per_bus < 0:
        raise ValueError("--max-modules-per-bus must be nonnegative")
    if a.max_modules_per_bus > 0:
        if a.budget_sense == "exact" and a.candidate_buses.lower() != "all":
            candidate_count_for_cap = len(ints(a.candidate_buses))
            if candidate_count_for_cap * a.max_modules_per_bus < a.modules:
                raise ValueError("Per-bus cap makes the exact module budget infeasible for the candidate set")
    grid, exp = a.drive_root / "TX123BT", a.drive_root / EXP
    rr, lr = FILES[a.scenario_set]
    paths = {
        "bus": grid / "Bus_data.csv",
        "line": grid / "Line_data.csv",
        "generator": grid / "Generator_data.xlsx",
        "renewable": a.renewable_npz.expanduser().resolve() if a.renewable_npz else exp / rr,
        "load": a.load_npz.expanduser().resolve() if a.load_npz else exp / lr,
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    bus = pd.read_csv(paths["bus"])
    line = pd.read_csv(paths["line"])
    gen = pd.read_excel(paths["generator"], sheet_name="Gen data")
    wind = pd.read_excel(paths["generator"], sheet_name="Wind Plant Number")
    solar = pd.read_excel(paths["generator"], sheet_name="Solar Plant Number")
    required_gen_columns = {"Gen Number", "Bus Number", "Pmax (MW)", "Pmin (MW)", "C1($/MWh)"}
    missing_gen_columns = required_gen_columns.difference(gen.columns)
    if missing_gen_columns:
        raise ValueError(f"Generator data missing required columns: {sorted(missing_gen_columns)}")
    if gen["C1($/MWh)"].isna().any() or (gen["C1($/MWh)"] < 0).any():
        raise ValueError("C1($/MWh) must contain finite nonnegative marginal costs")
    if gen["Pmin (MW)"].isna().any() or not np.isfinite(gen["Pmin (MW)"].astype(float)).all():
        raise ValueError("Pmin (MW) must contain finite values")
    if (gen["Pmin (MW)"] < 0).any() or (gen["Pmin (MW)"] > gen["Pmax (MW)"]).any():
        raise ValueError("Generator Pmin values must satisfy 0 <= Pmin <= Pmax")
    if not np.isfinite(a.renewable_variable_cost_per_mwh) or a.renewable_variable_cost_per_mwh < 0:
        raise ValueError("--renewable-variable-cost-per-mwh must be finite and nonnegative")
    rn = np.load(paths["renewable"], allow_pickle=False)
    ln = np.load(paths["load"], allow_pickle=False)
    renewable, demand = rn["bus_generation_mw"].astype(float), ln["load_mw"].astype(float)
    buses = bus["Bus Number"].astype(int).tolist()
    scenarios = list(range(demand.shape[0])) if a.scenarios.lower() == "all" else ints(a.scenarios)
    candidates = buses if a.candidate_buses.lower() == "all" else ints(a.candidate_buses)
    if renewable.shape != demand.shape or not np.array_equal(buses, rn["bus_id"].astype(int)) or not np.array_equal(buses, ln["bus_id"].astype(int)):
        raise ValueError("Renewable/load/bus alignment failure")
    if not scenarios or min(scenarios) < 0 or max(scenarios) >= demand.shape[0]:
        raise ValueError("Invalid scenarios")
    if not candidates or not set(candidates).issubset(buses):
        raise ValueError("Invalid candidate buses")
    required, minimum, fixed, start = ints(a.required_buses), mapping(a.minimum_modules), mapping(a.fixed_modules), mapping(a.mip_start)
    if a.max_modules_per_bus > 0:
        cap = float(a.max_modules_per_bus)
        if any(value > cap + 1e-9 for value in minimum.values()):
            raise ValueError("A minimum-modules requirement exceeds --max-modules-per-bus")
        if any(value > cap + 1e-9 for value in fixed.values()):
            raise ValueError("A fixed-modules value exceeds --max-modules-per-bus")
        if any(value > cap + 1e-9 for value in start.values()):
            raise ValueError("A MIP-start value exceeds --max-modules-per-bus")
    for label, values in (("required", required), ("minimum", minimum), ("fixed", fixed), ("start", start)):
        if not set(values).issubset(candidates):
            raise ValueError(f"{label} bus outside candidate set")
    if start:
        if any(not np.isfinite(v) or v < 0 or v > a.modules for v in start.values()):
            raise ValueError("MIP-start values must be finite and between 0 and the module budget")
        if a.placement_domain == "integer" and any(abs(v-round(v)) > 1e-9 for v in start.values()):
            raise ValueError("Integer placement requires integer-valued MIP-start entries")
        start_total = float(sum(start.values()))
        if a.budget_sense == "exact" and abs(start_total-a.modules) > 1e-9:
            raise ValueError(
                f"MIP start violates exact module budget: supplied {start_total:g}, required {a.modules}"
            )
        if a.budget_sense == "upper" and start_total > a.modules + 1e-9:
            raise ValueError(
                f"MIP start exceeds module budget: supplied {start_total:g}, maximum {a.modules}"
            )
        if any(start.get(b, 0.0) < 1-1e-9 for b in required):
            raise ValueError("MIP start violates a required-bus lower bound")
        if any(start.get(b, 0.0) < value-1e-9 for b, value in minimum.items()):
            raise ValueError("MIP start violates a minimum-modules lower bound")
        if any(abs(start.get(b, 0.0)-value) > 1e-9 for b, value in fixed.items()):
            raise ValueError("MIP start violates a fixed-modules value")
    raw_p = ln["probability"].astype(float)[scenarios]
    probability = raw_p / raw_p.sum()
    renewable_ids = set(wind["Generator Number"].astype(int)) | set(solar["Generator Number"].astype(int))
    thermal = gen[~gen["Gen Number"].astype(int).isin(renewable_ids)].copy()
    a.output_dir.mkdir(parents=True, exist_ok=True)
    return dict(paths=paths, bus=bus, line=line, thermal=thermal, renewable=renewable, demand=demand,
                buses=buses, scenarios=scenarios, candidates=candidates,
                probability=dict(zip(scenarios, probability)),
                scenario_id={s: str(ln["scenario_id"][s]) for s in scenarios},
                required=required, minimum=minimum, fixed=fixed, start=start)


def build_and_solve(d, a):
    B, S, C = d["buses"], d["scenarios"], d["candidates"]
    H = list(range(d["demand"].shape[1])); Q = list(range(len(H) + 1)); bi = {b: i for i, b in enumerate(B)}
    thermal = d["thermal"]; G = thermal["Gen Number"].astype(int).tolist()
    pmax = {int(r["Gen Number"]): float(r["Pmax (MW)"]) for _, r in thermal.iterrows()}
    pmin = {int(r["Gen Number"]): float(r["Pmin (MW)"]) for _, r in thermal.iterrows()}
    marginal_cost = {int(r["Gen Number"]): float(r["C1($/MWh)"]) for _, r in thermal.iterrows()}
    ramp = {int(r["Gen Number"]): 60.0 * float(r["Ramping Rate(MW/min)"]) for _, r in thermal.iterrows()}
    gb = {b: [] for b in B}
    for _, row in thermal.iterrows(): gb[int(row["Bus Number"])].append(int(row["Gen Number"]))
    line = d["line"].copy(); line["line_num"] = line["line_num"].astype(int)
    K = line["line_num"].tolist(); fr = dict(zip(K, line["From Bus Number"].astype(int))); to = dict(zip(K, line["To Bus Number"].astype(int)))
    reactance = dict(zip(K, line["X, pu"].astype(float))); capacity = dict(zip(K, line["Capacity (MW)"].astype(float)))
    incoming, outgoing = {b: [] for b in B}, {b: [] for b in B}
    for k in K: outgoing[fr[k]].append(k); incoming[to[k]].append(k)

    m = gp.Model("tx123bt_stochastic_storage_lexicographic")
    m.Params.OutputFlag = int(a.solver_log); m.Params.LogToConsole = int(a.solver_log)
    m.Params.Threads = a.threads; m.Params.Presolve = a.presolve; m.Params.Method = a.level1_method
    m.Params.NumericFocus = a.numeric_focus; m.Params.Seed = a.seed
    xtype = GRB.INTEGER if a.placement_domain == "integer" else GRB.CONTINUOUS
    placement_ub = min(a.modules, a.max_modules_per_bus) if a.max_modules_per_bus > 0 else a.modules
    x = m.addVars(C, lb=0, ub=placement_ub, vtype=xtype, name="modules")
    pg = m.addVars(S, G, H, lb=0, name="pg")
    theta_bound = a.phase_angle_bound_radians if a.phase_angle_bound_radians > 0 else GRB.INFINITY
    theta = m.addVars(S, B, H, lb=-theta_bound, ub=theta_bound, name="theta")
    flow = m.addVars(S, K, H, lb=-GRB.INFINITY, name="flow")
    unserved = m.addVars(S, B, H, lb=0, name="unserved")
    renew = m.addVars(S, B, H, lb=0, name="renew")
    charge = m.addVars(S, C, H, lb=0, name="charge")
    discharge = m.addVars(S, C, H, lb=0, name="discharge")
    soc = m.addVars(S, C, Q, lb=0, name="soc")
    total = gp.quicksum(x[b] for b in C)
    m.addConstr(total == a.modules if a.budget_sense == "exact" else total <= a.modules, name="budget")
    for b in d["required"]: x[b].LB = max(x[b].LB, 1)
    for b, value in d["minimum"].items(): x[b].LB = max(x[b].LB, value)
    for b, value in d["fixed"].items(): x[b].LB = x[b].UB = value
    if d["start"]:
        for b in C:
            x[b].Start = d["start"].get(b, 0.0)
    energy = a.module_power_mw * a.duration_hours
    for s in S:
        for g in G:
            for t in H:
                m.addConstr(pg[s,g,t] <= pmax[g])
                if a.thermal_pmin:
                    m.addConstr(pg[s,g,t] >= pmin[g])
                if t and not a.no_ramping:
                    m.addConstr(pg[s,g,t] - pg[s,g,t-1] <= ramp[g])
                    m.addConstr(pg[s,g,t-1] - pg[s,g,t] <= ramp[g])
        for b in B:
            for t in H:
                m.addConstr(renew[s,b,t] <= float(d["renewable"][s,t,bi[b]]))
                m.addConstr(unserved[s,b,t] <= float(d["demand"][s,t,bi[b]]))
        for k in K:
            for t in H:
                m.addConstr(flow[s,k,t] == (a.base_mva/reactance[k])*(theta[s,fr[k],t]-theta[s,to[k],t]))
                m.addConstr(flow[s,k,t] <= capacity[k]); m.addConstr(flow[s,k,t] >= -capacity[k])
        for t in H: m.addConstr(theta[s,1,t] == 0)
        for b in C:
            for t in H:
                m.addConstr(charge[s,b,t] <= a.module_charge_mw*x[b])
                m.addConstr(discharge[s,b,t] <= a.module_discharge_mw*x[b])
                m.addConstr(soc[s,b,t+1] == soc[s,b,t] + a.eta_charge*charge[s,b,t] - discharge[s,b,t]/a.eta_discharge)
            for q in Q: m.addConstr(soc[s,b,q] <= energy*x[b])
            m.addConstr(soc[s,b,0] == a.initial_soc_fraction*energy*x[b])
            m.addConstr(soc[s,b,len(H)] == a.terminal_soc_fraction*energy*x[b])
        for b in B:
            for t in H:
                storage = discharge[s,b,t]-charge[s,b,t] if b in C else 0
                m.addConstr(gp.quicksum(pg[s,g,t] for g in gb[b]) + renew[s,b,t] + storage
                            + gp.quicksum(flow[s,k,t] for k in incoming[b])
                            - gp.quicksum(flow[s,k,t] for k in outgoing[b])
                            + unserved[s,b,t] == float(d["demand"][s,t,bi[b]]))
    shed = gp.quicksum(d["probability"][s]*unserved[s,b,t] for s in S for b in B for t in H)
    thermal_obj = gp.quicksum(d["probability"][s]*pg[s,g,t] for s in S for g in G for t in H)
    production_cost_obj = gp.quicksum(
        d["probability"][s] * marginal_cost[g] * pg[s,g,t]
        for s in S for g in G for t in H
    ) + gp.quicksum(
        d["probability"][s] * a.renewable_variable_cost_per_mwh * renew[s,b,t]
        for s in S for b in B for t in H
    )
    throughput_obj = gp.quicksum(d["probability"][s]*(charge[s,b,t]+discharge[s,b,t]) for s in S for b in C for t in H)
    probability_scale = (
        1.0 / max(d["probability"].values())
        if a.level2_probability_scaling == "auto" else 1.0
    )
    shed_level2_solver = probability_scale * shed
    production_cost_level2_solver = probability_scale * production_cost_obj
    m.update()
    if a.write_model: m.write(str(a.output_dir / "lexicographic_model_before_caps.lp"))

    level_rows = []
    placement_rows = []
    status_names = {GRB.OPTIMAL:"OPTIMAL", GRB.TIME_LIMIT:"TIME_LIMIT", GRB.INTERRUPTED:"INTERRUPTED"}

    def solve_level(level, objective_name, expression, abs_gap, method, report_scale=1.0):
        m.setObjective(expression, GRB.MINIMIZE)
        m.Params.TimeLimit = a.time_limit_per_level
        m.Params.MIPGap = a.level_relative_gap
        m.Params.MIPGapAbs = abs_gap * report_scale
        m.Params.Method = method
        if level == 1:
            m.Params.NumericFocus = a.numeric_focus
            m.Params.ConcurrentMethod = a.level1_concurrent_method
            m.Params.ScaleFlag = -1
            m.Params.CrossoverBasis = -1
            m.Params.LPWarmStart = 0
            m.Params.BarHomogeneous = a.level1_bar_homogeneous
            m.Params.BarOrder = -1
            m.Params.BarCorrectors = -1
            m.Params.BarConvTol = 1e-8
            m.Params.Aggregate = 1
        elif level == 2:
            m.Params.NumericFocus = a.level2_numeric_focus
            m.Params.ConcurrentMethod = a.level2_concurrent_method
            m.Params.ScaleFlag = a.level2_scale_flag
            m.Params.CrossoverBasis = a.level2_crossover_basis
            m.Params.LPWarmStart = a.level2_lp_warm_start
            m.Params.BarHomogeneous = a.level2_bar_homogeneous
            m.Params.BarOrder = a.level2_bar_order
            m.Params.BarCorrectors = a.level2_bar_correctors
            m.Params.BarConvTol = a.level2_bar_conv_tol
            m.Params.Aggregate = a.level2_aggregate
        else:
            m.Params.NumericFocus = a.numeric_focus
            m.Params.ConcurrentMethod = -1
            m.Params.ScaleFlag = -1
            m.Params.CrossoverBasis = -1
            m.Params.LPWarmStart = 2
            m.Params.BarHomogeneous = -1
            m.Params.BarOrder = -1
            m.Params.BarCorrectors = -1
            m.Params.BarConvTol = 1e-8
            m.Params.Aggregate = 1
        m.update()
        stamp(
            f"LEVEL {level} start: {objective_name}; vars={m.NumVars:,}, "
            f"constraints={m.NumConstrs:,}, memory={mem_gib():.2f} GiB; "
            f"Method={method}, NumericFocus={m.Params.NumericFocus}, "
            f"ScaleFlag={m.Params.ScaleFlag}, CrossoverBasis={m.Params.CrossoverBasis}, "
            f"LPWarmStart={m.Params.LPWarmStart}, BarHomogeneous={m.Params.BarHomogeneous}, "
            f"BarOrder={m.Params.BarOrder}, BarCorrectors={m.Params.BarCorrectors}, "
            f"BarConvTol={m.Params.BarConvTol:.3g}, Aggregate={m.Params.Aggregate}, "
            f"objective_scale={report_scale:.12g}"
        )
        started = time.perf_counter(); m.optimize(); elapsed = time.perf_counter()-started
        if m.SolCount == 0:
            raise RuntimeError(f"Level {level} has no feasible incumbent; Gurobi status={m.Status}")
        incumbent_solver, bound_solver = float(m.ObjVal), float(m.ObjBound)
        incumbent, bound = incumbent_solver/report_scale, bound_solver/report_scale
        gap = max(0.0, incumbent-bound)
        if gap > abs_gap + 1e-5:
            raise RuntimeError(
                f"Level {level} did not certify its requested absolute gap: "
                f"{gap:.6f} > {abs_gap:.6f}; status={m.Status}"
            )
        level_rows.append(dict(
            level=level, objective_name=objective_name,
            incumbent=incumbent, best_bound=bound,
            absolute_gap=gap,
            relative_gap=float(m.MIPGap) if m.IsMIP else 0.0,
            solve_seconds=elapsed, status=int(m.Status),
            status_name=status_names.get(m.Status,str(m.Status)),
            method=method, solver_objective_scale=report_scale,
            solver_incumbent=incumbent_solver, solver_best_bound=bound_solver,
            modules_installed=sum(x[b].X for b in C),
        ))
        for b in C:
            placement_rows.append(dict(level=level, objective_name=objective_name,
                                       bus=b, modules=x[b].X))
        stamp(f"LEVEL {level} finished: incumbent={incumbent:.6f}, bound={bound:.6f}, gap={gap:.6f}, seconds={elapsed:.2f}")
        return incumbent, bound

    level1_value, level1_bound = solve_level(1, "expected_load_shed_mwh", shed, a.level1_abs_gap, a.level1_method)

    # Persist the certified Level-1 solution before starting Level 2.
    # This protects the primary reliability result if a later level
    # times out, fails numerically, or is interrupted.
    level1_checkpoint_path = Path(a.output_dir) / "level1_checkpoint.csv"
    level1_placement_checkpoint_path = (
        Path(a.output_dir) / "level1_placement_checkpoint.csv"
    )

    pd.DataFrame(
        [r for r in level_rows if r["level"] == 1]
    ).to_csv(
        level1_checkpoint_path,
        index=False,
    )

    pd.DataFrame(
        [r for r in placement_rows if r["level"] == 1]
    ).to_csv(
        level1_placement_checkpoint_path,
        index=False,
    )

    stamp(
        "LEVEL 1 checkpoint written: "
        f"{level1_checkpoint_path}; "
        f"{level1_placement_checkpoint_path}"
    )

    if a.stop_after_level1:
        stamp(
            "Stopping after Level 1 as requested; "
            "Level-1 checkpoint files have been preserved."
        )
        raise SystemExit(0)

    load_epsilon = (a.zero_load_cap_tolerance
                    if level1_value <= a.zero_load_threshold
                    else a.load_cap_feasibility_tolerance)
    load_cap = level1_value + load_epsilon
    stamp(
        f"LEVEL 2 scaling: factor={probability_scale:.12g}; "
        f"expected load cap={load_cap:.6f} MWh; "
        f"solver cap RHS={probability_scale*load_cap:.6f}"
    )
    load_cap_constr = m.addConstr(
        shed_level2_solver <= probability_scale*load_cap,
        name="lexicographic_load_shed_cap_scaled",
    )

    level2_value, level2_bound = solve_level(
        2, "expected_variable_production_cost_dollars", production_cost_level2_solver,
        a.level2_abs_gap_dollars, a.level2_method, report_scale=probability_scale,
    )
    production_cost_cap = level2_value + a.production_cost_cap_feasibility_tolerance_dollars

    # Capture the realized Level-2 scenario outcomes before changing the
    # objective.  Scenario caps preserve these outcomes independently during
    # throughput cleanup; expected caps preserve only their weighted totals.
    stage2_scenario = []
    stage2_shed = {}
    stage2_thermal = {}
    stage2_production_cost = {}
    for s in S:
        shed_s = float(sum(unserved[s,b,t].X for b in B for t in H))
        thermal_s = float(sum(pg[s,g,t].X for g in G for t in H))
        production_cost_s = float(
            sum(marginal_cost[g]*pg[s,g,t].X for g in G for t in H)
            + a.renewable_variable_cost_per_mwh*sum(renew[s,b,t].X for b in B for t in H)
        )
        ch_s = float(sum(charge[s,b,t].X for b in C for t in H))
        dc_s = float(sum(discharge[s,b,t].X for b in C for t in H))
        renewable_used_s = float(sum(renew[s,b,t].X for b in B for t in H))
        renewable_available_s = float(d["renewable"][s].sum())
        desired_shed_eps_s = (a.zero_load_cap_tolerance
                              if shed_s <= a.zero_load_threshold
                              else a.load_cap_feasibility_tolerance)
        stage2_shed[s] = shed_s
        stage2_thermal[s] = thermal_s
        stage2_production_cost[s] = production_cost_s
        stage2_scenario.append(dict(
            scenario=s,
            scenario_id=d["scenario_id"][s],
            conditional_probability=d["probability"][s],
            dispatch_level="level2",
            load_shed_mwh=shed_s,
            weighted_load_shed_mwh=d["probability"][s]*shed_s,
            renewable_available_mwh=renewable_available_s,
            renewable_used_mwh=renewable_used_s,
            renewable_curtailed_mwh=renewable_available_s-renewable_used_s,
            total_charge_mwh=ch_s,
            total_discharge_mwh=dc_s,
            battery_throughput_mwh=ch_s+dc_s,
            thermal_generation_mwh=thermal_s,
            weighted_thermal_generation_mwh=d["probability"][s]*thermal_s,
            variable_production_cost_dollars=production_cost_s,
            weighted_variable_production_cost_dollars=d["probability"][s]*production_cost_s,
            weighted_battery_throughput_mwh=d["probability"][s]*(ch_s+dc_s),
            soc_closure_residual_mwh=a.eta_charge*ch_s-dc_s/a.eta_discharge,
            simultaneous_rows=sum(
                charge[s,b,t].X > a.activity_tolerance
                and discharge[s,b,t].X > a.activity_tolerance
                for b in C for t in H
            ),
            stage2_load_shed_mwh=shed_s,
            desired_stage3_load_shed_tolerance_mwh=desired_shed_eps_s,
            stage2_thermal_generation_mwh=thermal_s,
            stage2_variable_production_cost_dollars=production_cost_s,
            stage3_production_cost_tolerance_dollars=a.production_cost_cap_feasibility_tolerance_dollars,
            stage3_production_cost_cap_dollars=production_cost_s + a.production_cost_cap_feasibility_tolerance_dollars,
        ))

    stage2_final_load = float(shed.getValue())
    stage2_final_thermal = float(thermal_obj.getValue())
    stage2_final_production_cost = float(production_cost_obj.getValue())
    stage2_final_throughput = float(throughput_obj.getValue())
    stage2_status = int(m.Status)
    stage2_status_name = status_names.get(m.Status, str(m.Status))

    def write_hourly_diagnostics(dispatch_level):
        """Write primal operating diagnostics for the current solved dispatch."""
        if not a.save_diagnostics:
            return

        prefix = dispatch_level
        tol = a.activity_tolerance
        active_threshold = a.diagnostic_active_threshold_mwh

        battery_hourly = []
        battery_summary = []
        bus_hourly = []
        line_hourly = []
        generator_hourly = []
        system_hourly = []

        installed = {b: float(x[b].X) for b in C if x[b].X > tol}

        gen_bus = {
            int(r["Gen Number"]): int(r["Bus Number"])
            for _, r in thermal.iterrows()
        }

        for s in S:
            sid = d["scenario_id"][s]

            for b, modules_b in installed.items():
                ch_total = 0.0
                dc_total = 0.0
                soc_values = []
                max_ch = 0.0
                max_dc = 0.0
                for t in H:
                    ch = float(charge[s,b,t].X)
                    dc = float(discharge[s,b,t].X)
                    soc0 = float(soc[s,b,t].X)
                    soc1 = float(soc[s,b,t+1].X)
                    ch_total += ch
                    dc_total += dc
                    max_ch = max(max_ch, ch)
                    max_dc = max(max_dc, dc)
                    soc_values.extend((soc0, soc1))
                    capacity_mwh = energy * modules_b
                    battery_hourly.append(dict(
                        dispatch_level=dispatch_level,
                        scenario=s, scenario_id=sid, hour=t, bus=b,
                        installed_modules=modules_b,
                        installed_power_mw=modules_b*a.module_power_mw,
                        installed_energy_mwh=capacity_mwh,
                        charge_mw=ch, discharge_mw=dc,
                        net_discharge_mw=dc-ch,
                        hourly_throughput_mwh=ch+dc,
                        soc_start_mwh=soc0, soc_end_mwh=soc1,
                        soc_start_fraction=(soc0/capacity_mwh if capacity_mwh > 0 else np.nan),
                        soc_end_fraction=(soc1/capacity_mwh if capacity_mwh > 0 else np.nan),
                        simultaneous_charge_discharge=bool(ch > tol and dc > tol),
                    ))
                throughput = ch_total + dc_total
                battery_summary.append(dict(
                    dispatch_level=dispatch_level,
                    scenario=s, scenario_id=sid, bus=b,
                    installed_modules=modules_b,
                    installed_power_mw=modules_b*a.module_power_mw,
                    installed_energy_mwh=modules_b*energy,
                    total_charge_mwh=ch_total,
                    total_discharge_mwh=dc_total,
                    battery_throughput_mwh=throughput,
                    active_threshold_mwh=active_threshold,
                    active=bool(throughput > active_threshold),
                    max_charge_mw=max_ch,
                    max_discharge_mw=max_dc,
                    min_soc_mwh=min(soc_values) if soc_values else np.nan,
                    max_soc_mwh=max(soc_values) if soc_values else np.nan,
                ))

            for t in H:
                sys_demand = 0.0
                sys_ren_avail = 0.0
                sys_ren_used = 0.0
                sys_shed = 0.0
                sys_thermal = 0.0
                sys_charge = 0.0
                sys_discharge = 0.0
                sys_cost = 0.0

                for b in B:
                    demand_bt = float(d["demand"][s,t,bi[b]])
                    ren_avail_bt = float(d["renewable"][s,t,bi[b]])
                    ren_used_bt = float(renew[s,b,t].X)
                    shed_bt = float(unserved[s,b,t].X)
                    thermal_bt = float(sum(pg[s,g,t].X for g in gb[b]))
                    ch_bt = float(charge[s,b,t].X) if b in C else 0.0
                    dc_bt = float(discharge[s,b,t].X) if b in C else 0.0
                    net_inflow_bt = float(
                        sum(flow[s,k,t].X for k in incoming[b])
                        - sum(flow[s,k,t].X for k in outgoing[b])
                    )
                    balance_residual = (
                        thermal_bt + ren_used_bt + (dc_bt-ch_bt)
                        + net_inflow_bt + shed_bt - demand_bt
                    )
                    bus_hourly.append(dict(
                        dispatch_level=dispatch_level,
                        scenario=s, scenario_id=sid, hour=t, bus=b,
                        demand_mw=demand_bt,
                        renewable_available_mw=ren_avail_bt,
                        renewable_used_mw=ren_used_bt,
                        renewable_curtailed_mw=ren_avail_bt-ren_used_bt,
                        unserved_load_mw=shed_bt,
                        thermal_generation_mw=thermal_bt,
                        installed_modules=installed.get(b, 0.0),
                        battery_charge_mw=ch_bt,
                        battery_discharge_mw=dc_bt,
                        battery_net_discharge_mw=dc_bt-ch_bt,
                        net_transmission_inflow_mw=net_inflow_bt,
                        power_balance_residual_mw=balance_residual,
                    ))
                    sys_demand += demand_bt
                    sys_ren_avail += ren_avail_bt
                    sys_ren_used += ren_used_bt
                    sys_shed += shed_bt
                    sys_thermal += thermal_bt
                    sys_charge += ch_bt
                    sys_discharge += dc_bt

                for k in K:
                    f = float(flow[s,k,t].X)
                    cap = float(capacity[k])
                    line_hourly.append(dict(
                        dispatch_level=dispatch_level,
                        scenario=s, scenario_id=sid, hour=t,
                        line_num=k, from_bus=fr[k], to_bus=to[k],
                        reactance_pu=float(reactance[k]),
                        capacity_mw=cap,
                        flow_mw=f,
                        abs_flow_mw=abs(f),
                        utilization_fraction=(abs(f)/cap if cap > 0 else np.nan),
                        utilization_pct=(100.0*abs(f)/cap if cap > 0 else np.nan),
                        remaining_capacity_mw=cap-abs(f),
                        at_capacity=bool(cap > 0 and cap-abs(f) <= max(1e-3, tol)),
                    ))

                for g in G:
                    p = float(pg[s,g,t].X)
                    c = float(marginal_cost[g])
                    generator_hourly.append(dict(
                        dispatch_level=dispatch_level,
                        scenario=s, scenario_id=sid, hour=t,
                        generator=g,
                        bus=gen_bus[g],
                        generation_mw=p,
                        pmin_mw=float(pmin[g]),
                        pmax_mw=float(pmax[g]),
                        marginal_cost_dollars_per_mwh=c,
                        variable_cost_dollars=p*c,
                    ))
                    sys_cost += p*c

                sys_cost += a.renewable_variable_cost_per_mwh * sys_ren_used
                system_hourly.append(dict(
                    dispatch_level=dispatch_level,
                    scenario=s, scenario_id=sid, hour=t,
                    demand_mw=sys_demand,
                    renewable_available_mw=sys_ren_avail,
                    renewable_used_mw=sys_ren_used,
                    renewable_curtailed_mw=sys_ren_avail-sys_ren_used,
                    load_shed_mw=sys_shed,
                    thermal_generation_mw=sys_thermal,
                    battery_charge_mw=sys_charge,
                    battery_discharge_mw=sys_discharge,
                    battery_net_discharge_mw=sys_discharge-sys_charge,
                    variable_production_cost_dollars=sys_cost,
                ))

        files = {
            f"{prefix}_battery_hourly.csv.gz": battery_hourly,
            f"{prefix}_battery_bus_summary.csv.gz": battery_summary,
            f"{prefix}_bus_hourly.csv.gz": bus_hourly,
            f"{prefix}_line_hourly.csv.gz": line_hourly,
            f"{prefix}_generator_hourly.csv.gz": generator_hourly,
            f"{prefix}_system_hourly.csv.gz": system_hourly,
        }
        for filename, records in files.items():
            pd.DataFrame(records).to_csv(
                a.output_dir / filename, index=False, compression="gzip"
            )

        manifest = {
            "dispatch_level": dispatch_level,
            "scenario_count": len(S),
            "candidate_count": len(C),
            "installed_bus_count": len(installed),
            "active_threshold_mwh": active_threshold,
            "activity_tolerance": tol,
            "files": list(files),
            "note": (
                "These are primal values from the current solved dispatch. "
                "The diagnostic writer does not change the optimization model."
            ),
        }
        (a.output_dir / f"{prefix}_diagnostic_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        stamp(
            f"{dispatch_level.upper()} diagnostics written: "
            f"{len(battery_summary)} battery-bus rows, "
            f"{len(bus_hourly)} bus-hour rows, "
            f"{len(line_hourly)} line-hour rows"
        )



    write_hourly_diagnostics("level2")

    if a.level3_cap_mode == "scenario":
        stage2_expected_shed = sum(
            d["probability"][item["scenario"]] * item["stage2_load_shed_mwh"]
            for item in stage2_scenario
        )
        available_expected_load_slack = max(0.0, load_cap - stage2_expected_shed)
        desired_expected_load_slack = sum(
            d["probability"][item["scenario"]]
            * item["desired_stage3_load_shed_tolerance_mwh"]
            for item in stage2_scenario
        )
        load_tolerance_scale = (
            min(1.0, available_expected_load_slack / desired_expected_load_slack)
            if desired_expected_load_slack > 0 else 0.0
        )
        for item in stage2_scenario:
            s = item["scenario"]
            shed_eps_s = (
                item["desired_stage3_load_shed_tolerance_mwh"]
                * load_tolerance_scale
            )
            item["stage3_load_shed_tolerance_mwh"] = shed_eps_s
            item["stage3_load_shed_cap_mwh"] = (
                item["stage2_load_shed_mwh"] + shed_eps_s
            )
            shed_s_expr = gp.quicksum(unserved[s,b,t] for b in B for t in H)
            production_cost_s_expr = (
                gp.quicksum(marginal_cost[g]*pg[s,g,t] for g in G for t in H)
                + gp.quicksum(a.renewable_variable_cost_per_mwh*renew[s,b,t] for b in B for t in H)
            )
            m.addConstr(
                shed_s_expr <= item["stage3_load_shed_cap_mwh"],
                name=f"stage3_scenario_load_cap[{s}]",
            )
            m.addConstr(
                production_cost_s_expr <= item["stage3_production_cost_cap_dollars"],
                name=f"stage3_scenario_production_cost_cap[{s}]",
            )
        # The weighted sum of the scenario caps is no larger than load_cap, so
        # the aggregate constraint is redundant. Removing it exposes independent
        # scenario blocks to presolve and the LP algorithm.
        m.remove(load_cap_constr)
    else:
        for item in stage2_scenario:
            item["stage3_load_shed_tolerance_mwh"] = load_epsilon
            item["stage3_load_shed_cap_mwh"] = item["stage2_load_shed_mwh"] + load_epsilon
        m.addConstr(
            production_cost_level2_solver <= probability_scale*production_cost_cap,
            name="lexicographic_production_cost_cap_scaled",
        )

    # Variable production cost may break primary-objective placement ties. Throughput
    # is only an operational cleanup criterion and therefore cannot move sites.
    stage2_placement = {b: int(round(x[b].X)) for b in C}
    for b in C:
        x[b].LB = stage2_placement[b]
        x[b].UB = stage2_placement[b]
        if a.run_level3 and not a.keep_stage3_integer_types:
            x[b].VType = GRB.CONTINUOUS
    m.update()

    # These compact files survive even if Level 3 is interrupted and provide
    # everything needed to audit or reconstruct the cleanup problem.
    pd.DataFrame(stage2_scenario).to_csv(
        a.output_dir / "stage2_scenario_caps_checkpoint.csv", index=False
    )
    pd.DataFrame([
        dict(bus=b, modules=stage2_placement[b]) for b in C
        if stage2_placement[b] > 0
    ]).to_csv(a.output_dir / "stage2_placement_checkpoint.csv", index=False)
    (a.output_dir / "stage2_checkpoint.json").write_text(json.dumps({
        "status": "stage2_complete",
        "level3_cap_mode": a.level3_cap_mode,
        "level1_incumbent_mwh": level1_value,
        "level1_bound_mwh": level1_bound,
        "level2_objective": "expected_variable_production_cost_dollars",
        "level2_incumbent_dollars": level2_value,
        "level2_bound_dollars": level2_bound,
        "level2_probability_scale": probability_scale,
        "candidate_count": len(C),
        "scenario_count": len(S),
        "placement": {str(b): value for b, value in stage2_placement.items() if value > 0},
        "level3_requested": bool(a.run_level3),
    }, indent=2), encoding="utf-8")


    def collect_dispatch_rows(dispatch_level):
        collected = []
        tol = a.activity_tolerance
        for s in S:
            scenario_shed = sum(unserved[s,b,t].X for b in B for t in H)
            ch = sum(charge[s,b,t].X for b in C for t in H)
            dc = sum(discharge[s,b,t].X for b in C for t in H)
            used = sum(renew[s,b,t].X for b in B for t in H)
            available = float(d["renewable"][s].sum())
            thermal_mwh = sum(pg[s,g,t].X for g in G for t in H)
            production_cost = (
                sum(marginal_cost[g]*pg[s,g,t].X for g in G for t in H)
                + a.renewable_variable_cost_per_mwh*sum(renew[s,b,t].X for b in B for t in H)
            )
            collected.append(dict(
                scenario=s, scenario_id=d["scenario_id"][s],
                conditional_probability=d["probability"][s],
                dispatch_level=dispatch_level,
                load_shed_mwh=scenario_shed,
                weighted_load_shed_mwh=d["probability"][s]*scenario_shed,
                renewable_available_mwh=available,
                renewable_used_mwh=used,
                renewable_curtailed_mwh=available-used,
                total_charge_mwh=ch, total_discharge_mwh=dc,
                battery_throughput_mwh=ch+dc,
                thermal_generation_mwh=thermal_mwh,
                weighted_thermal_generation_mwh=d["probability"][s]*thermal_mwh,
                variable_production_cost_dollars=production_cost,
                weighted_variable_production_cost_dollars=d["probability"][s]*production_cost,
                weighted_battery_throughput_mwh=d["probability"][s]*(ch+dc),
                soc_closure_residual_mwh=a.eta_charge*ch-dc/a.eta_discharge,
                simultaneous_rows=sum(
                    charge[s,b,t].X > tol and discharge[s,b,t].X > tol
                    for b in C for t in H
                ),
            ))
        return collected

    if not a.run_level3:
        rows = [dict(item) for item in stage2_scenario]
        final_load = stage2_final_load
        final_thermal = stage2_final_thermal
        final_production_cost = stage2_final_production_cost
        final_throughput = stage2_final_throughput
        tol = a.activity_tolerance
        placements = [
            {"bus": b, "modules": stage2_placement[b],
             "power_mw": stage2_placement[b]*a.module_power_mw,
             "energy_mwh": stage2_placement[b]*energy}
            for b in C if stage2_placement[b] > tol
        ]
        validations = dict(
            probability_sum=float(sum(d["probability"].values())),
            modules_installed=float(sum(stage2_placement.values())),
            maximum_placement_integrality_error=float(max(
                abs(stage2_placement[b]-round(stage2_placement[b])) for b in C
            )) if a.placement_domain == "integer" else 0.0,
            dispatch_level="level2",
            level3_executed=False,
            expected_load_shed_mwh=final_load,
            load_shed_cap_mwh=load_cap,
            load_shed_cap_residual_mwh=final_load-load_cap,
            expected_thermal_generation_mwh=final_thermal,
            expected_variable_production_cost_dollars=final_production_cost,
            expected_battery_throughput_mwh=final_throughput,
            maximum_abs_soc_closure_residual_mwh=float(max(
                abs(r["soc_closure_residual_mwh"]) for r in rows
            )),
            simultaneous_charge_discharge_rows=int(sum(
                r["simultaneous_rows"] for r in rows
            )),
        )
        validations["passed"] = bool(
            abs(validations["probability_sum"]-1.0) <= 1e-10
            and abs(validations["modules_installed"]-a.modules) <= 1e-6
            and validations["maximum_placement_integrality_error"] <= 1e-6
            and validations["load_shed_cap_residual_mwh"] <= 1e-3
            and validations["maximum_abs_soc_closure_residual_mwh"] <= 1e-4
        )
        if not validations["passed"]:
            raise RuntimeError(f"Level-2 final audit failed: {validations}")
        summary = dict(
            status=stage2_status,
            status_name=stage2_status_name,
            scenario_count=len(S), candidate_count=len(C),
            placement_domain=a.placement_domain,
            modules_installed=sum(stage2_placement.values()),
            final_dispatch_level="level2", level3_executed=False,
            expected_load_shed_mwh=final_load,
            expected_thermal_generation_mwh=final_thermal,
            expected_variable_production_cost_dollars=final_production_cost,
            expected_battery_throughput_mwh=final_throughput,
            level1_load_shed_incumbent_mwh=level1_value,
            level1_load_shed_bound_mwh=level1_bound,
            load_shed_cap_epsilon_mwh=load_epsilon,
            load_shed_cap_mwh=load_cap,
            level2_variable_production_cost_incumbent_dollars=level2_value,
            level2_variable_production_cost_bound_dollars=level2_bound,
            level2_probability_scale=probability_scale,
            placement_fixed_after_level=2,
            stage3_cap_mode="not_run",
            stage3_placement_types_relaxed=False,
            stage3_throughput_incumbent_mwh=None,
            stage3_throughput_bound_mwh=None,
            total_solve_seconds=sum(r["solve_seconds"] for r in level_rows),
            peak_memory_gib=mem_gib(), validation_passed=True,
        )
        stamp("STOPPING AFTER LEVEL 2 by default; use --run-level3 to opt in to cleanup")
        return summary, placements, rows, level_rows, placement_rows, validations, stage2_scenario

    level3_value, level3_bound = solve_level(3, "expected_battery_throughput_mwh", throughput_obj, a.level3_abs_gap, a.level3_method)
    write_hourly_diagnostics("level3")
    if a.write_model: m.write(str(a.output_dir / "lexicographic_model_final.lp"))

    tol = a.activity_tolerance
    placements = [{"bus":b,"modules":x[b].X,"power_mw":x[b].X*a.module_power_mw,"energy_mwh":x[b].X*energy} for b in C if x[b].X > tol]
    rows = collect_dispatch_rows("level3")
    final_load=float(shed.getValue()); final_thermal=float(thermal_obj.getValue()); final_production_cost=float(production_cost_obj.getValue()); final_throughput=float(throughput_obj.getValue())
    cap_lookup = {item["scenario"]: item for item in stage2_scenario}
    for row in rows:
        cap = cap_lookup[row["scenario"]]
        row["stage2_load_shed_mwh"] = cap["stage2_load_shed_mwh"]
        row["stage3_load_shed_cap_mwh"] = cap["stage3_load_shed_cap_mwh"]
        row["stage3_load_cap_residual_mwh"] = row["load_shed_mwh"] - cap["stage3_load_shed_cap_mwh"]
        row["stage2_thermal_generation_mwh"] = cap["stage2_thermal_generation_mwh"]
        row["stage2_variable_production_cost_dollars"] = cap["stage2_variable_production_cost_dollars"]
        row["stage3_production_cost_cap_dollars"] = cap["stage3_production_cost_cap_dollars"]
        row["stage3_production_cost_cap_residual_dollars"] = row["variable_production_cost_dollars"] - cap["stage3_production_cost_cap_dollars"]

    maximum_scenario_load_residual = float(max(
        row["stage3_load_cap_residual_mwh"] for row in rows
    ))
    maximum_scenario_production_cost_residual = float(max(
        row["stage3_production_cost_cap_residual_dollars"] for row in rows
    ))
    validations=dict(
        probability_sum=float(sum(d["probability"].values())),
        modules_installed=float(sum(x[b].X for b in C)),
        maximum_placement_integrality_error=float(max(abs(x[b].X-round(x[b].X)) for b in C)) if a.placement_domain=="integer" else 0.0,
        final_expected_load_shed_mwh=final_load,
        stage1_load_cap_epsilon_mwh=load_epsilon,
        load_shed_cap_mwh=load_cap,
        load_shed_cap_residual_mwh=final_load-load_cap,
        final_expected_thermal_generation_mwh=final_thermal,
        final_expected_variable_production_cost_dollars=final_production_cost,
        production_cost_cap_dollars=production_cost_cap,
        production_cost_cap_residual_dollars=final_production_cost-production_cost_cap,
        level3_cap_mode=a.level3_cap_mode,
        level3_executed=True,
        maximum_scenario_load_cap_residual_mwh=maximum_scenario_load_residual,
        maximum_scenario_production_cost_cap_residual_dollars=maximum_scenario_production_cost_residual,
        final_expected_battery_throughput_mwh=final_throughput,
        maximum_abs_soc_closure_residual_mwh=float(max(abs(r["soc_closure_residual_mwh"]) for r in rows)),
        simultaneous_charge_discharge_rows=int(sum(r["simultaneous_rows"] for r in rows)),
    )
    validations["passed"] = bool(
        abs(validations["probability_sum"]-1.0) <= 1e-10
        and abs(validations["modules_installed"]-a.modules) <= 1e-6
        and validations["maximum_placement_integrality_error"] <= 1e-6
        and validations["load_shed_cap_residual_mwh"] <= 1e-3
        and validations["production_cost_cap_residual_dollars"] <= 1e-3
        and (a.level3_cap_mode != "scenario" or maximum_scenario_load_residual <= 1e-3)
        and (a.level3_cap_mode != "scenario" or maximum_scenario_production_cost_residual <= 1e-3)
        and validations["maximum_abs_soc_closure_residual_mwh"] <= 1e-4
    )
    if not validations["passed"]:
        raise RuntimeError(f"Final lexicographic audit failed: {validations}")
    summary=dict(status=int(m.Status),status_name=status_names.get(m.Status,str(m.Status)),
                 scenario_count=len(S),candidate_count=len(C),placement_domain=a.placement_domain,
                 modules_installed=sum(x[b].X for b in C),
                 expected_load_shed_mwh=final_load,
                 expected_thermal_generation_mwh=final_thermal,
                 expected_variable_production_cost_dollars=final_production_cost,
                 expected_battery_throughput_mwh=final_throughput,
                 level1_load_shed_incumbent_mwh=level1_value,level1_load_shed_bound_mwh=level1_bound,
                 load_shed_cap_epsilon_mwh=load_epsilon,load_shed_cap_mwh=load_cap,
                 level2_variable_production_cost_incumbent_dollars=level2_value,level2_variable_production_cost_bound_dollars=level2_bound,
                 level2_probability_scale=probability_scale,
                 production_cost_cap_dollars=production_cost_cap,
                 level3_cap_mode=a.level3_cap_mode,
                 final_dispatch_level="level3",level3_executed=True,
                 placement_fixed_after_level=2,
                 stage3_placement_types_relaxed=not a.keep_stage3_integer_types,
                 level3_throughput_incumbent_mwh=level3_value,level3_throughput_bound_mwh=level3_bound,
                 total_solve_seconds=sum(r["solve_seconds"] for r in level_rows),
                 peak_memory_gib=mem_gib(),validation_passed=validations["passed"])
    return summary, placements, rows, level_rows, placement_rows, validations, stage2_scenario


def main():
    a=cli(); stamp("Loading inputs"); d=load_inputs(a); stamp("Building lexicographic extensive form")
    summary, placement, rows, stages, stage_placements, validations, stage2_scenario=build_and_solve(d,a)
    pd.DataFrame([summary]).to_csv(a.output_dir/"overall_summary.csv",index=False)
    pd.DataFrame(placement).to_csv(a.output_dir/"final_shared_storage_placement.csv",index=False)
    pd.DataFrame(rows).to_csv(a.output_dir/"scenario_summary.csv",index=False)
    pd.DataFrame(stages).to_csv(a.output_dir/"lexicographic_level_summary.csv",index=False)
    pd.DataFrame(stage_placements).to_csv(a.output_dir/"lexicographic_level_placements.csv",index=False)
    pd.DataFrame(stage2_scenario).to_csv(a.output_dir/"stage3_scenario_caps.csv",index=False)
    cost_audit = d["thermal"][["Gen Number", "Bus Number", "Fuel type", "Pmin (MW)", "Pmax (MW)", "C1($/MWh)"]].copy()
    cost_audit = cost_audit.rename(columns={"C1($/MWh)": "variable_cost_dollars_per_mwh"})
    cost_audit["dispatch_class"] = "dispatchable"
    cost_audit["included_in_level2"] = True
    cost_audit.to_csv(a.output_dir/"generator_variable_costs_used.csv", index=False)
    (a.output_dir/"validation_report.json").write_text(json.dumps(validations,indent=2),encoding="utf-8")
    manifest={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()}; manifest["gurobi_version"]=".".join(map(str,gp.gurobi.version())); manifest["input_sha256"]={k:sha256(v) for k,v in d["paths"].items()}
    manifest["code_lineage"] = "tx123bt_gurobi_lexicographic_v6.py -> tx123bt_gurobi_lexicographic_v7.py -> tx123bt_gurobi_lexicographic_v7_1.py -> tx123bt_gurobi_lexicographic_v7_2.py"
    manifest["formulation_parity_options"] = {
        "thermal_pmin_enforced": bool(a.thermal_pmin),
        "thermal_pmin_column": "Pmin (MW)",
        "phase_angle_bound_enabled": bool(a.phase_angle_bound_radians > 0),
        "phase_angle_bound_radians": a.phase_angle_bound_radians,
    }
    manifest["level2_cost_definition"] = {
        "dispatchable_generator_variable_cost_column": "C1($/MWh)",
        "excluded_columns": ["C0($/MWh)", "Csu($)"],
        "renewable_variable_cost_dollars_per_mwh": a.renewable_variable_cost_per_mwh,
        "time_step_hours": 1.0,
    }
    (a.output_dir/"run_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2)); print(pd.DataFrame(placement).to_string(index=False)); stamp(f"Saved {a.output_dir}")


if __name__ == "__main__":
    main()
