from ninja.errors import HttpError
from organizations.permissions import is_member
from organizations.models import Organization


def require_authenticated_user(user):
    if user is None or not getattr(user, "is_authenticated", False):
        raise HttpError(401, "Authentication required")

def check_contact_member(user, organization):
    if not is_member(user, organization):
        raise HttpError(403, "You do not have access to this organization.")


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