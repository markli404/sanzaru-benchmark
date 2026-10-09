"""Every word a model ever reads.

Nothing in this package imports the rest of the benchmark, so the code that routes
messages can pull its wording from here without a cycle. If a sentence reaches a model —
a rule, a route, a rejection notice — it is written in a `.md` file beside this one and
never in a Python string.

A file is either one prose template (`common.md`, `deaf.md`) or a set of named phrases
under `### key` headings (`notices.md`, `communication.md`).
"""

from __future__ import annotations

from pathlib import Path
import re

DIRECTORY = Path(__file__).parent
DEFAULT_FORMAT = "functions"

PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
FIELD_RE = re.compile(r"\{(\w+)\}")
HEADING_RE = re.compile(r"^### (\w+)$", re.M)


def load(name: str) -> str:
    return (DIRECTORY / f"{name}.md").read_text(encoding="utf-8").strip()


def phrases(name: str) -> dict[str, str]:
    """The `### key` sections of a phrase file, keyed by name."""
    text = load(name)
    parts = HEADING_RE.split(text)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def phrase(name: str, key: str, **fields: object) -> str:
    """One named phrase with its {fields} filled in."""
    text = phrases(name)[key]
    missing = set(FIELD_RE.findall(text)) - fields.keys()
    if missing:
        raise KeyError(f"unfilled fields in {name}.{key}: {sorted(missing)}")
    return text.format(**fields)


def render(role: str, **context: str) -> str:
    """The common skeleton with the role's own section rendered into {{role_block}}.

    The role text sits in the middle rather than at the end, so the compiled prompt
    reads objective, then who knows what, then you, then how you communicate.
    """
    sheet = load(role)
    common = "common_info" if role.startswith("info_") else "common"
    text = sheet if sheet.startswith("# LLM-BANANA") else load(common).replace("{{role_block}}", sheet)
    rendered = PLACEHOLDER_RE.sub(lambda match: context[match.group(1)], text)
    leftover = PLACEHOLDER_RE.findall(rendered)
    if leftover:
        raise KeyError(f"unfilled prompt placeholders in {role}: {sorted(set(leftover))}")
    return rendered
