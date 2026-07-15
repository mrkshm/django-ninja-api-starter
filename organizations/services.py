import uuid

from django.db import IntegrityError, transaction

from core.utils.identifiers import make_it_unique
from organizations.models import Membership, Organization


class ActiveOwnerRequiredError(ValueError):
    """Raised when a membership change would leave a group without an active owner."""


def _is_personal_creator_membership(organization, membership) -> bool:
    return (
        organization.type == "personal"
        and organization.creator_id == membership.user_id
    )


def _has_other_active_owner(*, organization, membership) -> bool:
    return (
        Membership.objects.filter(
            organization=organization,
            role="owner",
            user__is_active=True,
        )
        .exclude(pk=membership.pk)
        .exists()
    )


@transaction.atomic
def change_membership_role(membership: Membership, *, role: str) -> Membership:
    """Change a role while preserving at least one active owner per group."""
    valid_roles = {value for value, _label in Membership.ROLE_CHOICES}
    if role not in valid_roles:
        raise ValueError(f"Unsupported membership role: {role}")

    organization = Organization.objects.select_for_update().get(
        pk=membership.organization_id
    )
    locked = Membership.objects.select_for_update().get(pk=membership.pk)
    if _is_personal_creator_membership(organization, locked) and role != "owner":
        raise ActiveOwnerRequiredError(
            "A personal organization's creator must remain its owner."
        )
    if (
        organization.type == "group"
        and locked.role == "owner"
        and role != "owner"
        and not _has_other_active_owner(
            organization=organization,
            membership=locked,
        )
    ):
        raise ActiveOwnerRequiredError(
            "Promote another active member to owner before changing this owner."
        )

    locked.role = role
    locked.save(update_fields=["role", "updated_at"])
    return locked


@transaction.atomic
def remove_membership(membership: Membership) -> None:
    """Remove a membership without orphaning a group organization."""
    organization = Organization.objects.select_for_update().get(
        pk=membership.organization_id
    )
    locked = Membership.objects.select_for_update().get(pk=membership.pk)
    if _is_personal_creator_membership(organization, locked):
        raise ActiveOwnerRequiredError(
            "A personal organization's creator membership cannot be removed."
        )
    if (
        organization.type == "group"
        and locked.role == "owner"
        and not _has_other_active_owner(
            organization=organization,
            membership=locked,
        )
    ):
        raise ActiveOwnerRequiredError(
            "Promote another active member to owner before removing this owner."
        )
    locked.delete()


def assert_user_can_be_deactivated(user) -> None:
    """Reject deactivation/deletion when the user is a group's last active owner."""
    owned_groups = (
        Organization.objects.select_for_update()
        .filter(type="group", memberships__user=user, memberships__role="owner")
        .order_by("pk")
    )
    for organization in owned_groups:
        has_successor = (
            Membership.objects.filter(
                organization=organization,
                role="owner",
                user__is_active=True,
            )
            .exclude(user=user)
            .exists()
        )
        if not has_successor:
            raise ActiveOwnerRequiredError(
                f"Promote another active owner for {organization.name} first."
            )


@transaction.atomic
def create_group_organization(*, name: str, slug: str, owner) -> Organization:
    """Create a group and its first active owner in one transaction."""
    if not owner.is_active:
        raise ActiveOwnerRequiredError("The initial group owner must be active.")
    organization = Organization.objects.create(
        name=name,
        slug=slug,
        type="group",
        creator=owner,
    )
    Membership.objects.create(
        user=owner,
        organization=organization,
        role="owner",
    )
    return organization


@transaction.atomic
def create_personal_organization(user) -> Organization:
    existing = Organization.objects.filter(type="personal", creator=user).first()
    if existing is not None:
        Membership.objects.update_or_create(
            user=user,
            organization=existing,
            defaults={"role": "owner"},
        )
        return existing

    base_slug = user.slug or f"user-{user.pk}"
    for attempt in range(5):
        slug = (
            make_it_unique(base_slug, Organization, "slug")
            if attempt == 0
            else f"{base_slug[:41]}-{uuid.uuid4().hex[:8]}"
        )
        try:
            with transaction.atomic():
                organization = Organization.objects.create(
                    name=user.username or f"user-{user.pk}",
                    slug=slug,
                    type="personal",
                    creator=user,
                )
                Membership.objects.create(
                    user=user, organization=organization, role="owner"
                )
                return organization
        except IntegrityError:
            existing = Organization.objects.filter(
                type="personal", creator=user
            ).first()
            if existing is not None:
                Membership.objects.update_or_create(
                    user=user,
                    organization=existing,
                    defaults={"role": "owner"},
                )
                return existing
            if attempt == 4:
                raise
    raise RuntimeError("Personal organization retry loop exhausted unexpectedly.")
