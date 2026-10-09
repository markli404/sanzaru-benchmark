from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import random
import time
from typing import Protocol
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class Backend(Protocol):
    def generate(self, messages: list[dict[str, str]]) -> str: ...


@dataclass
class OpenAICompatibleBackend:
    model: str
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    temperature: float = 0.0
    max_tokens: int = 256
    prompt_prefix: str = ""
    # Server-specific knobs passed through verbatim, e.g. Qwen's
    # {"chat_template_kwargs": {"enable_thinking": False}}.
    extra_body: dict = field(default_factory=dict)
    # A round asks every monkey at once, so a rate limit is normal rather than
    # exceptional. Back off and try again instead of losing the run.
    retries: int = 8
    backoff: float = 2.0
    max_wait: float = 60.0
    # Reasoning models bill their thinking as output, so they name the budget
    # differently and refuse a temperature. None means: decide from the model name.
    reasoning: bool | None = None
    # Some providers (Qwen) only serve thinking mode over SSE streaming; the
    # stream is gathered back into one reply, reasoning deltas dropped.
    stream: bool = False

    def thinks(self) -> bool:
        """Whether this model reasons before answering, which changes the request."""
        if self.reasoning is not None:
            return self.reasoning
        name = self.model.lower()
        if name.startswith(("o1", "o3", "o4")):
            return True
        return name.startswith("gpt-5") and "chat" not in name

    def generate(self, messages: list[dict[str, str]]) -> str:
        if self.prompt_prefix and messages:
            messages = [dict(message) for message in messages]
            messages[-1]["content"] = self.prompt_prefix + messages[-1]["content"]
        payload: dict[str, object] = {"model": self.model, "messages": messages}
        if self.thinks():
            payload["max_completion_tokens"] = self.max_tokens
        else:
            payload["max_tokens"] = self.max_tokens
            # The Claude 5 family rejects the parameter outright ("deprecated
            # for this model"), so those models run at their house default.
            if not self.model.startswith(("claude-sonnet-5", "claude-opus-5",
                                          "claude-fable")):
                payload["temperature"] = self.temperature
        payload.update(self.extra_body)
        if self.stream:
            payload["stream"] = True
        body = json.dumps(payload).encode()
        key = self.api_key or os.environ.get("OPENAI_API_KEY", "")
        request = Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request) as response:
                    if not self.stream:
                        return json.load(response)["choices"][0]["message"]["content"]
                    pieces = []
                    for raw in response:
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if chunk == "[DONE]":
                            break
                        choices = json.loads(chunk).get("choices") or []
                        if choices:
                            piece = (choices[0].get("delta") or {}).get("content")
                            if piece:
                                pieces.append(piece)
                    return "".join(pieces)
            except HTTPError as error:
                retriable = error.code == 429 or 500 <= error.code < 600
                if not retriable or attempt == self.retries:
                    raise
                wait = min(float(error.headers.get("retry-after")
                                  or self.backoff ** attempt), self.max_wait)
            except (URLError, HTTPException, TimeoutError):
                # A response cut off mid-stream is the transport's failure, not
                # the model's answer. Same medicine as an unreachable host.
                if attempt == self.retries:
                    raise
                wait = min(self.backoff ** attempt, self.max_wait)
            time.sleep(wait + random.uniform(0, 0.4))
        raise RuntimeError("unreachable")


@dataclass
class AnthropicBackend:
    """Native Anthropic Messages API, chosen for its prompt caching.

    Anthropic's cache is opt-in through cache_control breakpoints, which the
    OpenAI-compatible surface cannot express, so that path repays the whole
    growing history at full price on every call. Here the system prompt and
    the newest turn carry the markers; each request then rides the longest
    previously cached prefix at a tenth of the input price.
    """

    model: str
    api_key: str | None = None
    max_tokens: int = 256
    retries: int = 12
    backoff: float = 2.0
    max_wait: float = 60.0

    def generate(self, messages: list[dict[str, str]]) -> str:
        system = ""
        convo: list[dict] = []
        for message in messages:
            if message["role"] == "system" and not convo:
                system += message["content"]
            else:
                convo.append({"role": message["role"],
                              "content": [{"type": "text", "text": message["content"]}]})
        if convo:
            convo[-1]["content"][-1]["cache_control"] = {"type": "ephemeral"}
        # House-default adaptive thinking, the same footing terra, GLM and
        # Gemini run on. SANZARU_NOTHINK=1 switches it off; the non-thinking
        # control round lives in its own output folder.
        payload: dict[str, object] = {"model": self.model, "max_tokens": self.max_tokens,
                                      "messages": convo}
        if os.environ.get("SANZARU_NOTHINK"):
            payload["thinking"] = {"type": "disabled"}
        if system:
            payload["system"] = [{"type": "text", "text": system,
                                  "cache_control": {"type": "ephemeral"}}]
        body = json.dumps(payload).encode()
        request = Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={"Content-Type": "application/json",
                     "x-api-key": self.api_key or os.environ.get("CLAUDE_API_KEY", ""),
                     "anthropic-version": "2023-06-01"},
        )
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request) as response:
                    data = json.load(response)
                    if os.environ.get("SANZARU_USAGE"):
                        usage = data.get("usage", {})
                        print("usage " + " ".join(f"{k}={usage.get(k, 0)}" for k in (
                            "input_tokens", "cache_creation_input_tokens",
                            "cache_read_input_tokens", "output_tokens")), flush=True)
                    return "".join(block.get("text", "") for block in data["content"]
                                   if block.get("type") == "text")
            except HTTPError as error:
                try:
                    detail = error.read().decode(errors="replace")
                except Exception:
                    detail = ""
                # An empty wallet is a pause, not a verdict: hold the run at
                # one-minute beats so a mid-flight top-up lets it continue.
                credit_dry = error.code == 400 and "credit" in detail.lower()
                retriable = (error.code == 429 or 500 <= error.code < 600
                             or credit_dry)
                if not retriable or attempt == self.retries:
                    raise
                wait = self.max_wait if credit_dry else min(
                    float(error.headers.get("retry-after")
                          or self.backoff ** attempt), self.max_wait)
            except (URLError, HTTPException, TimeoutError):
                if attempt == self.retries:
                    raise
                wait = min(self.backoff ** attempt, self.max_wait)
            time.sleep(wait + random.uniform(0, 0.4))
        raise RuntimeError("unreachable")


class TransformersBackend:
    def __init__(self, model: str, max_new_tokens: int = 256):
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("Install local support with: pip install -e '.[local]'") from exc
        self.tokenizer = AutoTokenizer.from_pretrained(model)
        self.model = AutoModelForCausalLM.from_pretrained(model, device_map="auto")
        self.max_new_tokens = max_new_tokens

    def generate(self, messages: list[dict[str, str]]) -> str:
        inputs = self.tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt")
        inputs = inputs.to(self.model.device)
        output = self.model.generate(inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        return self.tokenizer.decode(output[0, inputs.shape[-1]:], skip_special_tokens=True)


@dataclass
class OllamaBackend:
    model: str
    base_url: str = "http://127.0.0.1:11434"
    temperature: float = 0.0
    max_tokens: int = 256
    think: bool = False

    def generate(self, messages: list[dict[str, str]]) -> str:
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": self.think,
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens},
        }).encode()
        request = Request(
            self.base_url.rstrip("/") + "/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            data = json.load(response)
        return data["message"]["content"]


def backend_from_spec(spec: str, base_url: str | None = None, api_key: str | None = None) -> Backend:
    scheme, separator, model = spec.partition(":")
    if not separator or not model:
        raise ValueError("model must be api:MODEL or local:PATH")
    if scheme == "api":
        default = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return OpenAICompatibleBackend(model, base_url or default, api_key)
    if scheme == "local":
        return TransformersBackend(model)
    raise ValueError(f"unknown model scheme: {scheme}")
