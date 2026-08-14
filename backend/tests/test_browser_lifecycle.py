import unittest
from unittest import mock

from backend.automation import session as browser_session


class CamoufoxProcessMatchTests(unittest.TestCase):
    def tearDown(self):
        browser_session.allow_browser_launches()

    def test_matches_camoufox_executables_and_managed_profiles(self):
        self.assertTrue(browser_session._is_camoufox_process("/cache/camoufox/camoufox-bin", ""))
        self.assertTrue(
            browser_session._is_camoufox_process(
                "/usr/lib/firefox/firefox",
                "firefox -profile /tmp/grok-register-camoufox/123-profile",
            )
        )

    def test_does_not_match_regular_firefox(self):
        self.assertFalse(
            browser_session._is_camoufox_process(
                "/usr/lib/firefox/firefox",
                "firefox https://example.com",
            )
        )

    def test_emergency_block_prevents_browser_restart(self):
        browser_session.block_browser_launches()
        with self.assertRaisesRegex(RuntimeError, "紧急终止"):
            browser_session.start_browser()

    def test_kill_all_targets_camoufox_tree_only(self):
        processes = {
            101: (1, "/cache/camoufox/camoufox", "camoufox"),
            102: (101, "/usr/lib/helper", "content process"),
            201: (1, "/usr/lib/firefox/firefox", "firefox https://example.com"),
        }
        killed = []
        with (
            mock.patch.object(browser_session, "_linux_processes", return_value=processes),
            mock.patch.object(browser_session, "_cleanup_all_managed_profiles", return_value=2),
            mock.patch.object(browser_session.os, "kill", side_effect=lambda pid, sig: killed.append((pid, sig))),
            mock.patch.object(browser_session.time, "sleep"),
        ):
            result = browser_session.kill_all_camoufox_processes()

        self.assertEqual(result, {"killed": 2, "profiles_cleaned": 2})
        self.assertEqual({pid for pid, _ in killed}, {101, 102})
        self.assertNotIn(201, {pid for pid, _ in killed})


# Playwright 在缺少系统库时抛出的真实报文（Linux，未安装 GTK3）
MISSING_GTK_ERROR = """BrowserType.launch_persistent_context: Failed to launch the browser process.
Browser logs:

<launching> /home/user/.cache/camoufox/browsers/official/152.0.4/camoufox-bin -no-remote
<launched> pid=394805
[pid=394805][err] [394807] Sandbox: CanCreateUserNamespace() unshare(CLONE_NEWPID): EPERM
[pid=394805][err] XPCOMGlueLoad error for file /home/user/.cache/camoufox/browsers/official/152.0.4/libmozgtk.so:
[pid=394805][err] libgtk-3.so.0: cannot open shared object file: No such file or directory
[pid=394805][err] Couldn't load XPCOM.
[pid=394805] <process did exit: exitCode=255, signal=null>
"""


class MissingSystemLibraryTests(unittest.TestCase):
    def tearDown(self):
        browser_session._note_start_success()

    def test_extracts_missing_soname_and_offers_fix(self):
        message = browser_session.missing_system_library_error(MISSING_GTK_ERROR)
        self.assertIn("libgtk-3.so.0", message)
        self.assertIn("playwright install-deps firefox", message)
        self.assertIn("Docker", message)
        # 沙箱 EPERM 只是伴随告警，不该被当成缺失的库名列出来
        self.assertNotIn("CLONE_NEWPID", message)

    def test_deduplicates_and_falls_back_when_no_soname_parsed(self):
        message = browser_session.missing_system_library_error(
            "libx.so.1: cannot open shared object file\nlibx.so.1: cannot open shared object file"
        )
        self.assertEqual(message.count("libx.so.1"), 1)
        fallback = browser_session.missing_system_library_error("Couldn't load XPCOM.")
        self.assertIn("图形相关的共享库", fallback)

    def test_ignores_unrelated_launch_failures(self):
        self.assertEqual(browser_session.missing_system_library_error(""), "")
        self.assertEqual(
            browser_session.missing_system_library_error("Timeout 30000ms exceeded"), ""
        )

    def test_message_is_classified_as_browser_failure(self):
        from backend.registration import engine

        message = browser_session.missing_system_library_error(MISSING_GTK_ERROR)
        self.assertEqual(engine.classify_failure(RuntimeError(message)), engine.FAIL_BROWSER)

    def test_start_browser_stops_retrying_on_missing_library(self):
        attempts = []

        def _boom(*args, **kwargs):
            attempts.append(1)
            raise RuntimeError(MISSING_GTK_ERROR)

        with (
            mock.patch.object(browser_session, "create_browser_options", side_effect=_boom),
            mock.patch.object(browser_session.time, "sleep") as slept,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                browser_session.start_browser()

        # 缺系统库重试 4 次也是同一个结果：只试一次，且不再退避等待
        self.assertEqual(len(attempts), 1)
        self.assertFalse(slept.called)
        self.assertIn("libgtk-3.so.0", str(ctx.exception))

    def test_start_browser_still_retries_other_failures(self):
        attempts = []

        def _boom(*args, **kwargs):
            attempts.append(1)
            raise RuntimeError("Timeout 30000ms exceeded")

        with (
            mock.patch.object(browser_session, "create_browser_options", side_effect=_boom),
            mock.patch.object(browser_session.time, "sleep"),
        ):
            with self.assertRaisesRegex(Exception, "已重试4次"):
                browser_session.start_browser()

        self.assertEqual(len(attempts), 4)


if __name__ == "__main__":
    unittest.main()
