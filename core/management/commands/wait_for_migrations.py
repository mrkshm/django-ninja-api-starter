import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import OperationalError


class Command(BaseCommand):
    """Django command to wait for migrations to complete."""

    def add_arguments(self, parser):
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="Seconds to wait between migration checks.",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=300.0,
            help="Maximum seconds to wait. Use 0 to wait forever.",
        )

    def handle(self, *args, **options):
        """Entrypoint for command."""
        sleep_seconds = options["sleep"]
        timeout_seconds = options["timeout"]
        deadline = time.monotonic() + timeout_seconds if timeout_seconds else None

        self.stdout.write("Waiting for migrations to complete...")
        db_conn = connections["default"]
        while True:
            try:
                # Rebuild the loader on every poll so migrations applied by a
                # different process become visible.
                executor = MigrationExecutor(db_conn)
                if not executor.migration_plan(executor.loader.graph.leaf_nodes()):
                    break
                message = "Migrations pending"
            except OperationalError as exc:
                message = f"Database unavailable while checking migrations: {exc}"

            if deadline is not None and time.monotonic() >= deadline:
                raise CommandError("Timed out waiting for migrations.")

            self.stdout.write(f"{message}, waiting {sleep_seconds:g} second(s)...")
            time.sleep(sleep_seconds)

        self.stdout.write(self.style.SUCCESS("All migrations completed!"))
