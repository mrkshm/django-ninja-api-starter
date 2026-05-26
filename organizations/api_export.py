from ninja import Router
from organizations.access import assert_org_admin
from organizations.models import Organization
from organizations.export_tasks import export_org_data_task
from ninja.schema import Schema
from django.shortcuts import get_object_or_404
from core.utils.auth_utils import require_authenticated_user

class ExportRequestSchema(Schema):
    # Can be extended later
    pass

export_router = Router(tags=["organization", "export"])

@export_router.post("/orgs/{org_slug}/export/")
def trigger_export(request, org_slug: str):
    user = request.user
    require_authenticated_user(user)
    org = get_object_or_404(Organization, slug=org_slug)
    assert_org_admin(user, org)
    # Trigger Celery export task
    export_org_data_task.delay(org.id, user.email)
    return {"detail": "Export started. You will receive an email when it is ready."}
