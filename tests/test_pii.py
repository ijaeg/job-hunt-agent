"""Tests for :mod:`job_hunt_agent.pii`.

All examples are synthetic (CI has no raw spike data, CLAUDE.md invariant
4). The five name patterns mirror D-3's description of what the D-1 spike's
own regex-only cleaning missed.

Related: FR-22 AC1, FR-22 AC5, D-3
"""

from __future__ import annotations

from job_hunt_agent.pii import clean_ad_text


def test_email_is_masked_and_counted() -> None:
    """A bare e-mail address is replaced and counted."""
    cleaned, counts = clean_ad_text("Bewerbungen an bewerbung@beispiel-gmbh.de senden.")
    assert "[EMAIL]" in cleaned
    assert "bewerbung@beispiel-gmbh.de" not in cleaned
    assert counts["emails_masked"] == 1


def test_phone_with_telefon_context_is_masked() -> None:
    """A phone number following "Telefon:" is masked."""
    cleaned, counts = clean_ad_text("Bei Rueckfragen erreichen Sie uns:\nTelefon: 040 / 123 456 78")
    assert "[TELEFON]" in cleaned
    assert "123 456 78" not in cleaned
    assert counts["phones_masked"] == 1


def test_phone_with_plus_49_prefix_is_masked_without_keyword() -> None:
    """A ``+49`` number is masked even without the word "Telefon"."""
    cleaned, counts = clean_ad_text("Erreichbar: +49 40 1234567 zu Geschaeftszeiten.")
    assert "[TELEFON]" in cleaned
    assert counts["phones_masked"] == 1


def test_bare_number_without_phone_context_is_not_masked() -> None:
    """A leading-zero number with no phone keyword nearby stays untouched.

    This is the exact failure mode D-3 found in the D-1 spike: a
    context-free regex masked part of a reference number.
    """
    cleaned, counts = clean_ad_text("Bitte Unterlagen bis 01234567 einreichen.")
    assert "[TELEFON]" not in cleaned
    assert counts["phones_masked"] == 0


def test_reference_number_stays_unchanged() -> None:
    """Reference numbers such as 19522-0068291613-S are never touched."""
    text = "Referenznummer dieser Anzeige: 19522-0068291613-S"
    cleaned, counts = clean_ad_text(text)
    assert cleaned == text
    assert counts == {"emails_masked": 0, "phones_masked": 0, "contact_lines_removed": 0}


def test_second_reference_number_stays_unchanged() -> None:
    """The second D-1 reference-number regression case also stays unchanged."""
    text = "Kennziffer: 13509-000021100c7004-S"
    cleaned, _ = clean_ad_text(text)
    assert cleaned == text


def test_postal_code_stays_unchanged() -> None:
    """A postal code that happens to start with 0 is not a phone number."""
    text = "Dienstort: 04109 Leipzig"
    cleaned, counts = clean_ad_text(text)
    assert cleaned == text
    assert counts["phones_masked"] == 0


def test_salary_stays_unchanged() -> None:
    """Salary figures are not touched by the phone or name rules."""
    text = "Gehalt: 60.000 EUR - 80.000 EUR brutto pro Jahr."
    cleaned, _ = clean_ad_text(text)
    assert cleaned == text


def test_date_stays_unchanged() -> None:
    """ISO dates stay untouched."""
    text = "Eintrittsdatum: 2026-11-04."
    cleaned, _ = clean_ad_text(text)
    assert cleaned == text


def test_year_stays_unchanged() -> None:
    """A bare year is not mistaken for a phone number."""
    text = "Gegruendet im Jahr 2026 in Hamburg."
    cleaned, _ = clean_ad_text(text)
    assert cleaned == text


def test_pattern_1_inline_name_after_bei_frau() -> None:
    """D-3 pattern 1: inline "bei Frau <Name>" - the name is replaced."""
    text = "Bewerbungen bitte online unter der Kennziffer VA42 bei Frau Elif Rühl."
    cleaned, counts = clean_ad_text(text)
    assert "Elif Rühl" not in cleaned
    assert "bei Frau [NAME]" in cleaned
    assert counts["contact_lines_removed"] == 1


def test_pattern_2_signature_line_is_dropped() -> None:
    """D-3 pattern 2: a standalone "Herr <Name>" signature line is dropped."""
    text = "Ihr Team von Dock 22\n\nHerr Torben Schulz\nDock 22 GmbH\nAm Sandtorkai 23"
    cleaned, counts = clean_ad_text(text)
    assert "Torben Schulz" not in cleaned
    assert "Dock 22 GmbH" in cleaned
    assert "Am Sandtorkai 23" in cleaned
    assert counts["contact_lines_removed"] == 1


def test_pattern_3_name_before_phone_number_is_dropped() -> None:
    """D-3 pattern 3: a bare name line right before a phone line is dropped."""
    text = "Wir freuen uns auf Ihre Bewerbung.\n\nPeter Müller\nTelefon: 040 1234567"
    cleaned, counts = clean_ad_text(text)
    assert "Peter Müller" not in cleaned
    assert "[TELEFON]" in cleaned
    assert counts["contact_lines_removed"] == 1


def test_pattern_4_ihr_ansprechpartner_header_drops_the_rest() -> None:
    """D-3 pattern 4: "Ihr Ansprechpartner: Herr X" opens a dropped block."""
    text = (
        "Wir freuen uns auf Ihre Bewerbung.\n\n"
        "Ihr Ansprechpartner: Herr Jonas Weber\n"
        "Beispiel GmbH\n"
        "Telefon: 030 9876543\n"
        "E-Mail: jobs@beispiel.de"
    )
    cleaned, counts = clean_ad_text(text)
    assert "Jonas Weber" not in cleaned
    assert "Beispiel GmbH" not in cleaned
    assert "[TELEFON]" not in cleaned  # the whole block is gone, not just masked
    assert "Wir freuen uns auf Ihre Bewerbung." in cleaned
    assert counts["contact_lines_removed"] == 4


def test_pattern_5_name_and_address_block_drops_only_the_name() -> None:
    """D-3 pattern 5: a name line followed by a company/address block."""
    text = "Herr Max Mustermann\nMusterfirma GmbH\nMusterstrasse 1\n12345 Musterstadt"
    cleaned, counts = clean_ad_text(text)
    assert "Max Mustermann" not in cleaned
    assert "Musterfirma GmbH" in cleaned
    assert "Musterstrasse 1" in cleaned
    assert "12345 Musterstadt" in cleaned
    assert counts["contact_lines_removed"] == 1


def test_kontakt_header_also_opens_a_dropped_block() -> None:
    """A plain "Kontakt:" header (no "Ansprechpartner") also starts the block."""
    text = "Teaser-Text.\n\nKontakt:\nBeispiel GmbH\nTelefon: 089 111222"
    cleaned, counts = clean_ad_text(text)
    assert "Beispiel GmbH" not in cleaned
    assert counts["contact_lines_removed"] == 3


def test_job_title_line_is_not_mistaken_for_a_name() -> None:
    """A plain two-word job title with no following phone line survives."""
    text = "Python Entwickler\n\nWir suchen eine engagierte Persoenlichkeit."
    cleaned, _ = clean_ad_text(text)
    assert "Python Entwickler" in cleaned


def test_combined_realistic_ad_text() -> None:
    """A combined, fictional ad with several contact patterns at once."""
    text = (
        "Python-Entwickler (m/w/d)\n\n"
        "Wir suchen dich fuer unser Team in Hamburg!\n\n"
        "Referenznummer: 13509-000021100c7004-S\n"
        "Gehalt: 60.000 EUR - 75.000 EUR\n\n"
        "Fragen? Melde dich einfach bei Frau Sandra Klein.\n\n"
        "Ihr Ansprechpartner:\n"
        "Herr Markus Lang\n"
        "Beispiel Software GmbH\n"
        "Beispielweg 5\n"
        "22305 Hamburg\n"
        "Telefon: 040 55512345\n"
        "E-Mail: kontakt@beispiel-software.de"
    )
    cleaned, counts = clean_ad_text(text)
    assert "Sandra Klein" not in cleaned
    assert "Markus Lang" not in cleaned
    assert "kontakt@beispiel-software.de" not in cleaned
    assert "13509-000021100c7004-S" in cleaned
    assert "60.000 EUR - 75.000 EUR" in cleaned
    assert counts["emails_masked"] == 0  # the e-mail line is gone with the block, not masked
    assert counts["contact_lines_removed"] >= 6
