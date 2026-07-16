import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Lower


def remove_legacy_provisional_accounts(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    PendingEmailChange = apps.get_model("accounts", "PendingEmailChange")
    Organization = apps.get_model("organizations", "Organization")

    # Existing pending email-change tokens predate auth-version binding and
    # cannot be made safe retroactively.
    PendingEmailChange.objects.all().delete()

    provisional_user_ids = list(
        User.objects.filter(
            email_verified=False,
            is_staff=False,
            is_superuser=False,
        ).values_list("pk", flat=True)
    )
    if not provisional_user_ids:
        return

    # Legacy registration created personal organizations before verification.
    # Delete those first so the personal-org creator constraint remains valid.
    Organization.objects.filter(
        type="personal", creator_id__in=provisional_user_ids
    ).delete()
    User.objects.filter(pk__in=provisional_user_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        (
            "organizations",
            "0002_exportjob_attempt_count_exportjob_heartbeat_at_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            remove_legacy_provisional_accounts,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="pendingregistration",
            name="user",
        ),
        migrations.AddField(
            model_name="pendingregistration",
            name="email",
            field=models.EmailField(default="", max_length=254),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="pendingregistration",
            constraint=models.UniqueConstraint(
                Lower("email"),
                name="accounts_pending_registration_email_ci_uniq",
            ),
        ),
        migrations.AddField(
            model_name="pendingemailchange",
            name="auth_version",
            field=models.PositiveBigIntegerField(default=1),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="pendingemailchange",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                to="accounts.user",
            ),
        ),
    ]
