"""Transaction-scoped PostgreSQL limits; never alter the server configuration."""
import time
from contextlib import contextmanager

from django.conf import settings
from django.db import connection, transaction


class PlannerDeadline(Exception):
    pass


@contextmanager
def planner_transaction():
    deadline = time.monotonic() + settings.TAG_COLLECTION_PLANNER_WALL_SECONDS

    def check_deadline(execute, sql, params, many, context):
        if time.monotonic() >= deadline:
            raise PlannerDeadline()
        return execute(sql, params, many, context)

    with transaction.atomic():
        previous = {}
        if connection.vendor == "postgresql":
            limits = {
                "statement_timeout": str(settings.TAG_COLLECTION_PLANNER_STATEMENT_MS),
                "lock_timeout": str(settings.TAG_COLLECTION_PLANNER_LOCK_MS),
                "max_parallel_workers_per_gather": "0",
            }
            with connection.cursor() as cursor:
                for name, value in limits.items():
                    cursor.execute("SELECT current_setting(%s)", [name])
                    previous[name] = cursor.fetchone()[0]
                    cursor.execute("SELECT set_config(%s, %s, true)", [name, value])
        try:
            with connection.execute_wrapper(check_deadline):
                yield
        except BaseException:
            transaction.set_rollback(True)
            raise
        finally:
            # A failed statement rolls the savepoint/transaction back, including
            # SET LOCAL. Restore explicitly for callers already in a transaction.
            if previous and not connection.needs_rollback:
                with connection.cursor() as cursor:
                    for name, value in previous.items():
                        cursor.execute("SELECT set_config(%s, %s, true)", [name, value])
