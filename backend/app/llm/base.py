"""LLM provider boundary.

The architecture must not depend on a specific vendor, so everything downstream
talks to this Protocol. Three implementations ship: Anthropic, OpenAI, and a
deterministic offline stub.

What the LLM is allowed to do here is narrow by design. It composes and
explains; it never adjudicates safety. It is handed a pre-filtered candidate
list and its output is re-validated against the graph afterwards.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when a provider call fails or returns unusable output."""


@runtime_checkable
class LLMClient(Protocol):
    name: str

    async def generate_structured(
        self,
        *,
        schema: type[T],
        system: str,
        user: str,
        max_tokens: int = 2000,
    ) -> T:
        """Return output validated against ``schema``."""
        ...

    async def answer_grounded(
        self,
        *,
        system: str,
        user: str,
        evidence: str,
        max_tokens: int = 700,
    ) -> str:
        """Answer a question using only the supplied evidence."""
        ...
