# -*- coding: utf-8 -*-
"""
deslop_reporter.py — 退化与泄漏检测引擎（核心 IP 质量扩展 · 方向 B）

纯正则 / 零依赖（仅标准库 re + json）。把退化检测思路（engineering leak + 退化）
下沉为本项目的
第十三节「退化与泄漏检测」。

红线约束（不可破）：
  - 不读取 / 修改 tools/fusion.py（互消层）。只读最终文本 + config。
  - 不泄露 corpus 字面：config 只存通用正则/阈值，报告只回显计数。
  - 质量扩展规则仅作 INFO / WARN / ISSUE 级弱信号，绝不产出 FAIL。
  - 8G 安全：KB 级词典常驻内存；单篇流式统计。

引号适配（与 qiaomu 增量一致）：
  - 本项目对话用「」。tier2 工程词 / soft placeholder 在「…」内豁免（角色读章/系统文/台词合法）。
  - tier1 工程词 / 截断 / 叙述复读不豁免（正文逃逸硬证据）。

用法（内部被 check_story.py 第十三节调用）:
    from tools.deslop_reporter import report_degeneration, load_degeneration_rules
"""
import os
import re
import json
from collections import Counter

# 配置路径：相对项目根（本文件位于 tools/，父目录即项目根），与 CWD 无关。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_PATH = os.path.join(_ROOT, "config", "degeneration_rules.json")

# 内联保守默认（config 缺失 / 解析失败时降级，不崩、不中断质检）。
_INLINE = {
    "version": "deslop-v1",
    "engineering_leak": {
        "tier1": ["细纲", "情节点", "卷纲", "功能标签", "目标情绪", "字数目标", "章首钩子", "章尾钩子"],
        "tier2": ["第[一二三四五六七八九十百零0-9]+章", "本章", "这一章", "上一章", "下一章", "上章", "下章", "前文", "后文", "伏笔", "读者", "任务描述"],
    },
    "repeat": {
        "long_sentence_min_visible_chars": 12,
        "long_sentence_min_occurrences": 3,
        "adjacent_line_min_visible_chars": 8,
    },
    "truncate": {
        "allowed_ending_punct": ["。", "！", "？", "…", "”", "」"],
    },
    "placeholder_refusal": {
        "blocking": [
            "作为(一个)?(AI|人工智能|大?语言模型)[^，。]{0,20}(无法|不能|抱歉|很抱歉)",
            "(此处|以下)[^，。]{0,10}(省略|待补|待续)",
            "未完待续|TODO|占位符|placeholder",
            "我(无法|不能)(继续写|生成|创作|续写|完成[^，。]{0,6}章)",
        ],
        "soft_dialogue_exempt": True,
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


def load_degeneration_rules(path=_DEFAULT_PATH):
    """加载 config/degeneration_rules.json。"""
    return _load_json(path, _INLINE, "degeneration_rules")


_PUNCT_RE = re.compile(r"[\s\W]")


def _visible_chars(s):
    """可见字计数（去空白与所有非单词字符，保留中文汉字），用于复读/截断阈值。"""
    return len(_PUNCT_RE.sub("", s))


# 复用 anti_ai_reporter 的引号脱敏（避免重复实现；失败时回退内联等价实现）。
try:
    from tools.anti_ai_reporter import _mask_quotes
except Exception:  # noqa: BLE001
    def _mask_quotes(text, quote_pairs=(("「", "」"), ("“", "”"))):
        result = text
        for left, right in quote_pairs:
            pat = re.escape(left) + r"[\s\S]*?" + re.escape(right)
            result = re.sub(pat, lambda m: " " * len(m.group(0)), result)
        return result


def _has_in_quotes(text, pattern):
    """回检 pattern 在 text 中的命中是否落在「」内（用于 tier2/placeholder 豁免判断）。"""
    try:
        for m in re.finditer(pattern, text):
            seg = text[:m.start()]
            if seg.count("「") - seg.count("」") > 0:
                return True
    except re.error:
        pass
    return False


def _check_repeat_long(masked, min_chars, min_occ):
    """长句(可见字≥min_chars)出现≥min_occ 次 → 返回该句信息或 None（引号内台词已 mask 豁免）。"""
    sentences = re.split(r"[。！？]|\n", masked)
    cnt = Counter()
    for s in sentences:
        if _visible_chars(s) >= min_chars:
            cnt[s.strip()] += 1
    for s, c in cnt.items():
        if c >= min_occ and _visible_chars(s) >= min_chars:
            return {"sentence": s.strip()[:30], "count": c}
    return None


def _check_repeat_adjacent(masked, min_chars):
    """紧邻整行重复(可见字≥min_chars) → 返回该行信息或 None（标题行「第N章」无标点会被剔除）。"""
    lines = [ln for ln in masked.split("\n") if _visible_chars(ln) >= min_chars]
    for i in range(len(lines) - 1):
        if lines[i] == lines[i + 1]:
            return {"line": lines[i].strip()[:30], "count": 2}
    return None


def _check_truncate(text, allowed_end):
    """末行（去尾随空白）末字符非 allowed_end → 返回末行或 None。"""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return None
    last = lines[-1].rstrip()
    if not last:
        return None
    if last[-1] not in allowed_end:
        return last
    return None


def merge_ai_flavor_signals(*reports):
    """合并 qiaomu(方向 A/B) + 退化(方向 B) + advisory(方向 H) 弱信号为单一 ai_flavor 层。

    每个 report 须含以下键之一：
      - qiaomu report: ai_flavor_alarm(bool) + severity(0-1 浮点) + alarm_detail(str)
      - 退化 deg report: degeneration_alarm(bool) + severity(0-1 浮点) + flags[list]
      - advisory report: advisory_alarm(bool) + severity(0-1 浮点) + flags[list]
    可为 None（引擎关闭或缺失），自动跳过。

    返回供 triple_cross_judge(ai_flavor=...) 的 dict：
        {"ai_flavor_alarm": bool, "severity": float, "alarm_detail": str}
    红线：verdict 恒 WARN，confidence 封顶 0.5（由 triple_cross_judge 保证），
    本函数只负责 OR 多告警 + MAX 多 severity。注意 qiaomu 的 alarm_severity 是字符串
    （"INFO"/"WARN"），severity 才是 0-1 浮点——这是此前 13节联调踩坑点（float("WARN") 崩溃）。
    """
    _merged_alarm = False
    _merged_sev = 0.0
    _details = []
    for r in reports:
        if not r:
            continue
        # qiaomu 报告（report_ai_flavor）：ai_flavor_alarm + severity(浮点)
        if r.get("ai_flavor_alarm"):
            _merged_alarm = True
            _qsev = float(r.get("severity", 0.0) or 0.0)
            _merged_sev = max(_merged_sev, _qsev)
            _details.append("qiaomu:" + str(r.get("alarm_detail", "")))
        # 退化报告（report_degeneration）：degeneration_alarm + severity(浮点)
        if r.get("degeneration_alarm"):
            _merged_alarm = True
            _osev = float(r.get("severity", 0.0) or 0.0)
            _merged_sev = max(_merged_sev, _osev)
            _flags = r.get("flags", []) or []
            _details.append("deslop:" + (",".join(_flags) if _flags else "退化信号"))
        # advisory 报告（report_advisory，方向 H）：advisory_alarm + severity(浮点)
        if r.get("advisory_alarm"):
            _merged_alarm = True
            _asev = float(r.get("severity", 0.0) or 0.0)
            _merged_sev = max(_merged_sev, _asev)
            _flags = r.get("flags", []) or []
            _details.append("advisory:" + (",".join(_flags) if _flags else "风格密度信号"))
        # quality_matrix 报告（方向 D）：show_dont_tell（画面感）唯一新增 WARN 源
        _sdt = r.get("show_dont_tell")
        if isinstance(_sdt, dict) and _sdt.get("alarm"):
            _merged_alarm = True
            _sdsev = float(_sdt.get("severity", 0.0) or 0.0)
            _merged_sev = max(_merged_sev, _sdsev)
            _sdt_signals = _sdt.get("signals", []) or []
            _details.append("quality_matrix:" + (",".join(_sdt_signals) if _sdt_signals else "画面感弱信号"))
    return {
        "ai_flavor_alarm": _merged_alarm,
        "severity": _merged_sev,
        "alarm_detail": " | ".join(_details) if _details else "无",
    }


def report_degeneration(text, rules=None, in_quotes_exempt=True):
    """方向 B：工程词泄漏 tier1/tier2 + 退化检测(复读/截断/占位符/拒绝语)。

    返回（契约，见设计文档 §3.4）：
      {
        "enabled": True,
        "engineering_leak": {"tier1": {"hits":[...], "level":"ISSUE|INFO"},
                              "tier2": {"hits":[...], "level":"WARN|INFO"}},
        "repeat": {"long_sentence": {...}|None, "adjacent_line": {...}|None},
        "truncate": {"violated": bool, "last_line": str},
        "placeholder": {"hits":[...], "level":"WARN|INFO"},
        "degeneration_alarm": bool, "severity": float(0-1),
        "flags": [str], "issues": [ {type,value,count,detail} ]
      }

    关键不变量：
      - tier1 命中 → issues（与 banned 硬项同级严重），不进终判；
      - tier2 / 退化软告警 → WARN 弱信号（合并进 ai_flavor）；
      - 「」内 tier2 / soft placeholder 豁免（台词合法），tier1 / 截断 / 叙述复读不豁免；
      - 标题行(第N章) / 引用块预剔除，防误杀；
      - 全函数 level ∈ {INFO, WARN, ISSUE}，绝不 FAIL。
    """
    if rules is None:
        rules = load_degeneration_rules()

    leak = rules.get("engineering_leak", {}) or {}
    tier1 = leak.get("tier1", []) or []
    tier2 = leak.get("tier2", []) or []
    rep_cfg = rules.get("repeat", {}) or {}
    trunc_cfg = rules.get("truncate", {}) or {}
    ph_cfg = rules.get("placeholder_refusal", {}) or {}

    long_min_chars = int(rep_cfg.get("long_sentence_min_visible_chars", 12))
    long_min_occ = int(rep_cfg.get("long_sentence_min_occurrences", 3))
    adj_min_chars = int(rep_cfg.get("adjacent_line_min_visible_chars", 8))
    allowed_end = trunc_cfg.get("allowed_ending_punct", ["。", "！", "？", "…", "”", "」"])
    ph_blocking = ph_cfg.get("blocking", []) or []
    ph_soft_exempt = bool(ph_cfg.get("soft_dialogue_exempt", True))

    # 引号脱敏（tier2 / soft placeholder 在「」内豁免）
    quote_pairs = [("「", "」"), ("“", "”")]
    masked = _mask_quotes(text, quote_pairs) if in_quotes_exempt else text

    flags = []
    issues = []

    # ---- tier1 工程词泄漏（正文逃逸硬证据，不豁免，→ issues） ----
    tier1_hits = []
    for t in tier1:
        n = text.count(t)
        if n > 0:
            tier1_hits.append({"term": t, "count": n})
            issues.append({"type": "engineering_leak_tier1", "value": t, "count": n,
                           "detail": f"工程词泄漏 tier1「{t}」出现{n}处（正文逃逸硬证据，来源 degeneration_rules）"})
    if tier1_hits:
        flags.append("tier1_leak")

    # ---- tier2 工程词泄漏（叙事层可能合法，引号内豁免，→ WARN） ----
    tier2_hits = []
    for p in tier2:
        try:
            n = len(re.findall(p, masked))
        except re.error:
            n = masked.count(p)
        if n > 0:
            tier2_hits.append({"term": p, "count": n, "in_quotes": _has_in_quotes(text, p)})
    if tier2_hits:
        flags.append("tier2_leak")

    # ---- 复读检测（masked 上跑，引号内台词豁免） ----
    repeat_long = _check_repeat_long(masked, long_min_chars, long_min_occ)
    repeat_adj = _check_repeat_adjacent(masked, adj_min_chars)
    if repeat_long:
        flags.append("repeat_long")
    if repeat_adj:
        flags.append("repeat_adjacent")

    # ---- 截断检测（原始文本末行，允许「…」合法结尾） ----
    trunc = _check_truncate(text, allowed_end)
    if trunc:
        flags.append("truncate")

    # ---- 占位符 / 拒绝语（soft 类对话行豁免；未完待续由第六节管，去重） ----
    ph_hits = []
    end300 = text[-300:] if len(text) > 300 else text
    for p in ph_blocking:
        try:
            n = len(re.findall(p, masked))
        except re.error:
            n = masked.count(p)
        if n > 0:
            managed_by_s6 = ("未完待续" in p) and ("未完待续" in end300)
            in_quotes = _has_in_quotes(text, p) if ph_soft_exempt else False
            exempt = in_quotes
            ph_hits.append({"pattern": p, "count": n, "in_quotes": in_quotes,
                            "exempt": exempt, "managed_by_s6": managed_by_s6})
            if not exempt and not managed_by_s6:
                issues.append({"type": "placeholder_refusal", "value": p, "count": n,
                               "detail": f"占位符/拒绝语「{p}」命中{n}处（来源 degeneration_rules）"})
    if ph_hits:
        flags.append("placeholder")

    degeneration_alarm = len(flags) > 0
    severity = min(1.0, len(flags) / 5.0) if degeneration_alarm else 0.0

    return {
        "enabled": True,
        "engineering_leak": {
            "tier1": {"hits": tier1_hits, "level": "ISSUE" if tier1_hits else "INFO"},
            "tier2": {"hits": tier2_hits, "level": "WARN" if tier2_hits else "INFO"},
        },
        "repeat": {"long_sentence": repeat_long, "adjacent_line": repeat_adj},
        "truncate": {"violated": bool(trunc), "last_line": trunc or ""},
        "placeholder": {"hits": ph_hits, "level": "WARN" if ph_hits else "INFO"},
        "degeneration_alarm": degeneration_alarm,
        "severity": round(severity, 4),
        "flags": flags,
        "issues": issues,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python deslop_reporter.py <story.txt>")
        sys.exit(1)
    _txt = open(sys.argv[1], "r", encoding="utf-8", errors="replace").read()
    print(json.dumps(report_degeneration(_txt), ensure_ascii=False, indent=2))
