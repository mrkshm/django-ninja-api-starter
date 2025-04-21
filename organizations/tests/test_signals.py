import pytest
from django.contrib.auth import get_user_model
from organizations.models import Organization, Membership

User = get_user_model()

@pytest.mark.django_db
def test_personal_org_created_on_user_creation():
    user = User.objects.create_user(email="test1@example.com", password="pw")
    orgs = Organization.objects.filter(type="personal", memberships__user=user)
    assert orgs.count() == 1
    org = orgs.first()
    assert org.name == user.username or org.name == f"user-{user.pk}"
    assert org.slug == user.slug or org.slug.startswith(user.slug) or org.slug == f"user-{user.pk}" or org.slug.startswith(f"user-{user.pk}")
    assert org.creator == user

@pytest.mark.django_db
def test_membership_created_for_personal_org():
    user = User.objects.create_user(email="test2@example.com", password="pw")
    org = Organization.objects.get(type="personal", memberships__user=user)
    membership = Membership.objects.get(user=user, organization=org)
    assert membership.role == "owner"

@pytest.mark.django_db
def test_personal_org_deleted_on_user_deletion():
    user = User.objects.create_user(email="test3@example.com", password="pw")
    org_id = Organization.objects.get(type="personal", memberships__user=user).id
    user.delete()
    assert not Organization.objects.filter(id=org_id).exists()

@pytest.mark.django_db
def test_no_duplicate_personal_orgs():
    user = User.objects.create_user(email="test4@example.com", password="pw")
    # Simulate a second save (should not create a new org)
    user.save()
    orgs = Organization.objects.filter(type="personal", memberships__user=user)
    assert orgs.count() == 1
