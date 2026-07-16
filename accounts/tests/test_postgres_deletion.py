import pytest
from django.db import IntegrityError, connection, transaction

from accounts.models import User
from organizations.models import Membership, Organization
from organizations.services import create_group_organization

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="deferred ownership triggers require PostgreSQL",
    ),
]


@pytest.mark.parametrize("use_queryset", [False, True])
def test_raw_user_deletion_removes_personal_organization(use_queryset):
    user = User.objects.create_user(
        email=f"raw-delete-{use_queryset}@example.com", password="pw"
    )
    user_id = user.pk
    personal_id = Organization.objects.get(type="personal", creator=user).pk

    if use_queryset:
        User.objects.filter(pk=user_id).delete()
    else:
        user.delete()

    assert not User.objects.filter(pk=user_id).exists()
    assert not Organization.objects.filter(pk=personal_id).exists()


def test_database_trigger_rejects_raw_last_group_owner_deletion():
    user = User.objects.create_user(email="raw-last-owner@example.com", password="pw")
    organization = create_group_organization(
        name="Raw guarded",
        slug="raw-guarded",
        owner=user,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.filter(pk=user.pk).delete()

    assert User.objects.filter(pk=user.pk).exists()
    assert Membership.objects.filter(
        user=user, organization=organization, role="owner"
    ).exists()
