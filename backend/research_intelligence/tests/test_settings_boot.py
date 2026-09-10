"""Boot the settings module the way production does.

settings.py has branches that only run outside the test runner: the Sentry
block is guarded by ``SENTRY_DSN and not is_testing`` and the security
warnings by ``not DEBUG and not is_testing``. The suite never executes them,
so an import error there is invisible to CI and only shows up as a crashed
instance on deploy (10 Sep 2026: ``NameError: name 'logging' is not defined``
took sri-api to 0/2 instances while CI was green).

Importing the module in a fresh interpreter, with a DSN set and the test
markers absent, makes those branches part of the suite.
"""

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]


class SettingsBootTests(SimpleTestCase):
    def test_settings_import_with_production_shape(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"DJANGO_TESTING", "DEBUG", "DB_HOST"}
        }
        env.update(
            {
                "DEBUG": "False",
                "SECRET_KEY": "settings-boot-test-not-a-real-key",
                # Well-formed but unreachable; sentry_sdk.init does no I/O.
                "SENTRY_DSN": "https://0123456789abcdef@o0.ingest.sentry.io/0",
                "SENTRY_TRACES_SAMPLE_RATE": "0",
                "SENTRY_PROFILE_SESSION_SAMPLE_RATE": "0",
            }
        )
        result = subprocess.run(
            [sys.executable, "-c", "import django_project.settings"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "settings.py failed to import with a production-shaped environment:\n"
            + result.stderr[-3000:],
        )
