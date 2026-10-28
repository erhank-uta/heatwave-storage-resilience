#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

python code/expanded48/expanded48_freeze_after_level1_v74.py \
  --drive-root data \
  --scenario-set expanded48 \
  --scenarios all \
  --candidate-buses all \
  --placement-domain integer \
  --budget-sense exact \
  --modules 40 \
  --max-modules-per-bus 0 \
  --duration-hours 4 \
  --threads 0 \
  --time-limit-per-level 7200 \
  --level1-method 3 \
  --level1-abs-gap 1 \
  --numeric-focus 1 \
  --level1-bar-homogeneous -1 \
  --level2-method 2 \
  --level2-bar-homogeneous 1 \
  --level2-numeric-focus 2 \
  --level2-scale-flag 2 \
  --level2-aggregate 0 \
  --level2-abs-gap-dollars 10000 \
  --solver-log \
  --output-dir results/expanded48_m40_d4_reproduction
