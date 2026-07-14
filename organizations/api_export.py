from ninja import Router
from organizations.export_tasks import export_org_data_task
from organizations.scope import resolve_admin_org_scope
from ninja.schema import Schema
from core.authentication import JWTAuth
from pydantic import ConfigDict

class ExportRequestSchema(Schema):
    # Can be extended later
    model_config = ConfigDict(extra="forbid")

export_router = Router(tags=["organization", "export"])

@export_router.post("/orgs/{org_slug}/export/", auth=JWTAuth())
def trigger_export(request, org_slug: str):
    scope = resolve_admin_org_scope(request, org_slug)
    # Trigger Celery export task
    export_org_data_task.delay(scope.org.id, scope.user.email)
    return {"detail": "Export started. You will receive an email when it is ready."}
