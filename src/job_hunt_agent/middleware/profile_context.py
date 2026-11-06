"""Loads the user's profile into the agent's context at thread start (FR-01 AC4).

The profile is injected at invoke time (``AgentContext.profile``), not baked
into the static ``prompts/system.md`` text, so the model never sees it
unless something puts it into the conversation. This middleware does
that once per thread, so autonomous search refinement (FR-03 AC1 - narrow
using the profile's skills, seniority and radius before asking the user)
has something to narrow *with*.

Related: FR-01 AC4, FR-03 AC1
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

from job_hunt_agent.context import AgentContext
from job_hunt_agent.models import Profile
from job_hunt_agent.state import JobHuntState


def profile_context_message(profile: Profile) -> HumanMessage:
    """Builds the one-off context message describing the profile.

    A plain message (not a second system message - provider support for
    more than one is inconsistent) clearly labelled as context, not a real
    user utterance, so the model does not mistake it for something the
    person just said.
    """
    text = (
        "[Context, not a message from the user - the selected user's stored "
        "profile, for your own reference when searching and assessing fit]\n"
        f"Skills: {', '.join(profile.skills) or '(none given)'}\n"
        f"Seniority: {profile.seniority}\n"
        f"Location: {profile.location}\n"
        f"Preferred radius: {profile.radius_km} km\n"
        f"Remote preference: {profile.remote_preference}\n"
        f"Wants full-time: {profile.wants_full_time}\n"
        f"Wants a permanent contract: {profile.wants_permanent}\n"
        f"Excludes temporary agency work: {profile.exclude_temp_agency}\n"
        f"German level: {profile.german_level}\n"
        f"English level: {profile.english_level}"
    )
    return HumanMessage(content=text, name="profile_context")


class LoadProfileContextMiddleware(AgentMiddleware):
    """Injects :func:`profile_context_message` once, on a thread's first model call.

    Detected by ``len(state["messages"]) == 1`` - only the thread-opening
    ``HumanMessage`` is present yet; every later turn already has this
    message in its history, so nothing is injected again.

    Related: FR-01 AC4, FR-03 AC1
    """

    state_schema = JobHuntState

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        messages = state["messages"]
        if len(messages) != 1:
            return None
        context: AgentContext = runtime.context
        return {"messages": [profile_context_message(context.profile)]}
