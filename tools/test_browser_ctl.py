# -*- coding: utf-8 -*-
"""browser_ctl 轻量烟测（无网络、无 LLM）。运行: python tools/test_browser_ctl.py

覆盖：
  1. 模块可导入
  2. browse --print-cmd 干跑返回 0（不实际 curl，不触网）
  3. node 缺失（launch 默认）清晰降级返回 1，不崩溃
  4. curl 缺失（browse）清晰降级返回 1，不崩溃

设计约束：绝不触网、绝不启动 Chrome；仅校验参数解析与运行时探测降级路径。
"""
import os
import sys

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)

from browser_ctl import launch_cdp

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


# 1) browse --print-cmd 干跑：仅打印命令，不实际 curl，不触网
rc = launch_cdp(["--action", "browse", "--print-cmd"])
_assert(rc == 0, "browser_ctl browse --print-cmd 干跑返回 0（未实际执行）")

# 2) node 缺失（launch 默认）清晰降级返回 1
rc2 = launch_cdp(["--node", "nonexistent_node_bin_xyz"])
_assert(rc2 == 1, "node 缺失时 launch_cdp 返回 1（清晰降级，未崩溃）")

# 3) curl 缺失（browse）清晰降级返回 1
rc3 = launch_cdp(["--action", "browse", "--curl", "nonexistent_curl_bin_xyz"])
_assert(rc3 == 1, "curl 缺失时 browse 返回 1（清晰降级，未崩溃）")

print(f"\n===== browser_ctl 烟测: {PASS} 通过 / {FAIL} 失败 =====")
sys.exit(1 if FAIL else 0)
