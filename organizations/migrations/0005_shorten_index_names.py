from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0004_organization_organizations_personal_creator_unique"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="membership",
            old_name="organizations_member_org_role_idx",
            new_name="org_membership_org_role_idx",
        ),
        migrations.RenameIndex(
            model_name="exportjob",
            old_name="organizations_export_org_created_idx",
            new_name="org_export_org_created_idx",
        ),
        migrations.RenameIndex(
            model_name="exportjob",
            old_name="organizations_export_status_exp_idx",
            new_name="org_export_status_exp_idx",
        ),
        migrations.RenameIndex(
            model_name="exportjob",
            old_name="organizations_export_status_hb_idx",
            new_name="org_export_status_hb_idx",
        ),
    ]
