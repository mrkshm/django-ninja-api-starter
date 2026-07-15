import uuid

from django.conf import settings
from django.db import models

# Create your models here.


class Organization(models.Model):
    ORG_TYPE_CHOICES = [
        ("personal", "Personal"),
        ("group", "Group"),
    ]
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    type = models.CharField(max_length=20, choices=ORG_TYPE_CHOICES, default="group")
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_organizations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(type__in=("personal", "group")),
                name="organizations_org_valid_type",
            ),
            models.CheckConstraint(
                condition=models.Q(type="group") | models.Q(creator__isnull=False),
                name="organizations_personal_org_has_creator",
            ),
            models.UniqueConstraint(
                fields=("creator",),
                condition=models.Q(type="personal"),
                name="organizations_personal_creator_unique",
            ),
        ]

    def __str__(self):
        return self.name


class Membership(models.Model):
    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("admin", "Admin"),
        ("member", "Member"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "organization"),
                name="organizations_membership_user_org_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=("owner", "admin", "member")),
                name="organizations_membership_valid_role",
            ),
        ]
        indexes = [
            models.Index(
                fields=("organization", "role"),
                name="org_membership_org_role_idx",
            )
        ]

    def __str__(self):
        return (
            f"Membership(user={self.user_id}, organization={self.organization_id}, "
            f"role={self.role})"
        )


class ExportJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="export_jobs"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="requested_export_jobs",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    object_key = models.CharField(max_length=512, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    queued_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(
                fields=("organization", "created_at"),
                name="org_export_org_created_idx",
            ),
            models.Index(
                fields=("status", "expires_at"),
                name="org_export_status_exp_idx",
            ),
            models.Index(
                fields=("status", "heartbeat_at"),
                name="org_export_status_hb_idx",
            ),
        ]
