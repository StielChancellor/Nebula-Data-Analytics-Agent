"""
insnav_contracts — the load-bearing shapes every agent and service depend on.

This package is import-safe (no GCP/HTTP side effects on import). Keep it that
way so it stays cheap to import in any context.

Exports:
  AgentMessage    — inter-agent envelope used by the orchestrator
  AgentResult     — MANDATORY return shape from every agent call
  Intent          — enum of allowed message intents
  AgentName       — enum of the 7 agent identities
"""
from .envelope import (
    AgentMessage,
    AgentResult,
    AgentName,
    Intent,
    DataHealthBadge,
    InterpretationEcho,
    ResultEnvelopeError,
)

__all__ = [
    "AgentMessage",
    "AgentResult",
    "AgentName",
    "Intent",
    "DataHealthBadge",
    "InterpretationEcho",
    "ResultEnvelopeError",
]

__version__ = "0.1.0"
