"""One door in.

    python3 -m sanzaru run   ...   an OpenAI-compatible API plays the bomb
    python3 -m sanzaru local ...   a locally loaded model plays it (needs vllm)
    python3 -m sanzaru page  ...   re-render output/rollout.html
    python3 -m sanzaru bank  ...   (re)write the frozen problem bank
    python3 -m sanzaru batch ...   many bombs through the OpenAI Batch API, half price

Each subcommand keeps its own flags; `local` imports its heavy runtime only
when asked for.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args.pop(0) if args else ""
    if command == "run":
        from .api import main as run_main
        return run_main(args)
    if command == "local":
        from .local import main as local_main
        return local_main(args)
    if command == "page":
        from ..viewer.page import main as page_main
        return page_main(args)
    if command == "bank":
        from ..bank import main as bank_main
        return bank_main(args)
    if command == "batch":
        from ..batchrun import main as batch_main
        return batch_main(args)
    print(__doc__.strip())
    return 0 if command in ("", "-h", "--help") else 2
