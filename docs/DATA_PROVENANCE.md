# Data provenance and third-party materials

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

<!-- BEGIN ASSOCIATED PAPER -->
## Associated research publication

B. Bilir, E. Kutanoglu, J. J. Hasenbein, and J. K. Skolfield, *A Data-Driven Approach to Enhancing Grid Resilience to Heatwaves with Optimal Deployment of Grid-level Energy Storage Systems*. Revision under review for **Energy** (unpublished).

This repository provides code and processed scenario inputs supporting the manuscript.
<!-- END ASSOCIATED PAPER -->
