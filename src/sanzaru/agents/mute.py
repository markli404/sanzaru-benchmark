"""Mute: cannot speak. Gesturing is the only channel out, and only the sighted see it."""

from __future__ import annotations

from ..protocol import Senses
from .base import Agent
from .registry import register


@register
class Mute(Agent):
    role = "mute"
    order = 1
    senses = Senses(speaks=False)
    may_act = False
