# -*- coding: utf-8 -*-
"""
run_pipeline.py — 全自动熔铸管道

用法:
    .venv/Scripts/python run_pipeline.py
    .venv/Scripts/python run_pipeline.py --category 01_现代言情
    .venv/Scripts/python run_pipeline.py --category 05_古代言情
    .venv/Scripts/python run_pipeline.py --sample 5
    .venv/Scripts/python run_pipeline.py --stage 脑洞          ← 分阶段模式
    .venv/Scripts/python run_pipeline.py -s 开篇 -c 05_古代言情 --template 西瓜大法
    .venv/Scripts/python run_pipeline.py -s 正文 -P output/开篇_output.txt  ← 链式传递

corpus 结构（两种都支持，9个分类任选）:
    corpus/小说.txt                    ← 平铺
    corpus/01_现代言情/小说.txt         ← 分类子目录
    corpus/05_古代言情/小说.txt
"""
import sys, os, random, re, time, json
from datetime import datetime

# ── 编码强制 UTF-8（解决 Windows cmd/bash 乱码）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── 优先使用本项目 venv
_here = os.path.dirname(os.path.abspath(__file__))
_venv_site = os.path.join(_here, ".venv", "Lib", "site-packages")
if os.path.isdir(_venv_site) and _venv_site not in sys.path:
    sys.path.insert(0, _venv_site)

ISSUES = []
OUTPUT_DIR = os.path.join(_here, "output")
CORPUS_DIR = os.path.join(_here, "corpus")
PROMPT_DIR = os.path.join(_here, "prompt")
MIN_CHINESE = 500   # 低于此中文字数视为损坏文件，跳过

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


def build_full_prompt(stage, prompt_template, fusion_context, user_params, previous_output=None):
    """
    拼装完整LLM调用指令：
    提示词模板 + 语料指纹上下文 + 前序阶段输出（链式传递） + 用户自定义参数
    """
    parts = []
    # 角色指令
    parts.append("你是资深网文主编，深谙番茄小说平台规则与读者心理。\n")
    # 提示词模板
    parts.append(prompt_template)
    parts.append("")
    # 前序阶段输出（链式传递上下文）
    if previous_output:
        parts.append("\n---\n## 前序阶段输出（请在此基础上继续创作）\n")
        parts.append(previous_output[:2000])  # 截断防超长
        parts.append("")
    # 语料指纹（创作类阶段提供参考源文）
    if fusion_context and stage != "优化":
        parts.append("\n---\n## 参考语料指纹（仅风格参考，内容需原创）\n")
        parts.append(fusion_context[:3000])  # 截断防超长
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


def is_healthy(path):
    """返回 (ok, 中文字数) — 中文字数 < MIN_CHINESE 视为损坏"""
    text = read_file_safe(path)
    n = count_chinese(text)
    return n >= MIN_CHINESE, n


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
# 解析命令行参数
# ============================================================
def parse_args():
    args = sys.argv[1:]
    opts = {
        "category": None,
        "sample": 5,
        "stage": None,
        "template": None,
        "params": {},
        "interactive": "--interactive" in sys.argv,
        "previous_output": None,
    }
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--category", "-c") and i + 1 < len(args):
            opts["category"] = args[i + 1]; i += 2
        elif a in ("--sample", "-n") and i + 1 < len(args):
            opts["sample"] = int(args[i + 1]); i += 2
        elif a in ("--stage", "-s") and i + 1 < len(args):
            opts["stage"] = args[i + 1]; i += 2
        elif a in ("--template", "-t") and i + 1 < len(args):
            opts["template"] = args[i + 1]; i += 2
        elif a in ("--params", "-p") and i + 1 < len(args):
            try:
                opts["params"] = json.loads(args[i + 1])
            except json.JSONDecodeError:
                log(f"参数格式错误: {args[i+1]}，应为JSON格式", "WARN")
            i += 2
        elif a in ("--previous-output", "-P") and i + 1 < len(args):
            opts["previous_output"] = args[i + 1]; i += 2
        else:
            i += 1
    return opts


# ============================================================
# 主流程
# ============================================================
def main():
    opts = parse_args()
    category = opts["category"]
    sample_n = opts["sample"]
    stage = opts["stage"]
    template = opts["template"]
    user_params = opts["params"]
    is_interactive = opts["interactive"]
    previous_output_path = opts["previous_output"]

    log("=== 熔铸管道启动 ===")
    log(f"工作目录: {_here}")
    if stage:
        log(f"创作阶段: {stage}")

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
        log("jieba 未安装 → 请运行: .venv/Scripts/pip install jieba", "ERROR")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Step 1: 扫描 corpus + 选源文（优化阶段不需要）
    fusion_context = ""
    if stage != "优化":
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

        # ── Step 2: 蒸馏指纹
        log("\n--- Step 2: 蒸馏指纹 ---")
        sys.path.insert(0, _here)
        import tools.fusion as fusion_mod

        files_info = []
        for fp in picked:
            text = read_file_safe(fp)
            fingerprint = fusion_mod.extract_fingerprint(text)
            files_info.append({"name": os.path.basename(fp), "fp": fingerprint})

        prompt = fusion_mod.build_llm_prompt(files_info, include_rules=False)
        fusion_context = prompt

        fusion_out = os.path.join(OUTPUT_DIR, "fusion_context.txt")
        with open(fusion_out, "w", encoding="utf-8") as f:
            f.write(fusion_context)
        log(f"指纹蒸馏完成 -> fusion_context.txt ({len(fusion_context)} 字符)")

    # ── Step 3: 加载提示词 + 拼装指令
    if stage and stage in STAGE_PROMPT_MAP:
        log(f"\n--- Step 3: 加载提示词模板 [{stage}] ---")
        prompt_template = load_prompt_template(stage, template)
        if not prompt_template:
            log("提示词加载失败", "ERROR")
            sys.exit(1)
        log(f"提示词模板加载成功 ({len(prompt_template)} 字符)")

        # 交互式参数输入
        if is_interactive:
            user_params = {**user_params, **input_user_params(stage)}

        # 拼装完整指令
        full_prompt = build_full_prompt(stage, prompt_template, fusion_context, user_params, previous_output)
        prompt_out = os.path.join(OUTPUT_DIR, f"{stage}_llm_prompt.txt")
        with open(prompt_out, "w", encoding="utf-8") as f:
            f.write(full_prompt)
        log(f"完整LLM调用指令已保存: {stage}_llm_prompt.txt ({len(full_prompt)} 字符)")
    else:
        # 无stage → 原始模式
        if not stage:
            log("\n--- Step 3: LLM生成短篇（原始模式） ---")
        fusion_out = os.path.join(OUTPUT_DIR, "fusion_context.txt")
        if os.path.exists(fusion_out):
            log(f"读取 {fusion_out} → 生成 → 写入 output/story.txt")
        story_out = os.path.join(OUTPUT_DIR, "story.txt")
        if not os.path.exists(story_out) or open(story_out, encoding="utf-8").read().strip() in ("", "【待LLM填充】"):
            with open(story_out, "w", encoding="utf-8") as f:
                f.write("【待LLM填充】\n")

    # ── 写入运行日志
    issues_out = os.path.join(OUTPUT_DIR, "pipeline_issues.txt")
    with open(issues_out, "w", encoding="utf-8") as f:
        f.write("熔铸管道运行记录\n")
        f.write("=" * 50 + "\n")
        f.write(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        if stage:
            f.write(f"创作阶段: {stage}\n")
        f.write("\n")
        for line in ISSUES:
            f.write(line + "\n")
        f.write("\n--- 以下为生成阶段后补 ---\n")
    log(f"运行日志已保存: output/pipeline_issues.txt")

    if stage:
        print(f"\n✅ 管道就绪。请将 output/{stage}_llm_prompt.txt 内容交给 LLM 生成对应阶段内容")
    else:
        print(f"\n✅ 管道就绪。请将 output/fusion_context.txt 内容交给 LLM 生成故事，保存到 output/story.txt")
        print(f"   然后运行后处理: .venv/Scripts/python tools/clean_commas.py output/story.txt")


if __name__ == "__main__":
    main()
