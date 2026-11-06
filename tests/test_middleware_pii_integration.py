"""PII middleware wired into a real agent run, on tool results (FR-22 AC2).

``test_middleware.py`` covers ``detect_phone_pii`` in isolation; this file
checks the full ``PIIMiddleware(apply_to_tool_results=True)`` wiring
(``pii_guard.build_pii_middlewares``) actually redacts a tool's output
inside a running agent, and that it never touches a bare reference number.

Related: FR-22 AC1, FR-22 AC2, FR-22 AC5
"""

from __future__ import annotations

from typing import Any

from conftest import ScriptedModel
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from job_hunt_agent.middleware.pii_guard import build_pii_middlewares


@tool
def echo_contact_info(text: str) -> str:
    """Echoes back whatever text it is given (test double, not a real tool)."""
    return text


def _run(echoed_text: str) -> str:
    agent = create_agent(
        model=ScriptedModel(
            [[{"name": "echo_contact_info", "args": {"text": echoed_text}}], "done"]
        ),
        tools=[echo_contact_info],
        middleware=build_pii_middlewares(),
        checkpointer=InMemorySaver(),
    )
    result: dict[str, Any] = agent.invoke(
        {"messages": [HumanMessage("echo it")]},
        config={"configurable": {"thread_id": "t1"}},
    )
    tool_message = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    return str(tool_message.content)


def test_pii_middleware_redacts_email_in_a_tool_result() -> None:
    """FR-22 AC2: an e-mail address in a tool result is redacted."""
    content = _run("Contact us at jobs@example-gmbh.de for more info.")
    assert "jobs@example-gmbh.de" not in content
    assert "REDACTED" in content.upper()


def test_pii_middleware_redacts_phone_with_context_in_a_tool_result() -> None:
    """FR-22 AC2: a phone number with context in a tool result is redacted."""
    content = _run("Bei Rueckfragen:\nTelefon: 040 / 123 456 78")
    assert "123 456 78" not in content
    assert "REDACTED" in content.upper()


def test_pii_middleware_never_redacts_a_bare_reference_number() -> None:
    """FR-22 AC5: the exact D-1 regression - a reference number is never touched."""
    content = _run("Referenznummer dieser Anzeige: 19522-0068291613-S")
    assert "19522-0068291613-S" in content
