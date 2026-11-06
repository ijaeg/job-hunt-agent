"""D-10 follow-up 2: fetches v4 details for the recorded "Softwareentwickler"/München search.

The München recorded search (D-10 Option 4, `spikes/fixtures/search/
softwareentwickler-m-nchen.json`) has zero overlap with the 40 listings
the D-1 spike detail-fetched, because D-1's 40-detail budget was spent on
the 4 other searches first (confirmed in the D-10 addendum). This fetches
the details for München's own 25 referenznummern directly, so demo mode
can show the full "narrow -> details -> assess_fit" chain for this query.

One live run, polite pacing (same 0.5 s / retry-on-429-5xx pattern as
`spikes/ba_api_spike.py`, reusing its `call`/`encode_refnr` directly).
Raw responses are saved **unscrubbed** this time (unlike the original D-1
spike's own ad-hoc regex scrub, which is exactly what corrupted 3
reference numbers in the first place, D-1/D-10 regression) - cleaning
happens later, properly, via `pii.py` inside `scripts/build_fixtures.py`.
Raw files are gitignored (`spikes/fixtures/*`, D-3) like every other raw
response.

404s (`STELLENANGEBOT_NICHT_GEFUNDEN` - the listing expired since the D-1
search ran on 2026-11-05) are expected and simply skipped, not an error.

Usage (from the project root):
    uv run python spikes/fetch_muenchen_details.py

Related: D-1, D-3, D-10
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ba_api_spike import BASE_URL, HEADERS, TIMEOUT_S, call, encode_refnr, slug  # noqa: E402

SEARCH_RESPONSE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "search" / "softwareentwickler-m-nchen.json"
)
DETAILS_DIR = Path(__file__).resolve().parent / "fixtures" / "details"


def referenznummern() -> list[str]:
    body = json.loads(SEARCH_RESPONSE_PATH.read_text(encoding="utf-8"))
    return [
        item["referenznummer"]
        for item in body.get("ergebnisliste") or []
        if isinstance(item, dict) and isinstance(item.get("referenznummer"), str)
    ]


def main() -> int:
    refs = referenznummern()
    print(f"Fetching details for {len(refs)} München referenznummern...")

    ok = 0
    not_found = 0
    other_errors: list[str] = []

    with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT_S) as client:
        for ref in refs:
            encoded = encode_refnr(ref)
            result = call(client, f"/pc/v4/jobdetails/{encoded}")
            status = result["status"]
            if status == 200 and isinstance(result["json"], dict):
                target = DETAILS_DIR / f"{slug(ref)}.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    json.dumps(result["json"], ensure_ascii=False, indent=2), encoding="utf-8"
                )
                ok += 1
                print(f"  OK    {ref}")
            elif status == 404:
                not_found += 1
                print(f"  404   {ref} (no longer available)")
            else:
                other_errors.append(f"{ref}: status={status} error={result['error']!r}")
                print(f"  ERROR {ref}: status={status}")

    print(
        f"\nDone. {ok} saved, {not_found} no longer available (404), "
        f"{len(other_errors)} other errors."
    )
    for line in other_errors:
        print(f"  - {line}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
