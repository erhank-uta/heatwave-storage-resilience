# Data licenses and attribution

This repository uses **different licenses for software and data**.

| Material | License / treatment |
|---|---|
| Original Python optimization code and experiment scripts | [MIT License](../LICENSE), copyright (c) 2026 Erhan Kutanoglu |
| Author-generated synthetic heat-wave scenarios and derived hourly bus-level load and renewable-availability datasets under `data/AORC_TX123BT/` | [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/), to the extent the authors hold licensing rights |
| Original TX123-BT network inputs under `data/TX123BT/` | Original TX123-BT license (CC BY 4.0); retain source attribution and any applicable notices |
| IBMWeatherGen software | Not redistributed here; refer to its upstream repository and license |
| Historical AORC meteorological data | Not redistributed here; cite the original NOAA source |
| Gurobi solver | Not distributed or licensed by this repository; users must obtain their own license |

## Attribution for the processed scenario datasets

When using the author-generated scenario data, cite:

B. Bilir, E. Kutanoglu, J. J. Hasenbein, and J. K. Skolfield,
*A Data-Driven Approach to Enhancing Grid Resilience to Heatwaves with Optimal
Deployment of Grid-level Energy Storage Systems*,
manuscript under revision for *Energy*.

Please also cite the upstream TX123-BT, AORC, and IBMWeatherGen sources as
appropriate; see [DATA_PROVENANCE.md](DATA_PROVENANCE.md).

Under CC BY 4.0, give appropriate credit, provide a link to the license,
and indicate if changes were made. This license does not require that
adaptations be distributed under the same license.

The MIT license in the repository root applies to original software, **not
automatically to third-party data**. This document does not relicense any
third-party material or override applicable upstream terms.

## Scope of the data release

The repository provides selected synthetic weather and processed optimization
inputs, not the complete upstream AORC dataset or the 100-member weather
simulation ensemble. Refer to the provenance documentation for details.
