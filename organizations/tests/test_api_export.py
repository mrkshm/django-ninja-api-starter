import pytest
from django.contrib.auth import get_user_model
from organizations.models import Organization, Membership
from organizations.api_export import trigger_export
from ninja.errors import HttpError
from unittest import mock
from django.test import RequestFactory

User = get_user_model()

@pytest.mark.django_db
def test_trigger_export_auth_required():
    rf = RequestFactory()
    request = rf.post("/orgs/test-org/export/")
    request.user = mock.Mock(is_authenticated=False)
    with pytest.raises(HttpError) as exc:
        trigger_export(request, org_slug="test-org")
    assert exc.value.status_code == 401
    assert "Authentication required" in str(exc.value)

@pytest.mark.django_db
def test_trigger_export_forbidden():
    rf = RequestFactory()
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group")
    user = User.objects.create(email="user@example.com", username="user")
    request = rf.post("/orgs/test-org/export/")
    request.user = user
    # User is not a member
    with pytest.raises(HttpError) as exc:
        trigger_export(request, org_slug="test-org")
    assert exc.value.status_code == 403
    # Now add as member but not admin/owner
    Membership.objects.create(user=user, organization=org, role="member")
    with pytest.raises(HttpError) as exc:
        trigger_export(request, org_slug="test-org")
    assert exc.value.status_code == 403
    assert "Only org admins/owners" in str(exc.value)

@pytest.mark.django_db
def test_trigger_export_success(monkeypatch):
    rf = RequestFactory()
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group")
    user = User.objects.create(email="admin@example.com", username="admin")
    Membership.objects.create(user=user, organization=org, role="admin")
    request = rf.post("/orgs/test-org/export/")
    request.user = user
    called = {}
    def fake_delay(org_id, email):
        called['org_id'] = org_id
        called['email'] = email
    monkeypatch.setattr("organizations.api_export.export_org_data_task.delay", fake_delay)
    resp = trigger_export(request, org_slug="test-org")
    assert resp["detail"].startswith("Export started")
    assert called['org_id'] == org.id
    assert called['email'] == user.email