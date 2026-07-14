# -*- coding: utf-8 -*-
"""advisory_reporter 单元自测（核心 IP 质量扩展 · 方向 H）。运行: python tools/test_advisory_reporter.py"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from advisory_reporter import report_advisory, load_advisory_rules
from deslop_reporter import merge_ai_flavor_signals
from humanity_scorer import triple_cross_judge

_pass = 0
_fail = 0


def _assert(cond, msg):
    global _pass, _fail
    if cond:
        _pass += 1
        print("[OK] " + msg)
    else:
        _fail += 1
        print("[FAIL] " + msg)


rules = load_advisory_rules()

# 1. 正常叙事长文（有连接词、无套路）→ 不告警
normal = ("林霜推开木门。院子里的老槐树落了半地叶子。她蹲下身，指尖触到冰凉的泥土。"
          "远处传来一声犬吠。故事就在这样的黄昏里收了尾。他因为她不肯走，所以留了下来。"
          "风停了，雨也住了。日子一天天过去，镇上的人渐渐忘了那场大火。只有她还偶尔在梦里听见木门吱呀作响。") * 3
r0 = report_advisory(normal, rules)
_assert(not r0["advisory_alarm"], "正常叙事长文无 advisory 告警")

# 2. 碎片化短句 → fragment_short
frag = "他来了。" * 80
rf = report_advisory(frag, rules)
_assert("fragment_short" in rf["flags"], "碎片化短句触发 fragment_short")

# 3. 排比（有的…有的…有的）
para = ("有的大人缩在墙角。有的小孩哭着喊娘。有的老人呆坐着不动。") * 10
rp = report_advisory(para, rules)
_assert("parallelism" in rp["flags"], "排比'有的…有的…有的'触发 parallelism")

# 4. 微动作套路密度（≥4/千字）
micro = ("他眼皮一跳。她心口一沉。我胃里翻涌。你指尖一颤。他喉头一紧。") * 8
rm = report_advisory(micro, rules)
_assert("micro_action" in rm["flags"], "微动作套路高密度触发 micro_action")

# 5. 比喻密度
met = ("他像山。她如风。那似水。光若剑。云仿佛棉。月犹如盘。") * 10
rmet = report_advisory(met, rules)
_assert("metaphor_density" in rmet["flags"], "比喻标记高密度触发 metaphor_density")

# 6. 低连接密度（无连接词）→ 默认阈值(0.0)已禁用该退化信号（人类语料 63.4% 误杀），不触发
lowc = ("天黑了。门开了。人走了。灯灭了。狗叫了。猫跑了。书掉了。水凉了。") * 10
rl = report_advisory(lowc, rules)
_assert("low_connectivity" not in rl["flags"], "低连接词默认禁用(阈值0.0)不触发 low_connectivity")

# 6b. 触发逻辑仍在：临时恢复阈值 2.0/千字 → 验证低连接词仍触发（锁定实现）
enabled = load_advisory_rules()
# low_connectivity 在 metrics 嵌套下（非 thresholds）；恢复阈值 2.0/千字验证触发逻辑仍在
enabled["metrics"]["low_connectivity"]["min_per_1k_chars"] = 2.0
rle = report_advisory(lowc, rules=enabled)
_assert("low_connectivity" in rle["flags"], "低连接词触发逻辑仍在(阈值恢复到2.0)")

# 7. 过度精炼短段
shortpara = "\n\n".join(["他走了。"] * 150)
rsp = report_advisory(shortpara, rules)
_assert("over_refined_short_para" in rsp["flags"], "过度精炼短段触发 over_refined_short_para")

# 8. 公文腔
off = ("根据会议精神，按照部署，鉴于当前形势，综上所述，予以进一步推进，开展专项工作。") * 10
ro = report_advisory(off, rules)
_assert("official_tone" in ro["flags"], "公文腔触发 official_tone")

# 9. 引号豁免：微动作在「」内不计入 masked → 不触发 micro_action
quoted = ("「他眼皮一跳，心口一沉，胃里翻涌，指尖一颤，喉头一紧」") * 8
rq = report_advisory(quoted, rules)
_assert("micro_action" not in rq["flags"], "「」内微动作被豁免（不触发 micro_action）")

# 10. 标题行不误杀：含排比结构的章节标题被剔除，正文无排比 → 不触发 parallelism
title = ("第一章 有的大人缩在墙角，有的小孩哭着喊娘，有的老人呆坐着不动。\n"
         + ("林霜推开门。院子老槐落半地叶。她蹲下触泥土。远处犬吠声。故事收尾黄昏里。") * 12)
rt = report_advisory(title, rules)
_assert("parallelism" not in rt["flags"], "章节标题行不误杀排比（标题行已剔除）")

# 11. 短文本跳过（< min_chars_total）
tiny = "他来了。"
rti = report_advisory(tiny, rules)
_assert(not rti["advisory_alarm"], "中文字数不足跳过 advisory")

# 12. merge 多参（qiaomu + deg + adv）→ OR + MAX
fake_ai = {"ai_flavor_alarm": True, "severity": 0.3, "alarm_detail": "qiaomu 测试"}
fake_deg = {"degeneration_alarm": True, "severity": 0.4, "flags": ["tier1_leak"]}
fake_adv = {"advisory_alarm": True, "severity": 0.2, "flags": ["micro_action", "parallelism"]}
merged = merge_ai_flavor_signals(fake_ai, fake_deg, fake_adv)
_assert(merged["ai_flavor_alarm"], "merge 多参 alarm=True")
_assert(abs(merged["severity"] - 0.4) < 1e-6, "merge severity 取 MAX(0.4)")
_assert("advisory:" in merged["alarm_detail"], "merge detail 含 advisory 标签")
_assert("deslop:" in merged["alarm_detail"], "merge detail 含 deslop: 标签（退化去品牌）")

# 13. 终判不翻 FAIL（红线）：合并 advisory 进 triple_cross_judge
base = ("林霜推开木门。院子里的老槐树落了半地叶子。她蹲下身，指尖触到冰凉的泥土。"
        "远处传来一声犬吠。故事就在这样的黄昏里收了尾。他因为她不肯走，所以留了下来。") * 2
tc = triple_cross_judge(base, ai_flavor=merged)
_assert(tc["verdict"] != "FAIL", "合并弱信号(含 advisory)绝不翻 FAIL（verdict=%s）" % tc["verdict"])
_assert(tc["layers"].get("ai_flavor", {}).get("verdict") == "WARN", "弱信号层恒 WARN")
_assert(tc["layers"]["ai_flavor"]["confidence"] <= 0.5, "弱信号 confidence 封顶 0.5")

print("\n=== advisory 自测: %d 通过 / %d 失败 ===" % (_pass, _fail))
sys.exit(1 if _fail else 0)
