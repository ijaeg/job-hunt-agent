# D-17: Source of model prices for the cost display

Related: FR-18 AC2, NFR-02, spec §12.3 (Medium 1), WP-09

## Question

FR-18 AC2 asks for token usage and cost per turn and per session. Where do
the model prices come from?

## Context

The spec text says "a price table in `config.py`". Ingo's Sprint 2 project
(`ijager-AE.AFA.updated0209.2.5`, `src/collection_letter_navigator/pricing.py`,
adapted from Sprint 1, reviewed with 100/100) solved the same task
differently: prices are fetched from the OpenRouter models endpoint, which
needs no API key. In Sprint 2, OpenRouter did not report the cost of the
structured-output calls, so a token-based estimate was still needed.
Current OpenRouter prices (checked 2026-11-10, per 1M tokens):
`openai/gpt-5-mini` 0.25 USD input / 2.00 USD output,
`anthropic/claude-haiku-4.5` 1.00 USD input / 5.00 USD output.

## Options

A. **Static price table in `config.py`** with source and date. Simple and
   offline, but goes stale and has to be maintained by hand.
B. **Sprint 2 pattern:** fetch the price table once per session from the
   OpenRouter models endpoint; use the cost OpenRouter reports for a call
   when present, otherwise estimate from token counts (reasoning tokens as
   completion tokens); if the endpoint is unavailable, show "cost
   unavailable" and keep working; never cache failures. Adapted to `httpx`.

## Recommendation

Option B: current prices, proven code, known from the Sprint 2 review.

## Consequences

- WP-09 implements a price module after the Sprint 2 pattern with `httpx`;
  the models URL goes into `config.py`.
- The UI shows "cost" for a reported value and "estimated cost" otherwise.
- Spec FR-18 AC2 is reworded from "price table in `config.py`" to prices
  from the OpenRouter models endpoint (coach updates the spec).

**Decision:** Option B (2026-11-10, Ingo).
