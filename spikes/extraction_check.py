"""Spike D-4: is openai/gpt-5-mini good enough for extraction and tool calling?

Compares the default model against one alternative, anthropic/claude-haiku-4.5,
both restricted to zero-data-retention (ZDR) provider routing (spec §5.5). Two
questions:

  (a) Structured extraction: does the model turn a German ad text into a valid
      JobRequirements (spec §6.2), with evidence quotes that are verbatim
      substrings of the (cleaned) ad text?
  (b) Tool calling: does the model pick the right tool and arguments for a
      search request, and correctly call no tool for an off-topic request?

The ad-text cleaning in :func:`clean_ad_text` is a throwaway approximation of
FR-22 AC1 for this spike only; the real implementation lives in ``pii.py``
(not yet built). ZDR routing is never relaxed: if a model has no ZDR
endpoint, the call fails and the failure is recorded as a fact for D-4.

Call (in the project folder, needs OPENROUTER_API_KEY):
    uv run python spikes/extraction_check.py

Result:
    spikes/fixtures/d4/*.json   Raw request/response records (contain ad text,
                                 gitignored, see D-3)
    spikes/d4_results.json      Aggregated numbers, no ad text (committed)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from job_hunt_agent import config

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
DETAILS_DIR = FIXTURES_DIR / "details"
RAW_OUT_DIR = FIXTURES_DIR / "d4"
RESULTS_PATH = Path(__file__).resolve().parent / "d4_results.json"

MODELS: tuple[str, ...] = (config.CHAT_MODEL, "anthropic/claude-haiku-4.5")
RUNS_PER_LISTING = 2

#: Five listings chosen for length spread and the required special cases:
#: a teaser with an external URL, a temporary-agency listing with a contact
#: name in the free text, and one with a missing ``istArbeitnehmerUeberlassung``.
LISTING_FILES: tuple[str, ...] = (
    "12336-a26f1192j0455715-s.json",  # 284 chars, teaser, externeURL
    "13545-dztbhcdpfnhf7dsr-s.json",  # 4249 chars, temp agency, contact name
    "19522-0068291613-s.json",  # 3813 chars
    "19913-3087851793401200-s.json",  # 6790 chars
    "10001-1003893191-s.json",  # 9712 chars, zeitarbeit missing
)

#: The listing whose "before -> after" cleaning result is shown in the summary.
CONTACT_NAME_LISTING = "13545-dztbhcdpfnhf7dsr-s.json"

# ---------------------------------------------------------------------------
# Ad-text cleaning, a spike-only approximation of FR-22 AC1
# ---------------------------------------------------------------------------

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_PATTERN = re.compile(r"(?:\+49|0049|\b0)[\d\s/()-]{6,}\d")
CONTACT_HEADER_PATTERN = re.compile(r"^(ihr\s+)?(ansprechpartner|kontakt)\b", re.I)
NAME_LINE_PATTERN = re.compile(r"^(frau|herrn?)\s+[a-zäöüß]+(\s+[a-zäöüß]+)?\s*$", re.I)


def clean_ad_text(text: str) -> str:
    """Mask e-mail/phone and drop the contact block (FR-22 AC1, spike approximation).

    Related: FR-22 AC1
    """
    text = EMAIL_PATTERN.sub("[email masked]", text)
    text = PHONE_PATTERN.sub("[phone masked]", text)
    kept = [
        line
        for line in text.split("\n")
        if not CONTACT_HEADER_PATTERN.match(line.strip())
        and not NAME_LINE_PATTERN.match(line.strip())
    ]
    return "\n".join(kept)


# ---------------------------------------------------------------------------
# JobRequirements schema (spec §6.2), local to this spike
# ---------------------------------------------------------------------------


class Requirement(BaseModel):
    name: str
    required: bool
    evidence_de: str = Field(description="Verbatim quote from the ad text.")
    evidence_en: str = Field(description="English translation of evidence_de.")


class JobRequirements(BaseModel):
    """Local copy of spec §6.2 for the spike; the real schema lives in models.py."""

    referenznummer: str
    skills: list[Requirement]
    seniority: Literal["junior", "mid", "senior", "lead", "not_mentioned"]
    seniority_evidence: str | None = None
    german_level: Literal["none", "basic", "fluent", "native", "not_mentioned"]
    german_level_evidence: str | None = None
    english_required: bool | None
    summary_en: str = Field(description="At most 3 sentences.")


EXTRACTION_PROMPT = """\
You extract structured job requirements from a German job ad for an English-speaking
software developer. Every evidence quote (evidence_de, seniority_evidence,
german_level_evidence) MUST be a verbatim substring of the ad text below - copy it
character for character, do not paraphrase or translate it. Give each evidence_de its
own evidence_en translation. If something is not mentioned, use "not_mentioned" (for
seniority/german_level) or null (for english_required) rather than guessing.

referenznummer: {referenznummer}

Ad text:
---
{ad_text}
---
"""

# ---------------------------------------------------------------------------
# Dummy search_jobs tool (spec FR-02 signature)
# ---------------------------------------------------------------------------


@tool
def search_jobs(
    keywords: str,
    location: str,
    radius_km: int,
    published_within_days: int,
    exclude_temp_agency: bool,
    page: int = 1,
) -> dict[str, Any]:
    """Search the BA job board for listings matching keywords and location."""
    return {
        "tool": "search_jobs",
        "result": {"total": 12, "listings": []},
        "notes": [],
        "not_applicable_reason": None,
    }


TOOL_SYSTEM_PROMPT = (
    "You are the Job Hunt Agent. You have one tool, search_jobs, to search the German "
    "Federal Employment Agency job board. Call it whenever the user wants to search for "
    "jobs. For anything unrelated to job search, do not call any tool and answer briefly "
    "that you can only help with job search."
)

TOOL_CALLING_REQUESTS: tuple[str, ...] = (
    "Python jobs in Hamburg, no temp agencies",
    "AI roles in Berlin from this week",
    "What's the weather?",
)


# ---------------------------------------------------------------------------
# Model client
# ---------------------------------------------------------------------------


def build_chat_model(model: str) -> ChatOpenAI:
    """Build a ZDR-routed OpenRouter chat model; never relaxed (spec §5.5)."""
    api_key = SecretStr(_get_api_key())
    return ChatOpenAI(
        model=model,
        base_url=config.OPENROUTER_BASE_URL,
        api_key=api_key,
        timeout=config.OPENROUTER_TIMEOUT_SECONDS,
        max_retries=0,
        extra_body={
            "reasoning": {"effort": config.REASONING_EFFORT},
            "provider": config.PROVIDER_PREFERENCES,  # ZDR - never relaxed
        },
    )


def _get_api_key() -> str:
    import os

    key = os.getenv(config.OPENROUTER_API_KEY_ENV, "").strip()
    if not key:
        raise RuntimeError(f"{config.OPENROUTER_API_KEY_ENV} is not set in the environment.")
    return key


def call_with_single_retry(call: Any) -> Any:
    """Run one call, retrying once after 2s on a likely-transient error."""
    try:
        return call()
    except Exception:  # noqa: BLE001 - spike: record and retry once, then re-raise
        time.sleep(2.0)
        return call()


# ---------------------------------------------------------------------------
# Result records
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    model: str
    referenznummer: str
    listing_file: str
    run: int
    valid: bool
    num_requirements: int
    evidence_total: int
    evidence_verbatim: int
    latency_s: float
    input_tokens: int
    output_tokens: int
    error: str | None


@dataclass
class ToolCallResult:
    model: str
    prompt: str
    tool_called: str | None
    args: dict[str, Any] | None
    expected_no_tool: bool
    correct: bool | None  # None when a judgement call is left to the reviewer
    latency_s: float
    error: str | None


def usage_from_raw(raw: AIMessage) -> tuple[int, int]:
    usage = raw.usage_metadata or {}
    return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))


def verbatim_evidence_counts(requirements: JobRequirements, cleaned_text: str) -> tuple[int, int]:
    """Count evidence quotes and how many are verbatim substrings (FR-05 AC2)."""
    quotes = [r.evidence_de for r in requirements.skills]
    if requirements.seniority_evidence:
        quotes.append(requirements.seniority_evidence)
    if requirements.german_level_evidence:
        quotes.append(requirements.german_level_evidence)
    verbatim = sum(1 for q in quotes if q and q in cleaned_text)
    return len(quotes), verbatim


def save_raw(name: str, payload: dict[str, Any]) -> None:
    RAW_OUT_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_OUT_DIR / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Extraction run
# ---------------------------------------------------------------------------


def run_extraction(model_name: str, listing_file: str, run_idx: int) -> ExtractionResult:
    detail = json.loads((DETAILS_DIR / listing_file).read_text(encoding="utf-8"))
    referenznummer = detail.get("referenznummer", listing_file)
    raw_text = detail.get("stellenangebotsBeschreibung", "") or ""
    cleaned_text = clean_ad_text(raw_text)

    model = build_chat_model(model_name)
    structured = model.with_structured_output(JobRequirements, include_raw=True)
    prompt = EXTRACTION_PROMPT.format(referenznummer=referenznummer, ad_text=cleaned_text)
    messages = [HumanMessage(prompt)]

    start = time.perf_counter()
    try:
        outcome = call_with_single_retry(lambda: structured.invoke(messages))
    except Exception as exc:  # noqa: BLE001 - spike: record every failure as data
        latency = time.perf_counter() - start
        save_raw(
            f"extract_{model_name.replace('/', '_')}_{referenznummer}_run{run_idx}",
            {"model": model_name, "referenznummer": referenznummer, "error": str(exc)},
        )
        return ExtractionResult(
            model=model_name,
            referenznummer=referenznummer,
            listing_file=listing_file,
            run=run_idx,
            valid=False,
            num_requirements=0,
            evidence_total=0,
            evidence_verbatim=0,
            latency_s=latency,
            input_tokens=0,
            output_tokens=0,
            error=str(exc),
        )
    latency = time.perf_counter() - start

    raw: AIMessage = outcome["raw"]
    parsed: JobRequirements | None = outcome["parsed"]
    parsing_error = outcome.get("parsing_error")
    input_tokens, output_tokens = usage_from_raw(raw)

    save_raw(
        f"extract_{model_name.replace('/', '_')}_{referenznummer}_run{run_idx}",
        {
            "model": model_name,
            "referenznummer": referenznummer,
            "cleaned_ad_text": cleaned_text,
            "parsed": parsed.model_dump() if parsed else None,
            "parsing_error": str(parsing_error) if parsing_error else None,
            "finish_reason": raw.response_metadata.get("finish_reason"),
        },
    )

    if parsed is None:
        return ExtractionResult(
            model=model_name,
            referenznummer=referenznummer,
            listing_file=listing_file,
            run=run_idx,
            valid=False,
            num_requirements=0,
            evidence_total=0,
            evidence_verbatim=0,
            latency_s=latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=str(parsing_error) if parsing_error else "no parsed output",
        )

    evidence_total, evidence_verbatim = verbatim_evidence_counts(parsed, cleaned_text)
    return ExtractionResult(
        model=model_name,
        referenznummer=referenznummer,
        listing_file=listing_file,
        run=run_idx,
        valid=True,
        num_requirements=len(parsed.skills),
        evidence_total=evidence_total,
        evidence_verbatim=evidence_verbatim,
        latency_s=latency,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error=None,
    )


# ---------------------------------------------------------------------------
# Tool-calling run
# ---------------------------------------------------------------------------


def run_tool_calling(model_name: str, user_request: str) -> ToolCallResult:
    model = build_chat_model(model_name).bind_tools([search_jobs])
    messages = [SystemMessage(TOOL_SYSTEM_PROMPT), HumanMessage(user_request)]
    expected_no_tool = user_request == "What's the weather?"

    start = time.perf_counter()
    try:
        reply = call_with_single_retry(lambda: model.invoke(messages))
    except Exception as exc:  # noqa: BLE001 - spike: record every failure as data
        latency = time.perf_counter() - start
        return ToolCallResult(
            model=model_name,
            prompt=user_request,
            tool_called=None,
            args=None,
            expected_no_tool=expected_no_tool,
            correct=None,
            latency_s=latency,
            error=str(exc),
        )
    latency = time.perf_counter() - start

    tool_calls = reply.tool_calls
    save_raw(
        f"tools_{model_name.replace('/', '_')}_{abs(hash(user_request))}",
        {"model": model_name, "prompt": user_request, "tool_calls": tool_calls},
    )

    if not tool_calls:
        return ToolCallResult(
            model=model_name,
            prompt=user_request,
            tool_called=None,
            args=None,
            expected_no_tool=expected_no_tool,
            correct=expected_no_tool,
            latency_s=latency,
            error=None,
        )

    call = tool_calls[0]
    correct: bool | None
    if expected_no_tool or call["name"] != "search_jobs":
        correct = False
    else:
        args = call["args"]
        location = str(args.get("location", "")).lower()
        if "hamburg" in user_request.lower():
            correct = "hamburg" in location and args.get("exclude_temp_agency") is True
        elif "berlin" in user_request.lower():
            correct = "berlin" in location and args.get("published_within_days", 999) <= 7
        else:
            correct = None  # leave ambiguous cases to manual review
    return ToolCallResult(
        model=model_name,
        prompt=user_request,
        tool_called=call["name"],
        args=call["args"],
        expected_no_tool=expected_no_tool,
        correct=correct,
        latency_s=latency,
        error=None,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    extraction_results: list[ExtractionResult] = []
    tool_results: list[ToolCallResult] = []

    for model_name in MODELS:
        print(f"=== {model_name} : extraction ===")
        for listing_file in LISTING_FILES:
            for run_idx in (1, 2)[:RUNS_PER_LISTING]:
                result = run_extraction(model_name, listing_file, run_idx)
                extraction_results.append(result)
                print(
                    f"  {listing_file} run{run_idx}: valid={result.valid} "
                    f"n_req={result.num_requirements} "
                    f"evidence={result.evidence_verbatim}/{result.evidence_total} "
                    f"latency={result.latency_s:.1f}s error={result.error}"
                )

        print(f"=== {model_name} : tool calling ===")
        for request in TOOL_CALLING_REQUESTS:
            result = run_tool_calling(model_name, request)
            tool_results.append(result)
            print(
                f"  {request!r}: tool={result.tool_called} args={result.args} "
                f"correct={result.correct} error={result.error}"
            )

    before_text = json.loads((DETAILS_DIR / CONTACT_NAME_LISTING).read_text(encoding="utf-8")).get(
        "stellenangebotsBeschreibung", ""
    )
    after_text = clean_ad_text(before_text)
    # No ad text in the committed report (D-3): only counts, never the text itself.
    before_lines, after_lines = before_text.split("\n"), after_text.split("\n")
    name_lines_removed = sum(1 for line in before_lines if NAME_LINE_PATTERN.match(line.strip()))
    save_raw(
        "cleaning_example_contact_listing",
        {"file": CONTACT_NAME_LISTING, "before": before_text, "after": after_text},
    )

    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "models": list(MODELS),
        "provider_preferences": config.PROVIDER_PREFERENCES,
        "reasoning_effort": config.REASONING_EFFORT,
        "listing_files": list(LISTING_FILES),
        "runs_per_listing": RUNS_PER_LISTING,
        "extraction": [asdict(r) for r in extraction_results],
        "tool_calling": [asdict(r) for r in tool_results],
        "cleaning_example_contact_listing": {
            "file": CONTACT_NAME_LISTING,
            "note": "full before/after text is in the gitignored raw output, not here (D-3)",
            "before_line_count": len(before_lines),
            "after_line_count": len(after_lines),
            "name_lines_removed": name_lines_removed,
            "emails_masked": len(EMAIL_PATTERN.findall(before_text)),
            "phones_masked": len(PHONE_PATTERN.findall(before_text)),
        },
    }
    RESULTS_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
