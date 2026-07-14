# -*- coding: utf-8 -*-
"""
workflow_hooks.py — 统一流胶水模块（Casting-Workflow 熔铸版）

职责（仅标准库：os / json / argparse / dataclasses / re / glob）：
  1. WorkflowState：统一流唯一跨步骤状态对象。
  2. build_*_argv：把 run_pipeline 的 opts + state 重组为四工具既有 argv，
     是唯一「理解子工具参数」的地方（集中透传，避免 run_pipeline 散落子工具细节）。
  3. read_capture_insights / read_analysis_refs：读取前置步骤产物（Markdown / 目录）。
  4. inject_capture_into_brainstorm / inject_analysis_into_characters_outline：
     把前置参考文本注入对应生成阶段。
  5. detect_book_name：推导封面 / 拆书书名。

设计红线：
  - 零新增第三方依赖（仅 os/json/argparse/dataclasses/re/glob）。
  - 不改变四工具（story_capture/story_analyze/cover_gen/browser_ctl）的任何逻辑，
    仅经 build_*_argv 构造 argv 喂给它们。
  - 不引入任何 LLM 调用；本模块纯确定性。

capture 产物修正（主理人实测）：扫榜输出是 **Markdown 文件**（非 JSON），
写到 scan_output/，文件名形如 `番茄男频阅读榜_全题材_YYYYMMDD.md`。
read_capture_insights 必须解析 Markdown，绝不让统一流崩溃。
"""

import os
import re
import glob
import json
from dataclasses import dataclass, field


# ────────────────────────────────────────────────────────────
# Markdown 解析正则（capture 扫榜产物）
# ────────────────────────────────────────────────────────────
RE_HEADER = re.compile(r"^#\s+(.*)$")
RE_CATEGORY = re.compile(r"^##\s+(.*)$")
RE_BOOK = re.compile(r"^###\s+#\d+\s+(.*)$")
RE_BOOK_PLAIN = re.compile(r"^###\s+(.*)$")
RE_TAGS = re.compile(r"^\*\*标签[:：]\*\*\s*(.*)$")
RE_BOOKID = re.compile(r"^\*\*bookId[:：]\*\*\s*(.*)$")
RE_INTRO = re.compile(r"^\*\*简介\*\*\s*$")

# 品类名后缀（`## 西方奇幻 — 20 本`）
RE_CAT_SUFFIX = re.compile(r"\s*[—–-]\s*\d+\s*本\s*$")


# ────────────────────────────────────────────────────────────
# 统一流状态
# ────────────────────────────────────────────────────────────
@dataclass
class WorkflowState:
    """统一流唯一跨步骤状态对象。

    路由/主题、路径、注入上下文、步骤开关集中于此；capture/analyze 产物写入
    capture_insights / analysis_refs，generate 主干与 cover 步骤消费。
    """

    category: object = None
    topic: object = None
    sample: int = 5
    target_chars: object = None
    short_mode: bool = False
    no_methodology: bool = False
    scan_output_dir: str = ""
    analysis_dir: str = ""
    story_path: str = ""
    cover_path: object = None
    capture_insights: dict = field(default_factory=dict)
    analysis_refs: dict = field(default_factory=dict)
    do_capture: bool = False
    do_analyze: bool = False
    do_cover: bool = False
    do_browser: bool = False


# ────────────────────────────────────────────────────────────
# 文件读取（三级降级，与 run_pipeline.read_file_safe 对齐）
# ────────────────────────────────────────────────────────────
def _read_file_safe(path):
    """尝试 utf-8 → gbk → utf-8-sig，最后 utf-8+replace 三级读取。"""
    for enc in ("utf-8", "gbk", "utf-8-sig"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


# ────────────────────────────────────────────────────────────
# argv 构造器（集中透传四工具参数）
# ────────────────────────────────────────────────────────────
def build_capture_argv(opts, state):
    """构造 story_capture.capture 的 argv。

    capture 内部用 parse_known_args，故 --type/--channel/--top 等平台专有参数
    可直接透传。--platform 必填，--outdir 默认取 state.scan_output_dir。
    """
    platform = (opts.get("capture_platform") or "qidian")
    outdir = state.scan_output_dir or opts.get("capture_outdir") or "scan_output"
    argv = ["--platform", str(platform), "--outdir", str(outdir)]
    if opts.get("capture_type"):
        argv += ["--type", str(opts["capture_type"])]
    if opts.get("capture_channel"):
        argv += ["--channel", str(opts["capture_channel"])]
    if opts.get("capture_top"):
        argv += ["--top", str(opts["capture_top"])]
    return argv


def build_analyze_argv(opts, state):
    """构造 story_analyze.analyze 的 argv。

    --input 必填（用户显式提供的本地 txt/目录）；--out 默认取 state.analysis_dir。
    未提供 --analyze-input 时返回空列表，交由 run_pipeline 打印 WARN 跳过。
    """
    analyze_input = opts.get("analyze_input")
    if not analyze_input:
        return []
    argv = ["--input", str(analyze_input), "--out", str(state.analysis_dir or "analysis")]
    if opts.get("analyze_book"):
        argv += ["--book", str(opts["analyze_book"])]
    if opts.get("analyze_length"):
        argv += ["--length", str(opts["analyze_length"])]
    if opts.get("analyze_force"):
        argv += ["--force"]
    return argv


def detect_book_name(opts, state):
    """推导封面/拆书书名。

    优先级：--cover-book > category 基名（去掉 `NN_` 前缀）> "未命名"。
    """
    book = (opts.get("cover_book") or "").strip()
    if book:
        return book
    cat = state.category or opts.get("category") or ""
    if cat:
        base = os.path.basename(str(cat))
        base = re.sub(r"^\d+_", "", base)
        if base:
            return base
    return "未命名"


def build_cover_argv(opts, state):
    """构造 cover_gen.generate_cover 的 argv。

    合并 --cover-prompt / --cover-api-key / 环境变量 GPT_IMAGE_API_KEY。
    缺 PROMPT 或 KEY（REQUIRED_KEYS）时返回 None，交由 run_pipeline WARN 跳过（不阻断）。
    BOOK_DIR 默认 covers/{book}，book 由 detect_book_name 推导。
    """
    prompt = opts.get("cover_prompt")
    api_key = opts.get("cover_api_key") or os.environ.get("GPT_IMAGE_API_KEY")
    if not prompt or not api_key:
        return None
    book = detect_book_name(opts, state)
    # analysis_dir 形如 <root>/analysis → 父目录即项目根
    root = os.path.dirname(state.analysis_dir) if state.analysis_dir else "."
    book_dir = os.path.join(root, "covers", book)
    argv = ["--book-dir", book_dir, "--prompt", str(prompt), "--api-key", str(api_key)]
    if opts.get("cover_size"):
        argv += ["--size", str(opts["cover_size"])]
    return argv


def build_browser_argv(opts):
    """构造 browser_ctl.launch_cdp 的 argv。"""
    argv = [
        "--port", str(opts.get("browser_port", 9222)),
        "--action", str(opts.get("browser_action", "launch")),
    ]
    if opts.get("browser_detect_only"):
        argv.append("--detect-only")
    return argv


# ────────────────────────────────────────────────────────────
# 产物读取：capture（Markdown 解析）
# ────────────────────────────────────────────────────────────
def read_capture_insights(scan_dir):
    """读取扫榜产物（Markdown），解析为参考上下文 dict。

    主理人实测修正：**capture 产物是 Markdown 文件，不是 JSON**。
    读 scan_output/ 下最新的 *.md，用正则提取：
      - 首行 `# 平台 · 榜单 · 全 N 题材` → platform / board
      - `## 品类名 — N 本` → 品类
      - `### #N 书名` → 书名
      - `**标签：** ...` → 标签
      - `**简介**` 下一段 → 简介
    汇总成一段「扫榜参考」文本（注入 脑洞 阶段）。

    缺失目录/文件返回 `{}`；解析过程鲁棒：匹配不到的段跳过，绝不令统一流崩溃。
    """
    if not scan_dir or not os.path.isdir(scan_dir):
        return {}
    md_files = glob.glob(os.path.join(scan_dir, "*.md"))
    if not md_files:
        return {}

    # 取最新修改的 .md（兼容各平台文件名前缀：番茄/起点/七猫…）
    latest = max(md_files, key=os.path.getmtime)
    text = _read_file_safe(latest)
    if not text.strip():
        return {}

    return _parse_capture_markdown(text, latest)


def _parse_capture_markdown(text, source_file):
    """解析单份扫榜 Markdown，返回结构化 dict。"""
    platform = ""
    board = ""
    categories = []          # list of {"name": str, "books": [...]}
    books_flat = []          # 全部书的扁平列表
    cur_cat = None
    cur_book = None
    expect_intro = False

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        # 简介下一行（非空即简介文本）
        if expect_intro:
            if stripped:
                if cur_book is not None:
                    cur_book["intro"] = stripped
                expect_intro = False
                continue
            else:
                continue

        m_header = RE_HEADER.match(line)
        if m_header and not platform:
            parts = [p.strip() for p in re.split(r"[·•·\s]+", m_header.group(1)) if p.strip()]
            if len(parts) >= 1:
                platform = parts[0]
            if len(parts) >= 2:
                board = parts[1]
            continue

        m_cat = RE_CATEGORY.match(line)
        if m_cat:
            name = RE_CAT_SUFFIX.sub("", m_cat.group(1)).strip()
            cur_cat = {"name": name, "books": []}
            categories.append(cur_cat)
            continue

        m_book = RE_BOOK.match(line) or RE_BOOK_PLAIN.match(line)
        if m_book:
            cur_book = {
                "title": m_book.group(1).strip(),
                "tags": [],
                "author": "",
                "book_id": "",
                "intro": "",
            }
            if cur_cat is not None:
                cur_cat["books"].append(cur_book)
            books_flat.append(cur_book)
            continue

        m_tags = RE_TAGS.match(line)
        if m_tags and cur_book is not None:
            cur_book["tags"] = [
                t.strip() for t in re.split(r"[、,，/\s]+", m_tags.group(1)) if t.strip()
            ]
            continue

        m_id = RE_BOOKID.match(line)
        if m_id and cur_book is not None:
            cur_book["book_id"] = m_id.group(1).strip()
            continue

        if RE_INTRO.match(line):
            expect_intro = True
            continue

        # 作者行：`*作者 · 题材 · 状态 · 在读 · 字数*`（单星斜体，避开 `**` 元数据行）
        if (
            stripped.startswith("*")
            and not stripped.startswith("**")
            and cur_book is not None
            and not cur_book["author"]
        ):
            cur_book["author"] = stripped.strip("*").strip()
            continue

    summary = _build_capture_summary(platform, board, categories, books_flat)
    if not summary:
        # 解析不到任何可用信息：仍回传来源，但 text 为空（调用方据此跳过注入）
        return {"source_file": source_file, "platform": platform, "board": board,
                "categories": [], "books": [], "text": ""}

    return {
        "source_file": source_file,
        "platform": platform,
        "board": board,
        "categories": [c["name"] for c in categories if c["name"]],
        "books": books_flat,
        "text": summary,
    }


def _build_capture_summary(platform, board, categories, books_flat):
    """把解析结果汇总成一段注入 脑洞 阶段的「扫榜参考」文本。"""
    parts = []
    if platform or board:
        parts.append(f"榜单来源：{platform} {board}".strip())

    cat_names = [c["name"] for c in categories if c["name"]]
    if cat_names:
        parts.append("热门题材：" + " / ".join(cat_names[:12]))

    examples = []
    for b in books_flat[:6]:
        title = b.get("title", "")
        if not title or title == "（标题待解析）":
            continue
        seg = f"《{title}》"
        tags = "、".join(b.get("tags", [])[:4])
        if tags:
            seg += f"标签：{tags}"
        examples.append(seg)
    if examples:
        parts.append("爆款示例：" + "；".join(examples))

    if cat_names:
        parts.append(
            f"题材趋势：本期共 {len(cat_names)} 个题材上榜，可优先参考前列热门品类，"
            f"结合平台爆款逻辑确定小说类型/核心卖点/目标受众"
        )

    return "\n".join(parts)


# ────────────────────────────────────────────────────────────
# 产物读取：analyze（目录 glob）
# ────────────────────────────────────────────────────────────
def read_analysis_refs(analysis_book_dir):
    """读取拆书产物（analysis/{书名}/ 下所有 .md）作为参考文本。

    概要/拆文报告/文风/角色关系 等均可读取；鲁棒容错：
    目录不存在/无 .md / 单文件读取失败 → 返回 {}（调用方据此跳过注入）。
    """
    if not analysis_book_dir or not os.path.isdir(analysis_book_dir):
        return {}

    md_files = sorted(
        glob.glob(os.path.join(analysis_book_dir, "**", "*.md"), recursive=True)
    )
    if not md_files:
        return {}

    refs = {}
    texts = []
    for fp in md_files:
        try:
            content = _read_file_safe(fp)
        except (OSError, UnicodeDecodeError) as e:
            log(f"[workflow_hooks] 读取失败 {fp}: {e}", "WARN")
            continue
        if not content.strip():
            continue
        rel = os.path.relpath(fp, analysis_book_dir)
        key = os.path.splitext(rel)[0]
        refs[key] = content
        texts.append(f"### {key}\n{content}")

    if not texts:
        return {}

    combined = "\n\n".join(texts)
    return {
        "source_dir": analysis_book_dir,
        "files": list(refs.keys()),
        "refs": refs,
        "text": (
            "以下为拆书参考骨架（确定性产物，待 LLM 填充，仅作风格/结构参考）：\n\n"
            + combined
        ),
    }


# ────────────────────────────────────────────────────────────
# 注入器
# ────────────────────────────────────────────────────────────
def inject_capture_into_brainstorm(state, user_params):
    """把扫榜参考文本并入 脑洞 阶段的 user_params（新增「扫榜参考」键）。

    返回合并后的 user_params dict；无参考文本时原样返回。
    """
    ins = getattr(state, "capture_insights", None) or {}
    text = ins.get("text")
    if not text:
        return user_params if user_params is not None else {}
    params = dict(user_params) if user_params else {}
    params["扫榜参考"] = text
    return params


def inject_analysis_into_characters_outline(state, stage):
    """把拆书参考作为 人设/大纲/细纲/概要 阶段的参考块文本返回（字符串）。

    无参考文本时返回 ""（调用方据此不注入）。
    """
    refs = getattr(state, "analysis_refs", None) or {}
    text = refs.get("text")
    return text or ""
