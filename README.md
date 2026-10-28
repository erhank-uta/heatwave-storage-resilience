# Heatwave Storage Resilience

Reproduction package for stochastic transmission-level energy-storage planning
under heat-wave scenarios using the TX123-BT synthetic power system.

## Scope

This repository includes the authoritative V7.4 optimization implementation and
processed inputs for the **strict23** and **expanded48** scenario sets. It supports
reproduction of optimization experiments from these processed scenarios. It does
**not** reproduce the entire upstream AORC-to-weather-generator pipeline or include
the complete 100-member synthetic weather ensemble.

The included NPZ files contain hourly bus-level loads and renewable availability.
Selected bus-level daily weather files are provided for provenance and
temperature-derating sensitivity.

## Requirements

- Python environment with the packages in `requirements.txt`
- A separately obtained, valid Gurobi license (not distributed here)
- Sufficient memory and runtime for large 23- and 48-scenario runs

Tested on macOS Apple M2 Max with Python dependencies including Gurobi 13.0.3.
Solver results and runtime can vary by hardware, version, and numerical settings.

## Quick start

```bash
python -m pip install -r requirements.txt
python tx123bt_gurobi_lexicographic_v7_4.py --help
bash experiments/run_strict021_smoke_test.sh
```

For full multi-scenario experiments, see `experiments/README.md`.

## Input data

The `data/TX123BT/` directory contains the network inputs used by the model.
The scenario files retain the original relative paths expected by V7.4.
See `docs/DATA_PROVENANCE.md` and `docs/file_inventory.csv`.

## Reproducibility boundary

Prepared strict23/expanded48 loads and renewable availability are provided;
upstream TX123-BT and AORC datasets and the weather-generation software should
be obtained from their respective original sources. Full bibliographic citations,
source URLs, and redistribution terms must be verified and completed before release.

## Licensing and citation

**Pending before public release:** verify redistribution rights for TX123-BT
network files and generated scenario data; choose and add an appropriate LICENSE
for original code; complete CITATION.cff with the paper's authors and citation.
Do not publish Gurobi license files or WLS credentials.
