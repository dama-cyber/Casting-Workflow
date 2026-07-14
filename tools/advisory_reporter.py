# -*- coding: utf-8 -*-
"""
advisory_reporter.py — advisory 类质量密度告警引擎（核心 IP 质量扩展 · 方向 H）

纯正则 / 统计 / 零依赖（仅标准库 re + json）。把 advisory 风格密度检测思路
（排比 / 套词 / 低连接密度 / 碎句号 / 微动作 / 比喻密度 / 公文腔 /
过度精炼短段）以**启发式**下沉为本项目【十四、advisory 风格密度告警】。

⚠️ 启发式说明：未抓回外部精确正则真值，本实现基于中文写作常识 + 研究简报候选清单做
启发式密度检测。因本引擎**全 WARN 软信号**
（误报代价极低、红线绝对安全：只进 ai_flavor 弱信号层，conf≤0.5，绝不翻 FAIL），
启发式精度足够，后续抓回真值可校准阈值/正则。

红线约束（不可破）：
  - 不读取 / 修改 tools/fusion.py（互消层）。只读最终文本 + config。
  - 不泄露 corpus 字面：config 只存通用正则/阈值，报告只回显计数与率。
  - 全 WARN 级弱信号，绝不产出 FAIL；不并入全局 issues（不新增终判单点）。
  - 8G 安全：KB 级词典常驻内存；单篇流式统计。

引号适配（与 qiaomu 增量一致）：
  - 本项目对话用「」。微动作 / 比喻 / 公文腔词面统计在「…」内豁免（角色台词合法）。
  - 结构维（碎句号 / 排比 / 低连接 / 过度精炼短段）在原始文本统计，标题行（第N章）预剔除。

用法（内部被 check_story.py 第十四节调用）:
    from tools.advisory_reporter import report_advisory, load_advisory_rules
"""
import os
import re
import json

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_PATH = os.path.join(_ROOT, "config", "advisory_rules.json")

_INLINE = {
    "version": "advisory-v1",
    "min_chars_total": 200,
    "metrics": {
        "fragment_short": {"enabled": True, "max_ratio": 0.18, "short_sentence_max_visible_chars": 5},
        "parallelism": {"enabled": True, "min_consecutive": 3,
                        "patterns": ["有的[^。！？]*有的[^。！？]*有的",
                                     "一边[^。！？]*一边[^。！？]*一边"]},
        "micro_action": {"enabled": True,
                         "terms": ["眼皮一跳", "心口一沉", "胃里翻涌", "指尖一颤", "喉头一紧",
                                   "脊背一凉", "太阳穴突突", "呼吸一滞", "心头一跳", "指尖微凉"],
                         "per_1k_chars": 4.0},
        "metaphor_density": {"enabled": True,
                             "markers": ["像", "如", "似", "宛", "若", "仿佛", "犹如", "如同", "宛若"],
                             "max_per_1k_chars": 8.0},
        "low_connectivity": {"enabled": True,
                             "connectors": ["但是", "然而", "不过", "因为", "所以", "因此", "虽然", "尽管",
                                            "于是", "接着", "而", "却", "可是", "偏偏", "话说回来"],
                             "min_per_1k_chars": 2.0},
        "over_refined_short_para": {"enabled": True, "max_ratio": 0.20, "short_para_max_visible_chars": 10},
        "official_tone": {"enabled": True,
                          "terms": ["根据", "按照", "鉴于", "综上所述", "经研究决定", "予以",
                                    "进一步", "进行", "开展", "本着"],
                          "per_1k_chars": 3.0},
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


def load_advisory_rules(path=_DEFAULT_PATH):
    """加载 config/advisory_rules.json。"""
    return _load_json(path, _INLINE, "advisory_rules")


_PUNCT_RE = re.compile(r"[\s\W]")
_HAN_RE = re.compile(r"[\u4e00-\u9fff]")


def _visible_chars(s):
    """可见字计数（去空白与所有非单词字符，保留中文汉字）。"""
    return len(_PUNCT_RE.sub("", s))


def _han_count(s):
    """中文字数（用于每千字密度归一）。"""
    return len(_HAN_RE.findall(s))


try:
    from tools.anti_ai_reporter import _mask_quotes
except Exception:  # noqa: BLE001 - 复用引号脱敏，失败回退内联等价实现
    def _mask_quotes(text, quote_pairs=(("「", "」"), ("“", "”"))):
        result = text
        for left, right in quote_pairs:
            pat = re.escape(left) + r"[\s\S]*?" + re.escape(right)
            result = re.sub(pat, lambda m: " " * len(m.group(0)), result)
        return result


def _strip_title_lines(text):
    """剔除 '第N章' 标题行，避免排比/碎句检测误杀章节标题。"""
    out = []
    for ln in text.split("\n"):
        if re.match(r"^\s*第[一二三四五六七八九十百零0-9]+章", ln):
            continue
        out.append(ln)
    return "\n".join(out)


def report_advisory(text, rules=None):
    """方向 H：advisory 类质量密度告警。纯 WARN 软信号，绝不 FAIL。

    返回契约：
      {
        "enabled": True,
        "advisory_alarm": bool,
        "severity": float(0-1),
        "flags": [str],             # 触发的维名
        "details": {str: str},      # 维名 -> 人类可读说明
      }
    关键不变量：
      - 全 WARN 级，绝不 FAIL；不并入全局 issues（不新增终判单点）。
      - 「」内微动作/比喻/公文腔词面豁免；结构维剔除标题行。
    """
    if rules is None:
        rules = load_advisory_rules()
    m = rules.get("metrics", {}) or {}
    min_total = int(rules.get("min_chars_total", 200))

    total_han = _han_count(text)
    if total_han < min_total:
        return {"enabled": True, "advisory_alarm": False, "severity": 0.0,
                "flags": [], "details": {"_skip": f"中文字数 {total_han} < {min_total}，跳过 advisory 密度统计"}}

    per1k = total_han / 1000.0
    masked = _mask_quotes(text)              # 词面维在引号内豁免
    body = _strip_title_lines(text)          # 结构维剔除标题行

    flags = []
    details = {}

    # ---- fragment_short: 碎片化短句占比 ----
    mc = m.get("fragment_short", {})
    if mc.get("enabled", True):
        mx = int(mc.get("short_sentence_max_visible_chars", 5))
        ratio_max = float(mc.get("max_ratio", 0.18))
        sentences = [s for s in re.split(r"[。！？!?]", body) if s.strip()]
        if sentences:
            short_n = sum(1 for s in sentences if _visible_chars(s) <= mx)
            ratio = short_n / len(sentences)
            if ratio > ratio_max:
                flags.append("fragment_short")
                details["fragment_short"] = f"碎片化短句占比 {ratio:.0%}（>{ratio_max:.0%}），AI 断句跳跃感"

    # ---- parallelism: 排比 / 连续同结构（标题行已剔除，引号内豁免） ----
    pm = m.get("parallelism", {})
    if pm.get("enabled", True):
        masked_body = _mask_quotes(body)
        hit = False
        for pat in pm.get("patterns", []):
            if re.search(pat, masked_body):
                hit = True
                break
        if not hit:
            min_c = int(pm.get("min_consecutive", 3))
            first2 = [ln.strip()[:2] for ln in re.split(r"[。！？!?\n]", masked_body) if ln.strip()]
            run = 1
            for i in range(1, len(first2)):
                if first2[i] and first2[i] == first2[i - 1]:
                    run += 1
                    if run >= min_c:
                        hit = True
                        break
                else:
                    run = 1
        if hit:
            flags.append("parallelism")
            details["parallelism"] = "检测到排比/连续同结构句式（AI 套路感）"

    # ---- micro_action: 微动作套路密度（引号内豁免） ----
    mam = m.get("micro_action", {})
    if mam.get("enabled", True):
        thr = float(mam.get("per_1k_chars", 4.0))
        n = sum(masked.count(t) for t in mam.get("terms", []))
        if n / per1k > thr:
            flags.append("micro_action")
            details["micro_action"] = f"微动作套路 {n} 处（{n / per1k:.1f}/千字 > {thr}/千字），身体反应模板化"

    # ---- metaphor_density: 比喻标记密度（引号内豁免） ----
    md = m.get("metaphor_density", {})
    if md.get("enabled", True):
        thr = float(md.get("max_per_1k_chars", 8.0))
        n = sum(masked.count(mk) for mk in md.get("markers", []))
        if n / per1k > thr:
            flags.append("metaphor_density")
            details["metaphor_density"] = f"比喻标记 {n} 处（{n / per1k:.1f}/千字 > {thr}/千字），修辞密集"

    # ---- low_connectivity: 低连接密度（引号内豁免） ----
    lc = m.get("low_connectivity", {})
    if lc.get("enabled", True):
        thr = float(lc.get("min_per_1k_chars", 2.0))
        n = sum(masked.count(c) for c in lc.get("connectors", []))
        if n / per1k < thr:
            flags.append("low_connectivity")
            details["low_connectivity"] = f"转折/因果连接词 {n} 处（{n / per1k:.1f}/千字 < {thr}/千字），段落跳跃 AI 感"

    # ---- over_refined_short_para: 过度精炼短段占比 ----
    orp = m.get("over_refined_short_para", {})
    if orp.get("enabled", True):
        mx = int(orp.get("short_para_max_visible_chars", 10))
        ratio_max = float(orp.get("max_ratio", 0.20))
        paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
        if paras:
            short_n = sum(1 for p in paras if _visible_chars(p) <= mx)
            ratio = short_n / len(paras)
            if ratio > ratio_max:
                flags.append("over_refined_short_para")
                details["over_refined_short_para"] = f"过度精炼短段占比 {ratio:.0%}（>{ratio_max:.0%}），信息密度过低"

    # ---- official_tone: 公文腔密度（引号内豁免） ----
    ot = m.get("official_tone", {})
    if ot.get("enabled", True):
        thr = float(ot.get("per_1k_chars", 3.0))
        n = sum(masked.count(t) for t in ot.get("terms", []))
        if n / per1k > thr:
            flags.append("official_tone")
            details["official_tone"] = f"公文腔词 {n} 处（{n / per1k:.1f}/千字 > {thr}/千字），官方措辞 AI 感"

    advisory_alarm = len(flags) > 0
    severity = min(1.0, len(flags) / 7.0) if advisory_alarm else 0.0
    return {
        "enabled": True,
        "advisory_alarm": advisory_alarm,
        "severity": round(severity, 4),
        "flags": flags,
        "details": details,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python advisory_reporter.py <story.txt>")
        sys.exit(1)
    _txt = open(sys.argv[1], "r", encoding="utf-8", errors="replace").read()
    print(json.dumps(report_advisory(_txt), ensure_ascii=False, indent=2))
