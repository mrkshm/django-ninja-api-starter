import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    """Django command to wait for database."""

    def add_arguments(self, parser):
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="Seconds to wait between connection attempts.",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=0,
            help="Maximum seconds to wait. Use 0 to wait forever.",
        )

    def handle(self, *args, **options):
        """Entrypoint for command."""
        sleep_seconds = options["sleep"]
        timeout_seconds = options["timeout"]
        deadline = time.monotonic() + timeout_seconds if timeout_seconds else None

        self.stdout.write('Waiting for database...')
        while True:
            try:
                connections['default'].ensure_connection()
                break
            except OperationalError as exc:
                if deadline is not None and time.monotonic() >= deadline:
                    raise CommandError("Database unavailable.") from exc
                self.stdout.write(f'Database unavailable, waiting {sleep_seconds:g} second(s)...')
                time.sleep(sleep_seconds)

        self.stdout.write(self.style.SUCCESS('Database available!')) 
