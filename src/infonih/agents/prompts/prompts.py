"""Prompt loader.

Templates live as `.md` files under `agents/prompts/templates/`. Each loaded
template declares its input variables explicitly so missing values fail loudly
at format time rather than producing a silently broken prompt.
"""

from pathlib import Path
from typing import Any

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class PromptTemplate:
    """A `.md` template plus a declared list of input variables."""

    def __init__(self, name: str, input_variables: list[str]) -> None:
        self.name = name
        self.input_variables = input_variables
        path = _TEMPLATES_DIR / f"{name}.md"
        self._raw = path.read_text(encoding="utf-8")

    def format(self, **kwargs: Any) -> str:
        missing = set(self.input_variables) - set(kwargs)
        if missing:
            raise ValueError(f"prompt {self.name!r} missing variables: {sorted(missing)}")
        return self._raw.format(**kwargs)


SCORE_ARTICLE = PromptTemplate(
    "score_article",
    input_variables=[
        "interests",
        "source_name",
        "source_category",
        "title",
        "content",
        "recent_reactions",
    ],
)

SUMMARIZE_FOR_DIGEST = PromptTemplate(
    "summarize_for_digest",
    input_variables=["title", "source_name", "source_category", "content"],
)
