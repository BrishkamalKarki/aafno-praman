"""Issuance endpoints — the issuer console's API surface."""

from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import (
    CanIssueCredentials,
    IsCitizen,
    IsEmployer,
    IsInstitution,
    IsRecordIssuerOrReadOnly,
)
from apps.common.throttling import IssuanceThrottle
from apps.ledger.services import revoke_record

from .models import CredentialRecord, RecordStatus, RecordType
from .serializers import (
    AcademicIssueSerializer,
    BatchUploadSerializer,
    CredentialRecordSerializer,
    ExperienceClaimSerializer,
    ExperienceIssueSerializer,
    IssuanceBatchSerializer,
    RejectSerializer,
    ReviewSerializer,
    RevokeSerializer,
)
from .services import claim_record, endorse_claim, import_batch, issue_record, reject_claim


class _IssueView(APIView):
    """
    Shared issuance handler.

    Returns **201** when the record is anchored and confirmed, **202** when it is
    saved but the ledger has not confirmed yet. The distinction is not pedantry:
    a 201 means an employer can verify it right now, a 202 means "come back in a
    moment", and collapsing them would make the issuer console lie about state.
    """

    throttle_classes = [IssuanceThrottle]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = None

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        record = issue_record(
            issuer=request.organization,
            actor=request.user,
            request=request,
            record_type=data["record_type"],
            subject_email=data["subject_email"],
            subject_full_name=data["subject_full_name"],
            detail_data=data["detail"],
            document=data.get("document"),
            national_id=data.get("national_id", ""),
        )

        # 202, not 201. Under the consent gate issuance creates an *offer*: the
        # credential is recorded and its subject has been asked, but nothing is
        # published and nothing is on chain until they confirm. Returning 201
        # would tell the issuer's client the resource was fully created, which
        # is exactly the misunderstanding the gate exists to prevent.
        confirmed = record.status == RecordStatus.ISSUED
        return Response(
            CredentialRecordSerializer(record).data,
            status=status.HTTP_201_CREATED if confirmed else status.HTTP_202_ACCEPTED,
        )


@extend_schema(
    tags=["credentials"],
    summary="Issue an academic credential",
    request=AcademicIssueSerializer,
    responses={201: CredentialRecordSerializer, 202: CredentialRecordSerializer},
)
class IssueAcademicView(_IssueView):
    permission_classes = [IsAuthenticated, IsInstitution]
    serializer_class = AcademicIssueSerializer


@extend_schema(
    tags=["credentials"],
    summary="Issue a work experience record",
    request=ExperienceIssueSerializer,
    responses={201: CredentialRecordSerializer, 202: CredentialRecordSerializer},
)
class IssueExperienceView(_IssueView):
    permission_classes = [IsAuthenticated, IsEmployer]
    serializer_class = ExperienceIssueSerializer


@extend_schema(
    tags=["credentials"],
    summary="Bulk-issue a graduating batch from CSV",
    request=BatchUploadSerializer,
    responses={200: IssuanceBatchSerializer},
)
class BatchUploadView(APIView):
    permission_classes = [IsAuthenticated, CanIssueCredentials]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [IssuanceThrottle]

    def post(self, request):
        serializer = BatchUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        batch = import_batch(
            issuer=request.organization,
            actor=request.user,
            uploaded_file=serializer.validated_data["file"],
            record_type=serializer.validated_data["record_type"],
            request=request,
        )
        # 200 rather than 201: a partially successful batch is the common case,
        # and the body carries the per-row outcome.
        return Response(IssuanceBatchSerializer(batch).data, status=status.HTTP_200_OK)


@extend_schema(tags=["credentials"], summary="List this organisation's batches")
class BatchListView(ListAPIView):
    serializer_class = IssuanceBatchSerializer
    permission_classes = [IsAuthenticated, CanIssueCredentials]

    def get_queryset(self):
        return self.request.organization.batches.prefetch_related("errors")


@extend_schema_view(
    list=extend_schema(tags=["credentials"], summary="Records issued by my organisation"),
    retrieve=extend_schema(tags=["credentials"], summary="One issued record"),
)
class IssuedRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """
    The issuer's own records, plus the two post-issuance transitions.

    Read-only by design: there is no update endpoint, because editing an anchored
    record is definitionally tampering. Corrections go through supersede, and
    withdrawals through revoke — both of which leave a trail.
    """

    serializer_class = CredentialRecordSerializer
    permission_classes = [IsAuthenticated, CanIssueCredentials, IsRecordIssuerOrReadOnly]
    filterset_fields = ["record_type", "status"]
    search_fields = ["subject_full_name", "subject_email", "record_hash"]
    ordering_fields = ["created_at", "issued_at"]

    def get_queryset(self):
        return (
            CredentialRecord.objects.filter(issuer=self.request.organization)
            .select_related("issuer", "academic_detail", "experience_detail")
            .prefetch_related("anchors")
            .order_by("-created_at")
        )

    @extend_schema(summary="Revoke an issued record", request=RevokeSerializer)
    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        serializer = RevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record = self.get_object()
        revoke_record(
            record,
            reason=serializer.validated_data["reason"],
            actor=request.user,
            request=request,
        )
        record.refresh_from_db()
        return Response(CredentialRecordSerializer(record).data)

    @extend_schema(summary="Issuance statistics for my organisation")
    @action(detail=False, methods=["get"])
    def stats(self, request):
        stats = CredentialRecord.objects.filter(issuer=request.organization).aggregate(
            total=Count("id"),
            issued=Count("id", filter=Q(status=RecordStatus.ISSUED)),
            # The consent gate's own tile. Without it the issuer dashboard has no
            # way to show how many graduates have been asked and not yet
            # answered — which is the number that decides whether a batch is
            # actually finished.
            offered=Count("id", filter=Q(status=RecordStatus.OFFERED)),
            declined=Count("id", filter=Q(status=RecordStatus.DECLINED)),
            pending_anchor=Count("id", filter=Q(status=RecordStatus.PENDING_ANCHOR)),
            pending_review=Count("id", filter=Q(status=RecordStatus.PENDING_REVIEW)),
            revoked=Count("id", filter=Q(status=RecordStatus.REVOKED)),
            academic=Count("id", filter=Q(record_type=RecordType.ACADEMIC)),
            experience=Count("id", filter=Q(record_type=RecordType.EXPERIENCE)),
        )
        return Response(stats)


@extend_schema_view(
    list=extend_schema(tags=["credentials"], summary="Claims awaiting my endorsement"),
)
class ClaimReviewViewSet(viewsets.ReadOnlyModelViewSet):
    """The employer's inbox for seeker-submitted experience claims (§6.2)."""

    serializer_class = CredentialRecordSerializer
    permission_classes = [IsAuthenticated, CanIssueCredentials, IsRecordIssuerOrReadOnly]

    def get_queryset(self):
        return (
            CredentialRecord.objects.filter(
                issuer=self.request.organization, status=RecordStatus.PENDING_REVIEW
            )
            .select_related("issuer", "experience_detail", "subject__user")
            .order_by("submitted_at")
        )

    @extend_schema(summary="Endorse a claim and anchor it", request=ReviewSerializer)
    @action(detail=True, methods=["post"])
    def endorse(self, request, pk=None):
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record = endorse_claim(
            self.get_object(),
            actor=request.user,
            note=serializer.validated_data.get("note", ""),
            request=request,
        )
        confirmed = record.status == RecordStatus.ISSUED
        return Response(
            CredentialRecordSerializer(record).data,
            status=status.HTTP_200_OK if confirmed else status.HTTP_202_ACCEPTED,
        )

    @extend_schema(summary="Reject a claim", request=RejectSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record = reject_claim(
            self.get_object(),
            actor=request.user,
            note=serializer.validated_data["note"],
            request=request,
        )
        return Response(CredentialRecordSerializer(record).data)


@extend_schema(
    tags=["passport"],
    summary="Claim past employment for an employer to endorse",
    request=ExperienceClaimSerializer,
    responses={201: CredentialRecordSerializer},
)
class ExperienceClaimView(APIView):
    permission_classes = [IsAuthenticated, IsCitizen]

    def post(self, request):
        serializer = ExperienceClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        record = claim_record(
            seeker=request.user.seeker_profile,
            issuer=data["employer"],
            actor=request.user,
            request=request,
            record_type=RecordType.EXPERIENCE,
            subject_email=request.user.email,
            subject_full_name=request.user.full_name,
            detail_data=data["detail"],
        )
        return Response(CredentialRecordSerializer(record).data, status=status.HTTP_201_CREATED)
