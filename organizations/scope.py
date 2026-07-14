from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from core.utils.auth_utils import get_request_user
from organizations.access import is_platform_admin
from organizations.models import Membership, Organization

if TYPE_CHECKING:
    from accounts.models import User


@dataclass(frozen=True)
class OrgScope:
    user: User
    org: Organization
    membership: Membership | None = None

    @property
    def role(self) -> str | None:
        if is_platform_admin(self.user):
            return "platform_admin"
        return self.membership.role if self.membership else None

    @property
    def can_admin(self) -> bool:
        return is_platform_admin(self.user) or self.role in {"admin", "owner"}

    @property
    def can_write(self) -> bool:
        return is_platform_admin(self.user) or self.role in {"member", "admin", "owner"}

    def require_admin(self) -> "OrgScope":
        if not self.can_admin:
            raise HttpError(403, "Only org admins/owners can perform this action.")
        return self

    def require_write(self) -> "OrgScope":
        if not self.can_write:
            raise HttpError(403, "You do not have access to this organization.")
        return self


def resolve_org_scope(request, org_slug: str) -> OrgScope:
    user = get_request_user(request)
    org = get_object_or_404(Organization, slug=org_slug)
    membership = (
        Membership.objects.select_related("organization")
        .filter(user=user, organization=org)
        .first()
    )
    if membership is None and not is_platform_admin(user):
        raise HttpError(403, "You do not have access to this organization.")
    return OrgScope(user=user, org=org, membership=membership)


def resolve_write_org_scope(request, org_slug: str) -> OrgScope:
    return resolve_org_scope(request, org_slug).require_write()


def resolve_admin_org_scope(request, org_slug: str) -> OrgScope:
    return resolve_org_scope(request, org_slug).require_admin()
