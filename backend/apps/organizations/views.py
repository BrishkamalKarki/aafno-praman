"""Organisation self-service and registrar onboarding endpoints."""

from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.common.permissions import IsOrganizationMember, IsRegistrar

from .models import Organization, OrganizationStatus
from .serializers import (
    MembershipSerializer,
    OrganizationApplicationSerializer,
    OrganizationDirectorySerializer,
    OrganizationDocumentSerializer,
    OrganizationSerializer,
    PlanChangeSerializer,
    RegistrarOrganizationSerializer,
    StatusChangeSerializer,
    SubscriptionSerializer,
)
from .services import (
    approve_organization,
    reinstate_organization,
    reject_organization,
    suspend_organization,
)


@extend_schema(tags=["organizations"], summary="Approved organisations, by name")
class OrganizationDirectoryView(generics.ListAPIView):
    """
    The list of organisations a signed-in user may address.

    Added because the seeker-claim flow needs one: a citizen logging past
    employment must name the employer **by id**, since a free-text employer name
    would let anyone claim a job at a company with no account here and therefore
    no way to dispute it. Until this existed there was no endpoint a citizen
    could read that list from, so the claim flow could not be built at all and
    the employer's review inbox had nothing that could ever reach it.

    Deliberately thin. It returns the name, kind and slug of organisations that
    are already **approved**, which is to say the fact that a given university
    is accredited on this platform — public information by construction, and the
    thing an employer's letterhead states anyway. Contact details, addresses,
    registration numbers, member counts and chain addresses are all absent: this
    is a picker, not a directory of businesses to scrape.
    """

    serializer_class = OrganizationDirectorySerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["legal_name"]
    filterset_fields = ["kind"]

    def get_queryset(self):
        return Organization.objects.filter(status=OrganizationStatus.APPROVED).order_by(
            "legal_name"
        )


@extend_schema(tags=["organizations"], summary="Apply to become an issuer")
class OrganizationApplicationView(generics.CreateAPIView):
    serializer_class = OrganizationApplicationSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = serializer.save()

        record_event(
            AuditAction.ORG_APPLIED,
            actor=request.user,
            organization=organization,
            obj=organization,
            metadata={"kind": organization.kind},
            request=request,
        )
        return Response(OrganizationSerializer(organization).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(tags=["organizations"], summary="My organisation"),
)
class MyOrganizationView(generics.RetrieveAPIView):
    """The organisation the current user belongs to, with its approval state."""

    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_object(self) -> Organization:
        return self.request.organization

    def get_queryset(self):  # pragma: no cover
        return Organization.objects.none()


@extend_schema(tags=["organizations"], summary="Upload an accreditation document")
class OrganizationDocumentView(generics.ListCreateAPIView):
    serializer_class = OrganizationDocumentSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_queryset(self):
        return self.request.organization.documents.all()

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization, uploaded_by=self.request.user)


@extend_schema(tags=["organizations"], summary="List organisation members")
class MembershipListView(generics.ListAPIView):
    serializer_class = MembershipSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_queryset(self):
        return self.request.organization.memberships.select_related("user")


@extend_schema_view(
    get=extend_schema(tags=["organizations"], summary="My organisation's plan"),
    patch=extend_schema(
        tags=["organizations"],
        summary="Switch plan (demo — no payment provider)",
        request=PlanChangeSerializer,
    ),
)
class SubscriptionView(generics.RetrieveUpdateAPIView):
    """
    Read the plan, and switch it.

    ``PATCH`` exists because there is no payment provider wired up: no Stripe,
    no Khalti, no eSewa. Rather than a client-side flag that makes the paid
    tier look real without the quota ever changing, the switch is a genuine
    write — the very next verification is metered against the new limit. What
    is missing is the money, and the endpoint says so instead of miming it.

    Only an OWNER may change it. A viewer flipping their employer onto a paid
    plan is not a billing decision they get to make, even in demo mode.
    """

    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        from .models import Plan, Subscription

        subscription, _ = Subscription.objects.get_or_create(
            organization=self.request.organization,
            defaults={"plan": Plan.FREE, "monthly_lookup_limit": _free_lookup_limit()},
        )
        return subscription

    def get_queryset(self):  # pragma: no cover
        from .models import Subscription

        return Subscription.objects.none()

    def patch(self, request, *args, **kwargs):
        from .models import MembershipRole, Plan

        if request.membership.role != MembershipRole.OWNER:
            raise PermissionDenied("Only the organisation owner can change the plan.")

        serializer = PlanChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.validated_data["plan"]

        subscription = self.get_object()
        subscription.plan = plan
        # 0 means unlimited, per the model. Downgrading restores the configured
        # free allowance rather than whatever the row happened to hold before.
        subscription.monthly_lookup_limit = 0 if plan == Plan.PRO else _free_lookup_limit()
        subscription.save(update_fields=["plan", "monthly_lookup_limit", "updated_at"])

        record_event(
            AuditAction.ORG_APPLIED,
            actor=request.user,
            organization=request.organization,
            obj=subscription,
            metadata={"plan": plan, "demo_mode": True},
            request=request,
        )
        return Response(SubscriptionSerializer(subscription).data)


def _free_lookup_limit() -> int:
    from django.conf import settings

    return settings.FREE_PLAN_MONTHLY_LOOKUPS


@extend_schema(tags=["registrar"])
class RegistrarOrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    The registrar console.

    Read plus four state transitions — approve, reject, suspend, reinstate. There
    is deliberately no generic update endpoint: an organisation's status must only
    ever change through a transition that generates a chain transaction and an
    audit entry, never through a stray PATCH.
    """

    serializer_class = RegistrarOrganizationSerializer
    permission_classes = [IsAuthenticated, IsRegistrar]
    filterset_fields = ["status", "kind"]
    search_fields = ["legal_name", "registration_number", "contact_email"]
    ordering_fields = ["created_at", "legal_name"]

    def get_queryset(self):
        return (
            Organization.objects.all()
            .prefetch_related("documents", "memberships__user")
            .annotate(record_total=Count("issued_records"))
            .order_by("-created_at")
        )

    @extend_schema(summary="Approve an organisation and register it on chain", request=None)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        organization = approve_organization(
            self.get_object(), registrar=request.user, request=request
        )
        return Response(RegistrarOrganizationSerializer(organization).data)

    @extend_schema(summary="Reject an application", request=StatusChangeSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = reject_organization(
            self.get_object(),
            registrar=request.user,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(RegistrarOrganizationSerializer(organization).data)

    @extend_schema(summary="Suspend an approved issuer", request=StatusChangeSerializer)
    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = suspend_organization(
            self.get_object(),
            registrar=request.user,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(RegistrarOrganizationSerializer(organization).data)

    @extend_schema(summary="Reinstate a suspended issuer", request=None)
    @action(detail=True, methods=["post"])
    def reinstate(self, request, pk=None):
        organization = reinstate_organization(
            self.get_object(), registrar=request.user, request=request
        )
        return Response(RegistrarOrganizationSerializer(organization).data)

    @extend_schema(summary="Registrar dashboard counts")
    @action(detail=False, methods=["get"])
    def summary(self, request):
        counts = Organization.objects.aggregate(
            pending=Count("id", filter=Q(status=OrganizationStatus.PENDING)),
            approved=Count("id", filter=Q(status=OrganizationStatus.APPROVED)),
            suspended=Count("id", filter=Q(status=OrganizationStatus.SUSPENDED)),
            rejected=Count("id", filter=Q(status=OrganizationStatus.REJECTED)),
        )
        from apps.credentials.models import CredentialRecord, RecordStatus

        counts["records_issued"] = CredentialRecord.objects.filter(
            status=RecordStatus.ISSUED
        ).count()
        return Response(counts)
