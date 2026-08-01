"""
Verification, passport and employer-dashboard endpoints.

The public verification endpoints are the only unauthenticated write-adjacent
surface on the platform, so each one is explicitly ``AllowAny`` plus throttled —
never implicitly open because a permission class was forgotten.
"""

import io

from django.contrib.auth.hashers import check_password
from django.db.models import Count, Q
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers, status, viewsets
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.common.exceptions import QuotaExceeded, ShareLinkExpired
from apps.common.permissions import IsCitizen, IsOrganizationMember, IsSubjectOfRecord
from apps.common.throttling import ShareUnlockThrottle, VerificationThrottle
from apps.common.utils import client_ip, hash_ip
from apps.credentials.models import CredentialRecord, RecordStatus, RecordType
from apps.credentials.serializers import CredentialRecordSerializer

from .models import ShareLink, VerificationLog, VerificationResult
from .serializers import (
    CandidateSerializer,
    LookupSerializer,
    SharedPassportSerializer,
    SharedRecordSerializer,
    ShareLinkSerializer,
    UnlockSerializer,
    VerificationLogSerializer,
    VerificationOutcomeSerializer,
)
from .services import QuotaService, find_record, log_verification, verify_record


class _VerifyMixin:
    """Shared plumbing for endpoints that run a verification and meter it."""

    def _run(self, request, reference: str, *, share_link=None):
        verifier_org = getattr(request, "organization", None)
        counts_against_quota = False

        # Only an authenticated employer's own lookup is metered. An anonymous QR
        # scan is rate-limited instead, so a candidate sharing their link with a
        # recruiter never silently burns that recruiter's monthly quota (§9).
        if verifier_org is not None and share_link is None:
            if not QuotaService.has_capacity(verifier_org):
                raise QuotaExceeded(
                    detail=(
                        "Your organisation has used its monthly verification quota. "
                        "Upgrade to Pro for unlimited lookups."
                    )
                )
            counts_against_quota = True

        outcome = verify_record(find_record(reference), reference=reference)

        log_verification(
            outcome,
            reference=reference,
            verifier_org=verifier_org,
            verifier_user=request.user if request.user.is_authenticated else None,
            share_link=share_link,
            client_ip_hash=hash_ip(client_ip(request)),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            counts_against_quota=counts_against_quota,
        )
        record_event(
            AuditAction.VERIFICATION_PERFORMED,
            actor=request.user if request.user.is_authenticated else None,
            organization=verifier_org,
            obj=outcome.record,
            metadata={"result": outcome.result, "reference": reference[:64]},
            request=request,
        )

        serializer = VerificationOutcomeSerializer(
            outcome, context={"mask": share_link.mask_identifiers if share_link else False}
        )
        http_status = (
            status.HTTP_404_NOT_FOUND
            if outcome.result == VerificationResult.NOT_FOUND
            else status.HTTP_200_OK
        )
        return Response(serializer.data, status=http_status)


@extend_schema(
    tags=["verification"],
    summary="Verify a credential by id or hash",
    description=(
        "Public and unauthenticated — a recruiter should not need an account to "
        "check a QR code. Anonymous callers are rate-limited; authenticated "
        "employers are metered against their plan quota instead."
    ),
    request=LookupSerializer,
    responses={200: VerificationOutcomeSerializer, 404: VerificationOutcomeSerializer},
)
class VerifyLookupView(_VerifyMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [VerificationThrottle]

    def post(self, request):
        serializer = LookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._run(request, serializer.validated_data["reference"])


@extend_schema(
    tags=["verification"],
    summary="Verify a credential by id (GET, for QR codes)",
    responses={200: VerificationOutcomeSerializer, 404: VerificationOutcomeSerializer},
)
class VerifyRecordView(_VerifyMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [VerificationThrottle]

    def get(self, request, reference: str):
        return self._run(request, reference)


@extend_schema(
    tags=["verification"],
    summary="Open a shared credential passport",
    parameters=[
        OpenApiParameter(
            "passphrase",
            str,
            description="Required only when the link is passphrase-protected.",
        )
    ],
    responses=SharedPassportSerializer,
)
class SharedPassportView(APIView):
    """
    The recruiter-facing view behind a share link (§6.3).

    Every failure mode — revoked, expired, view limit reached — returns the same
    410 with the same wording. Distinguishing them would tell a stranger holding
    a stale link whether the person is still job-hunting.
    """

    permission_classes = [AllowAny]
    throttle_classes = [VerificationThrottle]

    def get(self, request, token: str):
        link = ShareLink.objects.select_related("seeker__user").filter(token=token).first()
        if link is None or not link.is_active:
            raise ShareLinkExpired()

        if link.requires_passphrase:
            supplied = request.query_params.get("passphrase") or request.headers.get(
                "X-Share-Passphrase", ""
            )
            if not supplied or not check_password(supplied, link.passphrase_hash):
                return Response(
                    {
                        "error": {
                            "code": "passphrase_required",
                            "message": "This link is protected. Enter the passphrase to continue.",
                            "details": {"requires_passphrase": True},
                        }
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        records = self._records_for(link)

        ShareLink.objects.filter(pk=link.pk).update(
            view_count=link.view_count + 1, last_viewed_at=timezone.now()
        )

        summary = {
            "academic": sum(1 for r in records if r.record_type == RecordType.ACADEMIC),
            "experience": sum(1 for r in records if r.record_type == RecordType.EXPERIENCE),
            "total": len(records),
        }
        return Response(
            {
                "owner_name": link.seeker.user.full_name,
                "headline": link.seeker.headline,
                "shared_at": link.created_at,
                "expires_at": link.expires_at,
                "masked": link.mask_identifiers,
                "summary": summary,
                "records": SharedRecordSerializer(
                    records, many=True, context={"mask": link.mask_identifiers}
                ).data,
            }
        )

    @staticmethod
    def _records_for(link: ShareLink) -> list[CredentialRecord]:
        base = CredentialRecord.objects.select_related(
            "issuer", "academic_detail", "experience_detail"
        ).prefetch_related("anchors")

        if link.include_all:
            queryset = base.filter(
                subject=link.seeker,
                status__in=[RecordStatus.ISSUED, RecordStatus.REVOKED, RecordStatus.SUPERSEDED],
            )
        else:
            queryset = base.filter(share_selections__share_link=link)
        return list(queryset.order_by("-issued_at"))


@extend_schema(
    tags=["verification"],
    summary="Unlock a passphrase-protected link",
    request=UnlockSerializer,
    responses=inline_serializer(
        name="ShareLinkUnlocked",
        fields={
            "detail": serializers.CharField(),
            "token": serializers.CharField(),
        },
    ),
)
class UnlockShareLinkView(APIView):
    permission_classes = [AllowAny]
    # Keyed on the link token, not the IP (E-04): the threat is one attacker
    # rotating proxies against one link.
    throttle_classes = [ShareUnlockThrottle]

    def post(self, request, token: str):
        serializer = UnlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        link = ShareLink.objects.filter(token=token).first()
        if link is None or not link.is_active:
            raise ShareLinkExpired()

        if not link.requires_passphrase or not check_password(
            serializer.validated_data["passphrase"], link.passphrase_hash
        ):
            return Response(
                {
                    "error": {
                        "code": "invalid_passphrase",
                        "message": "Incorrect passphrase.",
                        "details": {},
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response({"detail": "Unlocked.", "token": token})


@extend_schema(
    tags=["passport"],
    summary="My credential passport",
    responses=inline_serializer(
        name="MyPassport",
        fields={
            "profile": serializers.DictField(),
            "summary": serializers.DictField(child=serializers.IntegerField()),
            "records": serializers.ListField(child=serializers.DictField()),
        },
    ),
)
class MyPassportView(APIView):
    permission_classes = [IsAuthenticated, IsCitizen]

    def get(self, request):
        profile = request.user.seeker_profile
        records = (
            CredentialRecord.objects.filter(subject=profile)
            .select_related("issuer", "academic_detail", "experience_detail")
            .prefetch_related("anchors")
            .order_by("-created_at")
        )
        counts = records.aggregate(
            total=Count("id"),
            issued=Count("id", filter=Q(status=RecordStatus.ISSUED)),
            pending=Count("id", filter=Q(status=RecordStatus.PENDING_REVIEW)),
            # Offers awaiting this holder's answer — the one number on their
            # dashboard that blocks something real, so it belongs in the summary
            # rather than being recounted from the record list by the client.
            offered=Count("id", filter=Q(status=RecordStatus.OFFERED)),
            pending_anchor=Count("id", filter=Q(status=RecordStatus.PENDING_ANCHOR)),
            revoked=Count("id", filter=Q(status=RecordStatus.REVOKED)),
            academic=Count(
                "id", filter=Q(record_type=RecordType.ACADEMIC, status=RecordStatus.ISSUED)
            ),
            experience=Count(
                "id", filter=Q(record_type=RecordType.EXPERIENCE, status=RecordStatus.ISSUED)
            ),
        )
        return Response(
            {
                "profile": {
                    "full_name": request.user.full_name,
                    "headline": profile.headline,
                    "public_slug": profile.public_slug,
                    "passport_url": profile.passport_url,
                    "is_discoverable": profile.is_discoverable,
                },
                "summary": counts,
                "records": CredentialRecordSerializer(records, many=True).data,
            }
        )


@extend_schema_view(
    list=extend_schema(tags=["passport"], summary="My share links"),
    create=extend_schema(tags=["passport"], summary="Create a share link"),
    destroy=extend_schema(tags=["passport"], summary="Revoke a share link"),
)
class ShareLinkViewSet(viewsets.ModelViewSet):
    serializer_class = ShareLinkSerializer
    permission_classes = [IsAuthenticated, IsCitizen, IsSubjectOfRecord]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return ShareLink.objects.filter(seeker=self.request.user.seeker_profile).prefetch_related(
            "selections"
        )

    def perform_create(self, serializer):
        link = serializer.save()
        record_event(
            AuditAction.SHARE_LINK_CREATED,
            actor=self.request.user,
            obj=link,
            metadata={
                "include_all": link.include_all,
                "masked": link.mask_identifiers,
                "has_passphrase": link.requires_passphrase,
                "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            },
            request=self.request,
        )

    def perform_destroy(self, instance):
        # Soft revoke: the row is kept so the audit trail and view history of a
        # link that was already shared survive its revocation.
        instance.revoked_at = timezone.now()
        instance.save(update_fields=["revoked_at", "updated_at"])
        record_event(
            AuditAction.SHARE_LINK_REVOKED,
            actor=self.request.user,
            obj=instance,
            request=self.request,
        )


@extend_schema(
    tags=["passport"],
    summary="QR code for a share link",
    responses={(200, "image/png"): bytes},
)
class ShareLinkQRView(APIView):
    """Renders the share URL as a PNG QR code — proposal §6.1/§6.3."""

    permission_classes = [IsAuthenticated, IsCitizen]

    def get(self, request, pk):
        import qrcode

        link = ShareLink.objects.filter(pk=pk, seeker=request.user.seeker_profile).first()
        if link is None:
            return Response(
                {"error": {"code": "not_found", "message": "Share link not found.", "details": {}}},
                status=status.HTTP_404_NOT_FOUND,
            )

        qr = qrcode.QRCode(
            version=None,
            # High error correction so a QR printed on a certificate still scans
            # after a photocopy or a coffee ring.
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=2,
        )
        qr.add_data(link.url)
        qr.make(fit=True)

        buffer = io.BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
        buffer.seek(0)
        return FileResponse(
            buffer, content_type="image/png", filename=f"aafno-praman-{link.token[:8]}.png"
        )


@extend_schema(
    tags=["analytics"],
    summary="My organisation's verification quota",
    responses=inline_serializer(
        name="QuotaStatus",
        fields={
            "plan": serializers.CharField(),
            "used": serializers.IntegerField(),
            "limit": serializers.IntegerField(allow_null=True),
            "remaining": serializers.IntegerField(allow_null=True),
            "unlimited": serializers.BooleanField(),
            "resets_at": serializers.DateTimeField(),
        },
    ),
)
class QuotaView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        return Response(QuotaService.status_for(request.organization))


@extend_schema(tags=["analytics"], summary="My organisation's verification history")
class VerificationHistoryView(ListAPIView):
    serializer_class = VerificationLogSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ["result"]

    def get_queryset(self):
        return VerificationLog.objects.filter(
            verifier_org=self.request.organization
        ).select_related("record", "record__issuer")


@extend_schema(
    tags=["analytics"],
    summary="Verification analytics (Pro tier)",
    responses=inline_serializer(
        name="VerificationAnalytics",
        fields={
            "total_verifications": serializers.IntegerField(),
            "by_result": serializers.DictField(child=serializers.IntegerField()),
            "flagged_count": serializers.IntegerField(),
            "flagged_rate": serializers.FloatField(),
            "quota": serializers.DictField(),
            "top_issuers": serializers.ListField(child=serializers.DictField()),
            "recent": VerificationLogSerializer(many=True),
        },
    ),
)
class AnalyticsView(APIView):
    """
    The paid-tier analytics dashboard from §9.

    Available to every plan in the MVP. Gating it behind Pro is a one-line change
    once there is real billing; shipping a paywall before a payment processor
    would only make the demo harder to show.
    """

    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        logs = VerificationLog.objects.filter(verifier_org=request.organization)
        by_result = dict(logs.values_list("result").annotate(count=Count("id")).order_by())
        total = sum(by_result.values())
        flagged = sum(
            by_result.get(result, 0)
            for result in (
                VerificationResult.TAMPERED,
                VerificationResult.REVOKED,
                VerificationResult.NOT_FOUND,
            )
        )

        recent = logs.order_by("-created_at")[:10]
        issuers = (
            logs.exclude(record__isnull=True)
            .values("record__issuer__legal_name")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        return Response(
            {
                "total_verifications": total,
                "by_result": by_result,
                "flagged_count": flagged,
                "flagged_rate": round(flagged / total, 4) if total else 0,
                "quota": QuotaService.status_for(request.organization),
                "top_issuers": [
                    {"issuer": row["record__issuer__legal_name"], "count": row["count"]}
                    for row in issuers
                ],
                "recent": VerificationLogSerializer(recent, many=True).data,
            }
        )


@extend_schema(tags=["analytics"], summary="Search discoverable candidates")
class CandidateSearchView(ListAPIView):
    """
    Employer candidate discovery (§5.3).

    Restricted to seekers who explicitly opted in (HR-07). Without that opt-in
    this endpoint would be a scraper for every citizen's education history, which
    is a considerably worse outcome than the fraud the platform sets out to stop.
    """

    serializer_class = CandidateSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_queryset(self):
        from apps.accounts.models import SeekerProfile

        queryset = (
            SeekerProfile.objects.filter(is_discoverable=True)
            .select_related("user")
            .annotate(
                verified_academic_count=Count(
                    "records",
                    filter=Q(
                        records__status=RecordStatus.ISSUED,
                        records__record_type=RecordType.ACADEMIC,
                    ),
                    distinct=True,
                ),
                verified_experience_count=Count(
                    "records",
                    filter=Q(
                        records__status=RecordStatus.ISSUED,
                        records__record_type=RecordType.EXPERIENCE,
                    ),
                    distinct=True,
                ),
            )
        )

        search = self.request.query_params.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(user__full_name__icontains=search)
                | Q(headline__icontains=search)
                | Q(records__academic_detail__degree_title__icontains=search)
            ).distinct()

        return queryset.order_by("-verified_academic_count")

    def get_serializer(self, *args, **kwargs):
        # DRF calls this as get_serializer(page, many=True); schema generation
        # calls it with no arguments. Accepting both keeps the endpoint in the
        # generated OpenAPI client instead of being dropped from it.
        queryset = args[0] if args else self.get_queryset()
        rows = [
            {
                "id": profile.pk,
                "full_name": profile.user.full_name,
                "headline": profile.headline,
                "public_slug": profile.public_slug,
                "verified_academic_count": profile.verified_academic_count,
                "verified_experience_count": profile.verified_experience_count,
                "highest_qualification": self._highest(profile),
            }
            for profile in queryset
        ]
        return CandidateSerializer(rows, many=True)

    @staticmethod
    def _highest(profile) -> str:
        order = ["DOCTORATE", "MASTERS", "BACHELORS", "DIPLOMA", "PLUS_TWO", "SCHOOL"]
        levels = {
            record.academic_detail.level
            for record in profile.records.filter(
                status=RecordStatus.ISSUED, record_type=RecordType.ACADEMIC
            ).select_related("academic_detail")
            if getattr(record, "academic_detail", None)
        }
        for level in order:
            if level in levels:
                return level
        return ""
