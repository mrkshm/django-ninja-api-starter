import pytest
from ninja.errors import HttpError
from organizations.models import Organization
from core.utils.auth_utils import (
    check_object_belongs_to_org,
    get_org_or_404,
    get_request_user,
    require_authenticated_user,
)
from types import SimpleNamespace


class DummyUser:
    def __init__(self, is_authenticated):
        self.is_authenticated = is_authenticated


@pytest.mark.django_db
def test_get_org_or_404_found():
    org = Organization.objects.create(name="TestOrg", slug="testorg")
    found = get_org_or_404("testorg")
    assert found == org


@pytest.mark.django_db
def test_get_org_or_404_not_found():
    with pytest.raises(HttpError) as exc:
        get_org_or_404("nope")
    assert exc.value.status_code == 404
    assert "Organization not found" in str(exc.value)


@pytest.mark.django_db
def test_check_object_belongs_to_org_org_self():
    org = Organization.objects.create(name="TestOrg", slug="testorg")
    # Should not raise
    check_object_belongs_to_org(org, org)


@pytest.mark.django_db
def test_check_object_belongs_to_org_org_wrong():
    org1 = Organization.objects.create(name="Org1", slug="org1")
    org2 = Organization.objects.create(name="Org2", slug="org2")
    with pytest.raises(HttpError) as exc:
        check_object_belongs_to_org(org2, org1)
    assert exc.value.status_code == 403
    assert "Object does not belong to this organization" in str(exc.value)


class DummyObj:
    def __init__(self, organization_id):
        self.organization_id = organization_id


@pytest.mark.django_db
def test_check_object_belongs_to_org_model_right():
    org = Organization.objects.create(name="Org", slug="org")
    obj = DummyObj(organization_id=org.id)
    check_object_belongs_to_org(obj, org)  # Should not raise


@pytest.mark.django_db
def test_check_object_belongs_to_org_model_wrong():
    org1 = Organization.objects.create(name="Org1", slug="org1")
    org2 = Organization.objects.create(name="Org2", slug="org2")
    obj = DummyObj(organization_id=org2.id)
    with pytest.raises(HttpError) as exc:
        check_object_belongs_to_org(obj, org1)
    assert exc.value.status_code == 403
    assert "Object does not belong to this organization" in str(exc.value)


def test_require_authenticated_user_none():
    with pytest.raises(HttpError) as exc:
        require_authenticated_user(None)
    assert exc.value.status_code == 401
    assert "Authentication required" in str(exc.value)


def test_require_authenticated_user_false():
    user = DummyUser(is_authenticated=False)
    with pytest.raises(HttpError) as exc:
        require_authenticated_user(user)
    assert exc.value.status_code == 401
    assert "Authentication required" in str(exc.value)


def test_require_authenticated_user_true():
    user = DummyUser(is_authenticated=True)
    require_authenticated_user(user)  # Should not raise


def test_get_request_user_returns_auth_user():
    user = DummyUser(is_authenticated=True)

    assert get_request_user(SimpleNamespace(auth=user, user=object())) is user


def test_get_request_user_does_not_fall_back_to_request_user():
    session_user = DummyUser(is_authenticated=True)

    with pytest.raises(HttpError) as exc:
        get_request_user(SimpleNamespace(auth=None, user=session_user))

    assert exc.value.status_code == 401
