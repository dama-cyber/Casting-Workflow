# -*- coding: utf-8 -*-
"""
_selftest_anti_ai.py — qiaomu 借鉴增量（方向 A + 方向 B）联调自测（T04）

覆盖主理人裁决的 4 个验收点：
  ① 用 corpus 真实小说跑 check_story.py --ai-flavor，确认第十二节正常输出；
  ② 用含「不是…而是」「关键在于」「——」的 AI 套路文本验证告警触发 + 引号豁免；
  ③ 调用 triple_cross_judge 传 ai_flavor，确认 verdict 绝不变成 FAIL、confidence ≤ 0.5；
  ④ 确认零新增第三方依赖、fusion.py 未改动（红线）。

纯标准库 + 项目内模块，零新增依赖。退出码 0 = 全部通过，1 = 有失败。
"""
import os
import re
import sys
import shutil
import subprocess

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_CHK = os.path.join(_ROOT, "check_story.py")
_REQ = os.path.join(_ROOT, "requirements.txt")
_FUSION = os.path.join(_ROOT, "tools", "fusion.py")

failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        failures.append(name)


# ============================================================
# ② 告警触发 + 引号豁免（引擎级）
# ============================================================
from tools.anti_ai_reporter import report_ai_flavor, load_banned

ai_tell = (
    "需求流程系统规范策略机制能力价值痛点闭环效率协同模型方案架构规则。"
    "会议室门口窗雨灯桌屏幕手机街车手眼血杯纸门椅走廊的场景描写。"
    "这不是我们想要的结果，而是彻底的失败。"          # 引号外 not_x_but_y → 应命中
    "关键在于我们需要重新审视。值得注意的是这问题。让我们想象一个世界。"  # teaching_transition
    "这不仅是一个错误，更是一次教训。这就是努力的意义。"  # not_only_more + meaning_slogan
    "他冷冷地说：「你不是英雄，而是懦夫。」"            # 引号内 not_x_but_y → 应豁免
    "—— —— —— ——"                                  # 破折号 > 3
    "死人走进了房间，尸体来到桌前。"                    # ambiguous_opening
)

r = report_ai_flavor(ai_tell)
check("② report_ai_flavor 返回结构含必要键",
      all(k in r for k in ("abstract", "scene", "hook", "dash", "aiish",
                           "ambiguous", "dialogue", "ai_flavor_alarm",
                           "alarm_severity", "severity", "issues")),
      str(list(r.keys())))
check("② 去 AI 味告警触发 (ai_flavor_alarm=True)", r["ai_flavor_alarm"], str(r["flags"]))
check("② not_x_but_y 命中(引号外)", r["aiish"]["breakdown"].get("not_x_but_y", 0) >= 1,
      f"not_x_but_y={r['aiish']['breakdown'].get('not_x_but_y')}")
check("② aiish 软信号总体命中", r["aiish"]["count"] >= 1, f"aiish_total={r['aiish']['count']}")
check("② 破折号 > 3 触发", r["dash"]["count"] > 3, f"dash={r['dash']['count']}")
check("② 误导开篇命中", r["ambiguous"]["count"] >= 1, f"amb={r['ambiguous']['count']}")
# 引号豁免：整段「你不是英雄，而是懦夫。」应被脱敏，not_x_but_y 仅计引号外 1 次
check("② 引号内 not_x_but_y 豁免(总数==1)",
      r["aiish"]["breakdown"].get("not_x_but_y", 0) == 1,
      f"not_x_but_y={r['aiish']['breakdown'].get('not_x_but_y')}")
# banned 硬项命中桶（不豁免）：「——」与「不是X是Y」正则
banned_hits = {it["value"]: it["count"] for it in r["issues"]}
check("② banned 硬项——命中", banned_hits.get("——", 0) >= 4, str(banned_hits))
# 不是X是Y 正则机制验证：banned.json 含该硬正则且对干净样本(无逗号阻断)可命中
_xy_pat = next((p for p in load_banned().get("banned_patterns", []) if p.startswith("不是")), None)
check("② banned.json 含『不是X是Y』硬正则且对干净样本命中",
      _xy_pat is not None and len(re.findall(_xy_pat, "他不是英雄而是懦夫。")) >= 1,
      str(_xy_pat))

# ============================================================
# ③ triple_cross_judge 注入 qiaomu 弱信号：绝不 FAIL，conf ≤ 0.5
# ============================================================
from tools.humanity_scorer import triple_cross_judge

# 3a. 真实 AI 套路文本 + 其 ai_flavor → 终判绝不 FAIL
tc1 = triple_cross_judge(ai_tell, ai_flavor=r)
check("③ 真实文本+ai_flavor 终判非 FAIL",
      tc1["verdict"] in ("PASS", "WARN"), f"verdict={tc1['verdict']}")
check("③ 注入 ai_flavor 层存在且为 WARN",
      tc1["layers"].get("ai_flavor", {}).get("verdict") == "WARN",
      str(tc1["layers"].get("ai_flavor")))
_conf = tc1["layers"]["ai_flavor"]["confidence"]
check("③ ai_flavor confidence ≤ 0.5", _conf <= 0.5, f"conf={_conf}")

# 3b. 构造 severity 拉满(=1.0) 的 ai_flavor，最极端情况仍不可翻成 FAIL
max_sig = dict(r)
max_sig["severity"] = 1.0
max_sig["ai_flavor_alarm"] = True
clean_text = "窗外的雨落在桌上。他握紧了刀，血从指缝渗出。「滚。」她冷笑。走廊尽头灯光熄灭。"
tc2 = triple_cross_judge(clean_text, ai_flavor=max_sig)
check("③ 极端 severity=1.0 终判仍非 FAIL",
      tc2["verdict"] in ("PASS", "WARN"), f"verdict={tc2['verdict']}")
check("③ 极端 severity confidence 封顶 0.5",
      tc2["layers"]["ai_flavor"]["confidence"] <= 0.5,
      f"conf={tc2['layers']['ai_flavor']['confidence']}")

# 3c. 对比：同一文本不传 ai_flavor 时仍可正常终判（无回归）
tc3 = triple_cross_judge(ai_tell)
check("③ 不传 ai_flavor 仍正常(无 ai_flavor 层)", "ai_flavor" not in tc3["layers"],
      f"verdict={tc3['verdict']}")

# ============================================================
# ① 端到端：corpus 真实小说 + check_story.py --ai-flavor
# ============================================================
corpus_story = None
for root, _, files in os.walk(os.path.join(_ROOT, "corpus")):
    for fn in files:
        if fn.endswith(".txt"):
            corpus_story = os.path.join(root, fn)
            break
    if corpus_story:
        break
check("① 找到 corpus 真实小说", corpus_story is not None, corpus_story or "")

if corpus_story:
    tmp_story = os.path.join(_ROOT, "output", "_selftest_story.txt")
    tmp_report = tmp_story.replace(".txt", "_check_report.txt")
    try:
        os.makedirs(os.path.dirname(tmp_story), exist_ok=True)
        shutil.copyfile(corpus_story, tmp_story)
        proc = subprocess.run(
            [sys.executable, _CHK, tmp_story, "--ai-flavor"],
            cwd=_ROOT, capture_output=True, timeout=300,
        )
        out = ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", "replace")
        check("① check_story 退出码 0", proc.returncode == 0,
              f"rc={proc.returncode}")
        check("① 终端输出含『十二、去 AI 味报告』", "十二、去 AI 味报告" in out)
        check("① 终端输出含『去AI味告警』", "去AI味告警" in out)
        check("① 报告文件含去 AI 味报告节",
              os.path.exists(tmp_report)
              and "去 AI 味报告" in open(tmp_report, encoding="utf-8").read())
    finally:
        for p in (tmp_story, tmp_report):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

# ============================================================
# ④ 红线校验：零新增依赖 + fusion.py 未改动
# ============================================================
req_txt = open(_REQ, encoding="utf-8").read()
req_lines = [ln.strip() for ln in req_txt.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
check("④ requirements.txt 仍仅含 jieba（零新增依赖）",
      req_lines == ["jieba"], str(req_lines))

fusion_src = open(_FUSION, encoding="utf-8").read()
check("④ fusion.py 未引用 anti_ai_reporter / 第十二节",
      "anti_ai" not in fusion_src and "第十二节" not in fusion_src)
chk_src = open(_CHK, encoding="utf-8").read()
check("④ check_story 第十二节消费 anti_ai_reporter",
      "anti_ai_reporter" in chk_src and "去 AI 味报告" in chk_src)
check("④ check_story CLI 含 --ai-flavor / --no-ai-flavor",
      "--no-ai-flavor" in chk_src and "--ai-flavor" in chk_src)

# ============================================================
print("\n" + "=" * 50)
if failures:
    print(f"自测结果: {len(failures)} 项失败 -> {failures}")
    sys.exit(1)
else:
    print("自测结果: 全部通过")
    sys.exit(0)
