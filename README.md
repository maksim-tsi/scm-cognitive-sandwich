# Cognitive Sandwich research artifacts

## Latest study: evidence-aware verification in urban freight

The latest research package supports **A Reproducible Research Methodology for
LLM-Based Logistics Decision Support: Lessons from Urban Freight Experiments**,
by Maksim Ilin and Dmitry Pavlyuk. **Status: manuscript prepared for Systems;
not a published or accepted journal article.**

Start with [the Systems study](studies/2026-systems-urban-freight/README.md).
It contains authored synthetic scenarios and references, source-qualified textual
site observations, prompts, controller/verifier/provider code, recorded outcomes,
selected final responses and offline reproduction instructions.

Two independently runnable levels require **no LLM API, HomeLab or private LTX**:
reproduction of reported numerical results and deterministic I2/I3 replay of the
original proposals and acquired evidence. New LLM collection is a separate level,
not executed by reproduction and not expected to reproduce identical generations.

```sh
python3.13 -m venv .venv-systems
.venv-systems/bin/python -m pip install -r studies/2026-systems-urban-freight/reproduction/requirements-lock.txt
.venv-systems/bin/python studies/2026-systems-urban-freight/reproduction/reproduce.py --output /tmp/systems-reproduction
```

Dependency installation may use a package index. The reproduction command blocks
network connections and uses only this checkout. See study instructions for tests,
reference provenance, licensing and the independent clean-copy verification record.

## Research development and publication-specific entry points

| Research phase | Scope and evidence | Publication status | Entry point |
| --- | --- | --- | --- |
| IDWL 2026, pre-workshop source anchor 31 May | Four-port maritime implementation; 100 generated inputs, 78 main result rows and a separate 66-run Variant B batch | Published antecedent, DOI [10.25673/123541](https://doi.org/10.25673/123541) | [IDWL](studies/2026-idwl/README.md) |
| Maritime extension, August–September 2026, subsequent development separate | 60 incidents; paired repair/verification analysis and retained simulation output | Research extension; associated manuscript not claimed accepted or published | [Maritime extension](studies/2026-maritime-extension/README.md) |
| Urban freight, October 2026 | EVAL30; separately collected Luna extension; EVAL-OP-V2-R1 with 16 enriched assignments and six matched controls per arm | Systems manuscript | [Systems package](studies/2026-systems-urban-freight/README.md) |

These are different experiments. Their results and denominators are not pooled.
Study directories contain separate citation records and source/export manifests.
Final publication releases/tags require author approval; none is created by this PR.

## Historical code and compatibility

Root `src/`, `scripts/`, `data/`, `tests/` and `docs/` retain their historical paths.
The [legacy quick start](docs/legacy-maritime-quickstart.md) and
[architecture documentation](docs/architecture/index.md) describe the maritime
implementation. Its YAAM/sandbox requirements do not govern new study packages.
See [AGENTS.md](AGENTS.md) for scope-specific maintenance instructions.

## Data, rights and citation

The original Padua dataset is a third-party source: [Cappi et al., archived
record](https://doi.org/10.5281/zenodo.22111450). This repository does not claim
its collection or redistribute it as author-generated observations.
The Systems package distinguishes authored synthetic premises from geographical
inputs and historical visual interpretations. No Google Street View images are
included in that package. Original requests, full technical traces, secrets and
private manuscript/editorial materials are excluded from new study exports.

Use the citation record for the study you actually use. See each study's rights
notice; the root MIT license does not replace third-party data licenses.
