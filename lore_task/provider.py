"""Model providers for the task runtime.

`OpenAICompatProvider` targets the ARC plan endpoint
(design/g3/provider/amendment-model-baseline-2026-09-16-ark.md). Credentials are
read from an env file outside the repository and never stored in a task dir.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    pass


def load_env_file(path) -> dict:
    out = {}
    p = os.path.expanduser(str(path))
    if not os.path.exists(p):
        return out
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


class FauxProvider:
    """Deterministic provider for offline cases (no network, no credentials)."""

    name = "faux"

    def __init__(self, responses, model="faux-1"):
        self.responses = list(responses)
        self.model = model
        self.calls = []

    def complete(self, messages, **kwargs) -> dict:
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if not self.responses:
            raise ProviderError("faux provider exhausted")
        content = self.responses.pop(0)
        return {
            "content": content,
            "reasoning": None,
            "model": self.model,
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "raw": {"faux": True, "call": len(self.calls)},
        }


class OpenAICompatProvider:
    """Minimal OpenAI-compatible chat client (stdlib only, no proxy, no retry)."""

    name = "openai-compat"

    def __init__(self, base_url: str, api_key: str, model: str, *, alias=None,
                 timeout: float = 180.0, max_tokens: int = 2048, temperature=None):
        if not base_url or not model:
            raise ProviderError("base_url and model are required")
        if not api_key:
            raise ProviderError("missing api key")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.alias = alias
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature

    def complete(self, messages, **kwargs) -> dict:
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": int(kwargs.get("max_tokens", self.max_tokens)),
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=kwargs.get("timeout", self.timeout)) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network path
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise ProviderError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network path
            raise ProviderError(f"transport error: {exc}") from exc

        if not payload.get("choices"):
            raise ProviderError(f"response without choices: {json.dumps(payload)[:300]}")
        choice = payload["choices"][0]
        message = choice.get("message") or {}
        echoed = payload.get("model")
        if echoed not in (self.model, self.alias):
            raise ProviderError(f"unexpected model echo {echoed!r}; expected {self.model!r} or alias {self.alias!r}")
        return {
            "content": message.get("content") or "",
            "reasoning": message.get("reasoning_content"),
            "model": echoed,
            "finish_reason": choice.get("finish_reason"),
            "usage": payload.get("usage") or {},
            "raw": payload,
        }
