# -*- coding: utf-8 -*-
"""
human_profile.py — 人类写作统计画像提取器（反向优化·风格对齐层数据源）

从 corpus（或指定分类）提取「人类写作」的统计指纹，用于：
  1. 风格对齐层：把人类分布区间注入生成 prompt
  2. 本地人类度判别器：对生成文本打分（朱雀 AI 检测的本地代理 / 反朱雀终判）
只提取统计分布，绝不复制字面文本。

v6.3.1 升级：
  - 修复分句 bug：原实现仅按 [。！？] 切句，语料中无句末标点的文件会被整体当成
    「一句」，导致 avg_sent_len 出现 800+ 字的物理不可能值，污染 p90 基准。
    现改用稳健分句（再按换行/逗号切超长伪句）。
  - 扩展「深层人类特征」（对齐朱雀真实判定维度：爆发性 burstiness / 词汇熵 /
    情感方差 / 机械过渡比 / 过渡多样性 / 离题率），供 humanity_scorer 与
    human_feature_injector 使用。

用法:
    python human_profile.py                              # 全 corpus 画像 -> data/_human_profile.json
    python human_profile.py --category 05_古代言情        # 某分类子画像
    python human_profile.py --out data/human_profile.json
"""
import re, os, sys, json, statistics, math
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CORPUS_ROOT = "corpus"
DEFAULT_OUT = os.path.join("data", "_human_profile.json")

# === 深层特征用的轻量词典（自包含，避免耦合重型模块） ===
MECH_TRANSITIONS = ["首先", "其次", "然后", "最后", "总之", "综上所述",
                    "第一", "第二", "第三", "其一", "其二"]
NATURAL_TRANSITIONS = ["事实上", "值得注意的是", "话说", "说来也怪", "偏巧",
                       "孰料", "谁知", "转念一想", "依我看", "巧的是",
                       "话分两头", "无独有偶", "换言之", "细想起来"]
DIGRESSION_MARKERS = ["说起", "话说", "扯句", "顺便", "题外话", "插一句",
                      "话头扯远", "闲话少说", "跑题", "顺便提一句"]
# 五类情绪词（高频、跨题材通用），用于情感方差
EMOTION_LEXICON = [
    # 喜
    "笑", "喜", "乐", "欢", "甜", "开心", "高兴", "雀跃",
    # 怒
    "怒", "恨", "恼", "火", "愤", "气急", "咬牙",
    # 哀
    "哭", "悲", "痛", "伤", "哀", "凄凉", "心碎", "落泪",
    # 惧
    "怕", "慌", "惧", "惊", "恐", "发抖", "窒息", "后背发凉",
    # 惊/反常
    "愣", "怔", "呆", "震撼", "难以置信", "崩塌", "碾压",
]


def count_chinese(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def _split_sentences(text):
    """稳健分句：按句末标点 + 换行 + 分号切；超长伪句再按逗号/顿号细分，
    避免把整篇无标点文本当成一个几百字的『巨句』污染句长统计。"""
    raw = re.split(r"[。！？!?；;\n]", text)
    sents = []
    for s in raw:
        s = s.strip()
        if not re.search(r"[\u4e00-\u9fff]", s):
            continue
        if len(re.findall(r"[\u4e00-\u9fff]", s)) > 200:
            for part in re.split(r"[，,、]", s):
                part = part.strip()
                if re.search(r"[\u4e00-\u9fff]", part):
                    sents.append(part)
        else:
            sents.append(s)
    return sents


def _char_entropy(text):
    """字符级香农熵（困惑度代理）：人类文本熵更高、信息密度不均。"""
    c = Counter(ch for ch in text if "\u4e00" <= ch <= "\u9fff")
    if len(c) <= 1:
        return 0.0
    total = sum(c.values())
    return -sum((v / total) * math.log2(v / total) for v in c.values())


def _ttr_2gram(text):
    """二元组类型-标记比（词汇多样性代理）：越低越重复。"""
    chars = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
    if len(chars) < 2:
        return 0.0
    grams = ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)]
    if not grams:
        return 0.0
    return len(set(grams)) / len(grams)


def extract_profile(text):
    """单文本统计特征（浅层 + 深层）。"""
    zh = count_chinese(text)
    sents = _split_sentences(text)
    n = len(sents) or 1
    excl = text.count("！")
    comma = text.count("，")
    q = text.count("「") + text.count("」")
    sent_lens = [len(re.findall(r"[\u4e00-\u9fff]", s)) for s in sents]
    avg_len = sum(sent_lens) / n
    sent_len_std = statistics.pstdev(sent_lens) if len(sent_lens) > 1 else 0.0
    short = sum(1 for l in sent_lens if l <= 5) / n
    # 深层
    lex_ent = _char_entropy(text)
    ttr = _ttr_2gram(text)
    # 情感方差：按段落统计情绪词密度，再取方差（人类有起伏，AI 常平直）
    paras = [p for p in re.split(r"\n{1,}|\u3000", text) if re.search(r"[\u4e00-\u9fff]", p)]
    if not paras:
        paras = sents
    emo_densities = []
    for p in paras:
        pc = max(1, count_chinese(p))
        emo_densities.append(sum(p.count(w) for w in EMOTION_LEXICON) / pc)
    emotion_var = statistics.pvariance(emo_densities) if len(emo_densities) > 1 else 0.0
    # 过渡结构
    mech = sum(text.count(w) for w in MECH_TRANSITIONS)
    nat = sum(text.count(w) for w in NATURAL_TRANSITIONS)
    total_trans = mech + nat
    mech_trans_ratio = mech / total_trans if total_trans else 0.0
    transition_diversity = len({w for w in NATURAL_TRANSITIONS if w in text}) / len(NATURAL_TRANSITIONS)
    dig = sum(text.count(w) for w in DIGRESSION_MARKERS)
    digression_rate = dig / (zh / 1000.0) if zh else 0.0
    return {
        "zh": zh,
        "n": n,
        "excl_per_sent": round(excl / n, 4),
        "comma_per_sent": round(comma / n, 4),
        "avg_sent_len": round(avg_len, 2),
        "short_sent_ratio": round(short, 4),
        "quote_density": round(q / zh, 6) if zh else 0.0,
        # 深层
        "sent_len_std": round(sent_len_std, 3),
        "lex_entropy": round(lex_ent, 4),
        "ttr_2gram": round(ttr, 4),
        "emotion_var": round(emotion_var, 6),
        "mech_trans_ratio": round(mech_trans_ratio, 4),
        "transition_diversity": round(transition_diversity, 4),
        "digression_rate": round(digression_rate, 4),
    }


PROFILE_KEYS = [
    "excl_per_sent", "comma_per_sent", "avg_sent_len", "short_sent_ratio",
    "quote_density", "sent_len_std", "lex_entropy", "ttr_2gram",
    "emotion_var", "mech_trans_ratio", "transition_diversity", "digression_rate",
]


def _stat(vals):
    v = sorted(vals)
    m = len(v)
    if m == 0:
        return {"mean": 0, "median": 0, "p10": 0, "p90": 0, "min": 0, "max": 0}
    return {
        "mean": round(statistics.mean(v), 4),
        "median": round(statistics.median(v), 4),
        "p10": round(v[max(0, m // 10)], 4),
        "p90": round(v[min(m * 9 // 10, m - 1)], 4),
        "min": round(min(v), 4),
        "max": round(max(v), 4),
    }


def build_corpus_profile(corpus_root=CORPUS_ROOT, category=None):
    """扫 corpus（或某分类）汇总统计画像。"""
    # 递归遍历 + 大小写不敏感匹配（修复 .TXT/.Txt 漏采，深层分类子目录不再遗漏）
    files = []
    root = os.path.join(corpus_root, category) if category else corpus_root
    for _dp, _dn, _fns in os.walk(root):
        for _fn in _fns:
            if _fn.lower().endswith(".txt"):
                files.append(os.path.join(_dp, _fn))
    def _read_file(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    rows = [extract_profile(_read_file(f)) for f in files]
    if not rows:
        return {"files": 0}
    profile = {"files": len(rows)}
    for k in PROFILE_KEYS:
        profile[k] = _stat([r[k] for r in rows])
    return profile


def load_or_build(out_path=DEFAULT_OUT, corpus_root=CORPUS_ROOT, category=None):
    """加载缓存画像；不存在或指定分类则重建并保存（分类画像存独立路径，不覆盖全量）。"""
    if category is not None:
        base, ext = os.path.splitext(out_path)
        out_path = f"{base}_{category}{ext}"
    if category is None and os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            import sys
            print(f"[human_profile] 画像缓存损坏，将重建: {e}", file=sys.stderr)
    prof = build_corpus_profile(corpus_root, category)
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(prof, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError) as e:
        import sys
        print(f"[human_profile] 画像保存失败: {e}", file=sys.stderr)
    return prof


def main():
    args = sys.argv[1:]
    category = None
    out = DEFAULT_OUT
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--category" and i + 1 < len(args):
            category = args[i + 1]; i += 2
        elif a == "--out" and i + 1 < len(args):
            out = args[i + 1]; i += 2
        else:
            i += 1
    prof = load_or_build(out, CORPUS_ROOT, category)
    print(json.dumps(prof, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
