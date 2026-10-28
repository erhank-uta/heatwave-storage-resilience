#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

MODULES="${1:-40}"
DURATION="${2:-4}"

case "${MODULES}x${DURATION}" in
  40x4|40x8|80x4|80x8)
    ;;
  *)
    echo "Supported configurations: 40x4, 40x8, 80x4, 80x8"
    exit 1
    ;;
esac

MODEL="code/temperature_derating/tx123bt_gurobi_lexicographic_v7_4_shared_strict23_all123_m${MODULES}_d${DURATION}_pcm_v7_4_tempderate30_beta1pct_floor80.py"

python "$MODEL" \
  --drive-root data \
  --scenario-set primary23 \
  --scenarios all \
  --candidate-buses all \
  --placement-domain integer \
  --budget-sense exact \
  --modules "$MODULES" \
  --max-modules-per-bus 0 \
  --duration-hours "$DURATION" \
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
  --output-dir "results/tempderate_m${MODULES}_d${DURATION}_reproduction"
