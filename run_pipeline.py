# -*- coding: utf-8 -*-
"""
run_pipeline.py — 全自动熔铸管道

用法:
    python run_pipeline.py
    python run_pipeline.py --category 01_现代言情
    python run_pipeline.py --category 05_古代言情
    python run_pipeline.py --sample 5
    python run_pipeline.py --stage 脑洞          ← 分阶段模式
    python run_pipeline.py -s 开篇 -c 05_古代言情 --template 西瓜大法
    python run_pipeline.py -s 正文 -P output/开篇_output.txt  ← 链式传递

    # 反模式生成 (公因子反转,最大化预期违背=爽感)
    python run_pipeline.py -s 正文 --anti
    python run_pipeline.py -s 正文 --anti --recipe 重度反模式
    python run_pipeline.py -s 大纲 --anti --recipe 极限反模式

    # 无钢印反模式 (不预设维度,纯自由反向)
    python run_pipeline.py -c 03_系统快穿 --anti --anti-free

    # 反朱雀保守校准 (对 output/story.txt 做机械过渡替换, 默认关闭)
    python run_pipeline.py --humanize

    # 本地三交叉终判 (默认关闭, 生成 output/story.txt 后运行, 写 output/narrative_verdict.json)
    python run_pipeline.py --narrative-check

    # 拼装4个叙事阶段输出为成稿 story.txt (P-G3/P-G4/P-G5)
    python run_pipeline.py --assemble
    python run_pipeline.py --assemble --target-chars 10000

    # 拼装后风格质检（P-S6，默认开启，仅报告不中断；可关闭或硬阻断）
    python run_pipeline.py --assemble              ← 默认跑 QA 报告块
    python run_pipeline.py --assemble --no-qa       ← 跳过 QA 报告块
    python run_pipeline.py --assemble --qa-strict   ← QA 未过则退出码 1（CI 硬阻断）

    # 方法论自动织入（approach A，默认开启：按阶段/题材自动织入 prompt/methodology/ 卡片）
    python run_pipeline.py -s 正文 -c 05_古代言情          ← 默认自动织入方法论
    python run_pipeline.py -s 正文 --no-methodology         ← 关闭方法论自动织入
    python run_pipeline.py -s 正文 --short-mode             ← 启用短篇专属方法论(short/)

    # 统一流四步骤（capture/analyze 前置，cover 后置，browser 旁路；默认全关，需显式开启）
    python run_pipeline.py -s 正文 -c 05_古代言情 --with capture,analyze,cover
    python run_pipeline.py --capture --capture-platform fanqie --capture-channel 1 --capture-type 2
    python run_pipeline.py --analyze --analyze-input 某书.txt --analyze-book 某书
    GPT_IMAGE_API_KEY=xxx python run_pipeline.py -s 正文 --cover --cover-prompt "..."
    python run_pipeline.py --browser --browser-action launch --browser-detect-only
    # 纯 generate（不传任何 step 标志）== 原 12 阶段熔铸管道（零改动）

corpus 结构（管道自动识别任意子目录，无需预设分类）:
    corpus/小说.txt                    ← 平铺
    corpus/01_现代言情/小说.txt         ← 分类子目录
    corpus/05_古代言情/小说.txt
"""
import sys, os, random, re, time, json, glob
from datetime import datetime

# ── 编码强制 UTF-8（解决 Windows cmd/bash 乱码）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── 优先使用本项目 venv（跨平台自动发现 site-packages）
_here = os.path.dirname(os.path.abspath(__file__))
_venv_dir = os.path.join(_here, ".venv")
if os.path.isdir(_venv_dir):
    # 检测是否已在 venv 中运行（无需手动注入）
    _in_venv = (hasattr(sys, 'real_prefix') or
                (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))
    if not _in_venv:
        # Linux/Mac: .venv/lib/python3.x/site-packages
        _venv_lib = os.path.join(_venv_dir, "lib")
        if os.path.isdir(_venv_lib):
            for _py_ver_dir in sorted(os.listdir(_venv_lib), reverse=True):
                _sp = os.path.join(_venv_lib, _py_ver_dir, "site-packages")
                if os.path.isdir(_sp) and _sp not in sys.path:
                    sys.path.insert(0, _sp)
                    break
        else:
            # Windows: .venv/Lib/site-packages
            _venv_site = os.path.join(_venv_dir, "Lib", "site-packages")
            if os.path.isdir(_venv_site) and _venv_site not in sys.path:
                sys.path.insert(0, _venv_site)

# ── 统一流胶水模块（新增，仅标准库：os/json/argparse/dataclasses/re/glob）
#    四工具逻辑零改动，仅经本模块构造 argv 喂给它们。
sys.path.insert(0, os.path.join(_here, "tools"))
from workflow_hooks import (
    WorkflowState,
    build_capture_argv,
    build_analyze_argv,
    build_cover_argv,
    build_browser_argv,
    read_capture_insights,
    read_analysis_refs,
    inject_capture_into_brainstorm,
    inject_analysis_into_characters_outline,
    detect_book_name,
)

ISSUES = []
OUTPUT_DIR = os.path.join(_here, "output")
CORPUS_DIR = os.path.join(_here, "corpus")
PROMPT_DIR = os.path.join(_here, "prompt")
METHODOLOGY_DIR = os.path.join(PROMPT_DIR, "methodology")  # approach A: 方法论自动织入目录
MIN_CHINESE = 500   # 低于此中文字数视为损坏文件，跳过

# ── 自动扩写闭环（--expand-to N）控制常量
MAX_EXPAND_ROUNDS = 5      # 闭环硬上限轮次
EXPAND_THRESHOLD = 0.95    # 达标线：成稿 ≥ N × 0.95 即视为达标
PER_ROUND_CAP = 3000       # 单轮预算上限（字），避免单轮 prompt 过载
FUSION_CONTEXT_CAP = 8000  # 融合上下文截断上限（20维指纹+双层互消+DNA锚点）
MIN_EXPAND_BUDGET = 200    # 剩余缺口过小则跳过收尾
EXPAND_GEN_HOOK = None     # 可选注入点：挂 LLM 客户端实现进程内全自动；默认 None（零模型）

# ── 章节识别正则（模块级，供 assemble_story / _check_assemble_consistency / _locate_shortest_chapter 复用）
CHAPTER_RE = re.compile(r"^第([一二三四五六七八九十百千零两\d]+)章", re.MULTILINE)

# ── 创作阶段 → 提示词文件映射
STAGE_PROMPT_MAP = {
    "脑洞": os.path.join(PROMPT_DIR, "prompt_inspiration.md"),
    "灵感风暴": os.path.join(PROMPT_DIR, "prompt_inspiration.md"),
    "人设": os.path.join(PROMPT_DIR, "prompt_character.md"),
    "大纲": os.path.join(PROMPT_DIR, "prompt_outline.md"),
    "细纲": os.path.join(PROMPT_DIR, "prompt_outline.md"),
    "概要": os.path.join(PROMPT_DIR, "prompt_outline.md"),
    "开篇": os.path.join(PROMPT_DIR, "prompt_opening.md"),
    "正文": os.path.join(PROMPT_DIR, "prompt_writing.md"),
    "优化": os.path.join(PROMPT_DIR, "prompt_polish.md"),
    "润色": os.path.join(PROMPT_DIR, "prompt_polish.md"),
    "续写": os.path.join(PROMPT_DIR, "prompt_expand.md"),
    "扩写": os.path.join(PROMPT_DIR, "prompt_expand.md"),
}

# ── 阶段 → 对应融合文件内的节目标记
STAGE_SECTION_MAP = {
    # 仅包含 STAGE_PROMPT_MAP 中实际使用的阶段
    "脑洞": "脑洞生成器",
    "灵感风暴": "灵感风暴",
    "人设": "人设生成器",
    "大纲": "大纲相关",
    "细纲": "细纲生成",
    "概要": "概要生成器",
    "开篇": "黄金开篇",
    "正文": "写作要求",
    "优化": "优化建议",
    "润色": "润色",
    "续写": "续写",
    "扩写": "扩写",
}

# ── 阶段顺序（用于 --previous-output 自动推断）
STAGE_ORDER = ["脑洞", "灵感风暴", "人设", "大纲", "细纲", "概要", "开篇", "正文", "优化", "润色", "续写", "扩写"]

# ── 拼装后自动风格质检配置（P-S6）
#    main() 据 opts 覆写；assemble_story 仅读取，不修改。
_QA_CFG: dict = {"enabled": True, "strict": False}


def _print_usage():
    """打印 run_pipeline.py 单流用法（统一流四步骤，已移除 --mode 平行入口）。"""
    print(
        "用法: python run_pipeline.py [选项]\n"
        "\n"
        "创作生成（12 阶段熔铸管道，主干必走；methodology_weaver 每阶段织入）:\n"
        "  -c/--category 分类    指定 corpus 子分类\n"
        "  -n/--sample N         采样源文篇数（默认 5）\n"
        "  -s/--stage 阶段       单阶段模式（脑洞/人设/大纲/开篇/正文/优化/润色/续写/扩写）\n"
        "  -t/--template 关键词  模板关键词筛选\n"
        "  --anti                反模式生成\n"
        "  --humanize            反朱雀保守校准（仅后处理 output/story.txt）\n"
        "  --assemble            拼装叙事阶段为成稿 story.txt\n"
        "  --expand-to N         自动扩写闭环至 N 字\n"
        "  --narrative-check     本地三交叉终判\n"
        "  --no-methodology      关闭方法论自动织入（approach A，默认开启）\n"
        "  --short-mode          启用短篇专属方法论（额外织入 prompt/methodology/short/）\n"
        "  --methodology-budget N  方法论织入字符上限（默认4000，重阶段可设6000）\n"
        "  --auto                全自动12阶段串联，一键生成全部prompt（LLM产出由主理人填充）\n"
        "\n"
        "互消层升级（v6.3+，DNA 演化蒸馏 + 增强指纹；默认全关/可选）:\n"
        "  --rebuild-dna         强制重建叙事 DNA 演化表（默认命中缓存 data/_narrative_dna.json）\n"
        "  --dna-scope 范围      演化数据源: category(默认,同题材 corpus/<category>/) / all(全量 corpus/)\n"
        "  --enhanced-fingerprint 开启增强指纹(默认关; ngram/plot/syntax 子开关见下)\n"
        "  --ef-ngram/--ef-plot/--ef-syntax 增强指纹子开关(默认全关; 开启也不注入生成指令)\n"
        "  注: 增强指纹默认关,新增字段仅作内部/诊断,不削弱朱雀不可反查目标。\n"
        "\n"
        "模块集成（v6.3+, 默认关闭）:\n"
        "  --rag                    开启 RAG 约束检索（默认关闭）\n"
        "  --rag-tags TAG           RAG 检索标签\n"
        "  --rag-top-k N            RAG 召回源文数（默认 5）\n"
        "  --postprocess             开启后处理链（默认关闭）\n"
        "  --postprocess-excl D     感叹号注入密度（默认 0.15）\n"
        "  --postprocess-comma D    逗号注入密度（默认 1.2）\n"
        "  --no-check-story         关闭 assemble 后的 check_story 全量质检\n"
        "\n"
        "统一流四步骤（可选，默认全关；开启后按 前置→主干→后置/旁路 串联，任一失败仅 WARN）:\n"
        "  --capture             [前置] 网文市场扫榜采集（tools/story_capture.py）→ 注入 脑洞\n"
        "  --analyze             [前置] 网文逆向拆书（tools/story_analyze.py）→ 注入 人设/大纲\n"
        "  --cover               [后置] 封面生成（tools/cover_gen.py，需 GPT_IMAGE_API_KEY）\n"
        "  --browser             [旁路] Chrome CDP 巡检（tools/browser_ctl.py，launch/browse）\n"
        "  --with 逗号列表        聚合开启上述步骤，如 --with capture,analyze,cover,browser\n"
        "  前置/后置透传:\n"
        "    capture: --capture-platform(默认qidian) --capture-type --capture-channel --capture-top --capture-outdir(默认<root>/scan_output)\n"
        "    analyze: --analyze-input(必填本地txt/目录) --analyze-book --analyze-length --analyze-force\n"
        "    cover:   --cover-book --cover-prompt --cover-api-key --cover-size\n"
        "    browser: --browser-action(默认launch) --browser-port(默认9222) --browser-detect-only\n"
        "\n"
        "示例:\n"
        "  python run_pipeline.py -s 正文 -c 05_古代言情\n"
        "  python run_pipeline.py -s 正文 -c 05_古代言情 --with capture,analyze,cover\n"
        "  python run_pipeline.py --capture --capture-platform fanqie --capture-channel 1 --capture-type 2\n"
        "  python run_pipeline.py --analyze --analyze-input 某书.txt --analyze-book 某书\n"
        "  GPT_IMAGE_API_KEY=xxx python run_pipeline.py -s 正文 --cover --cover-prompt \"...\"\n"
        "  python run_pipeline.py --browser --browser-action launch --browser-detect-only\n"
    )


def _resolve_steps(opts, state):
    """根据 --capture/--analyze/--cover/--browser 及 --with 聚合开关解析可选步骤开关。

    --with 为逗号分隔的聚合列表（如 capture,analyze,cover,browser）；
    单独的开关与 --with 取并集。
    """
    steps = set()
    if opts.get("capture"):
        steps.add("capture")
    if opts.get("analyze"):
        steps.add("analyze")
    if opts.get("cover"):
        steps.add("cover")
    if opts.get("browser"):
        steps.add("browser")
    with_csv = (opts.get("with") or "").strip()
    if with_csv:
        for tok in with_csv.split(","):
            t = tok.strip().lower()
            if t:
                steps.add(t)
    state.do_capture = "capture" in steps
    state.do_analyze = "analyze" in steps
    state.do_cover = "cover" in steps
    state.do_browser = "browser" in steps
    return state


def run_unified_workflow(opts):
    """统一流编排器（完全融合：取代旧 dispatch_mode 平行分派）。

    步骤链：
      [可选前置] capture → 写 scan_output/            （仅 --capture/--with 开启）
      [可选前置] analyze → 写 analysis/{书名}/        （仅 --analyze/--with 开启）
      12 阶段 generate 主干（含 methodology_weaver 每阶段织入，零改动）  ← 必走
        └─ assemble_story → output/story.txt（保留）
      [可选后置] cover   → 写 covers/{书名}/cover.png （仅 --cover/--with 开启）
      [可选旁路] browser → CDP 巡检（失败仅 WARN）      （仅 --browser/--with 开启）

    关键：旧 dispatch_mode 在 --mode X 时 sys.exit 直接退出；新编排器把可选步骤
    作为步骤返回继续走后续步骤，只有生成主干自身异常才退出。统一流最终返回 0
    （除非主干异常）。任意可选步骤未开启或失败均不阻断 12 阶段主干。
    """
    sys.path.insert(0, os.path.join(_here, "tools"))

    # ── 初始化统一流状态
    scan_output_dir = opts.get("capture_outdir") or os.path.join(_here, "scan_output")
    analysis_dir = os.path.join(_here, "analysis")
    state = WorkflowState(
        category=opts.get("category"),
        topic=(opts.get("params") or {}).get("核心卖点"),
        sample=opts.get("sample", 5),
        target_chars=opts.get("target_chars"),
        short_mode=opts.get("short_mode", False),
        no_methodology=opts.get("no_methodology", False),
        scan_output_dir=scan_output_dir,
        analysis_dir=analysis_dir,
        story_path=os.path.join(OUTPUT_DIR, "story.txt"),
    )
    _resolve_steps(opts, state)

    # ── 可选前置：capture / analyze（开启时运行并读取产物，失败仅 WARN）
    if state.do_capture:
        _run_step_capture(state, opts)
    if state.do_analyze:
        _run_step_analyze(state, opts)

    # ── 特殊模式早退（向后兼容：与原 main() 行为一致，不触碰生成主干）
    if opts.get("humanize") and opts.get("stage") is None:
        run_humanize()
        print(f"\n✅ 反朱雀校准完成。可运行检查: python tools/check_padding.py output/story.txt")
        return 0
    if opts.get("assemble") and opts.get("stage") is None:
        _QA_CFG["no_check_story"] = opts.get("no_check_story", False)
        assemble_story(opts.get("target_chars"),
                       genre=opts.get("category"),
                       anti_mode=opts.get("anti", False))
        print(f"\n✅ 拼装完成。成稿: output/story.txt")
        return 0
    if opts.get("postprocess") and opts.get("stage") is None:
        story_path = os.path.join(OUTPUT_DIR, "story.txt")
        if not os.path.exists(story_path):
            log("[postprocess] output/story.txt 不存在", "WARN")
            return 1
        _run_postprocess_chain(
            story_path,
            excl_density=opts.get("postprocess_excl", 0.15),
            comma_density=opts.get("postprocess_comma", 1.2),
        )
        print(f"\n✅ 后处理完成。成稿: output/story.txt")
        return 0
    if opts.get("expand_to") is not None:
        expand_loop(
            opts["expand_to"],
            category=opts.get("category"),
            short_mode=opts.get("short_mode", False),
            methodology_budget=opts.get("methodology_budget", 4000),
        )
        print(f"\n✅ 自动扩写闭环结束。成稿: output/story.txt")
        return 0

    # ── 12 阶段 generate 主干（必走）
    _run_generate_trunk(opts, state)

    # ── 可选后置：cover（story.txt 之后）
    if state.do_cover:
        _run_step_cover(state, opts)

    # ── 可选旁路：browser（失败仅 WARN，不阻断主干）
    if state.do_browser:
        _run_step_browser(state, opts)

    return 0


def _run_step_capture(state, opts):
    """可选前置：扫榜。失败仅 WARN，不阻断主干。"""
    try:
        from story_capture import capture as _fn
        argv = build_capture_argv(opts, state)
        log(f"[unified] 前置 capture: {' '.join(argv)}")
        rc = _fn(argv)
        if rc != 0:
            log(f"[unified] capture 返回非零({rc})，跳过读产物（仅 WARN）", "WARN")
        else:
            state.capture_insights = read_capture_insights(state.scan_output_dir)
            if state.capture_insights:
                log(f"[unified] 已读取扫榜参考: {state.capture_insights.get('source_file')}")
    except Exception as e:
        log(f"[unified] capture 步骤失败: {e}（仅 WARN，不阻断主干）", "WARN")


def _run_step_analyze(state, opts):
    """可选前置：拆书。失败仅 WARN，不阻断主干。"""
    analyze_input = opts.get("analyze_input")
    if not analyze_input:
        log("[unified] analyze 需 --analyze-input（本地 txt/目录），未提供则跳过", "WARN")
        return
    try:
        from story_analyze import analyze as _fn
        argv = build_analyze_argv(opts, state)
        log(f"[unified] 前置 analyze: {' '.join(argv)}")
        rc = _fn(argv)
        if rc != 0:
            log(f"[unified] analyze 返回非零({rc})，跳过读产物（仅 WARN）", "WARN")
            return
        book = opts.get("analyze_book") or _derive_analyze_book(analyze_input)
        analysis_book_dir = os.path.join(state.analysis_dir, book)
        state.analysis_refs = read_analysis_refs(analysis_book_dir)
        if state.analysis_refs:
            log(f"[unified] 已读取拆书参考: {analysis_book_dir}")
    except Exception as e:
        log(f"[unified] analyze 步骤失败: {e}（仅 WARN，不阻断主干）", "WARN")


def _derive_analyze_book(analyze_input):
    """从 --analyze-input 路径推导 analyze 的书名（与 story_analyze._sanitize_book 对齐）。"""
    base = os.path.basename(os.path.normpath(analyze_input))
    name = re.sub(r"\.(txt|md)$", "", base, flags=re.I).strip()
    for ch in "/\\:*?\"<>|":
        name = name.replace(ch, "_")
    return name or "未命名"


def _run_step_cover(state, opts):
    """可选后置：封面。缺 PROMPT/KEY 或失败均仅 WARN，不阻断主干。"""
    try:
        argv = build_cover_argv(opts, state)
        if argv is None:
            log(
                "[unified] cover 缺少 PROMPT/API key（--cover-prompt / --cover-api-key / "
                "环境变量 GPT_IMAGE_API_KEY），跳过封面生成（仅 WARN）",
                "WARN",
            )
            return
        from cover_gen import generate_cover as _fn
        log(f"[unified] 后置 cover: {' '.join(argv)}")
        rc = _fn(argv)
        if rc != 0:
            log(f"[unified] cover 返回非零({rc})，跳过（仅 WARN）", "WARN")
            return
        book = detect_book_name(opts, state)
        cover_path = os.path.join(
            os.path.dirname(state.analysis_dir), "covers", book, "cover.png"
        )
        if os.path.exists(cover_path):
            state.cover_path = cover_path
            log(f"[unified] 封面已生成: {cover_path}")
    except Exception as e:
        log(f"[unified] cover 步骤失败: {e}（仅 WARN，不阻断主干）", "WARN")


def _run_step_browser(state, opts):
    """可选旁路：Chrome CDP 巡检。失败仅 WARN，不阻断主干。"""
    try:
        argv = build_browser_argv(opts)
        from browser_ctl import launch_cdp as _fn
        log(f"[unified] 旁路 browser: {' '.join(argv)}")
        rc = _fn(argv)
        if rc != 0:
            log(f"[unified] browser 返回非零({rc})，仅 WARN（不阻断主干）", "WARN")
    except Exception as e:
        log(f"[unified] browser 步骤失败: {e}（仅 WARN，不阻断主干）", "WARN")


def _run_auto_pipeline(opts, category, fusion_context, user_params, target_chars):
    """全自动管线：按顺序生成12阶段prompt，LLM产出由主理人(对话LLM)填充"""
    AUTO_STAGES = [
        "脑洞", "灵感风暴", "人设", "大纲", "细纲", "概要",
        "开篇", "正文", "优化", "润色", "续写", "扩写"
    ]

    previous_output = None  # 链式上下文

    for stage in AUTO_STAGES:
        if stage not in STAGE_PROMPT_MAP:
            continue

        # 加载模板
        template_path = STAGE_PROMPT_MAP[stage]
        if not os.path.exists(template_path):
            log(f"[auto] 跳过 {stage}：模板缺失 {template_path}", "WARN")
            continue

        prompt_template = read_file_safe(template_path)
        if not prompt_template.strip():
            log(f"[auto] 跳过 {stage}：模板为空", "WARN")
            continue

        log(f"\n{'='*40}")
        log(f"[auto] 阶段 {AUTO_STAGES.index(stage)+1}/{len(AUTO_STAGES)}: {stage}")
        log(f"{'='*40}")

        # 方法论织入
        methodology_context = ""
        if not opts.get("no_methodology"):
            try:
                from tools.methodology_weaver import weave_methodology
                mb = opts.get("methodology_budget", 4000)
                methodology_context = weave_methodology(stage, category, opts.get("short_mode", False), budget=mb)
            except Exception as e:
                log(f"方法论织入失败,跳过: {e}", "WARN")

        # 拼装 prompt
        full_prompt = build_full_prompt(
            stage, prompt_template, fusion_context, user_params, previous_output,
            target_chars, methodology_context=methodology_context,
        )

        # 保存 prompt
        prompt_out = os.path.join(OUTPUT_DIR, f"{stage}_llm_prompt.txt")
        with open(prompt_out, "w", encoding="utf-8") as f:
            f.write(full_prompt)
        log(f"[auto] prompt 已保存: {stage}_llm_prompt.txt ({len(full_prompt)} 字符)")

        # 保存占位符输出（LLM填充口）
        output_out = os.path.join(OUTPUT_DIR, f"{stage}_output.txt")
        with open(output_out, "w", encoding="utf-8") as f:
            f.write(f"【待LLM填充 — 阶段: {stage}】\n")

        # 链式：下一阶段引用当前输出
        previous_output = f"【前一阶段({stage})的LLM产出将自动注入此处。主理人填充 {stage}_output.txt 后重新运行即可。】\n"

    log(f"\n{'='*40}")
    log(f"[auto] 12阶段 prompt 全部生成完毕。请主理人按序调用LLM填充各阶段 output/{{阶段}}_output.txt")
    log(f"[auto] 完成后运行: python run_pipeline.py --assemble 拼装成稿")
    log(f"{'='*40}")

    # 汇总文件
    summary_path = os.path.join(OUTPUT_DIR, "auto_pipeline_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("全自动管线 — 12阶段填充清单\n")
        f.write("="*60 + "\n\n")
        for i, stage in enumerate(AUTO_STAGES):
            prompt_f = os.path.join(OUTPUT_DIR, f"{stage}_llm_prompt.txt")
            output_f = os.path.join(OUTPUT_DIR, f"{stage}_output.txt")
            size = os.path.getsize(prompt_f) if os.path.exists(prompt_f) else 0
            f.write(f"{i+1:2d}. {stage:6s}  prompt:{size:>6d}字符 → 输出: {output_f}\n")
        f.write(f"\n完成后: python run_pipeline.py --assemble\n")
    log(f"[auto] 填充清单已保存: auto_pipeline_summary.txt")


def _run_rag_retrieve(category=None, tags=None, top_k=5,
                       corpus_root=None, out_dir=None):
    """RAG 约束检索。返回 dict 或 None（静默降级）。"""
    try:
        sys.path.insert(0, os.path.join(_here, "tools"))
        from rag_retriever import retrieve
        cr = corpus_root or CORPUS_DIR
        result = retrieve(category=category, tags=tags, top_k=top_k, corpus_root=cr)
        od = out_dir or OUTPUT_DIR
        out_path = os.path.join(od, "_rag_constraints.json")
        import json
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        log(f"[rag] 约束检索完成 -> {out_path}")
        log(f"[rag]   黑名单: {len(result.get('content_blacklist', []))} 条")
        return result
    except Exception as e:
        log(f"[rag] 检索失败: {e}（仅 WARN，不阻断）", "WARN")
        return None


def _run_generate_trunk(opts, state):
    """12 阶段 generate 主干（取代旧 main() 中生成主干逻辑）。

    原样保留 methodology_weaver 每阶段织入调用点（原主路径、扩写闭环 :622-629）。
    统一流前置 capture/analyze 产物在对应阶段注入 user_params，但 weave 调用不受影响。
    """
    category = opts["category"]
    sample_n = opts["sample"]
    stage = opts["stage"]
    template = opts["template"]
    user_params = opts["params"]
    is_interactive = opts["interactive"]
    previous_output_path = opts["previous_output"]
    anti_mode = opts["anti"]
    anti_free = opts["anti_free"]
    recipe = opts["recipe"] or ("中度反模式" if anti_mode else None)
    humanize = opts["humanize"]
    narrative_check = opts["narrative_check"]
    assemble = opts["assemble"]
    target_chars = opts["target_chars"]
    expand_to = opts["expand_to"]

    # ── P-S6: 据命令行开关覆写拼装后质检配置（_QA_CFG 模块级，assemble_story 仅读取）
    _QA_CFG["enabled"] = not opts.get("no_qa", False)
    _QA_CFG["strict"] = bool(opts.get("qa_strict", False))
    _QA_CFG["no_check_story"] = opts.get("no_check_story", False)

    log("=== 熔铸管道启动 ===")
    log(f"工作目录: {_here}")
    if stage:
        log(f"创作阶段: {stage}")
        if state.do_capture or state.do_analyze or state.do_cover or state.do_browser:
            _steps_on = [
                s for s, v in (
                    ("capture", state.do_capture),
                    ("analyze", state.do_analyze),
                    ("cover", state.do_cover),
                    ("browser", state.do_browser),
                ) if v
            ]
            log(f"统一流步骤: {', '.join(_steps_on)}")
    if anti_mode:
        if anti_free:
            log("反模式生成: 无钢印自由反向")
        else:
            log(f"反模式生成: 开启 | 配方: {recipe}")

    # ── 前序阶段输出自动推断
    previous_output = None
    if stage and previous_output_path:
        # 用户显式指定
        if os.path.exists(previous_output_path):
            previous_output = read_file_safe(previous_output_path)
            log(f"加载前序输出: {previous_output_path} ({len(previous_output)} 字符)")
        else:
            log(f"前序输出文件不存在: {previous_output_path}", "WARN")
    elif stage and stage in STAGE_ORDER:
        # 自动推断：查找output/目录下前一个阶段的LLM输出
        idx = STAGE_ORDER.index(stage)
        if idx > 0:
            prev_stage = STAGE_ORDER[idx - 1]
            # 尝试多种可能的文件名
            candidates = [
                f"{prev_stage}_output.txt",
                f"{prev_stage}_result.txt",
                f"story_{prev_stage}.txt",
            ]
            for cand in candidates:
                cand_path = os.path.join(OUTPUT_DIR, cand)
                if os.path.exists(cand_path):
                    previous_output = read_file_safe(cand_path)
                    log(f"自动加载前序阶段 [{prev_stage}] 输出: {cand} ({len(previous_output)} 字符)")
                    break

    # ── 环境检查
    try:
        import jieba
        log(f"jieba {jieba.__version__}")
    except ImportError:
        log("jieba 未安装 → 请运行: pip install jieba", "ERROR")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Step 1: 扫描 corpus + 选源文（优化阶段不需要；无 --stage 的后处理模式也跳过）
    fusion_context = ""
    if (stage is not None and stage != "优化") or opts.get("auto"):
        log("\n--- Step 1: 扫描 corpus 并选源文 ---")
        all_files = collect_corpus(CORPUS_DIR, category)

        if not all_files:
            log(f"corpus 为空（category={category}）", "ERROR")
            sys.exit(1)

        cats = {}
        for p, c in all_files:
            cats.setdefault(c, 0)
            cats[c] += 1
        log(f"corpus 总文件: {len(all_files)} 篇")
        for c, cnt in sorted(cats.items()):
            log(f"  [{c}] {cnt} 篇")

        picked = pick_healthy(all_files, sample_n, category)
        if len(picked) < 3:
            log("健康源文不足 3 篇，无法继续", "ERROR")
            sys.exit(1)

        log(f"\n最终选中 {len(picked)} 篇:")
        for p in picked:
            log(f"  {os.path.basename(p)}")

        with open(os.path.join(OUTPUT_DIR, "picked_sources.txt"), "w", encoding="utf-8") as f:
            for p in picked:
                f.write(p + "\n")

        # P1: RAG 约束检索（--rag 开启）
        rag_constraints = None
        if opts.get("rag"):
            rag_constraints = _run_rag_retrieve(
                category=category,
                tags=opts.get("rag_tags"),
                top_k=opts.get("rag_top_k", 5),
            )

        # ── Step 2: 蒸馏指纹
        log("\n--- Step 2: 蒸馏指纹 ---")
        sys.path.insert(0, _here)
        import tools.fusion as fusion_mod

        # ── 互消层升级（v6.3+）：DNA 演化蒸馏（可选，失败回退内置表）
        dna = {}
        if getattr(fusion_mod, "_DNA_OK", False):
            try:
                _scope = opts.get("dna_scope", "category")
                dna = fusion_mod.load_or_build_dna(
                    opts.get("category"), _scope, bool(opts.get("rebuild_dna"))
                )
            except Exception as e:
                log(f"DNA蒸馏失败,回退内置表: {e}", "WARN")
        _enhanced = bool(opts.get("enhanced_fingerprint"))
        _enhanced_opts = {
            "ngram": bool(opts.get("ef_ngram")),
            "plot": bool(opts.get("ef_plot")),
            "syntax": bool(opts.get("ef_syntax")),
        }

        files_info = []
        for fp in picked:
            text = read_file_safe(fp)
            fingerprint = fusion_mod.extract_fingerprint(
                text, enhanced=_enhanced, enhanced_opts=_enhanced_opts
            )
            files_info.append({"name": os.path.basename(fp), "fp": fingerprint})

        prompt = fusion_mod.build_llm_prompt(files_info, include_rules=False, dna=dna)
        fusion_context = prompt

        # ── 反模式: 生成反因子上下文
        if anti_mode:
            try:
                import tools.anti_pattern as anti_mod
                engine = anti_mod.AntiPatternEngine(recipe=recipe)
                if anti_free:
                    anti_context = engine.build_freeform_anti_prompt(files_info)
                    log("无钢印反模式上下文生成完成 | 模式: 自由反向 | 无预设维度/无类型标签")
                else:
                    anti_context = engine.build_anti_prompt(files_info, stage=stage or "正文")
                    log(f"反模式上下文生成完成 | 配方: {recipe} | 目标EI: {engine.recipe_config.get('ei_target', 'N/A')}")
                fusion_context = anti_context
            except Exception as e:
                log(f"反模式引擎异常,回退到互消模式: {e}", "WARN")

        fusion_out = os.path.join(OUTPUT_DIR, "fusion_context.txt")
        with open(fusion_out, "w", encoding="utf-8") as f:
            f.write(fusion_context)

        # RAG 黑名单约束注入
        if rag_constraints:
            bl = rag_constraints.get("content_blacklist", [])
            if bl:
                bl_block = "\n\n【RAG 约束：禁止直接复用以下高频专名/设定词】\n"
                bl_block += "、".join(bl[:12])
                bl_block += "\n（以上词汇源自同题材 corpus 统计，仅作反向约束）\n"
                fusion_context = fusion_context.rstrip() + bl_block

        log(f"指纹蒸馏完成 -> fusion_context.txt ({len(fusion_context)} 字符)")

    # ── 全自动模式：串联12阶段
    if opts.get("auto"):
        _run_auto_pipeline(opts, category, fusion_context, user_params, target_chars)
        return

    # ── Step 3: 加载提示词 + 拼装指令
    if stage and stage in STAGE_PROMPT_MAP:
        log(f"\n--- Step 3: 加载提示词模板 [{stage}] ---")
        prompt_template = load_prompt_template(stage, template)
        if not prompt_template:
            log(f"提示词模板加载失败（stage={stage}, template={template}），跳过生成", "WARN")
            return
        log(f"提示词模板加载成功 ({len(prompt_template)} 字符)")

        # 交互式参数输入
        if is_interactive:
            user_params = {**user_params, **input_user_params(stage)}

        # ── 统一流前置注入（capture→脑洞 / analyze→人设·大纲·细纲·概要）
        #    注入点仍在 build_full_prompt 的 user_params，保留 methodology 织入。
        if stage == "脑洞" and state.capture_insights:
            user_params = inject_capture_into_brainstorm(state, user_params)
        if stage in ("人设", "大纲", "细纲", "概要") and state.analysis_refs:
            ref_block = inject_analysis_into_characters_outline(state, stage)
            if ref_block:
                user_params = {**user_params, "拆书参考": ref_block}

        # 拼装完整指令
        # 写作方法学（approach A: 运行时自动织入）—— 按阶段/题材自动选取方法论卡片
        # （红线：每阶段织入，原样保留旧 :1076-1083 调用点）
        methodology_context = ""
        if not opts.get("no_methodology") and stage and stage in STAGE_PROMPT_MAP:
            try:
                from tools.methodology_weaver import weave_methodology
                mb = opts.get("methodology_budget", 4000)
                methodology_context = weave_methodology(stage, category, opts.get("short_mode", False), budget=mb)
            except Exception as e:
                log(f"方法论织入失败,跳过: {e}", "WARN")
        full_prompt = build_full_prompt(
            stage, prompt_template, fusion_context, user_params, previous_output,
            target_chars, methodology_context=methodology_context,
        )
        prompt_out = os.path.join(OUTPUT_DIR, f"{stage}_llm_prompt.txt")
        with open(prompt_out, "w", encoding="utf-8") as f:
            f.write(full_prompt)
        log(f"完整LLM调用指令已保存: {stage}_llm_prompt.txt ({len(full_prompt)} 字符)")
    else:
        # 无stage → 原始模式
        if not stage:
            log("\n--- Step 3: LLM生成短篇（原始模式） ---")
            log("提示：零模型模式不调用LLM，仅生成指纹融合上下文(fusion_context.txt)。"
                "请将其交给LLM生成正文，保存到output/story.txt后运行后处理。")
        fusion_out = os.path.join(OUTPUT_DIR, "fusion_context.txt")
        if os.path.exists(fusion_out):
            log(f"读取 {fusion_out} → 生成 → 写入 output/story.txt")
        story_out = os.path.join(OUTPUT_DIR, "story.txt")
        if not os.path.exists(story_out) or _read_file_safe_for_check(story_out):
            with open(story_out, "w", encoding="utf-8") as f:
                f.write("【待LLM填充】\n")

    # ── 可选：反朱雀保守校准（默认关闭，需 --humanize；纯 --humanize 已在上方早退）
    if humanize:
        run_humanize()

    # P2: 后处理链（generate 主干后侧）
    if opts.get("postprocess"):
        story_path = os.path.join(OUTPUT_DIR, "story.txt")
        if os.path.exists(story_path):
            _run_postprocess_chain(
                story_path,
                excl_density=opts.get("postprocess_excl", 0.15),
                comma_density=opts.get("postprocess_comma", 1.2),
            )

    # ── 写入运行日志
    issues_out = os.path.join(OUTPUT_DIR, "pipeline_issues.txt")
    with open(issues_out, "w", encoding="utf-8") as f:
        f.write("熔铸管道运行记录\n")
        f.write("=" * 50 + "\n")
        f.write(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        if stage:
            f.write(f"创作阶段: {stage}\n")
        if anti_mode:
            f.write(f"反模式: 开启 | 配方: {recipe}\n")
        f.write("\n")
        for line in ISSUES:
            f.write(line + "\n")
        f.write("\n--- 以下为生成阶段后补 ---\n")
    log(f"运行日志已保存: output/pipeline_issues.txt")

    # ── 可选：本地三交叉终判（默认关闭，需 --narrative-check）
    # 生成 output/story.txt 后调用 triple_cross_judge，把共识 verdict 写入 output/narrative_verdict.json
    if narrative_check:
        _story_out = os.path.join(OUTPUT_DIR, "story.txt")
        if not os.path.exists(_story_out) or _read_file_safe_for_check(_story_out):
            log("[narrative-check] output/story.txt 不存在或为占位符，跳过三交叉终判", "WARN")
        else:
            try:
                sys.path.insert(0, os.path.join(_here, "tools"))
                from tools.humanity_scorer import triple_cross_judge
                _tc_text = read_file_safe(_story_out)
                _nar_base = None
                _base_path = os.path.join(_here, "data", "_narrative_baseline.json")
                if os.path.isfile(_base_path):
                    with open(_base_path, encoding="utf-8") as f:
                        _nar_base = json.load(f)
                _tc = triple_cross_judge(_tc_text, baseline=_nar_base)
                _verdict_path = os.path.join(OUTPUT_DIR, "narrative_verdict.json")
                with open(_verdict_path, "w", encoding="utf-8") as f:
                    json.dump(_tc, f, ensure_ascii=False, indent=2)
                log(f"[narrative-check] 三方交叉共识 verdict={_tc['verdict']} → {_verdict_path}")
            except Exception as e:
                log(f"[narrative-check] 执行异常: {e}", "WARN")

    if stage:
        mode_tag = ""
        if anti_mode:
            mode_tag = " [无钢印自由反向]" if anti_free else f" [反模式:{recipe}]"
        print(f"\n✅ 管道就绪{mode_tag}。请将 output/{stage}_llm_prompt.txt 内容交给 LLM 生成对应阶段内容")
        if anti_mode:
            print(f"   生成完成后可用以下命令评估爽感指数:")
            print(f"   python tools/anti_pattern.py --ei output/{stage}_output.txt")
    else:
        print(f"\n✅ 管道就绪。请将 output/fusion_context.txt 内容交给 LLM 生成故事，保存到 output/story.txt")
        print(f"   然后运行后处理: python tools/clean_commas.py output/story.txt")
        print(f"   可选反朱雀校准: python run_pipeline.py --humanize")
        print(f"   可选 Bloom 反查(朱雀不可反查增强, 零模型):")
        print(f"     先建索引: python tools/bloom_guard.py --build --corpus corpus")
        print(f"     再审计:   python tools/audit.py output/story.txt --strict")
        print(f"   可选本地三交叉终判(默认关闭, 生成 story.txt 后):")
        print(f"      python run_pipeline.py --narrative-check")


# ============================================================
# 工具函数
# ============================================================

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    ISSUES.append(line)


def count_chinese(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def load_prompt_template(stage, template_keyword=None):
    """
    加载对应创作阶段的提示词模板，支持按关键词筛选模板内容。
    融合文件结构: <!-- FILE_SECTION: 源文件名 --> 标记各章节。
    :param stage: 创作阶段，对应STAGE_PROMPT_MAP的键
    :param template_keyword: 模板关键词，为空则加载文件第一个模板
    :return: 提示词模板内容字符串
    """
    prompt_path = STAGE_PROMPT_MAP.get(stage)
    if not prompt_path or not os.path.exists(prompt_path):
        log(f"提示词文件不存在：{prompt_path}", "ERROR")
        return None
    content = read_file_safe(prompt_path)

    # 检查是否为融合文件（含 FILE_SECTION 标记）
    section_name = STAGE_SECTION_MAP.get(stage)
    section_extracted = False
    if section_name and "<!-- FILE_SECTION:" in content:
        # 融合文件：按 FILE_SECTION 标签名直接匹配章节
        pattern = re.compile(
            r'<!-- FILE_SECTION:\s*' + re.escape(section_name) + r'\s*-->'
        )
        match = pattern.search(content)
        if match:
            # 提取从此标记到下一个 FILE_SECTION（或文件末尾）之间的内容
            rest = content[match.end():]
            next_section = re.search(r'<!-- FILE_SECTION:', rest)
            if next_section:
                content = rest[:next_section.start()].strip()
            else:
                content = rest.strip()
            section_extracted = True
        else:
            log(f"融合文件中未找到「{section_name}」章节，使用整个文件", "WARN")

    if not template_keyword:
        # 若已提取章节：跳过描述头（来源/统计行），返回第一个实际模板
        if section_extracted:
            # 找到第一个 --- 之后的内容（跳过章节描述头）
            first_sep = content.find("\n---\n")
            if first_sep >= 0:
                content = content[first_sep + 5:].strip()
        parts = content.split("---")
        if len(parts) > 1:
            return parts[0].strip()
        return content.strip()
    # 有关键词，筛选包含关键词的模板
    parts = content.split("---")
    for part in parts:
        if template_keyword in part:
            return part.strip()
    log(f"未找到关键词为「{template_keyword}」的模板，使用第一个模板", "WARN")
    return load_prompt_template(stage)


def input_user_params(stage):
    """交互式输入用户自定义参数"""
    params = {}
    print(f"\n=== {stage}阶段 - 用户参数输入（回车跳过=自动匹配热门内容）===")
    if stage == "脑洞":
        params["小说类型"] = input("  小说类型（如：古代言情/都市复仇/玄幻系统）：").strip()
        params["核心卖点"] = input("  核心卖点（如：重生复仇/金手指爽文/马甲大佬）：").strip()
        params["目标受众"] = input("  目标受众（如：女频/男频）：").strip()
    elif stage == "人设":
        params["主角人设"] = input("  主角人设（如：杀伐果断/清醒独立/黑莲花）：").strip()
        params["金手指类型"] = input("  金手指类型（如：系统/空间/预知）：").strip()
    elif stage in ("开篇", "正文"):
        params["开篇风格"] = input("  开篇风格（如：爽文直给/慢热铺垫/悬念切入）：").strip()
    params = {k: v for k, v in params.items() if v}
    return params


def build_full_prompt(stage, prompt_template, fusion_context, user_params,
                       previous_output=None, target_chars=None,
                       append_mode=False, round_no=None, methodology_context=None):
    """
    拼装完整LLM调用指令：
    提示词模板 + 目标字数（创作类阶段） + 语料指纹上下文 + 前序阶段输出（链式传递） + 用户自定义参数

    :param target_chars: 目标中文字数，仅在创作类阶段（开篇/正文/续写/扩写）注入提示词
    :param append_mode: 扩写追加模式（自动闭环专用）。为 True 且 stage=="扩写" 时，
        注入「仅追加、不重写、针对最短章接续」指令块，替换原目标字数块
    :param round_no: 自动扩写闭环轮次编号（append_mode 下用于提示文案）
    """
    parts = []
    # 全局创作约束（P2-5 修复: 单点维护，自动注入，避免各阶段模板重复）
    common_path = os.path.join(PROMPT_DIR, "COMMON.md")
    if os.path.exists(common_path):
        common = read_file_safe(common_path)
        if common.strip():
            parts.append("## 全局创作约束（系统自动注入）\n")
            parts.append(common.strip())
            parts.append("")
    # 提示词模板
    parts.append(prompt_template)
    parts.append("")
    # 目标字数（P-G1: 仅创作类阶段注入，优化/润色阶段不注入）
    if append_mode and stage == "扩写":
        parts.append("\n---\n## 扩写追加模式（自动闭环）\n")
        parts.append(
            f"这是自动扩写闭环的第 {round_no} 轮。请【仅追加】，不要重写或复述已有内容。\n"
            f"请针对全文中【最短章节】进行扩写，在其末尾【接续】新增约 {target_chars} 字（中文）。\n"
            f"要求：保持原有人设、节奏与对话风格；新增段落对话密度≥40%；不重复已有内容。\n"
            f"仅输出新增的段落文本，不要输出章节标题或任何说明。"
        )
        parts.append("")
    elif target_chars and stage in ("开篇", "正文", "续写", "扩写"):
        parts.append("\n---\n## 目标字数\n")
        parts.append(f"本篇目标成稿中文字数：{target_chars} 字。请确保篇幅充足，不得大幅低于目标。")
        parts.append("")
    # 前序阶段输出（链式传递上下文）
    if previous_output:
        parts.append("\n---\n## 前序阶段输出（请在此基础上继续创作）\n")
        orig_len = len(previous_output)
        parts.append(previous_output[:2000])  # 截断防超长
        if orig_len > 2000:
            log(f"前序输出截断: {orig_len} → 2000 字符 (丢弃 {orig_len - 2000} 字符)", "WARN")
        parts.append("")
    # 语料指纹（创作类阶段提供参考源文）
    if fusion_context and stage != "优化":
        parts.append("\n---\n## 参考语料指纹（仅风格参考，内容需原创）\n")
        orig_f_len = len(fusion_context)
        parts.append(fusion_context[:FUSION_CONTEXT_CAP])  # 截断防超长（v6.3: 20维表+双层互消更长，8000字覆盖75-89%信号）
        if orig_f_len > FUSION_CONTEXT_CAP:
            log(f"指纹上下文截断: {orig_f_len} → {FUSION_CONTEXT_CAP} 字符 (丢弃 {orig_f_len - FUSION_CONTEXT_CAP} 字符)", "WARN")
    # 写作方法学（approach A: 运行时自动织入）
    if methodology_context and methodology_context.strip():
        parts.append("\n---\n## 写作方法学（系统自动织入）\n")
        parts.append(methodology_context.strip())
        parts.append("")
    # 用户参数
    if user_params:
        parts.append("\n---\n## 用户自定义参数\n")
        for k, v in user_params.items():
            parts.append(f"- {k}: {v}")
    else:
        parts.append("\n---\n## 用户自定义参数\n- 所有参数留空，请自动匹配当前平台最热门的题材、卖点、人设\n")
    return "\n".join(parts)


def read_file_safe(path):
    """尝试 utf-8 → gbk → replace 三级读取"""
    for enc in ("utf-8", "gbk", "utf-8-sig"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def run_humanize():
    """对 output/story.txt 做反朱雀保守校准（机械过渡替换），备份原文件。"""
    story_path = os.path.join(OUTPUT_DIR, "story.txt")
    if not os.path.exists(story_path):
        log("[humanize] 未找到 output/story.txt，跳过", "WARN")
        return
    try:
        sys.path.insert(0, os.path.join(_here, "tools"))
        from human_feature_injector import apply_light_transitions
        t = read_file_safe(story_path)
        new_t, n = apply_light_transitions(t)
        if n:
            bak = story_path + ".bak"
            if not os.path.exists(bak):
                with open(bak, "w", encoding="utf-8") as f:
                    f.write(t)
            with open(story_path, "w", encoding="utf-8") as f:
                f.write(new_t)
            log(f"[humanize] 已保守替换 {n} 处机械过渡 → {story_path}（备份 {bak}）")
        else:
            log("[humanize] 未发现可替换的机械过渡", "INFO")
    except Exception as e:
        log(f"[humanize] 执行异常: {e}", "WARN")


def _run_postprocess_chain(story_path, excl_density=0.15, comma_density=1.2):
    """后处理链：clean_commas -> inject_punctuation -> check_padding。返回 dict 或 None。"""
    PREFIX = "[postprocess]"
    report = {}
    try:
        sys.path.insert(0, os.path.join(_here, "tools"))

        text = read_file_safe(story_path)
        original_text = text

        from clean_commas import clean_commas as _cc
        text = _cc(text)
        report["clean_commas_removed"] = len(original_text) - len(text)
        log(f"{PREFIX} clean_commas 完成")

        from inject_punctuation import inject_exclamation, inject_commas
        text = inject_exclamation(text, excl_density)
        text = inject_commas(text, comma_density)
        excl_after = text.count("！") - original_text.count("！")
        comma_after = text.count("，") - original_text.count("，")
        report["excl_injected"] = max(0, excl_after)
        report["comma_injected"] = max(0, comma_after)
        log(f"{PREFIX} inject_punctuation: !+{report['excl_injected']}, ，+{report['comma_injected']}")

        bak = story_path + ".postprocess.bak"
        if not os.path.exists(bak):
            with open(bak, "w", encoding="utf-8") as f:
                f.write(original_text)
        with open(story_path, "w", encoding="utf-8") as f:
            f.write(text)
        log(f"{PREFIX} 文本已写回（备份: {bak}）")

        from check_padding import check as _cp
        pad_result = _cp(text)
        report["padding_risk"] = pad_result.get("padding_risk", "unknown")
        report["padding_verdict"] = pad_result.get("verdict", "unknown")
        log(f"{PREFIX} check_padding: {report['padding_risk']} -> {report['padding_verdict']}")

        report_path = os.path.join(OUTPUT_DIR, "_postprocess_report.json")
        import json
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        log(f"{PREFIX} 报告: {report_path}")

        return report
    except Exception as e:
        log(f"{PREFIX} 异常: {e}（仅 WARN）", "WARN")
        return None


def _chinese_num_to_int(num_str):
    """将中文数字字符串转为整数，如「二十三」→ 23；也支持阿拉伯数字字符串。

    :param num_str: 中文数字或阿拉伯数字字符串
    :return: 对应的整数值
    """
    if num_str.isdigit():
        return int(num_str)
    digit_map = {
        "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }
    unit_map = {"十": 10, "百": 100, "千": 1000}
    result = 0
    current = 0
    for ch in num_str:
        if ch in digit_map:
            current = digit_map[ch]
        elif ch in unit_map:
            unit = unit_map[ch]
            if current == 0:
                current = 1
            result += current * unit
            current = 0
    result += current
    return result


def assemble_story(target_chars=None, genre=None, anti_mode=False):
    """拼装4个叙事阶段输出为成稿 story.txt，并做字数统计与一致性检查。

    读取 output/ 下的 开篇/正文/续写/扩写 _output.txt，
    防御性过滤衔接注行后拼接，统计中文字数与章节数，
    可选与目标字数对比（P-G4），并做章节连续性与单章字数下限检查（P-G5）。

    :param target_chars: 目标中文字数，为 None 时不做对比
    :param genre: 题材分类（透传给 check_story）
    :param anti_mode: 反模式标志（透传给 check_story）
    """
    narrative_stages = ["开篇", "正文", "续写", "扩写"]
    segments = []
    found = 0
    for sname in narrative_stages:
        fpath = os.path.join(OUTPUT_DIR, f"{sname}_output.txt")
        if not os.path.exists(fpath):
            log(f"[assemble] 未找到 {sname}_output.txt，跳过", "WARN")
            continue
        text = read_file_safe(fpath)
        if not text.strip():
            log(f"[assemble] {sname}_output.txt 为空，跳过", "WARN")
            continue
        # 防御性过滤衔接注行
        filtered_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if any(kw in stripped for kw in ("起见", "全文完", "待LLM填充")):
                log(f"[assemble] 过滤衔接注行: {stripped[:40]}", "WARN")
                continue
            filtered_lines.append(line)
        cleaned = "\n".join(filtered_lines).strip()
        if not cleaned:
            log(f"[assemble] {sname}_output.txt 过滤后为空，跳过", "WARN")
            continue
        segments.append(cleaned)
        found += 1
        log(f"[assemble] 加载 {sname}_output.txt ({count_chinese(cleaned)} 中文字)")

    if found == 0:
        log("[assemble] 未找到任何叙事阶段输出文件，无法拼装", "ERROR")
        return

    # 拼接，段落间用空行分隔
    story_text = "\n\n".join(segments)

    # 统计中文字数
    total_chars = count_chinese(story_text)

    # 统计章节数（第X章 独占一行）
    chapter_matches = CHAPTER_RE.findall(story_text)
    chapter_count = len(chapter_matches)

    log(f"[assemble] 拼装完成: {total_chars} 中文字 | {chapter_count} 章")

    # P-G4: 目标字数对比
    if target_chars is not None:
        gap = target_chars - total_chars
        if gap > 0:
            pct = round(gap / target_chars * 100, 1)
            log(
                f"[assemble] 目标 {target_chars} 字，实际 {total_chars} 字，"
                f"缺口 {gap} 字 ({pct}%)",
                "WARN",
            )
        else:
            log(f"[assemble] 目标 {target_chars} 字，实际 {total_chars} 字，达标")

    # P-G5: 一致性检查
    _check_assemble_consistency(story_text)

    # 写入 story.txt
    story_path = os.path.join(OUTPUT_DIR, "story.txt")
    with open(story_path, "w", encoding="utf-8") as f:
        f.write(story_text)
    log(f"[assemble] 成稿已保存: output/story.txt")

    # P-S6: 拼装后自动风格质检（默认开启，仅报告不中断；--qa-strict 可硬阻断）
    if _QA_CFG["enabled"]:
        ok = _post_assemble_qa(story_text)
        if _QA_CFG["strict"] and not ok:
            log("[post-assemble QA] --qa-strict 模式：质检未通过，终止管道", "ERROR")
            sys.exit(1)

    # P0: check_story 全量质检（默认开启；--no-check-story 可关闭）
    if not _QA_CFG.get("no_check_story", False):
        cs_exit = _run_check_story(story_path, genre=genre, anti_mode=anti_mode)
        if _QA_CFG.get("strict", False) and cs_exit != 0:
            log("[post-assemble QA] --qa-strict：check_story 未通过，终止", "ERROR")
            sys.exit(1)


def _style_scan(text: str) -> list[tuple[str, int]]:
    """扫描项目红线，返回 [(违规名, 次数), ...]；仅含次数>0 项，按次数降序。"""
    patterns = [
        ("破折号——", "——"),
        ("突转词", r"(?:忽然|猛地|瞬间)"),
        ("软副词", r"(?:轻轻|缓缓|微微|悄悄)"),
        ("西文引号", r"""["']"""),
    ]
    hits = []
    for name, pat in patterns:
        try:
            cnt = len(re.findall(pat, text))
        except re.error:
            cnt = 0
        if cnt > 0:
            hits.append((name, cnt))
    hits.sort(key=lambda x: x[1], reverse=True)
    return hits


def _post_assemble_qa(story_text: str) -> bool:
    """拼装后自动质检：固定规则审计 + 红线扫描 + 原创度信号（Bloom 非致命）。

    返回 ok(bool)：audit 通过 且 无红线命中。Bloom 命中不计入 ok（仅展示信号）。
    """
    PREFIX = "[post-assemble QA]"
    sys.path.insert(0, os.path.join(_here, "tools"))

    log(f"{PREFIX} ===== 拼装后风格质检 =====")

    # 1) 固定规则审计（分号 / ！！！/ ？！/ 禁用模板等）
    from audit import audit_story
    audit_result, audit_fail = audit_story(story_text)
    log(f"{PREFIX} [固定规则审计]")
    for line in audit_result.splitlines():
        log(f"{PREFIX}   {line}")

    # 2) 红线扫描
    redlines = _style_scan(story_text)
    log(f"{PREFIX} [红线扫描] " + (f"发现 {len(redlines)} 类需修正:" if redlines else "未发现需修正项 [OK]"))
    redline_fail = bool(redlines)
    for name, cnt in redlines:
        log(f"{PREFIX}   [FAIL] {name}: {cnt} 处", "WARN")

    # 3) 原创度信号（Bloom 非致命，仅展示）
    from bloom_guard import bloom_check
    bloom_lines, _bloom_fail = bloom_check(story_text, "data", strict=False)
    log(f"{PREFIX} [原创度信号 Bloom·非致命]")
    for line in bloom_lines.splitlines():
        log(f"{PREFIX}   {line}")

    ok = (not audit_fail) and (not redline_fail)
    if ok:
        log(f"{PREFIX} 结论: 拼装后质检全部通过 [OK]")
    else:
        reasons = []
        if audit_fail:
            reasons.append("固定规则未通过")
        if redline_fail:
            reasons.append(f"红线扫描 {len(redlines)} 类")
        log(f"{PREFIX} 结论: 存在需修正项（{'、'.join(reasons)}），请外部 LLM 修正后重跑 --assemble", "WARN")
    return ok


def _run_check_story(story_path: str, genre: str = None,
                    anti_mode: bool = False, ai_flavor: bool = True) -> int:
    """通过 subprocess 调用 check_story.py 执行 15 节全量质检。返回 exit_code。"""
    import subprocess
    check_script = os.path.join(_here, "check_story.py")
    argv = [sys.executable, check_script, story_path]
    if genre:
        argv.extend(["--genre", genre])
    if anti_mode:
        argv.append("--anti")
    if not ai_flavor:
        argv.append("--no-ai-flavor")

    PREFIX = "[check_story]"
    log(f"{PREFIX} ===== 15节全量质检 =====")
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                encoding='utf-8', timeout=300, cwd=_here)
        stdout_lines = result.stdout.splitlines()
        for line in stdout_lines[-30:]:
            log(f"{PREFIX}   {line}")
        if result.returncode != 0:
            log(f"{PREFIX} 质检发现问题（报告见 output/story_check_report.txt）", "WARN")
        else:
            log(f"{PREFIX} 全量质检通过 [OK]")
        return result.returncode
    except subprocess.TimeoutExpired:
        log(f"{PREFIX} 质检超时（>300s），跳过", "WARN")
        return -1
    except Exception as e:
        log(f"{PREFIX} 质检异常: {e}", "WARN")
        return -1


def _check_assemble_consistency(story_text):
    """拼装后一致性检查：章节连续性 + 单章字数下限（P-G5）。

    :param story_text: 拼装后的完整文本
    """
    matches = list(CHAPTER_RE.finditer(story_text))
    if not matches:
        log("[assemble] 未检测到章节标题，跳过一致性检查", "WARN")
        return

    # 提取章节编号
    chapter_nums = [_chinese_num_to_int(m.group(1)) for m in matches]

    # P-G5-1: 章节连续性
    for i in range(1, len(chapter_nums)):
        if chapter_nums[i] != chapter_nums[i - 1] + 1:
            expected = chapter_nums[i - 1] + 1
            log(
                f"[assemble] 章节不连续: 第{chapter_nums[i - 1]}章 → "
                f"第{chapter_nums[i]}章 (期望第{expected}章)",
                "WARN",
            )

    # P-G5-2: 单章字数下限
    min_chapter_chars = 200
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(story_text)
        chapter_content = story_text[start:end]
        chapter_chars = count_chinese(chapter_content)
        if chapter_chars < min_chapter_chars:
            log(
                f"[assemble] 第{chapter_nums[i]}章字数不足: "
                f"{chapter_chars} 字 < {min_chapter_chars} 字下限",
                "WARN",
            )


def _locate_shortest_chapter(story_text):
    """返回 (最短章节文本, 章号)；无章节则返回 (全文, None)。"""
    matches = list(CHAPTER_RE.finditer(story_text))
    if not matches:
        return story_text, None
    best, best_n, best_chars = None, None, float("inf")
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(story_text)
        seg = story_text[start:end]
        c = count_chinese(seg)
        if c < best_chars:
            best_chars, best, best_n = c, seg, _chinese_num_to_int(m.group(1))
    return best, best_n


def _expand_methodology_context(category, short_mode, budget=4000):
    """扩写闭环专用：以「扩写」阶段织入方法论；失败静默返回 ""。"""
    try:
        from tools.methodology_weaver import weave_methodology
        return weave_methodology("扩写", category, short_mode, budget=budget)
    except Exception as e:
        log(f"方法论织入失败(扩写),跳过: {e}", "WARN")
        return ""


def expand_loop(target_chars, max_rounds=MAX_EXPAND_ROUNDS, threshold=EXPAND_THRESHOLD,
                category=None, short_mode=False, methodology_budget=4000):
    """自动扩写闭环（零模型）：复用 fusion_context，定位最短章，分轮追加至达标或达上限。

    默认零模型：每轮生成一个 prompt 文件并提示用户交给外部 LLM，LLM 把新增段落追加到
    output/扩写_output.txt 后，用户重新运行 --expand-to N 进入下一轮。轮次由磁盘上
    扩写_round*_llm_prompt.txt 的数量自动推算，内置上限 max_rounds 强制终止。

    可选全自动：若 EXPAND_GEN_HOOK 被挂上 LLM 客户端，则每轮调用钩子取回文本并追加，
    实现进程内真正全自动闭环。

    :param target_chars: 目标成稿中文字数（达标基准）
    :param max_rounds: 闭环硬上限轮次
    :param threshold: 达标阈值（成稿 ≥ N × threshold 即达标）
    :return: True=达标结束；False=达上限未达标；None=已生成本轮 prompt，等待外部 LLM（需重跑）
    """
    # 1) 复用磁盘 fusion_context（不重扫 corpus，杜绝 corpus 重扫）
    fc_path = os.path.join(OUTPUT_DIR, "fusion_context.txt")
    if os.path.exists(fc_path):
        fusion_context = read_file_safe(fc_path)
    else:
        fusion_context = ""
        log("[expand] 未找到 output/fusion_context.txt，将不使用语料指纹（仍可扩写）", "WARN")

    # 2) 加载扩写模板一次
    expand_tpl = load_prompt_template("扩写")
    if not expand_tpl:
        log("[expand] 扩写模板加载失败", "ERROR")
        return False

    # 3) 前置校验：4 个叙事阶段至少存在其一
    narrative_outputs = [f"{s}_output.txt" for s in ("开篇", "正文", "续写", "扩写")]
    if not any(os.path.exists(os.path.join(OUTPUT_DIR, f)) for f in narrative_outputs):
        log("[expand] 未找到任何叙事阶段输出，请先生成 开篇/正文/续写/扩写", "ERROR")
        return False

    while True:
        # 重建 story.txt 并统计
        assemble_story()
        story_path = os.path.join(OUTPUT_DIR, "story.txt")
        story = read_file_safe(story_path) if os.path.exists(story_path) else ""
        cur = count_chinese(story)

        # 达标判定
        if cur >= target_chars * threshold:
            log(f"[expand] 达标: 当前 {cur} 字 ≥ 目标 {target_chars} 字 × {threshold}")
            return True

        # 轮次推算（基于磁盘 prompt 文件数，无需状态文件）
        round_files = glob.glob(os.path.join(OUTPUT_DIR, "扩写_round*_llm_prompt.txt"))
        if len(round_files) >= max_rounds:
            gap = target_chars - cur
            pct = round(gap / target_chars * 100, 1) if target_chars else 0.0
            log(
                f"[expand] 已达上限 {max_rounds} 轮，仍未达标：当前 {cur} 字 / 目标 {target_chars} 字，"
                f"缺口 {gap} 字（{pct}%）— 请检查外部 LLM 输出是否成功追加到 output/扩写_output.txt",
                "WARN",
            )
            return False

        round_no = len(round_files) + 1
        gap = target_chars - cur
        budget = min(gap, PER_ROUND_CAP)

        # 缺口过小则跳过收尾
        if budget < MIN_EXPAND_BUDGET:
            log(f"[expand] 剩余缺口 {gap} 字过小，跳过本轮")
            return False

        # 定位最短章节，取其尾部 2000 字作为 previous_output（自然续写）
        chap_text, chap_num = _locate_shortest_chapter(story)
        prev = chap_text[-2000:] if chap_text else story[-2000:]

        full_prompt = build_full_prompt(
            "扩写", expand_tpl, fusion_context, {}, prev, budget,
            append_mode=True, round_no=round_no,
            methodology_context=_expand_methodology_context(category, short_mode,
                budget=methodology_budget),
        )
        prompt_out = os.path.join(OUTPUT_DIR, f"扩写_round{round_no}_llm_prompt.txt")
        with open(prompt_out, "w", encoding="utf-8") as f:
            f.write(full_prompt)
        log(f"[expand] 第 {round_no} 轮: 最短第{chap_num}章，预算 {budget} 字 → {prompt_out}")

        # 可选：进程内全自动（注入 LLM 钩子）
        if EXPAND_GEN_HOOK is not None:
            out = EXPAND_GEN_HOOK(full_prompt)
            with open(os.path.join(OUTPUT_DIR, "扩写_output.txt"), "a", encoding="utf-8") as f:
                f.write("\n\n" + out)
            continue  # 继续下一轮

        # 默认：外部 LLM，等待用户重跑 --expand-to N
        log(
            f"[expand] 请将该 prompt 交给 LLM，把【新增段落】追加写入 output/扩写_output.txt，"
            f"然后重新运行: python run_pipeline.py --expand-to {target_chars}",
            "INFO",
        )
        return None


def is_healthy(path):
    """返回 (ok, 中文字数) — 中文字数 < MIN_CHINESE 视为损坏"""
    text = read_file_safe(path)
    n = count_chinese(text)
    return n >= MIN_CHINESE, n


def _read_file_safe_for_check(path):
    """检查文件内容是否为空或占位符（安全读取，不抛异常）"""
    try:
        text = read_file_safe(path)
        return text.strip() in ("", "【待LLM填充】")
    except Exception as e:
        import logging
        logging.warning(f"_read_file_safe_for_check failed: {e}")
        return True


def collect_corpus(corpus_dir, category=None):
    """
    扫描 corpus 目录，返回 [(path, category_tag), ...]。
    支持平铺 (corpus/*.txt) 和分类子目录 (corpus/分类/*.txt)。
    若指定 category，只返回该分类的文件。
    """
    results = []
    if not os.path.isdir(corpus_dir):
        return results

    entries = os.listdir(corpus_dir)

    # 判断是否有子目录
    subdirs = [e for e in entries if os.path.isdir(os.path.join(corpus_dir, e))]
    flat_txts = [e for e in entries if e.endswith(".txt")]

    if subdirs:
        # 子目录模式
        targets = subdirs if not category else [d for d in subdirs if d == category]
        for d in targets:
            dpath = os.path.join(corpus_dir, d)
            for fname in os.listdir(dpath):
                if fname.endswith(".txt"):
                    results.append((os.path.join(dpath, fname), d))
    else:
        # 平铺模式
        for fname in flat_txts:
            results.append((os.path.join(corpus_dir, fname), "corpus"))

    return results


def pick_healthy(candidates, n, category=None):
    """
    从候选列表中随机选 n 篇健康文件。
    损坏文件自动剔除并记录，若剩余不足 n 篇则取全部健康文件。
    """
    if category:
        pool = [(p, c) for p, c in candidates if c == category]
    else:
        pool = list(candidates)

    random.shuffle(pool)
    healthy = []
    damaged = []

    for path, cat in pool:
        ok, zh_count = is_healthy(path)
        if ok:
            healthy.append(path)
        else:
            damaged.append((path, zh_count))
            log(f"[SKIP] 损坏文件（仅{zh_count}字中文）: {os.path.basename(path)}", "WARN")

    if damaged:
        log(f"共跳过 {len(damaged)} 篇损坏文件，建议移出 corpus/", "WARN")

    if len(healthy) < n:
        log(f"健康文件仅 {len(healthy)} 篇，不足 {n} 篇，取全部", "WARN")
        return healthy
    return random.sample(healthy, n)


# ============================================================
# 解析命令行参数（argparse 标准化）
# ============================================================
def parse_args(args=None):
    """使用标准 argparse 解析命令行参数，保留所有现有参数的行为和默认值。

    :param args: 可选参数列表，为 None 时自动读取 sys.argv[1:]。
                 允许 console_scripts 入口传入自定义参数列表。
    """
    import argparse

    ap = argparse.ArgumentParser(
        description="run_pipeline.py — 全自动熔铸管道 v6.3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python run_pipeline.py -s 正文 -c 05_古代言情
  python run_pipeline.py -s 正文 -c 05_古代言情 --with capture,analyze,cover
  python run_pipeline.py --capture --capture-platform fanqie --capture-channel 1 --capture-type 2
  python run_pipeline.py --analyze --analyze-input 某书.txt --analyze-book 某书
  GPT_IMAGE_API_KEY=xxx python run_pipeline.py -s 正文 --cover --cover-prompt "..."
  python run_pipeline.py --browser --browser-action launch --browser-detect-only""",
    )

    # ── 创作生成（12 阶段熔铸管道）
    ap.add_argument("-c", "--category", default=None, help="指定 corpus 子分类")
    ap.add_argument("-n", "--sample", type=int, default=5, help="采样源文篇数（默认 5）")
    ap.add_argument("-s", "--stage", default=None, help="单阶段模式（脑洞/人设/大纲/开篇/正文/优化/润色/续写/扩写）")
    ap.add_argument("-t", "--template", default=None, help="模板关键词筛选")
    ap.add_argument("-p", "--params", default="{}", help="用户自定义参数（JSON 格式）")
    ap.add_argument("-P", "--previous-output", default=None, help="前序阶段输出文件路径")
    ap.add_argument("--interactive", action="store_true", help="交互式参数输入")
    ap.add_argument("--anti", action="store_true", help="反模式生成")
    ap.add_argument("--anti-free", action="store_true", help="无钢印反模式（不预设维度，纯自由反向）")
    ap.add_argument("--recipe", default=None, help="反模式配方（如：中度反模式/重度反模式/极限反模式）")
    ap.add_argument("--humanize", action="store_true", help="反朱雀保守校准（仅后处理 output/story.txt）")
    ap.add_argument("--assemble", action="store_true", help="拼装叙事阶段为成稿 story.txt")
    ap.add_argument("--target-chars", type=int, default=None, help="目标中文字数")
    ap.add_argument("--expand-to", type=int, default=None, help="自动扩写闭环至 N 字")
    ap.add_argument("--narrative-check", action="store_true", help="本地三交叉终判")
    ap.add_argument("--no-methodology", action="store_true", help="关闭方法论自动织入（approach A，默认开启）")
    ap.add_argument("--short-mode", action="store_true", help="启用短篇专属方法论（额外织入 prompt/methodology/short/）")
    ap.add_argument("--methodology-budget", type=int, default=4000, help="方法论织入字符上限（默认4000）")
    ap.add_argument("--auto", action="store_true", help="全自动12阶段串联")

    # ── 互消层升级（v6.3+）
    ap.add_argument("--rebuild-dna", action="store_true", help="强制重建叙事 DNA 演化表")
    ap.add_argument("--dna-scope", default="category", help="演化数据源: category(默认) / all")
    ap.add_argument("--enhanced-fingerprint", action="store_true", help="开启增强指纹（默认关）")
    ap.add_argument("--ef-ngram", action="store_true", help="增强指纹子开关：ngram 向量")
    ap.add_argument("--ef-plot", action="store_true", help="增强指纹子开关：情节单元标签")
    ap.add_argument("--ef-syntax", action="store_true", help="增强指纹子开关：句法画像")

    # ── 模块集成（v6.3+）
    ap.add_argument("--rag", action="store_true", help="开启 RAG 约束检索（默认关闭）")
    ap.add_argument("--rag-tags", default=None, help="RAG 检索标签")
    ap.add_argument("--rag-top-k", type=int, default=5, help="RAG 召回源文数（默认 5）")
    ap.add_argument("--postprocess", action="store_true", help="开启后处理链（默认关闭）")
    ap.add_argument("--postprocess-excl", type=float, default=0.15, help="感叹号注入密度（默认 0.15）")
    ap.add_argument("--postprocess-comma", type=float, default=1.2, help="逗号注入密度（默认 1.2）")
    ap.add_argument("--no-check-story", action="store_true", help="关闭 assemble 后的 check_story 全量质检")

    # ── QA 控制
    ap.add_argument("--no-qa", action="store_true", help="跳过 QA 报告块")
    ap.add_argument("--qa-strict", action="store_true", help="QA 未过则退出码 1（CI 硬阻断）")

    # ── 统一流四步骤
    ap.add_argument("--capture", action="store_true", help="[前置] 网文市场扫榜采集 → 注入 脑洞")
    ap.add_argument("--analyze", action="store_true", help="[前置] 网文逆向拆书 → 注入 人设/大纲")
    ap.add_argument("--cover", action="store_true", help="[后置] 封面生成（需 GPT_IMAGE_API_KEY）")
    ap.add_argument("--browser", action="store_true", help="[旁路] Chrome CDP 巡检")
    ap.add_argument("--with", default="", dest="with_csv",
                    help="聚合开启上述步骤，如 --with capture,analyze,cover,browser")

    # 前置/后置透传
    ap.add_argument("--capture-platform", default="qidian", help="网文平台（默认 qidian）")
    ap.add_argument("--capture-type", default=None, help="榜单类型")
    ap.add_argument("--capture-channel", default=None, help="频道")
    ap.add_argument("--capture-top", type=int, default=None, help="榜单 top-N")
    ap.add_argument("--capture-outdir", default=None, help="扫榜输出目录（默认 <root>/scan_output）")
    ap.add_argument("--analyze-input", default=None, help="拆书输入（本地 txt/目录）")
    ap.add_argument("--analyze-book", default=None, help="拆书书名")
    ap.add_argument("--analyze-length", default=None, help="拆书长度限制")
    ap.add_argument("--analyze-force", action="store_true", help="强制重新拆书")
    ap.add_argument("--cover-book", default=None, help="封面书名")
    ap.add_argument("--cover-prompt", default=None, help="封面生成提示词")
    ap.add_argument("--cover-api-key", default=None, help="封面 API Key")
    ap.add_argument("--cover-size", default=None, help="封面尺寸")
    ap.add_argument("--browser-action", default="launch", help="浏览器动作（默认 launch）")
    ap.add_argument("--browser-port", type=int, default=9222, help="CDP 端口（默认 9222）")
    ap.add_argument("--browser-detect-only", action="store_true", help="仅检测浏览器")
    ap.add_argument("--rebuild-all-caches", action="store_true",
                    help="替换语料后一键重建全部缓存（Bloom/画像/叙事/质量/DNA）")

    parsed = ap.parse_args(args)

    # 构建与旧 parse_args() 同构的 dict 返回结构
    opts = {
        "category": parsed.category,
        "sample": parsed.sample,
        "stage": parsed.stage,
        "template": parsed.template,
        "params": {},
        "interactive": parsed.interactive,
        "previous_output": parsed.previous_output,
        "anti": parsed.anti,
        "anti_free": parsed.anti_free,
        "recipe": parsed.recipe,
        "humanize": parsed.humanize,
        "narrative_check": parsed.narrative_check,
        "assemble": parsed.assemble,
        "target_chars": parsed.target_chars,
        "expand_to": parsed.expand_to,
        "no_qa": parsed.no_qa,
        "qa_strict": parsed.qa_strict,
        "no_methodology": parsed.no_methodology,
        "short_mode": parsed.short_mode,
        "auto": parsed.auto,
        "methodology_budget": parsed.methodology_budget,
        # ── 统一流四步骤
        "capture": parsed.capture,
        "analyze": parsed.analyze,
        "cover": parsed.cover,
        "browser": parsed.browser,
        "with": parsed.with_csv,
        "capture_platform": parsed.capture_platform,
        "capture_type": parsed.capture_type,
        "capture_channel": parsed.capture_channel,
        "capture_top": parsed.capture_top,
        "capture_outdir": parsed.capture_outdir,
        "analyze_input": parsed.analyze_input,
        "analyze_book": parsed.analyze_book,
        "analyze_length": parsed.analyze_length,
        "analyze_force": parsed.analyze_force,
        "cover_book": parsed.cover_book,
        "cover_prompt": parsed.cover_prompt,
        "cover_api_key": parsed.cover_api_key,
        "cover_size": parsed.cover_size,
        "browser_action": parsed.browser_action,
        "browser_port": parsed.browser_port,
        "browser_detect_only": parsed.browser_detect_only,
        # ── 互消层升级
        "rebuild_dna": parsed.rebuild_dna,
        "dna_scope": parsed.dna_scope,
        "enhanced_fingerprint": parsed.enhanced_fingerprint,
        "ef_ngram": parsed.ef_ngram,
        "ef_plot": parsed.ef_plot,
        "ef_syntax": parsed.ef_syntax,
        # ── 模块集成
        "rag": parsed.rag,
        "rag_tags": parsed.rag_tags,
        "rag_top_k": parsed.rag_top_k,
        "postprocess": parsed.postprocess,
        "postprocess_excl": parsed.postprocess_excl,
        "postprocess_comma": parsed.postprocess_comma,
        "no_check_story": parsed.no_check_story,
        "rebuild_all_caches": parsed.rebuild_all_caches,
    }

    # 解析 JSON params（兼容旧的 --params 行为）
    if parsed.params and parsed.params != "{}":
        try:
            opts["params"] = json.loads(parsed.params)
        except json.JSONDecodeError:
            log(f"参数格式错误: {parsed.params}，应为JSON格式", "WARN")

    return opts


# ============================================================
# 全量缓存一键重建
# ============================================================
def _rebuild_all_caches():
    """重建全部语料缓存。依次调用 bloom/human/narrative/quality/dna 构建器。"""
    import subprocess
    import sys as _sys
    import os as _os

    _here = _os.path.dirname(_os.path.abspath(__file__))
    python = _sys.executable
    results = {}

    steps = [
        ("Bloom反查索引", [
            python, _os.path.join(_here, "tools", "bloom_guard.py"),
            "--build", "--corpus", _os.path.join(_here, "corpus"),
            "--cache", _os.path.join(_here, "data"),
        ]),
        ("人类写作画像", [
            python, "-c", f"""
import sys; sys.path.insert(0, {repr(_here)})
from tools.human_profile import build_corpus_profile
import json, os
prof = build_corpus_profile(os.path.join({repr(_here)}, 'corpus'))
out = os.path.join({repr(_here)}, 'data', '_human_profile.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(prof, f, ensure_ascii=False, indent=2)
print(f"人类画像已写出 -> {{out}}（{{prof.get('files', 0)}} 篇）")
""",
        ]),
        ("叙事特征基线", [
            python, _os.path.join(_here, "tools", "narrative_features.py"),
            "--build-baseline",
            "--corpus", _os.path.join(_here, "corpus"),
            "--cache", _os.path.join(_here, "data"),
            "--features-out", _os.path.join(_here, "data", "_narrative_features.jsonl"),
            "--out", _os.path.join(_here, "data", "_narrative_baseline.json"),
        ]),
        ("质量基线", [
            python, _os.path.join(_here, "tools", "build_quality_baseline.py"),
            "--out", _os.path.join(_here, "data", "_quality_baseline.json"),
        ]),
        ("叙事DNA演化表", [
            python, "-c", f"""
import sys; sys.path.insert(0, {repr(_here)})
from tools.dna_distiller import load_or_build_dna
import os
# 先重建 all 范围，确保全量DNA基线
dna = load_or_build_dna(None, 'all', force=True, dna_path=os.path.join({repr(_here)}, 'data', '_narrative_dna.json'))
print(f"DNA演化表已重建 -> 维度数: {{len(dna)}}")
""",
        ]),
    ]

    for name, cmd in steps:
        print(f"\n{'='*60}")
        print(f"[重建] {name} ...")
        print(f"{'='*60}")
        try:
            result = subprocess.run(cmd, cwd=_here, capture_output=False, timeout=3600)
            ok = (result.returncode == 0)
            results[name] = "PASS" if ok else f"FAIL (exit={result.returncode})"
            if ok:
                print(f"[OK] {name} 完成")
            else:
                print(f"[FAIL] {name} 退出码={result.returncode}")
        except subprocess.TimeoutExpired:
            results[name] = "FAIL (timeout)"
            print(f"[FAIL] {name} 超时")
        except Exception as e:
            results[name] = f"FAIL ({e})"
            print(f"[FAIL] {name}: {e}")

    print(f"\n{'='*60}")
    print("[重建汇总]")
    for name, status in results.items():
        print(f"  {name:20s} {status}")

    all_ok = all(v == "PASS" for v in results.values())
    return all_ok


# ============================================================
# 主流程
# ============================================================
def main(args=None):
    """统一流入口：解析参数后交给 run_unified_workflow 编排（取代旧 dispatch_mode 平行分派）。

    run_unified_workflow 返回 int 退出码（通常 0）；任意可选步骤失败不阻断主干，
    仅 12 阶段 generate 主干自身异常才会非零退出。

    :param args: 可选参数列表，为 None 时自动读取 sys.argv[1:]。
                 允许 console_scripts 入口（如 pyproject.toml 的 [project.scripts]）调用。
    """
    opts = parse_args(args)
    if opts.get("rebuild_all_caches"):
        ok = _rebuild_all_caches()
        sys.exit(0 if ok else 1)
    rc = run_unified_workflow(opts)
    if isinstance(rc, int):
        sys.exit(rc)


if __name__ == "__main__":
    main()
