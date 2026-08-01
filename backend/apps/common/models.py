"""Abstract base models shared across every app."""

import uuid

from django.db import models


class UUIDModel(models.Model):
    """
    UUID primary keys everywhere.

    Sequential integer IDs would let anyone holding one credential URL walk the
    entire registry by decrementing the number — the exact enumeration risk
    flagged as HR-07. UUIDv4 keys make identifiers unguessable.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimestampedModel):
    class Meta:
        abstract = True
