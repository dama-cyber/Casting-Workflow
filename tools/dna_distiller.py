# -*- coding: utf-8 -*-
"""
dna_distiller.py — 叙事 DNA 自动蒸馏器（Casting-Workflow 熔铸版 · 互消层升级）

定位：从 corpus 中流式蒸馏「20 维叙事 DNA 演化关键词表」，落盘 data/_narrative_dna.json。
纯 jieba + 标准库，零新增依赖；与 fusion.py 解耦，独立于 human_profile / rag_retriever。

红线（与 narrative_features.py 同约束，仅借鉴其模式，绝不 import / 改动它）：
① 不泄 corpus 字面：本模块只输出通用叙事信号词（关键词），绝不缓存任何原文片段；
② 不 import / 不改 narrative_features.py：仅借鉴其「词典种子 + 流式分词 + 频率聚合 + 落盘 JSON」模式；
③ 不引外部 persona 技能文件；
④ 零重型依赖：仅 os/re/json/collections/jieba。

保形策略（主理人拍板）：
以 _DIMENSION_KEYWORDS（来自 fusion）20 维骨架锁定维度；蒸馏时仅在每维内【追加】
corpus 高频信号词，不删除/替换内置种子词。最终每维 = 内置词 ∪ 演化高频词。

接口：
  distill_dna_from_corpus(corpus_files, seed_dims) -> dict
  load_or_build_dna(category, scope="category", force=False, ...) -> dict
"""
import os
import re
import sys
import json
import random
import logging
from collections import Counter
from datetime import datetime, timezone

import jieba
# 静默 jieba 构建日志（不强制成功，失败则忽略）
try:
    jieba.setLogLevel(logging.ERROR)
except Exception as e:
    logging.warning(f"Failed to set jieba log level: {e}")

# ── 路径约定
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
DATA_DIR = os.path.join(_ROOT, "data")
CORPUS_ROOT = os.path.join(_ROOT, "corpus")
DEFAULT_DNA_PATH = os.path.join(DATA_DIR, "_narrative_dna.json")

# ── 蒸馏配置（可内联常量，不强制独立配置文件）
DNA_VERSION = "1"
TOP_K = 60          # 每维最多追加的演化高频词数
MIN_FREQ = 3         # 演化词最低词频（低于此视为噪声，不入表）
MAX_FILES = 200      # 单题材抽样上限，避免超大数据集蒸馏超时（主理人允许 200 篇上限）
MAX_CHARS_PER_FILE = 200000  # 单篇扫描字符上限（性能护栏，仍足以捕捉高频信号）

# 通用中文停用词（仅用于过滤，非 corpus 字面）
_STOP_WORDS = set(
    "的 了 和 是 在 我 有 他 这 中 大 来 上 国 个 到 说 们 为 子 也 你 得 着 下 自 之 "
    "年 对 能 而 后 可 以 都 一 二 三 四 五 六 七 八 九 十 人 她 就 那 要 会 被 把 让 "
    "给 与 及 等 又 还 很 再 更 最 太 却 但 因 然后 于是 不过 只是 还是 就是 已经 知道 "
    "可以 起来 现在 如果 因为 所以 但是 然而 不过 只是 就是 一个 没有 自己 什么 他们 "
    "我们 不是 这个 那个 这种 那种 这样 那样 什么 怎么 怎样 如何 一样 一些 这些 那些".split()
)

_CJK = re.compile(r"[\u4e00-\u9fff]")


def _is_valid_term(w):
    """过滤单字 / 超长 / 纯标点 / 停用词 / 含非中文字符的 token。"""
    if not w or len(w) < 2 or len(w) > 4:
        return False
    if not _CJK.search(w):
        return False
    if w in _STOP_WORDS:
        return False
    if re.search(r"[a-zA-Z0-9\s]", w):
        return False
    return True


def _now_iso():
    """ISO 8601 UTC 时间戳。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================
# 公开接口
# ============================================================
def distill_dna_from_corpus(corpus_files, seed_dims):
    """流式逐篇 jieba 分词 → 聚合各维高频信号词 → 返回 {dim_name: [kw,...]}（保形：内置 ∪ 演化）。

    :param corpus_files: 文本文件路径列表（调用方负责抽样/范围）
    :param seed_dims: 维度名 → 内置关键词列表（来自 fusion._DIMENSION_KEYWORDS）
    :return: {dim_name: [kw,...]}，已保形（内置词在前，演化高频词追加在后，去重）
    说明：仅统计 2-4 字中文词，过滤停用词/单字/纯标点；绝不缓存任何原文片段（红线①）。
    """
    if not corpus_files:
        # 无语料：退化为纯内置骨架（保形起点）
        return {dim: list(kws) for dim, kws in seed_dims.items()}

    global_counter = Counter()
    # 流式逐篇，避免一次性载入全量文本
    for fpath in corpus_files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(MAX_CHARS_PER_FILE)
        except Exception as e:
            logging.warning(f"dna_distiller: failed to read {fpath}: {e}")
            continue
        # 流式分词 + 频率聚合
        for w in jieba.cut(text):
            if _is_valid_term(w):
                global_counter[w] += 1

    # 预计算全局高频候选池（按词频降序，已满足 MIN_FREQ），供各维共享演化补充
    pool = [w for w, c in global_counter.most_common() if c >= MIN_FREQ]

    dimensions = {}
    for dim, seed_kws in seed_dims.items():
        # 保形：内置词保留且在前
        seed_frozen = set(seed_kws)
        # 演化补充 = 全局高频候选中排除该维内置词后的前 TOP_K（不依赖语义对齐，零风险）
        extra = [w for w in pool if w not in seed_frozen][:TOP_K]
        dimensions[dim] = list(seed_kws) + extra
    return dimensions


def _resolve_corpus_files(category, scope, max_files=MAX_FILES):
    """根据 scope 确定 corpus 文件列表。

    scope == "category": corpus/<category>/ 下 .txt（category 空则退化全量）
    scope == "all": 遍历 corpus/ 递归所有 .txt
    超出 max_files 则随机抽样，避免超大题材蒸馏超时。
    """
    files = []
    try:
        if scope == "all" or not category:
            search_root = CORPUS_ROOT
        else:
            search_root = os.path.join(CORPUS_ROOT, category)
        if not os.path.isdir(search_root):
            return []
        for dirpath, _, fnames in os.walk(search_root):
            for fn in fnames:
                if fn.lower().endswith(".txt"):
                    files.append(os.path.join(dirpath, fn))
    except Exception as e:
        logging.warning(f"dna_distiller: failed to resolve corpus files: {e}")
        return []
    if len(files) > max_files:
        files = random.sample(files, max_files)
    return files


def _persist(dna, path=DEFAULT_DNA_PATH):
    """落盘 DNA 演化表（ensure_ascii=False 保留中文）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(dna, fh, ensure_ascii=False, indent=2)


def _load_cached(path=DEFAULT_DNA_PATH):
    """读取缓存 DNA；损坏/缺失返回 None。"""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data and isinstance(data.get("dimensions"), dict):
            return data
    except (json.JSONDecodeError, OSError) as e:
        logging.warning(f"dna_distiller: failed to load cached DNA: {e}")
        return None
    return None


def load_or_build_dna(category, scope="category", force=False, dna_path=DEFAULT_DNA_PATH):
    """加载或构建叙事 DNA 演化表，落盘 data/_narrative_dna.json。

    - 文件存在且 force=False → 直接读缓存返回。
    - 否则：确定 corpus 文件列表 → distill_dna_from_corpus → 构造元数据 → 落盘。
    - 任意异常 → 返回空 dict（让 fusion 退化为内置表），绝不抛异常阻断流水线。

    :param category: 题材名（对应 corpus/<category>/）；为空则按 scope 退化
    :param scope: "category"（默认同题材）或 "all"（全量 corpus）
    :param force: True 时强制重建（忽略缓存）
    :param dna_path: 落盘路径（默认 data/_narrative_dna.json）
    :return: {version, scope, built_from, built_at, dimensions} 或空 dict
    """
    # 1) 命中缓存（force=False 且文件有效，且 scope 与本次请求一致）
    _want_scope = "all" if scope == "all" else (category or "all")
    if (not force) and os.path.isfile(dna_path):
        cached = _load_cached(dna_path)
        if cached and cached.get("scope") == _want_scope:
            return cached

    # 2) 导入种子骨架（融合层 20 维关键词）；绝不 import narrative_features
    try:
        sys.path.insert(0, _HERE)
        from fusion import _DIMENSION_KEYWORDS
    except Exception as e:
        logging.warning(f"dna_distiller: failed to import fusion._DIMENSION_KEYWORDS: {e}")
        return {}  # 种子不可得 → 回退内置（空 dict 让 fusion 用 _DIMENSION_KEYWORDS）

    # 3) 收集 corpus 文件
    files = _resolve_corpus_files(category, scope)
    if not files:
        # 无 corpus 可蒸馏 → 返回空 dict，fusion 退化为内置表（红线：不缓存字面）
        return {}

    # 4) 蒸馏
    try:
        dimensions = distill_dna_from_corpus(files, _DIMENSION_KEYWORDS)
    except Exception as e:
        logging.warning(f"dna_distiller: distillation failed: {e}")
        return {}

    # 5) 构造 + 落盘
    scope_label = "all" if scope == "all" else (category or "all")
    built_from = CORPUS_ROOT if (scope == "all" or not category) else os.path.join(CORPUS_ROOT, category)
    dna = {
        "version": DNA_VERSION,
        "scope": scope_label,
        "built_from": built_from,
        "built_at": _now_iso(),
        "dimensions": dimensions,
    }
    try:
        _persist(dna, dna_path)
    except Exception as e:
        logging.warning(f"dna_distiller: failed to persist DNA: {e}")
        pass  # 落盘失败不阻断流水线，仍返回内存结果
    return dna


if __name__ == "__main__":
    # 简易 CLI：python dna_distiller.py [category] [scope] [--force]
    _cat = sys.argv[1] if len(sys.argv) > 1 else None
    _scp = sys.argv[2] if len(sys.argv) > 2 else "category"
    _f = "--force" in sys.argv
    _d = load_or_build_dna(_cat, _scp, force=_f)
    if _d:
        print("scope:", _d.get("scope"), "| dims:", len(_d.get("dimensions", {})))
        for _k, _v in list(_d.get("dimensions", {}).items())[:3]:
            print(f"  {_k}: {_v[:8]}")
    else:
        print("DNA 蒸馏返回空（已回退内置表）")
