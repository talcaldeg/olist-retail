"""Metrics agent: routes a question to the semantic layer, never writes SQL."""

from agent.core import Answer, ask

__all__ = ["Answer", "ask"]
