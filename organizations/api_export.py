from ninja import Router
from ninja_jwt.authentication import JWTAuth
from ninja.errors import HttpError
from django.contrib.auth import get_user_model
from organizations.models import Organization, Membership
from organizations.export_tasks import export_org_data_task
from ninja.security import django_auth
from ninja.schema import Schema
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, route
from ninja_jwt.authentication import JWTAuth

class ExportRequestSchema(Schema):
    # Can be extended later
    pass

export_router = Router(tags=["organization", "export"])

@export_router.post("/orgs/{org_slug}/export/")
def trigger_export(request, org_slug: str):
    user = request.user
    if not user.is_authenticated:
        raise HttpError(401, "Authentication required")
    org = get_object_or_404(Organization, slug=org_slug)
    # Only allow admins/owners
    membership = Membership.objects.filter(user=user, organization=org).first()
    if not membership or membership.role not in ("admin", "owner"):
        raise HttpError(403, "Only org admins/owners can export data")
    # Trigger Celery export task
    export_org_data_task.delay(org.id, user.email)
    return {"detail": "Export started. You will receive an email when it is ready."}
