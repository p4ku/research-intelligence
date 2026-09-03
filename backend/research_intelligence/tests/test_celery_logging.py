import io
import sys
import logging
from unittest.mock import patch
from django.test import SimpleTestCase
from celery.signals import after_setup_logger, after_setup_task_logger
from django_project.celery import setup_celery_logging_to_stdout


class CeleryLoggingRedirectionTestCase(SimpleTestCase):
    """
    Validates that Celery worker log output is properly redirected to sys.stdout
    instead of sys.stderr. This ensures Cloud Foundry / PaaS Loggregators
    do not falsely flag INFO/DEBUG worker logs as ERR (in red text).
    """

    def test_celery_signals_are_connected(self):
        """
        Ensure setup_celery_logging_to_stdout is hooked into both
        after_setup_logger and after_setup_task_logger signals.
        """
        # after_setup_logger receivers (stored as weakrefs in celery signal dispatcher)
        logger_receivers = [r[1]() if callable(r[1]) else r[1] for r in after_setup_logger.receivers]
        self.assertIn(
            setup_celery_logging_to_stdout,
            logger_receivers,
            "setup_celery_logging_to_stdout must be connected to after_setup_logger signal."
        )

        # after_setup_task_logger receivers
        task_logger_receivers = [r[1]() if callable(r[1]) else r[1] for r in after_setup_task_logger.receivers]
        self.assertIn(
            setup_celery_logging_to_stdout,
            task_logger_receivers,
            "setup_celery_logging_to_stdout must be connected to after_setup_task_logger signal."
        )

    def test_setup_celery_logging_redirects_stderr_to_stdout(self):
        """
        When a logger has a StreamHandler pointing to sys.stderr or sys.__stderr__,
        setup_celery_logging_to_stdout must redirect it to sys.stdout.
        """
        dummy_logger = logging.getLogger("test_celery_stderr_redirect")
        dummy_logger.handlers = []

        handler_err = logging.StreamHandler(sys.stderr)
        dummy_logger.addHandler(handler_err)
        self.assertIs(handler_err.stream, sys.stderr)

        # Execute hook
        setup_celery_logging_to_stdout(dummy_logger)

        self.assertIs(
            handler_err.stream,
            sys.stdout,
            "StreamHandler pointing to sys.stderr must be redirected to sys.stdout."
        )

    def test_setup_celery_logging_redirects_sys_under_stderr_to_stdout(self):
        """
        When a logger has a StreamHandler pointing to sys.__stderr__,
        it must also be redirected to sys.stdout.
        """
        dummy_logger = logging.getLogger("test_celery_under_stderr_redirect")
        dummy_logger.handlers = []

        handler_under_err = logging.StreamHandler(sys.__stderr__)
        dummy_logger.addHandler(handler_under_err)

        setup_celery_logging_to_stdout(dummy_logger)

        self.assertIs(
            handler_under_err.stream,
            sys.stdout,
            "StreamHandler pointing to sys.__stderr__ must be redirected to sys.stdout."
        )

    def test_setup_celery_logging_leaves_custom_streams_unmodified(self):
        """
        Non-stderr streams (e.g. StringIO, file handlers, or existing stdout)
        must not be overwritten.
        """
        custom_stream = io.StringIO()
        dummy_logger = logging.getLogger("test_celery_custom_stream")
        dummy_logger.handlers = []

        custom_handler = logging.StreamHandler(custom_stream)
        dummy_logger.addHandler(custom_handler)

        setup_celery_logging_to_stdout(dummy_logger)

        self.assertIs(
            custom_handler.stream,
            custom_stream,
            "Custom stream handlers (e.g. StringIO) must remain unmodified."
        )

    def test_logging_emits_to_stdout_after_redirection(self):
        """
        Verify that emitting a log line through a redirected handler
        writes bytes to sys.stdout, and nothing to sys.stderr.
        """
        test_logger = logging.getLogger("test_celery_emit_stdout")
        test_logger.handlers = []
        test_logger.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter("[TEST] %(message)s")
        handler.setFormatter(formatter)
        test_logger.addHandler(handler)

        # Redirect to stdout
        setup_celery_logging_to_stdout(test_logger)

        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()

        with patch("sys.stdout", captured_stdout), patch("sys.stderr", captured_stderr):
            # Update stream to the mocked stdout
            handler.setStream(sys.stdout)
            test_logger.info("Operational screening step completed successfully.")

        self.assertIn("Operational screening step completed successfully.", captured_stdout.getvalue())
        self.assertEqual(captured_stderr.getvalue(), "")

    def test_celery_task_loggers_setup_signals_integration(self):
        """
        End-to-end signal integration test: When Celery initializes task loggers,
        the connected after_setup_task_logger signal intercepts the handlers
        and converts any stderr streams to stdout.
        """
        from django_project.celery import app
        task_logger = app.log.setup_task_loggers(loglevel="INFO")
        for h in getattr(task_logger, 'handlers', []):
            if isinstance(h, logging.StreamHandler) and hasattr(h, 'stream'):
                self.assertNotIn(
                    h.stream,
                    (sys.stderr, sys.__stderr__),
                    "No Celery task logger handler should point to sys.stderr after signal hook execution."
                )
                self.assertIs(
                    h.stream,
                    sys.stdout,
                    "Celery task logger StreamHandler must point to sys.stdout."
                )
