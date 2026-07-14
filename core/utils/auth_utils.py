from ninja.errors import HttpError
from organizations.models import Organization


def require_authenticated_user(user):
    if user is None or not getattr(user, "is_authenticated", False):
        raise HttpError(401, "Authentication required")


def get_request_user(request):
    user = getattr(request, "auth", None)
    require_authenticated_user(user)
    return user


def get_org_or_404(slug):
    try:
        return Organization.objects.get(slug=slug)
    except Organization.DoesNotExist:
        raise HttpError(404, "Organization not found")


def check_object_belongs_to_org(obj, org):
    if isinstance(obj, Organization):
        if obj.id != org.id:
            raise HttpError(403, "Object does not belong to this organization")
    elif getattr(obj, "organization_id", None) != org.id:
        raise HttpError(403, "Object does not belong to this organization")
