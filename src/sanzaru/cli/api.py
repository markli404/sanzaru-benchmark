"""One seeded bomb against an OpenAI-compatible model, saving a replay-complete trace."""

from __future__ import annotations

import os

from ..backends import AnthropicBackend, OpenAICompatibleBackend
from ..config import load_env
from .core import execute, parser

# The provider is read off the model's name; every entry is an OpenAI-compatible
# endpoint, the key's environment variable, and any request fields the provider
# needs verbatim. DeepSeek ships its models with reasoning on; we switch it off,
# because the visible thinking the protocol demands is the thinking we measure.
PROVIDERS = {
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY",
                 {"thinking": {"type": "disabled"}}),
    # GLM-5.3-Flash cannot switch thinking off; the reasoning rides in a separate
    # field the transcript never keeps, so the visible reply stays the measure.
    "glm": ("https://open.bigmodel.cn/api/paas/v4", "GLM_API_KEY", {}),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai",
               "GEMINI_API_KEY", {}),
    # Qwen defaults to no thinking; the -think suffixes opt into SSE below.
    # Supply the account/region-specific compatible endpoint via QWEN_BASE_URL.
    "qwen": ("",
             "QWEN_API_KEY", {"enable_thinking": False}),
}


def _endpoint(model: str) -> tuple[str, str | None, dict]:
    for prefix, (base_url, key_var, extra) in PROVIDERS.items():
        if model.lower().startswith(prefix):
            base_url = os.environ.get(f"{prefix.upper()}_BASE_URL") or base_url
            if not base_url:
                raise ValueError(f"Set {prefix.upper()}_BASE_URL to your provider's compatible API URL")
            return base_url, os.environ.get(key_var), extra
    return "https://api.openai.com/v1", None, {}


def main(argv: list[str] | None = None) -> int:
    p = parser(model_default="gpt-4o")
    p.add_argument("--max-tokens", type=int, default=1200)
    p.add_argument("--temperature", type=float, default=0.6)
    args = p.parse_args(argv)
    load_env()

    def backends(args, roles):
        # No separate thinking_budget; max_tokens still caps the response.
        if args.model.startswith("qwen") and args.model.endswith("-think-max"):
            base_url, api_key, _ = _endpoint(args.model)
            return {role: OpenAICompatibleBackend(args.model[:-10], base_url=base_url,
                                                  api_key=api_key,
                                                  max_tokens=args.max_tokens,
                                                  temperature=args.temperature,
                                                  extra_body={"enable_thinking": True},
                                                  stream=True)
                    for role in roles}
        # qwen*-think: the suffix names the run folder; the API gets the bare
        # model with thinking on, which Qwen only serves over streaming.
        if args.model.startswith("qwen") and args.model.endswith("-think"):
            base_url, api_key, _ = _endpoint(args.model)
            return {role: OpenAICompatibleBackend(args.model[:-6], base_url=base_url,
                                                  api_key=api_key,
                                                  max_tokens=args.max_tokens,
                                                  temperature=args.temperature,
                                                  extra_body={"enable_thinking": True,
                                                              "thinking_budget": 4096},
                                                  stream=True)
                    for role in roles}
        if args.model.startswith("claude"):
            return {role: AnthropicBackend(args.model, max_tokens=args.max_tokens)
                    for role in roles}
        base_url, api_key, extra_body = _endpoint(args.model)
        return {role: OpenAICompatibleBackend(args.model, base_url=base_url,
                                              api_key=api_key,
                                              max_tokens=args.max_tokens,
                                              temperature=args.temperature,
                                              extra_body=extra_body)
                for role in roles}

    return execute(args, backends,
                   extras={"temperature": args.temperature, "max_tokens": args.max_tokens})


if __name__ == "__main__":
    raise SystemExit(main())
