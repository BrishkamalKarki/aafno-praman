"""
Shared Django settings for Aafno Praman.

Split settings: `base` holds everything common, `dev` / `prod` / `test` layer on
environment-specific overrides. Nothing secret is ever committed here — every
sensitive value reads from the environment and, where a missing value would be
dangerous rather than merely inconvenient, has no default at all.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:3000"]),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    CHAIN_ENABLED=(bool, True),
    CHAIN_RPC_URL=(str, "http://127.0.0.1:8545"),
    CHAIN_ID=(int, 31337),
    CHAIN_CONTRACT_ADDRESS=(str, ""),
    CHAIN_REGISTRAR_PRIVATE_KEY=(str, ""),
    CHAIN_TX_TIMEOUT_SECONDS=(int, 30),
    CHAIN_GAS_MULTIPLIER=(float, 1.2),
    PUBLIC_APP_URL=(str, "http://localhost:3000"),
    VERIFY_ANON_THROTTLE=(str, "60/hour"),
    FREE_PLAN_MONTHLY_LOOKUPS=(int, 50),
    CACHE_URL=(str, "locmemcache://aafnopraman"),
    CREDENTIAL_CONFIRM_TTL_HOURS=(int, 168),
)

# Read .env if present. Absent in Docker, where compose injects the environment.
env_file = BASE_DIR / ".env"
if env_file.exists():
    env.read_env(str(env_file))

# --------------------------------------------------------------------- core

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # Local — order matters: accounts defines AUTH_USER_MODEL
    "apps.common",
    "apps.accounts",
    "apps.organizations",
    "apps.credentials",
    "apps.ledger",
    "apps.verification",
    "apps.audit",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ----------------------------------------------------------------- database

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = 60

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------- cache
#
# Every DRF throttle in this file is only as good as the cache behind it. The
# default LocMemCache is per-process, so under gunicorn with N workers a
# "10/minute" login limit is really 10N/minute and resets on every deploy — a
# silently ineffective rate limit is worse than a documented absent one.
#
# Local development keeps LocMemCache (single process, no extra service to run).
# Any multi-process deployment MUST set CACHE_URL to a shared backend; prod.py
# refuses to boot without one.
CACHES = {"default": env.cache("CACHE_URL")}

# --------------------------------------------------------------------- auth

AUTH_USER_MODEL = "accounts.User"

# PBKDF2 is Django's default and is FIPS-friendly; Argon2 would be stronger but
# adds a compiled dependency. Iteration count comes from Django 5.1's default,
# which is raised every release.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ------------------------------------------------------------ i18n / time

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kathmandu"  # NPT (UTC+05:45) — the platform's operating zone
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------------ static/media

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Uploaded diplomas are PDFs and scans; 10 MB is generous and bounds abuse.
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"]
MAX_BATCH_ROWS = 200  # must not exceed CredentialRegistry.MAX_BATCH

# ---------------------------------------------------------------------- DRF

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Deny by default. Every public endpoint opts out explicitly, so forgetting
    # a permission class fails closed instead of leaking credential data.
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (),
    "DEFAULT_THROTTLE_RATES": {
        # Unauthenticated QR / ID verification. Generous enough for a real
        # recruiter, tight enough that scraping the registry is impractical.
        "verify_anon": env("VERIFY_ANON_THROTTLE"),
        # Login and password endpoints — credential stuffing defence.
        "auth": "10/minute",
        # Share-link passphrase attempts (E-04): no brute-force oracle.
        "share_unlock": "10/hour",
        "issue": "300/hour",
        # Credential confirmation links. The token is the only thing between an
        # attacker and someone else's credential, so guessing is capped hard.
        "confirm": "10/hour",
        # Resending a confirmation email. Unbounded, this endpoint is a free
        # mail-bomb aimed at any address an attacker chooses.
        "confirm_resend": "3/hour",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,  # no blacklist app; rotation alone
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.TokenObtainSerializer",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Aafno Praman API",
    "DESCRIPTION": (
        "Blockchain-anchored academic credential and employment verification "
        "for Nepal. Write access is permissioned to registrar-approved issuers; "
        "the verification read path is public and unauthenticated."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    # Two distinct choice sets are each named "role", and two are named "status".
    # Without these, generated clients get types like `Role4e1Enum` — a hash
    # suffix that changes if the choices ever move, silently breaking the
    # frontend's imports. Naming them pins the contract.
    "ENUM_NAME_OVERRIDES": {
        "UserRoleEnum": "apps.accounts.models.Role.choices",
        "MembershipRoleEnum": "apps.organizations.models.MembershipRole.choices",
        "OrganizationStatusEnum": "apps.organizations.models.OrganizationStatus.choices",
        "RecordStatusEnum": "apps.credentials.models.RecordStatus.choices",
    },
    "TAGS": [
        {"name": "auth", "description": "Registration, login, token refresh"},
        {"name": "registrar", "description": "Platform root of trust: issuer onboarding"},
        {"name": "organizations", "description": "Institution and employer self-service"},
        {"name": "credentials", "description": "Issuance — academic and experience records"},
        {"name": "passport", "description": "Job seeker credential passport and share links"},
        {"name": "verification", "description": "Public verification (no account required)"},
        {"name": "analytics", "description": "Employer dashboard metrics"},
    ],
}

# ---------------------------------------------------------------------- CORS

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = False  # JWT travels in the Authorization header

# ------------------------------------------------------------------ security

# Applied in every environment; prod.py tightens further.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Fernet key protecting custodial issuer private keys at rest. Deliberately has
# no default: booting with a predictable encryption key would make every
# issuer's signing key recoverable from a database dump alone.
KEY_ENCRYPTION_KEY = env("KEY_ENCRYPTION_KEY")

# --------------------------------------------------------- citizen identity
#
# Secret mixed into every national-ID lookup hash. No default, for the same
# reason KEY_ENCRYPTION_KEY has none, but the threat here is subtler and worse.
#
# A Nepali citizenship number is district-structured and sequentially issued —
# the whole plausible keyspace is small enough to enumerate exhaustively. A
# plain SHA-256 of one is therefore reversible in seconds on commodity hardware:
# hashing a low-entropy identifier is not anonymisation. HMAC under a secret the
# database does not contain is what makes the lookup column safe to hold.
#
# Rotating this invalidates every stored hash, which is why national_id_hmac
# carries an hmac_version alongside it — see apps/accounts/identity.py.
NATIONAL_ID_PEPPER = env("NATIONAL_ID_PEPPER")
NATIONAL_ID_HMAC_VERSION = 1

# How long a credential confirmation link stays valid. Long enough that a
# graduate who checks email weekly does not lose their degree offer; short
# enough that a leaked institutional mail archive is not a permanent takeover
# toolkit.
CREDENTIAL_CONFIRM_TTL_HOURS = env("CREDENTIAL_CONFIRM_TTL_HOURS")

# ----------------------------------------------------------------- blockchain

CHAIN = {
    "ENABLED": env("CHAIN_ENABLED"),
    "RPC_URL": env("CHAIN_RPC_URL"),
    "CHAIN_ID": env("CHAIN_ID"),
    "CONTRACT_ADDRESS": env("CHAIN_CONTRACT_ADDRESS"),
    "REGISTRAR_PRIVATE_KEY": env("CHAIN_REGISTRAR_PRIVATE_KEY"),
    "TX_TIMEOUT_SECONDS": env("CHAIN_TX_TIMEOUT_SECONDS"),
    "GAS_MULTIPLIER": env("CHAIN_GAS_MULTIPLIER"),
    "MAX_ANCHOR_ATTEMPTS": 5,
    # Sponsored gas (HR-05). The platform tops up an issuer's signing account so
    # a university registrar never has to acquire crypto to issue a degree.
    # Top-up fires on approval and again whenever the balance falls below the
    # floor, so a busy institution does not stall mid-graduation-batch.
    "GAS_TOPUP_WEI": env.int("CHAIN_GAS_TOPUP_WEI", default=10**17),  # 0.1 ETH
    "GAS_MIN_BALANCE_WEI": env.int("CHAIN_GAS_MIN_BALANCE_WEI", default=10**16),  # 0.01 ETH
}

# Domain separation tag mixed into every record hash. Changing this invalidates
# every QR code ever issued — it is part of the on-chain contract with verifiers.
#
# Deliberately NOT renamed with the rest of the product. This string is hashed
# into every fingerprint already written to the ledger and re-derived by
# `contracts/scripts/chain-proof.js` when a verifier checks one independently.
# Renaming it to match the new brand would make every credential issued before
# the rename verify as TAMPERED — a cosmetic edit with the blast radius of a
# forged-document accusation against every existing holder. It is a protocol
# version, and the version has not changed.
CANONICAL_DOMAIN_TAG = "VERIDOCK-RECORD-V1"

PUBLIC_APP_URL = env("PUBLIC_APP_URL")
FREE_PLAN_MONTHLY_LOOKUPS = env("FREE_PLAN_MONTHLY_LOOKUPS")

# ------------------------------------------------------------------- logging

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name}:{lineno} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        # The ledger is the component whose failures matter most operationally.
        "apps.ledger": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
        "apps.verification": {"level": "INFO", "handlers": ["console"], "propagate": False},
    },
}
