import unittest
from unittest import mock

from backend.registration import engine
from backend.web import application
from backend.web.jobs import RegistrationJobCoordinator


class RegisterLimitTests(unittest.TestCase):
    def test_engine_exposes_shared_upper_bounds(self):
        self.assertEqual(engine.MAX_REGISTER_WORKERS, 10)
        self.assertEqual(engine.MAX_REGISTER_COUNT, 100000)

    def test_config_updates_clamp_to_engine_limits(self):
        with mock.patch.object(engine, "load_config"), mock.patch.object(
            engine, "save_config"
        ), mock.patch.dict(engine.config, {}, clear=False):
            result = application._apply_config_updates(
                {"register_count": 10**9, "register_workers": 99}
            )

        self.assertEqual(result["config"]["register_count"], engine.MAX_REGISTER_COUNT)
        self.assertEqual(result["config"]["register_workers"], engine.MAX_REGISTER_WORKERS)

    def test_config_updates_keep_lower_bound(self):
        with mock.patch.object(engine, "load_config"), mock.patch.object(
            engine, "save_config"
        ), mock.patch.dict(engine.config, {}, clear=False):
            result = application._apply_config_updates(
                {"register_count": 0, "register_workers": -5}
            )

        self.assertEqual(result["config"]["register_count"], 1)
        self.assertEqual(result["config"]["register_workers"], 1)

    def test_job_start_clamps_count_and_workers(self):
        manager = RegistrationJobCoordinator()
        seen = []

        with mock.patch.object(engine, "load_config"), mock.patch.object(
            engine, "_wire_runtime_modules"
        ), mock.patch.object(
            engine._bs, "allow_browser_launches"
        ), mock.patch.object(
            engine, "run_registration", side_effect=seen.append
        ), mock.patch.dict(
            engine.config, {"debug_mode": False}, clear=False
        ):
            status = manager.start(count=10**9, workers=99)
            if manager._thread is not None:
                manager._thread.join(timeout=5)

        self.assertEqual(status["target_count"], engine.MAX_REGISTER_COUNT)
        self.assertEqual(status["workers"], engine.MAX_REGISTER_WORKERS)
        self.assertEqual(seen, [engine.MAX_REGISTER_COUNT])

    def test_job_start_never_exceeds_requested_count_with_workers(self):
        manager = RegistrationJobCoordinator()

        with mock.patch.object(engine, "load_config"), mock.patch.object(
            engine, "_wire_runtime_modules"
        ), mock.patch.object(
            engine._bs, "allow_browser_launches"
        ), mock.patch.object(
            engine, "run_registration"
        ), mock.patch.dict(
            engine.config, {"debug_mode": False}, clear=False
        ):
            status = manager.start(count=3, workers=10)
            if manager._thread is not None:
                manager._thread.join(timeout=5)

        self.assertEqual(status["target_count"], 3)
        self.assertEqual(status["workers"], 3)


if __name__ == "__main__":
    unittest.main()
