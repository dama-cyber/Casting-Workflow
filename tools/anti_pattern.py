# -*- coding: utf-8 -*-
"""
anti_pattern.py - 反模式生成引擎

核心原理: 指纹互消的对偶系统
  互消: 5源文本 -> 提取公因子F -> 消除F -> 保留差异 -> 最小化相似度
  反模式: 5源文本 -> 提取公因子F -> 反转F -> 注入反因子 -> 最大化预期违背(爽感)

公因子 = 类型公式 = 读者预期
反转公因子 = 预期违背 = 爽感本质

5种反模式操作器:
  1. structure_invert  - 结构反转器: 三幕式 -> 中点爆炸/倒序/环形
  2. emotion_polarize  - 情绪极化器: 渐强式 -> 断崖式(长蓄力+瞬时崩溃)
  3. causality_invert  - 因果反转器: 线性因果 -> 倒因果/量子因果
  4. character_subvert - 角色颠覆器: 成长弧 -> 降级弧/突变弧
  5. info_bomb         - 信息炸弹器: 均匀分布 -> 黑洞+爆炸交替

用法:
    from tools.anti_pattern import AntiPatternEngine
    engine = AntiPatternEngine(recipe="中度反模式")
    anti_context = engine.build_anti_prompt(files_info, stage="正文")
    ei_score = engine.calculate_EI(story_text)
"""

import os
import re
import json
from collections import Counter

# ── 配置加载
_HERE = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_HERE, "..", "config", "anti_pattern.json")


def _load_config():
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


CONFIG = _load_config()


# ============================================================
# 1. 公因子反转器 - 从指纹中提取公因子,生成反面
# ============================================================

COMMON_FACTOR_CATALOG = CONFIG.get("common_factor_catalog", {}).get("factors", {})


def extract_common_factors(files_info):
    """
    从5源指纹中提取公因子(类型公式),并生成对应的反因子。
    v2.0: 集成jieba词频分析，从关键词匹配升级到NLP主题词提取。

    :param files_info: [{name, fp}, ...] 源文指纹列表
    :return: {"common": {...}, "anti": {...}}
    """
    factors = {}

    # v2.0: jieba词频分析 — 提取跨源文共享的高频主题词
    shared_themes = _extract_shared_themes(files_info)

    # 1.1 死亡方式公因子 (v2.0: 融合词频分析)
    death_patterns = _detect_pattern(files_info, "death", keywords=["死", "杀", "亡", "毙"])
    death_themes = [w for w in shared_themes if any(k in w for k in ["死", "杀", "亡", "毙", "丧"])]
    if death_themes:
        death_patterns = f"高频词: {', '.join(death_themes[:3])} -> {death_patterns}"
    factors["death"] = {
        "common": death_patterns,
        "anti": _invert_death(death_patterns),
    }

    # 1.2 重生/穿越触发公因子
    rebirth_patterns = _detect_pattern(files_info, "rebirth", keywords=["重生", "穿越", "回到", "醒来"])
    rebirth_themes = [w for w in shared_themes if any(k in w for k in ["重生", "穿越", "前世", "回到", "醒来"])]
    if rebirth_themes:
        rebirth_patterns = f"高频词: {', '.join(rebirth_themes[:3])} -> {rebirth_patterns}"
    factors["rebirth"] = {
        "common": rebirth_patterns,
        "anti": _invert_rebirth(rebirth_patterns),
    }

    # 1.3 背景设定公因子 (v2.0: 用词频分析增强)
    setting_patterns = _detect_pattern(files_info, "setting", keywords=["朝代", "都市", "古代", "现代", "末世", "修仙"])
    setting_themes = [w for w in shared_themes if any(k in w for k in ["朝代", "都市", "古代", "现代", "末世", "修仙", "宫", "府", "门", "派"])]
    if setting_themes:
        setting_patterns = f"高频词: {', '.join(setting_themes[:3])} -> {setting_patterns}"
    factors["setting"] = {
        "common": setting_patterns,
        "anti": _invert_setting(setting_patterns),
    }

    # 1.4 背叛者模式公因子
    betrayal_patterns = _detect_pattern(files_info, "betrayal", keywords=["背叛", "出卖", "欺骗", "利用"])
    betrayal_themes = [w for w in shared_themes if any(k in w for k in ["背叛", "出卖", "欺骗", "利用", "算计"])]
    if betrayal_themes:
        betrayal_patterns = f"高频词: {', '.join(betrayal_themes[:3])} -> {betrayal_patterns}"
    factors["betrayal"] = {
        "common": betrayal_patterns,
        "anti": COMMON_FACTOR_CATALOG.get("betrayal_pattern", {}).get("anti", "主角是背叛者->被反噬->在背叛中觉醒->反向救赎"),
    }

    # 1.5 复仇手段公因子
    revenge_patterns = _detect_pattern(files_info, "revenge", keywords=["复仇", "报仇", "报复", "还回去"])
    revenge_themes = [w for w in shared_themes if any(k in w for k in ["复仇", "报仇", "报复", "还回去", "算账"])]
    if revenge_themes:
        revenge_patterns = f"高频词: {', '.join(revenge_themes[:3])} -> {revenge_patterns}"
    factors["revenge"] = {
        "common": revenge_patterns,
        "anti": COMMON_FACTOR_CATALOG.get("revenge_pattern", {}).get("anti", "不复仇,而是反向救赎/以德报怨后反转"),
    }

    # 1.6 叙事结构公因子
    factors["narrative_structure"] = {
        "common": COMMON_FACTOR_CATALOG.get("narrative_structure", {}).get(
            "common", "三幕式: 平静->冲突->高潮->解决"
        ),
        "anti": COMMON_FACTOR_CATALOG.get("narrative_structure", {}).get(
            "anti", "中点爆炸: 从高潮开始->倒叙->二次反转->终极真相"
        ),
    }

    # 1.7 角色弧光公因子
    factors["character_arc"] = {
        "common": COMMON_FACTOR_CATALOG.get("character_arc", {}).get(
            "common", "成长弧: 弱->遇机->变强->碾压->登顶"
        ),
        "anti": COMMON_FACTOR_CATALOG.get("character_arc", {}).get(
            "anti", "降级弧: 强->遭创->坠落->低谷觉醒->以弱胜强"
        ),
    }

    # 1.8 情绪节奏公因子
    factors["emotion_rhythm"] = {
        "common": COMMON_FACTOR_CATALOG.get("emotion_rhythm", {}).get(
            "common", "渐强式: 平淡->紧张->爆发->余韵"
        ),
        "anti": COMMON_FACTOR_CATALOG.get("emotion_rhythm", {}).get(
            "anti", "断崖式: 蓄力(20句)->断崖(2句)->寂静(3句)->终极爆发"
        ),
    }

    # 1.9 因果链公因子
    factors["causality_chain"] = {
        "common": COMMON_FACTOR_CATALOG.get("causality_chain", {}).get(
            "common", "线性因果: A->B->C->D"
        ),
        "anti": COMMON_FACTOR_CATALOG.get("causality_chain", {}).get(
            "anti", "倒因果: D先现->回溯C->揭示B->颠覆A"
        ),
    }

    # 1.10 结局类型公因子
    factors["ending"] = {
        "common": COMMON_FACTOR_CATALOG.get("ending_type", {}).get(
            "common", "大团圆/碾压式胜利"
        ),
        "anti": COMMON_FACTOR_CATALOG.get("ending_type", {}).get(
            "anti", "惨胜/代价式胜利/胜利中的毁灭"
        ),
    }

    return factors


def _detect_pattern(files_info, name, keywords):
    """从指纹opening_50_lines中检测关键词出现频率"""
    hits = []
    for fi in files_info:
        opening = fi["fp"].get("opening_50_lines", "")
        for kw in keywords:
            if kw in opening:
                hits.append(kw)
                break
    if not hits:
        return f"未检测到明显{name}模式"
    freq = Counter(hits).most_common(1)[0]
    return f"{freq[0]}类({freq[1]}/5篇共有)"


# v2.0: jieba词频分析 — 跨源文共享主题词提取
_jieba_available = False
try:
    import jieba
    list(jieba.cut("初始化"))
    _jieba_available = True
except ImportError:
    pass

# 停用词表 (网文场景)
_STOP_WORDS = {
    "一个", "没有", "自己", "什么", "他们", "我们", "不是", "这个", "那个",
    "已经", "知道", "可以", "起来", "现在", "还是", "如果", "因为", "所以",
    "但是", "然而", "不过", "只是", "就是", "不会", "不能", "不要", "这样",
    "那样", "怎么", "为什么", "时候", "地方", "东西", "事情", "样子",
    "过来", "过去", "出来", "进去", "上去", "下去", "回来", "回去",
    "一下", "一些", "一点", "一面", "一边", "一种", "一切", "所有", "任何",
    "非常", "十分", "特别", "尤其", "格外", "极其", "极为", "异常", "分外",
    "忽然", "突然", "猛然", "顿时", "霎时", "刹那", "瞬间", "立刻", "马上",
    "于是", "因此", "虽然", "尽管", "即使", "哪怕", "无论", "不管",
    "只有", "只要", "除非", "除了", "既然", "倘若", "要是", "万一",
    "难道", "岂不", "岂非", "并非", "并不", "不曾", "无非",
    "的话", "似的", "一样", "一般", "般的",
}


def _extract_shared_themes(files_info, top_n=15):
    """
    v2.0: 用jieba对全源文做词频分析，提取跨源文共享的高频主题词。
    
    算法:
    1. 对每篇源文的opening_50_lines做jieba分词
    2. 统计每篇的top词频
    3. 取在>=3篇源文中都出现的词，按跨源频率排序
    
    :param files_info: [{name, fp}, ...]
    :param top_n: 返回前N个共享主题词
    :return: ["词1", "词2", ...]
    """
    if not _jieba_available or len(files_info) < 2:
        return []
    
    # 每篇源文的词频统计
    per_file_words = []
    for fi in files_info:
        opening = fi["fp"].get("opening_50_lines", "")
        if not opening:
            continue
        # 分词，保留长度>=2的非停用词
        words = [w for w in jieba.cut(opening) if len(w) >= 2 and w not in _STOP_WORDS]
        per_file_words.append(Counter(words))
    
    if len(per_file_words) < 2:
        return []
    
    # 统计跨源出现次数: 一个词在几篇源文中出现
    cross_freq = Counter()
    for wc in per_file_words:
        for word in wc:
            cross_freq[word] += 1
    
    # 筛选: 至少在3篇(或半数)源文中出现
    min_files = max(3, len(per_file_words) // 2)
    shared = [(word, count) for word, count in cross_freq.items() if count >= min_files]
    
    # 按跨源频率排序，同频率按总词频排序
    total_freq = Counter()
    for wc in per_file_words:
        total_freq += wc
    
    shared.sort(key=lambda x: (x[1], total_freq[x[0]]), reverse=True)
    
    return [word for word, _ in shared[:top_n]]


def _invert_death(pattern_str):
    inversions = {
        "死": "自然死亡时微笑(反转:非暴力->安详)",
        "杀": "被杀者反而笑了(反转:被动->主动接受)",
        "亡": "假死后以新身份回归(反转:终局->起点)",
        "毙": "被击毙者留下关键遗物改变全局(反转:终结->催化)",
    }
    for k, v in inversions.items():
        if k in pattern_str:
            return v
    return "非死亡结局,以活着的代价替代死亡"


def _invert_rebirth(pattern_str):
    inversions = {
        "重生": "不重生,而是前世的记忆反向流入现世(反转:时空置换->信息渗透)",
        "穿越": "不穿越,而是两个时空的人共享一个身体(反转:单向->双向)",
        "回到": "不回到过去,而是未来的人来到现在(反转:回溯->前瞻)",
        "醒来": "不是醒来,而是发现之前的清醒才是梦(反转:现实->幻象)",
    }
    for k, v in inversions.items():
        if k in pattern_str:
            return v
    return "无重生触发,以连续视角替代时空跳跃"


def _invert_setting(pattern_str):
    inversions = {
        "都市": "都市中的古典江湖(现代+古风碰撞)",
        "古代": "古代中的未来遗迹(古风+科幻碰撞)",
        "现代": "现代中的折叠时空(日常+超现实)",
        "末世": "末世中的乌托邦孤岛(毁灭+建构)",
        "修仙": "修仙世界的科学革命(玄幻+理性)",
    }
    for k, v in inversions.items():
        if k in pattern_str:
            return v
    return "混合设定:两种不兼容的世界观叠加"


# ============================================================
# 2. 五种反模式操作器
# ============================================================

class StructureInverter:
    """结构反转器: 三幕式 -> 中点爆炸/倒序/环形/碎片/平行时间线"""

    MODES = {
        "reverse_chronology": "倒序叙事: 从结局开始,逆向回溯,每一步都是揭示",
        "circular": "环形叙事: 开头即结尾,中间是循环,最后一句话改变整个故事的含义",
        "fragmented": "碎片叙事: 打碎时间线,用3-4条平行线索交叉推进,最后汇聚",
        "parallel_timeline": "平行时间线: 两条时间线并行,在关键节点交叉反转",
        "midpoint_explosion": "中点爆炸: 前50%看似正常类型文->中点突然反转->后50%完全不同",
    }

    @staticmethod
    def generate_prompt(intensity, mode=None):
        mode = mode or "midpoint_explosion"
        mode_desc = StructureInverter.MODES.get(mode, StructureInverter.MODES["midpoint_explosion"])

        if intensity < 0.3:
            return f"【轻度结构反转】在传统三幕式的基础上,将高潮点提前10-15%,让读者提前进入紧张状态。其余结构保持类型惯例。\n模式: {mode_desc}"

        elif intensity < 0.5:
            return f"【中度结构反转】采用{mode_desc}。前30%按类型惯例铺垫,中点突然打破框架,后70%以全新结构推进。读者预期被颠覆但叙事仍然连贯。\n关键要求: 反转点必须在读者最确信走向的时刻发生。"

        elif intensity < 0.8:
            return f"【重度结构反转】完全采用{mode_desc}。抛弃三幕式,从第一段开始就打破线性叙事。每个章节的开头都应该是读者以为的'结局'。\n关键要求: 碎片之间必须有隐藏的逻辑线,在最后1/3处全部汇聚,产生认知爆炸。"

        else:
            return f"【极限结构反转】{mode_desc}。同时叠加: (1)叙事视角在每章切换(2)时间线非线性跳跃(3)每章结尾都是下一章的伏笔但读者无法预判。\n关键要求: 最终汇聚时,所有碎片必须在同一段落内完成闭环。读者必须重读才能理解全文。"


class EmotionPolarizer:
    """情绪极化器: 渐强式 -> 断崖式(长蓄力+瞬时崩溃+反弹)"""

    @staticmethod
    def generate_prompt(intensity):
        if intensity < 0.3:
            return "【轻度情绪极化】在常规情绪渐强的基础上,在高潮前插入一个3-5句的情绪低谷(沉默/空白/日常对话),然后再爆发。落差制造爽感。"

        elif intensity < 0.5:
            return "【中度情绪极化】采用断崖式情绪节奏:\n1. 蓄力段(15-20句): 情绪持续上升,读者以为即将爆发\n2. 断崖(1-2句): 突然情绪归零,角色说了一句完全无关的话/做了一个日常动作\n3. 寂静(2-3句): 沉默,环境描写,时间停滞感\n4. 终极爆发(3-5句): 比蓄力预期更猛烈的爆发\n每个情绪弧至少使用一次断崖结构。"

        elif intensity < 0.8:
            return "【重度情绪极化】全篇情绪节奏采用'蓄力-断崖-寂静-爆发'循环,至少3次:\n1. 第一次断崖: 在读者最紧张时突然平静(角色笑了/说了句日常话)\n2. 第二次断崖: 在读者以为要爆发时再次延迟(插入完全无关的回忆)\n3. 第三次断崖: 终极爆发时,情绪方向与预期相反(该愤怒时笑了/该悲伤时兴奋)\n关键: 每次断崖都必须有后续逻辑解释,不是随机而是角色内心深处的真实反应。"

        else:
            return "【极限情绪极化】情绪完全非线性:\n1. 每段情绪方向与上一段相反(紧张->平静->更紧张->寂静->爆发->空虚)\n2. 关键场景使用'情绪真空'技巧: 在最该有情绪的时刻,角色完全无情绪(白描事实),由读者自己填充情绪\n3. 结尾情绪必须是全篇唯一一次'正常'情绪,但这个正常本身就是最大的反转\n4. 禁止使用任何情绪描写词(不/愤怒/悲伤/开心),只用动作和对话传达"


class CausalityInverter:
    """因果反转器: 线性因果 -> 倒因果/量子因果/反因果/嵌套揭示"""

    MODES = {
        "effect_first": "结果先现: 先展示结果(一个震撼场景),再花整章回溯原因,最后揭示原因比结果更震撼",
        "quantum_cause": "量子因果: 同一事件有两个互斥的原因,都成立,读者无法确定哪个是真的,直到最后一句话锁定",
        "anti_cause": "反因果: 角色的行动不是为了达成目的,而是为了阻止一个已经发生的结果(时间逆流感)",
        "nested_reveal": "嵌套揭示: 揭示A->揭示B(颠覆A)->揭示C(颠覆B)->终极揭示(颠覆一切)",
    }

    @staticmethod
    def generate_prompt(intensity, mode=None):
        mode = mode or "effect_first"
        mode_desc = CausalityInverter.MODES.get(mode, CausalityInverter.MODES["effect_first"])

        if intensity < 0.3:
            return f"【轻度因果反转】在关键情节点使用一次'结果先现': 先展示一个震撼结果,然后用2-3段回溯原因。其余保持线性因果。\n模式: {mode_desc}"

        elif intensity < 0.5:
            return f"【中度因果反转】采用{mode_desc}。\n在3个关键节点使用因果倒置:\n1. 开篇: 展示一个结果的碎片(不完整),引起好奇\n2. 中段: 揭示原因,但原因本身又是一个更大的结果的碎片\n3. 结尾: 终极原因揭示,颠覆读者对整个故事的理解\n关键: 每次揭示都必须让之前的内容产生新含义。"

        elif intensity < 0.8:
            return f"【重度因果反转】全篇采用{mode_desc}。\n1. 打碎所有因果链,按'结果->碎片->碎片->原因->新结果'排列\n2. 每个章节的第一句话都是上一章的'结果'\n3. 读者必须自己拼装因果链\n4. 在3/4处给出一个看似完整的因果解释\n5. 最后1/4颠覆这个解释,给出真正的因果\n关键: 假因果链必须足够自洽,让读者相信,然后才颠覆。"

        else:
            return f"【极限因果反转】{mode_desc}。\n叠加三层:\n1. 表层因果: 读者能直接看到的线性因果(假因果)\n2. 深层因果: 通过伏笔暗示的真因果(读者需要拼装)\n3. 元因果: 最后一句话揭示的,颠覆整个故事性质的因果\n关键: 三层因果必须互相矛盾但各自自洽。最终读者会发现: 故事的真相比所有版本都更震撼。"


class CharacterSubverter:
    """角色颠覆器: 成长弧 -> 降级弧/突变弧/双面弧"""

    @staticmethod
    def generate_prompt(intensity, collapse_point=None):
        collapse = collapse_point or "climax"

        if intensity < 0.3:
            return f"【轻度角色颠覆】在{collapse}处,主角的一个人设标签暂时失效(如:杀伐果断->短暂犹豫),造成后果后重新硬化。让角色有'人味'。"

        elif intensity < 0.5:
            return f"【中度角色颠覆】采用降级弧:\n1. 前半段: 主角是强者的形象,碾压一切\n2. {collapse}处: 人设标签全部崩溃(不是弱点暴露,而是价值观动摇)\n3. 后半段: 以'弱化版'自己重新应对,最终以弱胜强\n关键: 崩溃必须有深层原因(不是简单的失误),且崩溃后的角色比崩溃前更有魅力。"

        elif intensity < 0.8:
            return f"【重度角色颠覆】采用双面弧:\n1. 主角有两个互相矛盾的人设标签(如:杀伐果断+圣母心)\n2. 两个标签在不同场景交替主导,读者无法预判哪个会出现\n3. 在{collapse}处,两个标签同时失效,暴露第三个隐藏标签\n4. 结尾: 第三个标签成为主角的真正定义\n关键: 三个标签必须都有合理性,让读者事后回想时觉得'早就该想到'。\n额外: 配角也至少有一人经历人设反转,且反转方向与主角相反。"

        else:
            return f"【极限角色颠覆】主角身份本身是谜:\n1. 全文读者以为主角是A,实际上主角是B\n2. 主角的所有行为在A视角下合理,在B视角下也合理,但含义完全不同\n3. 在{collapse}处,主角主动暴露B身份,但暴露方式是'做出A绝对不会做的事'\n4. 结尾: 读者重读时发现,第一句话就暗示了B身份\n关键: A和B不是简单的'伪装',而是主角内心两个真实存在的面。配角中至少一人知道B身份,但全程不说。"


class InfoBomber:
    """信息炸弹器: 均匀分布 -> 黑洞+爆炸交替"""

    @staticmethod
    def generate_prompt(intensity):
        if intensity < 0.3:
            return "【轻度信息炸弹】在常规均匀信息分布中,插入1-2个'信息密集段'(一段内释放3个以上新信息),紧跟一个'信息静默段'(纯环境描写/无新信息)。制造信息节奏感。"

        elif intensity < 0.5:
            return "【中度信息炸弹】采用'黑洞-爆炸'交替结构:\n1. 信息黑洞(占篇幅30%): 长段描写,几乎无新信息,只有氛围/情绪/环境。读者以为无聊。\n2. 信息爆炸(占篇幅50%): 突然在短段内密集释放关键信息(身份揭示/阴谋暴露/关系翻转),每句话都是新信息\n3. 信息余震(占篇幅20%): 爆炸后的碎片整理,读者消化\n关键: 黑洞必须让读者放松警惕,爆炸才能产生最大冲击。"

        elif intensity < 0.8:
            return "【重度信息炸弹】全篇采用'黑洞-爆炸-黑洞-爆炸-终极爆炸'节奏:\n1. 第一黑洞(15%): 世界观铺垫,信息稀疏\n2. 第一爆炸(10%): 抛出核心悬念\n3. 第二黑洞(15%): 角色日常,信息稀疏,读者消化\n4. 第二爆炸(20%): 大量信息同时释放,关系网/阴谋/真相交织\n5. 第三黑洞(10%): 沉默,只有主角的独白\n6. 终极爆炸(30%): 所有线索汇聚,信息量是前两次爆炸的总和\n关键: 每次爆炸的信息必须有内在关联,不是随机堆砌。"

        else:
            return "【极限信息炸弹】信息密度极化到极致:\n1. 全篇70%的篇幅是信息黑洞: 极慢节奏,大量环境描写,角色闲聊,看似无意义的细节\n2. 30%的篇幅是信息爆炸: 每一句话都改变故事走向,每一段都颠覆前文\n3. 爆炸段之间的黑洞越来越短,节奏越来越快\n4. 最后一段(全文1%)的信息密度=全篇总信息量的50%\n关键: 黑洞中的'无意义细节'必须在爆炸中被回收,成为关键线索。读者重读时发现: 没有一个字是废的。"


# ============================================================
# 3. 爽感指数 EI (Excitement Index) 评估体系
# ============================================================

# 情绪词典 (简化版,可扩展)
EMOTION_LEXICON = {
    "high_positive": ["狂喜", "癫狂", "炽热", "爆裂", "碾压", "撕裂", "焚毁", "崩塌", "暴怒", "疯魔"],
    "high_negative": ["绝望", "崩溃", "窒息", "坠落", "深渊", "毁灭", "碎裂", "崩坏", "癫"],
    "mid_positive": ["兴奋", "激动", "畅快", "霸气", "强势", "嚣张", "不屑", "冷笑"],
    "mid_negative": ["愤怒", "恐惧", "痛苦", "压抑", "心寒", "刺骨"],
    "low": ["平静", "沉默", "安静", "淡然", "冷漠", "空白", "虚无"],
}

# 预期违背关键词
SUBVERSION_KEYWORDS = [
    "但是", "然而", "可是", "不料", "谁知", "偏偏", "竟然", "居然",
    "没想到", "万万没想到", "不可能", "怎么会", "不对",
    "反转", "颠覆", "真相", "原来", "实际上", "事实是",
]

# 冲突关键词
CONFLICT_KEYWORDS = [
    "打", "杀", "冲", "撞", "撕裂", "碾碎", "暴怒", "怒吼",
    "对抗", "冲突", "对峙", "交锋", "碰撞", "爆发",
    "威胁", "逼迫", "镇压", "反叛", "背叛", "决裂",
]


# ============================================================
# P1/P5 爽感维度校准常量（P1-2 修复：消除连接词密度虚高）
# ------------------------------------------------------------
# 来源：data/_quality_baseline.json 对 11030 篇朱雀判 100% 人类语料的流式扫描
#   conjunction_density: p10=0.0 / p50=0.0 / p90=11.17 / mean=3.54
# 结论：中文广义连接词本就稀（p50=0，半数作品密度≈0），用连接词密度度量
#       "爽感"是错误前提；原 P1/P5 直计"但是/然而/所以/这就是"等高频连词，
#       导致任何中文文本 EI 几乎恒为"极致爽文"（系统性虚高）。
# 修复：P1/P5 剔除纯转折/因果连词，仅保留强信号反转/回收词，并用以下
#       保守满分锚做相对归一化（强信号词密度约为广义连接词的 1/3~1/4，
#       首次启发标定，非 corpus 直统；后续可专项扫描 STRONG_SUBVERSION
#       密度做精确标定）。
# ============================================================
_PURE_CONJ = ("但是", "然而", "可是")          # 纯转折连词，不代表爽点
_PURE_CAUSAL = ("所以", "这就是")               # 纯因果连词，不代表回收
_CONJ_P90 = 11.17                                # 广义连接词密度 p90 (/千字)
_STRONG_SUBVERSION_P90 = _CONJ_P90 / 3.0         # ≈ 3.72 /千字 满分锚
_STRONG_PAYOFF_P90 = _CONJ_P90 / 4.0             # ≈ 2.79 /千字 满分锚
_STRONG_SUBVERSION = [w for w in SUBVERSION_KEYWORDS if w not in _PURE_CONJ]
_STRONG_PAYOFF = [w for w in (
    "原来", "实际上", "事实是", "真相", "难怪", "所以", "这就是", "正是", "果然"
) if w not in _PURE_CAUSAL]


def calculate_EI(text):
    """
    计算爽感指数 EI (Excitement Index)

    EI = (P1*0.25 + P2*0.20 + P3*0.25 + P4*0.15 + P5*0.15) / 10 * 100

    P1: 预期违背密度 (25%) - 每1000字反转/颠覆事件数
    P2: 节奏加速度 (20%) - 段落长度变化率
    P3: 情绪极差 (25%) - 情绪最高点与最低点差值
    P4: 冲突烈度 (15%) - 冲突关键词密度+冲突场景占比
    P5: 回收密度 (15%) - 伏笔回收频率
    """
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    if zh == 0:
        return {"EI": 0, "details": {"error": "无中文内容"}}

    # P1: 预期违背密度（仅强信号反转词，剔除纯转折连词"但是/然而/可是"——
    #     纯连词不代表爽点，且中文连接词本就稀(p50=0, 见 data/_quality_baseline.json
    #     conjunction_density)。改用相对 corpus 基线(p90 推导的保守满分锚)归一化，
    #     消除"任何中文文本 EI 恒极致爽感"的系统性虚高。
    subversion_count = sum(text.count(kw) for kw in SUBVERSION_KEYWORDS)  # 全量，供展示
    strong_subv = sum(text.count(kw) for kw in _STRONG_SUBVERSION)
    p1_dens = strong_subv / (zh / 1000)
    p1 = min(p1_dens / _STRONG_SUBVERSION_P90 * 10, 10)

    # P2: 节奏加速度
    paragraphs = [p.strip() for p in text.split("\n") if p.strip() and len(p.strip()) > 5]
    rhythm_variability = 0
    if len(paragraphs) > 1:
        para_lens = [len(p) for p in paragraphs]
        deltas = [abs(para_lens[i] - para_lens[i + 1]) for i in range(len(para_lens) - 1)]
        avg_delta = sum(deltas) / len(deltas)
        avg_len = sum(para_lens) / len(para_lens)
        rhythm_variability = avg_delta / avg_len if avg_len > 0 else 0
        p2 = min(rhythm_variability * 15, 10)  # 归一化,理想变化率>0.6
    else:
        p2 = 0

    # P3: 情绪极差
    sentences = [s.strip() for s in re.split(r"[。！？\n]", text) if s.strip()]
    emotion_scores = []
    for sent in sentences:
        score = 0
        for level, words in EMOTION_LEXICON.items():
            weight = {"high_positive": 10, "high_negative": 9, "mid_positive": 6, "mid_negative": 5, "low": 2}[level]
            for w in words:
                if w in sent:
                    score = max(score, weight)
        emotion_scores.append(score)
    if emotion_scores:
        import statistics as _stats
        # 情绪极差：原 max-min 因 min 恒≈0（多数中性句 score=0）而几乎恒满 10，
        # 改为「情绪波动性」(总体标准差) 反映真实起伏（首次标定，精确阈值待 corpus 基线 qiaomu-E）
        max_e = max(emotion_scores)
        min_e = min(emotion_scores)
        std_e = _stats.pstdev(emotion_scores) if len(emotion_scores) > 1 else 0.0
        p3 = min(std_e * 2.5, 10)
    else:
        p3 = 0

    # P4: 冲突烈度
    conflict_count = sum(text.count(kw) for kw in CONFLICT_KEYWORDS)
    conflict_density = conflict_count / (zh / 1000)
    p4 = min(conflict_density * 1.5, 10)

    # P5: 回收密度（仅强信号回收词，剔除纯因果连词"所以/这就是"；
    #     相对 corpus 基线(p90 推导的保守满分锚)归一化，避免虚高）
    PAYOFF_KEYWORDS = ["原来", "实际上", "事实是", "真相", "难怪", "所以", "这就是", "正是", "果然"]
    payoff_count = sum(text.count(kw) for kw in PAYOFF_KEYWORDS)  # 全量，供展示
    strong_payoff = sum(text.count(kw) for kw in _STRONG_PAYOFF)
    p5_dens = strong_payoff / (zh / 1000)
    p5 = min(p5_dens / _STRONG_PAYOFF_P90 * 10, 10)

    # 综合EI
    ei_raw = p1 * 0.25 + p2 * 0.20 + p3 * 0.25 + p4 * 0.15 + p5 * 0.15
    ei = round(ei_raw / 10 * 100, 1)

    # 等级
    if ei <= 20:
        grade = "平淡如水"
    elif ei <= 40:
        grade = "略有起伏"
    elif ei <= 60:
        grade = "爽文及格"
    elif ei <= 80:
        grade = "爆款爽文"
    else:
        grade = "极致爽感"

    return {
        "EI": ei,
        "grade": grade,
        "details": {
            "P1_预期违背密度": round(p1, 1),
            "P2_节奏加速度": round(p2, 1),
            "P3_情绪极差": round(p3, 1),
            "P4_冲突烈度": round(p4, 1),
            "P5_回收密度": round(p5, 1),
            "中文字数": zh,
            "预期违背次数": subversion_count,
            "冲突关键词次数": conflict_count,
            "回收标记次数": payoff_count,
            "段落变化率": round(rhythm_variability, 3) if paragraphs else 0,
        }
    }


# ============================================================
# 4. 无钢印模式发现 — 不预设维度，从源文直接提取共享叙事 DNA
# ============================================================

def _discover_narrative_patterns(opened_texts, all_names, min_share=2):
    """从多篇源文中发现实际重复的叙事模式，不预设任何类型标签"""
    patterns = []
    combined = " ".join(opened_texts)
    words = list(jieba.cut(combined))
    word_freq = Counter(w for w in words if len(w) >= 2)
    common_names = Counter(n for n in all_names if n and len(n) >= 2)
    ranked_names = [n for n, _ in common_names.most_common(5)]

    if ranked_names:
        patterns.append({
            "label": "重复角色类型",
            "description": f"以下角色名在多篇源文中高频出现: {', '.join(ranked_names[:5])}",
            "anti": "让这些名字出现在完全不同的语境里,或者反过来——让他们不是主角,只是被主角路过的路人。"
        })

    action_kw = ["复仇", "重生", "攻略", "碾压", "打脸", "觉醒", "绑定", "穿越",
                 "离开", "抛弃", "回头", "跪下", "求饶", "陷害", "背叛", "翻盘"]
    found_actions = [kw for kw in action_kw if kw in combined]
    if found_actions:
        top_actions = Counter(found_actions).most_common(4)
        patterns.append({
            "label": "重复行为模式",
            "description": f"共享动作词: {', '.join([a for a,_ in top_actions])}",
            "anti": "主角不做这些动作。或者做了但结果完全相反——复仇变成和解,打脸变成被打,觉醒变成接受无知。"
        })

    relation_kw = ["夫君", "丈夫", "妻子", "母亲", "父亲", "闺蜜", "兄弟", "兄妹",
                   "青梅竹马", "白月光", "替身", "主母", "姨娘", "小妾", "王爷", "太子"]
    found_relations = [kw for kw in relation_kw if kw in combined]
    if found_relations:
        top_rel = Counter(found_relations).most_common(3)
        patterns.append({
            "label": "重复关系结构",
            "description": f"共享关系: {', '.join([r for r,_ in top_rel])}",
            "anti": "把这些关系剥掉。让故事里没有丈夫/妻子/母亲/父亲这些标签。只有人和人。关系不由血缘或婚约定义,由此刻的距离定义。"
        })

    setting_kw = ["王府", "侯府", "京城", "校园", "职场", "宫", "村", "边关",
                  "现代", "古代", "末世", "重生后"]
    found_settings = [kw for kw in setting_kw if kw in combined]
    if found_settings:
        top_set = Counter(found_settings).most_common(1)
        patterns.append({
            "label": "背景设定",
            "description": f"共享场景: {top_set[0][0] if top_set else '不明'}",
            "anti": "换掉。不是换个朝代,是换一种空间逻辑。如果共享场景是京城,你就在渔船上写。如果共享场景是校园,你就在菜市场写。"
        })

    return patterns


# ============================================================
# 5. 反模式LLM提示词构建器
# ============================================================

class AntiPatternEngine:
    """反模式生成引擎主控"""

    def __init__(self, recipe="中度反模式"):
        self.recipe_name = recipe
        self.recipe_config = CONFIG.get("recipes", {}).get(recipe, {})
        if not self.recipe_config:
            # 回退到默认
            self.recipe_config = CONFIG.get("recipes", {}).get("中度反模式", {})

    def build_anti_prompt(self, files_info, stage="正文"):
        """
        构建反模式LLM提示词: 公因子反转表 + 反模式操作指令 + 阶段专属反因子

        :param files_info: [{name, fp}, ...] 源文指纹列表
        :param stage: 创作阶段
        :return: 反模式提示词字符串
        """
        parts = []

        # 第一步: 提取公因子并反转
        factors = extract_common_factors(files_info)

        parts.append("你是反模式生成引擎。你的任务不是模仿类型公式,而是系统性地反转类型公式,制造最大化预期违背。\n")

        parts.append("## 第一步: 公因子 -> 反因子对照表\n")
        parts.append("以下是从5篇源文中提取的类型公式(公因子)及其反因子:\n")
        parts.append("| 维度 | 公因子(读者预期) | 反因子(预期违背) |")
        parts.append("|------|-----------------|-----------------|")
        for key, val in factors.items():
            parts.append(f"| {key} | {val['common']} | {val['anti']} |")
        parts.append("")

        parts.append("## 第二步: 反模式操作指令\n")
        parts.append("你必须系统性使用以下反因子,而非公因子:\n")
        parts.append("1. 叙事结构: 使用反因子描述的结构,而非三幕式")
        parts.append("2. 角色弧光: 使用反因子描述的弧光,而非成长弧")
        parts.append("3. 情绪节奏: 使用反因子描述的节奏,而非渐强式")
        parts.append("4. 因果链: 使用反因子描述的因果,而非线性因果")
        parts.append("5. 信息分布: 使用黑洞-爆炸交替,而非均匀分布")
        parts.append("6. 背叛/复仇/结局: 全部使用反因子描述")
        parts.append("")

        # 第三步: 阶段专属反模式操作
        stage_ops = self.recipe_config.get("stages", {}).get(stage, {})
        if stage_ops:
            parts.append(f"## 第三步: {stage}阶段反模式操作\n")
            for op_name, intensity in stage_ops.items():
                prompt_fragment = self._get_operator_prompt(op_name, intensity)
                if prompt_fragment:
                    parts.append(prompt_fragment)
                    parts.append("")

        # 第四步: 爽感目标
        ei_target = self.recipe_config.get("ei_target", "55-70")
        parts.append(f"## 第四步: 爽感指数目标\n")
        parts.append(f"目标EI: {ei_target}")
        parts.append("EI五维:")
        parts.append("- P1 预期违背密度: 每1000字3-8次反转/颠覆事件")
        parts.append("- P2 节奏加速度: 段落长度变化率>0.6")
        parts.append("- P3 情绪极差: 最高情绪与最低情绪差>7")
        parts.append("- P4 冲突烈度: 冲突关键词>5/1000字")
        parts.append("- P5 回收密度: 伏笔回收2-5次/1000字")
        parts.append("")

        parts.append("## 输出\n")
        parts.append("直接输出故事正文。所有反因子必须自然融入叙事,不能机械反转。")
        parts.append('读者读完后的感受应该是: 每一处都在意料之外,但每一处又都在情理之中。\n')

        return "\n".join(parts)

    def build_freeform_anti_prompt(self, files_info):
        """无钢印反模式: 不预设任何维度类别,从源文直接提取共享模式并逐项反转。
        适用于'世界是虚假的'前提——不关心死亡/重生/背叛等类型标签,
        只关心源文之间实际重复的叙事 DNA 是什么,然后翻转它。

        :param files_info: [{name, fp}, ...] 源文指纹列表
        :return: 自由反模式提示词
        """
        parts = []
        parts.append("你是反模式引擎,但这一次没有类型公式给你参考。")
        parts.append("你要做的事情很简单:下面是从若干源文中提取的共享叙事模式,逐一列出。")
        parts.append("你的任务是——每一个模式,都写出它的反面。不要参考任何'类型公约',")
        parts.append("不要预设什么是'爽文',不要考虑任何道德锚点。这个世界是纸做的,纸不需要道德。\n")

        # 直接提取高频共享词和模式
        opened_texts = []
        for fi in files_info:
            opened_texts.append(fi["fp"].get("opening_50_lines", ""))
        all_names = []
        for fi in files_info:
            all_names.extend(fi["fp"].get("top_names", []))

        # 发现共享的叙事模式
        patterns = _discover_narrative_patterns(opened_texts, all_names)

        parts.append("## 发现的共享模式\n")
        if not patterns:
            parts.append("(未检测到强共享模式。请在故事中刻意避开所有源文的叙事习惯。)\n")
        else:
            for i, p in enumerate(patterns, 1):
                parts.append(f"{i}. **{p['label']}**: {p['description']}")
                parts.append(f"   反转: {p['anti']}")
                parts.append("")

        parts.append("## 叙事指令\n")
        parts.append("不要线性叙述。从一个已经发生的结局开始,然后往回想为什么。")
        parts.append("不要给角色赋予道德标签。他们的行为只是行为,不是善恶。")
        parts.append("不要让任何角色成为'正义的代言人'或'邪恶的化身'。")
        parts.append("每一段都可以推翻上一段给你的印象。读者从头到尾不应该确定谁是好人。")
        parts.append("结尾不需要和解。可以停在任何一个你觉得不该停的位置。\n")
        parts.append("## 输出\n直接输出故事正文,不解释。\n")

        return "\n".join(parts)

    def _get_operator_prompt(self, op_name, intensity):
        """根据操作器名称和强度生成提示词片段"""
        if op_name == "structure_invert":
            return StructureInverter.generate_prompt(intensity)
        elif op_name == "emotion_polarize":
            return EmotionPolarizer.generate_prompt(intensity)
        elif op_name == "causality_invert":
            return CausalityInverter.generate_prompt(intensity)
        elif op_name == "character_subvert":
            return CharacterSubverter.generate_prompt(intensity)
        elif op_name == "info_bomb":
            return InfoBomber.generate_prompt(intensity)
        return None


# ============================================================
# 5. 互消 vs 反模式 对照分析
# ============================================================

def compare_modes(files_info):
    """
    对比展示互消模式和反模式的不同输出,帮助理解对偶关系。

    :param files_info: [{name, fp}, ...]
    :return: {"fusion": "...", "anti_pattern": "..."}
    """
    factors = extract_common_factors(files_info)

    comparison = {
        "互消模式(现有)": {},
        "反模式(新增)": {},
    }

    for key, val in factors.items():
        comparison["互消模式(现有)"][key] = f"消除公因子,自创全新: {val['common']} -> 创造不重叠的新值"
        comparison["反模式(新增)"][key] = f"反转公因子: {val['common']} -> {val['anti']}"

    return comparison


# ============================================================
# CLI 入口
# ============================================================

def main():
    import sys
    print(__doc__)

    if len(sys.argv) < 2:
        print("用法: python anti_pattern.py --recipe 中度反模式 --stage 正文 --files file1.txt file2.txt ...")
        print("      python anti_pattern.py --ei story.txt  # 计算爽感指数")
        sys.exit(1)

    args = sys.argv[1:]
    recipe = "中度反模式"
    stage = "正文"
    files = []
    ei_mode = False
    ei_file = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--recipe" and i + 1 < len(args):
            recipe = args[i + 1]; i += 2
        elif a == "--stage" and i + 1 < len(args):
            stage = args[i + 1]; i += 2
        elif a == "--ei" and i + 1 < len(args):
            ei_mode = True
            ei_file = args[i + 1]; i += 2
        elif not a.startswith("-"):
            files.append(a); i += 1
        else:
            i += 1

    if ei_mode:
        # 爽感指数计算模式
        if not os.path.exists(ei_file):
            print(f"文件不存在: {ei_file}")
            sys.exit(1)
        with open(ei_file, "r", encoding="utf-8") as f:
            text = f.read()
        result = calculate_EI(text)
        print(f"\n{'='*50}")
        print(f"爽感指数 EI: {result['EI']} / 100")
        print(f"等级: {result['grade']}")
        print(f"{'='*50}")
        print("\n五维详情:")
        for k, v in result["details"].items():
            print(f"  {k}: {v}")
        sys.exit(0)

    # 反模式生成模式
    if not files:
        print("错误: 需要至少3篇源文")
        sys.exit(1)

    # 提取指纹
    sys.path.insert(0, os.path.join(_HERE, ".."))
    import tools.fusion as fusion_mod

    files_info = []
    for fp in files:
        text = fusion_mod.read_file(fp)
        fingerprint = fusion_mod.extract_fingerprint(text)
        files_info.append({"name": os.path.basename(fp), "fp": fingerprint})

    engine = AntiPatternEngine(recipe=recipe)
    prompt = engine.build_anti_prompt(files_info, stage=stage)

    output_path = os.path.join(_HERE, "..", "output", f"{stage}_anti_pattern_prompt.txt")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    print(f"\n反模式提示词已生成: {output_path}")
    print(f"配方: {recipe}")
    print(f"阶段: {stage}")
    print(f"目标EI: {engine.recipe_config.get('ei_target', 'N/A')}")

    # 对照分析
    comparison = compare_modes(files_info)
    print(f"\n{'='*60}")
    print("互消模式 vs 反模式 对照:")
    print(f"{'='*60}")
    for key in comparison["互消模式(现有)"]:
        print(f"\n[{key}]")
        print(f"  互消: {comparison['互消模式(现有)'][key]}")
        print(f"  反模式: {comparison['反模式(新增)'][key]}")


if __name__ == "__main__":
    main()
