"""Explicitly configured providers and bounded local -> frontier escalation.

No subprocess agent sessions. Candidate images/context only; no ground truth or notes.
"""

import asyncio
import os
import time
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone

from .vlm import InvalidResponse, OpenAICompatible, ProviderFailure, validate


def flag(name):
    value = os.getenv(name, "false").lower()
    if value not in ("true", "false", "1", "0"):
        raise ValueError(name + " must be true/false")
    return value in ("true", "1")


def provider_config(kind, common):
    """Frontier invocation requires both configuration AND explicit spend authorization."""
    prefix = "IDENTITY_" + kind.upper() + "_"
    if not flag(prefix + "ENABLED"):
        return None
    if kind == "frontier" and not flag(prefix + "AUTHORIZED"):
        raise ValueError(
            "Set IDENTITY_FRONTIER_AUTHORIZED=true only to authorize configured API calls"
        )
    changes = {
        "vlm_enabled": True,
        "endpoint": os.getenv(prefix + "ENDPOINT", ""),
        "model": os.getenv(prefix + "MODEL", ""),
        "api_key": os.getenv(prefix + "API_KEY", ""),
    }
    for key, suffix in [
        ("timeout_s", "TIMEOUT_S"),
        ("input_usd_per_million", "INPUT_USD_PER_MILLION"),
        ("output_usd_per_million", "OUTPUT_USD_PER_MILLION"),
    ]:
        if prefix + suffix in os.environ:
            changes[key] = float(os.environ[prefix + suffix])
    return replace(common, **changes)


class ProviderHub:
    """Common adapter, global actual-call budget, individual timeouts, optional escalation.

    One hub owns all reasoning calls within a runner, across sequence/session resets.
    The controller still owns acceptance and stale-result rejection.
    """

    def __init__(self, providers, config, escalate=False, clock=time.monotonic):
        # Ordered (provider name, adapter, provider Config) triples.
        self.providers = providers
        self.config = config
        self.escalate = escalate
        self.clock = clock
        self.budget = deque()
        self.semaphore = asyncio.Semaphore(config.concurrency)
        self.events = []
        self.current = lambda request: True
        self.supported = lambda request, matches: False

    async def match(self, request):
        last = None
        for index, (name, adapter, config) in enumerate(self.providers):
            if not self.current(request):
                raise ProviderFailure("stale_before_provider")
            if index and not self.escalate:
                break
            async with self.semaphore:
                if not self.current(request):
                    raise ProviderFailure("stale_after_queue")
                now = self.clock()
                while self.budget and now - self.budget[0] >= 60:
                    self.budget.popleft()
                if len(self.budget) >= self.config.requests_per_minute:
                    raise ProviderFailure("global_provider_rate_limit")
                self.budget.append(now)
                category = None
                usage = {}
                result = None
                event = {
                    "provider": name,
                    "model": config.model,
                    "request_id": request.get("request_id"),
                    "epoch": request.get("epoch"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "observations": [
                        {
                            k: o[k]
                            for k in ("track_id", "generation", "timestamp", "reason")
                        }
                        for o in request["observations"]
                    ],
                }
                try:
                    result = await asyncio.wait_for(
                        adapter.match(request), config.timeout_s
                    )
                    raw_usage = result.get("usage", {})
                    if isinstance(raw_usage, dict):
                        usage = {
                            k: v
                            for k, v in raw_usage.items()
                            if k
                            in ("prompt_tokens", "completion_tokens", "total_tokens")
                            and type(v) is int
                            and v >= 0
                        }
                    matches = validate(result["response"], request)
                    last = {
                        "response": {"matches": matches},
                        "usage": {},
                        "provider": name,
                    }
                except asyncio.CancelledError:
                    category = "cancelled"
                    raise
                except (TimeoutError, asyncio.TimeoutError):
                    category = "timeout"
                except InvalidResponse:
                    category = "invalid_response"
                except Exception:
                    category = "provider_error"
                finally:
                    cost = None
                    if (
                        "prompt_tokens" in usage
                        and "completion_tokens" in usage
                        and config.input_usd_per_million is not None
                        and config.output_usd_per_million is not None
                    ):
                        cost = (
                            usage["prompt_tokens"] * config.input_usd_per_million
                            + usage["completion_tokens"] * config.output_usd_per_million
                        ) / 1e6
                    event.update(
                        latency_ms=(self.clock() - now) * 1000,
                        failure_category=category,
                        usage=usage,
                        estimated_cost_usd=cost,
                        outcome="failed" if category else "validated",
                    )
                    self.events.append(event)
                if category is None and self.supported(request, matches):
                    return last
        if last is not None:
            return last
        raise ProviderFailure("all_providers_failed")


def configured_providers(method, config):
    if method not in ("H2", "H3", "H4"):
        return []
    names = (
        ["local"]
        if method == "H2"
        else ["frontier"]
        if method == "H3"
        else ["local", "frontier"]
    )
    providers = []
    for name in names:
        c = provider_config(name, config)
        if c is not None:
            providers.append((name, OpenAICompatible(c), c))
    if not providers or (method == "H4" and providers[0][0] != "local"):
        raise ValueError(
            method
            + " requires its explicitly configured provider (H4 requires local first)"
        )
    return providers
