"""Hard mode's Blind: the hands are also voiceless. Gesture out, hearing in."""

from __future__ import annotations

from ..protocol import Senses
from .base import Agent


class BlindMute(Agent):
    role = "blind"
    sheet = "blind_mute"
    order = 2
    senses = Senses(sees=False, speaks=False)
    may_act = True
