"""
Payload builders — what exactly gets hashed.

These functions are the bridge between the database and the ledger. They read the
**live** detail rows and produce the dict that ``canonical.compute_record_hash``
turns into a digest. Verification calls the very same builders, which is what
makes tamper detection real: if anyone edits a detail row after issuance, the
rebuilt payload differs and the recomputed hash no longer matches the anchor.

## What is deliberately excluded, and why

Two fields you might expect are absent, both because they are **mutable**:

* **The issuer's display name.** ``issuer_id`` and ``issuer_address`` go in
  instead. If a college rebrands — and Nepali colleges do — including the name
  would invalidate every degree it had ever issued. The organisation's name is
  still cryptographically attested: the contract stores it against the issuer
  address at approval time.

* **The subject's email address.** It is the *routing* mechanism that links a
  pushed record to an account, not part of the credential. A graduate who moves
  from a college address to a personal one must not lose their degree.

``record_id`` is included so that two genuinely distinct records can never
collide — two people with the same name, title, and dates at the same employer
would otherwise produce identical hashes and the second anchor would revert.
"""

from __future__ import annotations

import hashlib
from typing import Any

from apps.common.utils import normalise_text
from apps.ledger.canonical import (
    PAYLOAD_SCHEMA_VERSION,
    canonical_dict,
    compute_record_hash,
)

from .models import CredentialRecord, RecordType


def build_payload(record: CredentialRecord) -> dict[str, Any]:
    """
    Build the canonical payload for a record from its live database rows.

    Raises ``ValueError`` when the record has no detail row: hashing a record
    with no substance would produce an anchor that attests to nothing.
    """
    detail = record.detail
    if detail is None:
        raise ValueError(
            f"Record {record.pk} has no {record.record_type} detail row and cannot be hashed."
        )

    payload: dict[str, Any] = {
        "schema": PAYLOAD_SCHEMA_VERSION,
        "record_id": str(record.pk),
        "type": record.record_type,
        "issuer_id": str(record.issuer_id),
        "issuer_address": record.issuer.chain_address.lower(),
        "subject_name": normalise_text(record.subject_full_name),
    }

    if record.record_type == RecordType.EXPERIENCE:
        payload["experience"] = _experience_fields(detail)
    else:
        payload["academic"] = _academic_fields(detail)

    # Binds the uploaded certificate scan to the record. Swapping the PDF for a
    # different one changes the hash, so the document is covered by the same
    # tamper guarantee as the structured fields.
    if record.document_sha256:
        payload["document_sha256"] = record.document_sha256

    # Binds the credential to its subject without naming them. Read from the
    # frozen column rather than recomputed from the holder's profile, so
    # attesting a citizenship number after issuance cannot retroactively
    # invalidate records issued before it.
    #
    # Its presence is also what makes tampering with `subject` detectable: the
    # FK itself is not hashed, so without this an insider could reassign a
    # genuine degree to a different account and every integrity check would
    # still pass.
    if record.subject_binding:
        payload["subject_binding"] = record.subject_binding

    return payload


def _academic_fields(detail) -> dict[str, Any]:
    return {
        "registration_number": normalise_text(detail.registration_number),
        "degree_title": normalise_text(detail.degree_title),
        "major": normalise_text(detail.major),
        "level": detail.level,
        # Gregorian only. Bikram Sambat conversion tables disagree by a day at
        # the edges, and a hash must not depend on which table the issuer used.
        "graduation_date": detail.graduation_date,
        "cgpa": detail.cgpa,
        "percentage": detail.percentage,
        "honours": normalise_text(detail.honours),
    }


def _experience_fields(detail) -> dict[str, Any]:
    return {
        "job_title": normalise_text(detail.job_title),
        "department": normalise_text(detail.department),
        "employment_type": detail.employment_type,
        "start_date": detail.start_date,
        "end_date": detail.end_date,
        "is_current": detail.is_current,
        "departure_status": detail.departure_status,
        "responsibilities": normalise_text(detail.responsibilities),
    }


def hash_record(record: CredentialRecord) -> tuple[str, dict[str, Any]]:
    """
    Return ``(record_hash, canonical_payload)`` for a record.

    The single hashing entry point, used by both issuance and verification — the
    two must never drift apart, or genuine credentials start failing. The second
    element is the canonicalised, JSON-safe pre-image, not the raw builder
    output, so what gets stored is exactly what got hashed.
    """
    payload = build_payload(record)
    return compute_record_hash(payload), canonical_dict(payload)


def compute_dedupe_key(record: CredentialRecord) -> str:
    """
    Derive the natural-key fingerprint that blocks duplicate live issuance (E-11).

    Unlike the record hash, this intentionally **excludes** ``record_id`` — the
    whole point is that two different rows describing the same real-world
    credential collide here and are rejected by the partial unique index.

    Email is used for experience records because employment has no equivalent of
    a registration number, and (employer, person, title, start date) is the
    closest thing to a natural key that exists.
    """
    detail = record.detail
    if detail is None:
        return ""

    if record.record_type == RecordType.EXPERIENCE:
        parts = [
            str(record.issuer_id),
            record.record_type,
            record.subject_email.lower(),
            normalise_text(detail.job_title).lower(),
            detail.start_date.isoformat(),
        ]
    else:
        parts = [
            str(record.issuer_id),
            record.record_type,
            normalise_text(detail.registration_number).lower(),
            normalise_text(detail.degree_title).lower(),
        ]

    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
