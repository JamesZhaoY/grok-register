#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""准备 config.json，容器入口与本机启动脚本共用。

首次运行按 config.example.json 生成配置，之后只补齐模板新增的键，不覆盖用户
已填写的值；文件损坏时先备份再重建，避免容器因 JSON 解析失败反复重启。
容器内额外强制写入有头浏览器与挂载卷内的授权目录（--no-container-defaults 关闭）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

DEFAULT_TARGET = "/app/data/config.json"
DEFAULT_TEMPLATE = "/app/config.example.json"
DEFAULT_OUTLOOKEMAIL_API_BASE = "http://outlook-email:5000"
LOG_PREFIX = "[config]"


class SeedError(RuntimeError):
    """配置准备失败，调用方应立即退出并给出可读原因。"""


def container_defaults(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """容器内必须生效的值：无桌面环境靠 Xvfb 跑有头浏览器，授权目录落在挂载卷。"""
    environ = os.environ if env is None else env
    api_base = (environ.get("GROK_OUTLOOKEMAIL_API_BASE") or "").strip()
    return {
        "browser_headless": False,
        "cpa_auth_dir": "data/cpa_auth",
        "grok2api_auth_dir": "data/grok2api_auth",
        "outlookemail_api_base": api_base or DEFAULT_OUTLOOKEMAIL_API_BASE,
    }


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("配置内容不是 JSON 对象")
    return data


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp.replace(path)


def _backup(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    backup = path.with_name(f"{path.name}.broken-{stamp}")
    index = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.broken-{stamp}-{index}")
        index += 1
    path.replace(backup)
    return backup


def seed_config(
    target: os.PathLike | str,
    template: os.PathLike | str,
    env: Optional[Mapping[str, str]] = None,
    apply_container_defaults: bool = True,
) -> Dict[str, Any]:
    """确保 target 存在且包含模板里的全部键，返回本次动作摘要。"""
    target_path = Path(target)
    template_path = Path(template)
    notes: List[str] = []

    if target_path.is_dir():
        raise SeedError(f"配置路径是目录: {target_path}（请删除该目录或改用 GROK_CONFIG_FILE）")

    template_data: Dict[str, Any] = {}
    if template_path.is_file():
        try:
            template_data = _read_json(template_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise SeedError(f"配置模板不可用: {template_path}（{exc}）") from exc
    elif not target_path.is_file():
        raise SeedError(f"缺少配置模板: {template_path}")

    current: Dict[str, Any] = {}
    backup: Optional[Path] = None
    fresh = True
    if target_path.is_file():
        try:
            current = _read_json(target_path)
            fresh = False
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            backup = _backup(target_path)
            notes.append(f"配置解析失败（{exc}），已备份为 {backup.name} 并按模板重建")

    merged = dict(current)
    added = [key for key in template_data if key not in merged]
    for key in added:
        merged[key] = template_data[key]

    forced = container_defaults(env) if apply_container_defaults else {}
    if fresh:
        merged.update(forced)
    else:
        for key, value in forced.items():
            merged.setdefault(key, value)

    changed = fresh or merged != current
    if changed:
        try:
            _write_json(target_path, merged)
        except OSError as exc:
            raise SeedError(f"写入配置失败: {target_path}（{exc}）") from exc

    if fresh:
        action = "recreated" if backup else "created"
    else:
        action = "merged" if changed else "unchanged"
    return {
        "action": action,
        "path": str(target_path),
        "added": added,
        "backup": str(backup) if backup else None,
        "changed": changed,
        "keys": len(merged),
        "notes": notes,
    }


def _describe(result: Dict[str, Any]) -> str:
    action = result["action"]
    if action in ("created", "recreated"):
        verb = "已生成" if action == "created" else "已重建"
        return f"{verb}配置: {result['path']}（{result['keys']} 项）"
    if action == "merged":
        added = result["added"]
        preview = "、".join(added[:8]) + ("…" if len(added) > 8 else "")
        return f"配置已补齐 {len(added)} 个新增键: {preview}" if added else "配置已规范化写回"
    return f"配置已存在，无需变更: {result['path']}"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="生成或补齐 config.json")
    parser.add_argument("--target", default=os.environ.get("GROK_CONFIG_FILE") or DEFAULT_TARGET)
    parser.add_argument(
        "--template", default=os.environ.get("GROK_CONFIG_TEMPLATE") or DEFAULT_TEMPLATE
    )
    parser.add_argument(
        "--no-container-defaults",
        dest="container_defaults",
        action="store_false",
        help="本机运行时使用：不写入容器专用默认值",
    )
    parser.add_argument("--quiet", action="store_true", help="只在出错时输出")
    args = parser.parse_args(argv)

    try:
        result = seed_config(
            args.target, args.template, apply_container_defaults=args.container_defaults
        )
    except SeedError as exc:
        print(f"{LOG_PREFIX} {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        for note in result["notes"]:
            print(f"{LOG_PREFIX} {note}")
        print(f"{LOG_PREFIX} {_describe(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
