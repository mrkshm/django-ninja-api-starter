from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from ninja.errors import HttpError

from organizations.models import Membership, Organization
from organizations.scope import (
    is_platform_admin,
    resolve_org_scope,
    resolve_write_org_scope,
)
from organizations.tests.utils import create_test_group

User = get_user_model()


def request_for(user, *, method="GET", path="/"):
    return SimpleNamespace(auth=user, method=method, path=path)


@pytest.mark.django_db
def test_only_superusers_are_platform_admins():
    regular = User.objects.create_user(email="regular@example.com", password="pw")
    staff = User.objects.create_user(
        email="staff@example.com", password="pw", is_staff=True
    )
    superuser = User.objects.create_superuser(email="super@example.com", password="pw")

    assert is_platform_admin(regular) is False
    assert is_platform_admin(staff) is False
    assert is_platform_admin(superuser) is True


@pytest.mark.django_db
def test_member_scope_resolves_role_in_exactly_one_query(django_assert_num_queries):
    user = User.objects.create_user(email="scope-member@example.com", password="pw")
    org = create_test_group(name="Scope", slug="scope")
    Membership.objects.create(user=user, organization=org, role="admin")

    with django_assert_num_queries(1):
        scope = resolve_org_scope(request_for(user), org.slug)

    assert scope.user == user
    assert scope.org == org
    assert scope.role == "admin"
    assert scope.can_admin is True
    assert scope.can_write is True


@pytest.mark.django_db
def test_unknown_and_inaccessible_slugs_are_identical_and_one_query(
    django_assert_num_queries,
):
    user = User.objects.create_user(email="scope-outsider@example.com", password="pw")
    create_test_group(name="Hidden", slug="hidden")

    errors = []
    for slug in ("missing", "hidden"):
        with django_assert_num_queries(1):
            with pytest.raises(HttpError) as raised:
                resolve_org_scope(request_for(user), slug)
        errors.append(raised.value)

    assert [(error.status_code, error.message) for error in errors] == [
        (404, "Organization not found"),
        (404, "Organization not found"),
    ]


@pytest.mark.django_db
def test_platform_admin_scope_without_membership_is_audited():
    superuser = User.objects.create_superuser(
        email="scope-super@example.com", password="pw"
    )
    org = create_test_group(name="Staff", slug="staff")
    request = request_for(
        superuser,
        method="DELETE",
        path=f"/orgs/{org.slug}/contacts/example/",
    )

    with patch("organizations.scope.audit_logger.info") as audit_info:
        scope = resolve_org_scope(request, org.slug)

    assert scope.org == org
    assert scope.role == "platform_admin"
    assert scope.can_admin is True
    audit_info.assert_called_once_with(
        "audit:platform_admin_tenant_access",
        extra={
            "event": "platform_admin_tenant_access",
            "org": org.pk,
            "user": superuser.pk,
            "method": "DELETE",
            "path": f"/orgs/{org.slug}/contacts/example/",
            "access": "write",
        },
    )


@pytest.mark.django_db
def test_platform_admin_membership_does_not_log_cross_tenant_access():
    superuser = User.objects.create_superuser(
        email="scope-member-super@example.com", password="pw"
    )
    org = Organization.objects.create(
        name="MemberSuper", slug="member-super", type="group"
    )
    Membership.objects.create(user=superuser, organization=org, role="owner")

    with patch("organizations.scope.audit_logger.info") as audit_info:
        resolve_org_scope(request_for(superuser), org.slug)

    audit_info.assert_not_called()


@pytest.mark.django_db
def test_write_scope_uses_the_canonical_resolver():
    member = User.objects.create_user(email="scope-write@example.com", password="pw")
    outsider = User.objects.create_user(email="scope-no@example.com", password="pw")
    org = create_test_group(name="Write", slug="write")
    Membership.objects.create(user=member, organization=org, role="member")

    assert resolve_write_org_scope(request_for(member), org.slug).org == org
    with pytest.raises(HttpError) as raised:
        resolve_write_org_scope(request_for(outsider), org.slug)
    assert raised.value.status_code == 404
