import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User
from contacts.models import Contact
from organizations.models import Membership, Organization


@pytest.mark.django_db
def test_seed_demo_is_idempotent(settings):
    settings.DEBUG = True
    call_command("seed_demo", email="demo@example.com", password="safe-demo-password")
    call_command("seed_demo", email="demo@example.com", password="ignored-password")

    assert User.objects.filter(email="demo@example.com").count() == 1
    organization = Organization.objects.get(slug="demo-team")
    assert (
        Membership.objects.filter(organization=organization, role="owner").count() == 1
    )
    assert Contact.objects.filter(organization=organization).count() == 1


@pytest.mark.django_db
def test_seed_demo_refuses_non_debug_settings(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="disabled"):
        call_command("seed_demo")
