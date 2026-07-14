# -*- coding: utf-8 -*-
"""
local_discriminator.py — 本地叙事级人类度 / AI 度判别器（本地三交叉终判·叙事层）

设计依据：docs/system_design.md（熔铸版 v6.3 本地优先优化架构）。
定位：三方交叉终判的「叙事层」。phase1 纯规则打分（无重型 ML）；phase2 可选 xgboost
本地重训（P2-T1，本文件预留接口，P0 不引入）。纯 jieba + 标准库，零重型依赖。

核心约束（三红线）：
  ① 不泄 corpus 字面：只处理特征向量（来自 narrative_features），不缓存原文；
  ② 不动互消层：本模块只分析生成文本，不读取或修改 fusion.py；
  ③ 零模型 / CPU 友好 / 8G 安全：判定时只读单篇 + 落盘基线，无全量载入。

接口（与 design doc §3.3 对齐）：
  score(text, baseline=None) -> dict
      {human_score, ai_score, narrative_deviation, triggered_features, features}
  narrative_rarity(features, baseline=None) -> float   # 0-1，越高越像人类原创

设计要点（防单点）：
  叙事层**绝不**替代朱雀成为新单点终判；它只是三交叉之一，输出可解释信号。
  narrative_rarity 用于补偿 Bloom 对套话/成语的误命中（方向⑤）。
"""
import os
import sys
import json
import math

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── 同目录模块导入（确保从任意 cwd 运行都能找到 narrative_features）
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from narrative_features import (
    extract_narrative_features,
    load_taxonomy,
    NarrativeTaxonomy,
    DEFAULT_BASELINE_PATH,
)

# ── AI-tell 信号权重表（规则化，可解释）
# kind:
#   "high_is_ai"  : 取值越高越像 AI（如情节过度线性）
#   "low_is_ai"   : 取值越低越像 AI（如情绪弧方差过低、节奏单一）
#   "high_is_human": 取值越高越像人类（如道德模糊）
#   "near_zero_is_ai": 取值接近 0 且整体冲突低 → 像 AI（如事件无升级）
_SIGNALS = [
    ("plot_linearity", "high_is_ai", 1.0, 0.80),
    ("subplot_count", "low_is_ai", 1.0, 1.5),
    ("emotion_arc_variance", "low_is_ai", 1.2, 0.15),
    ("pacing_variability", "low_is_ai", 1.0, 0.25),
    ("foreshadow_density", "low_is_ai", 1.0, 0.12),
    ("agency_complexity", "low_is_ai", 0.8, 3.0),
    ("temporal_complexity", "low_is_ai", 0.5, 0.15),
    ("protagonist_moral_ambiguity", "high_is_human", 0.8, 0.40),
    ("event_escalation_slope", "near_zero_is_ai", 0.6, 0.05),
]


# ============================================================
# 默认基线（corpus 基线未构建时的优雅降级）
# ============================================================
def _default_baseline(taxonomy=None):
    """从 taxonomy 默认值构造伪基线，使 score / narrative_rarity 在无 corpus 基线时仍可运行。"""
    tax = taxonomy or NarrativeTaxonomy()
    numeric = {}
    for f in tax["features"]:
        if f["type"] in ("scale", "ordinal"):
            lo, hi = f["range"]
            center = f.get("default", (lo + hi) / 2.0)
            half = max(1e-6, (hi - lo) / 2.0)
            numeric[f["name"]] = {
                "center": float(center),
                "half": float(half),
                "p10": float(center - 0.4 * half),
                "p90": float(center + 0.4 * half),
            }
    return {"numeric": numeric, "categorical": {}, "_default": True}


def load_baseline(path=None):
    """加载 data/_narrative_baseline.json；不存在返回 None（调用方降级为默认基线）。"""
    path = path or DEFAULT_BASELINE_PATH
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _as_baseline(baseline, taxonomy=None):
    """统一基线结构：保证含 numeric[name]={center,half,p10,p90}。"""
    if baseline and baseline.get("numeric"):
        return baseline
    return _default_baseline(taxonomy)


# ============================================================
# 偏离度 & 稀有度
# ============================================================
def narrative_deviation(features, baseline=None):
    """生成文本相对人类基线在数值特征空间的偏离（0 = 完全落在人类 p10–p90 带内）。

    仅统计「落在正常带之外」的部分（以 half 带宽为单位），平均得到
    平均多少个半带宽超出 —— 越大越偏离人类叙事分布。
    """
    base = _as_baseline(baseline)
    num = base["numeric"]
    total = 0.0
    cnt = 0
    for name, info in num.items():
        v = features.get(name)
        if not isinstance(v, (int, float)):
            continue
        p10 = info.get("p10", info.get("center", 0))
        p90 = info.get("p90", info.get("center", 0))
        lo = min(p10, p90)
        hi = max(p10, p90)
        half = info.get("half", (hi - lo) / 2.0 if hi > lo else 1e-6)
        if v < p10:
            total += (p10 - v) / half
            cnt += 1
        elif v > p90:
            total += (v - p90) / half
            cnt += 1
        else:
            cnt += 1  # 带内计权但偏离 0
    if cnt == 0:
        return 0.0
    return round(total / cnt, 4)


def narrative_rarity(features, baseline=None):
    """叙事稀有度 0–1（方向⑤）。

    StoryScope 实证：人类叙事在特征空间更稀有（百分位 0.71 vs AI 0.49），
    即 AI 叙事更靠近人类分布质心（更「通用/套话」），人类更分散/多变。
    故：质心距离 d 越大 → 越稀有 → 越像人类原创。

    返回：d / (d + R0)，质心处(d=0)→0（AI 式通用），远端→1（人类式多变）。
    """
    base = _as_baseline(baseline)
    num = base["numeric"]
    R0 = 1.0  # 一个半带宽视为「典型人类散布」参考尺度
    sq = 0.0
    cnt = 0
    for name, info in num.items():
        v = features.get(name)
        if not isinstance(v, (int, float)):
            continue
        center = info.get("center", 0.0)
        half = max(1e-6, info.get("half", 1.0))
        z = (v - center) / half
        sq += z * z
        cnt += 1
    if cnt == 0:
        return 0.0
    d = math.sqrt(sq / cnt)
    return round(d / (d + R0), 4)


# ============================================================
# 规则化判别（phase1）
# ============================================================
def _clip01(x):
    return max(0.0, min(1.0, x))


def _discriminate(features, baseline):
    """基于 AI-tell 信号表（corpus 基线自适应）计算 ai/human 证据权重。

    关键：阈值来自 corpus 人类基线的 p10–p90 正常带，而非固定常量——
    这样「人类样本」落在带内时不产生误判（弱信号≈中性），只有明显偏离
    人类分布（过低/过高）的文本才触发 AI 证据。符合 P0 纯规则 + 弱判别定位。
    返回 (ai_score, human_score, triggered)。
    """
    base = _as_baseline(baseline)
    num = base["numeric"]
    ai_w = 0.0
    human_w = 0.0
    triggered = []
    for name, kind, weight, _thr in _SIGNALS:
        v = features.get(name)
        info = num.get(name)
        if not isinstance(v, (int, float)) or info is None:
            continue
        lo = min(info.get("p10", 0.0), info.get("p90", 0.0))
        hi = max(info.get("p10", 0.0), info.get("p90", 0.0))
        med = info.get("median", (lo + hi) / 2.0)
        half = max(1e-6, info.get("half", (hi - lo) / 2.0 if hi > lo else 1.0))
        ai_c = 0.0
        human_c = 0.0
        if kind == "high_is_ai":
            # AI 倾向：高于人类正常带（如情节过度线性）
            if v > hi:
                ai_c = _clip01((v - hi) / (2.0 * half))
            elif v < lo:
                human_c = _clip01((lo - v) / (2.0 * half))
        elif kind == "low_is_ai":
            # AI 倾向：低于人类正常带（如情绪弧/节奏/伏笔过平、副线/角色过少）
            if v < lo:
                ai_c = _clip01((lo - v) / (2.0 * half))
            elif v > hi:
                human_c = _clip01((v - hi) / (2.0 * half))
        elif kind == "high_is_human":
            # 人类倾向：高于人类正常带（如道德模糊更明显）
            if v > hi:
                human_c = _clip01((v - hi) / (2.0 * half))
            elif v < lo:
                ai_c = _clip01((lo - v) / (2.0 * half))
        elif kind == "near_zero_is_ai":
            # AI 倾向：事件升级过于平直（贴近质心）；人类更分散
            spread = max(half, 1e-6)
            dist = abs(v - med)
            if dist < 0.25 * spread:
                ai_c = _clip01((0.25 * spread - dist) / (0.25 * spread))
            elif dist > spread:
                human_c = _clip01((dist - spread) / (2.0 * spread))
        ai_w += weight * ai_c
        human_w += weight * human_c
        if ai_c >= 0.4:
            triggered.append(name)
    denom = ai_w + human_w + 1e-6
    ai_score = round(100.0 * ai_w / denom, 1)
    human_score = round(100.0 - ai_score, 1)
    return ai_score, human_score, triggered


def score(text, baseline=None):
    """叙事层判别主入口。

    返回：
      {
        "human_score": float,        # 0-100 叙事层人类度
        "ai_score": float,           # 0-100 叙事层 AI 度
        "narrative_deviation": float,# 相对人类基线偏离（0=完全吻合）
        "triggered_features": list,  # 触发/异常特征名（可解释）
        "features": dict             # 17 字段（供上层复用，无原文）
      }
    """
    features = extract_narrative_features(text)
    base = _as_baseline(baseline)
    dev = narrative_deviation(features, base)
    ai_score, human_score, triggered = _discriminate(features, base)
    return {
        "human_score": human_score,
        "ai_score": ai_score,
        "narrative_deviation": dev,
        "triggered_features": triggered,
        "features": features,
    }


# ============================================================
# 命令行（本地自测 / 调试）
# ============================================================
def main():
    import argparse
    ap = argparse.ArgumentParser(description="本地叙事判别器（规则版）")
    ap.add_argument("text", nargs="?", help="待判别文本路径（.txt）")
    ap.add_argument("--baseline", default=None, help="叙事基线 JSON 路径")
    args = ap.parse_args()
    if not args.text:
        print("用法: python local_discriminator.py <story.txt> [--baseline path]")
        sys.exit(1)
    with open(args.text, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    base = load_baseline(args.baseline) if args.baseline else load_baseline()
    res = score(text, base)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
