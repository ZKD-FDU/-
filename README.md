# HongCe

洪策：基于真实灾害事故调查报告训练素材的极端事件人员转移与协同治理多智能体政策推演系统。

本轮升级为 **v4 三维政策沙盘**：保留初步修改版本的深蓝指挥舱、原导航和数据仪表盘，在原 Three.js 基础上修复标签遮挡，补充河谷、河床水面、实体道路桥梁和分类建筑；支持设施定位与分段行程检查。车辆从实际集结位置出发，沿路空驶接人、装载转运，在目的地卸载后继续调度。道路双向共享分时容量，群体覆盖均衡可作为对照策略。

- [模型机制、同类开源项目参考与策划书完成度](docs/model-v4.md)
- [本轮验证结果](docs/validation-v4.md)
- [1,850 次 v4 实验汇总](data/validation/competition_v4.json) / [逐次 CSV](data/validation/competition_v4_runs.csv)
- [v3 历史档案](docs/validation-v3.md)

本项目仍为合成情景研究原型，未以实测洪水或独立演练数据完成校准。地形与街区制图不代表实景数字孪生。各版本结果分别保存，不能混算；综合方案不保证最优，策略搜索不等于已训练强化学习。

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
- `GET /validation/latest`
- `GET /cases`
- `GET /cases/{case_id}`
- `GET /cases/{case_id}/scenario`
- `POST /scenarios/validate`
- `GET /spatial/package?path=data/spatial/qingyuan`
- `POST /spatial/derive-scenario`
- `GET /parameters`
- `GET /parameters/cases/{case_id}`
- `POST /parameters/derive-scenario`
- `POST /simulations/run`
- `GET /simulations/{run_id}`
- `GET /simulations/{run_id}/events`
- `GET /simulations/{run_id}/agents/{agent_id}/trace`
- `POST /experiments/run`
- `GET /experiments/{experiment_id}/comparison`
- `GET /decision/mdp`
- `POST /decision/optimize`
- `POST /decision/bandit`

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

The first case-derived parameter library lives in `data/parameters/` and can be
rebuilt with:

```bash
python3 scripts/build_mem_parameter_library.py
```

Each parameter estimate keeps a range, source label, confidence score, evidence
keys, and review status.

Raw downloaded PDFs/pages live under `data/raw/` during local research, but they
are bulky and not required for classmates to run the app.

## QGIS/PyQGIS Spatial Link

HongCe can consume a QGIS-generated `spatial_package.json` with villages,
shelters, rivers/tributaries, risk zones, bridges/culverts, routes, and coverage metrics. Generate it with
`scripts/qgis_build_spatial_package.py` inside QGIS Python, then pass
`spatial_package_path` to `/spatial/derive-scenario` or `/simulations/run`.
See `docs/qgis_pyqgis_integration.md` and `docs/qgis_spatial_data_standard.md`.

## Key Files

- `src/hongce/models.py`: data contracts and evacuation state machine.
- `src/hongce/scenario.py`: reproducible synthetic Qingyuan scenario generator.
- `src/hongce/engine.py`: rule-based multi-agent simulation kernel.
- `src/hongce/experiments.py`: batch policy experiments and explanation packs.
- `src/hongce/calibration.py`: case-derived parameter library and calibration priors.
- `src/hongce/decision.py`: MDP/POMDP contract, interpretable policy optimization, and contextual bandit recommendation.
- `src/hongce/spatial.py`: QGIS spatial package adapter and scenario mapper.
- `src/hongce/adapters.py`: offline rule adapter and YuLan adapter contract.
- `data/processed/`: processed FACT case corpus used by the app.
- `data/parameters/`: MEM case-derived parameter library used for calibration.
- `scripts/build_hongce_training_corpus.py`: rebuilds the processed case corpus.
- `scripts/build_mem_parameter_library.py`: rebuilds the parameter library from processed cases.
- `scripts/qgis_build_spatial_package.py`: QGIS/PyQGIS spatial package builder.
- `api/`: service, optional FastAPI app, no-dependency HTTP server.
- `web/`: browser workbench without a build step; Three.js 0.160.0 is bundled locally with its MIT license in `web/vendor/`, so rendering does not require an external CDN.
- `docs/`: architecture, technical document, model/data cards, validation report, demo script, decision/RL design, calibration and QGIS data standards.

## Reproduce v4 evidence

```bash
PYTHONPATH=src python scripts/validate_competition.py
```

Windows PowerShell: first run `$env:PYTHONPATH="src"`, then use the same `python` commands without the `PYTHONPATH=src` prefix.

Open `http://127.0.0.1:5173/?sandbox=1` for an automatically computed 500-person preview, or `http://127.0.0.1:5173/?review=1` for the completed experiment bundle. In the sandbox, select a place/road/vehicle, replay time, change a pressure scenario, and apply parameters to rerun. Changed inputs do not relabel a previous run as a new result.

The v4 bundle uses 50 paired seeds (202609110–202609159): 150 policy baselines, 1,100 A/B/C mechanism runs, 300 stress runs, and 300 fleet/fairness comparisons. Baseline and fleet comparisons use 2,000 people; mechanisms and stresses use 500. Earlier version archives are not overwritten.
