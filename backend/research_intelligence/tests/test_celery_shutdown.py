import os
import unittest

from django.test import SimpleTestCase
from django_project.celery import app

MANIFEST = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'manifest.yml'))


class CeleryShutdownRequeueTestCase(SimpleTestCase):
    """
    Cloud Foundry sends SIGTERM to sri-worker and SIGKILLs it 10 seconds later on every
    deploy or restart. For in-flight tasks to be re-queued instead of waiting out the 1 h
    Redis visibility timeout, three things must hold: the signal must reach Celery (CF runs
    a Docker app's `command:` under `sh -c`, so the manifest command must `exec`), TERM must
    mean cold shutdown (REMAP_SIGTERM=SIGQUIT in the worker env), and the shutdown must
    finish inside the 10 s window with late acks so kombu restores the unacked messages
    when the broker channel closes.
    """

    def test_soft_shutdown_window_leaves_headroom_inside_cloud_foundry_grace_period(self):
        timeout = app.conf.worker_soft_shutdown_timeout
        self.assertGreater(
            timeout, 0,
            "Soft shutdown is off: short tasks would be cancelled instead of being allowed to finish."
        )
        self.assertLessEqual(
            timeout, 5,
            "Cancel + pool join + exit took ~2 s under the prod worker flags; the window must leave "
            "that headroom inside Cloud Foundry's 10 s SIGKILL grace period."
        )

    def test_soft_shutdown_on_idle_is_enabled(self):
        self.assertTrue(
            app.conf.worker_enable_soft_shutdown_on_idle,
            "Celery recommends soft shutdown on idle when ETA tasks (retry countdowns) can be reserved."
        )

    def test_late_ack_and_reject_on_worker_lost(self):
        self.assertTrue(app.conf.task_acks_late, "task_acks_late must stay on: tasks are acked after they finish.")
        self.assertTrue(
            app.conf.task_reject_on_worker_lost,
            "task_reject_on_worker_lost must stay on so a cancelled task's message is re-queued."
        )

    @unittest.skipUnless(os.path.exists(MANIFEST), "manifest.yml is only present in a full repo checkout")
    def test_manifest_worker_execs_celery_and_remaps_sigterm(self):
        with open(MANIFEST) as fh:
            manifest = fh.read()
        worker_commands = [
            line.strip() for line in manifest.splitlines()
            if line.strip().startswith('command:') and 'worker' in line
        ]
        self.assertEqual(len(worker_commands), 1, worker_commands)
        self.assertTrue(
            worker_commands[0].startswith('command: exec celery'),
            f"CF runs `command:` as `sh -c COMMAND`; without `exec`, SIGTERM stops sh, not Celery: {worker_commands[0]}"
        )
        self.assertIn('REMAP_SIGTERM: SIGQUIT', manifest, "sri-worker needs REMAP_SIGTERM=SIGQUIT so TERM is a cold shutdown.")
