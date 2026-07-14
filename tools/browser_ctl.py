#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
browser_ctl.py — Chrome CDP 浏览器操控封装（无 LLM，依赖 Node + curl）

封装 tools/browser_scripts/setup-cdp-chrome.js（准备带 CDP 调试的 Chrome 环境），
并提供 browse() 通过 CDP HTTP 接口列举已打开页面（无 LLM，仅本地 HTTP）。

用法:
    python tools/browser_ctl.py                            # 启动 CDP Chrome（端口 9222）
    python tools/browser_ctl.py --port 9222 --detect-only  # 仅探测 CDP 状态
    python tools/browser_ctl.py --action browse            # 列举 CDP 页面

设计约束:
    - 零 LLM；纯命令行编排。
    - 依赖 Node（setup-cdp-chrome.js）与可选 curl（browse）；缺失时清晰报错退出。
    - 不改写脚本逻辑（脚本位于 tools/browser_scripts/，去品牌路径）。
"""

import argparse
import os
import shutil
import subprocess
import sys

THIS = os.path.dirname(os.path.abspath(__file__))
BROWSER_SCRIPTS_DIR = os.path.join(THIS, "browser_scripts")
SETUP_SCRIPT = os.path.join(BROWSER_SCRIPTS_DIR, "setup-cdp-chrome.js")

DEFAULT_PORT = 9222


def _has_node(node_bin="node"):
    """返回 node 是否可用（缺失时清晰降级）。"""
    return shutil.which(node_bin) is not None


def _has_curl(curl_bin="curl"):
    """返回 curl 是否可用（缺失时清晰降级）。"""
    return shutil.which(curl_bin) is not None


def launch_cdp(argv=None):
    """准备/复用 Chrome CDP 环境（run_pipeline --browser / --with browser 调用）。"""
    if argv is None:
        argv = sys.argv[1:]

    ap = argparse.ArgumentParser(
        description="Chrome CDP 浏览器操控封装（无 LLM）",
        allow_abbrev=False,
    )
    ap.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help="CDP 端口（默认 9222）",
    )
    ap.add_argument(
        "--action", choices=["launch", "browse"], default="launch",
        help="launch=准备 CDP Chrome；browse=列举 CDP 页面",
    )
    ap.add_argument("--detect-only", action="store_true", help="仅探测 CDP 状态")
    ap.add_argument(
        "--yes", action="store_true",
        help="跳过交互确认（同意杀现有 Chrome）",
    )
    ap.add_argument("--reset", action="store_true", help="重置 debug profile 后重启")
    ap.add_argument("--profile", default=None, help="Chrome profile 名（默认 Default）")
    ap.add_argument("--dry-run", action="store_true", help="只打印操作不执行")
    ap.add_argument("--print-cmd", action="store_true", help="仅打印命令不执行（browse 透传）")
    ap.add_argument("--node", default="node", help="node 可执行文件（默认 node）")
    ap.add_argument("--curl", default="curl", help="curl 可执行文件（browse 透传）")
    args = ap.parse_args(argv)

    # browse 子动作复用独立入口
    if args.action == "browse":
        return browse(
            ["--port", str(args.port), "--curl", args.curl]
            + (["--print-cmd"] if args.print_cmd else [])
        )

    if not _has_node(args.node):
        print(
            f"[browser_ctl] 未找到 Node 运行时（{args.node}）。"
            f"CDP Chrome 准备依赖 setup-cdp-chrome.js，请先安装 Node.js。",
            file=sys.stderr,
        )
        return 1
    if not os.path.isfile(SETUP_SCRIPT):
        print(f"[browser_ctl] 脚本缺失: {SETUP_SCRIPT}", file=sys.stderr)
        return 1

    cmd = [args.node, SETUP_SCRIPT, str(args.port)]
    if args.detect_only:
        cmd.append("--detect-only")
    if args.yes:
        cmd.append("--yes")
    if args.reset:
        cmd.append("--reset")
    if args.dry_run:
        cmd.append("--dry-run")
    if args.profile:
        cmd += ["--profile", args.profile]

    print(f"[browser_ctl] 准备 CDP Chrome（port={args.port}）")
    try:
        rc = subprocess.call(cmd)
    except Exception as e:  # pragma: no cover - 防御性
        print(f"[browser_ctl] 执行失败: {e}", file=sys.stderr)
        return 1
    if rc != 0:
        print(
            f"[browser_ctl] setup-cdp-chrome.js 返回非零退出码: {rc}",
            file=sys.stderr,
        )
    return rc


def browse(argv=None):
    """通过 CDP HTTP 接口列举已打开页面（无 LLM，仅本地 HTTP）。"""
    if argv is None:
        argv = sys.argv[1:]

    ap = argparse.ArgumentParser(
        description="列举 Chrome CDP 已打开页面", allow_abbrev=False,
    )
    ap.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help="CDP 端口（默认 9222）",
    )
    ap.add_argument("--curl", default="curl", help="curl 可执行文件（默认 curl）")
    ap.add_argument(
        "--print-cmd", action="store_true",
        help="仅打印命令不执行",
    )
    args = ap.parse_args(argv)

    if not _has_curl(args.curl):
        print(
            f"[browser_ctl] 未找到 curl 运行时（{args.curl}）。"
            f"browse 依赖 curl 访问 CDP HTTP 接口，请先安装 curl。",
            file=sys.stderr,
        )
        return 1

    url = f"http://127.0.0.1:{args.port}/json"
    cmd = [args.curl, "-fsS", "--max-time", "5", url]
    if args.print_cmd:
        print(" ".join(cmd))
        return 0
    print(f"[browser_ctl] 查询 CDP 页面: {url}")
    try:
        rc = subprocess.call(cmd)
    except Exception as e:  # pragma: no cover - 防御性
        print(f"[browser_ctl] 执行失败: {e}", file=sys.stderr)
        return 1
    return rc


# 兼容别名：旧调用 browser_ctl.main(...) 仍可用
main = launch_cdp


if __name__ == "__main__":
    sys.exit(main())
