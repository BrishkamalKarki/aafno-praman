"""Authentication and profile endpoints."""

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.common.permissions import IsCitizen
from apps.common.throttling import AuthThrottle

from .models import SeekerProfile
from .serializers import (
    ChangePasswordSerializer,
    RegistrationSerializer,
    SeekerProfileSerializer,
    UserSerializer,
)


@extend_schema(tags=["auth"], summary="Register a new account")
class RegisterView(generics.CreateAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        record_event(
            AuditAction.USER_REGISTERED,
            actor=user,
            obj=user,
            metadata={"role": user.role},
            request=request,
        )

        # Records issued to this email before signup are linked by a post_save
        # signal; refreshing here means the response already reflects them.
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["auth"], summary="Obtain an access and refresh token pair")
class LoginView(TokenObtainPairView):
    throttle_classes = [AuthThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            from .models import User

            user = User.objects.filter(email=request.data.get("email", "").lower()).first()
            record_event(AuditAction.USER_LOGGED_IN, actor=user, obj=user, request=request)
        return response


@extend_schema(tags=["auth"], summary="Exchange a refresh token for a new access token")
class RefreshView(TokenRefreshView):
    throttle_classes = [AuthThrottle]


@extend_schema_view(
    get=extend_schema(tags=["auth"], summary="Current user"),
    patch=extend_schema(tags=["auth"], summary="Update current user"),
)
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user

    def get_queryset(self):  # pragma: no cover - required by DRF introspection
        from .models import User

        return User.objects.none()


@extend_schema_view(
    get=extend_schema(tags=["passport"], summary="Seeker profile"),
    patch=extend_schema(tags=["passport"], summary="Update seeker profile"),
)
class SeekerProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = SeekerProfileSerializer
    permission_classes = [IsAuthenticated, IsCitizen]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self) -> SeekerProfile:
        return self.request.user.seeker_profile

    def get_queryset(self):  # pragma: no cover
        return SeekerProfile.objects.none()


@extend_schema(
    tags=["auth"],
    summary="Change password",
    request=ChangePasswordSerializer,
    responses=inline_serializer(name="PasswordChanged", fields={"detail": serializers.CharField()}),
)
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthThrottle]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Existing refresh tokens stay valid: without a blacklist there is no way
        # to revoke them, and pretending otherwise would be a false security
        # claim. Documented in docs/SECURITY.md as a known MVP limitation.
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)
