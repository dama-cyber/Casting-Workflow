# -*- coding: utf-8 -*-
"""
check_padding.py — 反凑字数护栏（反 padding 守卫，v6.3.1）

检测生成文本中"加宽式凑字数"的嫌疑段：
  1. 低信息密度段：功能词(的/了/是/在…)占比过高 + 长度偏长 → 疑似注水
  2. 近重复句：相邻语义高度相似句 → 疑似重复同一个点
  3. 展示不足(tell>show)：抽象概括句占比高、感官/动作动词少 → 疑似空泛
输出风险报告与 padding_risk 评分(0-100, 越高越疑似凑字数)。

用法:
    python check_padding.py output/story.txt
    python check_padding.py output/story.txt --json
"""
import re, os, sys, json

FUNC_WORDS = set(
    "的了吗呢啊吧着过地和得与及或但对就也都很更太最之其为被把将已才恰虽固因所但然而过且并若如跟同给让叫使令比"
)
VERBS = set(
    "说看听跑跳走打杀骂笑哭喊叫拿放推拉扯抱握站坐躺蹲趴摔跌撞冲扑咬吞吃喝吐喷砸烧死活做干搞弄写读想知懂会能要想要想念爱恨怕惊慌怒喜悲痛伤离弃背叛骗隐瞒救帮护守等送收买卖换借还追逃躲闪避拦挡格架接踢踹踩踏蹬碾挤"
)
SENSORY = set(
    "声光色香味冷暖疼痒酸麻涩咸甜苦辣红绿蓝白黑亮暗灰腥膻臭烫凉滑糙软硬轻重快慢尖钝"
)


def split_paragraphs(text):
    return [p for p in re.split(r"\n{1,}", text) if re.search(r"[\u4e00-\u9fff]", p)]


def split_sentences(text):
    return [s for s in re.split(r"[。！？!?]", text) if re.search(r"[\u4e00-\u9fff]", s)]


def paragraph_info(p):
    zh = [c for c in p if "\u4e00" <= c <= "\u9fff"]
    n = len(zh)
    if n == 0:
        return None
    func = sum(1 for c in zh if c in FUNC_WORDS)
    verbs = sum(1 for c in zh if c in VERBS)
    sensory = sum(1 for c in zh if c in SENSORY)
    return {
        "zh": n,
        "func_ratio": round(func / n, 3),
        "verb_ratio": round(verbs / n, 3),
        "sensory": sensory,
    }


def near_dup_sentences(sents, thresh=0.6):
    """返回相邻句相似度超阈值的对数（字符集合 Jaccard 近似）。"""
    pairs = []
    for i in range(len(sents) - 1):
        a = set(re.findall(r"[\u4e00-\u9fff]", sents[i]))
        b = set(re.findall(r"[\u4e00-\u9fff]", sents[i + 1]))
        if not a or not b:
            continue
        j = len(a & b) / len(a | b)
        if j >= thresh:
            pairs.append((i, round(j, 2)))
    return pairs


def check(text):
    paras = split_paragraphs(text)
    info = [paragraph_info(p) for p in paras]
    info = [x for x in info if x]
    # 1. 低信息密度段
    low_info = []
    for idx, d in enumerate(info):
        if d["zh"] >= 80 and d["func_ratio"] >= 0.38:
            low_info.append((idx, d))
    # 2. 近重复句
    dups = near_dup_sentences(split_sentences(text))
    # 3. 展示不足：平均动词比低
    avg_verb = sum(d["verb_ratio"] for d in info) / max(1, len(info))
    # 评分
    risk = 0
    risk += min(40, len(low_info) * 8)
    risk += min(30, len(dups) * 10)
    risk += min(30, max(0, (0.12 - avg_verb)) * 250)
    risk = round(min(100, risk), 1)
    return {
        "paragraphs": len(info),
        "low_info_paras": [
            {"idx": i, "zh": d["zh"], "func_ratio": d["func_ratio"]} for i, d in low_info
        ],
        "near_dup_sentence_pairs": len(dups),
        "avg_verb_ratio": round(avg_verb, 3),
        "padding_risk": risk,
        "verdict": "疑似凑字数" if risk >= 50 else ("轻度风险" if risk >= 25 else "OK"),
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    res = check(text)
    if "--json" in sys.argv:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"段落数: {res['paragraphs']}")
        print(f"低信息密度段(疑似注水): {len(res['low_info_paras'])}")
        for p in res["low_info_paras"][:10]:
            print(f"  段落#{p['idx']} 字数={p['zh']} 功能词比={p['func_ratio']}")
        print(f"近重复句对: {res['near_dup_sentence_pairs']}")
        print(f"平均动词比: {res['avg_verb_ratio']}")
        print(f"padding_risk = {res['padding_risk']} → {res['verdict']}")


if __name__ == "__main__":
    main()
