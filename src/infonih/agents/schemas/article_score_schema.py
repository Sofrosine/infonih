from pydantic import BaseModel, ConfigDict, Field


class ArticleScoreSchema(BaseModel):
    """Structured output schema for the article scoring chain.

    Per FLOWS.md §185, the LLM returns score (0-100), reasoning (auditable),
    and a low-content-confidence flag for entries with thin raw_content.
    """

    model_config = ConfigDict(extra="forbid")

    score: int = Field(
        ge=0, le=100, description="Relevance score from 0 (skip) to 100 (must-read)."
    )
    reasoning: str = Field(
        min_length=1,
        max_length=500,
        description="2-3 sentences explaining the score.",
    )
    low_content_confidence: bool = Field(
        default=False,
        description="True when raw_content was missing or too short to score reliably.",
    )
