"""
Root URL configuration.

The API is versioned under `/api/v1/`. Public, unauthenticated verification
endpoints are grouped under `/api/v1/verify/` so the boundary between "anyone may
call this" and "an approved issuer may call this" is visible in the URL itself.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.common.views import health_check

admin.site.site_header = "Aafno Praman Platform Registrar"
admin.site.site_title = "Aafno Praman"
admin.site.index_title = "Root of trust — issuer onboarding and oversight"

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("organizations/", include("apps.organizations.urls")),
    path("credentials/", include("apps.credentials.urls")),
    path("passport/", include("apps.verification.passport_urls")),
    path("verify/", include("apps.verification.urls")),
    path("registrar/", include("apps.organizations.registrar_urls")),
    path("ledger/", include("apps.ledger.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health"),
    path("api/v1/", include((api_v1, "v1"), namespace="v1")),
    # API documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
