# -*- coding: utf-8 -*-
"""退化与泄漏检测引擎 单元自测（核心 IP 质量扩展 · 方向 B 联调回归子集）。

验证：
  - report_degeneration 各信号触发/豁免正确（tier1 硬证据 / tier2 引号豁免 /
    复读 / 截断 / 占位符拒绝语 / 未完待续去重）
  - 合并弱信号层传入 triple_cross_judge 绝不翻 FAIL（红线）
  - 仅依赖标准库（零新增依赖）

用法:
    python tools/test_deslop_reporter.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deslop_reporter import report_degeneration, merge_ai_flavor_signals, load_degeneration_rules
from humanity_scorer import triple_cross_judge


def _assert(cond, msg):
    if not cond:
        raise AssertionError("FAIL: " + msg)
    print("PASS: " + msg)


# 0. 版本标签（去品牌：deslop-v1，与 T04 对齐）
_rules = load_degeneration_rules()
_assert(_rules.get("version") == "deslop-v1", "退化检测版本标签为 deslop-v1（去品牌，与 T04 对齐）")


# 1. 干净文本：无告警、无硬证据
clean = "苏暖推开门。院子里静悄悄的。她不知道接下来会发生什么。故事在此落幕。"
r = report_degeneration(clean)
_assert(not r["degeneration_alarm"], "clean -> 无退化告警")
_assert(r["issues"] == [], "clean -> 无硬证据 issue")

# 2. tier1 工程词泄漏（正文逃逸，不豁免，含「」内仍命中）
leak = "细纲写好了。她翻出卷纲。「细纲」也提到了。"
r = report_degeneration(leak)
_assert(any(h["term"] == "细纲" for h in r["engineering_leak"]["tier1"]["hits"]),
        "tier1 细纲命中（含引号内不豁免）")
_assert(r["engineering_leak"]["tier1"]["level"] == "ISSUE", "tier1 level=ISSUE")
_assert(len(r["issues"]) >= 1, "tier1 进全局 issues")

# 3. tier2 引号内豁免 / 明文命中
t2_q = "「本章我们复盘一下」他说完就走了。"
r = report_degeneration(t2_q)
_assert(r["engineering_leak"]["tier1"]["hits"] == [], "tier2 样本无 tier1")
_assert(all("本章" != h["term"] for h in r["engineering_leak"]["tier2"]["hits"]),
        "tier2 引号内「本章」豁免（masked 后不命中）")
t2_p = "本章讲了一个故事。上一章埋了伏笔。"
r = report_degeneration(t2_p)
_assert(len(r["engineering_leak"]["tier2"]["hits"]) >= 1, "tier2 明文命中")

# 4. 复读检测（长句可见字≥12，重复≥3）
long_rep = "月光洒在青石板上泛着冷冷的光。" * 3
r = report_degeneration(long_rep)
_assert(r["repeat"]["long_sentence"] is not None, "长句复读触发")

# 5. 截断检测（末行无合法结尾 / 合法结尾不触发）
r = report_degeneration("他终于明白一切真相")
_assert(r["truncate"]["violated"], "截断触发（末字符非句末标点）")
r = report_degeneration("他终于明白一切真相。")
_assert(not r["truncate"]["violated"], "句末句号不触发截断")

# 6. 占位符 / 拒绝语（进 issues）；未完待续（第六节已管，去重不进 issues）
ph = "作为一个AI我无法继续写下去了。"
r = report_degeneration(ph)
_assert(any("placeholder_refusal" in i["type"] for i in r["issues"]),
        "AI 拒绝语进 issues")
wq = "故事到此为止未完待续"
r = report_degeneration(wq)
_assert(r["degeneration_alarm"], "未完待续触发退化告警")
_assert(not any("未完待续" in i["detail"] for i in r["issues"]),
        "未完待续被第六节去重，不重复进 issues")

# 7. 合并弱信号层（真实 _ai schema：alarm_severity 为字符串 "WARN"，severity 为浮点）
base = ("林霜推开木门。院子里的老槐树落了半地叶子。她蹲下身，指尖触到冰凉的泥土。"
        "远处传来一声犬吠。故事就在这样的黄昏里收了尾。")
leak_trunc = "细纲写好他终于明白一切真相"  # 制造退化双告警
_deg = report_degeneration(leak_trunc)
_assert(_deg["degeneration_alarm"], "_deg 退化告警为真（供合并测试）")
# 真实 report_ai_flavor 返回：alarm_severity 字符串、severity 浮点
_real_ai = {"ai_flavor_alarm": True, "alarm_severity": "WARN",
            "severity": 0.5, "alarm_detail": "qiaomu:abstract高密度"}
merged = merge_ai_flavor_signals(_real_ai, _deg)
_assert(merged["ai_flavor_alarm"] is True, "合并层 ai_flavor_alarm=True")
_assert(isinstance(merged["severity"], float), "合并 severity 为浮点（非字符串 WARN）")
_assert(0.0 <= merged["severity"] <= 1.0, "合并 severity 在 0-1")
tc = triple_cross_judge(base, ai_flavor=merged)
_assert(tc["verdict"] != "FAIL", f"合并弱信号绝不翻 FAIL（verdict={tc['verdict']}）")
_assert(tc["layers"].get("ai_flavor", {}).get("verdict") == "WARN", "弱信号层恒 WARN")
_assert(tc["layers"]["ai_flavor"]["confidence"] <= 0.5, "弱信号 confidence 封顶 0.5")
_assert("deslop:" in merged["alarm_detail"], "合并弱信号 detail 含 deslop: 标签（去品牌）")

# 7b. AI_FLAVOR 关闭（_ai=None）时合并仅含退化
merged2 = merge_ai_flavor_signals(None, _deg)
_assert(merged2["ai_flavor_alarm"] is True, "_ai=None 时仍含退化告警")

print("\n全部自测通过 ✅")
