"""Tests for :mod:`job_hunt_agent.steps_view` (FR-17 AC1).

Related: FR-17 AC1, D-19
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from job_hunt_agent.steps_view import (
    StepRow,
    build_turn_steps,
    compact_args,
    is_user_turn_message,
    short_result_for_message,
    split_into_turns,
)

# ---------------------------------------------------------------------------
# is_user_turn_message / split_into_turns
# ---------------------------------------------------------------------------


def test_is_user_turn_message_excludes_injected_context_messages() -> None:
    assert is_user_turn_message(HumanMessage("find python jobs"))
    assert not is_user_turn_message(HumanMessage("profile stuff", name="profile_context"))
    assert not is_user_turn_message(HumanMessage("memory stuff", name="memory_context"))
    assert not is_user_turn_message(HumanMessage(""))  # empty content, never a bubble
    assert not is_user_turn_message(AIMessage("not a human message"))


def test_split_into_turns_groups_by_real_human_message() -> None:
    messages = [
        HumanMessage("first"),
        HumanMessage("profile ctx", name="profile_context"),
        AIMessage("first reply"),
        HumanMessage("second"),
        AIMessage("second reply"),
    ]
    turns = split_into_turns(messages)
    assert [m.content for m in turns[0]] == ["first", "profile ctx", "first reply"]
    assert [m.content for m in turns[1]] == ["second", "second reply"]


def test_split_into_turns_drops_messages_before_the_first_real_human_message() -> None:
    messages = [HumanMessage("ctx", name="memory_context"), HumanMessage("hi")]
    turns = split_into_turns(messages)
    assert len(turns) == 1
    assert turns[0][0].content == "hi"


def test_split_into_turns_empty_input() -> None:
    assert split_into_turns([]) == []


# ---------------------------------------------------------------------------
# compact_args
# ---------------------------------------------------------------------------


def test_compact_args_renders_short_dict_in_full() -> None:
    assert compact_args({"keywords": "Python", "location": "Hamburg"}) == (
        '{"keywords": "Python", "location": "Hamburg"}'
    )


def test_compact_args_truncates_long_values() -> None:
    text = compact_args({"note": "x" * 200})
    assert len(text) == 100
    assert text.endswith("…")


def test_compact_args_renders_non_ascii_unescaped() -> None:
    text = compact_args({"location": "München"})
    assert "München" in text
    assert "\\u00fc" not in text


# ---------------------------------------------------------------------------
# short_result_for_message
# ---------------------------------------------------------------------------


def _tool_message(tool: str, content: str, status: str = "success") -> ToolMessage:
    return ToolMessage(content=content, tool_call_id="call_1", name=tool, status=status)


def test_short_result_search_jobs() -> None:
    msg = _tool_message(
        "search_jobs",
        '{"tool": "search_jobs", "result": {"total": 103, '
        '"listings": [{}, {}]}, "notes": [], "not_applicable_reason": null}',
    )
    assert short_result_for_message(msg) == "103 results, 2 returned"


def test_short_result_get_job_details_success() -> None:
    msg = _tool_message(
        "get_job_details",
        '{"tool": "get_job_details", "result": {"title": "x"}, "notes": [], '
        '"not_applicable_reason": null}',
    )
    assert short_result_for_message(msg) == "details loaded"


def test_short_result_get_job_details_not_available() -> None:
    msg = _tool_message(
        "get_job_details",
        '{"tool": "get_job_details", "result": null, "notes": [], '
        '"not_applicable_reason": "Listing X is no longer available."}',
    )
    assert short_result_for_message(msg) == "Listing X is no longer available."


def test_short_result_assess_fit() -> None:
    msg = _tool_message(
        "assess_fit",
        '{"tool": "assess_fit", "result": {"assessed": [{}, {}, {}], "dropped_evidence": 0}, '
        '"notes": [], "not_applicable_reason": null}',
    )
    assert short_result_for_message(msg) == "3 listings assessed"


def test_short_result_save_to_tracker_reflects_status() -> None:
    msg = _tool_message(
        "save_to_tracker",
        '{"tool": "save_to_tracker", "result": {"status": "applied"}, "notes": [], '
        '"not_applicable_reason": null}',
    )
    assert short_result_for_message(msg) == "applied"


def test_short_result_remember_success() -> None:
    msg = _tool_message(
        "remember",
        '{"tool": "remember", "result": {"kind": "preference", "value": "remote only"}, '
        '"notes": [], "not_applicable_reason": null}',
    )
    assert short_result_for_message(msg) == "saved"


def test_short_result_list_tracker() -> None:
    msg = _tool_message(
        "list_tracker",
        '{"tool": "list_tracker", "result": {"entries": [{}, {}, {}, {}]}, "notes": [], '
        '"not_applicable_reason": null}',
    )
    assert short_result_for_message(msg) == "4 entries"


def test_short_result_hitl_rejection_is_plain_text_not_json() -> None:
    msg = _tool_message(
        "save_to_tracker",
        "User rejected the tool call for `save_to_tracker` with id call_1. "
        "The tool was not executed.",
        status="error",
    )
    assert short_result_for_message(msg) == "rejected"


def test_short_result_falls_back_when_json_is_not_an_object() -> None:
    msg = _tool_message("search_jobs", "[1, 2, 3]")
    assert short_result_for_message(msg) == "[1, 2, 3]"


def test_short_result_done_when_no_result_and_no_reason() -> None:
    msg = _tool_message("search_jobs", '{"tool": "search_jobs"}')
    assert short_result_for_message(msg) == "done"


def test_short_result_done_for_an_unrecognised_tool_name() -> None:
    msg = _tool_message("some_future_tool", '{"tool": "some_future_tool", "result": {}}')
    assert short_result_for_message(msg) == "done"


def test_short_result_falls_back_to_truncated_plain_text() -> None:
    msg = _tool_message(
        "get_job_details",
        "Error: get_job_details is not a valid tool, try one of [search_jobs].",
        status="error",
    )
    assert short_result_for_message(msg) == (
        "Error: get_job_details is not a valid tool, try one of [search_jobs]."
    )


# ---------------------------------------------------------------------------
# build_turn_steps
# ---------------------------------------------------------------------------


def _tool_result_json(tool: str, result: dict[str, object]) -> str:
    import json

    return json.dumps({"tool": tool, "result": result, "notes": [], "not_applicable_reason": None})


def test_build_turn_steps_single_call() -> None:
    call_id = "call_1"
    turn = [
        HumanMessage("find python jobs"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search_jobs", "args": {"keywords": "Python"}, "id": call_id}],
        ),
        ToolMessage(
            content=_tool_result_json("search_jobs", {"total": 5, "listings": [{}]}),
            tool_call_id=call_id,
            name="search_jobs",
        ),
        AIMessage("Here is what I found."),
    ]
    rows = build_turn_steps(turn, durations={call_id: 1.23})
    assert rows == [
        StepRow(
            tool="search_jobs",
            args_text='{"keywords": "Python"}',
            short_result="5 results, 1 returned",
            duration_seconds=1.23,
            parallel=False,
        )
    ]


def test_build_turn_steps_parallel_calls_are_both_flagged() -> None:
    turn = [
        HumanMessage("search two things"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "search_jobs", "args": {"keywords": "a"}, "id": "c1"},
                {"name": "search_jobs", "args": {"keywords": "b"}, "id": "c2"},
            ],
        ),
        ToolMessage(
            content=_tool_result_json("search_jobs", {"total": 1, "listings": [{}]}),
            tool_call_id="c1",
            name="search_jobs",
        ),
        ToolMessage(
            content=_tool_result_json("search_jobs", {"total": 2, "listings": [{}, {}]}),
            tool_call_id="c2",
            name="search_jobs",
        ),
    ]
    rows = build_turn_steps(turn)
    assert len(rows) == 2
    assert all(row.parallel for row in rows)
    assert rows[0].short_result == "1 results, 1 returned"
    assert rows[1].short_result == "2 results, 2 returned"


def test_build_turn_steps_not_applicable_reason() -> None:
    turn = [
        HumanMessage("get details"),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_job_details", "args": {"referenznummer": "X"}, "id": "c1"}],
        ),
        ToolMessage(
            content='{"tool": "get_job_details", "result": null, "notes": [], '
            '"not_applicable_reason": "Listing X is no longer available."}',
            tool_call_id="c1",
            name="get_job_details",
        ),
    ]
    rows = build_turn_steps(turn)
    assert rows[0].short_result == "Listing X is no longer available."


def test_build_turn_steps_missing_tool_message_is_pending() -> None:
    turn = [
        HumanMessage("save it"),
        AIMessage(
            content="",
            tool_calls=[{"name": "save_to_tracker", "args": {"referenznummer": "X"}, "id": "c1"}],
        ),
        # No ToolMessage yet - the HITL interrupt is still pending.
    ]
    rows = build_turn_steps(turn)
    assert len(rows) == 1
    assert rows[0].short_result is None
    assert rows[0].duration_seconds is None


def test_build_turn_steps_no_duration_for_an_unknown_call_id() -> None:
    """A resumed older thread's calls are never in this session's duration dict."""
    turn = [
        HumanMessage("find python jobs"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search_jobs", "args": {}, "id": "old_call"}],
        ),
        ToolMessage(
            content=_tool_result_json("search_jobs", {"total": 1, "listings": [{}]}),
            tool_call_id="old_call",
            name="search_jobs",
        ),
    ]
    rows = build_turn_steps(turn, durations={})
    assert rows[0].duration_seconds is None


def test_build_turn_steps_skips_final_answer_without_tool_calls() -> None:
    turn = [HumanMessage("hello"), AIMessage("hi there, no tools needed")]
    assert build_turn_steps(turn) == []
