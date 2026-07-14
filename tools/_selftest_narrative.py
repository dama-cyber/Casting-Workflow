# -*- coding: utf-8 -*-
"""P0-T1 本地自测：验证导入/抽取/判别/三交叉，零重型依赖、流式不 OOM。纯本地。"""
import os
import sys
import time
import glob

ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import narrative_features as nf
from narrative_features import extract_narrative_features, build_narrative_baseline
from local_discriminator import score, narrative_rarity, load_baseline
from humanity_scorer import triple_cross_judge
from bloom_guard import rarity_hook

OUT = os.path.join(ROOT, "output")
CORPUS = os.path.join(ROOT, "corpus")

# ── 红线性自检：零重型依赖
HEAVY = ["torch", "transformers", "xgboost", "datasketch", "text_dedup",
         "pybloom", "gptzero", "raid"]
loaded_heavy = [m for m in HEAVY if m in sys.modules]
print("[红线] 重型依赖已加载:", loaded_heavy if loaded_heavy else "无 ✅")

# ── 1) 抽样流式基线（仅 400 篇，验证流式抽取 + 基线聚合不 OOM）
t0 = time.time()
sample_files = []
for r, _, fs in os.walk(CORPUS):
    for fn in fs:
        if fn.endswith(".txt"):
            sample_files.append(os.path.join(r, fn))
        if len(sample_files) >= 400:
            break
    if len(sample_files) >= 400:
        break
feats_list = []
for p in sample_files:
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            txt = f.read()
        feats_list.append(extract_narrative_features(txt))
    except Exception:
        continue
sample_base = build_narrative_baseline(iter(feats_list))
print(f"[基线] 样本 {len(feats_list)} 篇，聚合耗时 {time.time()-t0:.2f}s，"
      f"数值字段数={len(sample_base['numeric'])} ✅")

# ── 2) 三类文本三交叉终判
with open(sample_files[0], encoding="utf-8", errors="replace") as f:
    human_text = f.read()
story_path = os.path.join(OUT, "story.txt")
if os.path.exists(story_path):
    with open(story_path, encoding="utf-8", errors="replace") as f:
        story_text = f.read()
else:
    story_text = ""
# 合成 AI-tell：极度线性、无副线、低情绪方差、低节奏变化、少角色、平淡升级
ai_text = ("他觉得事情很简单。她认为这很正常。他们觉得没有问题。"
           "日子一天天过去。一切都按部就班。他明白了这个道理。"
           "她接受了这个事实。生活继续着。没有什么变化。结局很平静。") * 20

cases = [("HUMAN_SAMPLE", human_text), ("GENERATED_STORY", story_text), ("AI_TELL_SYNTH", ai_text)]
for label, txt in cases:
    tc = triple_cross_judge(txt, baseline=sample_base)
    print("\n" + "=" * 28, label, "=" * 28)
    print("  verdict      :", tc["verdict"])
    for ln, ly in tc["layers"].items():
        extra = ""
        if ln == "statistical":
            extra = f" humanity={ly.get('humanity_score')}"
        if ln == "narrative":
            extra = f" human={ly.get('human_score')} dev={ly.get('deviation')}"
        print(f"    - {ln:12s}: {ly['verdict']} (conf={ly.get('confidence',0):.2f}){extra}")
    print("  rarity       :", tc["narrative_rarity"])
    print("  consensus    :", tc["consensus"][:140])

# ── 3) 优雅降级：baseline=None 时仍可运行
print("\n" + "=" * 28, "退化测试(baseline=None)", "=" * 28)
nd_default = score(human_text, None)
print("  score(baseline=None) human/ai:", nd_default["human_score"], nd_default["ai_score"],
      "dev:", nd_default["narrative_deviation"], "triggered:", nd_default["triggered_features"][:5])
print("  rarity(baseline=None):", narrative_rarity(nd_default["features"], None))

# ── 4) bloom_guard.rarity_hook 委托
print("\n[钩子] bloom_guard.rarity_hook:", rarity_hook(extract_narrative_features(ai_text), sample_base))

# ── 5) 红线性：抽取结果只含统计量（无原文）
assert all(isinstance(v, (int, float, str)) for v in extract_narrative_features(human_text).values())
print("\n[红线] 特征向量仅含数值/类型标签，无原文缓存 ✅")
print("\n=== 自测通过 ===")
