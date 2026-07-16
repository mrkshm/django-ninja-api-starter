import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from contacts.models import Contact
from organizations.models import Membership, Organization


class Command(BaseCommand):
    help = "Create idempotent development-only demo data."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="demo@example.com")
        parser.add_argument("--password")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo is disabled unless DEBUG=True.")

        user_model = get_user_model()
        email = options["email"].strip().lower()
        password = options["password"] or secrets.token_urlsafe(18)
        user = user_model.objects.filter(email=email).first()
        created = user is None
        if user is None:
            user = user_model.objects.create_user(
                email=email,
                password=password,
                email_verified=True,
                first_name="Demo",
            )

        organization, _ = Organization.objects.get_or_create(
            slug="demo-team",
            defaults={"name": "Demo Team", "type": "group", "creator": user},
        )
        Membership.objects.get_or_create(
            user=user,
            organization=organization,
            defaults={"role": "owner"},
        )
        Contact.objects.get_or_create(
            organization=organization,
            slug="sample-contact",
            defaults={
                "display_name": "Sample Contact",
                "first_name": "Sample",
                "last_name": "Contact",
                "creator": user,
            },
        )

        self.stdout.write(self.style.SUCCESS(f"Demo data ready for {email}."))
        if created:
            self.stdout.write(f"Generated password: {password}")
        else:
            self.stdout.write("Existing user password was left unchanged.")
