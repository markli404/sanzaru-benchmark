"""Symmetric communication with the classic private views and action authority."""

from ..protocol import Senses
from .blind import Blind
from .deaf import Deaf
from .mute import Mute


class InfoDeaf(Deaf):
    senses = Senses()
    sheet = "info_deaf"


class InfoMute(Mute):
    senses = Senses()
    sheet = "info_mute"


class InfoBlind(Blind):
    senses = Senses()
    sheet = "info_blind"
