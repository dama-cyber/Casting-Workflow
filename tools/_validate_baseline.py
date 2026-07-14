# -*- coding: utf-8 -*-
"""
_validate_baseline.py — 真实 corpus 叙事基线验证（P0 交付后验证脚本）
主理人齐活林 / 熔铸版 v6.3 本地优先优化。

用途：基线构建完成后，用真实人类基线验证「叙事层判别」区分度。
- 正样本：corpus 中一篇真实人类文本（已判 100% 人类）
- 反样本：一段"AI 套路化"合成文本（高主题明示 / 单线 / 低道德模糊）
期望：正样本 human_score 高、narrative_deviation 低；反样本相反。
红线：不缓存 corpus 字面，仅打印路径与统计量。
"""
import os
import sys
import json
import glob

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import narrative_features as nf
import local_discriminator as ld
import humanity_scorer as hs

BASELINE_PATH = os.path.join(ROOT, "data", "_narrative_baseline.json")


def _pick_human_sample(corpus_root, max_chars=8000):
    """流式取第一篇 .txt 作为人类正样本（仅读前 max_chars，不缓存原文）。"""
    for root, _, files in os.walk(corpus_root):
        for fn in files:
            if fn.lower().endswith(".txt"):
                p = os.path.join(root, fn)
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        txt = f.read(max_chars)
                except Exception:
                    continue
                return os.path.relpath(p, corpus_root), txt
    return None, ""


def _synthetic_ai_text():
    """一段刻意"AI 套路化"的合成文本：单一主角、主题明示、单线、低道德模糊、无伏笔。"""
    return (
        "这是一个关于成长的故事。主人公小明代表着每一个平凡的年轻人，"
        "这意味着人生需要勇气。正如古人云，天道酬勤。故事告诉我们，"
        "只要努力就能成功。小明从小就很听话，他明白学习的重要性。"
        "后来他考上了大学，这象征着希望。其实成功并不难，"
        "关键在于坚持。小明最终获得了幸福，这揭示了奋斗的意义。"
        "这个故事寓意深刻，提醒我们珍惜当下。所谓成长，无非是学会承担。"
        "总之，只要心怀梦想，未来一定光明。"
    )


def main():
    if not os.path.isfile(BASELINE_PATH):
        print("基线尚未构建：", BASELINE_PATH)
        sys.exit(1)
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        baseline = json.load(f)
    print(f"[基线] 来源 = {baseline.get('files')} 篇人类文本")
    print(f"[基线] 数值字段数 = {len(baseline.get('numeric', {}))}")

    # 正样本：真实人类
    rel, human_txt = _pick_human_sample(os.path.join(ROOT, "corpus"))
    # 反样本：合成 AI 套路
    ai_txt = _synthetic_ai_text()

    for label, txt in (("HUMAN(真实人类)", human_txt), ("AI(合成套路)", ai_txt)):
        print("=" * 60)
        print(f"样本: {label}  | 来源: {rel if label.startswith('HUMAN') else 'synthetic'}")
        feats = nf.extract_narrative_features(txt)
        sc = ld.score(txt, baseline)
        rarity = ld.narrative_rarity(feats, baseline)
        # Bloom 层：此处无真实 Bloom 位图，用 (fail_bool, detail) 元组模拟字面层 PASS
        bloom_result = (False, "模拟字面层PASS(无字面命中)")
        tc = hs.triple_cross_judge(txt, bloom_result, baseline)
        print(f"  人类分={sc['human_score']:.3f}  AI分={sc['ai_score']:.3f}  "
              f"叙事偏离={sc['narrative_deviation']:.3f}  稀有度={rarity:.3f}")
        print(f"  触发特征={sc['triggered_features']}")
        print(f"  三交叉 verdict={tc['verdict']}  layers={tc['layers']}  consensus={tc['consensus']}")

    print("=" * 60)
    print("验证完成：若 HUMAN 人类分>AI 且偏离更低、AI 样本相反，则叙事层区分度成立。")


if __name__ == "__main__":
    main()
