# -*- coding: utf-8 -*-
"""
fusion.py — 熔铸核心: 5源文→指纹并排→20维叙事DNA提取→交集分析→输出LLM可用的上下文

用法:
    python fusion.py --category 05_古代言情 --sample 5 -o output/fusion_context.txt
    python fusion.py file1.txt file2.txt file3.txt file4.txt file5.txt -o output/fusion_context.txt

输出 output/fusion_context.txt 包含:
    - 5篇各自的指纹摘要
    - 20维叙事DNA(死亡方式/重生触发/背景设定/背叛者/复仇手段/独特道具/主角身份/核心冲突/情感基调/金手指/反派动机/救赎弧/关键转折/场景母题/人设标签/开篇钩子/结局取向/象征意象/叙事视角/节奏型)的对比表
    - 每个维度从5篇中提取的实际特征值和公约数交集结果
    - LLM生成指令(带动态阈值: ≥60%源文共有→公约数整体反转/自创)

依赖: pip install jieba

v6.3+: 支持 corpus 自动蒸馏演化 DNA（tools/dna_distiller.py）与增强指纹
        （extract_fingerprint 默认关，新增字段仅内部/诊断，绝不注入生成指令）。
"""

import sys, os, re, json, random, itertools
import warnings
warnings.filterwarnings("ignore", message=".*pkg_resources.*")
import jieba
from collections import Counter

# 反向优化层支持：导入人类画像（风格对齐用）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from human_profile import load_or_build as _load_human_profile
    _HUMAN_OK = True
except (ImportError, ModuleNotFoundError):
    _HUMAN_OK = False

# v6.3+ DNA 演化蒸馏（可选，缺失不阻断流水线）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dna_distiller import load_or_build_dna
    _DNA_OK = True
except (ImportError, ModuleNotFoundError):
    _DNA_OK = False

# v6.3+ 第二层互消：维度组合钢印按「组合强度」排序输出的 top-N 上限
COMBO_TOP_N = 10


def read_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def count_chinese(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def first_n_lines(text, n=50):
    lines = text.split("\n")
    result = []
    count = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("=") or "试读" in line or "版权所有" in line:
            continue
        result.append(line)
        count += 1
        if count >= n:
            break
    return "\n".join(result)


def _build_ngram_vec(text, top_n=30):
    """滑窗切中文 n-gram（n=2/3/4），返回按总频次降序的 top_n 向量 {ngram: freq}。

    纯统计，仅内部/诊断使用，**绝不**注入 build_llm_prompt 输出。
    """
    chunks = re.findall(r"[\u4e00-\u9fff]+", text)
    counter = Counter()
    for chunk in chunks:
        L = len(chunk)
        for ng in (2, 3, 4):
            if L < ng:
                continue
            for i in range(L - ng + 1):
                counter[chunk[i:i + ng]] += 1
    return dict(counter.most_common(top_n))


# 情节单元通用信号词（仅类型标记，非 corpus 字面）
_PLOT_TURN = ["但是", "然而", "却", "突然", "忽然", "就在这时", "没想到", "不料", "岂料", "转折"]
_PLOT_REVEAL = ["原来", "真相", "发现", "才知道", "竟", "竟然", "其实", "揭穿", "真相大白"]
_PLOT_CLIMAX = ["终于", "最后", "结局", "落幕", "大婚", "身死", "复仇成功", "收束", "尘埃落定"]


def _build_plot_units(text, max_units=30):
    """按通用信号词切分事件序列，输出情节单元「标签」列表（纯规则，非 corpus 字面）。

    标签为通用类型（铺陈/转折/揭示/收束），不回传任何原文片段；仅内部/诊断使用。
    """
    sents = [s.strip() for s in re.split(r"[。！？\n]", text) if re.search(r"[\u4e00-\u9fff]", s)]
    units = []
    for s in sents:
        if not s:
            continue
        label = "铺陈"
        if any(k in s for k in _PLOT_TURN):
            label = "转折"
        elif any(k in s for k in _PLOT_REVEAL):
            label = "揭示"
        elif any(k in s for k in _PLOT_CLIMAX):
            label = "收束"
        units.append(label)
        if len(units) >= max_units:
            break
    return units


def _build_syntax_profile(sentences, text):
    """句法画像：句长分布（avg/min/max/分布桶）+ 标点节奏（纯统计，仅内部/诊断）。"""
    lengths = [len(re.findall(r"[\u4e00-\u9fff]", s)) for s in sentences]
    if lengths:
        avg = round(sum(lengths) / len(lengths), 2)
        mn = min(lengths)
        mx = max(lengths)
        buckets = {
            "short_le10": sum(1 for x in lengths if x <= 10),
            "mid_11_30": sum(1 for x in lengths if 11 <= x <= 30),
            "long_gt30": sum(1 for x in lengths if x > 30),
        }
    else:
        avg, mn, mx = 0, 0, 0
        buckets = {"short_le10": 0, "mid_11_30": 0, "long_gt30": 0}
    punct = {
        "excl": text.count("！"),
        "comma": text.count("，"),
        "quest": text.count("？"),
        "colon": text.count("："),
        "quote": text.count("「") + text.count("」") + text.count("“") + text.count("”"),
    }
    return {
        "avg_sent_len": avg,
        "min_sent_len": mn,
        "max_sent_len": mx,
        "sent_count": len(lengths),
        "buckets": buckets,
        "punct_rhythm": punct,
    }


def extract_fingerprint(text, enhanced=False, enhanced_opts=None):
    """从源文提取结构化指纹

    :param enhanced: 是否追加增强指纹字段（默认 False，与旧行为 100% 一致）。
    :param enhanced_opts: dict，key ∈ {ngram, plot, syntax}，默认都 True；
        仅当 enhanced=True 且有对应子开关为真时才追加对应字段。
        新增字段（ngram_vec / plot_units / syntax_profile）仅作内部/诊断，
        **绝不**传给 build_llm_prompt 输出（守住朱雀不可反查目标红线）。
    """
    first = first_n_lines(text, 50)
    zh = count_chinese(text)
    sentences = [s.strip() for s in re.split(r"[。！？]", text) if re.search(r"[\u4e00-\u9fff]", s)]
    n = len(sentences) if sentences else 1

    fp = {
        "chars": zh,
        "sentences": n,
        "excl_per_sent": round(text.count("！") / n, 3),
        "comma_per_sent": round(text.count("，") / n, 2),
        "uses_quotes": '"' in text or '"' in text,
        "opening_50_lines": first,
    }

    # 提取人物名 (高频二字词中的专名)
    clean = re.sub(r"[^\u4e00-\u9fff]", "", text[: min(len(text), zh * 2)])
    words = list(jieba.cut(clean))
    word_freq = Counter(w for w in words if len(w) >= 2)
    # 取top 20中的人名(排除通用词)
    stop = {"一个", "没有", "自己", "什么", "他们", "我们", "不是", "这个", "那个",
            "已经", "知道", "可以", "起来", "现在", "还是", "如果", "因为", "所以",
            "但是", "然而", "不过", "只是", "就是", "都", "会", "很"}
    names = [(w, c) for w, c in word_freq.most_common(40) if w not in stop][:8]
    fp["top_names"] = [n[0] for n in names]

    # v6.3: 20 维叙事 DNA（供单层 + 双层互消使用，全文扫描避免截断漏维度）
    fp["dimensions"] = _extract_dimensions(text)

    # ── 增强指纹（默认关）：仅诊断/内部使用，绝不注入 prompt
    if enhanced:
        opts = enhanced_opts or {}
        do_ngram = bool(opts.get("ngram", True))
        do_plot = bool(opts.get("plot", True))
        do_syntax = bool(opts.get("syntax", True))
        if do_ngram:
            fp["ngram_vec"] = _build_ngram_vec(text)
        if do_plot:
            fp["plot_units"] = _build_plot_units(text)
        if do_syntax:
            fp["syntax_profile"] = _build_syntax_profile(sentences, text)

    return fp


def pick_files(category, sample_n, min_kb=0, max_kb=99999, corpus_root="corpus"):
    """
    支持两种 corpus 结构:
      - corpus/分类名/小说.txt  (子目录模式)
      - corpus/小说.txt         (平铺模式)

    优先查找 corpus_root/category/，不存在则直接在 corpus_root/ 下找。
    min_kb/max_kb 过滤文件大小（默认不限制）。
    """
    # 子目录模式
    cat_dir = os.path.join(corpus_root, category)
    if os.path.isdir(cat_dir):
        search_dir = cat_dir
    elif os.path.isdir(corpus_root):
        # 平铺模式 / category 为空时直接用 corpus_root
        search_dir = corpus_root
    else:
        return []

    candidates = []
    for fname in os.listdir(search_dir):
        if not fname.lower().endswith(".txt"):
            continue
        fpath = os.path.join(search_dir, fname)
        if not os.path.isfile(fpath):
            continue
        size_kb = os.path.getsize(fpath) / 1024
        if min_kb <= size_kb <= max_kb:
            candidates.append(fpath)

    if len(candidates) < sample_n:
        sample_n = len(candidates)
    return random.sample(candidates, sample_n)


# === 硬编码规则: LLM禁止项 ===
# 注意: run_pipeline.py 调用时使用 include_rules=False，
# 因为提示词模板会提供更精确的规则，避免规则冲突。
BANNED_PATTERNS = [
    "对X而言", "一切都在", "她心想", "她意识到", "她感到",
    "一种说不出的", "真正的X是Y", "X的意义在于", "X既是Y也是Z",
    "谁说X就一定Y",
]

BANNED_TEMPLATES = [
    "眼中闪过", "嘴角勾起", "眼眶微红", "不可置信",
    "眼底闪过", "咬了咬唇", "冷冷地说"
]

HARD_RULES = """
## 生成硬性约束

### 标点禁令
- 永远禁止: ； ！！！ ？！
- 对话用中文引号「」或 名字：前缀

### 禁用句式(一个都不能出现):
{patterns}

### 禁用模板描写(一个都不能出现):
{templates}

### 风格规则
- 第一人称
- 数字分节: 1 2 3...(裸数字，无标题)
- 分隔符: ……
- 精确数字: 金额/时间/数量精确到个位
- 压缩情感循环: 每弧≤8句
- 巧合推动情节: ≥1次意外发现
- 短段快节奏: 一段=一个动作/一句对话/一个念头
- 每段同时存在≤5字句和≥40字句
- 句式突变: 相邻3句不同结构
- 番茄小白话: 小学六年级词汇为主,复句≤30%
- 零思维标记: 禁用 心想/意识到/感到/觉得/认为
- 多主语修复: 无 他他他/她她她 连续序列
- 语域碰撞: 100字内正式+粗俗并置≥1次
- 刻意词汇重复: 500字内关键词≥3次
- 人设标签(≥3): 杀伐果断/清醒独立/拒绝内耗/黑莲花/人间清醒/搞钱脑
- 禁用: 圣母/优柔寡断/憋屈/精神内耗
"""


# v6.3 — 20 维叙事 DNA 关键词表（零模型，关键词驱动，可随 corpus 演化扩展）
_DIMENSION_KEYWORDS = {
    "死亡方式": ["被杀", "毒死", "淹死", "烧死", "摔死", "刺死", "勒死", "饿死",
              "自尽", "被害", "谋杀", "暗杀", "行刑", "处斩", "赐死",
              "咽气", "病逝", "战死", "遇刺", "干尸", "吸干"],
    "重生触发": ["重生", "穿越", "魂穿", "醒来", "回到", "复活", "附体", "穿越后",
              "睁开眼", "穿越过来", "穿书", "魂归"],
    "背景设定": ["侯府", "王府", "皇宫", "京城", "将军府", "太傅府", "太医院",
              "北境", "边关", "现代", "古代", "架空", "末世", "豪门", "校园"],
    "背叛者": ["夫君", "丈夫", "表哥", "表妹", "青梅竹马", "白月光",
            "兄长", "姐姐", "妹妹", "家人", "族人", "闺蜜",
            "嫡姐", "太子", "王爷", "皇帝", "皇上"],
    "复仇手段": ["报复", "复仇", "翻盘", "反击", "碾压", "打脸", "取代",
            "夺权", "离间", "栽赃", "揭发", "弹劾", "抄家", "种地"],
    "独特道具": ["系统", "金手指", "空间", "弹幕", "心声", "读心",
            "预知", "玉佩", "信物", "圣旨", "兵符", "令牌",
            "宝典", "秘籍", "空间戒指", "好孕系统", "攻略手册"],
    "主角身份": ["皇后", "嫡女", "庶女", "嫡子", "将军", "影后", "总裁", "学生",
             "神医", "农女", "王妃", "郡主", "首富", "特工", "法医"],
    "核心冲突": ["宅斗", "宫斗", "权谋", "商战", "替身", "误会", "追妻", "夺嫡",
             "和离", "退婚", "掉马", "身世", "复仇", "权位"],
    "情感基调": ["虐恋", "甜宠", "爽文", "暗黑", "治愈", "be", "he", "替身文学",
             "追妻火葬场", "白月光"],
    "金手指": ["系统", "空间", "重生", "读心", "预知", "异能", "随身", "老爷爷",
            "签到", "抽奖", "复制", "透视"],
    "反派动机": ["妒忌", "贪财", "夺权", "灭口", "执念", "报复", "嫉妒", "私生",
             "遗产", "上位", "占有"],
    "救赎弧": ["洗白", "放下", "和解", "自我救赎", "原谅", "赎罪", "回头", "弥补"],
    "关键转折": ["真相", "失忆", "失身", "身世", "假死", "掉马", "揭穿", "病危",
             "遗书", "录音", "视频"],
    "场景母题": ["宴会", "寺庙", "边疆", "豪门", "校园", "医院", "公司", "地下室",
             "祠堂", "婚礼", "产房", "考场"],
    "人设标签": ["黑莲花", "清醒", "病娇", "偏执", "白切黑", "人间清醒", "搞钱脑",
             "杀伐果断", "独立", "绿茶", "白莲花"],
    "开篇钩子": ["被杀", "被背叛", "重生", "系统激活", "穿书", "离婚", "退婚",
             "出海", "坠崖", "临盆", "入狱"],
    "结局取向": ["大婚", "团圆", "病逝", "孤老", "复仇成功", "身死", "封后",
             "和解", "开放式", "隐退"],
    "象征意象": ["玉佩", "梧桐", "血", "雪", "信", "刀", "簪", "棋", "佛珠",
             "红灯", "旧照"],
    "叙事视角": ["我", "朕", "本宫", "本王", "他", "她", "顾", "沈", "林"],
    "节奏型": ["一夜", "三天", "不过", "瞬间", "转眼", "当日", "翌日", "多年后",
            "刹那", "很快"],
}


def _extract_dimensions(text, dna=None):
    """v6.3 — 从源文提取 20 维叙事 DNA 特征，用于单层 + 双层互消公约数分析。

    演化表优先（dna 非空时，每维命中 = 该维"内置词 ∪ dna[dim]演化词"并集命中）；
    dna 缺失 / 某维为空则纯用内置兜底。保形：内置词始终保留，演化词仅追加。
    """
    head = text
    dims = {}
    for dim, seed_kws in _DIMENSION_KEYWORDS.items():
        # 演化词（来自 DNA 蒸馏表），缺失/空则回退空列表
        evo_kws = (dna or {}).get(dim) or []
        # 保形并集：内置 + 演化；dict.fromkeys 去重且保序
        kw_list = list(dict.fromkeys(list(seed_kws) + list(evo_kws)))
        hits = []
        for kw in kw_list:
            if kw and kw in head:
                hits.append(kw)
        dims[dim] = hits
    return dims


def build_llm_prompt(files_info, include_rules=True, style_align=False, rag_constraints=None, dna=None):
    """构建发给LLM的完整上下文
    :param files_info: [(name, fp_dict), ...] 源文指纹列表（兼容 dict {name,fp} 或 tuple (name,fp)）
    :param include_rules: 是否包含硬编码规则（提示词模式下为False）
    """
    prompt_parts = []

    # 归一化 files_info：dict {name,fp} 原样；tuple/list (name,fp) 转为 dict（兼容两种调用形态）
    _norm = []
    for fi in (files_info or []):
        if isinstance(fi, dict):
            _norm.append(fi)
        elif isinstance(fi, (tuple, list)) and len(fi) >= 2:
            _norm.append({"name": fi[0], "fp": fi[1]})
        else:
            _norm.append({"name": "", "fp": {}})
    files_info = _norm

    prompt_parts.append("你是熔铸仿写引擎。按以下流程生成一篇番茄风格短篇小说，目标 10000±500 字：建议分 15 章、每章 600-700 字（加深式扩写，勿加无关支线/新角色凑字数）。\n")

    # 第一步: 指纹
    prompt_parts.append("## 第一步: 阅读5份指纹\n")
    all_dims = []
    for i, fi in enumerate(files_info, 1):
        prompt_parts.append(f"### 源文{i}: {fi['name']}")
        prompt_parts.append(f"字数: {fi['fp']['chars']} | 句数: {fi['fp']['sentences']}")
        prompt_parts.append(f"!/句: {fi['fp']['excl_per_sent']} | ,/句: {fi['fp']['comma_per_sent']}")
        prompt_parts.append(f"高频人名: {', '.join(fi['fp']['top_names'][:5])}")
        prompt_parts.append(f"\n开篇50行:\n{fi['fp']['opening_50_lines']}")
        prompt_parts.append("")
        all_dims.append(fi['fp'].get('dimensions') or _extract_dimensions(fi['fp']['opening_50_lines']))

    # 第二步: 公约数提取逻辑（实际交集分析）
    n_files = len(files_info)
    intersection_threshold = max(3, n_files * 0.6)  # 至少3篇或60%的源文共有
    prompt_parts.append(f"## 第二步: 从{n_files}篇中提取公约数\n")
    prompt_parts.append(f"下面表格展示每篇源文在各维度的特征，以及{int(intersection_threshold)}篇交集的公约数：\n")
    header_cells = [f"文{i+1}" for i in range(n_files)] + [f"公约数(≥{int(intersection_threshold)}篇)"]
    prompt_parts.append("| 维度 | " + " | ".join(header_cells) + " |")
    prompt_parts.append("|" + "---|" * (n_files + 2))

    dimension_names = list(_DIMENSION_KEYWORDS.keys())  # v6.3: 20 维
    dimension_advice = {
        dim: "该维度≥3篇共有项须整体反转/自创，不可直抄任一源文"
        for dim in dimension_names
    }

    common_dict = {}
    common_count = {}
    for dim in dimension_names:
        cols = []
        flat_values = []
        for d in all_dims:
            vals = d.get(dim, [])
            label = "/".join(vals[:3]) if vals else "—"
            cols.append(label)
            flat_values.extend(vals)

        counter = Counter(flat_values)
        common = [v for v, c in counter.most_common() if c >= intersection_threshold]
        common_dict[dim] = "、".join(common[:5]) if common else ""
        common_count[dim] = len(common)
        intersection = common_dict[dim] if common_dict[dim] else f"无共同项 → {dimension_advice[dim]}"
        cols.append(intersection)

        # 截断过长的单元格（20维表更紧凑）
        cols = [c[:16] for c in cols]
        prompt_parts.append("| " + " | ".join([dim] + cols) + " |")

    prompt_parts.append("")

    # ── 第一层严格化（v6.3+ 互消升级）：列出「必须打破的高共有项 + 具体关键词」+ 生成前自检清单
    prompt_parts.append("\n## 第一层互消：单维严格反转（生成前必读）\n")
    reverse_items = []
    for dim in dimension_names:
        common_terms = common_dict.get(dim)
        if common_terms:
            reverse_items.append(
                f"- 【{dim}】高共有项「{common_terms}」→ 必须整体反转/自创，不可直抄任一源文"
            )
    if reverse_items:
        prompt_parts.extend(reverse_items)
    else:
        prompt_parts.append("本批源文无显著高共有单维项，按自身设定自创即可（仍须避开朱雀 16 字串）。")

    # 若 dna 演化表非空，给出更精准的反转锚点（用 dna 的具体词，而非仅维度名）
    if dna:
        prompt_parts.append("\n### 演化 DNA 反转锚点（基于同题材高频信号，须刻意避开/反转）")
        for dim in dimension_names:
            evo = (dna.get(dim) or [])[:8]
            if evo:
                prompt_parts.append(
                    f"- {dim} 高频信号: {', '.join(evo)} → 你的设定须明显偏离这些词，或取其反义/错位组合"
                )
    else:
        prompt_parts.append("\n（未加载演化 DNA，反转锚点采用内置 20 维关键词表。）")

    # 生成前自检清单
    prompt_parts.append("\n### 生成前自检清单（逐项确认后再动笔）")
    prompt_parts.append("自检：以下维度你已整体反转/自创了吗？")
    for dim in dimension_names:
        common_terms = common_dict.get(dim)
        if common_terms:
            prompt_parts.append(f"- [ ] {dim}：已避开「{common_terms}」并自创新设定")
        else:
            prompt_parts.append(f"- [ ] {dim}：已自创且不与任一源文雷同")
    prompt_parts.append("")

    # v6.3 第二层互消：维度组合钢印（按「组合强度」降序取 top-N，COMBO_TOP_N=10）
    prompt_parts.append("\n## 第二层互消：维度组合钢印\n")
    common_dims = [d for d in dimension_names if common_dict.get(d)]
    if len(common_dims) >= 2:
        combos = []
        for d1, d2 in itertools.combinations(common_dims, 2):
            # 组合强度 = 两维各自高共有项数之和（common_count 即该维 hit 计数）
            strength = common_count.get(d1, 0) + common_count.get(d2, 0)
            combos.append((d1, d2, strength))
        # 按组合强度降序取 top-N
        combos.sort(key=lambda x: x[2], reverse=True)
        for d1, d2, strength in combos[:COMBO_TOP_N]:
            prompt_parts.append(
                f"- 「{d1}={common_dict[d1]}」 × 「{d2}={common_dict[d2]}」 "
                f"(组合强度{strength}) 同时高共有 → 强类型钢印组合，"
                f"须连维度带组合一起打破，不可只换其一"
            )
        prompt_parts.append(
            "第二层原则：单层自创仍可能被朱雀按『维度组合』反查，"
            "须把高共有维度对整体错位（维度名与组合值同时自创）。"
        )
    else:
        prompt_parts.append("暂未检测到强维度组合钢印，按第一层单维互消执行即可。")
    prompt_parts.append("")

    # 第三步: 生成约束
    prompt_parts.append("## 第三步: 用公约数生成\n")
    prompt_parts.append("所有维度的高共有项都必须是你自创的，不能跟任何一篇源文相同或相似。")
    prompt_parts.append("如果犹豫一个设定是否太像某篇源文 → 换掉。宁可远，不可近。")
    prompt_parts.append("目标: 朱雀对5篇源文扫描输出的16字连续子串，一个都匹配不到（零命中）。")
    prompt_parts.append("生成后请用 Bloom 反查自检：把你产出中最长的连续中文串与源文逐字比对，确保无任何 ≥16 字重合。")
    prompt_parts.append("")

    if include_rules:
        prompt_parts.append(HARD_RULES.format(
            patterns=", ".join(BANNED_PATTERNS),
            templates=", ".join(BANNED_TEMPLATES)
        ))

    if style_align and _HUMAN_OK:
        _prof = _load_human_profile()
        _ap = _prof.get("avg_sent_len", {})
        _ep = _prof.get("excl_per_sent", {})
        _cp = _prof.get("comma_per_sent", {})
        _sp = _prof.get("short_sent_ratio", {})
        prompt_parts.append("## 人类风格对齐约束（反向优化层，目标为人类写作分布）")
        prompt_parts.append(
            "句长: 平均句长控制在 {}~{} 字之间，中位约 {} 字；"
            "短句(≤5字)占比 {}%~{}%；"
            "标点: ！/句 ≤ {}，,/句约 {}。".format(
                _ap.get("p10", 13), _ap.get("p90", 91), _ap.get("median", 20),
                int(_sp.get("p10", 0) * 100), int(_sp.get("p90", 0.17) * 100),
                _ep.get("p90", 0.25), _cp.get("median", 1.0)
            )
        )
        prompt_parts.append("写作时贴近上述人类分布，避免过长工整句式，保留自然碎句与口语节奏。")
        prompt_parts.append("")

    if rag_constraints:
        prompt_parts.append("## RAG 约束（题材自适应，仅约束不抄写）")
        _bl = rag_constraints.get("content_blacklist", [])
        if _bl:
            prompt_parts.append("内容黑名单（禁止直接使用以下高频名/设定，须自创替代）: " + "、".join(_bl[:10]))
        _tf = rag_constraints.get("type_formulas", {})
        if _tf:
            prompt_parts.append("该题材常见类型公式(请反转运用): " + "、".join("{}({})".format(k, v) for k, v in list(_tf.items())[:6]))
        prompt_parts.append("")

    prompt_parts.append("\n## 输出\n直接输出故事正文。不要前言、后记、说明。\n")

    return "\n".join(prompt_parts)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    args = sys.argv[1:]
    output_path = os.path.join("output", "fusion_context.txt")
    files = []
    category = None
    sample_n = 5
    min_kb, max_kb = 0, 99999
    corpus_root = "corpus"
    style_align = False
    rag_path = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "-o" and i + 1 < len(args):
            output_path = args[i + 1]; i += 2
        elif a == "--category" and i + 1 < len(args):
            category = args[i + 1]; i += 2
        elif a == "--sample" and i + 1 < len(args):
            sample_n = int(args[i + 1]); i += 2
        elif a == "--min-kb" and i + 1 < len(args):
            min_kb = int(args[i + 1]); i += 2
        elif a == "--max-kb" and i + 1 < len(args):
            max_kb = int(args[i + 1]); i += 2
        elif a == "--corpus" and i + 1 < len(args):
            corpus_root = args[i + 1]; i += 2
        elif a == "--style-align":
            style_align = True; i += 1
        elif a == "--rag" and i + 1 < len(args):
            rag_path = args[i + 1]; i += 2
        elif not a.startswith("-"):
            files.append(a); i += 1
        else:
            i += 1

    if category:
        picked = pick_files(category, sample_n, min_kb, max_kb, corpus_root)
        print(f"从 {category} 随机选 {len(picked)} 篇:")
        for p in picked:
            print(f"  {os.path.basename(p)}")
        files.extend(picked)

    if len(files) < 3:
        print("错误: 至少需要3篇源文")
        sys.exit(1)

    files_info = []
    for fp in files:
        text = read_file(fp)
        fingerprint = extract_fingerprint(text)
        files_info.append({
            "name": os.path.basename(fp),
            "fp": fingerprint
        })

    rag_data = None
    if rag_path and os.path.exists(rag_path):
        with open(rag_path, encoding="utf-8") as f:
            rag_data = json.load(f)
    prompt = build_llm_prompt(files_info, style_align=style_align, rag_constraints=rag_data)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    print(f"\n已输出: {output_path}")
    print("将此文件内容复制给LLM即可生成熔铸短篇")


if __name__ == "__main__":
    main()
