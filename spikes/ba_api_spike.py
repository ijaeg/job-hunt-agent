"""Spike: Jobsuche-API der Bundesagentur für Arbeit prüfen und Fixtures aufzeichnen.

Beantwortet vor dem Bau des Agenten diese Fragen:
  Q1  Funktioniert die Suche (v6) mit dem öffentlichen API-Key, und wie sieht die Antwort aus?
  Q2  Wie stark filtert "veroeffentlichtseit" (Tage seit Veröffentlichung)?
  Q3  Wirkt der Filter "zeitarbeit=false", und gibt es ein strukturiertes Feld dafür?
  Q4  Liefert die Paginierung überschneidungsfreie Seiten?
  Q5  Liefert der Details-Endpunkt (v4, sonst v3) den Volltext der Anzeige?
  Q6  Wie reagiert die API auf Fehler (falscher Key, unbekannte Referenznummer)?
  Q7  Wie lange dauern die Aufrufe?

Aufruf (im Projektordner):
    uv run python spikes/ba_api_spike.py

Ergebnis:
    spikes/fixtures/search/*.json      Suchantworten
    spikes/fixtures/details/*.json     Detailantworten (Kontaktdaten entfernt)
    spikes/fixtures/spike_report.json  Messwerte für die Auswertung
"""

from __future__ import annotations

import base64
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
API_KEY = "jobboerse-jobsuche"  # öffentliche Client-ID der Jobsuche-Web-App, kein Geheimnis
HEADERS = {
    "X-API-Key": API_KEY,
    "Accept": "application/json",
    "User-Agent": "job-hunt-agent-spike/0.1 (Lernprojekt)",
}
TIMEOUT_S = 15.0
PAUSE_S = 0.5  # Pause zwischen Aufrufen, um die API zu schonen
MAX_DETAILS = 40

OUT_DIR = Path(__file__).resolve().parent / "fixtures"

# Suchanfragen für vielfältige Fixtures (Ort, Rolle, Technologie)
SEARCHES: list[dict[str, Any]] = [
    {"was": "Python Entwickler", "wo": "Hamburg", "umkreis": 25},
    {"was": "AI Engineer", "wo": "Hamburg", "umkreis": 50},
    {"was": "Java Entwickler", "wo": "Hamburg", "umkreis": 25},
    {"was": "Machine Learning", "wo": "Berlin", "umkreis": 25},
    {"was": "Softwareentwickler", "wo": "München", "umkreis": 25},
]

# Schlüssel mit Kontaktdaten Dritter: werden vor dem Speichern entfernt
CONTACT_KEY_PATTERN = re.compile(
    r"ansprech|kontakt|telefon|e-?mail|fax|mobilnummer|mobiltelefon|handy", re.I)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_PATTERN = re.compile(r"(?:\+49|0049|\b0)[\d\s/()-]{6,}\d")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def call(client: httpx.Client, path: str, params: dict[str, Any] | None = None,
         headers: dict[str, str] | None = None) -> dict[str, Any]:
    """Ruft einen Endpunkt auf und liefert Status, Dauer und JSON (oder Fehlertext).

    Bei 429, 5xx oder Timeout wird einmal nach 2 Sekunden wiederholt.
    """
    for attempt in (1, 2):
        start = time.perf_counter()
        try:
            resp = client.get(path, params=params, headers=headers)
            elapsed_ms = round((time.perf_counter() - start) * 1000)
        except httpx.HTTPError as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            result: dict[str, Any] = {"status": None, "error": type(exc).__name__,
                                      "ms": elapsed_ms, "json": None}
        else:
            try:
                body: Any = resp.json()
            except ValueError:
                body = None
            result = {"status": resp.status_code, "ms": elapsed_ms, "json": body,
                      "error": None if resp.is_success else resp.text[:300]}
        retryable = result["status"] is None or result["status"] == 429 or (
            result["status"] is not None and result["status"] >= 500)
        result["attempts"] = attempt
        if retryable and attempt == 1:
            time.sleep(2)
            continue
        time.sleep(PAUSE_S)
        return result
    raise AssertionError("unreachable")


def search(client: httpx.Client, **params: Any) -> dict[str, Any]:
    full = {"angebotsart": 1, "size": 25, "page": 1, **params}
    return call(client, "/pc/v6/jobs", params=full)


def encode_refnr(refnr: str) -> str:
    return base64.b64encode(refnr.encode()).decode()


# ---------------------------------------------------------------------------
# Auswertung der Antworten
# ---------------------------------------------------------------------------


def offers(body: Any) -> list[dict[str, Any]]:
    """Trefferliste: v6 liefert "ergebnisliste", ältere Versionen "stellenangebote"."""
    if isinstance(body, dict):
        items = body.get("ergebnisliste") or body.get("stellenangebote") or []
        return [i for i in items if isinstance(i, dict)]
    return []


def ref_of(item: dict[str, Any]) -> str | None:
    """Referenznummer: v6 "referenznummer", ältere Versionen "refnr"."""
    ref = item.get("referenznummer") or item.get("refnr")
    return ref if isinstance(ref, str) else None


def total(body: Any) -> int | None:
    if isinstance(body, dict) and body.get("maxErgebnisse") is not None:
        try:
            return int(body["maxErgebnisse"])
        except (TypeError, ValueError):
            return None
    return None


def keys_with(obj: Any, pattern: re.Pattern[str], prefix: str = "") -> list[str]:
    """Liefert alle (verschachtelten) Schlüsselpfade, deren Name auf pattern passt."""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if pattern.search(k):
                found.append(path)
            found.extend(keys_with(v, pattern, path))
    elif isinstance(obj, list):
        for item in obj[:3]:
            found.extend(keys_with(item, pattern, f"{prefix}[]"))
    return sorted(set(found))


def longest_text(obj: Any) -> tuple[str | None, int]:
    """Findet das längste Textfeld (Kandidat für den Volltext der Anzeige)."""
    best: tuple[str | None, int] = (None, 0)

    def walk(o: Any, path: str) -> None:
        nonlocal best
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(o, list):
            for item in o:
                walk(item, f"{path}[]")
        elif isinstance(o, str) and len(o) > best[1]:
            best = (path, len(o))

    walk(obj, "")
    return best


def scrub(obj: Any, removed: set[str], path: str = "") -> Any:
    """Entfernt Kontakt-Schlüssel und maskiert E-Mails und Telefonnummern in Texten."""
    if isinstance(obj, dict):
        clean: dict[str, Any] = {}
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if CONTACT_KEY_PATTERN.search(k):
                removed.add(p)
                continue
            clean[k] = scrub(v, removed, p)
        return clean
    if isinstance(obj, list):
        return [scrub(i, removed, f"{path}[]") for i in obj]
    if isinstance(obj, str):
        masked = EMAIL_PATTERN.sub("[EMAIL]", obj)
        return PHONE_PATTERN.sub("[TELEFON]", masked)
    return obj


def save(rel_path: str, data: Any) -> None:
    target = OUT_DIR / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ---------------------------------------------------------------------------
# Spike
# ---------------------------------------------------------------------------


def run(client: httpx.Client) -> dict[str, Any]:
    report: dict[str, Any] = {"started": datetime.now(UTC).isoformat(timespec="seconds")}
    removed_keys: set[str] = set()
    timings: list[int] = []

    # Q1 + Fixtures: mehrere Suchen
    print("Q1  Suchen ...")
    q1: list[dict[str, Any]] = []
    refnrs: list[str] = []
    sample_body: Any = None
    for params in SEARCHES:
        r = search(client, veroeffentlichtseit=28, **params)
        timings.append(r["ms"])
        items = offers(r["json"])
        name = slug(f"{params['was']}-{params['wo']}")
        if r["json"] is not None:
            save(f"search/{name}.json", scrub(r["json"], removed_keys))
        if sample_body is None and r["status"] == 200 and items:
            sample_body = r["json"]
        q1.append({"params": params, "status": r["status"], "ms": r["ms"],
                   "total": total(r["json"]), "returned": len(items), "error": r["error"]})
        for item in items:
            ref = ref_of(item)
            if ref is not None and ref not in refnrs:
                refnrs.append(ref)
        print(f"    {params['was']} / {params['wo']}: Status {r['status']}, "
              f"{len(items)} von {total(r['json'])}")
    report["q1_search"] = q1
    is_dict = isinstance(sample_body, dict)
    report["q1_response_keys"] = sorted(sample_body.keys()) if is_dict else None
    sample_items = offers(sample_body)
    report["q1_offer_keys"] = sorted(sample_items[0].keys()) if sample_items else None
    report["q1_facet_keys"] = (sorted(sample_body["facetten"].keys())
                               if isinstance(sample_body, dict)
                               and isinstance(sample_body.get("facetten"), dict) else None)

    base = SEARCHES[0]

    # Q2: Veröffentlichungsalter
    print("Q2  veroeffentlichtseit ...")
    q2 = {}
    for days in (1, 7, 28):
        r = search(client, veroeffentlichtseit=days, **base)
        timings.append(r["ms"])
        q2[str(days)] = {"status": r["status"], "total": total(r["json"])}
    report["q2_published_since"] = q2

    # Q3: Zeitarbeit
    print("Q3  zeitarbeit ...")
    r_all = search(client, veroeffentlichtseit=28, **base)
    r_no_temp = search(client, veroeffentlichtseit=28, zeitarbeit="false", **base)
    timings += [r_all["ms"], r_no_temp["ms"]]
    report["q3_temp_agency"] = {
        "total_without_filter": total(r_all["json"]),
        "total_zeitarbeit_false": total(r_no_temp["json"]),
        "status_zeitarbeit_false": r_no_temp["status"],
        "offer_fields_matching_zeitarbeit": keys_with(offers(r_all["json"])[:3],
                                                      re.compile("zeitarbeit|arbeitnehmerueberl",
                                                                 re.I)),
    }

    # Q4: Paginierung
    print("Q4  Paginierung ...")
    p1 = search(client, veroeffentlichtseit=28, size=10, page=1, **base)
    p2 = search(client, veroeffentlichtseit=28, size=10, page=2, **base)
    timings += [p1["ms"], p2["ms"]]
    refs1 = {ref_of(i) for i in offers(p1["json"])}
    refs2 = {ref_of(i) for i in offers(p2["json"])}
    report["q4_pagination"] = {"page1": len(refs1), "page2": len(refs2),
                               "overlap": len(refs1 & refs2)}

    # Q5: Details
    print(f"Q5  Details für bis zu {MAX_DETAILS} Anzeigen ...")
    q5: list[dict[str, Any]] = []
    detail_keys: set[str] = set()
    for ref in refnrs[:MAX_DETAILS]:
        enc = encode_refnr(ref)
        used = "v4"
        r = call(client, f"/pc/v4/jobdetails/{enc}")
        if r["status"] != 200:
            used = "v3"
            r = call(client, f"/pc/v3/jobdetails/{enc}")
        timings.append(r["ms"])
        entry: dict[str, Any] = {"refnr": ref, "endpoint": used, "status": r["status"],
                                 "ms": r["ms"], "error": r["error"]}
        if isinstance(r["json"], dict):
            detail_keys.update(r["json"].keys())
            field, length = longest_text(r["json"])
            entry.update({"longest_text_field": field, "longest_text_len": length})
            save(f"details/{slug(ref)}.json", scrub(r["json"], removed_keys))
        q5.append(entry)
    ok = [d for d in q5 if d["status"] == 200]
    report["q5_details"] = {
        "requested": len(q5),
        "ok": len(ok),
        "by_endpoint": {e: sum(1 for d in ok if d["endpoint"] == e) for e in ("v4", "v3")},
        "statuses": sorted({str(d["status"]) for d in q5}),
        "top_level_keys": sorted(detail_keys),
        "longest_text_fields": sorted({d["longest_text_field"] for d in ok
                                       if d.get("longest_text_field")}),
        "text_len_min": min((d["longest_text_len"] for d in ok), default=None),
        "text_len_max": max((d["longest_text_len"] for d in ok), default=None),
        "items": q5,
    }
    print(f"    {len(ok)} von {len(q5)} erfolgreich")

    # Q6: Fehlerverhalten
    print("Q6  Fehlerfälle ...")
    bad_key = call(client, "/pc/v6/jobs", params={"was": "Python", "size": 1},
                   headers={"X-API-Key": "falsch"})
    bad_ref = call(client, f"/pc/v4/jobdetails/{encode_refnr('00000-0000000000-S')}")
    report["q6_errors"] = {
        "wrong_api_key": {"status": bad_key["status"], "error": bad_key["error"]},
        "unknown_refnr": {"status": bad_ref["status"], "error": bad_ref["error"]},
    }

    # Q7: Dauer
    valid = sorted(t for t in timings if t is not None)
    report["q7_timing_ms"] = {
        "calls": len(valid),
        "median": valid[len(valid) // 2] if valid else None,
        "max": valid[-1] if valid else None,
    }

    report["removed_contact_keys"] = sorted(removed_keys)
    report["finished"] = datetime.now(UTC).isoformat(timespec="seconds")
    return report


def main() -> int:
    with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=TIMEOUT_S) as client:
        report = run(client)
    save("spike_report.json", report)
    print(f"\nFertig. Bericht: {OUT_DIR / 'spike_report.json'}")
    return 0 if report["q5_details"]["ok"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
