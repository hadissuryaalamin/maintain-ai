"""Versioned model pricing lookup and cost calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.llm.base import ProviderUsage


class PricingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    effective_from: date
    verified_at: date
    source_url: str
    input_per_million_tokens: Decimal = Field(ge=0)
    cached_input_per_million_tokens: Decimal = Field(ge=0)
    cache_write_multiplier: Decimal = Field(default=Decimal("1"), ge=0)
    output_per_million_tokens: Decimal = Field(ge=0)
    notes: str = ""


class PricingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    currency: str = "USD"
    unit: str = "per_1m_tokens"
    entries: list[PricingEntry]


@dataclass(frozen=True, slots=True)
class CostEstimate:
    input_cost: Decimal | None
    output_cost: Decimal | None
    total_cost: Decimal | None
    pricing_version: str | None


class PricingCatalog:
    def __init__(self, config: PricingConfig | None) -> None:
        self.config = config

    @classmethod
    def load(cls, path: Path) -> PricingCatalog:
        if not path.exists():
            return cls(None)
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        return cls(PricingConfig.model_validate(raw))

    def find(self, *, provider: str, model: str, at: datetime) -> PricingEntry | None:
        if self.config is None:
            return None
        eligible = [
            entry
            for entry in self.config.entries
            if entry.provider == provider
            and entry.model == model
            and entry.effective_from <= at.date()
        ]
        if not eligible:
            return None
        return max(eligible, key=lambda entry: entry.effective_from)

    def calculate(
        self,
        *,
        provider: str,
        model: str,
        usage: ProviderUsage,
        at: datetime,
    ) -> CostEstimate:
        entry = self.find(provider=provider, model=model, at=at)
        config = self.config
        if (
            entry is None
            or config is None
            or usage.input_tokens is None
            or usage.output_tokens is None
        ):
            return CostEstimate(None, None, None, None)

        million = Decimal(1_000_000)
        cached = max(usage.cached_input_tokens or 0, 0)
        cache_write = max(usage.cache_write_tokens or 0, 0)
        uncached = max(usage.input_tokens - cached - cache_write, 0)
        input_cost = (
            Decimal(uncached) * entry.input_per_million_tokens
            + Decimal(cached) * entry.cached_input_per_million_tokens
            + Decimal(cache_write) * entry.input_per_million_tokens * entry.cache_write_multiplier
        ) / million
        output_cost = Decimal(usage.output_tokens) * entry.output_per_million_tokens / million
        input_cost = input_cost.quantize(Decimal("0.00000001"))
        output_cost = output_cost.quantize(Decimal("0.00000001"))
        return CostEstimate(
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=(input_cost + output_cost).quantize(Decimal("0.00000001")),
            pricing_version=(
                f"{config.schema_version}:{entry.model}:{entry.effective_from.isoformat()}"
            ),
        )
