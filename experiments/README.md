# Reproduction experiments

Run scripts from the repository root. Outputs go into ignored `results/` folders.
These scripts preserve the principal V7.4 solver settings used in the paper.

- `run_strict021_smoke_test.sh`: one scenario (zero-based index 20), quick check.
- `run_strict23_baseline.sh`: primary 23-scenario 40-module, 4-hour model.
- `run_expanded48_40x4.sh`: expanded 48-scenario 40-module, 4-hour model.
- `run_eev_fixed.sh`: strict23 evaluation with the previously computed mean
  scenario EV placement fixed.

The expanded48 experiment uses the original freeze-after-Level-1 implementation. Temperature-dependent transmission-capacity experiments are available for 40×4, 40×8, 80×4, and 80×8 storage configurations. The specialized models have been syntax-checked and their weather-data paths made portable. Full optimization reproductions of these larger experiments have not been rerun from the public package. Perfect-information experiments use the standard V7.4 model with a single scenario selected.

## Perfect-information (wait-and-see) evaluation

The same V7.4 model is used for stochastic and single-scenario planning.
For example, to optimize storage placement knowing STRICT_001 in advance:

```bash
python tx123bt_gurobi_lexicographic_v7_4.py \
  --drive-root data --scenario-set primary23 --scenarios 0 \
  --candidate-buses all --placement-domain integer \
  --budget-sense exact --modules 40 --max-modules-per-bus 0 \
  --duration-hours 4 --threads 0 --time-limit-per-level 28800 \
  --level1-method 3 --level1-abs-gap 1 \
  --level2-method 2 --level2-bar-homogeneous 1 \
  --level2-numeric-focus 3 --level2-scale-flag 2 \
  --level2-aggregate 0 --level2-abs-gap-dollars 10000 \
  --output-dir results/pi_strict001
```

Use `--scenarios 0` through `22` for the 23 strict scenarios.
For the 48-scenario input, use `--scenario-set expanded48` and
`--scenarios 0` through `47`. Each run optimizes its own first-stage placement.
Read the **Level-1 incumbent** from `lexicographic_level_summary.csv`.
For each scenario set, obtain the probabilities from its supplied load NPZ
(`probability` array); normalize them over the included scenarios as the model
itself does. Then calculate

`WS = sum_s p_s * PI_Level1_s` and `EVPI = RP_Level1 - WS`,

where `RP_Level1` is from the corresponding shared stochastic run.
Do not use Level-2 cost to calculate reliability EVPI. Check all scenarios
were solved and their validation reports passed before aggregating.
Historical PI runs used earlier V7.x implementations; small numerical or
placement differences can occur with V7.4 or other solver versions.

## Published benchmark values (MWh, rounded)

| Scenario set | WS | RP | EVPI |
|---|---:|---:|---:|
| strict23 | 5098.923 | 5116.489 | 17.566 |
| expanded48 | 2762.963 | 2774.988 | 12.025 |

These are reference results from the research runs, not automatically
recomputed by this repository setup.
