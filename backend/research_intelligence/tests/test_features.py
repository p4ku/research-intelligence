"""
Unit Tests for Central Feature Flagging Module (research_intelligence.features).
"""

import os
from unittest.mock import patch
from django.test import TestCase, override_settings

from research_intelligence.features import (
    Feature,
    ALL_FEATURES,
    is_feature_enabled,
    get_all_features,
    require_feature,
    KNOWN_FEATURES,
)


class FeatureFlagsTestCase(TestCase):
    """
    Validates central feature flag resolution, safe defaults (False),
    StrEnum support, case-insensitivity, settings overrides, environment fallback,
    and gating decorators.
    """

    def test_strenum_properties_and_all_features_list(self):
        """Feature is a StrEnum that behaves as native strings with ALL_FEATURES list."""
        self.assertEqual(Feature.SCHEDULING, "SCHEDULING")
        self.assertEqual(Feature.EMAIL_NOTIFICATIONS, "EMAIL_NOTIFICATIONS")
        self.assertIsInstance(Feature.SCHEDULING, str)
        self.assertEqual(ALL_FEATURES, [Feature.SCHEDULING, Feature.EMAIL_NOTIFICATIONS])
        self.assertEqual(list(Feature), [Feature.SCHEDULING, Feature.EMAIL_NOTIFICATIONS])

    def test_default_unconfigured_feature_returns_false(self):
        """Unconfigured feature names must always resolve to False by default."""
        self.assertFalse(is_feature_enabled("TOTALLY_UNKNOWN_FEATURE_XYZ"))
        self.assertFalse(is_feature_enabled("RANDOM_FLAG"))

    def test_default_flags_are_false_in_base_settings(self):
        """SCHEDULING is permanently enabled; EMAIL_NOTIFICATIONS evaluates to False by default."""
        self.assertTrue(is_feature_enabled(Feature.SCHEDULING))
        self.assertFalse(is_feature_enabled(Feature.EMAIL_NOTIFICATIONS))
        self.assertTrue(is_feature_enabled("SCHEDULING"))
        self.assertFalse(is_feature_enabled("EMAIL_NOTIFICATIONS"))

    def test_explicit_default_fallback_argument(self):
        """If unconfigured, is_feature_enabled respects an explicit default argument."""
        self.assertTrue(is_feature_enabled("NON_EXISTENT_FLAG", default=True))
        self.assertFalse(is_feature_enabled("NON_EXISTENT_FLAG", default=False))

    def test_empty_or_none_feature_name(self):
        """Empty, whitespace, or None feature names safely return default (False)."""
        self.assertFalse(is_feature_enabled(None))
        self.assertFalse(is_feature_enabled(""))
        self.assertFalse(is_feature_enabled("   "))
        self.assertTrue(is_feature_enabled(None, default=True))
        self.assertTrue(is_feature_enabled("", default=True))

    @override_settings(FEATURES={"SCHEDULING": True, "EMAIL_NOTIFICATIONS": False})
    def test_override_settings_dict_enables_and_disables_features(self):
        """FEATURES dictionary in Django settings controls feature state directly."""
        self.assertTrue(is_feature_enabled(Feature.SCHEDULING))
        self.assertFalse(is_feature_enabled(Feature.EMAIL_NOTIFICATIONS))
        # String lookup also matches
        self.assertTrue(is_feature_enabled("SCHEDULING"))
        self.assertFalse(is_feature_enabled("EMAIL_NOTIFICATIONS"))

    @override_settings(FEATURES={Feature.SCHEDULING: True})
    def test_features_dict_with_strenum_keys(self):
        """FEATURES dictionary works seamlessly with StrEnum keys."""
        self.assertTrue(is_feature_enabled(Feature.SCHEDULING))
        self.assertTrue(is_feature_enabled("SCHEDULING"))

    @override_settings(FEATURES={"SCHEDULING": True})
    def test_case_insensitivity_and_whitespace(self):
        """Feature name lookup must be completely case-insensitive and strip padding whitespace."""
        self.assertTrue(is_feature_enabled("scheduling"))
        self.assertTrue(is_feature_enabled("Scheduling"))
        self.assertTrue(is_feature_enabled("SCHEDULING"))
        self.assertTrue(is_feature_enabled("  scheduling  "))
        self.assertTrue(is_feature_enabled("  SCHEDULING\n"))

    @override_settings(
        FEATURES={
            "FLAG_BOOL_TRUE": True,
            "FLAG_STR_TRUE": "true",
            "FLAG_STR_UPPER_TRUE": "TRUE",
            "FLAG_STR_1": "1",
            "FLAG_INT_1": 1,
            "FLAG_YES": "yes",
            "FLAG_ON": "on",
            "FLAG_T": "t",
            "FLAG_ENABLED": "enabled",
        }
    )
    def test_truthy_value_representations(self):
        """Various truthy string/int representations must all parse cleanly to True."""
        for flag in [
            "FLAG_BOOL_TRUE",
            "FLAG_STR_TRUE",
            "FLAG_STR_UPPER_TRUE",
            "FLAG_STR_1",
            "FLAG_INT_1",
            "FLAG_YES",
            "FLAG_ON",
            "FLAG_T",
            "FLAG_ENABLED",
        ]:
            with self.subTest(flag=flag):
                self.assertTrue(is_feature_enabled(flag))

    @override_settings(
        FEATURES={
            "FLAG_BOOL_FALSE": False,
            "FLAG_STR_FALSE": "false",
            "FLAG_STR_0": "0",
            "FLAG_INT_0": 0,
            "FLAG_NO": "no",
            "FLAG_OFF": "off",
            "FLAG_F": "f",
            "FLAG_DISABLED": "disabled",
            "FLAG_EMPTY": "",
        }
    )
    def test_falsy_value_representations(self):
        """Various falsy string/int representations must all parse cleanly to False."""
        for flag in [
            "FLAG_BOOL_FALSE",
            "FLAG_STR_FALSE",
            "FLAG_STR_0",
            "FLAG_INT_0",
            "FLAG_NO",
            "FLAG_OFF",
            "FLAG_F",
            "FLAG_DISABLED",
            "FLAG_EMPTY",
        ]:
            with self.subTest(flag=flag):
                self.assertFalse(is_feature_enabled(flag))

    @override_settings(FEATURES={"EXPLICIT_NONE": None})
    def test_none_value_in_features_dict_falls_back(self):
        """None value in FEATURES dictionary falls back to default argument."""
        self.assertFalse(is_feature_enabled("EXPLICIT_NONE"))
        self.assertTrue(is_feature_enabled("EXPLICIT_NONE", default=True))

    @override_settings(FEATURES={"COMPLEX_OBJ": ["custom_element"], "RANDOM_STR": "some_random_word"})
    def test_arbitrary_objects_and_strings_evaluated_via_bool(self):
        """Arbitrary non-standard objects and strings evaluate via standard bool()."""
        self.assertTrue(is_feature_enabled("COMPLEX_OBJ"))
        self.assertTrue(is_feature_enabled("RANDOM_STR"))

    @override_settings(FEATURES=None, FEATURE_CUSTOM_ATTRIBUTE=True)
    def test_fallback_to_direct_setting_attribute(self):
        """When settings.FEATURES is None or lacks key, checks settings.FEATURE_<NAME>."""
        self.assertTrue(is_feature_enabled("CUSTOM_ATTRIBUTE"))

    @override_settings(FEATURES={}, FEATURE_LEGACY_STYLE="1")
    def test_fallback_to_direct_setting_attribute_string(self):
        """Direct attribute fallback handles string truthy representations."""
        self.assertTrue(is_feature_enabled("LEGACY_STYLE"))

    @override_settings(FEATURES={})
    def test_fallback_to_environment_variables(self):
        """When not present in Django settings, falls back to environment variables."""
        with patch.dict(os.environ, {"FEATURE_ENV_TEST_FLAG": "true"}):
            self.assertTrue(is_feature_enabled("ENV_TEST_FLAG"))

        with patch.dict(os.environ, {"FEATURE_ENV_TEST_FLAG": "false"}):
            self.assertFalse(is_feature_enabled("ENV_TEST_FLAG"))

        with patch.dict(os.environ, {"DIRECT_ENV_KEY": "yes"}):
            self.assertTrue(is_feature_enabled("DIRECT_ENV_KEY"))

    @override_settings(FEATURES={"SCHEDULING": True, "EMAIL_NOTIFICATIONS": False, "CUSTOM_BETA": True})
    def test_get_all_features_returns_snapshot(self):
        """get_all_features aggregates all known flags and custom configured flags."""
        snapshot = get_all_features()
        self.assertIsInstance(snapshot, dict)
        self.assertIn(Feature.SCHEDULING, snapshot)
        self.assertIn(Feature.EMAIL_NOTIFICATIONS, snapshot)
        self.assertIn("CUSTOM_BETA", snapshot)

        self.assertTrue(snapshot[Feature.SCHEDULING])
        self.assertFalse(snapshot[Feature.EMAIL_NOTIFICATIONS])
        self.assertTrue(snapshot["CUSTOM_BETA"])

    @override_settings(FEATURES={Feature.SCHEDULING: True})
    def test_get_all_features_with_strenum_keys_in_settings(self):
        """get_all_features handles StrEnum keys inside settings.FEATURES."""
        snapshot = get_all_features()
        self.assertTrue(snapshot[Feature.SCHEDULING])

    def test_known_features_registry(self):
        """KNOWN_FEATURES contains descriptions for core system features."""
        self.assertIn(Feature.SCHEDULING, KNOWN_FEATURES)
        self.assertIn(Feature.EMAIL_NOTIFICATIONS, KNOWN_FEATURES)
        self.assertTrue(len(KNOWN_FEATURES[Feature.SCHEDULING]) > 0)
        self.assertTrue(len(KNOWN_FEATURES[Feature.EMAIL_NOTIFICATIONS]) > 0)

    @override_settings(FEATURES={Feature.SCHEDULING: True, Feature.EMAIL_NOTIFICATIONS: False})
    def test_require_feature_decorator_with_enum(self):
        """require_feature gates function execution using StrEnum members."""
        @require_feature(Feature.SCHEDULING)
        def scheduled_job():
            return "executed_schedule"

        @require_feature(Feature.EMAIL_NOTIFICATIONS)
        def mailer_job():
            return "sent_mail"

        @require_feature(Feature.EMAIL_NOTIFICATIONS, fallback="email_skipped")
        def mailer_with_fallback():
            return "sent_mail"

        @require_feature(Feature.EMAIL_NOTIFICATIONS, fallback=lambda: "callable_fallback")
        def mailer_with_callable_fallback():
            return "sent_mail"

        self.assertEqual(scheduled_job(), "executed_schedule")
        self.assertIsNone(mailer_job())
        self.assertEqual(mailer_with_fallback(), "email_skipped")
        self.assertEqual(mailer_with_callable_fallback(), "callable_fallback")
