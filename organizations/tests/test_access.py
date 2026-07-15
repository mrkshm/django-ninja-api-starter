from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from ninja.errors import HttpError

from contacts.models import Contact
from organizations.access import (
    assert_org_admin,
    assert_org_scoped_object_write,
    assert_org_view,
    assert_org_write,
    get_membership_role,
    is_org_admin,
    is_org_member,
    is_org_owner,
    is_platform_admin,
    visible_org_scoped_queryset,
)
from organizations.models import Membership, Organization
from organizations.scope import resolve_org_scope, resolve_write_org_scope


@pytest.mark.django_db
def test_platform_admin_is_explicit_superuser():
    User = get_user_model()
    regular = User.objects.create_user(
        email="access-regular@example.com", password="pw"
    )
    staff = User.objects.create_user(
        email="access-staff@example.com", password="pw", is_staff=True
    )
    superuser = User.objects.create_superuser(
        email="access-super@example.com", password="pw"
    )

    assert is_platform_admin(regular) is False
    assert is_platform_admin(staff) is False
    assert is_platform_admin(superuser) is True


@pytest.mark.django_db
def test_membership_role_drives_org_permissions():
    User = get_user_model()
    owner = User.objects.create_user(email="access-owner@example.com", password="pw")
    admin = User.objects.create_user(email="access-admin@example.com", password="pw")
    member = User.objects.create_user(email="access-member@example.com", password="pw")
    outsider = User.objects.create_user(
        email="access-outsider@example.com", password="pw"
    )
    org = Organization.objects.create(name="Access", slug="access", type="group")
    Membership.objects.create(user=owner, organization=org, role="owner")
    Membership.objects.create(user=admin, organization=org, role="admin")
    Membership.objects.create(user=member, organization=org, role="member")

    assert get_membership_role(owner, org) == "owner"
    assert is_org_owner(owner, org) is True
    assert is_org_admin(owner, org) is True
    assert is_org_admin(admin, org) is True
    assert is_org_member(member, org) is True
    assert get_membership_role(outsider, org) is None
    assert is_org_member(outsider, org) is False


@pytest.mark.django_db
def test_org_assertions_raise_403_for_insufficient_role():
    User = get_user_model()
    member = User.objects.create_user(
        email="access-member-assert@example.com", password="pw"
    )
    outsider = User.objects.create_user(
        email="access-outsider-assert@example.com", password="pw"
    )
    org = Organization.objects.create(name="Assert", slug="assert", type="group")
    Membership.objects.create(user=member, organization=org, role="member")

    assert assert_org_view(member, org) is None
    assert assert_org_write(member, org) is None

    with pytest.raises(HttpError) as view_exc:
        assert_org_view(outsider, org)
    assert view_exc.value.status_code == 403

    with pytest.raises(HttpError) as admin_exc:
        assert_org_admin(member, org)
    assert admin_exc.value.status_code == 403


@pytest.mark.django_db
def test_org_scoped_object_write_handles_global_objects():
    User = get_user_model()
    regular = User.objects.create_user(
        email="access-global-regular@example.com", password="pw"
    )
    superuser = User.objects.create_superuser(
        email="access-global-super@example.com", password="pw"
    )
    global_obj = SimpleNamespace(organization=None, organization_id=None)

    with pytest.raises(HttpError):
        assert_org_scoped_object_write(regular, global_obj)

    assert assert_org_scoped_object_write(superuser, global_obj) is None


@pytest.mark.django_db
def test_visible_org_scoped_queryset_filters_memberships():
    User = get_user_model()
    user = User.objects.create_user(email="access-visible@example.com", password="pw")
    first = Organization.objects.create(
        name="FirstVisible", slug="first-visible", type="group"
    )
    second = Organization.objects.create(
        name="SecondVisible", slug="second-visible", type="group"
    )
    Membership.objects.create(user=user, organization=first, role="member")
    visible = Contact.objects.create(
        display_name="Visible", slug="visible", organization=first, creator=user
    )
    Contact.objects.create(
        display_name="Hidden", slug="hidden", organization=second, creator=user
    )

    qs = visible_org_scoped_queryset(user, Contact.objects.all())

    assert list(qs) == [visible]


@pytest.mark.django_db
def test_resolve_org_scope_returns_user_org_and_role():
    User = get_user_model()
    user = User.objects.create_user(email="scope-member@example.com", password="pw")
    org = Organization.objects.create(name="Scope", slug="scope", type="group")
    Membership.objects.create(user=user, organization=org, role="admin")
    request = SimpleNamespace(auth=user)

    scope = resolve_org_scope(request, org.slug)

    assert scope.user == user
    assert scope.org == org
    assert scope.role == "admin"
    assert scope.can_admin is True
    assert scope.can_write is True


@pytest.mark.django_db
def test_resolve_org_scope_rejects_non_member():
    User = get_user_model()
    user = User.objects.create_user(email="scope-outsider@example.com", password="pw")
    org = Organization.objects.create(
        name="ScopeDenied", slug="scope-denied", type="group"
    )
    request = SimpleNamespace(auth=user)

    with pytest.raises(HttpError) as exc_info:
        resolve_org_scope(request, org.slug)

    assert exc_info.value.status_code == 403


@pytest.mark.django_db
def test_platform_admin_scope_without_membership():
    User = get_user_model()
    superuser = User.objects.create_superuser(
        email="scope-super@example.com", password="pw"
    )
    org = Organization.objects.create(
        name="ScopeStaff", slug="scope-staff", type="group"
    )
    request = SimpleNamespace(
        auth=superuser,
        method="DELETE",
        path=f"/orgs/{org.slug}/contacts/example/",
    )

    with patch("organizations.scope.audit_logger.info") as audit_info:
        scope = resolve_org_scope(request, org.slug)

    assert scope.user == superuser
    assert scope.org == org
    assert scope.membership is None
    assert scope.role == "platform_admin"
    assert scope.can_admin is True
    assert scope.can_write is True
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
    User = get_user_model()
    superuser = User.objects.create_superuser(
        email="scope-member-super@example.com", password="pw"
    )
    org = Organization.objects.create(
        name="ScopeMemberSuper", slug="scope-member-super", type="group"
    )
    Membership.objects.create(user=superuser, organization=org, role="owner")

    with patch("organizations.scope.audit_logger.info") as audit_info:
        resolve_org_scope(SimpleNamespace(auth=superuser), org.slug)

    audit_info.assert_not_called()


@pytest.mark.django_db
def test_write_scope_reuses_org_scope_policy():
    User = get_user_model()
    member = User.objects.create_user(email="scope-write@example.com", password="pw")
    outsider = User.objects.create_user(
        email="scope-nowrite@example.com", password="pw"
    )
    org = Organization.objects.create(
        name="ScopeWrite", slug="scope-write", type="group"
    )
    Membership.objects.create(user=member, organization=org, role="member")

    assert resolve_write_org_scope(SimpleNamespace(auth=member), org.slug).org == org

    with pytest.raises(HttpError) as exc_info:
        resolve_write_org_scope(SimpleNamespace(auth=outsider), org.slug)

    assert exc_info.value.status_code == 403
