"""Minimal OpenAI-compatible chat client."""
from __future__ import annotations

import json
import http.client
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ChatConfig:
    """Configuration for a chat completion request."""

    model: str
    endpoint: str
    temperature: float = 0.1
    max_tokens: int = 1024
    api_key: Optional[str] = None
    site_url: Optional[str] = None
    app_name: Optional[str] = None
    timeout_seconds: int = 120
    retry_on_connection_error: int = 3
    retry_delay_seconds: int = 15


class OpenAICompatibleClient:
    """Tiny client for OpenAI-style chat completion APIs."""

    def __init__(self, config: ChatConfig):
        self.config = config

    @staticmethod
    def _text_from_content(content: Any) -> str:
        """Extract assistant text from OpenAI/OpenRouter content variants."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                    elif isinstance(block.get("content"), str):
                        parts.append(block["content"])
            return "\n".join(part for part in parts if part.strip())
        return ""

    @classmethod
    def _extract_assistant_text(cls, data: dict[str, Any]) -> str:
        choice = data["choices"][0]
        message = choice.get("message") or {}
        content = cls._text_from_content(message.get("content"))
        if content.strip():
            return content

        # Some OpenRouter/provider responses expose text outside message.content,
        # especially for reasoning models or streaming-compatible adapters.
        for source in (message, choice, data):
            if not isinstance(source, dict):
                continue
            for key in ("text", "output_text", "reasoning", "reasoning_content"):
                value = cls._text_from_content(source.get(key))
                if value.strip():
                    return value
        return ""

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request and return assistant text."""
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.site_url:
            headers["HTTP-Referer"] = self.config.site_url
        if self.config.app_name:
            headers["X-Title"] = self.config.app_name

        payload_bytes = json.dumps(payload).encode("utf-8")

        retries = max(0, int(self.config.retry_on_connection_error))
        delay = max(0, int(self.config.retry_delay_seconds))
        last_error: Optional[Exception] = None
        retryable_http_codes = {408, 409, 425, 429, 500, 502, 503, 504}

        for attempt in range(retries + 1):
            try:
                request = urllib.request.Request(
                    self.config.endpoint,
                    data=payload_bytes,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    body = response.read().decode("utf-8")
                data = json.loads(body)
                content = self._extract_assistant_text(data)
                if not content.strip():
                    raise ValueError("empty assistant content")
                return content
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                if exc.code not in retryable_http_codes or attempt >= retries:
                    raise RuntimeError(
                        f"LLM request failed with HTTP {exc.code}: {err_body}"
                    ) from exc
                last_error = RuntimeError(f"HTTP {exc.code}: {err_body[:500]}")
            except (
                urllib.error.URLError,
                TimeoutError,
                socket.timeout,
                ConnectionError,
                ConnectionResetError,
                http.client.IncompleteRead,
                http.client.RemoteDisconnected,
                http.client.HTTPException,
                json.JSONDecodeError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
            ) as exc:
                last_error = exc
                if attempt >= retries:
                    raise RuntimeError(f"LLM request failed: {exc}") from exc
            if attempt < retries and delay:
                time.sleep(delay)
        else:
            # Defensive fallback; loop should always break or raise.
            raise RuntimeError(f"LLM request failed: {last_error}")
