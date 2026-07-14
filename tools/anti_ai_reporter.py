# -*- coding: utf-8 -*-
"""
anti_ai_reporter.py — 去 AI 味报告引擎（qiaomu 借鉴增量 · 方向 A + 方向 B）

纯正则 / 零依赖（仅标准库 re + json）。把 qiaomu evaluate_story.py 的
ABSTRACT_TERMS / SCENE_MARKERS / HOOK_MARKERS / AIISH_PATTERNS /
AMBIGUOUS_OPENING_PATTERNS 思路下沉为本项目的「去 AI 味」五维统计（方向 A），
并闭合 prompt/COMMON.md 已禁用但 QA 未执行的硬禁用项（方向 B：banned.json）。

红线约束（不可破）：
  - 不读取 / 修改 tools/fusion.py（互消层）。本模块只读最终文本 + config。
  - 不泄露 corpus 字面：config 只存通用词典 / 正则 / 阈值，报告只回显计数与密度。
  - qiaomu 规则仅作 INFO / WARN 级弱信号，绝不产出 FAIL（severity.fail_disabled 哲学）。
  - 8G 安全：KB 级词典常驻内存；单篇流式统计，无全量载入、无 baseline 构建。

引号适配（主理人裁决 2 / 4）：
  - 本项目对话用「」而非 qiaomu 的 ""。对话行识别、软 AIISH 豁免均改用「」。
  - 软 AIISH 信号（6 条）在「…」内豁免：匹配前把「…」内部替换为等长空格再跑软模式。
  - banned 硬禁用项（—— / 不是X是Y / 格式化比喻 / 软副词 / 群像套路词）不豁免。

用法（内部被 check_story.py 第十二节调用）:
    from tools.anti_ai_reporter import report_ai_flavor, load_anti_ai_rules, load_banned
"""
import os
import re
import json

# 配置路径：相对项目根（本文件位于 tools/，父目录即项目根），与 CWD 无关。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_RULES_PATH = os.path.join(_ROOT, "config", "anti_ai_rules.json")
_DEFAULT_BANNED_PATH = os.path.join(_ROOT, "config", "banned.json")
_DEFAULT_WHITELIST_PATH = os.path.join(_ROOT, "config", "deslop_whitelist.txt")

# 内联保守默认（config 缺失 / 解析失败时降级，不崩、不中断质检）。
# 与 anti_ai_rules.json 真实值保持一致（主理人裁决：照搬 qiaomu 真实正则/阈值）。
_INLINE_RULES = {
    "version": "qiaomu-ai-flavor-v1",
    "dictionaries": {
        "abstract_terms": ["需求", "流程", "系统", "规范", "策略", "机制", "能力", "价值",
                           "痛点", "闭环", "效率", "协同", "模型", "方案", "架构", "规则"],
        "scene_markers": ["会议室", "门口", "窗", "雨", "灯", "桌", "屏幕", "手机", "街", "车",
                          "手", "眼", "血", "杯", "纸", "门", "椅", "走廊"],
        "hook_markers": ["死", "血", "笑", "哭", "错", "债", "骂", "停", "断", "丢", "骗",
                         "杀", "输", "滚", "赔", "取消"],
    },
    "aiish_patterns": [
        {"name": "not_x_but_y", "pattern": r"不是[^。！？\n]{0,40}而是"},
        {"name": "not_about_but_about", "pattern": r"不在于[^。！？\n]{0,40}在于"},
        {"name": "summary_ending", "pattern": r"总之|综上所述|总而言之"},
        {"name": "teaching_transition", "pattern": r"关键在于|值得注意的是|让我们|想象一个世界"},
        {"name": "not_only_more", "pattern": r"这不仅[^。！？\n]{0,40}更是"},
        {"name": "meaning_slogan", "pattern": r"这就是[^。！？\n]{0,30}的意义"},
    ],
    "ambiguous_opening": [
        {"name": "dead_person_walking", "pattern": r"死人[^。！？\n]{0,12}(走|进|来|到)"},
        {"name": "corpse_walking", "pattern": r"尸体[^。！？\n]{0,12}(走|进|来|到)"},
        {"name": "dead_speaking", "pattern": r"(死人|死者|尸体)[^。！？\n]{0,12}(说|问|喊|开口)"},
    ],
    "thresholds": {
        "dialogue_min": 4,
        "dialogue_ratio_min": 0.06,
        "abstract_abs_max": 12,
        "scene_min": 8,
        "hook_zero_alarm": True,
        "aiish_not_x_but_y_min": 1,
        "aiish_total_min": 1,
        "dash_max": 3,
        "ambiguous_min": 1,
    },
    "opening_exemptions": ["那一年", "那年", "多年以后", "时光倒流", "梦境", "梦回", "梦里", "醒来", "忆起", "忆及", "恍惚", "记得那年", "一晃", "往事", "旧年", "从前", "彼时", "彼年", "恍如隔世", "梦醒", "昨夜梦", "记忆里", "记忆中"],
    "quote_exemption": {
        "enabled": True,
        "quote_pairs": [["「", "」"], ["“", "”"]],
        "exempt_groups": ["aiish"],
    },
}

# banned.json 原始内容（兜底默认，避免文件缺失时完全无检查）。
_INLINE_BANNED = {
    "banned_patterns": [
        "对X而言", "一切都在", "她心想", "她意识到", "她感到", "一种说不出的",
        "真正的X是Y", "X的意义在于", "X既是Y也是Z", "谁说X就一定Y",
    ],
    "banned_templates": [
        "眼中闪过", "嘴角勾起", "眼眶微红", "不可置信", "眼底闪过", "咬了咬唇",
        "冷冷地说", "身子一颤", "心头一紧", "倒吸一口凉气", "目光一凝", "瞳孔一缩",
    ],
    "banned_punctuation": ["；", "！！！", "？！"],
}


# ============================================================
# 配置加载（标准库 json；失败降级，不崩）
# ============================================================
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


def load_anti_ai_rules(path=_DEFAULT_RULES_PATH):
    """加载 config/anti_ai_rules.json（去 AI 味词典/正则/阈值）。"""
    return _load_json(path, _INLINE_RULES, "anti_ai_rules")


def load_banned(path=_DEFAULT_BANNED_PATH):
    """加载 config/banned.json。返回 banned_punctuation(子串) / banned_patterns(正则) / banned_templates(子串)。"""
    return _load_json(path, _INLINE_BANNED, "banned")


def load_whitelist(path=_DEFAULT_WHITELIST_PATH):
    """加载 config/deslop_whitelist.txt（方向 G · 词表豁免层）。

    一行一词；以 # 开头的整行视为注释；空行忽略。返回**小写化**词集合。
    空表 = 零豁免（不改变任何现有检测行为）。
    文件缺失 / 解析失败 → 返回空集合并打印 [SKIP]，不崩。
    """
    wl = set()
    try:
        if not os.path.exists(path):
            print(f"[SKIP] whitelist 未找到: {path}，使用空白名单（零豁免）")
            return wl
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                wl.add(s.lower())
    except Exception as e:  # noqa: BLE001 - 白名单加载失败需优雅降级
        print(f"[SKIP] whitelist 解析失败: {e}，使用空白名单")
    return wl


# ============================================================
# 引号脱敏（软 AIISH 信号豁免）
# ============================================================
def _mask_quotes(text, quote_pairs=(("「", "」"), ("“", "”"))):
    """把「…」整段（含引号）替换为等长空格，使软 AIISH 正则不会在引号内命中。

    仅对 quote_exemption.exempt_groups 含 "aiish" 时生效；banned 硬项不调用本函数。
    """
    result = text
    for left, right in quote_pairs:
        pat = re.escape(left) + r"[\s\S]*?" + re.escape(right)
        result = re.sub(pat, lambda m: " " * len(m.group(0)), result)
    return result


def _pattern_of(p):
    """兼容 JSON 的 {name,pattern} 与元组 (name,pattern) 两种写法。"""
    if isinstance(p, dict):
        return p.get("name", ""), p.get("pattern", "")
    if isinstance(p, (list, tuple)) and len(p) >= 2:
        return str(p[0]), str(p[1])
    return "", str(p)


# ============================================================
# 主引擎：report_ai_flavor
# ============================================================
def report_ai_flavor(text, rules=None, banned=None, genre="default",
                     in_quotes_exempt=True, whitelist=None):
    """方向 A 五维（抽象/场景/钩子/AI味/误导）+ 方向 B 软/硬信号，纯正则统计。

    参数:
      text            : 待检测文本（已生成的最终文本）
      rules           : anti_ai_rules dict；为 None 时内部加载 config/anti_ai_rules.json
      banned          : banned dict；为 None 时内部加载 config/banned.json
      genre           : 体裁标识（预留，当前不影响阈值）
      in_quotes_exempt: 是否对软 AIISH 信号做「」豁免（默认开）

    返回（契约）:
      {
        "enabled": True,
        "abstract":  {"count":int, "per_100":float},
        "scene":     {"count":int, "per_100":float},
        "hook":      {"count":int, "per_100":float},
        "dash":      {"count":int, "per_100":float},
        "aiish":     {"count":int, "per_100":float, "breakdown":{name:int}},
        "ambiguous": {"count":int, "breakdown":{name:int}},
        "dialogue":  {"count":int, "per_100":float},   # 「」对话行数
        "dialogue_ratio": float,                        # 「」内字数 / 总中文字数（qiaomu F）
        "ambiguous_exempted": bool,                     # 开篇误导豁免（闪回/梦境，qiaomu F）
        "ambiguous_exempt_reason": str,
        "ai_flavor_alarm": bool,
        "alarm_severity": "INFO" | "WARN",
        "severity": float(0-1),                         # 供 triple_cross_judge 映射封顶置信度
        "alarm_detail": str,
        "flags": [str],                                 # 触发的阈值条件名
        "issues": [ {"type","value","count","detail"} ] # banned 硬项命中桶（不豁免）
      }

    关键不变量:
      - 所有 qiaomu 派生信号 level ∈ {INFO, WARN}，绝不 FAIL；
      - banned.json 硬禁用项单独计 issues（❌ 严重，与现有标点检查同级），但不进入软信号桶；
      - 「」内的 not_x_but_y 与 soft AIISH 命中按 quote_exemption 豁免。
    """
    if rules is None:
        rules = load_anti_ai_rules()
    if banned is None:
        banned = load_banned()
    if whitelist is None:
        whitelist = load_whitelist()

    zh = len(re.findall(r"[\u4e00-\u9fff]", text)) or 1

    dictionaries = rules.get("dictionaries", {}) or {}
    abstract_terms = dictionaries.get("abstract_terms", []) or []
    scene_markers = dictionaries.get("scene_markers", []) or []
    hook_markers = dictionaries.get("hook_markers", []) or []
    aiish_patterns = rules.get("aiish_patterns", []) or []
    ambiguous_patterns = rules.get("ambiguous_opening", []) or []
    thresholds = rules.get("thresholds", {}) or {}

    # ---- 引号豁免：构建软 AIISH 用的已脱敏文本 ----
    quote_cfg = rules.get("quote_exemption", {}) or {}
    exempt_on = bool(in_quotes_exempt) and bool(quote_cfg.get("enabled", True))
    if exempt_on:
        qpairs = [(p[0], p[1]) for p in quote_cfg.get("quote_pairs", [["「", "」"]])]
        masked_text = _mask_quotes(text, qpairs)
    else:
        masked_text = text

    # ---- 词典计数（抽象/场景/破折号：不豁免，全文本） ----
    abstract_hits = sum(text.count(t) for t in abstract_terms)
    scene_hits = sum(text.count(t) for t in scene_markers)
    dash_hits = text.count("——")

    # ---- 钩子标记：仅统计前 3 段（qiaomu oracle：hook_hits(前3段)==0 才告警） ----
    # 段切分按单换行「\n」（网文段落即单行）；全文不足 3 段时取全部，不越界。
    # 设计§7-② / 任务断言 1 明确要求 hook 仅统计前 3 段，避免真实故事中后续段落必含
    # 常见 hook 字（死/血/笑/哭…）之一，导致 no_hook 开场钩子检测形同虚设。
    # 注：ambiguous_opening 仍按全文统计（与 qiaomu oracle 的 ambiguous_opening_total>0 一致）。
    _first3_para = "\n".join(text.split("\n")[:3])
    hook_hits = sum(_first3_para.count(t) for t in hook_markers)

    # ---- 对话行数（「」识别；本项目对话约定） ----
    dialogue_lines = sum(1 for line in text.split("\n") if "「" in line)

    # ---- 对话字数占比（qiaomu F：对话绝对值门槛 ratio 版） ----
    _dialogue_chars = 0
    for _dm in re.finditer(r"「([^」]*)」", text):
        _dialogue_chars += len(_dm.group(1))
    _dialogue_ratio = round(_dialogue_chars / zh, 4)

    # ---- AIISH 软信号（引号内豁免） ----
    aiish_breakdown = {}
    aiish_total = 0
    for p in aiish_patterns:
        name, pat = _pattern_of(p)
        try:
            c = len(re.findall(pat, masked_text))
        except re.error:
            c = masked_text.count(pat)
        aiish_breakdown[name] = c
        aiish_total += c
    not_x_but_y = aiish_breakdown.get("not_x_but_y", 0)

    # ---- 误导开篇（硬信号：不豁免） ----
    ambiguous_breakdown = {}
    ambiguous_total = 0
    for p in ambiguous_patterns:
        name, pat = _pattern_of(p)
        try:
            c = len(re.findall(pat, text))
        except re.error:
            c = text.count(pat)
        ambiguous_breakdown[name] = c
        ambiguous_total += c

    # ---- 每千字密度 ----
    def per100(n):
        return round(n / (zh / 100.0), 3)

    # ---- 阈值触发判定（照搬 qiaomu evaluate_story.py 真实逻辑） ----
    flags = []
    if dialogue_lines < int(thresholds.get("dialogue_min", 4)):
        flags.append("dialogue_sparse")  # 对话行数 < 4
    if _dialogue_ratio < float(thresholds.get("dialogue_ratio_min", 0.06)):
        flags.append("dialogue_ratio_low")  # 对话字数占比 < 阈值
    if (abstract_hits > scene_hits * 2
            and abstract_hits > int(thresholds.get("abstract_abs_max", 12))):
        flags.append("abstract_dense")  # 抽象词 > 场景*2 且 > 12
    if scene_hits < int(thresholds.get("scene_min", 8)):
        flags.append("scene_sparse")  # 场景标记 < 8
    if bool(thresholds.get("hook_zero_alarm", True)) and hook_hits == 0:
        flags.append("no_hook")  # 钩子标记 == 0
    if not_x_but_y >= int(thresholds.get("aiish_not_x_but_y_min", 1)):
        flags.append("not_x_but_y")  # not_x_but_y > 0
    if aiish_total >= int(thresholds.get("aiish_total_min", 1)):
        flags.append("aiish_present")  # aiish_total > 0
    if dash_hits > int(thresholds.get("dash_max", 3)):
        flags.append("dash_overuse")  # 破折号 > 3
    if ambiguous_total >= int(thresholds.get("ambiguous_min", 1)):
        flags.append("ambiguous_opening")  # 误导开篇 > 0

    # ---- 开篇误导豁免（qiaomu F：闪回/梦境开篇合法，降假阳） ----
    exempt_markers = rules.get("opening_exemptions", []) or []
    _amb_exempted = False
    _amb_exempt_reason = ""
    if "ambiguous_opening" in flags and exempt_markers:
        _open_region = _first3_para
        _hit = [em for em in exempt_markers if em in _open_region]
        if _hit:
            _amb_exempted = True
            _amb_exempt_reason = "闪回/梦境开篇豁免: " + "/".join(_hit)
            flags.remove("ambiguous_opening")

    ai_flavor_alarm = len(flags) > 0
    alarm_severity = "WARN" if ai_flavor_alarm else "INFO"
    # severity 0-1：触发条件占比（封顶用，detail 见下）；qiaomu 共 9 个条件。
    severity = min(1.0, len(flags) / 9.0) if ai_flavor_alarm else 0.0
    alarm_detail = ("去AI味弱信号触发: " + ", ".join(flags)) if flags else "无去AI味弱信号"

    # ---- banned 硬项命中桶（白名单词表豁免，方向 G 闭环） ----
    issues = _check_banned_hard(text, banned, whitelist)

    result = {
        "enabled": True,
        "abstract": {"count": abstract_hits, "per_100": per100(abstract_hits)},
        "scene": {"count": scene_hits, "per_100": per100(scene_hits)},
        "hook": {"count": hook_hits, "per_100": per100(hook_hits)},
        "dash": {"count": dash_hits, "per_100": per100(dash_hits)},
        "aiish": {"count": aiish_total, "per_100": per100(aiish_total),
                  "breakdown": aiish_breakdown},
        "ambiguous": {"count": ambiguous_total, "per_100": per100(ambiguous_total),
                      "breakdown": ambiguous_breakdown},
        "dialogue": {"count": dialogue_lines, "per_100": per100(dialogue_lines)},
        "dialogue_ratio": _dialogue_ratio,
        "ai_flavor_alarm": ai_flavor_alarm,
        "alarm_severity": alarm_severity,
        "severity": round(severity, 4),
        "alarm_detail": alarm_detail,
        "ambiguous_exempted": _amb_exempted,
        "ambiguous_exempt_reason": _amb_exempt_reason,
        "flags": flags,
        "issues": issues,
    }
    return result


def _check_banned_hard(text, banned, whitelist=None):
    """遍历 banned.json 全部硬禁用项（标点/正则/模板），计「……」内不豁免的命中。

    白名单词表豁免（方向 G）：若被命中文本含任意白名单词（wl in matched），豁免该次命中。
    返回 issues 列表，每项 {type, value, count, matched, detail}。
    """
    issues = []
    if not banned:
        return issues
    wl = whitelist or set()

    def _kept(matches):
        """过滤掉白名单命中的匹配，返回保留的匹配文本列表。"""
        kept = []
        for m in matches:
            mm = m if isinstance(m, str) else (m[0] if m else "")
            if wl and any(w in mm.lower() for w in wl):
                continue
            kept.append(mm)
        return kept

    for b in banned.get("banned_punctuation", []) or []:
        kept = _kept(re.findall(re.escape(b), text))
        if kept:
            issues.append({"type": "punctuation", "value": b, "count": len(kept),
                           "matched": kept[0],
                           "detail": f"禁用标点「{b}」出现{len(kept)}处（来源 banned.json）"})
    for b in banned.get("banned_patterns", []) or []:
        try:
            matches = re.findall(b, text)
        except re.error:
            matches = [b] if b in text else []
        kept = _kept(matches)
        if kept:
            issues.append({"type": "pattern", "value": b, "count": len(kept),
                           "matched": kept[0],
                           "detail": f"禁用句式正则「{b}」命中{len(kept)}处（来源 banned.json）"})
    for b in banned.get("banned_templates", []) or []:
        kept = _kept(re.findall(re.escape(b), text))
        if kept:
            issues.append({"type": "template", "value": b, "count": len(kept),
                           "matched": kept[0],
                           "detail": f"禁用模板「{b}」出现{len(kept)}处（来源 banned.json）"})
    return issues


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python anti_ai_reporter.py <story.txt>")
        sys.exit(1)
    _path = sys.argv[1]
    _txt = open(_path, "r", encoding="utf-8", errors="replace").read()
    print(json.dumps(report_ai_flavor(_txt), ensure_ascii=False, indent=2))
