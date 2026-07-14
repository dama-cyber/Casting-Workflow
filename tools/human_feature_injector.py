# -*- coding: utf-8 -*-
"""
human_feature_injector.py — 人类特征校准器（反朱雀·风格对齐层扩展，v6.3.1）

基于 corpus 画像与朱雀真实判定维度，对生成文本做：
  1. analyze(text)              深度特征分析（爆发性/词汇熵/情感方差/机械过渡比…）
  2. report(text, profile)      人类度缺口报告（供 LLM 二次改写 / 人审参考）
  3. apply_light_transitions(t) 保守过渡词替换（仅替换列表式机械过渡，
                                需显式 --humanize 开启）

原则：本模块是「统计指纹对齐」工具，不保证过真·朱雀；自动改写仅做最保守的
过渡词同义替换，避免引入新的人工痕迹。重度校准建议走 LLM 二次改写 + 人审。

用法:
    python human_feature_injector.py output/story.txt
    python human_feature_injector.py output/story.txt --humanize
"""
import re, os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from human_profile import (
    extract_profile, load_or_build,
    MECH_TRANSITIONS, NATURAL_TRANSITIONS,
)

# 保守同义替换表（仅作用于"列表式机械过渡 + 后接标点"，避免误伤语义）
_LIGHT_SWAP = {
    "首先": "起初",
    "其次": "再说",
    "然后": "随后",
    "最后": "末了",
    "总之": "说到底",
    "综上所述": "统共说来",
    "第一": "其一",
    "第二": "其二",
    "第三": "其三",
}

# 非机械过渡采样池（供 LLM 提示 / 人工替换参考）
NATURAL_POOL = list(NATURAL_TRANSITIONS)


def analyze(text):
    return extract_profile(text)


def report(text, profile=None):
    if profile is None:
        profile = load_or_build()
    cur = extract_profile(text)
    lines = ["人类度缺口报告（基于 corpus 画像）:"]
    specs = [
        ("sent_len_std", "爆发性 burstiness", "偏低→制造长短交错；偏高→适度并句"),
        ("lex_entropy", "词汇熵", "偏低→增加词汇多样性/罕见字；偏高→适度收敛"),
        ("ttr_2gram", "词汇多样性", "偏低→避免重复用词"),
        ("emotion_var", "情感方差", "偏低→让情绪随段落起伏；偏高→收敛情绪峰谷"),
        ("mech_trans_ratio", "机械过渡比", "偏高→替换 首先/其次/最后 为非程式过渡"),
        ("transition_diversity", "过渡多样性", "偏低→多用 事实/上/话说/话分两头 等"),
    ]
    for key, label, advice in specs:
        p = profile.get(key, {})
        lo, hi = p.get("p10"), p.get("p90")
        v = cur.get(key)
        if lo is None or hi is None or lo == hi:
            lines.append(f"  [{label}] 当前 {v}（基准缺失，跳过）")
            continue
        flag = "OK" if lo <= v <= hi else ("偏低" if v < lo else "偏高")
        lines.append(
            f"  [{label}] 当前 {v} | 人类区间 [{lo}, {hi}] | {flag}"
            f" → {advice if flag != 'OK' else '保持'}"
        )
    return "\n".join(lines)


def apply_light_transitions(text):
    """保守替换列表式机械过渡（仅当后接标点/空白/行尾，避免误伤语义）。
    返回 (新文本, 替换数)。"""
    out = text
    n = 0
    for mech, alt in _LIGHT_SWAP.items():
        pat = re.compile(re.escape(mech) + r"(?=[，。：、；\s]|$)")
        out, c = pat.subn(alt, out)
        n += c
    return out, n


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    humanize = "--humanize" in sys.argv
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    prof = load_or_build()
    print(report(text, prof))
    if humanize:
        new_text, n = apply_light_transitions(text)
        bak = path + ".bak"
        if not os.path.exists(bak):
            with open(bak, "w", encoding="utf-8") as f:
                f.write(text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_text)
        print(f"\n[humanize] 已保守替换 {n} 处机械过渡，备份原文件于 {bak}")


if __name__ == "__main__":
    main()
