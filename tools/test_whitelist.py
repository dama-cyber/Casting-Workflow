# -*- coding: utf-8 -*-
"""白名单词表豁免（核心 IP 质量扩展 · 方向 G）单元自测。

覆盖：
  1. load_whitelist 解析（注释/空行忽略 + 小写化）
  2. _check_banned_hard 无白名单 → 全保留；有白名单 → 命中词豁免，其余保留
  3. issues 含 matched 字段
  4. report_ai_flavor 端到端：白名单仅影响 banned issues，不碰软信号
  5. audit.py 集成：monkeypatch _WHITELIST 验证禁用模板被豁免
红线：默认空白名单 = 零行为变更（不误杀任何现有检测）。
"""
import os
import sys
import tempfile

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)

from anti_ai_reporter import load_whitelist, _check_banned_hard, report_ai_flavor
import audit  # noqa: E402

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


# 1) load_whitelist 解析
tf = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False)
tf.write("# comment\n\n眼中闪过\n瞳孔收缩\n命运齿轮\n")
tf.close()
wl = load_whitelist(tf.name)
_assert("眼中闪过" in wl and "瞳孔收缩" in wl and "命运齿轮" in wl, "load_whitelist 解析+小写")
_assert(len(wl) == 3, f"load_whitelist 忽略注释/空行（实际 {len(wl)}）")
os.unlink(tf.name)

# 2) _check_banned_hard 无白名单 → 全保留
banned = {
    "banned_punctuation": ["；"],
    "banned_patterns": ["不是[^。！？\\n]{0,40}而是"],
    "banned_templates": ["眼中闪过"],
}
text = "他眼中闪过一丝决然。不是朋友而是敌人；"
iss = _check_banned_hard(text, banned, whitelist=set())
_assert(len(iss) == 3, f"无白名单保留3项（实际 {len(iss)}）")
_assert(any(i["value"] == "眼中闪过" for i in iss), "无白名单保留模板")

# 3) _check_banned_hard 有白名单 → 模板豁免，其余保留
iss2 = _check_banned_hard(text, banned, whitelist={"眼中闪过"})
_assert(len(iss2) == 2, f"白名单豁免模板后剩2项（实际 {len(iss2)}）")
_assert(all(i["value"] != "眼中闪过" for i in iss2), "白名单已豁免眼中闪过")
_assert(any(i["value"] == "；" for i in iss2), "标点仍保留")
_assert(any(i["value"] == "不是[^。！？\\n]{0,40}而是" for i in iss2), "正则仍保留")
_assert(all("matched" in i for i in iss2), "issues 含 matched 字段")

# 4) report_ai_flavor 端到端
r_no = report_ai_flavor(text, whitelist=set())
r_yes = report_ai_flavor(text, whitelist={"眼中闪过"})
_no = [i for i in r_no["issues"] if i["value"] == "眼中闪过"]
_yes = [i for i in r_yes["issues"] if i["value"] == "眼中闪过"]
_assert(len(_no) == 1, "report 无白名单含眼中闪过")
_assert(len(_yes) == 0, "report 白名单豁免眼中闪过")
_assert(r_no["ai_flavor_alarm"] == r_yes["ai_flavor_alarm"], "白名单仅影响 issues 不影响软信号")

# 5) audit.py 集成：monkeypatch _WHITELIST（audit_story 返回 (str, fail) 元组）
sample = "她眼中闪过一抹冷光。故事就这样开始了。"
audit._WHITELIST = set()
res_empty_str = audit.audit_story(sample)[0]
_assert("禁用模板: 眼中闪过" in res_empty_str, "audit 默认空白名单仍报禁用模板")
audit._WHITELIST = {"眼中闪过"}
res_wl_str = audit.audit_story(sample)[0]
_assert("禁用模板: 眼中闪过" not in res_wl_str, "audit 白名单豁免禁用模板")

print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
sys.exit(1 if FAIL else 0)
