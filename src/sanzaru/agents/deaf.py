"""Deaf: cannot hear. Speech reaches everyone; gestures reach only those who see."""

from __future__ import annotations

from ..protocol import Senses
from .base import Agent
from .registry import register


@register
class Deaf(Agent):
    role = "deaf"
    order = 0
    senses = Senses(hears=False)
    may_act = False
