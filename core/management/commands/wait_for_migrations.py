import time
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    """Django command to wait for migrations to complete."""

    def handle(self, *args, **options):
        """Entrypoint for command."""
        self.stdout.write('Waiting for migrations to complete...')
        db_conn = connections['default']
        executor = MigrationExecutor(db_conn)
        while True:
            try:
                # Check if there are any unapplied migrations
                if not executor.migration_plan(executor.loader.graph.leaf_nodes()):
                    break
                self.stdout.write('Migrations pending, waiting 1 second...')
                time.sleep(1)
            except Exception as e:
                self.stdout.write(f'Error checking migrations: {str(e)}, waiting 1 second...')
                time.sleep(1)

        self.stdout.write(self.style.SUCCESS('All migrations completed!')) 