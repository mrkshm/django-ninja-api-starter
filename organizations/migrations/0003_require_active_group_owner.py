from django.db import migrations

INSTALL_SQL = """
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

CREATE OR REPLACE FUNCTION organizations_membership_owner_guard()
RETURNS trigger AS $$
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        PERFORM organizations_check_active_owner(OLD.organization_id);
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        PERFORM organizations_check_active_owner(NEW.organization_id);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION organizations_org_owner_guard()
RETURNS trigger AS $$
BEGIN
    PERFORM organizations_check_active_owner(NEW.id);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION organizations_user_owner_guard()
RETURNS trigger AS $$
DECLARE
    org_id bigint;
BEGIN
    IF OLD.is_active AND NOT NEW.is_active THEN
        FOR org_id IN
            SELECT organization_id
            FROM organizations_membership
            WHERE user_id = NEW.id AND role = 'owner'
        LOOP
            PERFORM organizations_check_active_owner(org_id);
        END LOOP;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER organizations_membership_active_owner_guard
AFTER INSERT OR UPDATE OR DELETE ON organizations_membership
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION organizations_membership_owner_guard();

CREATE CONSTRAINT TRIGGER organizations_org_active_owner_guard
AFTER INSERT OR UPDATE ON organizations_organization
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION organizations_org_owner_guard();

CREATE CONSTRAINT TRIGGER organizations_user_active_owner_guard
AFTER UPDATE OF is_active ON accounts_user
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION organizations_user_owner_guard();
"""

UNINSTALL_SQL = """
DROP TRIGGER IF EXISTS organizations_user_active_owner_guard ON accounts_user;
DROP TRIGGER IF EXISTS organizations_org_active_owner_guard ON organizations_organization;
DROP TRIGGER IF EXISTS organizations_membership_active_owner_guard ON organizations_membership;
DROP FUNCTION IF EXISTS organizations_user_owner_guard();
DROP FUNCTION IF EXISTS organizations_org_owner_guard();
DROP FUNCTION IF EXISTS organizations_membership_owner_guard();
DROP FUNCTION IF EXISTS organizations_check_active_owner(bigint);
"""


def require_existing_active_owners(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Membership = apps.get_model("organizations", "Membership")
    orphan_ids = []
    for organization_id in Organization.objects.filter(type="group").values_list(
        "id", flat=True
    ):
        if not Membership.objects.filter(
            organization_id=organization_id,
            role="owner",
            user__is_active=True,
        ).exists():
            orphan_ids.append(organization_id)
            if len(orphan_ids) == 10:
                break
    if orphan_ids:
        raise RuntimeError(
            "Cannot install the active-owner invariant; group organizations without "
            f"an active owner exist: {orphan_ids}"
        )
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(INSTALL_SQL)


def remove_owner_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(UNINSTALL_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_harden_registration_and_email_changes"),
        (
            "organizations",
            "0002_exportjob_attempt_count_exportjob_heartbeat_at_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(require_existing_active_owners, remove_owner_guards),
    ]
