"""FastAPI app for HongCe.

This module is ready for environments with FastAPI installed. In this workspace
FastAPI is currently absent, so the no-dependency `api.simple_server` remains
the verified local serving path until dependencies are installed.
"""

from __future__ import annotations

from typing import Any

from . import service

try:
    from fastapi import FastAPI
except ModuleNotFoundError as exc:  # pragma: no cover - documents missing optional dep.
    raise RuntimeError("FastAPI is not installed. Use `python -m api.simple_server` for the no-dependency demo server.") from exc


app = FastAPI(title="HongCe API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return service.health()


@app.get("/cases")
def list_cases(
    q: str = "",
    scenario_class: str = "",
    module: str = "",
    policy: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    return service.list_cases(
        {
            "q": q,
            "scenario_class": scenario_class,
            "module": module,
            "policy": policy,
            "limit": limit,
        }
    )


@app.get("/cases/{case_id}")
def get_case(case_id: str) -> dict[str, Any]:
    return service.get_case(case_id)


@app.get("/cases/{case_id}/scenario")
def generate_case_scenario(case_id: str) -> dict[str, Any]:
    return service.generate_case_scenario(case_id)


@app.post("/scenarios/validate")
def validate_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    return service.validate_scenario(payload)


@app.post("/simulations/run")
def run_simulation(payload: dict[str, Any]) -> dict[str, Any]:
    return service.run_simulation(payload)


@app.get("/simulations/{run_id}")
def get_simulation(run_id: str) -> dict[str, Any]:
    return service.get_simulation(run_id)


@app.get("/simulations/{run_id}/events")
def get_events(run_id: str) -> dict[str, Any]:
    return service.get_events(run_id)


@app.get("/simulations/{run_id}/agents/{agent_id}/trace")
def get_agent_trace(run_id: str, agent_id: str) -> dict[str, Any]:
    return service.get_agent_trace(run_id, agent_id)


@app.post("/experiments/run")
def run_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    return service.run_experiment(payload)


@app.get("/experiments/{experiment_id}/comparison")
def get_experiment_comparison(experiment_id: str) -> dict[str, Any]:
    return service.get_experiment_comparison(experiment_id)
