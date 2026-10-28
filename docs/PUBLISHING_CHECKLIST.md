# Checklist before switching the repository to Public

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
