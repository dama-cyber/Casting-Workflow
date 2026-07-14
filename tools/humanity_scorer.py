# -*- coding: utf-8 -*-
"""
humanity_scorer.py — 本地人类度判别器（朱雀 AI 检测的本地代理 / 反朱雀终判）

用 corpus 人类写作统计画像作基准，对生成文本的多维统计量打分：越接近人类分布，
人类度越高（0-100）。替代朱雀 API 终判，零新增依赖。

v6.3.1 起覆盖「浅层 + 深层」共 11 维：浅层（句长/标点/短句/对话密度）+ 深层
（爆发性 burstiness / 词汇熵 / 词汇多样性 / 情感方差 / 机械过渡比 / 过渡多样性），
深层维度对齐朱雀真实判定逻辑。

重要边界：本判别器只是「朱雀」的本地统计代理，能近似"像不像人"，但无法替代
真实朱雀 API 的 verdict；原创性（Bloom 16字零匹配）与"像人"（过朱雀）是两个独立目标。
与「100%原创审计」互补：
    审计管「是否抄源文」（16字零匹配）
    本判别器管「是否像人类」（统计分布吻合）

用法:
    python humanity_scorer.py output/story.txt
    python humanity_scorer.py output/story.txt --profile data/_human_profile.json
"""
import re, os, sys, json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from human_profile import extract_profile, load_or_build

# 各指标权重（v6.3.1：浅层句长/标点 + 深层人类特征，对齐朱雀真实判定维度）
# 说明：本判别器是「朱雀 AI 检测」的本地代理，只近似统计指纹，不代表真·朱雀 verdict。
# 注：emotion_var / mech_trans_ratio / transition_diversity 已计入画像(human_profile)，
#     但 corpus(网文语料) 三者分布近乎全零或全幅，作为「人类目标区间」会反噬正确的人类化
#     行为，故仅保留于画像与 human_feature_injector 参考，不参与本地打分。
_METRICS = [
    # 浅层（表面统计量）
    ("avg_sent_len", 0.12),          # 平均句长
    ("excl_per_sent", 0.06),         # ！/句
    ("comma_per_sent", 0.06),        # ，/句
    ("short_sent_ratio", 0.06),      # 短句占比
    ("quote_density", 0.06),         # 对话密度
    # 深层（朱雀真实判定维度近似，corpus 分布有意义者）
    ("sent_len_std", 0.30),          # 爆发性 burstiness（核心）
    ("lex_entropy", 0.20),           # 词汇熵 / 困惑度代理
    ("ttr_2gram", 0.14),             # 词汇多样性（类型-标记比）
]


def score_humanity(text, profile=None):
    if profile is None:
        profile = load_or_build()
    cur = extract_profile(text)
    details = {}
    total = 0.0
    for key, w in _METRICS:
        p = profile.get(key, {})
        if not p or p.get("p90", 0) == p.get("p10", 0):
            details[key] = {"cur": cur[key], "score": 100.0, "note": "基准缺失,默认满分"}
            total += w * 100.0
            continue
        lo, hi = p["p10"], p["p90"]
        v = cur[key]
        if lo <= v <= hi:
            s = 100.0
            note = "在区间内"
        else:
            span = max(hi - lo, 1e-6)
            dev = (lo - v) if v < lo else (v - hi)
            ratio = min(dev / span, 3.0)  # 偏离超3个区间宽则0分
            s = max(0.0, 100.0 - ratio * 33.0)
            note = "低于区间" if v < lo else "高于区间"
        details[key] = {"cur": v, "p10": lo, "p90": hi, "score": round(s, 1), "note": note}
        total += w * s
    return {"humanity_score": round(total, 1), "details": details, "cur": cur}


# ============================================================
# 本地三交叉终判（熔铸版 v6.3 新增）
# ============================================================
# 共识阈值：PASS / FAIL 需累计置信度 ≥ 该值且为最高票，否则保守落到 WARN。
# 目的：杜绝「任一单层 FAIL → 终判 FAIL」的单点脆弱性（与朱雀单点 / Bloom 0命中=PASS 同构脆弱）。
_CONSENSUS_THRESHOLD = 1.3


def _judge_literal(bloom_fail, detail):
    """字面层（Bloom 零模型位图）：0 命中=可靠 PASS；命中=疑似 FAIL；索引缺失=跳过。"""
    if detail and "未构建" in detail:
        return {"source": "bloom", "verdict": "WARN", "confidence": 0.4,
                "detail": "Bloom索引未构建，字面层无法判定（跳过）"}
    if bloom_fail:
        return {"source": "bloom", "verdict": "FAIL", "confidence": 0.7,
                "detail": detail or "Bloom 疑似命中（字面层）"}
    return {"source": "bloom", "verdict": "PASS", "confidence": 0.95,
            "detail": detail or "Bloom 零命中（字面层可靠 PASS）"}


def _judge_statistical(score):
    """统计层（既有 8 维朱雀代理）：高分=像人=PASS。"""
    if score >= 75:
        return {"source": "humanity_scorer", "verdict": "PASS", "confidence": 0.7,
                "humanity_score": score}
    if score >= 55:
        return {"source": "humanity_scorer", "verdict": "WARN", "confidence": 0.5,
                "humanity_score": score}
    return {"source": "humanity_scorer", "verdict": "FAIL", "confidence": 0.6,
            "humanity_score": score}


def _judge_narrative(human_score, deviation):
    """叙事层（local_discriminator 规则判别）：human_score 高=像人=PASS。"""
    if human_score >= 65:
        return {"source": "local_discriminator", "verdict": "PASS", "confidence": 0.6,
                "human_score": human_score, "deviation": deviation}
    if human_score >= 45:
        return {"source": "local_discriminator", "verdict": "WARN", "confidence": 0.5,
                "human_score": human_score, "deviation": deviation}
    return {"source": "local_discriminator", "verdict": "FAIL", "confidence": 0.6,
            "human_score": human_score, "deviation": deviation}


def _consensus(layers):
    """多数一致 + 阈值区间汇总三层 verdict。

    任一单层 FAIL 不直接定 FAIL；需累计置信度超阈值且为最高票，否则保守 WARN。
    """
    votes = {"PASS": 0.0, "WARN": 0.0, "FAIL": 0.0}
    for layer in layers.values():
        votes[layer["verdict"]] += layer.get("confidence", 0.0)
    if (votes["FAIL"] >= _CONSENSUS_THRESHOLD
            and votes["FAIL"] >= votes["PASS"] and votes["FAIL"] >= votes["WARN"]):
        verdict = "FAIL"
    elif (votes["PASS"] >= _CONSENSUS_THRESHOLD
          and votes["PASS"] >= votes["FAIL"] and votes["PASS"] >= votes["WARN"]):
        verdict = "PASS"
    else:
        verdict = "WARN"
    detail = " | ".join(
        f"{name}={lyr['verdict']}({lyr.get('confidence', 0):.2f})"
        for name, lyr in layers.items()
    )
    return verdict, (f"多数一致+阈值区间：PASS={votes['PASS']:.2f} "
                     f"WARN={votes['WARN']:.2f} FAIL={votes['FAIL']:.2f} → {verdict}；{detail}")


def triple_cross_judge(text, bloom_result=None, baseline=None, ai_flavor=None):
    """本地三交叉终判：Bloom(字面) + humanity_scorer(统计) + local_discriminator(叙事)。

    参数:
      text        : 待判定文本（生成文本）
      bloom_result: 可选 (fail_bool, detail_str)；为 None 时内部调用 bloom_check（若索引存在）
      baseline     : 可选叙事基线 dict；为 None 时尝试加载 data/_narrative_baseline.json
      ai_flavor    : 可选 dict（来自 anti_ai_reporter.report_ai_flavor）；仅当其
                     "ai_flavor_alarm" 为真时，注入一条 verdict="WARN" 的附加弱信号层。
                     **绝不修改 _consensus 逻辑**，confidence 封顶 0.5，数学上不可能把
                     终判翻成 FAIL；仅在三层本就 Borderline 时把 PASS 弱降为 WARN。

    返回:
      {
        "verdict": "PASS" | "WARN" | "FAIL",
        "layers": { literal / statistical / narrative (+ai_flavor 可选) 各自 {verdict, confidence, ...} },
        "consensus": str,
        "narrative_rarity": float
      }

    关键防单点：三方各自独立出 PASS/WARN/FAIL + 置信度，由本函数多数一致汇总；
    叙事层绝不作为新单点终判。qiaomu 去 AI 味弱信号同理，仅作 WARN 附加层。
    """
    # ── 叙事层（local_discriminator）
    nd_score = nd_load = nd_rarity = None
    try:
        from local_discriminator import (
            score as nd_score,
            load_baseline as nd_load,
            narrative_rarity as nd_rarity,
        )
    except (ImportError, ModuleNotFoundError):
        pass

    if baseline is None and nd_load is not None:
        baseline = nd_load()

    narrative_layer = None
    rarity = 0.0
    if nd_score is not None:
        try:
            nd = nd_score(text, baseline)
            narrative_layer = _judge_narrative(nd["human_score"], nd["narrative_deviation"])
            if nd_rarity is not None:
                rarity = nd_rarity(nd.get("features", {}), baseline)
        except Exception as e:
            narrative_layer = {"source": "local_discriminator", "verdict": "WARN",
                               "confidence": 0.3, "human_score": 0,
                               "deviation": 0.0, "detail": f"叙事层异常: {e}"}
    else:
        narrative_layer = {"source": "local_discriminator", "verdict": "WARN",
                           "confidence": 0.3, "human_score": 0, "deviation": 0.0,
                           "detail": "local_discriminator 未加载"}

    # ── 统计层（既有 humanity_scorer）
    try:
        stat = score_humanity(text)
        stat_score = stat["humanity_score"]
    except Exception as e:
        stat_score = 0.0
        stat = {"detail": f"统计层异常: {e}"}
    statistical_layer = _judge_statistical(stat_score)

    # ── 字面层（Bloom 零模型位图）
    if bloom_result is not None:
        bloom_fail, bloom_detail = bloom_result
    else:
        bloom_fail, bloom_detail = False, None
        try:
            from bloom_guard import bloom_check as _bloom_check
            bloom_detail, bloom_fail = _bloom_check(text, "data", strict=False)
        except Exception:
            bloom_detail = "Bloom 不可用"
    literal_layer = _judge_literal(bloom_fail, bloom_detail)

    layers = {
        "literal": literal_layer,
        "statistical": statistical_layer,
        "narrative": narrative_layer,
    }

    # ── qiaomu 去 AI 味弱信号层（方向 A/B 借鉴，非终判单点）──
    # 红线：verdict 恒为 WARN，confidence 封顶 0.5（远低于 FAIL 阈值 1.3），
    # 仅向 _consensus 的 WARN 票桶累加；_consensus 逻辑不变，数学上不可能翻成 FAIL。
    # 仅在三层本就 Borderline（PASS/WARN 势均）时，可能把 PASS 弱降为 WARN。
    if ai_flavor is not None and ai_flavor.get("ai_flavor_alarm"):
        _sev = float(ai_flavor.get("severity", 0.0) or 0.0)
        _conf = min(0.5, 0.2 + 0.3 * _sev)
        layers["ai_flavor"] = {
            "source": "anti_ai_rules",
            "verdict": "WARN",
            "confidence": round(_conf, 3),
            "detail": "qiaomu 去AI味弱信号(非终判): " + str(ai_flavor.get("alarm_detail", "")),
        }

    verdict, consensus = _consensus(layers)
    return {
        "verdict": verdict,
        "layers": layers,
        "consensus": consensus,
        "narrative_rarity": rarity,
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python humanity_scorer.py <story.txt> [--profile path]")
        sys.exit(1)
    path = sys.argv[1]
    prof_path = None
    if "--profile" in sys.argv:
        idx = sys.argv.index("--profile") + 1
        if idx < len(sys.argv):
            prof_path = sys.argv[idx]
    if prof_path and os.path.exists(prof_path):
        with open(prof_path, encoding="utf-8") as f:
            profile = json.load(f)
    else:
        profile = load_or_build()
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    res = score_humanity(text, profile)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
