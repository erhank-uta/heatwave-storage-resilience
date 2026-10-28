#!/usr/bin/env python3
"""Update publication documentation in heatwave-storage-resilience.
Backs up overwritten files. Does not modify LICENSE, Git, or remote repositories.
"""
from pathlib import Path
from datetime import datetime
import shutil
import sys

root = Path(__file__).resolve().parent
if not (root / 'tx123bt_gurobi_lexicographic_v7_4.py').exists():
    sys.exit('Place this script at the root of heatwave-storage-resilience and rerun.')
backup = root / 'docs' / 'local_doc_backups'
backup.mkdir(parents=True, exist_ok=True)

def put(relative, content):
    p = root / relative
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = backup / (p.name + '.' + stamp + '.bak')
        shutil.copy2(p, dest)
        print('Backup:', dest.relative_to(root))
    p.write_text(content.strip() + '\n', encoding='utf-8')
    print('Updated:', relative)

put('README.md', '''# Heatwave Storage Resilience

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
''')

put('docs/DATA_PROVENANCE.md', '''# Data provenance and third-party materials

This package distributes selected processed inputs for reproduction of the
optimization experiments, not the full upstream meteorological pipeline.

## TX123-BT synthetic power network

The network input files in `data/TX123BT/` are derived from the TX123-BT
synthetic transmission-grid release. Attribute the original dataset and its
associated publication. Verify the applicable CC BY 4.0 notice and any
additional terms on the specific version used before public release.

- Source/project: https://rpglab.github.io/resources/TX123BT/
- Associated publication DOI: https://doi.org/10.1016/j.segan.2025.101774
- License reference: https://creativecommons.org/licenses/by/4.0/

These input files are included for convenience; they are not claimed as
originally authored network data. Any preprocessing and deviations from the
original release should be described in the paper and/or supplemental methods.

## AORC weather data

NOAA Analysis of Record for Calibration (AORC) supplied upstream meteorological
information. The raw AORC data are not included here; researchers should obtain
them from NOAA's authoritative distribution. Cite the AORC documentation and
associated methodological paper (Fall et al., 2023).

- NOAA AORC: https://registry.opendata.aws/noaa-nws-aorc/
- Publication DOI: https://doi.org/10.1111/1752-1688.13143

The synthetic scenario data are not unmodified NOAA observations and should
not be represented as NOAA-endorsed outputs.

## IBMWeatherGen and subsequent scenario processing

The research workflow used weather-generation methods associated with
IBMWeatherGen, together with project-specific scenario selection and
load/renewable transformations. Do not conflate the upstream IBM software
with the complete customized V6_B pipeline used in this study.

- Software: https://github.com/IBM/IBMWeatherGen
- Associated methodology DOI: https://doi.org/10.1029/2022MS003542

The IBMWeatherGen source repository provides its own license and version
history. It is not redistributed in this repository.

## Included scenario products

- `optimization_input_primary_23_strict_hybrid.npz`: strict23 hourly bus loads.
- `optimization_input_primary_23_strict_renewables.npz`: strict23 hourly bus renewable availability.
- `optimization_input_expanded_48_hybrid.npz`: expanded48 hourly bus loads.
- `optimization_input_expanded_48_renewables.npz`: expanded48 hourly bus renewable availability.
- `mean_strict23_loads.npz` and `mean_strict23_renewables.npz`: probability-weighted mean inputs.
- `strict23_bus_daily_weather.parquet` and `expanded48_bus_daily_weather.parquet`: selected bus-level daily weather context.
- `v6b_100_regional_daily_tmax.parquet`: compact regional-temperature diagnostic, not the complete ensemble.

Scenario selection is described in the manuscript. The expanded48 population
contains all 23 strict scenarios plus 25 supplemental near-heat-wave scenarios.
The optimization inputs are indexed by scenario, hour, and bus.

## Reproducibility limits and release checks

The processed scenario inputs support rerunning the optimization, but do not
independently reproduce all weather-generation, load-model fitting, or
renewable-model estimation stages. Exact historical training data, scripts,
configuration and seeds should be requested from the authors if not published.

Before making this repository public, confirm: (1) redistribution terms for
these exact TX123-BT files, (2) permission to release the processed scenario
products, (3) source citations and upstream version identifiers, and (4) the
copyright holder and license for original optimization code.
''')

put('CITATION.cff', '''cff-version: 1.2.0
message: "If you use this software, please cite this repository and the associated research paper when available."
title: "Heatwave Storage Resilience: Stochastic Storage Planning Reproducibility Code"
type: software
authors:
  - family-names: Kutanoglu
    given-names: Erhan
repository-code: "https://github.com/erhank-uta/heatwave-storage-resilience"
keywords:
  - stochastic optimization
  - power system resilience
  - energy storage
  - heat waves
  - transmission networks
''')

put('docs/PUBLISHING_CHECKLIST.md', '''# Checklist before switching the repository to Public

- [ ] Confirm UT Austin ownership/open-source release authorization for the original software; select the appropriate copyright notice and license.
- [ ] Confirm TX123-BT file-specific redistribution terms and attribution.
- [ ] Confirm processed scenario data can be publicly redistributed.
- [ ] Verify source citations and version information for TX123-BT, AORC, and IBMWeatherGen.
- [ ] Review the software author in `CITATION.cff`; add final paper citation when available.
- [ ] Ensure `.gitignore` excludes `private/`, `.venv/`, `results/`, and credentials.
- [ ] Inspect `git status` and staged changes; do not publish logs containing Gurobi WLS details.
- [ ] Confirm reproduction wrappers and README accurately distinguish tested and untested runs.
- [ ] Push documentation changes to the **private** GitHub repository.
- [ ] After approvals, add `LICENSE`, commit, and make repository public.
- [ ] Optionally tag v1.0.0 and archive through Zenodo or a university repository for a DOI.
''')

print('\nDocumentation generated. No LICENSE, Git commit, push, or public release performed.')
print('Backups are in docs/local_doc_backups/; do not commit those backups.')
