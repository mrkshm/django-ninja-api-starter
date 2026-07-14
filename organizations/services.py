from django.db import transaction

from core.utils import make_it_unique
from organizations.models import Membership, Organization


@transaction.atomic
def create_personal_organization(user) -> Organization:
    existing = Organization.objects.filter(
        type="personal", creator=user, memberships__user=user
    ).first()
    if existing is not None:
        return existing

    base_slug = user.slug or f"user-{user.pk}"
    organization = Organization.objects.create(
        name=user.username or f"user-{user.pk}",
        slug=make_it_unique(base_slug, Organization, "slug"),
        type="personal",
        creator=user,
    )
    Membership.objects.create(user=user, organization=organization, role="owner")
    return organization
