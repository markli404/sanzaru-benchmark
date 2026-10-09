"""One seeded bomb against a locally loaded model. No server, no HTTP, no tunnel.

    python3 -m sanzaru local --model Qwen/Qwen3-4B --task base-1 --problem 1
"""

from __future__ import annotations

from .core import execute, parser


class VLLMBackend:
    """Offline vLLM. One engine is shared by every role, so the weights load once."""

    _engine = None
    _params = None

    def __init__(self, model: str, max_model_len: int, max_tokens: int):
        if VLLMBackend._engine is None:
            from vllm import LLM, SamplingParams

            VLLMBackend._engine = LLM(
                model=model,
                max_model_len=max_model_len,
                gpu_memory_utilization=0.85,
                enforce_eager=False,
            )
            VLLMBackend._params = SamplingParams(temperature=0.0, max_tokens=max_tokens)

    def generate(self, messages):
        outputs = VLLMBackend._engine.chat([messages], VLLMBackend._params, use_tqdm=False)
        return outputs[0].outputs[0].text


def main(argv: list[str] | None = None) -> int:
    p = parser(model_default="Qwen/Qwen3-4B")
    p.add_argument("--max-model-len", type=int, default=24576)
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--call-format", default="functions")
    args = p.parse_args(argv)

    def backends(args, roles):
        backend = VLLMBackend(args.model, args.max_model_len, args.max_tokens)
        return {role: backend for role in roles}

    # One engine, one GPU: parallel requests only queue, so the runner stays serial.
    return execute(args, backends, extras={"max_tokens": args.max_tokens},
                   call_format=args.call_format, concurrent=False)


if __name__ == "__main__":
    raise SystemExit(main())
