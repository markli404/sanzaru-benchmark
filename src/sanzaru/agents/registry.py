"""Role registry. `roles()` is derived from what has registered, not hardcoded."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from ..prompts import load, phrase, phrases
from ..protocol import GESTURES, Senses, describe_own_routes, matrix, syntax_doc

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .base import Agent
    from ..backends import Backend

_REGISTRY: dict[str, type["Agent"]] = {}

T = TypeVar("T", bound="type[Agent]")


def register(cls: T) -> T:
    """Class decorator used by each role module to join the classic mode."""
    if cls.role in _REGISTRY:
        raise ValueError(f"role already registered: {cls.role}")
    _REGISTRY[cls.role] = cls
    return cls


def _modes() -> dict[str, dict[str, type["Agent"]]]:
    """Which classes make up each mode. `classic` is the registered trio; `hard`
    swaps in a Blind with no voice; `easy` is one almighty monkey, the control;
    `info` keeps private views and action authority with symmetric communication."""
    from .almighty import Almighty
    from .blind_mute import BlindMute
    from .info import InfoBlind, InfoDeaf, InfoMute
    classic = {role: _REGISTRY[role]
               for role in sorted(_REGISTRY, key=lambda r: _REGISTRY[r].order)}
    return {
        "norm": classic,
        "hard": {**classic, "blind": BlindMute},
        "easy": {"almighty": Almighty},
        "info": {"deaf": InfoDeaf, "mute": InfoMute, "blind": InfoBlind},
    }


def roles(mode: str = "norm") -> tuple[str, ...]:
    """The mode's roles in turn order."""
    return tuple(_modes()[mode])


def agent_class(role: str, mode: str = "norm") -> type["Agent"]:
    return _modes()[mode][role]


def senses(mode: str = "norm") -> dict[str, Senses]:
    """The skill table: the single source every route is derived from."""
    return {role: cls.senses for role, cls in _modes()[mode].items()}


def actors(mode: str = "norm") -> tuple[str, ...]:
    return tuple(role for role, cls in _modes()[mode].items() if cls.may_act)


def communication_matrix(mode: str = "norm") -> dict[tuple[str, str], tuple[str, ...]]:
    return matrix(senses(mode))


def build(role: str, backend: "Backend", call_format: str = "", actions: str = "",
          order: tuple[str, ...] = (), hints: str = "", mode: str = "norm",
          window: int = 0) -> "Agent":
    return agent_class(role, mode)(backend, call_format, actions, order, hints, mode, window)


def build_all(backends: dict[str, "Backend"], call_format: str = "", actions: str = "",
              order: tuple[str, ...] = (), hints: str = "",
              mode: str = "norm", window: int = 0) -> dict[str, "Agent"]:
    missing = set(roles(mode)) - backends.keys()
    if missing:
        raise ValueError(f"missing backends: {sorted(missing)}")
    return {role: build(role, backends[role], call_format, actions, order, hints, mode,
                        window)
            for role in roles(mode)}


def protocol_context(call_format: str, role: str = "", actions: str = "",
                     order: tuple[str, ...] = (), hints: str = "",
                     mode: str = "norm") -> dict[str, str]:
    """Prompt placeholders generated from the registry, so rules cannot drift.

    `my_routes` is per-role and outgoing only: a monkey is told what its own channels
    reach, never the whole communication graph.
    """
    return {
        "turn_order": (
            phrase("communication", "turn_order_sequential",
                   order=", ".join(name.capitalize() for name in order))
            if order else phrases("communication")["turn_order_simultaneous"]
        ),
        "my_routes": describe_own_routes(senses(mode), role, role in actors(mode)) if role else "",
        "gestures": " ".join(GESTURES),
        # A solo monkey coordinates with nobody: every hint tier is about the trio,
        # so easy mode runs bare regardless of what was asked for.
        "hints": ("\n" + load(f"hints_info_{hints}" if mode == "info" else f"hints_{hints}"))
                 if hints and mode != "easy" else "",
        "call_syntax": syntax_doc(call_format,
                                  ("act", "wait") if mode == "easy" else ("speak", "gesture", "wait")),
        "crew_table": load(f"crew_{mode}") if mode != "easy" else "",
        "my_actions": (phrase("communication", "actions_for_actor", actions=actions)
                       if role in actors(mode) and actions
                       else phrases("communication")["actions_for_others"]),
    }
