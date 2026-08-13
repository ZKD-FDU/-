"""Agent decision adapters.

The rule adapter is the production default for the competition MVP. External
model adapters may enrich explanations later, but they must return structured
decisions and must not bypass the evacuation state machine in models.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .models import PolicyConfig, PolicyId


@dataclass(frozen=True)
class DecisionContext:
    actor_id: str
    minute: int
    danger_arrival_minute: int
    risk_perception: float
    official_trust: float
    cadre_trust: float
    neighbor_trust: float
    neighbor_action_rate: float
    digital_access: float
    transfer_cost: float
    refusal_tendency: float
    false_alarm_memory: int
    mobility: str
    care_dependency: str
    has_private_transport: bool


@dataclass(frozen=True)
class AgentDecision:
    evacuate_probability: float
    action: str
    reason: str
    factors: dict[str, float]
    adapter: str


class AgentDecisionAdapter(Protocol):
    name: str

    def decide(self, context: DecisionContext, policy: PolicyConfig) -> AgentDecision:
        """Return a structured decision without mutating simulation state."""


class RuleBasedAgentAdapter:
    name = "RuleBasedAgentAdapter"

    def decide(self, context: DecisionContext, policy: PolicyConfig) -> AgentDecision:
        lead = max(0, context.danger_arrival_minute - context.minute) / max(1, context.danger_arrival_minute)
        confirmation = 0.18 if policy.confirmation_required else 0.0
        assisted_transfer = 0.15 if policy.dispatch_rule.value in {"vulnerable_first", "integrated_resilience"} else 0.0
        route_penalty = 0.10 if policy.id == PolicyId.S0 and context.mobility != "independent" else 0.0
        factors = {
            "risk_perception": 1.55 * context.risk_perception,
            "official_trust": 0.75 * context.official_trust,
            "cadre_trust": confirmation * context.cadre_trust,
            "neighbor_action": 0.65 * context.neighbor_action_rate * context.neighbor_trust,
            "direct_assistance": assisted_transfer,
            "lead_time": 0.35 * lead,
            "transfer_cost": -0.90 * context.transfer_cost,
            "false_alarm_fatigue": -0.10 * context.false_alarm_memory,
            "route_obstacle": -route_penalty,
            "refusal_tendency": -1.10 * context.refusal_tendency,
        }
        score = -1.35 + sum(factors.values())
        probability = 1.0 / (1.0 + pow(2.718281828, -score))
        action = "confirm_evacuation" if probability >= 0.5 else "delay_or_refuse"
        reason = "structured rule decision from risk, trust, peer action, transfer burden, and policy support"
        return AgentDecision(
            evacuate_probability=max(0.0, min(1.0, probability)),
            action=action,
            reason=reason,
            factors=factors,
            adapter=self.name,
        )


class YulanOneSimAdapter:
    """Placeholder boundary for YuLan-OneSim integration.

    The local MVP intentionally does not call external network services. This
    adapter exists to freeze the payload contract for later platform execution.
    """

    name = "YulanOneSimAdapter"

    def __init__(self, endpoint: str | None = None, api_key: str | None = None) -> None:
        self.endpoint = endpoint
        self.api_key = api_key

    def decide(self, context: DecisionContext, policy: PolicyConfig) -> AgentDecision:
        raise RuntimeError(
            "YulanOneSimAdapter is not configured in offline MVP; use RuleBasedAgentAdapter for full local runs."
        )

    def payload_for(self, context: DecisionContext, policy: PolicyConfig) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "policy_id": policy.id.value,
            "context": context.__dict__,
            "required_schema": {
                "evacuate_probability": "float[0,1]",
                "action": "confirm_evacuation|delay_or_refuse",
                "reason": "string",
                "factors": "object[number]",
            },
        }
