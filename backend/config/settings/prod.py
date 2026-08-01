"""
Production settings.

Everything here is a hardening step that would be annoying in development and is
non-negotiable in production.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *
from .base import env

DEBUG = False

# No wildcard fallback: an unset ALLOWED_HOSTS should stop the boot, not open the
# service up to Host-header poisoning.
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Behind a TLS-terminating proxy (Render, Railway, nginx).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Only the explicit allow-list in production — no localhost regexes.
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = ("rest_framework.renderers.JSONRenderer",)

# Media belongs on object storage in production; the local filesystem does not
# survive a container restart on Render or Railway.
if env.str("AWS_STORAGE_BUCKET_NAME", default=""):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
            "region_name": env.str("AWS_S3_REGION_NAME", default="ap-south-1"),
            "endpoint_url": env.str("AWS_S3_ENDPOINT_URL", default=None),
            "default_acl": "private",
            "querystring_auth": True,
            "querystring_expire": 300,
        },
    }

# A per-process cache silently disables every rate limit in the system once more
# than one gunicorn worker is running — including the claim-code redemption
# limit that protects national identities. Fail the boot rather than serve with
# throttles that only appear to work.
if "locmem" in CACHES["default"]["BACKEND"].lower():
    raise ImproperlyConfigured(
        "CACHE_URL must point at a shared cache (e.g. redis://…) in production. "
        "LocMemCache is per-process, which makes every DRF throttle ineffective "
        "under multiple workers."
    )

LOGGING["root"]["level"] = "INFO"
LOGGING["loggers"]["apps.ledger"]["level"] = "INFO"
