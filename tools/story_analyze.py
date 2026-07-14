#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
story_analyze.py — 网文逆向导入确定性骨架生成器（无 LLM）

用法:
    python tools/story_analyze.py --input <file_or_dir> [--out analysis] [--book 书名] [--length auto|short|long] [--force]

功能:
    1. 备份原文到  analysis/{书名}/原文/
    2. 按章节分隔符切分（第X章 / Chapter X / 数字编号）
    3. 用 jieba 做基础统计（字数 / 词数 / 高频词 / 句长爆发性分布）
    4. 生成 analysis/{书名}/ 标准骨架（长/短篇分流），供 tools/story_analyze.py 的 LLM 管道填充

设计约束:
    - 纯确定性，**不调用任何 LLM**
    - 只写 --out 目录（默认 analysis/），**绝不触碰 corpus/**
    - 引擎（run_pipeline.py / fusion.py 等）零改动
    - 8G 内存安全：流式读取，无大对象常驻

输出 schema 见本模块 OUTPUT_SCHEMA 常量（analysis/{书名}/ 标准文件树，单一事实来源，测试据此断言）。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta

try:
    import jieba
    jieba.setLogLevel(20)  # 压制 jieba 的 debug 日志
    _HAS_JIEBA = True
except Exception:
    _HAS_JIEBA = False

THIS = os.path.dirname(os.path.abspath(__file__))
SCHEMA_VERSION = "1.0"

# ── 输出文件树 schema（analysis/{书名}/ 标准结构） ──
# 原约定于已归档的 story-analyze 方法论文档，现固化于此作为单一事实来源，
# 供 tools/test_story_analyze.py 断言生成骨架与契约一致。
# 目录项以 "/" 结尾；文件项须存在。
OUTPUT_SCHEMA = {
    "long": [
        "概要.md",
        "快速预览.md",
        "拆文报告.md",
        "文风.md",
        "_progress.md",
        "原文/",
        "章节/",
        "角色/角色关系.md",
        "剧情/README.md",
        "剧情/故事线.md",
        "剧情/节奏.md",
        "剧情/情绪模块.md",
        "剧情/散落情节.md",
        "设定/世界观/背景设定.md",
        "设定/世界观/力量体系.md",
        "设定/世界观/地理.md",
        "设定/世界观/金手指.md",
        "设定/势力/README.md",
    ],
    "short": [
        "拆文报告.md",
        "情节节点.md",
        "写作手法.md",
        "_meta.json",
        "原文/",
    ],
}

# ── 章节分隔识别（优先级从高到低） ──
RE_ZH_CHAPTER = re.compile(r"^\s*第\s*[一二三四五六七八九十百千零〇0-9]+\s*章")
RE_EN_CHAPTER = re.compile(r"^\s*Chapter\s+\d+", re.I)
RE_NUM_CHAPTER = re.compile(r"^\s*\d{1,4}\s*[\.、]\s*\S")

# 长/短篇路由阈值（与 story-analyze SKILL 对齐：>20000 长篇）
LONG_THRESHOLD = 20000


# ────────────────────────────────────────────────────────────
# 文本读取与章节切分
# ────────────────────────────────────────────────────────────
def read_input(path):
    """返回 (text, list_of_files_or_None)。file 返回单文件文本；dir 返回拼接文本与文件清单。"""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read(), None
    if os.path.isdir(path):
        files = sorted(
            os.path.join(path, fn)
            for fn in os.listdir(path)
            if fn.lower().endswith((".txt", ".md"))
        )
        if not files:
            raise SystemExit(f"[story_analyze] 目录无 .txt/.md 文件: {path}")
        chunks = []
        for fp in files:
            try:
                with open(fp, encoding="utf-8") as f:
                    chunks.append(f.read())
            except Exception as e:
                print(f"  ! 跳过无法读取的文件 {fp}: {e}", file=sys.stderr)
        return "\n\n".join(chunks), files
    raise SystemExit(f"[story_analyze] 输入路径不存在: {path}")


def _detect_markers(text):
    """返回 [(line_index, marker, full_line)]，无序。"""
    out = []
    for i, line in enumerate(text.splitlines()):
        m = RE_ZH_CHAPTER.match(line) or RE_EN_CHAPTER.match(line) or RE_NUM_CHAPTER.match(line)
        if m:
            out.append((i, m.group(0).strip(), line.strip()))
    return out


def split_chapters(text, files):
    """返回 [(编号, 标题, 内容), ...]。>=2 章才视为多章，否则回退到单章/按文件切。"""
    marks = _detect_markers(text)
    if len(marks) >= 2:
        chapters = []
        lines = text.splitlines()
        for idx, (li, num, title) in enumerate(marks):
            end = marks[idx + 1][0] if idx + 1 < len(marks) else len(lines)
            content = "\n".join(lines[li:end]).strip()
            chapters.append((num, title, content))
        return chapters

    # 回退 1：目录输入且多文件 → 每文件一章
    if files and len(files) >= 2:
        out = []
        for i, fp in enumerate(files, 1):
            with open(fp, encoding="utf-8") as fh:
                content = fh.read().strip()
            out.append((f"第{i}章", os.path.splitext(os.path.basename(fp))[0], content))
        return out

    # 回退 2：整篇单章
    return [("第1章", "全文", text.strip())]


def compute_stats(text):
    """jieba 基础统计；缺失时回退到字级切分。"""
    if _HAS_JIEBA:
        words = [w for w in jieba.cut(text) if w.strip()]
    else:
        words = re.findall(r"[一-鿿]|[A-Za-z0-9]+", text)

    total_chars = len(text)
    total_words = len(words)
    kw = Counter(w for w in words if len(w) >= 2 and not re.fullmatch(r"[\s\W_]+", w))
    top_kw = kw.most_common(30)

    sents = [s for s in re.split(r"[。！？!?；;\n]", text) if s.strip()]
    lengths = [len(s) for s in sents]
    n = len(lengths) or 1
    avg_len = sum(lengths) / n
    short_ratio = sum(1 for l in lengths if l <= 5) / n
    long_ratio = sum(1 for l in lengths if l >= 40) / n

    return {
        "total_chars": total_chars,
        "total_words": total_words,
        "avg_sentence_len": round(avg_len, 2),
        "short_sentence_len_ratio": round(short_ratio, 4),
        "long_sentence_len_ratio": round(long_ratio, 4),
        "sentence_count": len(lengths),
        "top_keywords": top_kw,
    }


# ────────────────────────────────────────────────────────────
# 落盘工具
# ────────────────────────────────────────────────────────────
def _w(root, rel, content):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def _now_iso():
    return (datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S +08:00"))


def _sanitize_book(name):
    name = name.strip()
    for ch in '/\\:*?"<>|':
        name = name.replace(ch, "_")
    return name or "未命名"


# ────────────────────────────────────────────────────────────
# 模板
# ────────────────────────────────────────────────────────────
LONG_SUMMARY_TPL = """# 概要（骨架占位 · 待 LLM 填充）

> 本书：《{book}》
> 本文件由 `tools/story_analyze.py` 生成骨架，Stage 0/5 的 LLM 拆解会覆盖此处的 thin first-pass 与全书版。

## 首版 thin first-pass（待补，200 字）

## 章节索引
（Stage 0 由 LLM 补全章节边界与一句话提要）
"""

LONG_CHAPTER_DEEP_TPL = """# 第{n3}章 深度拆解（骨架占位 · 待 LLM 填充）

> 源编号：{num} | 源标题：{title} | 字数：{chars}

## 拆解要点（待 LLM 填充）
- 情节推进
- 人物弧光
- 钩子 / 悬念
- 写法技法锚点

## 原文锚点
（Stage 1 黄金三章由 LLM 摘录 4-6 段原文范例）
"""

LONG_CHAPTER_SUMMARY_TPL = """# 第{n3}章 摘要（骨架占位 · 待 LLM 填充）

> 源编号：{num} | 源标题：{title} | 字数：{chars}

## 情节点（10-40 个，待 LLM 填充）
- [ ] 关键点 + 功能标签

## 角色
（本出角色与状态变化，待 LLM 填充）

## 关键信息与扩写技法
（待 LLM 填充）
"""

LONG_ROLE_TPL = """# 角色关系（骨架占位 · 待 LLM 填充）

> Stage 4 由 LLM 生成角色档案（`角色/{角色名}.md`）与本关系总览。

## 关系总览
| 角色 A | 角色 B | 关系类型 | 情感倾向 | 当前状态 | 起始章节 | 变化节点 |
|--------|--------|----------|----------|---------|---------|---------|
| （待填充） | | | | | | |

## 关系演变
（待 LLM 填充）

## 核心冲突关系
（待 LLM 填充）
"""

PLOT_TPLS = {
    "README.md": "# 剧情目录（权威范围索引 · 骨架占位）\n\n> 本目录由 `tools/story_analyze.py` 建骨架；Stage 3 由 LLM 填充。\n\n- `故事线.md` — 主线/支线聚合\n- `节奏.md` — 权威：关键信息推进 / 情绪触动点 / 爆发节奏\n- `情绪模块.md` — 权威：读者需求 / 情绪引擎 / 可复现模块\n- `散落情节.md` — 兜底聚合\n",
    "故事线.md": "# 故事线（骨架占位 · 待 LLM 填充）\n\n（Stage 3 由 LLM 聚合全部章节摘要生成）\n",
    "节奏.md": "# 节奏（权威 · 骨架占位 · 待 LLM 填充）\n\n> 写作侧节奏权威：关键信息推进 / 情绪触动点 / 爆发节奏。\n\n（Stage 3 由 LLM 生成）\n",
    "情绪模块.md": "# 情绪模块（权威 · 骨架占位 · 待 LLM 填充）\n\n> 写作侧情绪权威：读者需求 / 情绪引擎 / 可复现模块。\n\n（Stage 3 由 LLM 生成）\n",
    "散落情节.md": "# 散落情节（骨架占位 · 待 LLM 填充）\n\n（Stage 3 由 LLM 兜底聚合未归入主线的情节点）\n",
}

SETTING_TPL = """# {name}（骨架占位 · 待 LLM 填充）

> Stage 4 由 LLM 从拆文库设定拆分生成。

（待填充）
"""

LONG_REPORT_TPL = """# 拆文报告（骨架占位 · 待 LLM 填充）

> 本书：《{book}》
> Stage 5 由 LLM 汇总生成：读者需求/情绪引擎、关键信息与扩写技法总览、节奏与情绪触动点、可复现模块、写法技巧清单。

## 基本信息
- 题材类型：（待补）
- 核心梗：（待补）
- 微创新点：（待补）

## 读者需求 / 情绪引擎
（待 LLM 填充）

## 关键信息与扩写技法总览
（待 LLM 填充）

## 节奏与情绪触动点
（待 LLM 填充）

## 可复现模块
（待 LLM 填充）

## 写法技巧清单
（待 LLM 填充）
"""

STYLE_TPL = """# 文风（骨架占位 · 待 LLM 填充）

> Stage 6 由 LLM 生成：句长/标点/对话潜台词/情绪交替 + 4-6 段原文锚点范例 + 分层模仿建议（硬上限 ~4000 字）。

（待 LLM 填充）
"""

SHORT_REPORT_TPL = """# 拆文报告（短篇 · 骨架占位 · 待 LLM 填充）

> 本书：《{book}》
> 短篇 Stage 2-6 由 LLM 串行填充：故事核/梗概/功能分段 → 情感曲线/爆点 → 反转/写作手法 → 人物/开头结尾 → 综合评估。

## 故事核
（待补）

## 梗概
（待补）

## 功能分段（4-6 段：开端/发展/高潮/结局）
（待 LLM 填充）

## 情感曲线（>=5 节点）
（待 LLM 填充）

## 爆点分析（6 维度）
（待 LLM 填充）

## 反转
（待 LLM 填充）

## 人物分类与功能评估
（待 LLM 填充）

## 开头前 50/100 字
（待 LLM 填充）

## 结尾收束
（待 LLM 填充）

## 五维评分
（待 LLM 填充）
"""

SHORT_NODES_TPL = """# 情节节点（短篇 · 骨架占位 · 待 LLM 填充）

> Stage 2 由 LLM 从全文提取功能分段与节点。

（待 LLM 填充）
"""

SHORT_CRAFT_TPL = """# 写作手法（短篇 · 骨架占位 · 待 LLM 填充）

> Stage 4 由 LLM 生成 >=5 项维度（POV/对话/时间/信息/其他）。

（待 LLM 填充）
"""


# ────────────────────────────────────────────────────────────
# 骨架生成
# ────────────────────────────────────────────────────────────
def _chapter_boundary_table(chapters):
    rows = ["| 序号 | 编号 | 标题 | 字数 |", "|------|------|------|------|"]
    for i, (num, title, content) in enumerate(chapters, 1):
        rows.append(f"| {i} | {num} | {title[:24]} | {len(content)} |")
    return "\n".join(rows)


def write_long_skeleton(root, book, chapters, stats):
    # 原文备份由 main() 统一写入 root/原文/原文{ext}，此处不再占位
    _w(root, "概要.md", LONG_SUMMARY_TPL.format(book=book))
    ch_dir = os.path.join(root, "章节")
    for i, (num, title, content) in enumerate(chapters, 1):
        n3 = f"{i:03d}"
        _w(ch_dir, f"第{n3}章_深度拆解.md",
           LONG_CHAPTER_DEEP_TPL.format(n3=n3, num=num, title=title, chars=len(content)))
        _w(ch_dir, f"第{n3}章_摘要.md",
           LONG_CHAPTER_SUMMARY_TPL.format(n3=n3, num=num, title=title, chars=len(content)))
    _w(root, "快速预览.md", f"# 快速预览（骨架占位 · 待 LLM 填充）\n\n> 本书：《{book}》 Stage 1 黄金三章后由 LLM 产出。\n")
    _w(os.path.join(root, "角色"), "角色关系.md", LONG_ROLE_TPL)
    for fn, c in PLOT_TPLS.items():
        _w(os.path.join(root, "剧情"), fn, c)
    for fn in ["背景设定.md", "力量体系.md", "地理.md", "金手指.md"]:
        _w(os.path.join(root, "设定", "世界观"), fn, SETTING_TPL.format(name=fn[:-3]))
    _w(os.path.join(root, "设定", "势力"), "README.md", "# 势力（骨架占位 · 待 LLM 填充）\n\n（Stage 4 由 LLM 生成 `势力/{势力名}.md`）\n")
    _w(root, "拆文报告.md", LONG_REPORT_TPL.format(book=book))
    _w(root, "文风.md", STYLE_TPL)
    progress = _progress_md(book, "long", chapters, stats)
    _w(root, "_progress.md", progress)
    return progress


def write_short_skeleton(root, book, text, stats):
    _w(root, "拆文报告.md", SHORT_REPORT_TPL.format(book=book))
    _w(root, "情节节点.md", SHORT_NODES_TPL)
    _w(root, "写作手法.md", SHORT_CRAFT_TPL)
    meta = {
        "schema_version": SCHEMA_VERSION,
        "book": book,
        "length_type": "short",
        "char_count": stats["total_chars"],
        "chapter_count": 1,
        "structure_counts": {
            "sentence_count": stats["sentence_count"],
            "avg_sentence_len": stats["avg_sentence_len"],
        },
        "created_at": _now_iso(),
        "stages_completed": [0],  # 0 = 骨架（确定性）已完成
    }
    _w(root, "_meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def _progress_md(book, length_type, chapters, stats):
    kw_line = "、".join(f"{w}({c})" for w, c in stats["top_keywords"][:15])
    return f"""# 拆解进度（story_analyze 确定性骨架）

- schema_version: {SCHEMA_VERSION}
- book: {book}
- length_type: {length_type}
- created_at: {_now_iso()}
- generator: tools/story_analyze.py（无 LLM）

## 阶段状态
| 阶段 | 状态 |
|------|------|
| 0 概要提取 / 骨架 | done（确定性） |
| 1 黄金三章 | pending（LLM） |
| 2 逐章摘要 | pending（LLM） |
| 3 聚合分析 | pending（LLM） |
| 4 设定+关系 | pending（LLM） |
| 5 汇总报告 | pending（LLM） |
| 6 文风 | pending（LLM） |

## 基础统计（jieba）
- 总字数：{stats['total_chars']}
- 总词数：{stats['total_words']}
- 平均句长：{stats['avg_sentence_len']}
- 短句(<=5字)占比：{stats['short_sentence_len_ratio']}
- 长句(>=40字)占比：{stats['long_sentence_len_ratio']}
- 高频词（前15）：{kw_line or '（无）'}

## 章节边界表
{_chapter_boundary_table(chapters)}
"""


# ────────────────────────────────────────────────────────────
# 入口
# ────────────────────────────────────────────────────────────
def analyze(argv=None):
    ap = argparse.ArgumentParser(description="网文逆向导入确定性骨架生成器（无 LLM）")
    ap.add_argument("--input", required=True, help="原文文件或目录（.txt/.md）")
    ap.add_argument("--out", default="analysis", help="输出根目录（默认 analysis/，绝不写 corpus/）")
    ap.add_argument("--book", default=None, help="书名（默认取文件名/目录名）")
    ap.add_argument("--length", default="auto", choices=["auto", "short", "long"], help="长/短篇路由（默认 auto，按字数）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 analysis/{书名}/")
    args = ap.parse_args(argv)

    text, files = read_input(args.input)
    if not text.strip():
        raise SystemExit("[story_analyze] 输入文本为空")

    stats = compute_stats(text)
    if not _HAS_JIEBA:
        print("  ! jieba 不可用，已回退字级统计", file=sys.stderr)

    # 书名
    if args.book:
        book = _sanitize_book(args.book)
    else:
        base = os.path.basename(os.path.normpath(args.input))
        book = _sanitize_book(re.sub(r"\.(txt|md)$", "", base, flags=re.I))

    # 路由
    if args.length == "short":
        is_long = False
    elif args.length == "long":
        is_long = True
    else:
        is_long = stats["total_chars"] >= LONG_THRESHOLD

    root = os.path.join(args.out, book)
    if os.path.exists(root) and not args.force:
        with os.scandir(root) as _it:
            if any(_it):
                raise SystemExit(f"[story_analyze] 已存在非空目录 {root}，使用 --force 覆盖")

    os.makedirs(root, exist_ok=True)
    # 原文备份
    ext = ".txt" if os.path.isfile(args.input) else ".md"
    orig_dir = os.path.join(root, "原文")
    os.makedirs(orig_dir, exist_ok=True)
    with open(os.path.join(orig_dir, f"原文{ext}"), "w", encoding="utf-8") as f:
        f.write(text)

    if is_long:
        chapters = split_chapters(text, files)
        progress = write_long_skeleton(root, book, chapters, stats)
        print(f"[story_analyze] 长篇骨架已生成：{root}")
        print(f"  章节数：{len(chapters)} | 字数：{stats['total_chars']} | 平均句长：{stats['avg_sentence_len']}")
    else:
        meta = write_short_skeleton(root, book, text, stats)
        print(f"[story_analyze] 短篇骨架已生成：{root}")
        print(f"  字数：{stats['total_chars']} | 平均句长：{stats['avg_sentence_len']}")

    print(f"  下一步：运行 python run_pipeline.py --analyze 加载本骨架，跑 LLM 拆文管道（Stage 0-6 / 2-6）填充。")
    return 0


# 兼容别名：旧调用 story_analyze.main(...) 仍可用
main = analyze

if __name__ == "__main__":
    sys.exit(main())
