"""
Issuance services.

Two entry points into one state machine (HR-06), because the proposal describes
both and they are both real:

* ``issue_record``  — an authority pushes a record. §4.1 Flow A/B.
* ``claim_record``  — a seeker logs history, an issuer endorses it. §6.2.

Plus ``import_batch`` for the CSV path that makes institutional adoption
plausible at all (§5.2 "minimal manual input").
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.common.exceptions import ConflictError, DomainError
from apps.common.utils import sha256_file
from apps.ledger.services import anchor_batch, anchor_record, freeze_record

from .models import (
    LIVE_STATUSES,
    AcademicDetail,
    BatchRowError,
    BatchStatus,
    CredentialRecord,
    ExperienceDetail,
    IssuanceBatch,
    IssuanceMode,
    RecordStatus,
    RecordType,
)
from .payloads import compute_dedupe_key

logger = logging.getLogger(__name__)


class DuplicateRecord(ConflictError):
    default_code = "duplicate_record"
    default_detail = "A live record already exists for this credential."


class InvalidTransition(DomainError):
    default_code = "invalid_transition"


def _guard_duplicate(record: CredentialRecord) -> None:
    """
    Reject a duplicate before it costs gas.

    The partial unique index is the real guarantee; this check exists to turn the
    resulting IntegrityError into a helpful message naming the existing record,
    rather than a bare 409 that leaves a registrar guessing.

    ``LIVE_STATUSES`` is imported rather than restated. It previously held its
    own hardcoded copy of the list, which silently stopped matching the database
    constraint the moment ``OFFERED`` was added to the state machine — so a
    second offer for the same degree bypassed this check and surfaced as a raw
    IntegrityError. A constant duplicated next to the thing it must agree with
    is a constant that will disagree with it.
    """
    key = compute_dedupe_key(record)
    if not key:
        return
    clash = (
        CredentialRecord.objects.filter(dedupe_key=key, status__in=LIVE_STATUSES)
        .exclude(pk=record.pk)
        .first()
    )
    if clash is not None:
        issued = f" on {clash.issued_at:%Y-%m-%d}" if clash.issued_at else ""
        awaiting = (
            " It is still awaiting the holder's confirmation."
            if clash.status == RecordStatus.OFFERED
            else " Revoke or supersede it instead of issuing a second copy."
        )
        raise DuplicateRecord(
            detail=(
                f"This credential was already issued{issued} (record {clash.pk})." f"{awaiting}"
            )
        )


@transaction.atomic
def _create_record(
    *,
    issuer,
    record_type: str,
    subject_email: str,
    subject_full_name: str,
    detail_data: dict,
    issuance_mode: str,
    subject=None,
    document=None,
    batch=None,
    national_id: str = "",
) -> CredentialRecord:
    """
    Create a record and its typed detail row. Shared by every entry point.

    Also provisions the holder's account. An institution issues at graduation,
    long before the graduate has heard of the platform, so the account is
    created here rather than waiting for a signup that may never come — with no
    usable password, so it holds the pending credential but cannot be signed
    into until its owner confirms the emailed link.

    ``national_id`` is optional and, when present, is an **attestation** by an
    approved issuer that already holds the number on file. It raises the
    holder's identity level, which is what lets a verifier later be told whether
    a genuine certificate really belongs to the person they named. There is no
    path by which a holder supplies their own.
    """
    record = CredentialRecord(
        record_type=record_type,
        issuer=issuer,
        subject=subject,
        subject_email=subject_email,
        subject_full_name=subject_full_name,
        issuance_mode=issuance_mode,
        batch=batch,
        status=RecordStatus.DRAFT,
    )
    if document is not None:
        record.document = document
        record.document_sha256 = sha256_file(document)
    record.save()

    if record_type == RecordType.EXPERIENCE:
        ExperienceDetail.objects.create(record=record, **detail_data)
    else:
        AcademicDetail.objects.create(record=record, **detail_data)

    record.refresh_from_db()

    if record.subject_id is None:
        from apps.accounts.services import attest_citizenship, get_or_create_account

        profile, _created = get_or_create_account(email=subject_email, full_name=subject_full_name)
        if national_id:
            # Raises on a number already attached to someone else. Failing the
            # issuance is correct: two people cannot share one citizenship
            # number, and quietly reassigning it would let this issuer hijack
            # the subject-match guarantee another one established.
            attest_citizenship(profile=profile, national_id=national_id, organization=issuer)
        record.subject = profile
        fields = ["subject", "updated_at"]

        # Freeze the subject binding now, from whatever identity the holder has
        # at issuance. Deriving it live would mean a later citizenship
        # attestation silently rehashed — and so invalidated — every credential
        # already issued to them.
        if profile.has_citizenship and national_id:
            from apps.accounts.identity import new_binding_salt, subject_binding

            record.binding_salt = new_binding_salt()
            record.subject_binding = subject_binding(national_id, record.binding_salt)
            fields += ["binding_salt", "subject_binding"]

        record.save(update_fields=fields)

    return record


def issue_record(*, issuer, actor, request=None, **kwargs) -> CredentialRecord:
    """
    Authority-push issuance — the primary flow.

    Creates the record, freezes it at ``OFFERED`` and emails its subject a
    confirmation link. **Nothing reaches the chain here.**

    This is the deliberate change from the earlier design, which anchored
    immediately. An anchor is permanent and public; writing one before the
    person it describes has agreed publishes a claim about them that can never
    be withdrawn. So consent is the gate, not a notification that follows the
    fact — and the graduate sees the exact hash before it exists on chain.

    The gas consequence is a feature, not a cost: confirmed records accumulate
    and anchor in batches, so an institution pays for one transaction per batch
    rather than one per graduate.
    """
    from .confirmations import create_offer

    record = _create_record(issuer=issuer, issuance_mode=IssuanceMode.AUTHORITY_PUSH, **kwargs)
    _guard_duplicate(record)

    create_offer(record, actor=actor, request=request)
    record.refresh_from_db()
    return record


def claim_record(*, seeker, issuer, actor, request=None, **kwargs) -> CredentialRecord:
    """
    Seeker-initiated claim (§6.2).

    Creates a record in ``PENDING_REVIEW``. Nothing is hashed and nothing reaches
    the chain until the named employer endorses it — an unendorsed claim is just
    an assertion by the candidate, and anchoring it would let anyone write
    self-attested "verified" employment onto the ledger.
    """
    record = _create_record(
        issuer=issuer,
        subject=seeker,
        issuance_mode=IssuanceMode.SEEKER_CLAIM,
        **kwargs,
    )
    _guard_duplicate(record)

    record.status = RecordStatus.PENDING_REVIEW
    record.submitted_at = timezone.now()
    record.save(update_fields=["status", "submitted_at", "updated_at"])

    record_event(
        AuditAction.RECORD_CLAIMED,
        actor=actor,
        organization=issuer,
        obj=record,
        metadata={"record_type": record.record_type},
        request=request,
    )
    return record


def endorse_claim(record: CredentialRecord, *, actor, note: str = "", request=None):
    """Issuer approves a seeker's claim: freeze, anchor, issue."""
    if record.status != RecordStatus.PENDING_REVIEW:
        raise InvalidTransition(
            detail=f"Only a claim awaiting review can be endorsed (status={record.status})."
        )

    record.reviewed_by = actor
    record.reviewed_at = timezone.now()
    record.review_note = note
    record.save(update_fields=["reviewed_by", "reviewed_at", "review_note", "updated_at"])

    _guard_duplicate(record)
    freeze_record(record)
    anchor_record(record, actor=actor, request=request)

    record_event(
        AuditAction.RECORD_ENDORSED,
        actor=actor,
        organization=record.issuer,
        obj=record,
        metadata={"note": note[:300]},
        request=request,
    )
    record.refresh_from_db()
    return record


def reject_claim(record: CredentialRecord, *, actor, note: str, request=None):
    """
    Issuer rejects a claim.

    A reason is mandatory (E-07). A claim that vanishes with no explanation is
    indistinguishable from a bug, and the seeker has no way to correct an honest
    mistake such as a mistyped start date.
    """
    if record.status != RecordStatus.PENDING_REVIEW:
        raise InvalidTransition(
            detail=f"Only a claim awaiting review can be rejected (status={record.status})."
        )

    record.status = RecordStatus.REJECTED
    record.reviewed_by = actor
    record.reviewed_at = timezone.now()
    record.review_note = note
    record.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])

    record_event(
        AuditAction.RECORD_CLAIM_REJECTED,
        actor=actor,
        organization=record.issuer,
        obj=record,
        metadata={"note": note[:300]},
        request=request,
    )
    return record


# ------------------------------------------------------------------- batch


ACADEMIC_COLUMNS = [
    "full_name",
    "email",
    "registration_number",
    "degree_title",
    "major",
    "level",
    "graduation_date",
    "graduation_date_bs",
    "cgpa",
    "percentage",
    "honours",
]

EXPERIENCE_COLUMNS = [
    "full_name",
    "email",
    "job_title",
    "department",
    "employment_type",
    "start_date",
    "end_date",
    "departure_status",
    "responsibilities",
]


@transaction.atomic
def import_batch(*, issuer, actor, uploaded_file, record_type: str, request=None) -> IssuanceBatch:
    """
    Parse a CSV into draft records and anchor the valid ones in one transaction.

    Every rejected row is stored with its original content and the reason
    (``BatchRowError``). Silently dropping a bad row would leave a graduate with
    no credential and nobody aware of it — the worst failure this system could
    have.

    Rows are validated *in full* before anything is anchored, so a typo on row
    140 does not leave rows 1-139 anchored and the rest lost.
    """
    from django.conf import settings

    raw = uploaded_file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DomainError(
            detail="The file must be UTF-8 encoded. Re-export it from your spreadsheet as CSV UTF-8."
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    expected = ACADEMIC_COLUMNS if record_type != RecordType.EXPERIENCE else EXPERIENCE_COLUMNS
    missing = {"full_name", "email"} - set(reader.fieldnames or [])
    if missing:
        raise DomainError(
            detail=(
                f"The CSV is missing required columns: {', '.join(sorted(missing))}. "
                f"Expected columns: {', '.join(expected)}."
            )
        )

    batch = IssuanceBatch.objects.create(
        organization=issuer,
        uploaded_by=actor,
        record_type=record_type,
        source_filename=getattr(uploaded_file, "name", "upload.csv")[:255],
        status=BatchStatus.PARSING,
    )

    created: list[CredentialRecord] = []
    errors: list[BatchRowError] = []
    total = 0

    for index, row in enumerate(reader, start=2):  # row 1 is the header
        total += 1
        if total > settings.MAX_BATCH_ROWS:
            errors.append(
                BatchRowError(
                    batch=batch,
                    row_number=index,
                    raw_row=dict(row),
                    error=(
                        f"Batch limit of {settings.MAX_BATCH_ROWS} rows exceeded. "
                        "Split the file and upload it in parts."
                    ),
                )
            )
            continue

        try:
            detail_data = (
                _parse_experience_row(row)
                if record_type == RecordType.EXPERIENCE
                else _parse_academic_row(row)
            )
            record = _create_record(
                issuer=issuer,
                record_type=record_type,
                subject_email=_require(row, "email"),
                subject_full_name=_require(row, "full_name"),
                detail_data=detail_data,
                issuance_mode=IssuanceMode.AUTHORITY_PUSH,
                batch=batch,
            )
            _guard_duplicate(record)
            freeze_record(record)
            created.append(record)
        except Exception as exc:
            errors.append(
                BatchRowError(
                    batch=batch, row_number=index, raw_row=dict(row), error=str(exc)[:500]
                )
            )

    if errors:
        BatchRowError.objects.bulk_create(errors)

    result = {}
    if created:
        result = anchor_batch(created, actor=actor, request=request)

    batch.total_rows = total
    batch.accepted_rows = len(created)
    batch.rejected_rows = len(errors)
    batch.anchor_tx_hash = result.get("tx_hash", "")
    batch.completed_at = timezone.now()
    batch.status = (
        BatchStatus.FAILED
        if not created and errors
        else BatchStatus.PARTIAL
        if errors
        else BatchStatus.COMPLETED
    )
    batch.save()

    record_event(
        AuditAction.BATCH_UPLOADED,
        actor=actor,
        organization=issuer,
        obj=batch,
        metadata={
            "total": total,
            "accepted": len(created),
            "rejected": len(errors),
            "tx_hash": batch.anchor_tx_hash,
        },
        request=request,
    )
    return batch


def _require(row: dict, column: str) -> str:
    value = (row.get(column) or "").strip()
    if not value:
        raise ValueError(f"'{column}' is required and was empty.")
    return value


def _optional(row: dict, column: str) -> str:
    return (row.get(column) or "").strip()


def _parse_date(value: str, column: str):
    value = value.strip()
    if not value:
        raise ValueError(f"'{column}' is required.")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{column}' is not a recognised date: '{value}'. Use YYYY-MM-DD.")


def _parse_decimal(value: str, column: str, *, low: Decimal, high: Decimal):
    value = value.strip()
    if not value:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"'{column}' is not a number: '{value}'.") from exc
    if not (low <= parsed <= high):
        raise ValueError(f"'{column}' must be between {low} and {high}, got {parsed}.")
    return parsed


def _parse_academic_row(row: dict) -> dict:
    level = _optional(row, "level").upper() or AcademicDetail.Level.BACHELORS
    valid_levels = {choice.value for choice in AcademicDetail.Level}
    if level not in valid_levels:
        raise ValueError(f"'level' must be one of: {', '.join(sorted(valid_levels))}.")

    return {
        "registration_number": _require(row, "registration_number"),
        "degree_title": _require(row, "degree_title"),
        "major": _optional(row, "major"),
        "level": level,
        "graduation_date": _parse_date(_optional(row, "graduation_date"), "graduation_date"),
        "graduation_date_bs": _optional(row, "graduation_date_bs"),
        "cgpa": _parse_decimal(_optional(row, "cgpa"), "cgpa", low=Decimal("0"), high=Decimal("4")),
        "percentage": _parse_decimal(
            _optional(row, "percentage"), "percentage", low=Decimal("0"), high=Decimal("100")
        ),
        "honours": _optional(row, "honours"),
    }


def _parse_experience_row(row: dict) -> dict:
    end_raw = _optional(row, "end_date")
    is_current = end_raw.lower() in {"", "present", "current"}
    departure = _optional(row, "departure_status").upper() or (
        ExperienceDetail.DepartureStatus.CURRENT
        if is_current
        else ExperienceDetail.DepartureStatus.RESIGNED
    )

    valid_departures = {choice.value for choice in ExperienceDetail.DepartureStatus}
    if departure not in valid_departures:
        raise ValueError(
            f"'departure_status' must be one of: {', '.join(sorted(valid_departures))}."
        )

    # E-06 again, this time at the CSV boundary: a row that says "still employed"
    # while carrying a departure status of RESIGNED is a data-entry error, and the
    # database CHECK constraint would reject it with a far less helpful message.
    if is_current and departure != ExperienceDetail.DepartureStatus.CURRENT:
        raise ValueError(
            "A row with no end date must have departure_status CURRENT, " f"not {departure}."
        )
    if not is_current and departure == ExperienceDetail.DepartureStatus.CURRENT:
        raise ValueError("A row with an end date cannot have departure_status CURRENT.")

    employment_type = _optional(row, "employment_type").upper() or (
        ExperienceDetail.EmploymentType.FULL_TIME
    )
    valid_types = {choice.value for choice in ExperienceDetail.EmploymentType}
    if employment_type not in valid_types:
        raise ValueError(f"'employment_type' must be one of: {', '.join(sorted(valid_types))}.")

    start_date = _parse_date(_optional(row, "start_date"), "start_date")
    end_date = None if is_current else _parse_date(end_raw, "end_date")
    if end_date and end_date < start_date:
        raise ValueError("'end_date' cannot be before 'start_date'.")

    return {
        "job_title": _require(row, "job_title"),
        "department": _optional(row, "department"),
        "employment_type": employment_type,
        "start_date": start_date,
        "end_date": end_date,
        "is_current": is_current,
        "departure_status": departure,
        "responsibilities": _optional(row, "responsibilities"),
    }
