from __future__ import annotations

from pydantic import BaseModel


class InvocationMetrics(BaseModel):
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: int | None = None
    estimated_cost_microusd: int | None = None
    pricing_version: str | None = None
    response_status: str | None = None


class TextInvocation(BaseModel):
    text: str
    metrics: InvocationMetrics


class BudgetPolicy(BaseModel):
    max_total_tokens: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_model_calls: int | None = None
    max_estimated_cost_microusd: int | None = None
