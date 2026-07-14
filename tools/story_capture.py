#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
story_capture.py — 网文市场扫榜采集封装（无 LLM，依赖 Node 采集脚本）

封装 tools/scan_scripts/ 下的各平台采集脚本（起点 / 番茄 / 七猫 / 晋江 /
刺猬猫 / 点众 / 黑岩）。先确保 Chrome CDP 环境（见 tools/browser_scripts/
setup-cdp-chrome.js）已就绪，再运行对应平台脚本。

用法:
    python tools/story_capture.py --platform qidian --type hotsales
    python tools/story_capture.py --platform fanqie --channel 1 --type 2 --outdir ./scan_output
    python tools/story_capture.py --platform jjwxc --type 12 --top 15
    python tools/story_capture.py --platform heiyan --booklist

设计约束:
    - 零 LLM；纯命令行编排。
    - 仅依赖 Node 运行时；缺失时清晰报错退出。
    - 不改写任何采集脚本逻辑（脚本位于 tools/scan_scripts/，去品牌路径）。
    - 8G 安全、不触碰 corpus/。
"""

import argparse
import os
import shutil
import subprocess
import sys

THIS = os.path.dirname(os.path.abspath(__file__))
SCAN_SCRIPTS_DIR = os.path.join(THIS, "scan_scripts")

# 平台 → 采集脚本（tools/scan_scripts/ 下，去品牌路径）
PLATFORM_SCRIPTS = {
    "qidian": "qidian-rank-scraper.js",
    "fanqie": "fanqie-rank-scraper.js",
    "qimao": "qimao-rank-scraper.js",
    "jjwxc": "jjwxc-rank-scraper.js",
    "ciweimao": "ciweimao-rank-scraper.js",
    "dz": "dz-browse-scraper.js",
    "heiyan": "heiyan-booklist-scraper.js",
}

DEFAULT_PORT = 9222
DEFAULT_OUTDIR = os.path.join(os.path.dirname(THIS), "scan_output")


def _has_node(node_bin="node"):
    """返回 node 是否可用（缺失时清晰降级）。"""
    return shutil.which(node_bin) is not None


def capture(argv=None):
    """扫榜采集入口（run_pipeline --capture / --with capture 调用）。返回进程退出码。"""
    if argv is None:
        argv = sys.argv[1:]

    ap = argparse.ArgumentParser(
        description="网文市场扫榜采集封装（无 LLM，依赖 Node 采集脚本）",
        allow_abbrev=False,
    )
    ap.add_argument(
        "--platform", required=True, choices=sorted(PLATFORM_SCRIPTS.keys()),
        help="目标平台",
    )
    ap.add_argument(
        "--chrome-port", type=int, default=DEFAULT_PORT,
        help="Chrome CDP 端口（默认 9222）",
    )
    ap.add_argument(
        "--outdir", default=DEFAULT_OUTDIR,
        help="采集结果输出目录（默认 ../scan_output）",
    )
    ap.add_argument("--node", default="node", help="node 可执行文件（默认 node）")
    ap.add_argument(
        "--print-cmd", action="store_true",
        help="仅打印将要执行的命令，不实际运行",
    )
    # 平台专有参数（--type / --channel / --top / --mode / --list-only /
    # --detail-limit 等）透传给底层采集脚本
    args, extra = ap.parse_known_args(argv)

    if not _has_node(args.node):
        print(
            f"[story_capture] 未找到 Node 运行时（{args.node}）。"
            f"扫榜依赖 Node 采集脚本，请先安装 Node.js 后重试。",
            file=sys.stderr,
        )
        return 1

    script_name = PLATFORM_SCRIPTS.get(args.platform)
    script_path = os.path.join(SCAN_SCRIPTS_DIR, script_name)
    if not os.path.isfile(script_path):
        print(f"[story_capture] 采集脚本缺失: {script_path}", file=sys.stderr)
        return 1

    cmd = [args.node, script_path]
    # 仅当用户未显式传 --port / --outdir 时补默认，避免重复
    if "--port" not in extra:
        cmd += ["--port", str(args.chrome_port)]
    if "--outdir" not in extra:
        cmd += ["--outdir", args.outdir]
    cmd += extra

    if args.print_cmd:
        print(" ".join(cmd))
        return 0

    os.makedirs(args.outdir, exist_ok=True)
    print(
        f"[story_capture] 运行 {args.platform} 扫榜: node {script_name} "
        f"(port={args.chrome_port}, outdir={args.outdir})"
    )
    try:
        rc = subprocess.call(cmd)
    except Exception as e:  # pragma: no cover - 防御性
        print(f"[story_capture] 执行失败: {e}", file=sys.stderr)
        return 1
    if rc != 0:
        print(
            f"[story_capture] 采集脚本返回非零退出码: {rc}（请检查 Chrome CDP / "
            f"网络 / 平台登录态）",
            file=sys.stderr,
        )
    return rc


# 兼容别名：旧调用 story_capture.main(...) 仍可用
main = capture


if __name__ == "__main__":
    sys.exit(main())
