from pydantic import BaseModel, ConfigDict, Field


class DigestSummarySchema(BaseModel):
    """Structured output for one item in the daily digest."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        min_length=1,
        max_length=600,
        description="2-3 sentences. Conservative for political content per PRODUCT.md §5.",
    )
