"""
Document-first verification — the employer's entry point.

## Why the document comes first

The obvious design is "type a name and a citizenship number, see if they exist".
That endpoint is a national PII enumeration oracle: Nepali citizenship numbers
are district-structured and sequentially issued, so the plausible keyspace is
small enough to walk exhaustively, and anyone could probe who is on the platform.

So possession of the document *is* the authorisation. The verifier uploads the
PDF they were given; the identity fields they type are never a query, only an
assertion checked against a record the upload already matched. Someone holding
no document learns nothing, at any rate limit.

## Why the PDF hash is not the whole answer

``sha256(pdf_bytes)`` changes when a file is re-saved by a reader, re-compressed
by a mail gateway, or downloaded through a preview service. Treating a byte
mismatch as "forged" would accuse honest graduates of fraud for using Gmail. So
the exact-bytes match is only the *lookup*; the verdict always comes from
recomputing the canonical payload and checking the ledger, exactly as a QR scan
does.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.common.exceptions import QuotaExceeded
from apps.common.throttling import VerificationThrottle
from apps.common.utils import client_ip, hash_ip, sha256_file
from apps.common.validators import UploadValidator
from apps.credentials.models import CredentialRecord

from .models import VerificationResult
from .services import QuotaService, check_subject, log_verification, verify_record


class DocumentVerifySerializer(serializers.Serializer):
    document = serializers.FileField(validators=[UploadValidator()])
    # Optional, and an assertion rather than a lookup — see the module docstring.
    claimed_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    claimed_national_id = serializers.CharField(required=False, allow_blank=True, max_length=32)


class DocumentVerifyResultSerializer(serializers.Serializer):
    result = serializers.CharField()
    reason = serializers.CharField()
    document_sha256 = serializers.CharField()
    issuer = serializers.JSONField()
    subject_match = serializers.BooleanField(allow_null=True)
    subject_check_available = serializers.BooleanField()
    identity_level = serializers.CharField()
    expected_hash = serializers.CharField()
    computed_hash = serializers.CharField()
    chain = serializers.JSONField()


@extend_schema(
    tags=["verification"],
    summary="Verify an uploaded certificate",
    request=DocumentVerifySerializer,
    responses={200: DocumentVerifyResultSerializer},
    description=(
        "Upload the PDF a candidate gave you. Optionally assert who it belongs "
        "to; that assertion is checked against the matched record and is never "
        "used to search for people."
    ),
)
class DocumentVerifyView(APIView):
    """
    Upload-and-check, metered and logged exactly like the QR path.

    It previously did neither, which broke three screens at once: an employer's
    quota meter never moved however many certificates they checked, their
    verification history stayed empty, and — worst of the three — a citizen's
    "who checked me" log recorded their prospective employer as an *anonymous
    scan*. That transparency log is the platform's central promise to holders,
    and the platform's own primary verification flow was the one thing invisible
    to it. Metering was likewise bypassed: the paid tier is defined by
    verification volume, and this is where the volume actually happens.

    Both are now handled here, on the same terms as ``_VerifyMixin._run``: an
    authenticated organisation is metered against its plan, and an anonymous
    caller is rate-limited instead.
    """

    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser]
    # No-ops for authenticated callers by design — they are bounded by quota
    # rather than by rate. See `VerificationThrottle`.
    throttle_classes = [VerificationThrottle]

    def post(self, request):
        serializer = DocumentVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["document"]
        claimed_id = serializer.validated_data.get("claimed_national_id", "")

        verifier_org = self._organization_for(request)
        counts_against_quota = False
        if verifier_org is not None:
            if not QuotaService.has_capacity(verifier_org):
                raise QuotaExceeded(
                    detail=(
                        "Your organisation has used its monthly verification quota. "
                        "Upgrade to Pro for unlimited lookups."
                    )
                )
            counts_against_quota = True

        digest = sha256_file(upload)
        record = (
            CredentialRecord.objects.select_related("issuer", "subject")
            .filter(document_sha256=digest)
            .first()
        )

        # `verify_record(None)` returns NOT_FOUND with wording identical to the
        # "not entitled to see it" case, so a miss reveals nothing about whether
        # the credential exists under a different file.
        outcome = verify_record(record, reference=f"sha256:{digest[:12]}")

        subject_match, identity_level = (None, "")
        if record is not None:
            subject_match, identity_level = check_subject(record, claimed_national_id=claimed_id)

        result = outcome.result
        reason = outcome.reason
        # A genuine certificate presented by the wrong person is its own outcome.
        # Reporting VERIFIED here would confirm a fraud; reporting TAMPERED would
        # libel the issuer, whose document is intact.
        if result == VerificationResult.VERIFIED and subject_match is False:
            result = VerificationResult.SUBJECT_MISMATCH
            reason = (
                "This is a genuine, unaltered credential, but it was not issued "
                "to the person named."
            )

        # Logged with the *final* result, so a SUBJECT_MISMATCH is recorded as
        # one rather than as the VERIFIED the ledger check alone returned. The
        # reference is the digest prefix, never the filename — a file called
        # "sita-sharma-degree.pdf" would put a name into a log the subject can
        # read without the verifier ever intending to disclose it.
        outcome.result = result
        outcome.reason = reason
        log_verification(
            outcome,
            reference=f"sha256:{digest[:12]}",
            verifier_org=verifier_org,
            verifier_user=request.user if request.user.is_authenticated else None,
            client_ip_hash=hash_ip(client_ip(request)),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            counts_against_quota=counts_against_quota,
        )
        record_event(
            AuditAction.VERIFICATION_PERFORMED,
            actor=request.user if request.user.is_authenticated else None,
            organization=verifier_org,
            obj=record,
            metadata={"result": result, "via": "document_upload"},
            request=request,
        )

        return Response(
            {
                "result": result,
                "reason": reason,
                "document_sha256": digest,
                "issuer": outcome.issuer,
                "subject_match": subject_match,
                # Lets the UI say "we cannot check who this belongs to" instead
                # of implying a guarantee this account never supported.
                "subject_check_available": subject_match is not None,
                "identity_level": identity_level,
                "expected_hash": outcome.expected_hash,
                "computed_hash": outcome.computed_hash,
                "chain": outcome.chain,
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _organization_for(request):
        """
        The organisation to meter and attribute this check to, if any.

        Resolved by hand rather than through ``IsOrganizationMember`` because
        this endpoint is deliberately ``AllowAny``: a recruiter holding a
        printed certificate must be able to check it without an account, and
        adding a permission class to get ``request.organization`` would close
        that door. A signed-in citizen has no membership and is treated exactly
        like an anonymous caller — rate-limited, not metered.
        """
        user = request.user
        if not (user and user.is_authenticated):
            return None

        membership = user.memberships.select_related("organization").order_by("created_at").first()
        return membership.organization if membership else None
