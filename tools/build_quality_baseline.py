# -*- coding: utf-8 -*-
"""
build_quality_baseline.py — qiaomu E 语料阈值标定（离线标定工具）

流式扫 corpus（100% 人类，朱雀判 100% 人类），复用三个开源借鉴检测器在语料上
的真实分布，标定各 WARN 阈值的「人类极端分位」，消除英文直觉词典误杀。

核心思路：
  - corpus 是 100% 人类作品，检测器在 corpus 上跑出的 density 分布即「人类基线」。
  - 每个 WARN 维度统计「当前阈值下的 corpus 触发率」= 该阈值对人类的误杀率。
  - 建议阈值 = 把人类触发率压到目标区间（默认 ~10%）的分位（high 维取 p90，low 维取 p10）。

产出 data/_quality_baseline.json：
  {
    "built_at": ..., "files": N, "target_trigger": 0.10,
    "dims": {
      "<维度名>": {"n","p10","p50","p90","mean",
                    "current_threshold","direction","trigger_rate","suggested_threshold"},
      ...
    }
  }

红线约束：
  - 离线统计工具：只读 corpus + 复用检测器；不写生成文本、不改 tools/fusion.py。
  - 8G 安全：单篇流式统计，只累积 float 列表（峰值内存极小）。
  - 不自动回写 config：仅产出建议阈值，由主理人审阅后回写（KB 级热调）。

用法（本文件位于 tools/，CWD 无关）:
    python build_quality_baseline.py                 # 全量扫 corpus -> data/_quality_baseline.json
    python build_quality_baseline.py --limit 100     # 抽样验证（不写全量）
    python build_quality_baseline.py --out /tmp/x.json
"""
import os
import re
import json
import sys
import statistics
import datetime

_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from anti_ai_reporter import report_ai_flavor
from quality_matrix import report_quality_matrix
from advisory_reporter import (report_advisory, load_advisory_rules,
                               _mask_quotes, _strip_title_lines)

ROOT = os.path.dirname(_TOOLS)
CORPUS_ROOT = os.path.join(ROOT, "corpus")
OUT_PATH = os.path.join(ROOT, "data", "_quality_baseline.json")

# P1-2 EI P1/P5 连词密度参考（轻量通用连词，独立于 EI 复杂逻辑，仅供标定参考）
CONJ = ["但是", "然而", "不过", "因为", "所以", "因此", "于是", "接着", "而", "却", "可是",
        "而且", "并且", "如果", "虽然", "尽管", "首先", "其次", "然后", "最后", "总之",
        "与此同时", "另外", "反之", "不然", "否则"]

TARGET_TRIGGER = 0.10  # 人类作品目标触发率上限

# 单篇读取字符上限：corpus 含大量中篇/短篇大文件（总 1.2G），全量读+3 检测器正则
# 在超大文件上极慢。密度统计按 per-1k-chars 计算，前 40k 字符（≈40 窗口）已足够代表
# 写作风格；截断仅限速 I/O 与正则，不改变统计总体（大文件仍被纳入，只是取开头段）。
MAX_CHARS = 40000


def _han(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text)) or 1


def _pct(vals, p):
    if not vals:
        return 0.0
    v = sorted(vals)
    n = len(v)
    return round(v[min(n - 1, max(0, int(round(p * (n - 1)))))], 4)


def _stat(vals):
    if not vals:
        return {"n": 0, "p10": 0, "p50": 0, "p90": 0, "mean": 0}
    return {"n": len(vals),
            "p10": _pct(vals, 0.10), "p50": _pct(vals, 0.50), "p90": _pct(vals, 0.90),
            "mean": round(statistics.mean(vals), 4)}


def _visible_chars(s):
    return len(re.sub(r"[\s\W]", "", s))


def _collect_advisory_densities(text, per1k, rules):
    """复用 advisory 词典 + 脱敏函数，按与 report_advisory 完全一致公式算各维密度/占比。"""
    m = rules.get("metrics", {}) or {}
    masked = _mask_quotes(text)
    body = _strip_title_lines(text)
    out = {}
    mam = m.get("micro_action", {})
    if mam.get("enabled", True):
        n = sum(masked.count(t) for t in mam.get("terms", []))
        out["micro_action"] = n / per1k
    md = m.get("metaphor_density", {})
    if md.get("enabled", True):
        n = sum(masked.count(mk) for mk in md.get("markers", []))
        out["metaphor_density"] = n / per1k
    lc = m.get("low_connectivity", {})
    if lc.get("enabled", True):
        n = sum(masked.count(c) for c in lc.get("connectors", []))
        out["low_connectivity"] = n / per1k
    ot = m.get("official_tone", {})
    if ot.get("enabled", True):
        n = sum(masked.count(t) for t in ot.get("terms", []))
        out["official_tone"] = n / per1k
    fsc = m.get("fragment_short", {})
    if fsc.get("enabled", True):
        mx = int(fsc.get("short_sentence_max_visible_chars", 5))
        sents = [s for s in re.split(r"[。！？!?]", body) if s.strip()]
        if sents:
            short = sum(1 for s in sents if _visible_chars(s) <= mx)
            out["fragment_short"] = short / len(sents)
    orp = m.get("over_refined_short_para", {})
    if orp.get("enabled", True):
        mx = int(orp.get("short_para_max_visible_chars", 10))
        paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
        if paras:
            short = sum(1 for p in paras if _visible_chars(p) <= mx)
            out["over_refined_short_para"] = short / len(paras)
    return out


def scan(corpus_root=CORPUS_ROOT, limit=None):
    """流式扫 corpus，收集各维度 density 列表。"""
    files = []
    for dp, dn, fns in os.walk(corpus_root):
        for fn in fns:
            if fn.lower().endswith(".txt"):
                files.append(os.path.join(dp, fn))
    if limit:
        files = files[:limit]
    adv_rules = load_advisory_rules()
    dial_ratios, tell_dens, conj_dens = [], [], []
    adv_dens = {k: [] for k in ["micro_action", "metaphor_density", "low_connectivity",
                                "official_tone", "fragment_short", "over_refined_short_para"]}
    adv_parallelism = []
    n_total = len(files)
    for i, f in enumerate(files):
        try:
            with open(f, encoding="utf-8", errors="replace") as _fh:
                text = _fh.read(MAX_CHARS)
        except Exception as e:
            import sys
            print(f"[WARN] skip file: {e}", file=sys.stderr)
            continue
        if (i + 1) % 500 == 0 or i == 0:
            print(f"[BASELINE] 进度 {i+1}/{n_total} ({(i+1)/n_total*100:.1f}%)", flush=True)
        zh = _han(text)
        per1k = zh / 1000.0
        _ai = report_ai_flavor(text)
        _qm = report_quality_matrix(text)
        _adv = report_advisory(text)
        dial_ratios.append(_ai.get("dialogue_ratio", 0.0))
        tell_dens.append(_qm.get("show_dont_tell", {}).get("tell_density", 0.0))
        conj_dens.append(sum(text.count(c) for c in CONJ) / per1k)
        ad = _collect_advisory_densities(text, per1k, adv_rules)
        for k in adv_dens:
            adv_dens[k].append(ad.get(k, 0.0))
        adv_parallelism.append(1 if "parallelism" in _adv.get("flags", []) else 0)
    return {"files": len(files), "dial_ratios": dial_ratios, "tell_dens": tell_dens,
            "conj_dens": conj_dens, "adv_dens": adv_dens, "adv_parallelism": adv_parallelism}


def _trigger_rate_and_suggest(density_list, current_threshold, direction, target=TARGET_TRIGGER):
    """direction: 'high'=密度高于阈值触发; 'low'=密度低于阈值触发。
    返回 (当前触发率, 建议阈值)。建议阈值把人类触发率压到 ~target。"""
    if not density_list:
        return (0.0, current_threshold)
    if direction == "high":
        trig = sum(1 for v in density_list if v > current_threshold) / len(density_list)
        sug = _pct(density_list, 1.0 - target)  # p90 使约 10% 人类触发
    else:
        trig = sum(1 for v in density_list if v < current_threshold) / len(density_list)
        sug = _pct(density_list, target)        # p10 使约 10% 人类触发
    return (round(trig, 4), round(sug, 4))


def calibrate(raw):
    """读当前各 config 阈值，结合 corpus 分布给出校准建议。"""
    with open(os.path.join(ROOT, "config", "anti_ai_rules.json"), encoding="utf-8") as f:
        ai_cfg = json.load(f)
    with open(os.path.join(ROOT, "config", "quality_matrix_rules.json"), encoding="utf-8") as f:
        qm_cfg = json.load(f)
    with open(os.path.join(ROOT, "config", "advisory_rules.json"), encoding="utf-8") as f:
        adv_cfg = json.load(f)
    ai_thr = float(ai_cfg.get("thresholds", {}).get("dialogue_ratio_min", 0.06))
    tell_thr = float(qm_cfg.get("show_dont_tell", {}).get("tell_density_warn", 3.0))
    adv_metrics = adv_cfg.get("metrics", {}) or {}
    adv_thr = {
        "micro_action": float(adv_metrics.get("micro_action", {}).get("per_1k_chars", 4.0)),
        "metaphor_density": float(adv_metrics.get("metaphor_density", {}).get("max_per_1k_chars", 8.0)),
        "low_connectivity": float(adv_metrics.get("low_connectivity", {}).get("min_per_1k_chars", 2.0)),
        "official_tone": float(adv_metrics.get("official_tone", {}).get("per_1k_chars", 3.0)),
        "fragment_short": float(adv_metrics.get("fragment_short", {}).get("max_ratio", 0.18)),
        "over_refined_short_para": float(adv_metrics.get("over_refined_short_para", {}).get("max_ratio", 0.20)),
    }
    dims = {}
    tr, sug = _trigger_rate_and_suggest(raw["dial_ratios"], ai_thr, "low")
    dims["dialogue_ratio"] = {**_stat(raw["dial_ratios"]), "current_threshold": ai_thr,
                              "direction": "low", "trigger_rate": tr, "suggested_threshold": sug}
    tr, sug = _trigger_rate_and_suggest(raw["tell_dens"], tell_thr, "high")
    dims["tell_density"] = {**_stat(raw["tell_dens"]), "current_threshold": tell_thr,
                            "direction": "high", "trigger_rate": tr, "suggested_threshold": sug}
    dims["conjunction_density"] = {**_stat(raw["conj_dens"]), "current_threshold": None,
                                   "direction": "ref", "trigger_rate": None,
                                   "suggested_threshold": round(_pct(raw["conj_dens"], 0.90), 4)}
    adv_dir = {"micro_action": "high", "metaphor_density": "high", "low_connectivity": "low",
               "official_tone": "high", "fragment_short": "high", "over_refined_short_para": "high"}
    for k in raw["adv_dens"]:
        tr, sug = _trigger_rate_and_suggest(raw["adv_dens"][k], adv_thr.get(k, 0.0), adv_dir[k])
        dims["advisory." + k] = {**_stat(raw["adv_dens"][k]), "current_threshold": adv_thr.get(k),
                                 "direction": adv_dir[k], "trigger_rate": tr, "suggested_threshold": sug}
    p = sum(raw["adv_parallelism"]) / len(raw["adv_parallelism"]) if raw["adv_parallelism"] else 0
    dims["advisory.parallelism"] = {"trigger_rate": round(p, 4),
                                    "note": "bool 维，无连续阈值，记录触发率参考"}
    return dims


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="抽样篇数（验证用）")
    ap.add_argument("--out", default=OUT_PATH, help="输出 JSON 路径")
    args = ap.parse_args()
    print(f"[BASELINE] 扫描 corpus: {CORPUS_ROOT} (limit={args.limit})")
    raw = scan(limit=args.limit)
    print(f"[BASELINE] 扫描完成 {raw['files']} 篇")
    dims = calibrate(raw)
    out = {"built_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "files": raw["files"], "target_trigger": TARGET_TRIGGER, "dims": dims}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[BASELINE] 已写出: {args.out}")
    for k, v in dims.items():
        sug = v.get("suggested_threshold")
        cur = v.get("current_threshold")
        print(f"  {k:28s} p10={v.get('p10')} p50={v.get('p50')} p90={v.get('p90')} "
              f"cur={cur} trig={v.get('trigger_rate')} sug={sug}")


if __name__ == "__main__":
    main()
