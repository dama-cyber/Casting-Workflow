# -*- coding: utf-8 -*-
"""cover_gen 轻量烟测（无网络、无 LLM）。运行: python tools/test_cover_gen.py

覆盖：
  1. 模块可导入
  2. --print-env 干跑可解析并返回 0（不实际执行 bash，不触网）
  3. bash 缺失时清晰降级返回 1，不崩溃
  4. 必填项缺失时清晰报错返回 1（不执行、不崩溃）

设计约束：绝不触网、绝不调用图像 API；仅校验参数解析与运行时探测降级路径。
"""
import os
import sys

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)

from cover_gen import generate_cover

PASS = 0
FAIL = 0


def _assert(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[OK] {msg}")
    else:
        FAIL += 1
        print(f"[FAIL] {msg}")


# 1) --print-env 干跑：仅打印环境变量，不执行 bash，不触网
rc = generate_cover([
    "--print-env",
    "--book-dir", "./covers/书名",
    "--prompt", "a book cover",
    "--api-key", "sk-test",
])
_assert(rc == 0, "cover_gen --print-env 干跑返回 0（未实际执行）")

# 2) bash 缺失清晰降级（返回 1，不抛异常）
rc2 = generate_cover([
    "--bash", "nonexistent_bash_bin_xyz",
    "--book-dir", "./covers/书名",
    "--prompt", "a book cover",
    "--api-key", "sk-test",
])
_assert(rc2 == 1, "bash 缺失时 cover_gen 返回 1（清晰降级，未崩溃）")

# 3) 必填项缺失 → 清晰报错返回 1（不执行、不崩溃）
rc3 = generate_cover(["--print-env"])
_assert(rc3 == 1, "缺必填项时 cover_gen 返回 1（清晰报错）")

print(f"\n===== cover_gen 烟测: {PASS} 通过 / {FAIL} 失败 =====")
sys.exit(1 if FAIL else 0)
