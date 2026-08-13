# HongCe

洪策：极端洪涝下脆弱群体转移与基层资源配置多智能体政策推演系统。

Current status: runnable competition MVP. The system includes a deterministic
simulation kernel, S0-S5 policies, A/B/C batch experiments, HTTP API, seven-page
frontend workbench, tests, and delivery documents. It runs without external model
keys; policy comparisons are produced from actual simulation runs.

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
- `POST /scenarios/validate`
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

## Key Files

- `src/hongce/models.py`: data contracts and evacuation state machine.
- `src/hongce/scenario.py`: reproducible synthetic Qingyuan scenario generator.
- `src/hongce/engine.py`: rule-based multi-agent simulation kernel.
- `src/hongce/experiments.py`: batch policy experiments and explanation packs.
- `src/hongce/adapters.py`: offline rule adapter and YuLan adapter contract.
- `api/`: service, optional FastAPI app, no-dependency HTTP server.
- `web/`: zero-dependency browser workbench.
- `docs/`: architecture, technical document, model/data cards, validation report, demo script.
