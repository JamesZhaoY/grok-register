"""守住 PEP 765：finally 里不允许 break / continue / return。

Python 3.14 会对这种写法发 SyntaxWarning，启动日志里会刷一堆告警；
更要紧的是它会吞掉正在传播的异常，让 run_registration 的外层
`except Exception` 永远收不到 except 分支里抛出的错误。
"""

from __future__ import annotations

import ast
import unittest

from backend.shared.paths import PROJECT_ROOT

# 只扫仓库自己的源码，跳过虚拟环境与依赖产物
SCAN_DIRS = ("backend", "scripts", "docker")
SKIP_PARTS = {".venv", "venv", "node_modules", "__pycache__", "dist", "build"}


def _iter_sources():
    for name in SCAN_DIRS:
        root = PROJECT_ROOT / name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if SKIP_PARTS & set(path.parts):
                continue
            yield path


SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
LOOP_NODES = (ast.For, ast.AsyncFor, ast.While)


def _escaping_jumps(node: ast.AST, in_loop: bool, sites: list) -> None:
    """收集会跳出当前 finally 的语句。

    嵌套的 def / class 自带作用域，其中的 return 与外层 finally 无关；
    finally 里自己写的循环，其 break / continue 也只作用于该循环，都不算命中。
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, SCOPE_NODES):
            continue
        if isinstance(child, (ast.Break, ast.Continue)):
            if not in_loop:
                sites.append((child.lineno, type(child).__name__.lower()))
            continue
        if isinstance(child, ast.Return):
            sites.append((child.lineno, "return"))
            continue
        _escaping_jumps(child, in_loop or isinstance(child, LOOP_NODES), sites)


def _jump_sites(tree: ast.AST):
    """找出会从 finally 块跳走的 break / continue / return。"""
    sites: list = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for stmt in node.finalbody:
            if isinstance(stmt, SCOPE_NODES):
                continue
            if isinstance(stmt, (ast.Break, ast.Continue)):
                sites.append((stmt.lineno, type(stmt).__name__.lower()))
                continue
            if isinstance(stmt, ast.Return):
                sites.append((stmt.lineno, "return"))
                continue
            _escaping_jumps(stmt, isinstance(stmt, LOOP_NODES), sites)
    return sites


class FinallyControlFlowTests(unittest.TestCase):
    def test_no_jump_statements_inside_finally_blocks(self):
        offenders = []
        scanned = 0
        for path in _iter_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            scanned += 1
            for lineno, kind in _jump_sites(tree):
                rel = path.relative_to(PROJECT_ROOT)
                offenders.append(f"{rel}:{lineno} 的 finally 里有 {kind}")

        self.assertGreater(scanned, 0, "没有扫到任何 Python 源码，检查 SCAN_DIRS")
        self.assertEqual(
            offenders,
            [],
            "finally 内的跳转会吞掉异常并触发 SyntaxWarning（PEP 765）：\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
