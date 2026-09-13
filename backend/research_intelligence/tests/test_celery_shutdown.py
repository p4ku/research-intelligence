from django.test import SimpleTestCase
from django_project.celery import app


class CeleryShutdownRequeueTestCase(SimpleTestCase):
    """
    Cloud Foundry sends SIGTERM to sri-worker and SIGKILLs it 10 seconds later on every
    deploy or restart. With REMAP_SIGTERM=SIGQUIT in the worker's env (manifest.yml),
    TERM starts a cold shutdown; the four settings checked here are what make the worker
    re-queue its in-flight tasks before exiting, instead of leaving them unacknowledged
    in Redis until the 1 h visibility timeout redelivers them.
    """

    def test_soft_shutdown_fits_inside_cloud_foundry_grace_period(self):
        timeout = app.conf.worker_soft_shutdown_timeout
        self.assertGreater(
            timeout, 0,
            "worker_soft_shutdown_timeout must be > 0 or the cold shutdown never re-queues tasks."
        )
        self.assertLess(
            timeout, 10,
            "worker_soft_shutdown_timeout must finish before Cloud Foundry's 10 s SIGKILL."
        )

    def test_soft_shutdown_runs_when_idle_with_eta_tasks(self):
        self.assertTrue(
            app.conf.worker_enable_soft_shutdown_on_idle,
            "Agent ticks are dispatched with a countdown (ETA); without soft shutdown on idle, "
            "a worker holding only ETA tasks skips the soft shutdown and can lose them."
        )

    def test_late_ack_and_reject_on_worker_lost(self):
        self.assertTrue(app.conf.task_acks_late, "task_acks_late must stay on: tasks are acked after they finish.")
        self.assertTrue(
            app.conf.task_reject_on_worker_lost,
            "task_reject_on_worker_lost must stay on so a cancelled task's message is re-queued."
        )
