"""Mistral 7B through Ollama: pinned weights, JSON Schema constrained answers, a cache, one retry and a log.

The same setup as my Project_Enrichment_Pipeline. Nothing here calls Claude or any paid api, so the brief keeps
working when those are gone. Every caller goes through Mistral.generate and never talks to Ollama itself.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import requests
from pydantic import BaseModel, ValidationError

from halflife import config

log = logging.getLogger(__name__)

TAG = "mistral:7b-instruct-v0.3-q4_K_M"  # never mistral:latest, that one can change under me
DIGEST = "6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf"


@dataclass
class Settings:
    ollama_url: str = config.OLLAMA_URL
    temperature: float = 0
    seed: int = 42
    num_ctx: int = 8192
    num_predict: int = 400
    max_retries: int = 1  # two attempts in total
    timeout_seconds: int = 900  # a call on a CPU can take minutes
    cache_dir: Path = config.MISTRAL_CACHE
    log_file: Path = config.MISTRAL_LOG


@dataclass
class LLMResponse:
    success: bool
    text: str = ""
    parsed: dict[str, Any] | None = None
    error: str | None = None
    truncated: bool = False
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    retries: int = 0
    cached: bool = False
    latency_seconds: float = 0.0


class ModelNotReadyError(RuntimeError):
    pass


def check_model(url: str = config.OLLAMA_URL) -> str:
    """verified, digest_mismatch, not_pulled or unavailable."""
    try:
        models = requests.get(f"{url}/api/tags", timeout=10).json().get("models", [])
    except (requests.RequestException, OSError, ValueError):
        return "unavailable"
    for model in models:
        if model.get("name") == TAG:
            return "verified" if model.get("digest") == DIGEST else "digest_mismatch"
    return "not_pulled"


class Mistral:
    runtime = "local"

    def __init__(self, settings: Settings | None = None, send: Callable[[dict], dict] | None = None):
        self.s = settings or Settings()
        self._send = send or self._send_http  # a test or another transport can swap the http part
        if send is None:
            status = check_model(self.s.ollama_url)
            if status != "verified":
                raise ModelNotReadyError(f"Ollama can't serve {TAG} ({status}). Run: ollama pull {TAG}")
        self.s.cache_dir.mkdir(parents=True, exist_ok=True)
        self.s.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _send_http(self, body: dict) -> dict:
        response = requests.post(f"{self.s.ollama_url}/api/generate", json=body, timeout=self.s.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def _body(self, prompt: str, schema: dict | None, system: str | None, seed: int) -> dict:
        body: dict[str, Any] = {
            "model": TAG, "prompt": prompt, "stream": False,
            "options": {"temperature": self.s.temperature, "seed": seed, "num_ctx": self.s.num_ctx,
                        "num_predict": self.s.num_predict},
        }
        if system:
            body["system"] = system
        if schema:
            body["format"] = schema  # Ollama only lets the model write json of this shape
        return body

    def _log(self, record: dict) -> None:
        with open(self.s.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def generate(self, prompt: str, schema: type[BaseModel] | None = None, system: str | None = None,
                 task: str = "-") -> LLMResponse:
        """Never raises, the caller decides what a failure means."""
        schema_json = schema.model_json_schema() if schema else None
        prompt_hash = hashlib.sha256(f"{system or ''}\n{prompt}".encode()).hexdigest()[:16]
        key = {"digest": DIGEST, "runtime": self.runtime, "system": system, "prompt": prompt, "schema": schema_json,
               "options": [self.s.temperature, self.s.seed, self.s.num_ctx, self.s.num_predict]}
        path = self.s.cache_dir / (hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest() + ".json")
        if path.exists():
            result = LLMResponse(**{**json.loads(path.read_text(encoding="utf-8")), "cached": True})
        else:
            result = LLMResponse(success=False)
            for attempt in range(self.s.max_retries + 1):
                # temperature 0 with the same seed would only repeat the failure, so a retry changes the seed
                result = self._attempt(self._body(prompt, schema_json, system, self.s.seed + attempt), schema)
                result.retries = attempt
                if result.success:
                    break
            if result.success:
                path.write_text(json.dumps(asdict(result), ensure_ascii=False), encoding="utf-8")
            else:
                log.warning("Mistral 7B failed in %s: %s", task, result.error)
        self._log({"task": task, "model": TAG, "prompt_hash": prompt_hash,
                   **{k: v for k, v in asdict(result).items() if k not in ("text", "parsed")}})
        return result

    def _attempt(self, body: dict, schema: type[BaseModel] | None) -> LLMResponse:
        started = time.perf_counter()
        result = LLMResponse(success=False)
        try:
            answer = self._send(body)
            result.text = answer.get("response", "")
            result.prompt_tokens = answer.get("prompt_eval_count")
            result.completion_tokens = answer.get("eval_count")
            result.truncated = answer.get("done_reason") == "length"
            if schema is None:
                result.success = bool(result.text.strip())
                result.error = None if result.success else "empty"
            else:
                result.parsed = schema.model_validate_json(result.text).model_dump()
                result.success = True
        except ValidationError as e:
            result.error = f"schema validation failed: {e.error_count()} errors"
        except (requests.RequestException, OSError) as e:
            result.error = f"request failed: {type(e).__name__}"
        result.latency_seconds = round(time.perf_counter() - started, 3)
        return result
