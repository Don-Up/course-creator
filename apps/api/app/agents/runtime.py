"""Factory that turns a provider name into an agent implementation.

Phase 1 ships exactly one implementation -- the fake runtime -- so the
factory refuses every other name instead of falling back to a provider that
does not exist yet.
"""

from __future__ import annotations

from app.agents.fake_runtime import FakeProvider
from app.agents.protocols import CourseAgent


def create_course_agent(
    provider_name: str | None = None,
    model_name: str | None = None,
) -> CourseAgent:
    """Return the agent implementation for `provider_name`.

    `model_name` belongs to the signature for the providers of the later
    phases; the fake runtime has no model, so it is accepted and ignored.

    Phase 1 has no real provider, and `AGENTS.md` forbids adding one before
    its phase.  The factory therefore refuses every name except `fake` --
    including the default, so that a caller cannot silently end up with a
    provider that does not exist.
    """
    if provider_name is not None and provider_name.lower() == "fake":
        return FakeProvider()
    raise NotImplementedError(
        f"Provider {provider_name!r} is not available in Phase 1; "
        "only 'fake' is implemented."
    )
