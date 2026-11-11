"""Custom agent state (spec §5.3).

The model can propose several tool calls in one step (parallel tool
calling, D-19). When two of those calls update the same field, LangGraph's
default "last value wins" channel raises ``InvalidUpdateError`` instead of
silently picking one (``seen_refs``/``summaries``/``assessments``/
``shortlist`` all hit this in WP-10/WP-11). Every field below that more
than one tool can write in the same step therefore carries an
``Annotated[..., reducer]`` that folds several same-step updates into one
value. Each reducer is written so that, for a single call per step (the
previous behaviour), ``reducer(existing, new) == new`` - the tool still
reads the current value and writes back the already-merged result, so
nothing changes when only one tool call touches the field.

Related: spec §5.3, FR-02 AC5, FR-04 AC3, FR-05 AC5, FR-10 AC3, FR-20 AC1, D-19
"""

from __future__ import annotations

from typing import Annotated, NamedTuple, NotRequired

from langchain.agents.middleware import AgentState

from job_hunt_agent.models import FitAssessment, JobSummary


def merge_refs(existing: list[str], new: list[str]) -> list[str]:
    """Order-preserving union, for fields where every write only adds refs.

    ``new`` is the full, already-merged value the tool computed (it read
    ``existing`` itself before writing); for a single write, ``new`` is a
    superset of ``existing``, so the union below returns exactly ``new``,
    sorted the same way the caller already sorted it. For two same-step
    writes, both read the same pre-step ``existing``, so folding them
    together (in either order - this reducer is commutative) yields their
    union with no duplicates.

    Related: FR-02 AC5, D-19
    """
    return sorted(set(existing) | set(new))


def merge_dicts[V](existing: dict[str, V], new: dict[str, V]) -> dict[str, V]:
    """Dict union, for fields where every write only adds or updates entries.

    Same reasoning as :func:`merge_refs`: a single write already contains
    ``existing`` plus its own additions, so this is a no-op for the
    single-call case. Two same-step writes (e.g. two ``assess_fit`` calls on
    disjoint referenznummern) merge without needing to touch each other's
    keys; the only risk - two calls assessing the *same* ref differently in
    one step - cannot happen here (``assess_fit`` would have to be given the
    same referenznummer twice by the model in one step) and is left as a
    last-write-wins tie-break, same as the sequential case today.

    Related: FR-02 AC5, FR-05 AC5, D-19
    """
    return {**existing, **new}


class ShortlistEdit(NamedTuple):
    """A tagged ``shortlist`` update: refs to add, refs to remove.

    ``shortlist`` has two writers with opposite-direction semantics:
    ``assess_fit`` only appends (FR-05 AC5), ``get_job_details`` only
    removes, on a 404 (FR-04 AC3). Neither is a subset/superset of the
    other, so a plain union or intersection reducer would break one of
    them (e.g. a union would resurrect a ref ``get_job_details`` just
    removed). Tagging each write as "add this" or "remove this" instead of
    "the new full list" lets the reducer apply both correctly regardless of
    which one runs first in a step: removal always drops a ref from the
    current list, addition always appends a ref that is not already in it.
    Related: FR-04 AC3, FR-05 AC5, D-19
    """

    add: tuple[str, ...] = ()
    remove: tuple[str, ...] = ()


def merge_shortlist(existing: list[str], edit: ShortlistEdit | list[str]) -> list[str]:
    """Applies one tagged add/remove edit to the shortlist (see :class:`ShortlistEdit`).

    For a single tool write this reproduces today's behaviour exactly:
    ``assess_fit``'s edit is ``ShortlistEdit(add=(...))`` (append, skip refs
    already present); ``get_job_details``'s 404 edit is
    ``ShortlistEdit(remove=(ref,))``. For two same-step writes, applying
    them in either order gives the same result as long as no ref is both
    added and removed in the same step - which cannot happen, since
    ``get_job_details`` only removes a ref it just confirmed as 404, and
    ``assess_fit`` fetches details itself and would skip (never add) that
    same ref instead.

    A plain ``list[str]`` (not a :class:`ShortlistEdit`) is treated as a
    direct replacement instead of an edit: this is the shape state-seeding
    callers use (``agent.invoke``'s initial state dict, ``agent.update_state``
    in tests) - a single, non-concurrent write where "replace" is the only
    sensible meaning, same as before this field had a reducer at all.

    Related: FR-04 AC3, FR-05 AC5, D-19
    """
    if not isinstance(edit, ShortlistEdit):
        return list(edit)
    result = [ref for ref in existing if ref not in edit.remove]
    for ref in edit.add:
        if ref not in result:
            result.append(ref)
    return result


class JobHuntState(AgentState):
    """Adds the job-hunt-specific fields of spec §5.3 to the base agent state.

    Attributes:
        user_id: The selected user (no authentication, spec §2.2). Set once
            per thread before the first model call; no tool writes it, so
            it keeps plain overwrite semantics.
        seen_refs: Reference numbers already returned to the model in this
            thread (FR-02 AC5); a later ``search_jobs`` call marks these
            ``seen: true`` instead of re-introducing them as new. Written
            only by ``search_jobs`` (append-only), merged with
            :func:`merge_refs`.
        summaries: Search-time :class:`JobSummary` objects keyed by
            reference number, kept for every ref in ``seen_refs``. **Not in
            §5.3's field list** - added because ``distance_km`` only exists
            on ``JobSummary`` (never on ``JobDetails``), so without this,
            ``assess_fit`` would have no way to feed FR-06 AC2's distance
            check or the rubric's location/remote dimension; FR-06 AC3
            ("missing value never excludes") already makes this degrade
            gracefully if a referenznummer was never searched for
            in this thread (e.g. the model got it from elsewhere). Written
            only by ``search_jobs`` (adds/updates entries, never removes),
            merged with :func:`merge_dicts`.
        shortlist: Reference numbers currently on the shortlist. Written by
            ``assess_fit`` (adds) and ``get_job_details`` (removes on a
            404, FR-04 AC3); merged with :func:`merge_shortlist` - see
            :class:`ShortlistEdit` for why a plain union/intersection
            reducer does not work here.
        assessments: Fit assessments keyed by reference number (FR-05 AC5),
            read by follow-up questions without a new tool call (FR-08 AC1).
            Written only by ``assess_fit`` (adds/updates entries, never
            removes), merged with :func:`merge_dicts`.
        rejected_actions: Hashes of ``(tool_name, args)`` for write actions
            already rejected in this thread (FR-10 AC3); recomputed in full
            from the message history on every model call, not accumulated,
            by ``RejectionLockMiddleware`` - the only writer, so this keeps
            plain overwrite semantics.
    """

    user_id: NotRequired[str]
    seen_refs: NotRequired[Annotated[list[str], merge_refs]]
    summaries: NotRequired[Annotated[dict[str, JobSummary], merge_dicts]]
    shortlist: NotRequired[Annotated[list[str], merge_shortlist]]
    assessments: NotRequired[Annotated[dict[str, FitAssessment], merge_dicts]]
    rejected_actions: NotRequired[list[str]]
