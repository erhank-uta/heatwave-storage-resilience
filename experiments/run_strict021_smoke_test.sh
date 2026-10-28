#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results
python tx123bt_gurobi_lexicographic_v7_4.py \
  --drive-root data \
  --scenario-set primary23 \
  --scenarios 20 \
  --candidate-buses all \
  --placement-domain integer \
  --budget-sense exact \
  --modules 40 \
  --max-modules-per-bus 0 \
  --duration-hours 4 \
  --threads 0 \
  --time-limit-per-level 28800 \
  --level1-method 3 \
  --level1-abs-gap 1 \
  --level2-method 2 \
  --level2-bar-homogeneous 1 \
  --level2-numeric-focus 3 \
  --level2-scale-flag 2 \
  --level2-aggregate 0 \
  --level2-abs-gap-dollars 10000 \
  --solver-log \
  --output-dir results/repository_smoke_test_strict021
