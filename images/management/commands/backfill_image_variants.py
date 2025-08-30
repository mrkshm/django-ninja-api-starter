from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.db.models import Q
from images.models import Image
from core.utils.image import resize_images
from core.utils.storage import upload_to_storage
import os
import sys

class Command(BaseCommand):
    help = "Generate and upload missing WebP variants (thumb, sm, md, lg) for images."

    def add_arguments(self, parser):
        parser.add_argument("--org", dest="org_id", type=int, help="Only process images for a specific organization id")
        parser.add_argument("--ids", dest="ids", nargs="*", type=int, help="Explicit image IDs to process")
        parser.add_argument("--limit", dest="limit", type=int, help="Limit number of images to process")
        parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Do not write variants, only report")
        parser.add_argument("--verbose", dest="verbose", action="store_true", help="Verbose output")

    def handle(self, *args, **options):
        org_id = options.get("org_id")
        ids = options.get("ids")
        limit = options.get("limit")
        dry = options.get("dry_run")
        verbose = options.get("verbose")

        qs = Image.objects.all().order_by("id")
        if org_id:
            qs = qs.filter(organization_id=org_id)
        if ids:
            qs = qs.filter(id__in=ids)
        if limit:
            qs = qs[:limit]

        total = qs.count()
        processed = 0
        created = 0
        skipped = 0
        errors = 0

        self.stdout.write(f"Scanning {total} images...")

        for img in qs.iterator():
            try:
                filename = str(img.file)
                base, ext = os.path.splitext(filename)

                # Check original exists
                if not default_storage.exists(filename):
                    skipped += 1
                    if verbose:
                        self.stdout.write(self.style.WARNING(f"[skip] original missing: id={img.id} file={filename}"))
                    continue

                # Determine which variants are missing
                targets = {
                    "thumb": f"{base}_thumb.webp",
                    "sm": f"{base}_sm.webp",
                    "md": f"{base}_md.webp",
                    "lg": f"{base}_lg.webp",
                }
                missing = {k: v for k, v in targets.items() if not default_storage.exists(v)}
                if not missing:
                    skipped += 1
                    if verbose:
                        self.stdout.write(f"[ok] all variants exist: id={img.id}")
                    continue

                # Read original bytes
                with default_storage.open(filename, mode="rb") as f:
                    original_bytes = f.read()

                # Generate all variants in-memory
                variants_bytes = resize_images(original_bytes)

                if dry:
                    self.stdout.write(self.style.NOTICE(f"[dry] would create {list(missing.keys())} for id={img.id}"))
                else:
                    for key in missing.keys():
                        variant_key = targets[key]
                        upload_to_storage(variant_key, variants_bytes[key])
                        created += 1
                    if verbose:
                        self.stdout.write(self.style.SUCCESS(f"[done] created {list(missing.keys())} for id={img.id}"))
                processed += 1
            except Exception as e:
                errors += 1
                self.stderr.write(self.style.ERROR(f"[err] id={img.id}: {e}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Completed. processed={processed} created_files={created} skipped={skipped} errors={errors}"
            )
        )
