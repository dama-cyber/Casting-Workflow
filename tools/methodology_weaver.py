# -*- coding: utf-8 -*-
"""
tools/methodology_weaver.py — 方法论自动织入（approach A）

纯标准库实现（仅 os / re / pathlib），零新增第三方依赖。

在**运行时、按阶段 + 题材**，自动选取并织入 `prompt/methodology/` 下相关
方法论卡片文本到 prompt，取代 `prompt/COMMON.md` 中「请 LLM 自行 recall」
的静态指针——LLM 拿到的是真实方法论内容，而非一份「请自己去查」的目录。

对外导出:
    weave_methodology(stage, category=None, short_mode=False, budget=4000) -> str

健壮性（红线要求）:
    - 模块缺失 / 目录不存在 / 任意文件读失败 / 任意异常 → 优雅返回 "" 或截断结果
    - 绝不抛出异常，绝不阻断主流水线（run_pipeline）
    - 缺失的方法学文件：静默跳过 + WARN
    - 题材卡仅作为「题材味校准参考」注入，并显式指令「严禁原样写入正文」

目录定位：本模块自行推导项目根（tools/ 的父目录），不反向依赖 run_pipeline，
可独立 import 使用。
"""

import os
import re
import sys

# ── methodology 目录自定位 ──────────────────────────────────────────────
# _HERE = tools/  ;  _ROOT = 项目根
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
METHODOLOGY_DIR = os.path.join(_ROOT, "prompt", "methodology")

# ── 单文件读取上限（字符）───────────────────────────────────────────────
_GENRE_CARD_MAX = 800   # 题材卡 ≤ 800 字符
_METHOD_MAX = 1200      # 其它方法论文件 ≤ 1200 字符

# ── 阶段内占位标记：表示「按 category 动态解析题材卡」─────────────────────
_PLACEHOLDER_GENRE = "<genre-card>"

# ── 阶段 → 方法论文件（相对 METHODOLOGY_DIR 的路径列表）─────────────────
#    <genre-card> 占位在运行时按 category 解析为具体题材卡文件。
STAGE_METHODOLOGY_MAP = {
    "脑洞": [_PLACEHOLDER_GENRE],
    "灵感风暴": [_PLACEHOLDER_GENRE],
    "人设": [
        "character/character-basics.md",
        "character/character-design-methods.md",
        "character/character-relations.md",
    ],
    "大纲": [
        "plot-emotion/outline-methods.md",
        "plot-emotion/outline-conflict.md",
        "plot-emotion/outline-rhythm.md",
        "plot-emotion/outline-structure-theory.md",
        "plot-emotion/plot-core-methods.md",
        "plot-emotion/reversal-toolkit.md",
    ],
    "细纲": [
        "plot-emotion/outline-methods.md",
        "plot-emotion/plot-core-methods.md",
        "plot-emotion/reversal-toolkit.md",
        "plot-emotion/emotional-arc-design.md",
    ],
    "概要": [
        "plot-emotion/outline-methods.md",
        # 注意：若 plot-frameworks.md 不存在，则回退 outline-structure-theory.md
        "plot-emotion/plot-frameworks.md",
    ],
    "开篇": [
        "hooks/chapter.md",
        "hooks/suspense.md",
        _PLACEHOLDER_GENRE,
    ],
    "正文": [
        _PLACEHOLDER_GENRE,
        "hooks/paragraph.md",
        "hooks/suspense.md",
        "plot-emotion/reversal-toolkit.md",
    ],
    "续写": [
        _PLACEHOLDER_GENRE,
        "hooks/paragraph.md",
        "hooks/suspense.md",
        "plot-emotion/reversal-toolkit.md",
    ],
    "扩写": [
        _PLACEHOLDER_GENRE,
        "hooks/paragraph.md",
        "hooks/suspense.md",
        "plot-emotion/reversal-toolkit.md",
    ],
    "优化": [
        "anti-ai/pointers.md",
    ],
    "润色": [
        "anti-ai/pointers.md",
    ],
}

# ── corpus 分类 → 题材卡文件名（不含 .md）───────────────────────────────
#    已核实的近似最佳映射；带「近似」注释的属兜底映射，主理人可后续微调。
CATEGORY_GENRE_MAP = {
    "01_末世科幻": "科幻末世",
    "02_悬疑灵异": "悬疑灵异",
    "03_系统快穿": "快穿",
    "04_病娇暗黑": "现言脑洞",   # 近似兜底
    "05_古代言情": "古言脑洞",
    "06_家庭伦理": "都市日常",   # 近似
    "07_重生复仇": "现言脑洞",
    "08_职场商战": "职场婚恋",
    "09_现代校园": "青春甜宠",
    "10_先婚后爱": "豪门总裁",
    "11_虐恋情深": "现言脑洞",   # 近似
    "12_狗血情感": "现言脑洞",   # 近似
    "13_娱乐圈": "星光璀璨",
    "14_现代言情": "现言脑洞",
    "15_豪门总裁": "豪门总裁",
}

# ── short 模式：正文/续写/扩写/优化/润色 额外织入的精选子集 ──────────────
#    从全量里挑 2-3 个最相关，避免膨胀。
_SHORT_APPLICABLE_STAGES = ("正文", "续写", "扩写", "优化", "润色")
_SHORT_EXTRA_FILES = [
    "short/short-craft.md",
    "short/short-deslop.md",
    "short/quality-checklist.md",
    "short/hooks-paragraph.md",
    "short/genre-writing-techniques.md",
]
# 各阶段优先级（排在前面的优先入选，最多 3 个）
_SHORT_PRIORITY = {
    "正文": ["short/short-craft.md", "short/hooks-paragraph.md", "short/genre-writing-techniques.md"],
    "续写": ["short/short-craft.md", "short/hooks-paragraph.md", "short/genre-writing-techniques.md"],
    "扩写": ["short/short-craft.md", "short/hooks-paragraph.md", "short/genre-writing-techniques.md"],
    "优化": ["short/short-deslop.md", "short/quality-checklist.md", "short/genre-writing-techniques.md"],
    "润色": ["short/short-deslop.md", "short/quality-checklist.md", "short/genre-writing-techniques.md"],
}


def _warn(msg):
    """WARN 日志（写 stderr，绝不抛异常）。"""
    try:
        sys.stderr.write(f"[methodology_weaver][WARN] {msg}\n")
    except Exception:
        pass


def _read_text_safe(path, max_chars):
    """安全读取文本：utf-8 → gbk → utf-8-sig 三级回落。

    :return: (text, ok) —— ok=False 表示文件不存在 / 读失败 / 空文件。
    """
    if not path or not os.path.isfile(path):
        return "", False
    text = None
    for enc in ("utf-8", "gbk", "utf-8-sig"):
        try:
            with open(path, "r", encoding=enc) as f:
                text = f.read()
            break
        except (UnicodeDecodeError, OSError):
            text = None
    if text is None:
        return "", False
    text = text.strip()
    if not text:
        return "", False
    if len(text) > max_chars:
        text = text[:max_chars]
    return text, True


def _parse_frontmatter(text):
    """解析题材卡 YAML frontmatter，返回 (fields_dict, body_text)。

    支持：标量 `k: v`、内联列表 `k: [a, b]`、块列表 `k:` + 续行 `- item`。
    解析失败返回 ({}, text)。
    """
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm, body = m.group(1), m.group(2)
    fields = {}
    cur_list_key = None
    for raw in fm.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        # 续行：- item （属于上一个块列表）
        if cur_list_key is not None and re.match(r"^\s*-\s+", line):
            item = re.sub(r"^\s*-\s+", "", line).strip().strip("'\"")
            if item:
                fields.setdefault(cur_list_key, [])
                if isinstance(fields[cur_list_key], list):
                    fields[cur_list_key].append(item)
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        cur_list_key = None
        if val.startswith("["):
            inner = val.strip("[]").strip()
            items = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
            fields[key] = items
        elif val == "":
            cur_list_key = key
            fields[key] = []
        else:
            fields[key] = val.strip("'\"")
    return fields, body


def _strip_frontmatter(text):
    """剥离 YAML frontmatter，返回正文。无 frontmatter 则原样返回。"""
    _, body = _parse_frontmatter(text)
    return body.strip() if body else text.strip()


def _resolve_genre_card(category):
    """按 category 解析题材卡（完整路径, 卡名）。失败返回 (None, None)。

    1) 命中 CATEGORY_GENRE_MAP → 取映射卡（文件缺失则继续兜底）；
    2) 兜底：遍历 genre-prose-cards/ 每张卡的 frontmatter aliases（及卡名），
       用子串匹配 category 文本，取首个命中；都没有返回 (None, None)。
    """
    if not category:
        return None, None
    cards_dir = os.path.join(METHODOLOGY_DIR, "genre-prose-cards")
    if not os.path.isdir(cards_dir):
        return None, None

    cat = str(category).strip()

    # 1) 精确映射表
    mapped = CATEGORY_GENRE_MAP.get(cat)
    if mapped:
        p = os.path.join(cards_dir, mapped + ".md")
        if os.path.isfile(p):
            return p, mapped
        _warn(f"CATEGORY_GENRE_MAP 命中但卡文件缺失: {mapped}.md，转兜底")

    # 2) 兜底：子串匹配
    try:
        entries = sorted(os.listdir(cards_dir))
    except OSError:
        return None, None
    for fn in entries:
        if not fn.endswith(".md") or fn == "_index.md":
            continue
        card_path = os.path.join(cards_dir, fn)
        text, ok = _read_text_safe(card_path, 4000)
        if not ok:
            continue
        name = fn[:-3]
        fields, _ = _parse_frontmatter(text)
        aliases = []
        if isinstance(fields.get("aliases"), list):
            aliases.extend(fields["aliases"])
        if isinstance(fields.get("genre"), str):
            aliases.append(fields["genre"])
        aliases.append(name)
        for a in aliases:
            if a and (a in cat or cat in a):
                return card_path, name
    return None, None


def _pick_short_files(stage):
    """从 short 精选子集按阶段优先级挑 2-3 个存在的文件。"""
    preferred = _SHORT_PRIORITY.get(stage, [])
    ordered = preferred + [f for f in _SHORT_EXTRA_FILES if f not in preferred]
    picked = []
    for rel in ordered:
        if len(picked) >= 3:
            break
        full = os.path.join(METHODOLOGY_DIR, rel)
        if os.path.isfile(full):
            picked.append(rel)
    return picked


def _weave(stage, category, short_mode, budget):
    """内部实现：返回织入文本块（不含顶层 `## 写作方法学` 标题，由调用方加）。"""
    if not stage or not os.path.isdir(METHODOLOGY_DIR):
        return ""

    rel_paths = STAGE_METHODOLOGY_MAP.get(stage)
    if not rel_paths:
        return ""

    sections = []  # list of (name, text, is_genre)
    total = 0

    def _add(rel, is_genre=False):
        nonlocal total
        full = os.path.join(METHODOLOGY_DIR, rel)
        max_chars = _GENRE_CARD_MAX if is_genre else _METHOD_MAX
        text, ok = _read_text_safe(full, max_chars)
        if not ok:
            _warn(f"读取失败或为空，跳过: {rel}")
            return
        name = os.path.splitext(os.path.basename(rel))[0]
        sections.append((name, text, is_genre))
        total += len(text)

    for rel in rel_paths:
        if rel == _PLACEHOLDER_GENRE:
            # 题材卡：按 category 动态解析
            card_path, card_name = _resolve_genre_card(category)
            if not card_path:
                _warn(f"阶段[{stage}]题材卡解析不到(category={category})，跳过题材卡")
                continue
            text, ok = _read_text_safe(card_path, _GENRE_CARD_MAX)
            if not ok:
                _warn(f"题材卡读取失败，跳过: {card_name}")
                continue
            body = _strip_frontmatter(text) or text
            body = body[:_GENRE_CARD_MAX]  # 再保一次上限
            sections.append((card_name, body, True))
            total += len(body)
        else:
            # 概要阶段：plot-frameworks.md 不存在 → 回退 outline-structure-theory.md
            real_rel = rel
            if rel == "plot-emotion/plot-frameworks.md":
                full = os.path.join(METHODOLOGY_DIR, rel)
                if not os.path.isfile(full):
                    _warn(f"{rel} 不存在，回退 outline-structure-theory.md")
                    real_rel = "plot-emotion/outline-structure-theory.md"
            _add(real_rel, is_genre=False)

    # short 模式：正文/续写/扩写/优化/润色 额外织入精选子集
    if short_mode and stage in _SHORT_APPLICABLE_STAGES:
        for rel in _pick_short_files(stage):
            _add(rel, is_genre=False)

    if not sections:
        return ""

    # budget 硬上限：最终字符串（含分节标题/分隔线开销）必须 ≤ budget
    if not sections:
        return ""

    def _assemble(sections):
        lines = []
        for name, text, is_genre in sections:
            lines.append("")
            lines.append(f"### 方法论：{name}")
            if is_genre:
                lines.append(
                    "> 以下为题材味校准参考，仅供风格对齐，**严禁原样写入正文**。"
                    "（只学题材味道，不抄卡名 / 题材标签 / 置信度 / 写作过程说明）"
                )
            lines.append("")
            lines.append(text)
            lines.append("")
            lines.append("---")
        return "\n".join(lines).strip() + "\n"

    result = _assemble(sections)

    if len(result) > budget:
        _warn(f"方法论总字数 {len(result)} 超出预算 {budget}，按比例从末项截断")
        text_total = sum(len(t) for _, t, _ in sections)
        if text_total > 0:
            # 1) 按比例缩放各 section 文本（预留约 15% 给分节标题/分隔线开销）
            ratio = min(1.0, (budget * 0.85) / text_total)
            scaled = [(n, t[:max(0, int(round(len(t) * ratio)))], g) for n, t, g in sections]
            sections = [(n, t, g) for n, t, g in scaled if t] or scaled
        # 2) 末项精确截断，确保最终字符串 ≤ budget
        result = _assemble(sections)
        while len(result) > budget and sections:
            name, text, is_genre = sections[-1]
            overflow = len(result) - budget
            cut = max(1, overflow + 8)  # 8 字符余量，避免临界抖动
            new_text = text[:max(0, len(text) - cut)]
            if new_text:
                sections[-1] = (name, new_text, is_genre)
            else:
                sections.pop()
            result = _assemble(sections)

    return result


def weave_methodology(stage, category=None, short_mode=False, budget=4000):
    """按阶段 + 题材自动织入方法论卡片文本。

    :param stage: 创作阶段名（须为 STAGE_METHODOLOGY_MAP 的键，如 正文/人设/大纲…）
    :param category: corpus 子分类（如 "05_古代言情"），用于解析题材卡；可为 None
    :param short_mode: 是否启用短篇专属方法论（额外织入 short/ 精选子集）
    :param budget: 整体字符硬上限（默认 4000）
    :return: 织入文本块；若为空返回 ""
    """
    try:
        return _weave(stage, category, short_mode, budget)
    except Exception as e:  # 任何异常都吞掉，绝不阻断流水线
        _warn(f"未知异常被吞，返回空: {type(e).__name__}: {e}")
        return ""
