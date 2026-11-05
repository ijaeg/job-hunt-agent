# D-4: Model for extraction and tool calling

## Question

Is `openai/gpt-5-mini` (the spec's default, §5.5) good enough for (a)
structured extraction of `JobRequirements` (§6.2) and (b) tool calling,
compared with one alternative, `anthropic/claude-haiku-4.5` - both restricted
to zero-data-retention (ZDR) provider routing?

## Context

`spikes/extraction_check.py` ran both models, ZDR-only, against 5 listings
from `spikes/fixtures/details/` (lengths 284–9,712 chars; one temporary-agency
listing with a contact name, one 284-char teaser with an external URL), each
combination twice (20 extraction calls), plus 3 fixed tool-calling prompts per
model (6 calls) - 26 calls total. Full numbers: `spikes/d4_results.json` and
`spikes/NOTES.md` § D-4.

| Metric | gpt-5-mini | claude-haiku-4.5 |
|---|---|---|
| Valid `JobRequirements` | 10/10 | 10/10 |
| ZDR endpoint available | yes | yes |
| Evidence verbatim share | 97.2 % (139/143) | 94.4 % (118/125) |
| Latency, mean | 15.8 s | 24.5 s |
| Input / output tokens, mean | 1,481 / 1,761 | 2,503 / 4,496 |
| Tool-calling correct | 3/3 | 3/3 |

Both models kept ZDR routing intact with no routing errors - the "if a model
has no ZDR endpoint" case did not occur for either.

## Options

1. **Keep `openai/gpt-5-mini` as the sole default**, `anthropic/claude-haiku-4.5`
   stays only as the FR-18 secondary option in developer settings (no change
   from the current spec §5.5 default). Supported directly by the numbers:
   faster, cheaper, slightly higher verbatim-evidence rate, equal tool-calling
   accuracy on this sample.
2. **Switch the default to `claude-haiku-4.5`.** No metric favours it on this
   sample; it is both slower (~1.5×) and uses far more output tokens (~2.5×)
   for the same task, with a lower verbatim-evidence rate.
3. **Drop `claude-haiku-4.5` from `CHAT_MODEL_OPTIONS` entirely** and offer a
   different second model. Nothing in the data argues for this - its
   extraction and tool-calling quality were both acceptable, just costlier.

## Recommendation

Option 1: keep the spec's existing default and secondary-model plan unchanged.
The spike is a confirmation, not a reason to deviate.

## Consequences

- No change to `PRODUCT_SPEC.md` §5.5 or FR-18.
- No change to `config.py` (`CHAT_MODEL`, `CHAT_MODEL_OPTIONS` already match
  this recommendation).
- Caveat for the record: 5 listings × 2 runs is a small sample picked for
  structural variety, not statistical power; this is a go/no-go check for the
  spike, not the fit evaluation of §9.3.

**Decision:** Option 1 - keep `openai/gpt-5-mini` as the sole default;
`claude-haiku-4.5` stays as the FR-18 secondary option. No spec or code
change needed. - Ingo, 2026-11-05
