"""In-memory request metrics used by adaptive routing."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass


@dataclass
class ProviderMetrics:
    provider_id: str
    requests: int = 0
    successes: int = 0
    failures: int = 0
    latency_ewma_ms: float | None = None
    first_byte_ewma_ms: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    last_used_at: float | None = None

    @property
    def success_rate(self) -> float:
        # Beta(1, 1) prior gives unseen providers a neutral score of 0.5.
        return (self.successes + 1.0) / (self.requests + 2.0)


class MetricsStore:
    """Thread-safe, process-local routing metrics."""

    def __init__(self) -> None:
        self._records: dict[str, ProviderMetrics] = {}
        self._lock = threading.RLock()

    def get(self, provider_id: str) -> ProviderMetrics:
        with self._lock:
            record = self._records.get(provider_id)
            return ProviderMetrics(**asdict(record)) if record else ProviderMetrics(provider_id)

    def record_success(
        self,
        provider_id: str,
        latency_ms: float,
        *,
        alpha: float,
        first_byte_ms: float | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost: float = 0.0,
    ) -> None:
        with self._lock:
            record = self._records.setdefault(provider_id, ProviderMetrics(provider_id))
            record.requests += 1
            record.successes += 1
            record.latency_ewma_ms = _ewma(record.latency_ewma_ms, latency_ms, alpha)
            if first_byte_ms is not None:
                record.first_byte_ewma_ms = _ewma(record.first_byte_ewma_ms, first_byte_ms, alpha)
            record.input_tokens += input_tokens
            record.output_tokens += output_tokens
            record.estimated_cost += estimated_cost
            record.last_used_at = time.time()

    def record_failure(self, provider_id: str) -> None:
        with self._lock:
            record = self._records.setdefault(provider_id, ProviderMetrics(provider_id))
            record.requests += 1
            record.failures += 1
            record.last_used_at = time.time()

    def records(self) -> list[dict]:
        with self._lock:
            return [
                {**asdict(record), "success_rate": record.success_rate}
                for record in self._records.values()
            ]


def _ewma(previous: float | None, value: float, alpha: float) -> float:
    return value if previous is None else alpha * value + (1.0 - alpha) * previous
