from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ninja.errors import HttpError

from core.utils.auth_utils import get_request_user
from organizations.models import Membership, Organization

if TYPE_CHECKING:
    from accounts.models import User

audit_logger = logging.getLogger("audit")


def is_platform_admin(user) -> bool:
    """Staff status alone never grants cross-tenant application access."""
    return bool(getattr(user, "is_superuser", False))


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
    membership = (
        Membership.objects.select_related("organization")
        .filter(
            user=user,
            organization__slug=org_slug,
        )
        .first()
    )
    if membership is not None:
        return OrgScope(user=user, org=membership.organization, membership=membership)

    if not is_platform_admin(user):
        raise HttpError(404, "Organization not found")

    try:
        org = Organization.objects.get(slug=org_slug)
    except Organization.DoesNotExist as exc:
        raise HttpError(404, "Organization not found") from exc
    else:
        audit_logger.info(
            "audit:platform_admin_tenant_access",
            extra={
                "event": "platform_admin_tenant_access",
                "org": org.pk,
                "user": user.pk,
                "method": getattr(request, "method", "UNKNOWN"),
                "path": getattr(request, "path", ""),
                "access": (
                    "read"
                    if getattr(request, "method", "GET") in {"GET", "HEAD", "OPTIONS"}
                    else "write"
                ),
            },
        )
    return OrgScope(user=user, org=org)


def resolve_write_org_scope(request, org_slug: str) -> OrgScope:
    return resolve_org_scope(request, org_slug).require_write()


def resolve_admin_org_scope(request, org_slug: str) -> OrgScope:
    return resolve_org_scope(request, org_slug).require_admin()
