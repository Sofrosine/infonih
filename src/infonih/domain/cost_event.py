from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CostEvent(BaseModel):
    """One LLM call's cost record. Append-only audit log used by /cost."""

    model_config = ConfigDict(frozen=True)

    id: int
    user_id: UUID | None = None
    flow: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_creation_input_tokens: int = Field(default=0, ge=0)
    cache_read_input_tokens: int = Field(default=0, ge=0)
    cost_usd: Decimal
    article_id: UUID | None = None
    created_at: datetime


class CostSummary(BaseModel):
    """Aggregate over a time window. `flow` is None for grand totals."""

    model_config = ConfigDict(frozen=True)

    flow: str | None = None
    call_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
