"""Local development settings."""

from .base import *
from .base import env

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Browsable API is genuinely useful when demonstrating the API to judges.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)

# Any localhost port, so `next dev` picking 3001 does not break the frontend.
CORS_ALLOWED_ORIGIN_REGEXES = [r"^http://localhost:\d+$", r"^http://127\.0\.0\.1:\d+$"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

if env.bool("SQL_DEBUG", default=False):
    LOGGING["loggers"]["django.db.backends"]["level"] = "DEBUG"
