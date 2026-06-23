# -*- coding: utf-8 -*-
"""
check_story.py — 爆款规则检查工具

基于提示词库中定义的黄金三章、爽点密度、人设规则、AI痕迹等规则，
对生成的故事进行全面质量检测。

用法:
    .venv/Scripts/python check_story.py                        # 检查 output/story.txt
    .venv/Scripts/python check_story.py output/story.txt       # 指定文件
    .venv/Scripts/python check_story.py story.txt --genre 系统流 # 体裁适配
"""
import re
import os
import sys

# ── 编码强制 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── 文件路径
STORY_PATH = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.join("output", "story.txt")
# ── 体裁参数解析
GENRE = "default"
for i, a in enumerate(sys.argv):
    if a == "--genre" and i + 1 < len(sys.argv):
        GENRE = sys.argv[i + 1]
        break

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
}
profile = GENRE_PROFILES.get(GENRE, GENRE_PROFILES["default"])
climax_keywords = profile["climax_keywords"]
emotion_keywords = profile["emotion_keywords"]
ch1_keywords = profile["ch1_keywords"]

if not os.path.exists(STORY_PATH):
    print(f"[ERROR] 文件不存在: {STORY_PATH}")
    sys.exit(1)

with open(STORY_PATH, "r", encoding="utf-8") as f:
    text = f.read()

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
banned_punctuation = ["；", "！！！", "？！"]  # 「」是标准中文引号，不禁用
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

# 思维标记（降AI检测关键指标）
thinking_markers = ["心想", "意识到", "感到", "觉得", "认为", "明白"]
total_thinking = 0
for m in thinking_markers:
    n = text.count(m)
    total_thinking += n
    if n > 0:
        warns.append(f"[思维标记]「{m}」{n}处")
if total_thinking == 0:
    passes.append("[OK] 无思维标记，AI特征低")
elif total_thinking > 5:
    issues.append(f"[AI痕迹] 思维标记共{total_thinking}处，超过5处警戒线")

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

    # 金手指/系统关键词检测（第一章应出现）
    ch1_found = any(k in chapters[0] for k in ch1_keywords)
    if ch1_found:
        passes.append("[OK] 第一章检测到金手指/系统设定，符合黄金三章首章规则")
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

dialogue_lines = len(re.findall(r'[""「」][^"「」""]{1,50}[""「」]', text))
dialogue_pat = len(re.findall(r'[。！？\n][^。！？\n]*?[说问道喊叫嚷吧吗呢啊]', text))
dialogue_total = dialogue_lines + dialogue_pat
if zh > 0:
    dialogue_ratio = dialogue_total / (zh / 100)  # 每100字对话次数
    if dialogue_ratio < 1.5:
        warns.append("[对话密度] 对话密度{:.1f}/100字，低于1.5，番茄风格建议提高对话".format(dialogue_ratio))
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

# ── 保存检查报告
report_path = STORY_PATH.replace(".txt", "_check_report.txt")
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
