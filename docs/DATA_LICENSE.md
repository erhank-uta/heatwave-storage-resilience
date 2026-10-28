# Data licensing and attribution

This repository combines original research software with third-party network
inputs and processed research scenario datasets. The root `LICENSE` grants the
MIT License to the original software authored for this repository; it does
**not** relicense third-party data, upstream software, or proprietary solvers.

## TX123-BT network data

The included `data/TX123BT/` files derive from the TX123-BT synthetic power
system. The original TX123-BT distribution identifies its dataset license as
Creative Commons Attribution 4.0 (CC BY 4.0). Attribute the original dataset,
link to its source and license, and identify adaptations. Verify that the
particular copied files are covered by those terms.

Original source: https://rpglab.github.io/resources/TX123BT/
License: https://creativecommons.org/licenses/by/4.0/

## Weather and scenario data

The bundled NPZ and selected-week Parquet files are processed research outputs
from a workflow using AORC meteorological data and a weather-generation and
scenario-selection pipeline. These are not unmodified AORC observations. They
are distributed for reproducibility of the associated optimization experiments;
no separate open-data license is asserted here pending confirmation of the
applicable rights and upstream conditions.

AORC source: https://registry.opendata.aws/noaa-nws-aorc/
IBM WeatherGen software: https://github.com/IBM/IBMWeatherGen

The full AORC source archive and the 100-member weather ensemble are not
included. See `docs/DATA_PROVENANCE.md` for methodological context and
bibliographic attribution.

## Dependencies

Gurobi is a separately licensed proprietary solver. A valid Gurobi license is
required to run the optimization; no license or credentials are distributed.
