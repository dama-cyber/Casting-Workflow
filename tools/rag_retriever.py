# -*- coding: utf-8 -*-
"""
rag_retriever.py — 受限约束检索（RAG 反向优化核心，绝不输出字面文本）

输入题材/标签，从 corpus 召回 top-k 相似源文（分类目录优先 + jieba 关键词兜底），
提取三类纯元数据约束：
    - style_profile    : 题材自适应人类风格画像（喂风格对齐层）
    - content_blacklist: 高频专名/设定黑名单（喂互消层，禁止直接复用）
    - type_formulas    : 高频类型公式（喂反模式层，供反转）
**绝不输出任何源文字面片段**，确保不破坏 100%原创核心。

用法:
    python rag_retriever.py --category 07_重生复仇 --top-k 5
    python rag_retriever.py --tags 重生,复仇,宅斗 --top-k 5 --out output/_rag_constraints.json
"""
import os, sys, re, glob, json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from human_profile import build_corpus_profile

try:
    import jieba
    _JIEBA = True
except ImportError:
    _JIEBA = False

CORPUS_ROOT = "corpus"
DEFAULT_OUT = os.path.join("output", "_rag_constraints.json")

# 类型公式关键词目录（与 anti_pattern 同源概念）
_TYPE_KEYWORDS = {
    "death": ["死", "杀", "亡", "毙", "灭", "葬", "毒", "血"],
    "rebirth": ["重生", "穿越", "回到", "醒来", "前世", "魂", "附身"],
    "setting": ["侯府", "王府", "皇宫", "京城", "将军", "宫", "宅", "村", "末世", "系统"],
    "betrayal": ["背叛", "出卖", "欺骗", "算计", "利用", "谋害"],
    "revenge": ["复仇", "报仇", "报复", "打脸", "碾压", "反转", "夺权"],
}


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _content_blacklist(files, top_n=12):
    """从 top-k 源文提取高频专名/设定词，作为禁止直接复用的黑名单。"""
    if not _JIEBA:
        return []
    counter = {}
    for f in files:
        t = _read(f)
        clean = re.sub(r"[^\u4e00-\u9fff]", "", t[: min(len(t), 20000)])
        for w in jieba.cut(clean):
            if re.match(r"[\u4e00-\u9fff]{2,4}$", w):
                counter[w] = counter.get(w, 0) + 1
    stop = {"一个", "没有", "自己", "什么", "他们", "我们", "不是", "这个", "那个",
            "已经", "知道", "可以", "起来", "现在", "还是", "如果", "因为", "所以",
            "但是", "然而", "不过", "只是", "就是", "看着", "说道", "真的", "时候"}
    items = [(w, c) for w, c in counter.items() if w not in stop]
    items.sort(key=lambda x: -x[1])
    return [w for w, _ in items[:top_n]]


def _type_formulas(files):
    """汇总 top-k 源文的高频类型公式关键词（供反模式层反转）。"""
    formulas = {}
    for cat, kws in _TYPE_KEYWORDS.items():
        hits = 0
        for f in files:
            t = _read(f)
            hits += sum(t.count(k) for k in kws)
        if hits > 0:
            formulas[cat] = hits
    return formulas


def retrieve(category=None, tags=None, top_k=5, corpus_root=CORPUS_ROOT):
    # 召回候选
    # 递归遍历 + 大小写不敏感匹配（修复 .TXT/.Txt 漏采，深层分类子目录不再遗漏）
    if category and os.path.isdir(os.path.join(corpus_root, category)):
        root = os.path.join(corpus_root, category)
    else:
        root = corpus_root
    candidates = []
    for _dp, _dn, _fns in os.walk(root):
        for _fn in _fns:
            if _fn.lower().endswith(".txt"):
                candidates.append(os.path.join(_dp, _fn))

    # 关键词召回：用 tags 与每篇 jieba 关键词重合度排序
    ranked = candidates
    if tags:
        tag_set = set(re.split(r"[,，\s]+", tags))
        if _JIEBA:
            def score(f):
                t = _read(f)
                words = set(jieba.cut(re.sub(r"[^\u4e00-\u9fff]", "", t[:20000])))
                return len(tag_set & words)
        else:
            def score(f):
                return len(tag_set & set(os.path.basename(f).split(".")[0]))
        ranked = sorted(candidates, key=score, reverse=True)

    top = ranked[:top_k]
    style = build_corpus_profile(corpus_root, category) if category else {}
    return {
        "category": category,
        "tags": tags,
        "top_k": top_k,
        "sources": [os.path.basename(f) for f in top],
        "style_profile": style,
        "content_blacklist": _content_blacklist(top),
        "type_formulas": _type_formulas(top),
    }


def main():
    args = sys.argv[1:]
    category = None
    tags = None
    top_k = 5
    out = DEFAULT_OUT
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--category" and i + 1 < len(args):
            category = args[i + 1]; i += 2
        elif a == "--tags" and i + 1 < len(args):
            tags = args[i + 1]; i += 2
        elif a == "--top-k" and i + 1 < len(args):
            top_k = int(args[i + 1]); i += 2
        elif a == "--out" and i + 1 < len(args):
            out = args[i + 1]; i += 2
        else:
            i += 1
    result = retrieve(category, tags, top_k)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
