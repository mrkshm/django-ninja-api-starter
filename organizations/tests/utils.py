import uuid

from django.contrib.auth import get_user_model

from organizations.models import Membership, Organization


def create_test_group(*, name: str, slug: str, owner=None, **kwargs) -> Organization:
    """Create a group fixture that satisfies the production owner invariant."""
    if owner is None:
        owner = get_user_model().objects.create_user(
            email=f"fixture-owner-{uuid.uuid4().hex}@example.test",
            password=None,
            email_verified=True,
        )
    organization = Organization.objects.create(
        name=name,
        slug=slug,
        type="group",
        **kwargs,
    )
    Membership.objects.create(
        user=owner,
        organization=organization,
        role="owner",
    )
    return organization
