# -*- coding: utf-8 -*-
"""
check_story.py — 爆款规则检查工具 (v6.3)

基于提示词库中定义的黄金三章、爽点密度、人设规则、AI痕迹等规则，
对生成的故事进行全面质量检测。支持体裁感知，自动适配检测维度。

用法:
    python check_story.py                        # 检查 output/story.txt
    python check_story.py output/story.txt       # 指定文件
    python check_story.py story.txt --genre 系统流 # 体裁适配
    python check_story.py story.txt --genre 古言   # 古代言情
    python check_story.py story.txt --genre 虐恋   # 虐恋
    python check_story.py story.txt --genre 重生   # 重生
    python check_story.py story.txt --anti           # 反模式作品 (调整EI阈值+思维标记容忍)

检测维度: 基础规范/标点/分节/AI模板词/黄金三章/爽点密度/角色归一化/
          结尾完整/对话密度/段落节奏/EI爽感指数(五维评估)/
          §11 叙事偏离度(本地三交叉·叙事层)/§12 去AI味/§13 退化与泄漏/
          §14 advisory风格密度/§15 统一创作质量矩阵
          （§11~§15 均为 WARN 软信号，零 corpus 泄漏，绝不产出 FAIL）
选项:     --genre 体裁适配 / --anti 反模式 / --no-ai-flavor 关闭第12节去AI味(默认开启)
"""

# ─────────────────────────────────────────────────────────────────────────────
# 红线登记（核心 IP 零改动，质量扩展已登记）
#   §11 叙事偏离度(本地三交叉·叙事层) / §12 去 AI 味 / §13 退化与泄漏检测 / §14 advisory 风格密度 / §15 统一创作质量矩阵
#   均为「已审思的引擎质量扩展」：仅弱信号、零 corpus 泄漏、绝不产出 FAIL；
#   不读取 / 不修改 fusion.py（互消层）等核心 IP，红线绝对安全。
#   本文件质量扩展逻辑与 fusion.py / bloom_guard.py / audit.py / anti_pattern.py
#   等核心 IP 严格隔离，互不影响。
# ─────────────────────────────────────────────────────────────────────────────
import re
import os
import sys

# ── 编码强制 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── 输出目录（所有产物强制落盘 output/）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_OUTPUT_DIR = os.path.join(_SCRIPT_DIR, "output")

# ── 体裁关键词配置 ──
# 不同体裁的爽点表达方式完全不同，需要独立词典
GENRE_PROFILES = {
    "default": {
        "climax_keywords": ["打脸", "反转", "碾压", "震惊", "崩溃", "愤怒", "嚣张", "冷笑"],
        "emotion_keywords": [
            "碾压", "打脸", "反转", "震惊全场", "不可思议", "难以置信",
            "冷笑", "不屑", "嘲讽", "威胁", "警告", "霸气", "强势",
            "泪流满面", "欣喜若狂", "激动万分", "终于", "成功", "胜利",
        ],
        "ch1_keywords": ["系统", "金手指", "重生", "穿越", "绑定", "觉醒", "激活"],
    },
    "系统流": {
        "climax_keywords": ["系统", "面板", "模拟", "绑定", "激活", "碾压", "反转", "震惊全场", "突破", "进化"],
        "emotion_keywords": [
            "面板", "点数", "模拟", "突破", "绑定", "激活", "进化", "升级",
            "碾压", "反转", "震惊", "打脸", "终于", "成功",
            "羡慕", "嫉妒", "不敢置信", "不可思议",
        ],
        "ch1_keywords": ["系统", "绑定", "面板", "激活", "模拟", "新手", "任务", "宿主"],
    },
    "虐恋": {
        "climax_keywords": ["误会", "心碎", "眼泪", "离开", "回头", "追妻", "后悔", "跪下"],
        "emotion_keywords": [
            "心碎", "眼泪", "误会", "离开", "转身", "后悔", "跪下", "深情",
            "虐心", "疼痛", "窒息", "崩溃", "绝望", "重逢", "原谅",
        ],
        "ch1_keywords": ["结婚", "契约", "替身", "误会", "离婚", "相遇", "重逢"],
    },
    "重生": {
        "climax_keywords": ["重生", "前世", "报仇", "复仇", "逆转", "碾压", "打脸", "后悔"],
        "emotion_keywords": [
            "重生", "前世", "报仇", "复仇", "碾压", "打脸", "逆转",
            "后悔", "震惊", "终于", "成功", "胜利", "归来",
        ],
        "ch1_keywords": ["重生", "前世", "死亡", "回到", "醒来", "复活"],
    },
    "古言": {
        "climax_keywords": ["打脸", "反转", "碾压", "赐婚", "封侯", "拜相", "灭门", "诛九族",
                            "震惊", "崩溃", "冷笑", "复仇"],
        "emotion_keywords": [
            "赐婚", "圣旨", "封侯", "拜相", "将军", "铁骑", "铠甲",
            "碾压", "打脸", "反转", "震惊", "终于", "成功", "归来",
            "冷笑", "不屑", "强势", "霸气", "命运", "权谋",
        ],
        "ch1_keywords": ["重生", "穿越", "赐婚", "圣旨", "婚事", "婚约", "将军", "战功",
                         "爵位", "封地", "兵权", "皇权", "权谋", "复仇", "前世"],
    },
    "文学": {
        "climax_keywords": [],
        "emotion_keywords": [],
        "ch1_keywords": [],
        "long_para_ok": True,
        "max_para_len": 500,
        "avg_para_max": 120,
        "dialogue_min": 0.3,
        "thinking_threshold_override": 25,
        "skip_golden_chapter": True,
        "skip_ending_check": True,
    },
}


def _read_file_safe(path):
    """统一文件读取: 支持utf-8/gbk/utf-8-sig三级回退"""
    for enc in ("utf-8", "gbk", "utf-8-sig"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def main(args=None):
    """check_story 主入口：解析参数 → 读取文件 → 15 节检查 → 输出报告。"""
    if args is None:
        args = sys.argv[1:]
    # ── 文件路径
    STORY_PATH = args[0] if len(args) > 0 and not args[0].startswith("--") else os.path.join(_OUTPUT_DIR, "story.txt")
    # ── 体裁参数解析
    GENRE = "default"
    ANTI_MODE = False
    AI_FLAVOR = True  # 第十二节「去 AI 味报告」默认开启（--no-ai-flavor 可关闭）
    for i, a in enumerate(args):
        if a == "--genre" and i + 1 < len(args):
            GENRE = args[i + 1]
        elif a == "--anti":
            ANTI_MODE = True
        elif a == "--no-ai-flavor":
            AI_FLAVOR = False
        elif a == "--ai-flavor":
            AI_FLAVOR = True

    profile = GENRE_PROFILES.get(GENRE, GENRE_PROFILES["default"])
    climax_keywords = profile["climax_keywords"]
    emotion_keywords = profile["emotion_keywords"]
    ch1_keywords = profile["ch1_keywords"]
    _LONG_PARA_OK = profile.get("long_para_ok", False)
    _MAX_PARA_LEN = profile.get("max_para_len", 200)
    _AVG_PARA_MAX = profile.get("avg_para_max", 80)
    _DIALOGUE_MIN = profile.get("dialogue_min", 1.5)
    _SKIP_GOLDEN = profile.get("skip_golden_chapter", False)
    _SKIP_ENDING = profile.get("skip_ending_check", False)

    if not os.path.exists(STORY_PATH):
        print(f"[ERROR] 文件不存在: {STORY_PATH}")
        sys.exit(1)

    text = _read_file_safe(STORY_PATH)

    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    print(f"文件: {STORY_PATH}")
    print(f"中文字数: {zh}")
    print(f"体裁模式: {GENRE} ({', '.join(profile['ch1_keywords'][:4])}...)")
    print("=" * 50)

    issues = []
    warns = []
    passes = []

    # ================================================================
    # 一、基础规范检查（提示词通用规则）
    # ================================================================
    print("\n【一、基础规范检查】")

    # 1.1 字数检查（短篇目标1000-3000字，熔铸版核心指标）
    if zh < 1000:
        issues.append(f"[P0-字数] 中文仅{zh}字，低于1000字最低标准")
    elif zh < 3000:
        passes.append(f"[OK] 字数{zh}字，达到短篇基础标准（1000+）")
    elif zh > 50000:
        warns.append(f"[字数] 中文{zh}字，超出短篇范围，检查是否有注水")
    else:
        passes.append(f"[OK] 字数{zh}字，充分达标")

    # 1.2 禁止标点（番茄平台审核规则）
    # 「」在fusion.py HARD_RULES中被禁止，此处统一检查
    banned_punctuation = ["；", "！！！", "？！"]
    for b in banned_punctuation:
        n = text.count(b)
        if n > 0:
            issues.append(f"[标点] 禁止标点「{b}」出现{n}处")
    # 检查引号：合并西文双引号和单引号
    ascii_double = text.count('"')
    ascii_single = text.count("'")
    ascii_quotes = ascii_double + ascii_single
    if ascii_quotes > 0:
        detail = f"双引号{ascii_double}次" if ascii_double > 0 else ""
        detail += f"{' + ' if ascii_double > 0 and ascii_single > 0 else ''}"
        detail += f"单引号{ascii_single}次" if ascii_single > 0 else ""
        warns.append(f"[引号] 西文引号出现{ascii_quotes}次({detail})，建议改用中文引号「」")
    if not any(text.count(b) > 0 for b in banned_punctuation) and ascii_quotes == 0:
        passes.append("[OK] 标点规范，无禁用标点")

    # 1.3 分节标记（支持多种格式：数字分节、第X章、Chapter、中文数字分节等）
    sections_num = len(re.findall(r"(?<=\n)\d+(?=\n)", text))
    sections_ch = len(re.findall(r"\n第[一二三四五六七八九十百千\d]+章", text))
    sections_en = len(re.findall(r"\nChapter\s+\d+", text, re.IGNORECASE))
    sections_cn = len(re.findall(r"\n[一二三四五六七八九十]{1,3}\s*\n", text))
    sections = max(sections_num, sections_ch, sections_en, sections_cn)
    print(f"  分节标记: 数字{sections_num}组 / 中文章{sections_ch}组 / 英文章{sections_en}组 / 中文数字{sections_cn}组 → 取最大值{sections}组")

    # ================================================================
    # 二、爆款模板禁用词（提示词规则）
    # ================================================================
    print("\n【二、AI模板禁用词检查】")

    # 核心禁用模板（高AI特征）
    core_templates = [
        "眼中闪过", "嘴角勾起", "眼眶微红", "不可置信",
        "眼底闪过", "咬了咬唇", "身子一颤", "心头一紧",
        "倒吸一口凉气", "目光一凝", "瞳孔一缩",
    ]
    total_templates = 0
    for t in core_templates:
        n = text.count(t)
        total_templates += n
        if n > 0:
            issues.append(f"[AI模板]「{t}」出现{n}次，高AI特征")
    if total_templates == 0:
        passes.append("[OK] 无AI模板禁用词")

    # 思维标记（降AI检测关键指标，体裁感知阈值）
    thinking_markers = ["心想", "意识到", "感到", "觉得", "认为", "明白"]
    # 系统流/反模式/古言故事叙事偏内省，容忍度提高
    _THINKING_THRESHOLD = {"default": 5, "系统流": 15, "古言": 12, "anti": 15}.get(
        "anti" if ANTI_MODE else GENRE,
        {"default": 5, "系统流": 15, "古言": 12, "虐恋": 10, "重生": 8}.get(GENRE, 5)
    )
    total_thinking = 0
    for m in thinking_markers:
        n = text.count(m)
        total_thinking += n
        if n > 0:
            warns.append(f"[思维标记]「{m}」{n}处")
    if total_thinking == 0:
        passes.append("[OK] 无思维标记，AI特征低")
    elif total_thinking > _THINKING_THRESHOLD:
        issues.append(f"[AI痕迹] 思维标记共{total_thinking}处，超过{_THINKING_THRESHOLD}处警戒线")

    # ================================================================
    # 三、黄金三章结构检查（提示词核心规则）
    # ================================================================
    print("\n【三、黄金三章结构检查】")

    # 3.1 检测是否存在分章结构（支持中文章/英文章/数字章/中文数字分节/裸数字分节）
    chapters = re.split(r"\n第[一二三四五六七八九十百千\d]+章[：:\s]*", text)
    if len(chapters) < 2:
        chapters = re.split(r"\nChapter\s+\d+", text, flags=re.IGNORECASE)
    if len(chapters) < 2:
        # 中文数字分节（如 "一\n" "十二\n"）
        chapters = re.split(r"\n[一二三四五六七八九十]{1,3}\s*\n", text)
    if len(chapters) < 2:
        # 按裸数字分节（如 "1\n" "2\n" 开头）
        chapters = re.split(r"\n(?=\d+\n)", text)
    if len(chapters) < 2:
        # 按段落密集型空行分节
        chapters = re.split(r"\n\s*\n\s*\n", text)

    if len(chapters) < 3:
        warns.append(f"[黄金三章] 仅检测到{len(chapters)}个分节，需要至少3章节结构")
    else:
        # 检查前三章的情绪推进
        early_text = "".join(chapters[:min(3, len(chapters))])
        # 爽点关键词检测（冲突、反转、打脸等）
        climax_count = sum(early_text.count(k) for k in climax_keywords)
        if climax_count < 1:
            warns.append("[黄金三章] 前三章爽点关键词仅{}处，建议加强冲突密度".format(climax_count))
        else:
            passes.append("[OK] 前三章爽点关键词{}处，节奏符合要求".format(climax_count))

        # 金手指/核心设定检测（第一章应出现核心设定，体裁差异）
        ch1_found = any(k in chapters[0] for k in ch1_keywords)
        if ch1_found:
            passes.append("[OK] 第一章检测到核心设定（{}），符合黄金三章首章规则".format(
                "金手指" if GENRE in ("default", "系统流") else "冲突铺垫"))
        else:
            if GENRE in ("古言", "虐恋", "重生"):
                warns.append("[黄金三章] 第一章未检测到核心设定词，检查开篇是否足够抓人")
            else:
                warns.append("[黄金三章] 第一章未检测到金手指/系统设定，建议首章亮出核心设定")

    # ================================================================
    # 四、爽点密度检查（提示词规则：每300字1个情绪点）
    # ================================================================
    print("\n【四、爽点密度检查】")

    # 情绪触发词（体裁感知）
    emotion_total = sum(text.count(k) for k in emotion_keywords)
    if zh > 0:
        emotion_density = emotion_total / (zh / 300)  # 每300字应有1个情绪点
        if emotion_density < 0.3:
            warns.append("[爽点密度] 情绪触发词密度{:.1f}/300字，偏低，建议加强".format(emotion_density))
        elif emotion_density < 0.5:
            warns.append("[爽点密度] 情绪触发词密度{:.1f}/300字，可进一步加强".format(emotion_density))
        else:
            passes.append("[OK] 情绪触发词密度{:.1f}/300字，符合要求".format(emotion_density))
    print(f"  情绪触发词总计: {emotion_total} 次")

    # ================================================================
    # 五、角色归一化检查（提示词人设规则）
    # ================================================================
    print("\n【五、角色归一化检查】")

    # ── 姓名提取引擎 v3.0 ──
    # 设计原则：不用黑名单筛查，而是靠姓氏分级+语义校验从底层杜绝误报。
    #   强姓氏/复姓（极少构成普通词汇）→ 宽上下文匹配
    #   弱姓氏（高频构成普通词汇）   → 宽匹配 + jieba词典过滤
    #   2字弱姓候选是歧义核心 → jieba识别的常见词直接筛掉

    # 复姓：天然无歧义
    _COMPOUND_SURNAMES = r"慕容|欧阳|司马|上官|诸葛|东方|西门|南宫|独孤|端木|尉迟|皇甫|令狐|夏侯|长孙|宇文|司徒|司空"

    # 强姓氏：几乎只作姓氏，极少出现在普通词汇中
    # （排除含"水""柏""窦"等极端罕见姓，它们在现代文本中带来的噪声远超价值）
    _STRONG_SURNAMES = "赵钱孙李周吴郑王冯蒋韩杨朱秦尤何吕施张孔曹严华金魏陶姜戚谢邹喻章"
    # 中等姓氏：常见姓氏，偶尔构成普通词汇（但概率低）
    _MEDIUM_SURNAMES = "苏沈顾楚陆萧"
    # 弱姓氏：高频出现在普通词汇中（方向/白云/江水/树林/叶子/许多等）
    _WEAK_SURNAMES = "方白江林叶云柳陈许"

    # 普适第二字过滤：语言学规则——这些字符几乎不可能作为任何中文名字的第二字
    # 涵盖：结构助词/方位词/量词/代词/疑问词/介词/数字序数/方向词
    # v3.1: 从仅弱姓扩展为全部姓氏普适（"张了/周上/周一"在任何姓氏下都不是人名）
    _UNLIKELY_SECOND_CHAR = set(
        "的得地了着过上中下内外前后左右里旁边这个些次回"
        "和与及或但而把被给对向从由吗呢吧啊什么每各某"
        "一二三四五六七八九十百千万亿零"  # 数字/序数后缀
        "东西南北"  # 绝对方向词（东张西望→张西）
        "不"        # 否定虚词（欠钱不还→钱不）
    )

    # 宽上下文：标点 + 说话/动作/修饰/副词 —— 名字后常见的各种跟随
    _BROAD_CONTEXT = r"[，。！？：\'\"说问道喊叫嚷骂答哭笑叹看走向站坐来去便就吃喝走跑拿放打推抱点望轻微悄缓也已只都还才又再正总]"

    # 复姓集合（模块级，供多处使用）
    _compound_set = set(_COMPOUND_SURNAMES.split("|"))

    # 构建分层正则（拆分为独立模式避免{1,2}贪婪吞字）
    # 词边界(?<![\u4e00-\u9fff])仅用于弱姓2字名——歧义最高的场景
    # 强/中/复姓和所有3字名不限制词边界（它们在"但X说"等位置也应是名字）
    _patterns = []
    _wb = r"(?<![\u4e00-\u9fff])"
    _strong_med = _STRONG_SURNAMES + _MEDIUM_SURNAMES
    # 1) 复姓 + 1字 → 宽上下文
    _patterns.append(rf"((?:{_COMPOUND_SURNAMES})[\u4e00-\u9fff])(?={_BROAD_CONTEXT})")
    # 2) 复姓 + 2字 → 宽上下文
    _patterns.append(rf"((?:{_COMPOUND_SURNAMES})[\u4e00-\u9fff]{{2}})(?={_BROAD_CONTEXT})")
    # 3) 强/中姓 + 1字（2字名）→ 宽上下文
    _patterns.append(rf"([{_strong_med}][\u4e00-\u9fff])(?={_BROAD_CONTEXT})")
    # 4) 强/中姓 + 2字（3字名）→ 宽上下文
    _patterns.append(rf"([{_strong_med}][\u4e00-\u9fff]{{2}})(?={_BROAD_CONTEXT})")
    # 5) 弱姓 + 2字（3字名）→ 宽上下文
    _patterns.append(rf"([{_WEAK_SURNAMES}][\u4e00-\u9fff]{{2}})(?={_BROAD_CONTEXT})")
    # 6) 弱姓 + 1字（2字名）⊕ 词边界 → 宽上下文（歧义最高，要求词边界）
    _patterns.append(rf"{_wb}([{_WEAK_SURNAMES}][\u4e00-\u9fff])(?={_BROAD_CONTEXT})")

    # 合并执行
    names_found = set()
    for pat in _patterns:
        names_found.update(re.findall(pat, text))

    # ── jieba 词频校验：弱姓2字候选 → 高频词典词=非人名 ──
    _jieba_loaded = False
    try:
        import jieba
        # 触发词典加载
        list(jieba.cut("初始化"))
        _jieba_loaded = True
    except ImportError:
        pass

    if names_found:
        # ── v3.1 普适规则：第二字过滤（对所有姓氏生效）──
        # 消除 "张了/周上/周一/周三/周的/方方的" 等批量误报
        # 语言学规则不因姓氏强弱而改变：数字/虚词/结构词不可作人名第二字
        all_2char = {n for n in names_found if len(n) == 2}
        for n in all_2char:
            if n[1] in _UNLIKELY_SECOND_CHAR:
                names_found.discard(n)
        # v3.1: 3字名第二字也检查数字/虚词 → 消除"张三月/李四也/周五点"
        all_3char = {n for n in names_found if len(n) == 3}
        _DIGIT_CHARS = set("一二三四五六七八九十百千万亿零")
        for n in all_3char:
            if n[1] in _DIGIT_CHARS or n[1] in _UNLIKELY_SECOND_CHAR:
                names_found.discard(n)
            # 首字重复 = 形容词重叠形式（"方方的/蒙蒙的"），非人名
            if n[0] == n[1]:
                names_found.discard(n)
        # v3.1: 2字名双方均为姓氏 → 上下文碎片（"谢谢周总监"→"谢周"）
        _ALL_SURNAMES = set(_STRONG_SURNAMES + _MEDIUM_SURNAMES + _WEAK_SURNAMES)
        for n in list(names_found):
            if len(n) == 2 and n[0] in _ALL_SURNAMES and n[1] in _ALL_SURNAMES:
                names_found.discard(n)

    if _jieba_loaded and names_found:
        # 利用 jieba 内置词典词频区分常见词和人名：
        #   常见词（方向8151/白云389/许多25601）→ freq > 200 → 过滤
        #   人名（方悦/叶璇/江辰）→ freq=-1（不在词典）→ 保留
        #   低频词（白芷19/林间92）→ freq 1~200 → 保留（可能是人名）
        _NAME_WHITELIST = {"白云"}  # 高频但可作人名
        weak_2char = {n for n in names_found if len(n) == 2 and n[0] in _WEAK_SURNAMES}
        weak_3char = {n for n in names_found if len(n) == 3 and n[0] in _WEAK_SURNAMES}
        # v3.1: 强/中姓2字名也做jieba高频词过滤，消除罕见强姓误报
        #   （阈值500=宁可漏一个真名也不放一个假名，强姓极少形成高频词）
        strong_med_2char = {n for n in names_found if len(n) == 2 and n[0] in _strong_med}
        verified = set()
        for n in weak_2char:
            freq = jieba.dt.FREQ.get(n, -1)
            if freq > 200 and n not in _NAME_WHITELIST:
                continue
            verified.add(n)
        for n in strong_med_2char:
            freq = jieba.dt.FREQ.get(n, -1)
            if freq > 500:  # 强姓高频词阈值更高（减少误杀）
                continue
            # v3.1: 前字+姓氏高频检查 → "一张表"中"一张"是高频量词→"张表"非人名
            is_real_name = False
            for m in re.finditer(re.escape(n), text):
                pos = m.start()
                if pos == 0:
                    is_real_name = True; break  # 句首→真实人名上下文
                prev = text[pos - 1]
                if not re.match(r"[\u4e00-\u9fff]", prev):
                    is_real_name = True; break  # 词边界→真实人名上下文
                compound_before = prev + n[0]
                if jieba.dt.FREQ.get(compound_before, -1) <= 500:
                    is_real_name = True; break  # 前字+姓氏非高频→可能是真名
            if not is_real_name:
                continue  # 所有出现都在高频复合词内部（如"一张"→"张表"）→非人名
            verified.add(n)
        # 弱姓3字名：复合词校验 —— 防止"北方更美"→"方更美"、以及"方案我"
        for n in weak_3char:
            freq = jieba.dt.FREQ.get(n, -1)
            if freq > 200:
                continue
            # v3.1: 额外检查 姓氏+第2字 是否为高频词 → 防"方案我"（方案=freq高）
            surname_plus_second = n[:2]
            if jieba.dt.FREQ.get(surname_plus_second, -1) > 200:
                continue
            # 检查是否所有出现位置都在复合词内部（如"北方更美"中的"方更美"）
            all_mid_compound = True
            for m in re.finditer(re.escape(n), text):
                pos = m.start()
                if pos == 0:
                    all_mid_compound = False
                    break
                prev = text[pos - 1]
                if not re.match(r"[\u4e00-\u9fff]", prev):
                    all_mid_compound = False
                    break
                compound = prev + n[0]
                if jieba.dt.FREQ.get(compound, -1) <= 200:
                    all_mid_compound = False
                    break
            if all_mid_compound:
                continue  # 所有出现都在高频复合词内部 → 非人名
            verified.add(n)
        # 重建：复姓 + 强中姓非高频 + 校验通过的弱姓和强中姓
        names_found = {n for n in names_found
                       if (n[:2] in _compound_set)
                       or (n[0] in _strong_med and n in verified)
                       or (n[0] in _WEAK_SURNAMES and n in verified)}

    # 去重时按前缀合并（苏暖、苏暖暖视为同一角色），频次优先
    # 复姓取前2字=姓氏，单姓取前2字=姓+第一字（保持原版行为）
    dedup_names = {}
    for n in names_found:
        prefix = n[:2]  # 始终取前2字作为分组键
        if prefix not in dedup_names:
            dedup_names[prefix] = []
        dedup_names[prefix].append(n)
    # 每个前缀组选最优：优先非说话动词结尾 + 高频次 + 长名
    _SPEECH_TAIL = set("说问道喊叫嚷骂答哭笑叹怒斥喝看")  # 结尾字是说话/动作动词 → 很可能是被吞掉的上下文
    all_names = set()
    for prefix, variants in dedup_names.items():
        if len(variants) == 1:
            all_names.add(variants[0])
        else:
            # 评分：clean(尾字不是动词)>0 > 出现次数 > 名字长度
            scored = [(0 if v[-1] in _SPEECH_TAIL else 1, text.count(v), len(v), v) for v in variants]
            scored.sort(reverse=True)
            all_names.add(scored[0][3])

    # ── 角色名后过滤：排除称号/家族词/常见词汇 ──
    _TITLE_WORDS = frozenset({
        "王妃", "王爷", "皇后", "皇上", "太子", "夫人", "小姐", "少爷",
        "公主", "郡主", "娘娘", "太后", "太妃", "世子", "侯爷", "将军",
        "大人", "尚书", "侍郎", "院判", "统领", "副将", "主母", "姨娘",
        "婆母", "小姑", "小叔", "夫君", "相公", "娘子",
    })
    _FAMILY_SUFFIX = frozenset("家府院宫阁殿堂坊")
    # 高频词但非人名的词组
    _COMMON_NOUNS = frozenset({
        "白甜", "白转", "钱都", "陆家", "顾家", "王家", "你们", "看着",
        "这是", "不是", "什么", "可以", "已经", "知道", "没有",
    })

    filtered_names = set()
    for n in all_names:
        if n in _TITLE_WORDS:
            continue
        if len(n) >= 2 and n[-1] in _FAMILY_SUFFIX:
            continue
        if n in _COMMON_NOUNS:
            continue
        filtered_names.add(n)
    all_names = filtered_names

    # ── 诊断输出 ──
    if len(all_names) > 0:
        strong = [n for n in all_names if n[0] in _STRONG_SURNAMES]
        compound = [n for n in all_names if n[:2] in _compound_set]
        medium = [n for n in all_names if n[0] in _MEDIUM_SURNAMES]
        weak = [n for n in all_names if n[0] in _WEAK_SURNAMES]
        print(f"  姓氏分级: 强姓{len(strong)}个 / 中姓{len(medium)}个 / 弱姓{len(weak)}个 / 复姓{len(compound)}个")
    if len(all_names) > 10:
        warns.append("[角色数量] 检测到{}个疑似角色名，短篇建议控制在10个以内".format(len(all_names)))
    elif len(all_names) > 0:
        passes.append("[OK] 检测到{}个角色名，短篇可控".format(len(all_names)))
    else:
        warns.append("[角色识别] 未检测到清晰的角色名，建议增加角色命名")
    print(f"  疑似角色名: {', '.join(sorted(list(all_names)[:8]))}")

    # 主角一致性检查：同名不同写法（如 苏暖 vs 苏暖暖，慕容雪 vs 慕容白雪）
    # v3.1: 只在实际名字有前缀关系时才标记为别名
    # 同姓不同名（赵天豪 vs 赵建明）不再误合并
    name_aliases = {}
    for n in all_names:
        # 分离姓氏和名字部分
        if n[:2] in _compound_set:
            surname_len = 2
        else:
            surname_len = 1
        base_surname = n[:surname_len]
        given_name = n[surname_len:]
        if base_surname not in name_aliases:
            name_aliases[base_surname] = []
        name_aliases[base_surname].append(given_name)
    for surname, givens in name_aliases.items():
        if len(givens) <= 1:
            continue
        # 检查是否有名字之间的前缀关系（如 "暖" 是 "暖暖" 的前缀）
        real_aliases = []
        givens_sorted = sorted(set(givens), key=len)
        for i, short_given in enumerate(givens_sorted):
            full_short = surname + short_given
            for long_given in givens_sorted[i + 1:]:
                full_long = surname + long_given
                if len(short_given) > 0 and long_given.startswith(short_given):
                    real_aliases.append(f"{full_short} → {full_long}")
        if real_aliases:
            warns.append("[角色归一化] 疑似同一角色名不同写法: {}".format(", ".join(real_aliases)))

    # ================================================================
    # 六、结尾检查（提示词规则：拒绝开放式结局）
    # ================================================================
    print("\n【六、结尾检查】")

    # 获取最后300字
    end_text = text[-300:] if len(text) > 300 else text
    open_endings = ["未完待续", "未完", "......", "…", "故事还在继续", "新的开始"]
    open_count = sum(end_text.count(o) for o in open_endings)
    if open_count > 0:
        issues.append("[结局] 检测到开放式结局标记，提示词要求闭合结局")

    # 结局情绪检测
    ending_power_keywords = ["终于", "成功", "幸福", "圆满", "胜利", "归来", "结束", "结局"]
    ending_power = sum(end_text.count(k) for k in ending_power_keywords)
    if ending_power == 0:
        warns.append("[结局] 未检测到结局情绪关键词，可能缺乏闭合感")
    else:
        passes.append("[OK] 结局情绪关键词{}处，结局收敛".format(ending_power))

    # ================================================================
    # 七、对话密度检查（番茄风格要求高对话密度）
    # ================================================================
    print("\n【七、对话密度检查】")

    # 对话密度: 匹配中文引号""或冒号对话
    dialogue_lines = len(re.findall(r'\u201c[^\u201c\u201d]{1,50}\u201d', text))
    dialogue_colon = len(re.findall(r'[：:][^。！？\n]{1,50}[。！？]', text))
    dialogue_pat = len(re.findall(r'[。！？\n][^。！？\n]*?[说问道喊叫嚷吧吗呢啊]', text))
    dialogue_total = dialogue_lines + dialogue_colon + dialogue_pat
    if zh > 0:
        dialogue_ratio = dialogue_total / (zh / 100)  # 每100字对话次数
        if dialogue_ratio < _DIALOGUE_MIN:
            warns.append("[对话密度] 对话密度{:.1f}/100字，低于{:.1f}，{}风格建议提高对话".format(
                dialogue_ratio, _DIALOGUE_MIN, GENRE if GENRE != "default" else "番茄"))
        else:
            passes.append("[OK] 对话密度{:.1f}/100字，达标".format(dialogue_ratio))
    print(f"  对话估算: {dialogue_total} 处")

    # ================================================================
    # 八、节奏检查（段落长度）
    # ================================================================
    print("\n【八、节奏检查】")

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    long_paragraphs = [p for p in paragraphs if len(p) > 200]
    if len(long_paragraphs) > 0:
        warns.append("[段落过长] {}个段落超过200字，番茄风格建议短段落".format(len(long_paragraphs)))
    if len(paragraphs) > 0:
        avg_para_len = sum(len(p) for p in paragraphs) / len(paragraphs)
        if avg_para_len > 80:
            warns.append("[段落节奏] 平均段落{:.0f}字，建议控制在80字以内".format(avg_para_len))
        else:
            passes.append("[OK] 平均段落{:.0f}字，节奏紧凑".format(avg_para_len))

    # ================================================================
    # 九、人类吻合度检查（反向优化·反朱雀代理）
    # ================================================================
    print("\n【九、人类吻合度检查】")

    try:
        _sd = os.path.dirname(os.path.abspath(__file__))
        if _sd not in sys.path:
            sys.path.insert(0, _sd)
        from tools.humanity_scorer import score_humanity

        _hs = score_humanity(text)
        _score = _hs["humanity_score"]
        print(f"  人类度评分: {_score} / 100")
        for _k, _d in _hs["details"].items():
            print(f"    {_k}: 当前{_d['cur']} | {_d.get('note','')} | 分{_d['score']}")
        if _score >= 75:
            passes.append(f"[OK] 人类吻合度{_score}，文本统计贴近人类写作分布")
        elif _score >= 55:
            warns.append(f"[人类吻合度] 评分{_score}，部分偏离人类分布，建议调整句长/标点节奏")
        else:
            warns.append(f"[人类吻合度] 评分{_score}，统计明显偏离人类分布，疑似AI工整句式")
    except Exception as _e:
        print(f"  [SKIP] 人类吻合度评估异常: {_e}")

    # ================================================================
    # 结果汇总
    # ================================================================
    print("\n" + "=" * 50)
    print("检查结果汇总")
    print("=" * 50)

    if passes:
        print(f"\n  ✅ 通过 ({len(passes)}):")
        for p in passes:
            print(f"     {p}")

    if warns:
        print(f"\n  ⚠️  警告 ({len(warns)}):")
        for w in warns:
            print(f"     {w}")

    if issues:
        print(f"\n  ❌ 严重问题 ({len(issues)}):")
        for i in issues:
            print(f"     {i}")

    print(f"\n总计: ✅{len(passes)} 通过 / ⚠️{len(warns)} 警告 / ❌{len(issues)} 严重问题")

    # ── 保存检查报告（报告强制落盘 output/ 目录）──
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    report_path = os.path.join(_OUTPUT_DIR, os.path.basename(STORY_PATH).replace(".txt", "_check_report.txt"))
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("爆款规则检查报告\n")
        f.write("=" * 50 + "\n")
        f.write(f"文件: {STORY_PATH}\n")
        f.write(f"中文字数: {zh}\n")
        f.write(f"体裁模式: {GENRE}\n\n")
        f.write(f"✅ 通过 ({len(passes)}):\n")
        for p in passes:
            f.write(f"  {p}\n")
        f.write(f"\n⚠️ 警告 ({len(warns)}):\n")
        for w in warns:
            f.write(f"  {w}\n")
        f.write(f"\n❌ 严重问题 ({len(issues)}):\n")
        for i in issues:
            f.write(f"  {i}\n")
    print(f"\n检查报告已保存: {report_path}")

    # ================================================================
    # 九 → 十、爽感指数 EI 评估（反模式系统集成）
    # ================================================================
    print("\n" + "=" * 50)
    print("【十、爽感指数 EI 评估】")
    print("=" * 50)

    try:
        _script_dir = os.path.dirname(os.path.abspath(__file__))
        if _script_dir not in sys.path:
            sys.path.insert(0, _script_dir)
        from tools.anti_pattern import calculate_EI

        ei_result = calculate_EI(text)
        ei_score = ei_result["EI"]
        ei_grade = ei_result["grade"]
        ei_details = ei_result.get("details", {})

        print(f"\n  爽感指数: {ei_score} / 100  |  等级: {ei_grade}")

        # ── 反模式调整 ──
        if ANTI_MODE:
            anti_note = "  (反模式作品走降级弧+惨胜路线，天然牺牲表层爽感换取心理深度)"
            print(anti_note)
            ei_score_adjusted = ei_score  # 移除原 ×1.3+8 通胀：反模式作品本就牺牲表层爽感，等效EI不应被放大
            ei_grade_adjusted = (
                "极致爽感" if ei_score_adjusted >= 95 else
                "爆款爽文" if ei_score_adjusted >= 75 else
                "爽文及格" if ei_score_adjusted >= 55 else
                "需要优化" if ei_score_adjusted >= 35 else "不及格"
            )
            print(f"  反模式等效EI: {ei_score_adjusted:.1f} / 100  |  等效等级: {ei_grade_adjusted}")

        print(f"\n  五维分解:")
        for k, v in ei_details.items():
            if isinstance(v, float):
                print(f"    {k}: {v:.1f}")
            else:
                print(f"    {k}: {v}")

        # EI评级建议
        if ANTI_MODE:
            effective = ei_score_adjusted
        else:
            effective = ei_score

        if effective < 40:
            warns.append(f"[EI] 爽感指数{ei_score}，低于及格线40，建议使用反模式生成增强爽感")
        elif effective < 60:
            warns.append(f"[EI] 爽感指数{ei_score}，达到及格但不够爆款，建议加强预期违背和情绪极差")
        elif effective < 80:
            passes.append(f"[OK] 爽感指数{ei_score}，达到爆款爽文水平")
        else:
            passes.append(f"[OK] 爽感指数{ei_score}，极致爽感级别")

        # 追加到报告文件
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 50}\n")
            f.write(f"爽感指数 EI 评估\n")
            f.write(f"{'=' * 50}\n")
            f.write(f"总分: {ei_score} / 100\n")
            f.write(f"等级: {ei_grade}\n\n")
            f.write(f"五维详情:\n")
            for k, v in ei_details.items():
                if isinstance(v, float):
                    f.write(f"  {k}: {v:.1f}\n")
                else:
                    f.write(f"  {k}: {v}\n")

        print(f"\n  EI评估已追加到检查报告: {report_path}")

    except ImportError:
        print("  [SKIP] anti_pattern 模块未找到，跳过EI评估")
        print("  安装反模式引擎: 确认 tools/anti_pattern.py 存在")
    except Exception as e:
        print(f"  [ERROR] EI评估异常: {e}")

    # ================================================================
    # 十一、叙事偏离度报告（本地三交叉·叙事层，方向③）
    # ================================================================
    print("\n" + "=" * 50)
    print("【十一、叙事偏离度报告】")
    print("=" * 50)

    try:
        _sd = os.path.dirname(os.path.abspath(__file__))
        if _sd not in sys.path:
            sys.path.insert(0, _sd)
        from tools.narrative_features import extract_narrative_features
        from tools.local_discriminator import score as nd_score, load_baseline as nd_load
        from tools.humanity_scorer import triple_cross_judge

        # 载入叙事基线（若已构建）；未构建则判别器使用 taxonomy 默认基线（优雅降级）
        _nar_base = nd_load()
        _nar_base_note = ("（已加载 corpus 叙事基线）" if _nar_base
                          else "（未构建基线，使用 taxonomy 默认基线，建议运行 "
                               "python tools/narrative_features.py --build-baseline）")

        _feats = extract_narrative_features(text)
        _nd = nd_score(text, _nar_base)
        print(f"  叙事层人类度: {_nd['human_score']} / AI度: {_nd['ai_score']}")
        print(f"  叙事偏离度(narrative_deviation): {_nd['narrative_deviation']}  {_nar_base_note}")
        if _nd['triggered_features']:
            print(f"  触发/异常特征: {', '.join(_nd['triggered_features'])}")
        else:
            print("  触发/异常特征: 无（叙事结构在人类区间内）")

        # 跨源叙事偏离度：相对人类基线各字段带外计数（可解释）
        _dev_feats = []
        if _nar_base:
            for _fn, _info in _nar_base.get("numeric", {}).items():
                _v = _feats.get(_fn)
                if not isinstance(_v, (int, float)):
                    continue
                _p10 = _info.get("p10")
                _p90 = _info.get("p90")
                if _p10 is not None and _p90 is not None and (_v < _p10 or _v > _p90):
                    _dev_feats.append(f"{_fn}={_v}(带{_p10:.2f}~{_p90:.2f})")
        if _dev_feats:
            print(f"  带外字段({len(_dev_feats)}): {'; '.join(_dev_feats[:8])}")
        else:
            print("  带外字段: 无（全部落在人类 p10–p90 区间内）")

        # 三方交叉共识终判（含字面层若 Bloom 索引已建）
        _tc = triple_cross_judge(text, baseline=_nar_base)
        print(f"\n  三方交叉共识 verdict: {_tc['verdict']}")
        for _ln, _ly in _tc['layers'].items():
            print(f"    - {_ln}: {_ly['verdict']} (conf={_ly.get('confidence', 0):.2f})")
        print(f"  叙事稀有度(narrative_rarity): {_tc['narrative_rarity']}")
        print(f"  共识说明: {_tc['consensus']}")

        # 追加到报告文件
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 50}\n")
            f.write(f"叙事偏离度报告（本地三交叉·叙事层）\n")
            f.write(f"{'=' * 50}\n")
            f.write(f"叙事层人类度: {_nd['human_score']} / AI度: {_nd['ai_score']}\n")
            f.write(f"叙事偏离度: {_nd['narrative_deviation']}  {_nar_base_note}\n")
            f.write(f"触发/异常特征: {', '.join(_nd['triggered_features']) if _nd['triggered_features'] else '无'}\n")
            f.write(f"带外字段: {'; '.join(_dev_feats) if _dev_feats else '无'}\n")
            f.write(f"\n三方交叉共识 verdict: {_tc['verdict']}\n")
            for _ln, _ly in _tc['layers'].items():
                f.write(f"  - {_ln}: {_ly['verdict']} (conf={_ly.get('confidence', 0):.2f})\n")
            f.write(f"叙事稀有度: {_tc['narrative_rarity']}\n")
            f.write(f"共识说明: {_tc['consensus']}\n")
        print(f"\n  叙事偏离度报告已追加到: {report_path}")

    except ImportError as _ie:
        print(f"  [SKIP] 叙事判别模块未找到（{_ie}），跳过叙事偏离度报告")
        print("  确认 tools/narrative_features.py / tools/local_discriminator.py 存在")
    except Exception as _e:
        print(f"  [ERROR] 叙事偏离度报告异常: {_e}")

    # ================================================================
    # 十二、去 AI 味报告（qiaomu 借鉴增量 · 方向 A + 方向 B）
    # ================================================================
    print("\n" + "=" * 50)
    print("【十二、去 AI 味报告】")
    print("=" * 50)

    _ai = None  # 供第十三节合并弱信号层使用（AI_FLAVOR 关闭或引擎缺失时为 None）

    if not AI_FLAVOR:
        print("  [SKIP] 已通过 --no-ai-flavor 关闭去 AI 味报告")
    else:
        try:
            _sd = os.path.dirname(os.path.abspath(__file__))
            if _sd not in sys.path:
                sys.path.insert(0, _sd)
            from tools.anti_ai_reporter import (
                report_ai_flavor as _report_ai_flavor,
                load_anti_ai_rules as _load_rules,
                load_banned as _load_banned,
            )
            from tools.humanity_scorer import triple_cross_judge as _tc_judge

            _rules = _load_rules()
            _banned = _load_banned()
            _ai = _report_ai_flavor(text, rules=_rules, banned=_banned)

            # ---- 终端输出 ----
            print(f"  抽象词密度: {_ai['abstract']['count']} 次 / 千字 {_ai['abstract']['per_100']}")
            print(f"  场景标记:   {_ai['scene']['count']} 次 / 千字 {_ai['scene']['per_100']}")
            print(f"  钩子标记:   {_ai['hook']['count']} 次 / 千字 {_ai['hook']['per_100']}")
            print(f"  破折号:     {_ai['dash']['count']} 次 / 千字 {_ai['dash']['per_100']}")
            print(f"  AI味正则:   {_ai['aiish']['count']} 次 / 千字 {_ai['aiish']['per_100']}  {_ai['aiish']['breakdown']}")
            print(f"  误导开篇:   {_ai['ambiguous']['count']} 次  {_ai['ambiguous']['breakdown']}")
            print(f"  对话行数:   {_ai['dialogue']['count']} 行（「」识别）")
            print(f"  对话字数占比: {_ai['dialogue_ratio']}（门槛 {_rules['thresholds'].get('dialogue_ratio_min', 0.06)}）")
            if _ai['ambiguous_exempted']:
                print(f"  开篇误导豁免: {_ai['ambiguous_exempt_reason']}")
            print(f"  去AI味告警: {'是' if _ai['ai_flavor_alarm'] else '否'} 级别={_ai['alarm_severity']}")
            if _ai['issues']:
                print(f"  禁用硬项命中({len(_ai['issues'])}):")
                for _it in _ai['issues']:
                    print(f"    - {_it['detail']}")

            # ---- 三交叉终判 verdict 推迟到第十三节：与退化弱信号合并后统一判定 ----
            print(f"  三方交叉共识 verdict: 见第十三节（与退化弱信号合并后统一终判）")

            # ---- 追加到报告文件 ----
            with open(report_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 50}\n")
                f.write(f"十二、去 AI 味报告（qiaomu 借鉴 · 方向 A + 方向 B）\n")
                f.write(f"{'=' * 50}\n")
                f.write(f"抽象词密度: {_ai['abstract']['count']} 次 / 千字 {_ai['abstract']['per_100']}\n")
                f.write(f"场景标记:   {_ai['scene']['count']} 次 / 千字 {_ai['scene']['per_100']}\n")
                f.write(f"钩子标记:   {_ai['hook']['count']} 次 / 千字 {_ai['hook']['per_100']}\n")
                f.write(f"破折号:     {_ai['dash']['count']} 次 / 千字 {_ai['dash']['per_100']}\n")
                f.write(f"AI味正则:   {_ai['aiish']['count']} 次 / 千字 {_ai['aiish']['per_100']}  {_ai['aiish']['breakdown']}\n")
                f.write(f"误导开篇:   {_ai['ambiguous']['count']} 次  {_ai['ambiguous']['breakdown']}\n")
                f.write(f"对话行数:   {_ai['dialogue']['count']} 行（「」识别）\n")
                f.write(f"对话字数占比: {_ai['dialogue_ratio']}（门槛 {_rules['thresholds'].get('dialogue_ratio_min', 0.06)}）\n")
                if _ai['ambiguous_exempted']:
                    f.write(f"开篇误导豁免: {_ai['ambiguous_exempt_reason']}\n")
                f.write(f"去AI味告警: {'是' if _ai['ai_flavor_alarm'] else '否'} 级别={_ai['alarm_severity']}\n")
                f.write(f"告警说明:   {_ai['alarm_detail']}\n")
                if _ai['issues']:
                    f.write(f"\n禁用硬项命中({len(_ai['issues'])}):\n")
                    for _it in _ai['issues']:
                        f.write(f"  - {_it['detail']}\n")
                f.write(f"\n三方交叉共识 verdict: 见第十三节（与退化弱信号合并后统一终判）\n")
            print(f"\n  去 AI 味报告已追加到: {report_path}")

            # ---- 禁用硬项命中并入全局 issues（与第一节已覆盖的3个旧标点去重，其余闭合） ----
            _LEGACY_PUNCT = {"；", "！！！", "？！"}
            for _it in _ai['issues']:
                if _it['type'] == 'punctuation' and _it['value'] in _LEGACY_PUNCT:
                    continue  # 第一节已覆盖，避免重复计入 ❌ 汇总
                issues.append(f"[去AI味·禁用硬项] {_it['detail']}")

        except ImportError as _ie:
            print(f"  [SKIP] 去 AI 味引擎未找到（{_ie}），跳过第十二节")
        except Exception as _e:
            print(f"  [ERROR] 去 AI 味报告异常: {_e}")

    # ================================================================
    # 十三、退化与泄漏检测（核心 IP 质量扩展 · 方向 B）
    # ================================================================
    print("\n" + "=" * 50)
    print("【十三、退化与泄漏检测】")
    print("=" * 50)

    try:
        _sd = os.path.dirname(os.path.abspath(__file__))
        if _sd not in sys.path:
            sys.path.insert(0, _sd)
        from tools.deslop_reporter import (
            report_degeneration,
            load_degeneration_rules,
            merge_ai_flavor_signals,
        )
        from tools.advisory_reporter import report_advisory, load_advisory_rules
        from tools.quality_matrix import report_quality_matrix, load_quality_matrix_rules
        from tools.humanity_scorer import triple_cross_judge as _tc_judge

        _deg_rules = load_degeneration_rules()
        _deg = report_degeneration(text, rules=_deg_rules)
        _adv_rules = load_advisory_rules()
        _adv = report_advisory(text, rules=_adv_rules)

        # ---- 统一创作质量矩阵（方向 D）：复用三源 report，算唯一新增 WARN 源 show_dont_tell ----
        _qm_rules = load_quality_matrix_rules()
        _qm = report_quality_matrix(text, {"ai": _ai, "deg": _deg, "adv": _adv}, rules=_qm_rules)

        # ---- 终端输出 ----
        _leak1 = _deg["engineering_leak"]["tier1"]
        _leak2 = _deg["engineering_leak"]["tier2"]
        if _leak1["hits"]:
            print(f"  工程词泄漏(tier1 硬证据, ISSUE): {len(_leak1['hits'])} 处")
            for _h in _leak1["hits"]:
                print(f"    - 「{_h['term']}」×{_h['count']}")
        else:
            print("  工程词泄漏(tier1): 无")
        if _leak2["hits"]:
            print(f"  工程词泄漏(tier2 叙事层, WARN): {len(_leak2['hits'])} 处")
            for _h in _leak2["hits"][:10]:
                print(f"    - 「{_h['term']}」×{_h['count']}" + ("（落「」内，豁免）" if _h.get('in_quotes') else ""))
        else:
            print("  工程词泄漏(tier2): 无")
        _rep_l = _deg["repeat"]["long_sentence"]
        _rep_a = _deg["repeat"]["adjacent_line"]
        if _rep_l:
            print(f"  长句复读: 「{_rep_l['sentence']}…」×{_rep_l['count']}")
        if _rep_a:
            print(f"  紧邻整行重复: 「{_rep_a['line']}…」×{_rep_a['count']}")
        _trunc = _deg["truncate"]
        if _trunc["violated"]:
            print(f"  截断（末行未以句号/叹号/问号/省略号收尾）: {_trunc['last_line'][:40]}")
        _ph = _deg["placeholder"]["hits"]
        if _ph:
            print(f"  占位符/拒绝语: {len(_ph)} 类命中")
            for _h in _ph:
                print(f"    - {_h['pattern']} ×{_h['count']}" + ("（「」内豁免）" if _h.get('in_quotes') else "")
                      + ("（第六节已管，去重）" if _h.get('managed_by_s6') else ""))
        print(f"  退化与泄漏告警: {'是' if _deg['degeneration_alarm'] else '否'} 级别={_deg['severity']}")

        # ---- 合并弱信号层（qiaomu _ai + 退化 _deg）→ 单一 ai_flavor 注入三交叉终判 ----
        # 红线：verdict 恒为 WARN，confidence 封顶 0.5，数学上不可能翻成 FAIL（与第十二节同构）。
        # 方向 D：质量矩阵的 show_dont_tell（画面感）作为第四路 WARN 弱信号并入终判
        merged_ai_flavor = merge_ai_flavor_signals(_ai, _deg, _adv, _qm)

        _tc = _tc_judge(text, ai_flavor=merged_ai_flavor)
        if merged_ai_flavor["ai_flavor_alarm"]:
            print(f"\n  三方交叉共识 verdict: {_tc['verdict']}（qiaomu + 退化 + advisory 弱信号已合并计入 WARN，未改变终判单点）")
            if 'ai_flavor' in _tc['layers']:
                _alf = _tc['layers']['ai_flavor']
                print(f"    - ai_flavor(弱信号): {_alf['verdict']} (conf={_alf.get('confidence', 0):.2f})")
        else:
            print(f"\n  三方交叉共识 verdict: {_tc['verdict']}（qiaomu + 退化 + advisory 均无弱信号，终判无影响）")

        # ---- 追加到报告文件 ----
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 50}\n")
            f.write(f"十三、退化与泄漏检测（核心 IP 质量扩展 · 方向 B）\n")
            f.write(f"{'=' * 50}\n")
            if _leak1["hits"]:
                f.write(f"工程词泄漏(tier1 硬证据, ISSUE): {len(_leak1['hits'])} 处\n")
                for _h in _leak1["hits"]:
                    f.write(f"  - 「{_h['term']}」×{_h['count']}\n")
            else:
                f.write("工程词泄漏(tier1): 无\n")
            if _leak2["hits"]:
                f.write(f"工程词泄漏(tier2 叙事层, WARN): {len(_leak2['hits'])} 处\n")
                for _h in _leak2["hits"][:10]:
                    f.write(f"  - 「{_h['term']}」×{_h['count']}" + ("（落「」内，豁免）" if _h.get('in_quotes') else "") + "\n")
            else:
                f.write("工程词泄漏(tier2): 无\n")
            if _rep_l:
                f.write(f"长句复读: 「{_rep_l['sentence']}…」×{_rep_l['count']}\n")
            if _rep_a:
                f.write(f"紧邻整行重复: 「{_rep_a['line']}…」×{_rep_a['count']}\n")
            if _trunc["violated"]:
                f.write(f"截断（末行未以句号/叹号/问号/省略号收尾）: {_trunc['last_line'][:40]}\n")
            if _ph:
                f.write(f"占位符/拒绝语: {len(_ph)} 类命中\n")
                for _h in _ph:
                    f.write(f"  - {_h['pattern']} ×{_h['count']}" + ("（「」内豁免）" if _h.get('in_quotes') else "")
                            + ("（第六节已管，去重）" if _h.get('managed_by_s6') else "") + "\n")
            f.write(f"退化与泄漏告警: {'是' if _deg['degeneration_alarm'] else '否'} 级别={_deg['severity']}\n")
            f.write(f"三方交叉共识 verdict: {_tc['verdict']}（qiaomu + 退化 + advisory 弱信号"
                    f"{'已合并计入 WARN，未改变终判单点' if merged_ai_flavor['ai_flavor_alarm'] else '无影响'}）\n")
            if 'ai_flavor' in _tc['layers']:
                _alf = _tc['layers']['ai_flavor']
                f.write(f"  - ai_flavor(弱信号): {_alf['verdict']} (conf={_alf.get('confidence', 0):.2f})\n")
        print(f"\n  退化与泄漏检测报告已追加到: {report_path}")

        # ---- 硬证据（tier1 工程词泄漏 / 占位符拒绝语）并入全局 issues（闭合「prompt 有、QA 无」） ----
        for _it in _deg["issues"]:
            issues.append(f"[退化·泄漏·硬证据] {_it['detail']}")

    except ImportError as _ie:
        print(f"  [SKIP] 退化检测引擎未找到（{_ie}），跳过第十三节")
    except Exception as _e:
        print(f"  [ERROR] 退化与泄漏检测异常: {_e}")

    # 十四、advisory 风格密度告警（核心 IP 质量扩展 · 方向 H）
    # ================================================================
    print("\n" + "=" * 50)
    print("【十四、advisory 风格密度告警】")
    print("=" * 50)

    try:
        _sd2 = os.path.dirname(os.path.abspath(__file__))
        if _sd2 not in sys.path:
            sys.path.insert(0, _sd2)
        _adv_fn = report_advisory
        _load_adv = load_advisory_rules
        _adv_rules2 = _load_adv()
        _adv2 = _adv_fn(text, rules=_adv_rules2)

        if _adv2["advisory_alarm"]:
            print(f"  advisory 弱信号告警: 是  级别={_adv2['severity']}")
            for _k, _v in _adv2["details"].items():
                print(f"    - {_k}: {_v}")
        else:
            print("  advisory 弱信号告警: 否（风格密度正常，无 AI 套路信号）")

        with open(report_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 50}\n")
            f.write("十四、advisory 风格密度告警（核心 IP 质量扩展 · 方向 H，全 WARN 软信号）\n")
            f.write(f"{'=' * 50}\n")
            if _adv2["advisory_alarm"]:
                f.write(f"advisory 弱信号告警: 是  级别={_adv2['severity']}\n")
                for _k, _v in _adv2["details"].items():
                    f.write(f"  - {_k}: {_v}\n")
            else:
                f.write("advisory 弱信号告警: 否（风格密度正常，无 AI 套路信号）\n")
        print(f"\n  advisory 报告已追加到: {report_path}")

    except ImportError as _ie:
        print(f"  [SKIP] advisory 引擎未找到（{_ie}），跳过第十四节")
    except Exception as _e:
        print(f"  [ERROR] advisory 告警异常: {_e}")

    # 十五、统一创作质量矩阵（qiaomu 借鉴增量 · 方向 D）
    # ================================================================
    print("\n" + "=" * 50)
    print("【十五、统一创作质量矩阵】（qiaomu 借鉴 · 方向 D）")
    print("=" * 50)

    try:
        _sd3 = os.path.dirname(os.path.abspath(__file__))
        if _sd3 not in sys.path:
            sys.path.insert(0, _sd3)
        from tools.anti_ai_reporter import report_ai_flavor as _qm_ai, load_anti_ai_rules as _qm_lar, load_banned as _qm_lb
        from tools.deslop_reporter import report_degeneration as _qm_deg, load_degeneration_rules as _qm_ldr
        _qm_adv = report_advisory
        _qm_ladv = load_advisory_rules
        _qm_fn = report_quality_matrix
        _load_qm = load_quality_matrix_rules

        # 自包含重算三源 report（不依赖十二/十三节作用域，结果一致；单篇轻量）
        _qm_ai_r = _qm_ai(text, rules=_qm_lar(), banned=_qm_lb()) if AI_FLAVOR else None
        _qm_deg_r = _qm_deg(text, rules=_qm_ldr())
        _qm_adv_r = _qm_adv(text, rules=_qm_ladv())
        _qm_rules3 = _load_qm()
        _qm3 = _qm_fn(text, {"ai": _qm_ai_r, "deg": _qm_deg_r, "adv": _qm_adv_r}, rules=_qm_rules3)

        print("  维度矩阵（level: OK/WARN/INFO/ISSUE；score 0-1 越高越好）:")
        for _row in _qm3["matrix"]:
            print(f"    - {_row['dim']:<6} | {_row['level']:<5} | score={_row['score']:<5} | {_row['note']}")
        _sdt = _qm3["show_dont_tell"]
        print(f"  画面感(show-don't-tell): score={_sdt['score']}  tell密度={_sdt['tell_density']}/千字  告警={'是' if _sdt['alarm'] else '否'}")
        if _sdt["signals"]:
            print(f"    信号: {'; '.join(_sdt['signals'])}")
        _cmp = _qm3["composite"]
        print(f"  综合质量分: {_cmp['score']}  综合级别={_cmp['level']}  综合告警={'是' if _cmp['alarm'] else '否'}")
        print(f"  （画面感为唯一新增 WARN 弱信号源，已并入第十三节三交叉终判；其余维度为汇总展示，不重复计入终判）")

        # 追加报告文件
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 50}\n")
            f.write("十五、统一创作质量矩阵（qiaomu 借鉴 · 方向 D，仅 WARN 软信号）\n")
            f.write(f"{'=' * 50}\n")
            f.write("维度矩阵（level: OK/WARN/INFO/ISSUE；score 0-1 越高越好）:\n")
            for _row in _qm3["matrix"]:
                f.write(f"  - {_row['dim']} | {_row['level']} | score={_row['score']} | {_row['note']}\n")
            f.write(f"画面感(show-don't-tell): score={_sdt['score']}  tell密度={_sdt['tell_density']}/千字  告警={'是' if _sdt['alarm'] else '否'}\n")
            if _sdt["signals"]:
                f.write(f"  信号: {'; '.join(_sdt['signals'])}\n")
            f.write(f"综合质量分: {_cmp['score']}  综合级别={_cmp['level']}  综合告警={'是' if _cmp['alarm'] else '否'}\n")
            f.write("（画面感为唯一新增 WARN 弱信号源，已并入第十三节三交叉终判；其余维度为汇总展示，不重复计入终判）\n")
        print(f"\n  统一创作质量矩阵已追加到: {report_path}")
    except ImportError as _ie:
        print(f"  [SKIP] 质量矩阵引擎未找到（{_ie}），跳过第十五节")
    except Exception as _e:
        print(f"  [ERROR] 统一创作质量矩阵异常: {_e}")


if __name__ == "__main__":
    main()
