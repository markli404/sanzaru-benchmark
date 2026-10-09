"""Easy mode: one monkey with every sense and every page. The control condition."""

from __future__ import annotations

from ..protocol import Senses
from .base import Agent


class Almighty(Agent):
    role = "almighty"
    sheet = "almighty"
    order = 0
    senses = Senses()
    may_act = True
