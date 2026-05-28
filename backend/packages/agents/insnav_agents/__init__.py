"""
insnav_agents — the 7 agents in the swarm.

V1 deployment (per PRD D5): all 7 live inside services/orchestrator/ as
in-process Python modules. They communicate via insnav_contracts.AgentMessage
so extraction-to-RPC later is a port, not a refactor.

TODO Phase 6 (Semantic + Critic + DataQuality MVP), Phase 9 (Stats + Maths + Graph).
"""

__version__ = "0.1.0"


# Each agent will export a `handle(msg: AgentMessage) -> AgentResult` function.
# Placeholders defined here so imports don't break during scaffold phase.

def list_agents() -> list[str]:
    return ["orchestrator", "semantic", "graph", "stats", "maths", "critic", "data_quality"]
