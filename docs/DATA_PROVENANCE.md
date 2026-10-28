# Data provenance and boundaries

1. **Network:** TX123-BT synthetic transmission system. Included network inputs
   are the exact files used by the V7.4 optimization. Add authoritative source
   citation, URL, version and redistribution permission before publication.
2. **Weather:** AORC meteorological inputs were used in the upstream scenario
   generation workflow. Raw AORC files are not redistributed here.
3. **Weather generation:** The research workflow used a V6_B weather generator
   and selection pipeline associated with IBM WeatherGen work. The exact
   implementation/provenance and citation must be documented; the full generator
   and 100-member ensemble are not included.
4. **Scenario selection:** The primary set has 23 strict heat-wave scenarios;
   the expanded set has 48 (23 strict plus 25 near/supplemental).
5. **Optimization inputs:** NPZ files provide scenario-by-hour-by-bus loads and
   renewable available generation. The mean strict23 NPZ files support the
   deterministic expected-value benchmark.
6. **Temperature sensitivity:** Selected daily bus weather files support the
   endpoint daily-Tmax transmission derating sensitivity.

## Reproduction scope

Optimization results can be reproduced from the processed files in this repository.
Reconstruction of all inputs from raw meteorological data requires additional
upstream datasets and code not bundled in this release.

## Before public release

- Confirm TX123-BT redistribution terms and attribution.
- Add AORC and IBM WeatherGen primary citations and version identifiers.
- Document exact generation seeds, processing versions and scenario selection
  rules from the research records.
- Confirm whether all distributed processed data may be openly redistributed.
