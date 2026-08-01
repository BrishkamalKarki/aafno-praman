"""
Citizen identity: wallet binding, peppered national-ID lookups, claim codes.

## Why the data step deletes rather than converts

Existing ``SeekerProfile`` rows cannot be carried forward. The new model keys
identity on ``national_id_hmac``, which is mandatory and unique, while the old
schema left ``national_id`` blank on almost every row — it was an optional,
self-asserted field. There is nothing to derive a real citizenship number from.

Without this step the migration would also simply fail: ``national_id_hmac`` is
added with a one-off default of ``''``, so two or more surviving rows would
collide on ``identity_national_id_unique`` a few operations later.

The three alternatives were all worse:

* **Synthesise a placeholder hash per row.** Creates identities that look
  attested but are not, in a table whose entire purpose is recording who
  attested to what. This is the option that quietly poisons the trust model.
* **Leave the column nullable.** Defers the problem into the application, where
  every query then has to handle an identity with no identity.
* **Carry forward the old self-asserted values.** Migrates forward exactly the
  unverified assertions this redesign exists to eliminate.

So pre-migration profiles are dropped. They are development fixtures — the
project has no released version and no deployment — and the way to get them back
is ``manage.py seed_demo``, which now provisions identities through the
issuer-attested path like everything else.

``CredentialRecord.subject`` is SET_NULL and ``ShareLink.seeker`` is CASCADE, so
the deletion leaves the schema consistent rather than orphaning rows.
"""

import apps.common.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def drop_unmigrable_profiles(apps, schema_editor):
    """
    Delete pre-migration profiles. See the module docstring for why.

    The ``SET CONSTRAINTS ALL IMMEDIATE`` is not optional on PostgreSQL. The
    cascade from this delete leaves deferred foreign-key trigger events queued
    until commit, and the very next ``ALTER TABLE`` in this migration then fails
    with "cannot ALTER TABLE because it has pending trigger events". Forcing the
    deferred checks to run now drains that queue inside the same transaction.
    """
    apps.get_model("accounts", "SeekerProfile").objects.all().delete()

    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def noop_reverse(apps, schema_editor):
    """
    Reversing cannot restore deleted rows.

    Deliberately a no-op rather than an error: refusing to reverse would strand a
    developer who needs to roll the schema back, and the data became
    unrecoverable the moment the forward migration ran.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='IdentityClaim',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('code_hash', models.CharField(editable=False, max_length=64, unique=True)),
                ('delivered_to', models.EmailField(help_text='The address the issuer had on file. Recorded for dispute resolution.', max_length=254)),
                ('expires_at', models.DateTimeField()),
                ('redeemed_at', models.DateTimeField(blank=True, null=True)),
                ('attempts', models.PositiveSmallIntegerField(default=0, help_text='Failed redemption attempts. Bounded to stop code guessing.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'accounts_identityclaim',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='WalletNonce',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('nonce', models.CharField(editable=False, max_length=64, unique=True)),
                ('address', models.CharField(max_length=42, validators=[apps.common.validators.validate_eth_address])),
                ('message', models.TextField(editable=False)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('requested_ip_hash', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'accounts_walletnonce',
            },
        ),
        migrations.RemoveConstraint(
            model_name='seekerprofile',
            name='seeker_national_id_unique_when_set',
        ),
        # Must precede the AddField/AddConstraint pair below: national_id_hmac is
        # added with a one-off default of '', so surviving rows would collide on
        # identity_national_id_unique.
        migrations.RunPython(drop_unmigrable_profiles, noop_reverse),
        migrations.RemoveField(
            model_name='seekerprofile',
            name='national_id',
        ),
        migrations.AddField(
            model_name='seekerprofile',
            name='binding_state',
            field=models.CharField(choices=[('UNBOUND', 'Created by an issuer, not yet invited'), ('INVITED', 'Claim code issued, awaiting redemption'), ('BOUND', 'Claimed and controlled by a wallet')], default='UNBOUND', max_length=10),
        ),
        migrations.AddField(
            model_name='seekerprofile',
            name='bound_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='seekerprofile',
            name='bound_via',
            field=models.ForeignKey(blank=True, help_text='The issuer whose attestation the citizen used to claim this identity.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='organizations.organization'),
        ),
        migrations.AddField(
            model_name='seekerprofile',
            name='hmac_version',
            field=models.PositiveSmallIntegerField(default=1, help_text='Which pepper generation produced national_id_hmac. Enables rotation.'),
        ),
        migrations.AddField(
            model_name='seekerprofile',
            name='legal_name',
            field=models.CharField(default='', help_text='Name as attested by the issuer that created this identity.', max_length=150),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='seekerprofile',
            name='national_id_ct',
            field=models.BinaryField(blank=True, default=b'', help_text='Fernet ciphertext of the number. Read only for dispute resolution.'),
        ),
        migrations.AddField(
            model_name='seekerprofile',
            name='national_id_hmac',
            field=models.CharField(default='', help_text='HMAC-SHA256 of the normalised citizenship number under the pepper.', max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='seekerprofile',
            name='primary_email',
            field=models.EmailField(blank=True, help_text='Contact and notification address. Not the identity key.', max_length=254),
        ),
        migrations.AddField(
            model_name='seekerprofile',
            name='primary_phone',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='seekerprofile',
            name='wallet_address',
            field=models.CharField(blank=True, help_text='EIP-55 checksummed. One wallet per identity, one identity per wallet.', max_length=42, validators=[apps.common.validators.validate_eth_address]),
        ),
        migrations.AlterField(
            model_name='seekerprofile',
            name='user',
            field=models.OneToOneField(blank=True, help_text='Null until the citizen claims the identity and signs in.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='seeker_profile', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(
            model_name='seekerprofile',
            index=models.Index(fields=['binding_state'], name='accounts_se_binding_c6adf3_idx'),
        ),
        migrations.AddIndex(
            model_name='seekerprofile',
            index=models.Index(fields=['primary_email'], name='accounts_se_primary_6d2218_idx'),
        ),
        migrations.AddConstraint(
            model_name='seekerprofile',
            constraint=models.UniqueConstraint(fields=('national_id_hmac',), name='identity_national_id_unique'),
        ),
        migrations.AddConstraint(
            model_name='seekerprofile',
            constraint=models.UniqueConstraint(condition=models.Q(('wallet_address', ''), _negated=True), fields=('wallet_address',), name='identity_wallet_unique_when_set'),
        ),
        migrations.AddConstraint(
            model_name='seekerprofile',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('binding_state', 'BOUND'), _negated=True), models.Q(models.Q(('wallet_address', ''), _negated=True), ('user__isnull', False)), _connector='OR'), name='identity_bound_requires_wallet_and_user'),
        ),
        migrations.AddField(
            model_name='identityclaim',
            name='identity',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='claims', to='accounts.seekerprofile'),
        ),
        migrations.AddField(
            model_name='identityclaim',
            name='issued_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='identity_claims', to='organizations.organization'),
        ),
        migrations.AddIndex(
            model_name='walletnonce',
            index=models.Index(fields=['expires_at'], name='accounts_wa_expires_3f4782_idx'),
        ),
        migrations.AddIndex(
            model_name='walletnonce',
            index=models.Index(fields=['address', '-created_at'], name='accounts_wa_address_ad5e6d_idx'),
        ),
        migrations.AddIndex(
            model_name='identityclaim',
            index=models.Index(fields=['expires_at'], name='accounts_id_expires_0476d4_idx'),
        ),
        migrations.AddConstraint(
            model_name='identityclaim',
            constraint=models.UniqueConstraint(condition=models.Q(('redeemed_at__isnull', True)), fields=('identity',), name='identityclaim_one_open_per_identity'),
        ),
    ]
