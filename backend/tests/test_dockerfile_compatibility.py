"""Dockerfile 必须能被旧版构建器（无 buildx / BuildKit 关闭）直接构建。

只装了发行版 docker.io 的宿主机没有 buildx 插件，docker compose build 会退回
旧版构建器（输出 "Sending build context to Docker daemon" + "Step N/M"）。
此时 BuildKit 专属语法不是降级而是硬失败：
    the --mount option requires BuildKit.
而且 compose 的这条退路走的是 classic build API，`DOCKER_BUILDKIT=1` 也救不回来，
所以镜像本身必须保持旧语法可构建。
"""

import os
import re
import unittest

from backend.shared.paths import PROJECT_ROOT

DOCKERFILE = PROJECT_ROOT / "Dockerfile"
ENTRYPOINT = PROJECT_ROOT / "docker" / "entrypoint.sh"

BUILDKIT_ONLY = (
    (r"^\s*(?:RUN|COPY|ADD)\s.*--mount=", "RUN/COPY --mount=（缓存或绑定挂载）"),
    (r"^\s*(?:COPY|ADD)\s.*--chmod=", "COPY --chmod="),
    (r"^\s*(?:COPY|ADD)\s.*--link(?:\s|=|$)", "COPY --link"),
    (r"^\s*RUN\s.*<<[-~]?['\"]?[A-Za-z_]", "RUN heredoc（<<EOF）"),
    (r"^#\s*syntax\s*=", "# syntax= 前端指令（宣告依赖 BuildKit 前端）"),
)


class DockerfileLegacyBuilderTests(unittest.TestCase):
    def setUp(self):
        self.text = DOCKERFILE.read_text(encoding="utf-8")

    def test_no_buildkit_only_syntax(self):
        for pattern, label in BUILDKIT_ONLY:
            hits = [
                line.strip()
                for line in self.text.splitlines()
                if re.search(pattern, line)
            ]
            self.assertEqual(
                hits,
                [],
                f"Dockerfile 用了 BuildKit 专属语法 {label}，"
                f"没有 buildx 的宿主机会构建失败: {hits}",
            )

    def test_entrypoint_gets_exec_bit_without_chmod_flag(self):
        # 去掉 COPY --chmod=755 之后，可执行位只剩两个来源：仓库里的文件权限
        # 和构建时显式 chmod。少了它 ENTRYPOINT 会以 permission denied 起不来。
        self.assertIn("chmod 755 /app/docker/entrypoint.sh", self.text)
        self.assertTrue(
            os.access(ENTRYPOINT, os.X_OK),
            f"{ENTRYPOINT} 需要保留可执行位",
        )

    def test_multi_stage_layout_is_intact(self):
        for stage in ("frontend-builder", "python-builder", "runtime"):
            self.assertIn(f"AS {stage}", self.text)
        # 多阶段和 COPY --from / --chown 是旧版构建器也支持的，不受本约束影响。
        self.assertIn("COPY --chown=app:app --from=python-builder", self.text)


if __name__ == "__main__":
    unittest.main()
