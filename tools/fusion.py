"""
fusion.py — 熔铸核心: 5源文→指纹并排→提取公约数→输出LLM可用的上下文

用法:
    python fusion.py --category 05_古代言情 --sample 5 -o output/fusion_context.txt
    python fusion.py file1.txt file2.txt file3.txt file4.txt file5.txt -o output/fusion_context.txt

输出 output/fusion_context.txt 包含:
    - 5篇各自的指纹摘要
    - 公约数(保留)和作者指纹(剔除)的对照表
    - LLM生成指令

依赖: pip install jieba
"""

import sys, os, re, json, random
import warnings
warnings.filterwarnings("ignore", message=".*pkg_resources.*")
import jieba
from collections import Counter


def read_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def count_chinese(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def first_n_lines(text, n=30):
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


def extract_fingerprint(text):
    """从源文提取结构化指纹"""
    first = first_n_lines(text, 30)
    zh = count_chinese(text)
    sentences = [s.strip() for s in re.split(r"[。！？]", text) if re.search(r"[\u4e00-\u9fff]", s)]
    n = len(sentences) if sentences else 1

    fp = {
        "chars": zh,
        "sentences": n,
        "excl_per_sent": round(text.count("！") / n, 3),
        "comma_per_sent": round(text.count("，") / n, 2),
        "uses_quotes": '"' in text[:zh//2],
        "opening_30_lines": first,
    }

    # 提取人物名 (高频二字词中的专名)
    clean = re.sub(r"[^\u4e00-\u9fff]", "", text[: min(len(text), zh * 2)])
    words = list(jieba.cut(clean))
    word_freq = Counter(w for w in words if len(w) >= 2)
    # 取top 20中的人名(排除通用词)
    stop = {"一个", "没有", "自己", "什么", "他们", "我们", "不是", "这个", "那个",
            "已经", "知道", "可以", "起来", "现在", "还是", "如果", "因为", "所以",
            "但是", "然而", "不过", "只是", "就是", "都", "会", "很", "都"}
    names = [(w, c) for w, c in word_freq.most_common(40) if w not in stop][:8]
    fp["top_names"] = [n[0] for n in names]

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
        if not fname.endswith(".txt"):
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
- 永远禁止: ； ！！！ ？！ 「」
- 不用引号，对话用 名字：或裸嵌入

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


def build_llm_prompt(files_info, include_rules=True):
    """构建发给LLM的完整上下文
    :param files_info: [(name, fp_dict), ...] 源文指纹列表
    :param include_rules: 是否包含硬编码规则（提示词模式下为False）
    """
    prompt_parts = []

    prompt_parts.append("你是熔铸仿写引擎。按以下流程生成一篇约10000字的番茄风格短篇小说。\n")

    # 第一步: 指纹
    prompt_parts.append("## 第一步: 阅读5份指纹\n")
    for i, fi in enumerate(files_info, 1):
        prompt_parts.append(f"### 源文{i}: {fi['name']}")
        prompt_parts.append(f"字数: {fi['fp']['chars']} | 句数: {fi['fp']['sentences']}")
        prompt_parts.append(f"!/句: {fi['fp']['excl_per_sent']} | ,/句: {fi['fp']['comma_per_sent']}")
        prompt_parts.append(f"高频人名: {', '.join(fi['fp']['top_names'][:5])}")
        prompt_parts.append(f"\n开篇30行:\n{fi['fp']['opening_30_lines']}")
        prompt_parts.append("")

    # 第二步: 公约数提取逻辑
    prompt_parts.append("## 第二步: 从5篇中提取公约数\n")
    prompt_parts.append("按以下维度对比5篇，提取公约数(≥3篇共有) AND 剔除作者指纹(1-2篇独有)：\n")
    prompt_parts.append("| 维度 | 文1 | 文2 | 文3 | 文4 | 文5 | 公约数 |")
    prompt_parts.append("|---|---|---|---|---|---|---|")
    prompt_parts.append("| 死亡方式 | ? | ? | ? | ? | ? | 从5篇中最少出现的那种里面挑一个全新的 |")
    prompt_parts.append("| 重生触发 | ? | ? | ? | ? | ? | 公约数保留 |")
    prompt_parts.append("| 背景设定 | ? | ? | ? | ? | ? | 挑一个5篇都不用的全新设定 |")
    prompt_parts.append("| 背叛者 | ? | ? | ? | ? | ? | 公约数保留 |")
    prompt_parts.append("| 复仇手段 | ? | ? | ? | ? | ? | 从5篇都不用的方法中自创 |")
    prompt_parts.append("| 独特道具 | ? | ? | ? | ? | ? | 剔除，自创全新 |")
    prompt_parts.append("")

    # 第三步: 生成约束
    prompt_parts.append("## 第三步: 用公约数生成\n")
    prompt_parts.append("死亡方式和背景必须是你自创的，不能跟任何一篇源文相同或相似。")
    prompt_parts.append("如果犹豫一个设定是否太像某篇源文 → 换掉。宁可远，不可近。")
    prompt_parts.append("目标: 朱雀对着5篇源文扫描输出的16字连续子串，一个都匹配不到。")
    prompt_parts.append("")

    if include_rules:
        prompt_parts.append(HARD_RULES.format(
            patterns=", ".join(BANNED_PATTERNS),
            templates=", ".join(BANNED_TEMPLATES)
        ))

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

    prompt = build_llm_prompt(files_info)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    print(f"\n已输出: {output_path}")
    print("将此文件内容复制给LLM即可生成熔铸短篇")


if __name__ == "__main__":
    main()
