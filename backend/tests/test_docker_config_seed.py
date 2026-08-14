"""覆盖 scripts/seed_config.py：容器入口与本机启动脚本共用的配置补齐逻辑。

该文件不在包内（供 docker/entrypoint.sh 与 scripts/start-*.sh 直接 python 调用），
所以这里按路径加载模块，而不是 import。
"""

import contextlib
import importlib.util
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = PROJECT_ROOT / "scripts" / "seed_config.py"


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("grok_seed_config", SEED_SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - 路径错误时才会发生
        raise AssertionError(f"无法加载配置脚本: {SEED_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed = _load_seed_module()

TEMPLATE = {
    "email_provider": "duckmail",
    "browser_headless": True,
    "register_count": 1,
    "cpa_auth_dir": "cpa_auth",
    "grok2api_auth_dir": "grok2api_auth",
    "outlookemail_api_base": "",
}


class SeedConfigTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.template = self.tmp / "config.example.json"
        self.template.write_text(
            json.dumps(TEMPLATE, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.target = self.tmp / "data" / "config.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self, **kwargs):
        return seed.seed_config(self.target, self.template, **kwargs)

    def _read_target(self):
        return json.loads(self.target.read_text(encoding="utf-8"))

    def test_creates_config_with_container_defaults(self):
        result = self._seed(env={})

        self.assertEqual(result["action"], "created")
        self.assertTrue(result["changed"])
        self.assertIsNone(result["backup"])
        self.assertEqual(sorted(result["added"]), sorted(TEMPLATE))

        data = self._read_target()
        # 容器内没有桌面，必须跑有头浏览器 + Xvfb；授权目录要落在挂载卷里。
        self.assertFalse(data["browser_headless"])
        self.assertEqual(data["cpa_auth_dir"], "data/cpa_auth")
        self.assertEqual(data["grok2api_auth_dir"], "data/grok2api_auth")
        self.assertEqual(data["outlookemail_api_base"], seed.DEFAULT_OUTLOOKEMAIL_API_BASE)
        # 其余键仍按模板取值。
        self.assertEqual(data["email_provider"], "duckmail")
        self.assertTrue(self.target.read_text(encoding="utf-8").endswith("\n"))

    def test_local_mode_keeps_template_values(self):
        result = self._seed(env={}, apply_container_defaults=False)

        self.assertEqual(result["action"], "created")
        data = self._read_target()
        self.assertTrue(data["browser_headless"])
        self.assertEqual(data["cpa_auth_dir"], "cpa_auth")
        self.assertEqual(data["outlookemail_api_base"], "")

    def test_outlookemail_api_base_env_override(self):
        self._seed(env={"GROK_OUTLOOKEMAIL_API_BASE": " http://mail:8000 "})

        self.assertEqual(self._read_target()["outlookemail_api_base"], "http://mail:8000")

    def test_merge_adds_new_keys_without_touching_user_values(self):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text(
            json.dumps({"email_provider": "vmail", "browser_headless": True}, indent=2),
            encoding="utf-8",
        )

        result = self._seed(env={})

        self.assertEqual(result["action"], "merged")
        self.assertIn("register_count", result["added"])
        self.assertNotIn("email_provider", result["added"])

        data = self._read_target()
        self.assertEqual(data["email_provider"], "vmail")
        # 已有配置里用户自己关掉的 headless 不能被容器默认值改写。
        self.assertTrue(data["browser_headless"])
        self.assertEqual(data["register_count"], 1)

    def test_existing_config_with_all_keys_is_untouched(self):
        payload = dict(TEMPLATE)
        payload["email_provider"] = "yyds"
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        before = self.target.read_text(encoding="utf-8")
        mtime = self.target.stat().st_mtime_ns

        result = self._seed(env={})

        self.assertEqual(result["action"], "unchanged")
        self.assertFalse(result["changed"])
        self.assertEqual(result["added"], [])
        self.assertEqual(self.target.read_text(encoding="utf-8"), before)
        self.assertEqual(self.target.stat().st_mtime_ns, mtime)

    def test_broken_config_is_backed_up_and_rebuilt(self):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("{ not json", encoding="utf-8")

        result = self._seed(env={})

        self.assertEqual(result["action"], "recreated")
        self.assertIsNotNone(result["backup"])
        self.assertTrue(result["notes"])
        backup = Path(result["backup"])
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_text(encoding="utf-8"), "{ not json")
        self.assertEqual(self._read_target()["email_provider"], "duckmail")

    def test_json_array_is_treated_as_broken(self):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("[1, 2, 3]", encoding="utf-8")

        result = self._seed(env={})

        self.assertEqual(result["action"], "recreated")
        self.assertIsNotNone(result["backup"])

    def test_target_directory_raises(self):
        self.target.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(seed.SeedError):
            self._seed(env={})

    def test_missing_template_raises_when_target_absent(self):
        with self.assertRaises(seed.SeedError):
            seed.seed_config(self.target, self.tmp / "nope.json", env={})

    def test_missing_template_tolerated_when_target_exists(self):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text(json.dumps({"email_provider": "vmail"}), encoding="utf-8")

        result = seed.seed_config(
            self.target, self.tmp / "nope.json", env={}, apply_container_defaults=False
        )

        self.assertEqual(result["action"], "unchanged")
        self.assertEqual(self._read_target()["email_provider"], "vmail")

    def test_broken_template_raises(self):
        self.template.write_text("{ broken", encoding="utf-8")

        with self.assertRaises(seed.SeedError):
            self._seed(env={})

    def test_no_tmp_file_left_behind(self):
        self._seed(env={})

        leftovers = sorted(p.name for p in self.target.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [])


class SeedConfigCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.template = self.tmp / "config.example.json"
        self.template.write_text(json.dumps(TEMPLATE, indent=2), encoding="utf-8")
        self.target = self.tmp / "config.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_cli_creates_config(self):
        rc = seed.main(["--target", str(self.target), "--template", str(self.template), "--quiet"])

        self.assertEqual(rc, 0)
        data = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertFalse(data["browser_headless"])

    def test_cli_no_container_defaults(self):
        rc = seed.main(
            [
                "--target",
                str(self.target),
                "--template",
                str(self.template),
                "--no-container-defaults",
                "--quiet",
            ]
        )

        self.assertEqual(rc, 0)
        data = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertTrue(data["browser_headless"])
        self.assertEqual(data["cpa_auth_dir"], "cpa_auth")

    def test_cli_reports_failure_without_raising(self):
        self.target.mkdir(parents=True, exist_ok=True)
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            rc = seed.main(
                ["--target", str(self.target), "--template", str(self.template), "--quiet"]
            )

        self.assertEqual(rc, 1)
        self.assertIn(seed.LOG_PREFIX, stderr.getvalue())

    def test_cli_defaults_come_from_environment(self):
        env = {
            "GROK_CONFIG_FILE": str(self.target),
            "GROK_CONFIG_TEMPLATE": str(self.template),
        }
        old = {key: os.environ.get(key) for key in env}
        os.environ.update(env)
        try:
            rc = seed.main(["--quiet"])
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(rc, 0)
        self.assertTrue(self.target.is_file())


class LauncherScriptTests(unittest.TestCase):
    """一键启动脚本与容器入口都调用同一份 seed_config.py，这里固定住共用约定。"""

    LOCAL_LAUNCHERS = (
        "scripts/_lib.sh",
        "scripts/start-windows.ps1",
    )

    def _read(self, relative):
        path = PROJECT_ROOT / relative
        self.assertTrue(path.is_file(), f"缺少文件: {relative}")
        return path.read_text(encoding="utf-8-sig")

    def test_all_launchers_exist(self):
        for relative in (
            "scripts/_lib.sh",
            "scripts/start-linux.sh",
            "scripts/start-macos.sh",
            "scripts/start-windows.ps1",
            "scripts/start-windows.bat",
            "docker/entrypoint.sh",
        ):
            self.assertTrue((PROJECT_ROOT / relative).is_file(), f"缺少文件: {relative}")

    def test_shell_launchers_are_executable(self):
        for relative in ("scripts/start-linux.sh", "scripts/start-macos.sh", "docker/entrypoint.sh"):
            mode = (PROJECT_ROOT / relative).stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR, f"{relative} 缺少可执行位")

    def test_local_launchers_disable_container_defaults(self):
        # 容器专用值（有头浏览器、outlook-email 服务名）不能写进本机 config.json。
        for relative in self.LOCAL_LAUNCHERS:
            text = self._read(relative)
            self.assertIn("seed_config.py", text, relative)
            self.assertIn("--no-container-defaults", text, relative)

    def test_container_entrypoint_keeps_container_defaults(self):
        text = self._read("docker/entrypoint.sh")
        self.assertIn("scripts/seed_config.py", text)
        self.assertNotIn("--no-container-defaults", text)

    def test_image_ships_the_shared_seeder(self):
        self.assertIn("scripts/seed_config.py", self._read("Dockerfile"))

    def test_windows_script_keeps_utf8_bom_and_safe_param_name(self):
        raw = (PROJECT_ROOT / "scripts" / "start-windows.ps1").read_bytes()
        # Windows PowerShell 5.1 无 BOM 时按系统 ANSI 代码页解码，中文提示会变乱码。
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "start-windows.ps1 需要 UTF-8 BOM")
        text = raw.decode("utf-8-sig")
        # $Host 是 PowerShell 保留变量，参数只能叫 BindHost。
        self.assertIn("$BindHost", text)
        self.assertNotIn("[string]$Host", text)


if __name__ == "__main__":
    unittest.main()
