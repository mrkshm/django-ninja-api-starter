from django.core.cache import cache
from django.db.models import Q
from ninja.errors import HttpError

from organizations.models import Membership, Organization

MEMBERSHIP_ROLE_CACHE_TIMEOUT = 3600
NO_MEMBERSHIP_ROLE = "__none__"


def membership_role_cache_key(user_id, organization_id):
    return f"membership_role_{user_id}_{organization_id}"


def is_platform_admin(user) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def get_membership_role(user, organization) -> str | None:
    if user is None or organization is None:
        return None

    user_id = getattr(user, "id", None)
    organization_id = getattr(organization, "id", None)
    if user_id is None or organization_id is None:
        return None

    cache_key = membership_role_cache_key(user_id, organization_id)
    cached_role = cache.get(cache_key)
    if cached_role is not None:
        return None if cached_role == NO_MEMBERSHIP_ROLE else cached_role

    role = (
        Membership.objects.filter(user_id=user_id, organization_id=organization_id)
        .values_list("role", flat=True)
        .first()
    )
    cache.set(cache_key, role or NO_MEMBERSHIP_ROLE, timeout=MEMBERSHIP_ROLE_CACHE_TIMEOUT)
    return role


def member_org_ids(user):
    return list(user.memberships.values_list("organization_id", flat=True))


def is_org_owner(user, organization) -> bool:
    return get_membership_role(user, organization) == "owner"


def is_org_admin(user, organization) -> bool:
    return get_membership_role(user, organization) in {"admin", "owner"}


def is_org_member(user, organization) -> bool:
    return get_membership_role(user, organization) is not None


def can_view_org(user, organization) -> bool:
    return is_platform_admin(user) or is_org_member(user, organization)


def can_write_org(user, organization) -> bool:
    return is_platform_admin(user) or is_org_member(user, organization)


def can_admin_org(user, organization) -> bool:
    return is_platform_admin(user) or is_org_admin(user, organization)


def assert_org_view(user, organization) -> None:
    if not can_view_org(user, organization):
        raise HttpError(403, "You do not have access to this organization.")


def assert_org_write(user, organization) -> None:
    if not can_write_org(user, organization):
        raise HttpError(403, "You do not have access to this organization.")


def assert_org_admin(user, organization) -> None:
    if not can_admin_org(user, organization):
        raise HttpError(403, "Only org admins/owners can perform this action.")


def assert_org_scoped_object_write(
    user,
    obj,
    *,
    allow_global: bool = False,
    global_message: str = "Only platform admins can mutate global data.",
) -> None:
    organization = getattr(obj, "organization", None)
    organization_id = getattr(obj, "organization_id", None)

    if organization_id is None:
        if allow_global or is_platform_admin(user):
            return
        raise HttpError(403, global_message)

    if organization is None:
        try:
            organization = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist as exc:
            raise HttpError(403, "You do not have access to this organization.") from exc

    assert_org_write(user, organization)


def visible_org_scoped_queryset(
    user,
    qs,
    *,
    include_global: bool = False,
    organization_field: str = "organization",
):
    if is_platform_admin(user):
        return qs

    organization_id_field = f"{organization_field}_id"
    org_filter = Q(**{f"{organization_id_field}__in": member_org_ids(user)})
    if include_global:
        org_filter |= Q(**{f"{organization_field}__isnull": True})
    return qs.filter(org_filter)
