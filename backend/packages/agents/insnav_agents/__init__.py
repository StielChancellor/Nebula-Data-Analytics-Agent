"""
insnav_agents — the agent swarm (Phase 6 MVP: Orchestrator + Semantic +
Critic + Data-Quality).

V1 deployment (PRD D5): in-process Python modules behind the orchestrator.
LLMs select; deterministic code (Cube) computes. `answer_question` is pure +
injectable (LLM router + Cube client) so the swarm is testable offline.

Stats / Maths / Graph specialists + the compute sandbox land in Phase 9.
"""
from .schemas import AnalysisLevel, ChatAnswer, DataHealthBadge, Interpretation
from .swarm import (
    answer_question,
    build_catalog,
    critic_check,
    data_health,
    interpret,
    to_cube_query,
)

__all__ = [
    "answer_question",
    "interpret",
    "critic_check",
    "to_cube_query",
    "data_health",
    "build_catalog",
    "ChatAnswer",
    "Interpretation",
    "DataHealthBadge",
    "AnalysisLevel",
]

__version__ = "0.2.0"


def list_agents() -> list[str]:
    return ["orchestrator", "semantic", "graph", "stats", "maths", "critic", "data_quality"]
