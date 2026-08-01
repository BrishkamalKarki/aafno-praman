"""
Test settings.

The chain is disabled by default so unit tests never depend on a running node;
the ledger client's fake adapter records what *would* have been submitted.
Tests that exercise real chain behaviour live in the Hardhat suite, and the
integration test marked `chain` re-enables this against a live node.
"""

from .base import *

DEBUG = False
CHAIN["ENABLED"] = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Fast, deterministic hashing — real PBKDF2 iterations make the suite crawl.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Throttling must be off by default, or the 30th request in a test file starts
# returning 429 for reasons unrelated to the assertion. The throttle tests
# re-enable it explicitly with override_settings.
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "verify_anon": None,
    "auth": None,
    "share_unlock": None,
    "issue": None,
    "confirm": None,
    "confirm_resend": None,
}

LOGGING["root"]["level"] = "ERROR"
LOGGING["loggers"]["apps.ledger"]["level"] = "ERROR"
