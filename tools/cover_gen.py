#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cover_gen.py — 封面生成封装（无 LLM，依赖 generate-cover.sh + 图像 API）

封装 tools/cover_scripts/generate-cover.sh：通过环境变量传入 GPT-Image 兼容
API 的 key / 提示词 / 输出目录，调用 bash 脚本生成封面 PNG。

用法:
    GPT_IMAGE_API_KEY=xxx PROMPT="..." BOOK_DIR=./covers/书名 \\
        python tools/cover_gen.py
    python tools/cover_gen.py --book-dir ./covers/书名 --prompt "..." --api-key xxx

设计约束:
    - 零 LLM；纯命令行编排。
    - 依赖 bash 运行时与 generate-cover.sh；缺失时清晰报错退出。
    - 不改写脚本逻辑（脚本位于 tools/cover_scripts/，去品牌路径）。
"""

import argparse
import os
import shutil
import subprocess
import sys

THIS = os.path.dirname(os.path.abspath(__file__))
COVER_SCRIPTS_DIR = os.path.join(THIS, "cover_scripts")
COVER_SCRIPT = os.path.join(COVER_SCRIPTS_DIR, "generate-cover.sh")

# 脚本内部必填项（缺失时由本封装提前拦截，给出清晰报错）
REQUIRED_KEYS = ("BOOK_DIR", "PROMPT", "GPT_IMAGE_API_KEY")


def _has_bash(bash_bin="bash"):
    """返回 bash 是否可用（缺失时清晰降级）。"""
    return shutil.which(bash_bin) is not None


def generate_cover(argv=None):
    """封面生成入口（run_pipeline --cover / --with cover 调用）。返回进程退出码。"""
    if argv is None:
        argv = sys.argv[1:]

    ap = argparse.ArgumentParser(
        description="封面生成封装（无 LLM，依赖 generate-cover.sh + 图像 API）",
        allow_abbrev=False,
    )
    ap.add_argument(
        "--book-dir", default=os.environ.get("BOOK_DIR"),
        help="输出目录（对应脚本 BOOK_DIR；默认取环境变量 BOOK_DIR）",
    )
    ap.add_argument(
        "--prompt", default=os.environ.get("PROMPT"),
        help="完整英文提示词（对应脚本 PROMPT）",
    )
    ap.add_argument(
        "--api-key", default=os.environ.get("GPT_IMAGE_API_KEY"),
        help="图像 API key（对应 GPT_IMAGE_API_KEY）",
    )
    ap.add_argument(
        "--api-base-url", default=os.environ.get("GPT_IMAGE_BASE_URL"),
        help="图像 API base url（可选，默认 OpenAI 兼容）",
    )
    ap.add_argument(
        "--model", default=os.environ.get("GPT_IMAGE_MODEL"),
        help="图像模型名（可选）",
    )
    ap.add_argument(
        "--size", default=os.environ.get("GPT_IMAGE_SIZE"),
        help="生成尺寸，如 1024x1536（可选）",
    )
    ap.add_argument(
        "--ref-image", default=os.environ.get("REF_IMAGE"),
        help="参考图路径/URL（可选，走图生图）",
    )
    ap.add_argument(
        "--upload-size", default=os.environ.get("UPLOAD_SIZE"),
        help="平台上传尺寸，如 600x800（可选）",
    )
    ap.add_argument("--bash", default="bash", help="bash 可执行文件（默认 bash）")
    ap.add_argument(
        "--print-env", action="store_true",
        help="仅打印将注入的环境变量，不实际运行",
    )
    args = ap.parse_args(argv)

    if not _has_bash(args.bash):
        print(
            f"[cover_gen] 未找到 bash 运行时（{args.bash}）。"
            f"封面生成依赖 generate-cover.sh，请先安装 bash 后重试。",
            file=sys.stderr,
        )
        return 1

    if not os.path.isfile(COVER_SCRIPT):
        print(f"[cover_gen] 脚本缺失: {COVER_SCRIPT}", file=sys.stderr)
        return 1

    # 合并命令行参数与环境变量（命令行优先）
    env = dict(os.environ)
    if args.book_dir:
        env["BOOK_DIR"] = args.book_dir
    if args.prompt:
        env["PROMPT"] = args.prompt
    if args.api_key:
        env["GPT_IMAGE_API_KEY"] = args.api_key
    if args.api_base_url:
        env["GPT_IMAGE_BASE_URL"] = args.api_base_url
    if args.model:
        env["GPT_IMAGE_MODEL"] = args.model
    if args.size:
        env["GPT_IMAGE_SIZE"] = args.size
    if args.ref_image:
        env["REF_IMAGE"] = args.ref_image
    if args.upload_size:
        env["UPLOAD_SIZE"] = args.upload_size

    missing = [k for k in REQUIRED_KEYS if not env.get(k)]
    if missing:
        print(
            f"[cover_gen] 缺少必填项: {', '.join(missing)}"
            f"（可用 --book-dir/--prompt/--api-key 或环境变量传入）",
            file=sys.stderr,
        )
        return 1

    if args.print_env:
        for k in (
            "BOOK_DIR", "PROMPT", "GPT_IMAGE_API_KEY", "GPT_IMAGE_BASE_URL",
            "GPT_IMAGE_MODEL", "GPT_IMAGE_SIZE", "REF_IMAGE", "UPLOAD_SIZE",
        ):
            if env.get(k):
                val = env[k]
                if k == "GPT_IMAGE_API_KEY":
                    val = (val[:4] + "****") if len(val) > 4 else "****"
                print(f"  {k}={val}")
        return 0

    print(f"[cover_gen] 运行 generate-cover.sh (BOOK_DIR={env.get('BOOK_DIR')})")
    try:
        rc = subprocess.call([args.bash, COVER_SCRIPT], env=env)
    except Exception as e:  # pragma: no cover - 防御性
        print(f"[cover_gen] 执行失败: {e}", file=sys.stderr)
        return 1
    if rc != 0:
        print(
            f"[cover_gen] 脚本返回非零退出码: {rc}（请检查 API key / 网络）",
            file=sys.stderr,
        )
    return rc


# 兼容别名：旧调用 cover_gen.main(...) 仍可用
main = generate_cover


if __name__ == "__main__":
    sys.exit(main())
