from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from contacts.models import Contact
from core.utils.storage import public_storage_exists
from images.models import Image
from images.services import image_storage_keys


def walk_storage(prefix: str):
    try:
        directories, files = default_storage.listdir(prefix)
    except FileNotFoundError, NotImplementedError:
        return
    for filename in files:
        yield f"{prefix.rstrip('/')}/{filename}"
    for directory in directories:
        yield from walk_storage(f"{prefix.rstrip('/')}/{directory}")


class Command(BaseCommand):
    help = "Audit private image records and objects; deletion is opt-in and age-gated."

    def add_arguments(self, parser):
        parser.add_argument("--fail-on-missing", action="store_true")
        parser.add_argument("--delete-unreferenced", action="store_true")
        parser.add_argument("--minimum-age-hours", type=int, default=24)

    def handle(self, *args, **options):
        referenced: set[str] = set()
        missing: list[str] = []
        for image in Image.objects.iterator():
            keys = image_storage_keys(image)
            referenced.update(keys)
            for key in keys:
                if not default_storage.exists(key):
                    missing.append(key)

        avatar_paths = list(
            get_user_model()
            .objects.exclude(avatar_path__isnull=True)
            .exclude(avatar_path="")
            .values_list("avatar_path", flat=True)
        ) + list(
            Contact.objects.exclude(avatar_path__isnull=True)
            .exclude(avatar_path="")
            .values_list("avatar_path", flat=True)
        )
        for avatar_path in avatar_paths:
            if not avatar_path:
                continue
            base = avatar_path.removesuffix(".webp")
            for key in (avatar_path, f"{base}_lg.webp"):
                if not public_storage_exists(key):
                    missing.append(key)

        stored = set(walk_storage("private/images") or ())
        unreferenced = sorted(stored - referenced)
        deleted = 0
        if options["delete_unreferenced"]:
            cutoff = timezone.now() - timedelta(
                hours=max(1, options["minimum_age_hours"])
            )
            for key in unreferenced:
                try:
                    if default_storage.get_modified_time(key) > cutoff:
                        continue
                except NotImplementedError, OSError:
                    self.stderr.write(f"Skipping {key}: storage age is unavailable")
                    continue
                default_storage.delete(key)
                deleted += 1

        self.stdout.write(
            f"media audit: missing={len(missing)} unreferenced={len(unreferenced)} deleted={deleted}"
        )
        for key in missing:
            self.stderr.write(f"missing: {key}")
        for key in unreferenced:
            self.stdout.write(f"unreferenced: {key}")

        if missing and options["fail_on_missing"]:
            raise CommandError("Referenced media objects are missing.")
