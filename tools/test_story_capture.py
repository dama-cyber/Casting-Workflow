# -*- coding: utf-8 -*-
"""story_capture 轻量烟测（无网络、无 LLM）。运行: python tools/test_story_capture.py

覆盖：
  1. 模块可导入
  2. --print-cmd 干跑可解析并返回 0（不实际执行 node，不触网）
  3. node 缺失时清晰降级返回 1，不崩溃
  4. 缺 --platform 时 argparse 报错（SystemExit，不崩溃）

设计约束：绝不触网、绝不启动 Chrome；仅校验参数解析与运行时探测降级路径。
"""
import os
import sys

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)

from story_capture import capture

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


# 1) --print-cmd 干跑：仅打印命令，不执行 node，不触网
rc = capture(["--platform", "qidian", "--print-cmd"])
_assert(rc == 0, "capture --print-cmd 干跑返回 0（未实际执行）")

# 2) node 缺失清晰降级（返回 1，不抛异常）
rc2 = capture(["--platform", "qidian", "--node", "nonexistent_node_bin_xyz"])
_assert(rc2 == 1, "node 缺失时 capture 返回 1（清晰降级，未崩溃）")

# 3) 缺 --platform → argparse 报错（SystemExit，未崩溃）
try:
    capture([])
    _assert(False, "缺 --platform 应触发 argparse 报错")
except SystemExit:
    _assert(True, "缺 --platform 时 capture 解析报错（SystemExit，未崩溃）")

print(f"\n===== story_capture 烟测: {PASS} 通过 / {FAIL} 失败 =====")
sys.exit(1 if FAIL else 0)
