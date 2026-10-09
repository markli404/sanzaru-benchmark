"""Blind: cannot see. Holds the cutters, so the judge listens only to this role."""

from __future__ import annotations

from ..protocol import Senses
from .base import Agent
from .registry import register


@register
class Blind(Agent):
    role = "blind"
    order = 2
    senses = Senses(sees=False)
    may_act = True
