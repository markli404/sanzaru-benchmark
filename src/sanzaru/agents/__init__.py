"""Agents package. Importing it registers every role."""

from .base import Agent
from .registry import (
    actors, agent_class, build, build_all, communication_matrix,
    protocol_context, register, roles, senses,
)
from . import blind, deaf, mute  # noqa: F401  (imported for registration side effects)

__all__ = [
    "Agent", "actors", "agent_class", "build", "build_all",
    "communication_matrix", "protocol_context", "register", "roles", "senses",
]
