from django.conf import settings
from django.db import migrations, models
from django.db.models import Count

PERSONAL_OWNER_SQL = """
CREATE OR REPLACE FUNCTION organizations_check_active_owner(org_id bigint)
RETURNS void AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM organizations_organization
        WHERE id = org_id AND type = 'group'
    ) AND NOT EXISTS (
        SELECT 1
        FROM organizations_membership membership
        JOIN accounts_user account ON account.id = membership.user_id
        WHERE membership.organization_id = org_id
          AND membership.role = 'owner'
          AND account.is_active
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'group organization ' || org_id || ' requires at least one active owner';
    END IF;

    IF EXISTS (
        SELECT 1 FROM organizations_organization
        WHERE id = org_id AND type = 'personal'
    ) AND NOT EXISTS (
        SELECT 1
        FROM organizations_membership membership
        JOIN organizations_organization organization
          ON organization.id = membership.organization_id
        WHERE membership.organization_id = org_id
          AND membership.user_id = organization.creator_id
          AND membership.role = 'owner'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'personal organization ' || org_id || ' requires its creator owner membership';
    END IF;
END;
$$ LANGUAGE plpgsql;
"""

GROUP_ONLY_SQL = """
CREATE OR REPLACE FUNCTION organizations_check_active_owner(org_id bigint)
RETURNS void AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM organizations_organization WHERE id = org_id AND type = 'group')
       AND NOT EXISTS (
           SELECT 1
           FROM organizations_membership membership
           JOIN accounts_user account ON account.id = membership.user_id
           WHERE membership.organization_id = org_id
             AND membership.role = 'owner'
             AND account.is_active
       )
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'group organization ' || org_id || ' requires at least one active owner';
    END IF;
END;
$$ LANGUAGE plpgsql;
"""


def repair_personal_owner_memberships(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Membership = apps.get_model("organizations", "Membership")
    duplicate_creators = list(
        Organization.objects.filter(type="personal")
        .values("creator_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .values_list("creator_id", flat=True)[:10]
    )
    if duplicate_creators:
        raise RuntimeError(
            "Cannot enforce personal organization uniqueness; duplicate creators "
            f"exist: {duplicate_creators}"
        )
    for organization in Organization.objects.filter(type="personal").iterator():
        Membership.objects.update_or_create(
            user_id=organization.creator_id,
            organization_id=organization.pk,
            defaults={"role": "owner"},
        )


def install_personal_owner_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(PERSONAL_OWNER_SQL)


def restore_group_owner_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(GROUP_ONLY_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0003_require_active_group_owner"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            repair_personal_owner_memberships, migrations.RunPython.noop
        ),
        migrations.AddConstraint(
            model_name="organization",
            constraint=models.UniqueConstraint(
                condition=models.Q(type="personal"),
                fields=("creator",),
                name="organizations_personal_creator_unique",
            ),
        ),
        migrations.RunPython(install_personal_owner_guard, restore_group_owner_guard),
    ]
