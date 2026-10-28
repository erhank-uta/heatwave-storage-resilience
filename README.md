# Heatwave Storage Resilience

Research reproducibility package for transmission-level battery energy-storage
placement under multiday heat-wave uncertainty on the synthetic TX123-BT network.

**Software author:** Erhan Kutanoglu  
**Repository:** https://github.com/erhank-uta/heatwave-storage-resilience

## What this repository reproduces

The package provides the V7.4 two-stage stochastic optimization model and
processed scenario inputs for the 23 strict heat-wave scenarios (`primary23`)
and the expanded 48-scenario set (`expanded48`, comprising the 23 strict and 25
supplemental near-heat-wave scenarios). The inputs contain 168 hourly periods
and 123 buses. Storage locations and module counts are common to all scenarios;
operations are scenario-specific. The model minimizes expected unserved energy
first and expected thermal production cost second.

The repository includes the single-scenario/PI interface, the mean-scenario
inputs, a freeze-after-Level-1 expanded48 implementation, and four
weather-dependent transmission-derating variants. See
[experiment instructions](experiments/README.md).

**Reproducibility boundary:** The supplied processed scenario files allow the
optimization experiments to be rerun without regenerating the underlying
weather ensemble. Raw AORC observations, the complete 100-member weather
ensemble, and the full upstream weather-to-load/renewables pipeline are not
included. See [data provenance](docs/DATA_PROVENANCE.md).

## Setup

Python dependencies are listed in `requirements.txt`. A separate, valid
[Gurobi](https://www.gurobi.com/) license is required; no license or
credentials are distributed. Install dependencies in a virtual environment:

```bash
python -m pip install -r requirements.txt
python tx123bt_gurobi_lexicographic_v7_4.py --help
```

The package was smoke-tested on an Apple M2 Max with Gurobi 13.0.3. The
single-scenario STRICT_021 (zero-based scenario index 20) run reproduced zero
Level-1 load shedding and approximately $202.075 million in Level-2 production
cost, with model validation passing:

```bash
bash experiments/run_strict021_smoke_test.sh
```

## Main experiments

```bash
bash experiments/run_strict23_baseline.sh
bash experiments/run_expanded48_40x4.sh
bash experiments/run_temperature_derating.sh 40 4
```

These multi-scenario runs can require substantial RAM and computation time.
The expanded48 wrapper uses the historical freeze-after-Level-1 model rather
than the ordinary V7.4 second-stage placement optimization. The derating
variant applies a 1% per degree C reduction above 30 C, floored at 80%,
using the maximum endpoint-bus daily Tmax repeated over 24 hours.

For perfect-information evaluation, run the main V7.4 model with one scenario
index at a time. Details, solver options, and published reference WS/EVPI
values appear in [experiments/README.md](experiments/README.md).

## Files

- `tx123bt_gurobi_lexicographic_v7_4.py`: core stochastic optimization.
- `code/expanded48/`: exact freeze-after-Level-1 variant.
- `code/temperature_derating/`: weather-dependent line-capacity variants.
- `data/TX123BT/`: network input files.
- `data/AORC_TX123BT/.../`: processed load, renewable, and selected weather files.
- `experiments/`: reproduction commands and methodological notes.
- `docs/`: provenance and file checksums.

## Upstream sources and attribution

This work builds on the TX123-BT synthetic grid, NOAA's Analysis of Record for
Calibration (AORC) weather data, and research associated with IBMWeatherGen.
The source URLs and methodological distinctions are documented in
[docs/DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md). These upstream works should
be cited independently of this repository.

## Citation and licensing

Use the GitHub citation metadata in `CITATION.cff` to cite the software. The
paper's full bibliographic information will be added when finalized.

**License review pending:** No license is granted for original code merely by
making the repository accessible. An MIT license for the original code is
proposed, subject to confirmation of the copyright holder and UT Austin's
software-release requirements. Upstream datasets and third-party software
retain their respective terms. Do not make the repository public until this
review and the data redistribution checks are complete.

<!-- BEGIN ASSOCIATED PAPER -->
## Associated publication

B. Bilir, E. Kutanoglu, J. J. Hasenbein, and J. K. Skolfield, *A Data-Driven Approach to Enhancing Grid Resilience to Heatwaves with Optimal Deployment of Grid-level Energy Storage Systems*. Revision under review for **Energy** (unpublished).

This repository provides code and processed scenario inputs supporting the manuscript.
<!-- END ASSOCIATED PAPER -->

## Licensing

Original Python optimization code and experiment scripts are released under
the [MIT License](LICENSE) (copyright (c) 2026 Erhan Kutanoglu).
Author-generated synthetic heat-wave scenarios and derived load/renewable
datasets are released under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), to the extent
the authors hold the relevant rights. The included TX123-BT network inputs
retain their original license and attribution requirements. See
[Data licenses and attribution](docs/DATA_LICENSE.md) and
[Data provenance](docs/DATA_PROVENANCE.md) for details.

