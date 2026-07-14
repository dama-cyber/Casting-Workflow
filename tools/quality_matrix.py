# -*- coding: utf-8 -*-
"""
quality_matrix.py — 统一创作质量矩阵（qiaomu 借鉴增量 · 方向 D）

把分散的创作质量维度（去 AI 味 / 画面感(show-don't-tell) / 开篇钩子 / 质量清单）
汇总成一张综合矩阵，并融合进三交叉终判（仅 WARN 弱信号）。

红线约束（不可破）：
  - 不读取 / 修改 tools/fusion.py（互消层）。只读最终文本 + 已有 report + config。
  - 不泄露 corpus 字面：config 只存通用词典 / 阈值；报告只回显计数与密度。
  - 质量矩阵仅作 INFO / WARN 级弱信号，绝不产出 FAIL。
  - 8G 安全：KB 级词典常驻；单篇流式统计，无全量载入。
  - 不重复计数：去 AI 味 / 退化 / 风格密度三维度直接复用 _ai/_deg/_adv 已算结果；
    本模块**唯一新增 WARN 源**是 show_dont_tell（画面感），其余维度仅做汇总展示。

用法（内部被 check_story.py 第十五节调用）:
    from tools.quality_matrix import report_quality_matrix, load_quality_matrix_rules
"""
import os
import re
import json

# 配置路径：相对项目根（本文件位于 tools/，父目录即项目根），与 CWD 无关。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_PATH = os.path.join(_ROOT, "config", "quality_matrix_rules.json")

# 内联保守默认（config 缺失 / 解析失败时降级，不崩、不中断质检）。
_INLINE = {
    "version": "qiaomu-quality-matrix-v1",
    "show_dont_tell": {
        # 告诉型（tell）思维标记：叙述直接交代内心/评判，画面感弱
        "tell_terms": ["心想", "意识到", "感到", "觉得", "认为", "明白", "知道",
                        "突然明白", "恍然", "蓦地明白", "明白过来", "心里想", "脑海中"],
        # 软副词：堆砌稀释画面感
        "soft_adverbs": ["轻轻", "缓缓", "微微", "悄悄", "明显地", "显然", "显然地",
                          "分明显得", "似乎", "好像", "仿佛", "俨然", "依稀", "隐约"],
        # 每千字 tell 词（思维标记+软副词）密度告警门槛
        "tell_density_warn": 3.0,
        # 展示型（show）感官/动作动词：有画面感
        "scene_show_verbs": ["看", "看见", "听见", "闻到", "摸", "嗅", "望", "盯",
                              "触", "尝", "凝视", "扫视", "倾听"],
        # 开篇（前 3 段）悬念/提问/冲突标记 → 强钩子
        "hook_opening_markers": ["？", "为什么", "究竟", "到底", "怎么会", "谁也想不到",
                                  "没人想到", "偏偏", "竟", "竟然", "不料"],
    },
}


def _load_json(path, default, label):
    """标准库 json.load；缺失 / 解析失败 → 返回内联默认并打印 [SKIP]，不崩。"""
    try:
        if not os.path.exists(path):
            print(f"[SKIP] {label} 未找到: {path}，使用内联默认")
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001 - 配置加载失败需优雅降级
        print(f"[SKIP] {label} 解析失败: {e}，使用内联默认")
        return default


def load_quality_matrix_rules(path=_DEFAULT_PATH):
    """加载 config/quality_matrix_rules.json（质量矩阵词典/阈值）。"""
    return _load_json(path, _INLINE, "quality_matrix_rules")


def _zh_count(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text)) or 1


def report_quality_matrix(text, reports=None, rules=None):
    """统一创作质量矩阵。

    参数:
      text    : 待评估文本（已生成的最终文本）
      reports : dict，含已计算的 {ai:_ai, deg:_deg, adv:_adv}（来自十二/十三节）
      rules   : 配置 dict；None 时内部加载 config/quality_matrix_rules.json

    返回（契约）:
      {
        "enabled": True,
        "show_dont_tell": {"alarm":bool, "severity":float(0-1), "score":float(0-1),
                            "tell_density":float, "signals":[str]},

        "matrix": [ {"dim":str, "level":"OK|WARN|INFO|ISSUE", "score":float,
                      "note":str}, ... 4 项 ],
        "composite": {"score":float, "level":str, "alarm":bool, "severity":float},
        "quality_matrix_alarm": bool,   # 综合告警（= show_dont_tell.alarm）
        "severity": float,               # 供 merge_ai_flavor_signals 接收
      }

    关键不变量：
      - `show_dont_tell` 是唯一新增 WARN 源，进 merge → 三交叉终判；
      - 去 AI 味 / 开篇钩子 / 质量清单三维度仅做汇总展示，不重复计入终判；
      - 全函数 level ∈ {OK, WARN, INFO, ISSUE}，绝不 FAIL。
    """
    if rules is None:
        rules = load_quality_matrix_rules()
    if reports is None:
        reports = {}
    _ai = reports.get("ai") or {}
    _deg = reports.get("deg") or {}
    _adv = reports.get("adv") or {}

    sdt = rules.get("show_dont_tell", {}) or {}
    tell_terms = sdt.get("tell_terms", []) or []
    soft_adverbs = sdt.get("soft_adverbs", []) or []
    tell_warn = float(sdt.get("tell_density_warn", 3.0))
    scene_verbs = sdt.get("scene_show_verbs", []) or []
    hook_open = sdt.get("hook_opening_markers", []) or []

    zh = _zh_count(text)

    def per100(n):
        return round(n / (zh / 100.0), 3)

    # ---- 画面感：告诉 vs 展示（唯一新增 WARN 源） ----
    tell_hits = sum(text.count(t) for t in tell_terms)
    adv_hits = sum(text.count(a) for a in soft_adverbs)
    tell_total = tell_hits + adv_hits
    tell_density = per100(tell_total)
    show_hits = sum(text.count(v) for v in scene_verbs)

    # score：展示信号相对占比（0-1，越高越"有画面感"）
    _denom = (show_hits + tell_hits) or 1
    sdt_score = round(min(1.0, max(0.0, show_hits / _denom)), 4)
    sdt_alarm = tell_density > tell_warn
    sdt_sev = round(min(1.0, (tell_density - tell_warn) / max(tell_warn, 0.001)), 4) if sdt_alarm else 0.0
    sdt_signals = []
    if tell_hits:
        sdt_signals.append(f"思维标记{tell_hits}处")
    if adv_hits:
        sdt_signals.append(f"软副词{adv_hits}处")
    if sdt_alarm:
        sdt_signals.append(f"tell密度{tell_density}/千字>门槛{tell_warn}")

    # ---- 去 AI 味维度（汇总自 _ai） ----
    ai_alarm = bool(_ai.get("ai_flavor_alarm"))
    ai_score = round(1.0 - float(_ai.get("severity", 0.0) or 0.0), 4)
    ai_flags = _ai.get("flags", []) or []
    ai_note = f"告警{'是' if ai_alarm else '否'}，触发{len(ai_flags)}项"

    # ---- 开篇钩子维度（自 _ai.hook + 开篇提问/冲突启发式） ----
    hook_count = int((_ai.get("hook") or {}).get("count", 0) or 0)
    _first3 = "\n".join(text.split("\n")[:3])
    opening_hook = any(m in _first3 for m in hook_open)
    hook_score = round(min(1.0, (hook_count + (1 if opening_hook else 0)) / 3.0), 4)
    hook_alarm = (hook_count == 0 and not opening_hook)
    hook_note = (f"前3段钩子标记{hook_count}；开篇悬念/提问{'有' if opening_hook else '无'}"
                 + ("；弱钩子 WARN" if hook_alarm else ""))

    # ---- 质量清单维度（汇总三源 flags + 硬项） ----
    deg_flags = _deg.get("flags", []) or []
    adv_flags = _adv.get("flags", []) or []
    ai_issues = _ai.get("issues", []) or []
    warn_count = len(ai_flags) + len(deg_flags) + len(adv_flags)
    hard_count = len(ai_issues) + len(_deg.get("issues", []) or [])
    qc_score = round(max(0.0, 1.0 - (warn_count + hard_count * 2) / 10.0), 4)
    if hard_count > 0:
        qc_level = "ISSUE"
    elif warn_count > 0:
        qc_level = "WARN"
    else:
        qc_level = "OK"
    qc_note = f"WARN信号{warn_count}项；硬证据{hard_count}处"

    # ---- 矩阵组装 ----
    _ai_level = "WARN" if ai_alarm else ("INFO" if ai_score < 0.6 else "OK")
    _sdt_level = "WARN" if sdt_alarm else ("OK" if sdt_score >= 0.6 else "INFO")
    _hook_level = "WARN" if hook_alarm else ("OK" if hook_score >= 0.34 else "INFO")
    matrix = [
        {"dim": "去AI味", "level": _ai_level, "score": ai_score, "note": ai_note},
        {"dim": "画面感", "level": _sdt_level, "score": sdt_score,
         "note": f"score={sdt_score}，tell密度{tell_density}/千字"},
        {"dim": "开篇钩子", "level": _hook_level, "score": hook_score, "note": hook_note},
        {"dim": "质量清单", "level": qc_level, "score": qc_score, "note": qc_note},
    ]

    # ---- 综合（唯一新增 WARN 源 = 画面感） ----
    _scores = [ai_score, sdt_score, hook_score, qc_score]
    composite_score = round(sum(_scores) / len(_scores), 4)
    composite_alarm = sdt_alarm  # 仅画面感新增 WARN；其余为汇总展示，不重复计入终判
    composite_sev = sdt_sev

    return {
        "enabled": True,
        "show_dont_tell": {
            "alarm": sdt_alarm,
            "severity": sdt_sev,
            "score": sdt_score,
            "tell_density": tell_density,
            "signals": sdt_signals,
        },
        "matrix": matrix,
        "composite": {
            "score": composite_score,
            "level": "WARN" if composite_alarm else ("OK" if composite_score >= 0.7 else "INFO"),
            "alarm": composite_alarm,
            "severity": composite_sev,
        },
        "quality_matrix_alarm": composite_alarm,
        "severity": composite_sev,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python quality_matrix.py <story.txt>")
        sys.exit(1)
    _txt = open(sys.argv[1], "r", encoding="utf-8", errors="replace").read()
    print(json.dumps(report_quality_matrix(_txt), ensure_ascii=False, indent=2))
