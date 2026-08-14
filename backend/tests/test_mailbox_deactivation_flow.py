import unittest
from unittest import mock

from backend.registration import engine as gr


class OutlookWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.original_config = dict(gr.config)

    def tearDown(self):
        gr.config.clear()
        gr.config.update(self.original_config)

    def test_all_email_providers_require_exact_cpa_success(self):
        providers = ("duckmail", "yyds", "cloudflare", "mailnest", "outlookemail", "cloudmail", "vmail")
        for provider in providers:
            gr.config["email_provider"] = provider
            self.assertTrue(gr.registration_counts_as_success({"status": "success"}))
            for status in (
                "failed",
                "disabled",
                "skipped",
                "not_attempted",
                "",
                "SUCCESS",
                " success ",
                None,
            ):
                self.assertFalse(gr.registration_counts_as_success({"status": status}))

    def test_cpa_conversion_is_enabled_by_default(self):
        self.assertTrue(gr.DEFAULT_CONFIG["cpa_auto_add"])

    def test_cpa_failure_skips_remote_disable(self):
        gr.config.update(
            {
                "email_provider": "outlookemail",
                "outlookemail_source": "accounts",
                "outlookemail_disable_after_cpa_success": True,
            }
        )
        with mock.patch.object(gr.outlookemail_provider, "account_for_email") as lookup:
            detail = gr.disable_outlookemail_after_cpa_success(
                "fixture@outlook.com", {"status": "failed", "error": "fixture"}
            )
        self.assertEqual(detail["status"], "skipped_cpa")
        lookup.assert_not_called()

    def test_feature_disabled_and_temp_source_are_recorded(self):
        gr.config.update(
            {
                "email_provider": "outlookemail",
                "outlookemail_source": "accounts",
                "outlookemail_disable_after_cpa_success": False,
            }
        )
        self.assertEqual(
            gr.default_email_disable_detail("outlookemail", {"status": "success"})["status"],
            "feature_disabled",
        )
        gr.config["outlookemail_disable_after_cpa_success"] = True
        gr.config["outlookemail_source"] = "temp"
        self.assertEqual(
            gr.default_email_disable_detail("outlookemail", {"status": "success"})["status"],
            "unsupported_source",
        )


if __name__ == "__main__":
    unittest.main()
