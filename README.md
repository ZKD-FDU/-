# HongCe

洪策：基于真实灾害事故调查报告训练素材的极端事件人员转移与协同治理多智能体政策推演系统。

Current status: runnable competition MVP. The system includes a deterministic
simulation kernel, S0-S5 policies, A/B/C batch experiments, HTTP API, seven-page
frontend workbench, a 28-case emergency-report training corpus, tests, and
delivery documents. It runs without external model keys; policy comparisons are
produced from actual simulation runs.

## Local Commands

```bash
PYTHONPATH=src python3 -m hongce.cli generate-scenario --population 2000
PYTHONPATH=src python3 -m hongce.cli run --policy S5 --seed 20260806 --population 2000 --out-dir outputs/demo
PYTHONPATH=src python3 -m hongce.cli batch --policies S0,S3,S5 --seeds 202608060:202608110 --population 2000 --out-dir outputs/experiments
PYTHONPATH=src python3 -m hongce.cli experiments --seeds 202608060:202608110 --population 2000 --out-dir outputs/experiments
PYTHONPATH=src python3 -m hongce.cli explain --policy S5 --seed 20260806 --population 2000 --out-dir outputs/demo
PYTHONPATH=src python3 -m unittest discover -s tests
```

## API And Frontend

One-command local launcher:

```bash
python3 -m pip install -r requirements.txt
python3 scripts/start_hongce.py
```

Then open `http://127.0.0.1:5173`.

Terminal A:

```bash
PYTHONPATH=src python3 -m api.simple_server
```

Terminal B:

```bash
cd web
python3 -m http.server 5173 --bind 127.0.0.1
```

Open `http://127.0.0.1:5173`. The frontend calls the API to run simulations,
fetch event streams and individual traces, and execute A/B/C policy experiments.

API endpoints:

- `GET /health`
- `GET /cases`
- `GET /cases/{case_id}`
- `GET /cases/{case_id}/scenario`
- `POST /scenarios/validate`
- `GET /spatial/package?path=data/spatial/qingyuan`
- `POST /spatial/derive-scenario`
- `POST /simulations/run`
- `GET /simulations/{run_id}`
- `GET /simulations/{run_id}/events`
- `GET /simulations/{run_id}/agents/{agent_id}/trace`
- `POST /experiments/run`
- `GET /experiments/{experiment_id}/comparison`

## Boundaries

- `FACT`: traceable public facts used only as scenario anchors.
- `SYNTHETIC`: generated county, population, institutions, networks, and parameters.
- `SIMULATED`: outputs from actual simulation runs.

HongCe is for policy stress testing and assisted analysis. It is not a flood
forecasting system, engineering assessment system, or automated command system.

## Training Case Corpus

The runnable app uses the processed case corpus in `data/processed/`.
The current corpus contains 28 structured cases from Ministry of Emergency
Management reports. Each case can be used for retrieval, scenario-template
generation, state-machine rule extraction, and parameter calibration.

Raw downloaded PDFs/pages live under `data/raw/` during local research, but they
are bulky and not required for classmates to run the app.

## QGIS/PyQGIS Spatial Link

HongCe can consume a QGIS-generated `spatial_package.json` with villages,
shelters, risk zones, bridges, routes, and coverage metrics. Generate it with
`scripts/qgis_build_spatial_package.py` inside QGIS Python, then pass
`spatial_package_path` to `/spatial/derive-scenario` or `/simulations/run`.
See `docs/qgis_pyqgis_integration.md`.

## Key Files

- `src/hongce/models.py`: data contracts and evacuation state machine.
- `src/hongce/scenario.py`: reproducible synthetic Qingyuan scenario generator.
- `src/hongce/engine.py`: rule-based multi-agent simulation kernel.
- `src/hongce/experiments.py`: batch policy experiments and explanation packs.
- `src/hongce/spatial.py`: QGIS spatial package adapter and scenario mapper.
- `src/hongce/adapters.py`: offline rule adapter and YuLan adapter contract.
- `data/processed/`: processed FACT case corpus used by the app.
- `scripts/build_hongce_training_corpus.py`: rebuilds the processed case corpus.
- `scripts/qgis_build_spatial_package.py`: QGIS/PyQGIS spatial package builder.
- `api/`: service, optional FastAPI app, no-dependency HTTP server.
- `web/`: zero-dependency browser workbench.
- `docs/`: architecture, technical document, model/data cards, validation report, demo script.
