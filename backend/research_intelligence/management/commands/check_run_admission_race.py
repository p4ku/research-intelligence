"""
Race proof for run admission on a real Postgres.

The unit suite runs on SQLite, where select_for_update() is a no-op, so it
cannot show that the Workspace row lock in admit_run() is what holds the
per-workspace cap. This command can: it fires N threads at the real
start_pipeline_run_logic at the same instant and checks that exactly
MAX_CONCURRENT_RUNS_PER_WORKSPACE runs land, then that one of N identical
windows lands. --no-lock repeats the burst with the lock patched out and
expects the overshoot, proving the lock is doing the work.

    docker run -d --rm --name sri-race-pg -p 55432:5432 \\
        -e POSTGRES_PASSWORD=race -e POSTGRES_DB=race postgres:16-alpine
    DB_HOST=localhost DB_PORT=55432 DB_NAME=race DB_USER=postgres DB_PASSWORD=race \\
        python manage.py migrate && python manage.py check_run_admission_race
    docker stop sri-race-pg

Refuses to run on anything but Postgres. Creates and deletes its own
workspace ("Run admission race"); never point it at a shared database.
"""
import json
import threading
from collections import Counter
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections

from research_intelligence.models import PipelineRun, Workspace, WorkspaceMember
from research_intelligence.services.run_admission import max_concurrent_runs

WORKSPACE_NAME = "Run admission race"
TICK = 'research_intelligence.tasks.orchestrator.runner.PipelineRunner.tick'


class Command(BaseCommand):
    help = "Prove admit_run()'s row lock holds the per-workspace cap under concurrent starts (Postgres only)."

    def add_arguments(self, parser):
        parser.add_argument('--threads', type=int, default=20, help="Concurrent starts per burst (default 20).")
        parser.add_argument('--no-lock', action='store_true', help="Control run: patch select_for_update out and expect an overshoot.")

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            raise CommandError(f"This proof needs Postgres; the current database is {connection.vendor}.")

        from mcp_server.tools.pipeline_runs.triggers import start_pipeline_run_logic

        threads = options['threads']
        no_lock = options['no_lock']
        limit = max_concurrent_runs()
        if threads <= limit:
            raise CommandError(f"--threads must exceed the cap ({limit}) for the burst to mean anything.")

        User = get_user_model()
        user, _ = User.objects.get_or_create(username='run_admission_race')
        PipelineRun.objects.filter(workspace__name=WORKSPACE_NAME).delete()
        Workspace.objects.filter(name=WORKSPACE_NAME).delete()
        workspace = Workspace.objects.create(name=WORKSPACE_NAME)
        WorkspaceMember.objects.create(workspace=workspace, user=user, role='admin')

        def fire(count, window_for):
            outcomes = []
            guard = threading.Lock()
            barrier = threading.Barrier(count)

            def worker(i):
                try:
                    barrier.wait()
                    res = json.loads(start_pipeline_run_logic(user, str(workspace.id), **window_for(i)))
                    with guard:
                        outcomes.append(res.get('code') or res.get('status'))
                finally:
                    connections.close_all()

            workers = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
            with patch(TICK, return_value={"success": True}):
                for w in workers:
                    w.start()
                for w in workers:
                    w.join()
            return Counter(outcomes)

        try:
            patches = []
            if no_lock:
                from django.db.models.query import QuerySet
                patches.append(patch.object(QuerySet, 'select_for_update', lambda self, *a, **k: self))
            for p in patches:
                p.start()
            try:
                burst = fire(threads, lambda i: {"n_last_days": i + 1})
                in_flight = PipelineRun.objects.filter(workspace=workspace, status='running').count()
                self.stdout.write(f"burst of {threads}: {dict(burst)} → {in_flight} in flight (cap {limit})")
                if no_lock:
                    if in_flight <= limit:
                        raise CommandError("Control did not overshoot the cap this time; run it again.")
                    self.stdout.write(self.style.WARNING("CONTROL: the cap overshot without the lock, as expected."))
                    return
                if in_flight != limit or burst['run_limit_reached'] != threads - limit:
                    raise CommandError(f"Cap not held: {dict(burst)}, {in_flight} in flight.")

                PipelineRun.objects.filter(workspace=workspace).update(status='completed')
                twins = fire(min(threads, 10), lambda i: {"start_date": "2026-08-01", "end_date": "2026-08-15"})
                in_flight = PipelineRun.objects.filter(workspace=workspace, status='running').count()
                self.stdout.write(f"identical windows: {dict(twins)} → {in_flight} in flight")
                if in_flight != 1 or twins['success'] != 1:
                    raise CommandError(f"Duplicate window not held: {dict(twins)}, {in_flight} in flight.")
            finally:
                for p in patches:
                    p.stop()
            self.stdout.write(self.style.SUCCESS("RACE PROOF PASSED on postgresql"))
        finally:
            PipelineRun.objects.filter(workspace=workspace).delete()
            workspace.delete()
