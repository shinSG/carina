"""Candidate filtering, rule matching, adaptive scoring, and explanations."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

from carina.models import ChatRequest, ProviderProfile, RoutingConfig, RoutingRule
from carina.routing.metrics import MetricsStore


@dataclass
class RankedProvider:
    provider: ProviderProfile
    allowed: bool
    score: float | None = None
    reasons: list[str] = field(default_factory=list)
    matched_rule: str | None = None


class RoutingPolicy:
    """Ranks providers while preserving manual-mode behavior exactly."""

    def __init__(self, metrics: MetricsStore) -> None:
        self._metrics = metrics

    def evaluate(
        self,
        req: ChatRequest,
        providers: list[ProviderProfile],
        active_id: str | None,
        config: RoutingConfig,
        allowed_ids: set[str],
    ) -> list[RankedProvider]:
        if config.mode == "manual":
            return self._manual(providers, active_id, allowed_ids)

        rule = next((r for r in config.rules if _rule_matches(r, req)), None)
        effective_rule = rule
        ranked = [
            self._evaluate_provider(req, provider, active_id, rule, allowed_ids)
            for provider in providers
        ]
        if rule is not None and not rule.strict and not any(item.allowed for item in ranked):
            effective_rule = None
            ranked = [
                self._evaluate_provider(req, provider, active_id, None, allowed_ids)
                for provider in providers
            ]
        if config.mode == "adaptive":
            eligible = [item.provider for item in ranked if item.allowed]
            priority_scores, cost_scores = _relative_scores(eligible)
            for item in ranked:
                if item.allowed:
                    item.score = self._adaptive_score(
                        item.provider,
                        active_id,
                        config,
                        effective_rule,
                        priority_scores[item.provider.id],
                        cost_scores[item.provider.id],
                    )
            ranked.sort(
                key=lambda item: (
                    not item.allowed,
                    -(item.score or 0.0),
                    item.provider.priority,
                    item.provider.name,
                )
            )
        else:
            ranked.sort(
                key=lambda item: (
                    not item.allowed,
                    not _is_preferred(item.provider, effective_rule),
                    item.provider.id != active_id,
                    item.provider.priority,
                    item.provider.name,
                )
            )
        return ranked

    def _manual(
        self,
        providers: list[ProviderProfile],
        active_id: str | None,
        allowed_ids: set[str],
    ) -> list[RankedProvider]:
        ranked = []
        for provider in providers:
            allowed = provider.enabled and provider.id in allowed_ids
            reasons = []
            if not provider.enabled:
                reasons.append("provider disabled")
            elif provider.id not in allowed_ids:
                reasons.append("circuit breaker open")
            else:
                reasons.append("manual mode")
            ranked.append(RankedProvider(provider, allowed, reasons=reasons))
        ranked.sort(
            key=lambda item: (
                not item.allowed,
                item.provider.id != active_id,
                item.provider.priority,
                item.provider.name,
            )
        )
        return ranked

    def _evaluate_provider(
        self,
        req: ChatRequest,
        provider: ProviderProfile,
        active_id: str | None,
        rule: RoutingRule | None,
        allowed_ids: set[str],
    ) -> RankedProvider:
        reasons: list[str] = []
        allowed = True
        if not provider.enabled:
            allowed = False
            reasons.append("provider disabled")
        elif provider.id not in allowed_ids:
            allowed = False
            reasons.append("circuit breaker open")

        if (
            req.model
            and provider.model_patterns
            and not any(
                fnmatch.fnmatchcase(req.model, pattern) for pattern in provider.model_patterns
            )
        ):
            allowed = False
            reasons.append(f"model {req.model!r} not supported")
        if req.stream and provider.capabilities and "streaming" not in provider.capabilities:
            allowed = False
            reasons.append("streaming capability missing")
        if (
            req.max_tokens is not None
            and provider.max_output_tokens is not None
            and req.max_tokens > provider.max_output_tokens
        ):
            allowed = False
            reasons.append("max output tokens exceeded")
        if provider.context_window is not None:
            estimated_input = _estimate_input_tokens(req)
            estimated_total = estimated_input + (req.max_tokens or 0)
            if estimated_total > provider.context_window:
                allowed = False
                reasons.append("estimated context window exceeded")

        if rule is not None:
            if rule.provider_ids and provider.id not in rule.provider_ids:
                allowed = False
                reasons.append("not selected by strict provider list")
            if rule.require_tags and not rule.require_tags.issubset(provider.tags):
                allowed = False
                reasons.append("required tags missing")
            if rule.strict and rule.prefer_tags and not (rule.prefer_tags & provider.tags):
                allowed = False
                reasons.append("preferred tags required by strict rule")
            if allowed:
                reasons.append(f"matched rule {rule.name!r}")
        elif allowed:
            reasons.append("default smart-routing policy")

        if provider.id == active_id and allowed:
            reasons.append("active provider bonus")
        return RankedProvider(
            provider,
            allowed,
            reasons=reasons,
            matched_rule=rule.name if rule else None,
        )

    def _adaptive_score(
        self,
        provider: ProviderProfile,
        active_id: str | None,
        config: RoutingConfig,
        rule: RoutingRule | None,
        priority_score: float,
        cost_score: float,
    ) -> float:
        metrics = self._metrics.get(provider.id)
        latency = metrics.first_byte_ewma_ms or metrics.latency_ewma_ms
        latency_score = (
            0.5
            if latency is None
            else config.latency_target_ms / (config.latency_target_ms + latency)
        )
        preference_score = 1.0 if _is_preferred(provider, rule) else 0.5
        weights = config.weights
        total_weight = (
            weights.success_rate
            + weights.latency
            + weights.priority
            + weights.cost
            + weights.preference
        ) or 1.0
        score = (
            weights.success_rate * metrics.success_rate
            + weights.latency * latency_score
            + weights.priority * priority_score
            + weights.cost * cost_score
            + weights.preference * preference_score
        ) / total_weight
        if provider.id == active_id:
            score += config.active_provider_bonus
        return round(score, 6)


def _rule_matches(rule: RoutingRule, req: ChatRequest) -> bool:
    if not rule.enabled:
        return False
    if rule.stream is not None and rule.stream != req.stream:
        return False
    if rule.model_patterns:
        if not req.model:
            return False
        if not any(fnmatch.fnmatchcase(req.model, pattern) for pattern in rule.model_patterns):
            return False
    return True


def _is_preferred(provider: ProviderProfile, rule: RoutingRule | None) -> bool:
    return bool(rule and rule.prefer_tags and rule.prefer_tags & provider.tags)


def _relative_scores(
    providers: list[ProviderProfile],
) -> tuple[dict[str, float], dict[str, float]]:
    """Normalize priority and known prices across the currently eligible set."""
    priorities = [provider.priority for provider in providers]
    priority_min = min(priorities, default=0)
    priority_max = max(priorities, default=0)
    priority_span = priority_max - priority_min
    priority_scores = {
        provider.id: (
            1.0 if priority_span == 0 else 1.0 - (provider.priority - priority_min) / priority_span
        )
        for provider in providers
    }

    known_costs = {
        provider.id: provider.input_cost_per_million + provider.output_cost_per_million
        for provider in providers
        if provider.input_cost_per_million is not None
        and provider.output_cost_per_million is not None
    }
    cost_min = min(known_costs.values(), default=0.0)
    cost_max = max(known_costs.values(), default=0.0)
    cost_span = cost_max - cost_min
    cost_scores = {}
    for provider in providers:
        cost = known_costs.get(provider.id)
        if cost is None:
            cost_scores[provider.id] = 0.5
        elif cost_span == 0:
            cost_scores[provider.id] = 1.0
        else:
            cost_scores[provider.id] = 1.0 - (cost - cost_min) / cost_span
    return priority_scores, cost_scores


def _estimate_input_tokens(req: ChatRequest) -> int:
    """Conservative tokenizer-free estimate used only for capacity filtering."""
    chars = len(req.system or "") + sum(len(message.content) for message in req.messages)
    return max(1, (chars + 3) // 4)
