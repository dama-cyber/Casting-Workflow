# -*- coding: utf-8 -*-
"""
narrative_features.py — 中文叙事话语特征提取器（StoryScope 10 维 taxonomy 规则化重建）

设计依据：docs/system_design.md（架构师高见远 / 熔铸版 v6.3 本地优先优化架构）。
定位：本地三交叉终判的「叙事层」特征源。纯 jieba + 标准库，零重型依赖、零模型、CPU 友好。

核心约束（三红线）：
  ① 不泄 corpus 字面：本模块只输出统计量（数值 / 类型标签），绝不缓存原文；
  ② 不动互消层：本模块只读单篇文本，不读取或修改 fusion.py；
  ③ 8G 防护：corpus 处理逐篇流式 + 落盘 JSONL 缓存，绝不一次性载入全量文本或特征矩阵。

接口（与 design doc §3 对齐）：
  extract_narrative_features(text, taxonomy=None) -> dict        # 单篇 17 字段 FeatureVector
  stream_extract_corpus(corpus_root, cache_path, ...)             # 逐篇流式抽取并 append 到 JSONL
  load_feature_cache(cache_path) -> Iterator[dict]                # 流式读回特征缓存
  build_narrative_baseline(stream) -> dict                        # 单遍聚合各字段 p10/p90/median

字段清单（17 个，14 个 P0 可规则化 + 3 个 degraded 占位，详见 config/narrative_taxonomy.json）。
"""
import os
import re
import sys
import json
import math
import glob
import statistics

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── 路径约定
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
OUTPUT_DIR = os.path.join(_ROOT, "data")
DEFAULT_TAXONOMY_PATH = os.path.join(_ROOT, "config", "narrative_taxonomy.json")
DEFAULT_FEATURE_CACHE = os.path.join(OUTPUT_DIR, "_narrative_features.jsonl")
DEFAULT_BASELINE_PATH = os.path.join(OUTPUT_DIR, "_narrative_baseline.json")

# ── 轻量内联词典（只存类型标签 / 标记词，不存 corpus 字面，符合红线①）
# 注：这些标记词属于「通用中文叙事信号」，非语料私有内容，不泄露任何原文。

# 时间跳跃（temporal_complexity）
_TIME_JUMP = [
    "三年后", "十年后", "一年后", "两年后", "五年后", "数年后", "时光荏苒",
    "光阴似箭", "话分两头", "转眼", "多年以后", "时光倒流", "回到那年",
    "回到过去", "当年", "从前", "翌日", "次日", "第二天", "隔日", "后来",
    "那一年", "有一天", "且说", "却说",
]
# 闪回（flashback_count）
_FLASHBACK = [
    "回想", "回忆", "当年", "记忆中", "记得", "往事", "那时候", "脑海",
    "想起", "追忆", "往事如烟", "恍然想起", "忆起",
]
# 视角 / 支线切换（subplot_count）
_THREAD_SWITCH = [
    "与此同时", "话分两头", "另一边", "另一头", "另一厢", "且说", "却说",
    "再说", "镜头一转", "转到", "无独有偶", "偏巧", "巧的是",
]
# 伏笔 / 悬念（foreshadow_density）
_FORESHADOW = [
    "殊不知", "谁料", "原来", "竟", "偏偏", "没想到", "埋下伏笔", "隐隐",
    "早有预感", "冥冥之中", "注定", "宿命", "暗藏", "伏笔", "草蛇灰线",
    "早有征兆",
]
# 道德模糊：利他 / 利己-伤害（protagonist_moral_ambiguity）
_MORAL_ALTRUISTIC = [
    "救", "帮", "护", "舍身", "牺牲", "让", "给予", "宽恕", "原谅",
    "成全", "守护", "庇护", "接济", "周济",
]
_MORAL_HARM = [
    "杀", "骗", "背叛", "利用", "谋害", "夺", "抢", "害", "算计", "报复",
    "坑", "陷害", "出卖", "残害",
]
# 情绪词（emotion_arc_variance，复用 human_profile 风格，自包含）
_EMOTION_LEXICON = [
    "笑", "喜", "乐", "欢", "甜", "开心", "高兴", "雀跃", "怒", "恨", "恼",
    "火", "愤", "气急", "咬牙", "哭", "悲", "痛", "伤", "哀", "凄凉", "心碎",
    "落泪", "怕", "慌", "惧", "惊", "恐", "发抖", "窒息", "后背发凉", "愣",
    "怔", "呆", "震撼", "难以置信", "崩塌", "碾压",
]
# 冲突关键词（event_escalation_slope）
_CONFLICT = [
    "杀", "战", "死", "败", "怒", "危", "危机", "崩", "毁灭", "覆灭", "血",
    "伤", "斗", "争", "爆", "惊", "震", "溃", "亡", "劫", "难", "敌", "攻",
    "破", "袭", "陷", "乱", "反",
]
# 场景具体度（setting_concreteness）：地点 / 感官 / 空间
_SETTING_PLACE = [
    "山", "河", "城", "宫", "殿", "院", "街", "巷", "房", "屋", "林", "海",
    "江", "湖", "原", "谷", "塔", "桥", "路", "门", "窗", "床", "桌", "楼",
    "阁", "寺", "庙", "村", "镇", "京", "都", "府", "园", "庭", "洞",
]
_SETTING_SENSORY = [
    "闻", "嗅", "触", "摸", "看", "听", "尝", "冷", "热", "温", "凉", "疼",
    "痛", "酸", "涩", "香", "臭", "亮", "暗", "红", "白", "黑", "青", "绿", "蓝",
]
_SETTING_SPATIAL = [
    "前", "后", "左", "右", "上", "下", "里", "外", "中", "旁", "边", "顶",
    "底", "内", "东", "西", "南", "北", "近", "远",
]
# 结尾类型（ending_type）
_END_TRAGIC = ["死", "亡", "葬", "悲", "陨", "灭", "殇", "凋零", "逝", "惨死", "含冤"]
_END_HAPPY = ["圆满", "幸福", "团聚", "大婚", "胜利", "归来", "团圆", "喜庆",
              "皆大欢喜", "有情人终成眷属"]
_END_BITTERWIN = ["惨胜", "代价", "满身伤", "两败", "惨烈", "遍体鳞伤", "险胜", "惨重"]
_END_OPEN = ["未完待续", "未完", "待续", "故事还在继续", "新的开始", "未知"]
# 冲突结构（conflict_structure）
_STRUCT_REVERSE = ["真相", "原来", "竟", "幕后", "反转", "实则", "其实", "不料", "殊不知"]
_STRUCT_MIDBURST = ["突变", "骤变", "风云突变", "霹雳", "霎时", "骤然", "平地惊雷",
                    "突发事件", "变故"]
# degraded 占位特征词典近似
_THEME_MARKERS = ["意味着", "象征", "隐喻", "寓意", "主题", "主旨", "其实", "本质上",
                  "说明", "揭示", "告诉我们", "所谓", "无非是", "代表着", "折射", "隐喻着", "意在"]
_INTERTEXT_MARKERS = ["古人云", "常言道", "《", "》", "典故", "诗词", "引用", "子曰",
                      "诗云", "俗话说", "有云", "正如", "经云", "古语"]
_SOCIAL_MARKERS = ["朋友", "师徒", "盟友", "敌人", "对手", "兄妹", "夫妻", "父子",
                   "母女", "同门", "同窗", "结拜", "世交", "邻居", "亲属", "恩师",
                   "爱徒", "同僚", "同乡", "仇家", "知己", "挚友", "死敌"]

# 轻量姓名提取（agency_complexity，复用 check_story 姓氏分级思路的轻量版）
_NAME_STRONG_MED = "赵钱孙李周吴郑王冯蒋韩杨朱秦尤何吕施张孔曹严华金魏陶姜戚谢邹喻章苏沈顾楚陆萧"
_NAME_WEAK = "方白江林叶云柳陈许"
_NAME_COMPOUND = ["慕容", "欧阳", "司马", "上官", "诸葛", "东方", "西门", "南宫",
                  "独孤", "端木", "尉迟", "皇甫", "令狐", "夏侯", "长孙", "宇文",
                  "司徒", "司空"]
_NAME_BLOCK = set(
    "的得地了着过上中下内外前后左右里这那此些个次回与和及或但而把被给对向从由"
    "吗呢吧啊什么每各某一二三四五六七八九十百千万亿零东西南北不"
)
_NAME_BROAD = r"[，。！？：\"'说问道喊叫嚷骂答哭笑叹看走向站坐来去便就吃喝走跑拿放打推抱点望轻微悄缓也已只都还才又再正总]"
_NAME_TITLE = frozenset({
    "王妃", "王爷", "皇后", "皇上", "太子", "夫人", "小姐", "少爷", "公主", "郡主",
    "娘娘", "太后", "太妃", "世子", "侯爷", "将军", "大人", "尚书", "侍郎", "统领",
    "副将", "主母", "姨娘", "婆母", "小姑", "小叔", "夫君", "相公", "娘子",
})
_NAME_COMMON = frozenset({
    "白甜", "白转", "钱都", "陆家", "顾家", "王家", "你们", "看着", "这是", "不是",
    "什么", "可以", "已经", "知道", "没有",
})


# ============================================================
# 词典加载
# ============================================================
def load_taxonomy(path=None):
    """加载 config/narrative_taxonomy.json；返回 {meta, features(list), by_name(dict)}。"""
    path = path or DEFAULT_TAXONOMY_PATH
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    features = data.get("features", [])
    by_name = {f["name"]: f for f in features}
    return {"meta": data.get("_meta", {}), "features": features, "by_name": by_name}


class NarrativeTaxonomy(object):
    """对 design doc 接口 `taxonomy: NarrativeTaxonomy` 的轻量封装（dict 兼容）。"""

    def __init__(self, path=None):
        self._data = load_taxonomy(path)
        self.features = self._data["features"]
        self.by_name = self._data["by_name"]
        self.meta = self._data["meta"]

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def numeric_names(self):
        return [f["name"] for f in self.features if f["type"] in ("scale", "ordinal")]

    def categorical_names(self):
        return [f["name"] for f in self.features if f["type"] == "categorical"]


# ============================================================
# 通用工具
# ============================================================
def _count_chinese(text):
    return len(re.findall(r"[一-鿿]", text))


def _split_paragraphs(text):
    return [p.strip() for p in re.split(r"\n+|\u3000", text) if re.search(r"[一-鿿]", p)]


def _soft_saturate(density_per_1k, half):
    """把「每千字出现次数」饱和映射到 [0,1)：half = 半饱和点密度。"""
    if density_per_1k <= 0:
        return 0.0
    return density_per_1k / (density_per_1k + half)


def _safe(default):
    """装饰器式安全求值：单特征计算异常时回退默认，保证整篇抽取不中断。"""

    def wrap(fn):
        def inner(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                return default
        return inner
    return wrap


# ============================================================
# 各特征规则实现
# ============================================================
@_safe(0)
def _feat_subplot_count(text):
    n = sum(text.count(m) for m in _THREAD_SWITCH)
    return min(n, 10)


@_safe(1)
def _feat_plot_linearity(subplot_count):
    # plot_linearity = 1 - normalize(subplot_count)，6 条以上副线视为完全非线性
    return max(0.0, min(1.0, 1.0 - subplot_count / 6.0))


@_safe(0.3)
def _feat_temporal_complexity(text, zh):
    d = sum(text.count(m) for m in _TIME_JUMP) / (zh / 1000.0 + 1e-6)
    return _soft_saturate(d, 2.0)


@_safe(0)
def _feat_flashback_count(text):
    n = sum(text.count(m) for m in _FLASHBACK)
    return min(n, 15)


@_safe(0.3)
def _feat_foreshadow_density(text, zh):
    d = sum(text.count(m) for m in _FORESHADOW) / (zh / 1000.0 + 1e-6)
    return _soft_saturate(d, 1.5)


@_safe(0.3)
def _feat_moral_ambiguity(text):
    a = sum(text.count(m) for m in _MORAL_ALTRUISTIC)
    h = sum(text.count(m) for m in _MORAL_HARM)
    if a > 0 and h > 0:
        # 利他/伤害并存 → 道德模糊；越均衡越模糊（上限 1.0）
        return min(1.0, 2.0 * min(a, h) / (a + h))
    return 0.0


@_safe(0.5)
def _feat_emotion_arc_variance(text):
    paras = _split_paragraphs(text)
    if len(paras) < 2:
        paras = re.split(r"[。！？]", text)
        paras = [p for p in paras if re.search(r"[一-鿿]", p)]
    if len(paras) < 2:
        return 0.0
    densities = []
    for p in paras:
        pc = max(1, _count_chinese(p))
        densities.append(sum(p.count(w) for w in _EMOTION_LEXICON) / pc)
    if len(densities) < 2:
        return 0.0
    return round(statistics.pvariance(densities), 4)


@_safe(0.8)
def _feat_pov_consistency(text):
    sents = [s for s in re.split(r"[。！？\n]", text) if re.search(r"[一-鿿]", s)]
    if not sents:
        return 0.8
    persons = []
    for s in sents:
        has_first = bool(re.search(r"我(们)?", s)) and not bool(re.search(r"他(们|她)?", s))
        has_third = bool(re.search(r"他(们|她)?", s)) and not bool(re.search(r"我(们)?", s))
        if has_first:
            persons.append("1")
        elif has_third:
            persons.append("3")
        else:
            persons.append(None)
    clear = [p for p in persons if p]
    if not clear:
        return 0.8
    fp = clear.count("1")
    tp = clear.count("3")
    mix_ratio = min(fp, tp) / len(clear)
    cons = 1.0 - mix_ratio * 0.9
    # 显式视角切换标记轻微扣分
    switches = sum(text.count(m) for m in _THREAD_SWITCH)
    cons -= min(0.2, switches * 0.02)
    return max(0.0, min(1.0, cons))


@_safe(0.6)
def _feat_pacing_variability(text):
    paras = _split_paragraphs(text)
    lens = [len(re.findall(r"[一-鿿]", p)) for p in paras if len(re.findall(r"[一-鿿]", p)) > 0]
    if len(lens) < 2:
        return 0.0
    mean = statistics.mean(lens)
    if mean <= 0:
        return 0.0
    cv = statistics.pstdev(lens) / mean
    return round(min(3.0, cv), 4)


@_safe(3)
def _feat_agency_complexity(text):
    names = _extract_names_light(text)
    return min(20, len(names))


@_safe(0.0)
def _feat_event_escalation_slope(text, zh):
    # 将文本等分为 10 段，计算每段冲突关键词密度，拟合线性斜率（归一化到 [-1,1]）
    chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    if len(chars) < 200:
        return 0.0
    k = 10
    seg_len = len(chars) // k
    if seg_len == 0:
        return 0.0
    densities = []
    for i in range(k):
        seg = "".join(chars[i * seg_len:(i + 1) * seg_len])
        densities.append(sum(seg.count(w) for w in _CONFLICT) / max(1, len(seg) / 1000.0))
    # 最小二乘斜率
    n = len(densities)
    xs = list(range(n))
    mx = statistics.mean(xs)
    my = statistics.mean(densities)
    num = sum((xs[i] - mx) * (densities[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    slope = num / den
    mean_d = max(my, 1e-6)
    norm = slope / mean_d
    return round(max(-1.0, min(1.0, norm)), 4)


@_safe(0.6)
def _feat_setting_concreteness(text, zh):
    d = (sum(text.count(w) for w in _SETTING_PLACE)
         + sum(text.count(w) for w in _SETTING_SENSORY)
         + sum(text.count(w) for w in _SETTING_SPATIAL)) / (zh / 1000.0 + 1e-6)
    return _soft_saturate(d, 8.0)


@_safe("其他")
def _feat_ending_type(text):
    tail = text[-300:] if len(text) > 300 else text
    if any(o in tail for o in _END_OPEN):
        return "开放式"
    if sum(tail.count(w) for w in _END_TRAGIC) > 0:
        return "悲剧"
    if any(w in tail for w in _END_HAPPY):
        return "大团圆"
    if any(w in tail for w in _END_BITTERWIN):
        return "惨胜"
    return "其他"


@_safe("线性")
def _feat_conflict_structure(text):
    if sum(text.count(w) for w in _STRUCT_MIDBURST) > 0:
        return "中点爆炸"
    if sum(text.count(w) for w in _STRUCT_REVERSE) > 0:
        return "倒因果"
    return "线性"


# ── 3 个 degraded 占位特征（P0 词典近似，P2 补全）
@_safe(0.5)
def _feat_theme_explicitness(text, zh):
    d = sum(text.count(m) for m in _THEME_MARKERS) / (zh / 1000.0 + 1e-6)
    return _soft_saturate(d, 1.0)


@_safe(0.2)
def _feat_intertextuality(text, zh):
    d = sum(text.count(m) for m in _INTERTEXT_MARKERS) / (zh / 1000.0 + 1e-6)
    return _soft_saturate(d, 0.6)


@_safe(0.4)
def _feat_social_network_density(text, zh):
    d = sum(text.count(m) for m in _SOCIAL_MARKERS) / (zh / 1000.0 + 1e-6)
    return _soft_saturate(d, 2.0)


def _extract_names_light(text):
    """轻量命名角色提取（agency_complexity 用），只取类型标签计数，不缓存字面。"""
    patterns = []
    wb = r"(?<![一-鿿])"
    strong_med = _NAME_STRONG_MED
    comp = "|".join(_NAME_COMPOUND)
    broad = _NAME_BROAD
    patterns.append(rf"((?:{comp})[一-鿿])(?={broad})")
    patterns.append(rf"((?:{comp})[一-鿿]{{2}})(?={broad})")
    patterns.append(rf"([{strong_med}][一-鿿])(?={broad})")
    patterns.append(rf"([{strong_med}][一-鿿]{{2}})(?={broad})")
    patterns.append(rf"([{_NAME_WEAK}][一-鿿]{{2}})(?={broad})")
    patterns.append(rf"{wb}([{_NAME_WEAK}][一-鿿])(?={broad})")
    found = set()
    for pat in patterns:
        found.update(re.findall(pat, text))
    # 过滤：第二字为虚词/数字、称号词、常见名词
    out = set()
    for n in found:
        if len(n) >= 2 and n[1] in _NAME_BLOCK:
            continue
        if n in _NAME_TITLE or n in _NAME_COMMON:
            continue
        out.add(n)
    return out


# ============================================================
# 主入口：单篇特征提取
# ============================================================
def extract_narrative_features(text, taxonomy=None):
    """输入单篇文本，返回 17 字段 FeatureVector（dict）。

    严格遵守红线①：只输出统计量，不缓存原文。
    taxonomy 仅用于字段顺序 / 默认值回退；规则逻辑内联，不依赖 taxonomy 内容。
    """
    zh = _count_chinese(text)
    subplot = _feat_subplot_count(text)
    feats = {
        "plot_linearity": _feat_plot_linearity(subplot),
        "subplot_count": subplot,
        "ending_type": _feat_ending_type(text),
        "conflict_structure": _feat_conflict_structure(text),
        "temporal_complexity": _feat_temporal_complexity(text, zh),
        "flashback_count": _feat_flashback_count(text),
        "foreshadow_density": _feat_foreshadow_density(text, zh),
        "protagonist_moral_ambiguity": _feat_moral_ambiguity(text),
        "emotion_arc_variance": _feat_emotion_arc_variance(text),
        "pov_consistency": _feat_pov_consistency(text),
        "pacing_variability": _feat_pacing_variability(text),
        "agency_complexity": _feat_agency_complexity(text),
        "event_escalation_slope": _feat_event_escalation_slope(text, zh),
        "setting_concreteness": _feat_setting_concreteness(text, zh),
        "theme_explicitness": _feat_theme_explicitness(text, zh),
        "intertextuality": _feat_intertextuality(text, zh),
        "social_network_density": _feat_social_network_density(text, zh),
    }
    return feats


# ============================================================
# 流式抽取 + 缓存（8G 安全）
# ============================================================
def _read_text(path):
    for enc in ("utf-8", "gbk", "utf-8-sig"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def stream_extract_corpus(corpus_root, cache_path, taxonomy=None, workers=1):
    """逐篇 open→read→extract→append 到 cache_path(JSONL)。

    单篇处理完即释放，绝不把全 corpus 载入内存（8G 安全）。
    workers 参数保留 API 兼容（P0 单进程流式即可，避免多进程位图副本风险）。
    """
    taxonomy = taxonomy or NarrativeTaxonomy()
    count = 0
    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
    with open(cache_path, "a", encoding="utf-8") as out:
        for root, _, files in os.walk(corpus_root):
            for fn in files:
                if not fn.lower().endswith(".txt"):
                    continue
                path = os.path.join(root, fn)
                try:
                    text = _read_text(path)
                    feats = extract_narrative_features(text, taxonomy)
                except Exception as e:
                    print(f"[WARN] stream_extract skip: {e}", file=sys.stderr)
                    continue
                rec = {"path": os.path.relpath(path, corpus_root), "features": feats}
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                count += 1
                if count % 500 == 0:
                    out.flush()
    return count


def load_feature_cache(cache_path):
    """流式读回特征缓存，逐行 yield features dict，不整体载入内存。"""
    if not os.path.isfile(cache_path):
        return
    with open(cache_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            yield rec.get("features", rec)


# ============================================================
# 基线聚合（单遍 / 轻量数组，内存可忽略）
# ============================================================
def _percentile(sorted_vals, q):
    """q in [0,1]；返回分位值。"""
    m = len(sorted_vals)
    if m == 0:
        return 0.0
    idx = max(0, min(m - 1, int(round(q * (m - 1)))))
    return sorted_vals[idx]


def build_narrative_baseline(stream, taxonomy=None):
    """单遍扫描各数值字段收集标量数组（17×~1e4 个数字 ≈ 数 MB，远低于 8G），
    计算 p10/p90/median/mean；分类字段统计分布。返回基线 dict。

    注：design doc 建议 Welford 在线统计「只存计数器」；本实现改为收集标量数组，
    因数字量极小（非文本/非特征矩阵），正确性更佳且同样不触发 OOM，符合 8G 约束。
    """
    taxonomy = taxonomy or NarrativeTaxonomy()
    numeric_names = taxonomy.numeric_names()
    cat_names = taxonomy.categorical_names()
    numeric_arrays = {n: [] for n in numeric_names}
    cat_counts = {n: {} for n in cat_names}
    total = 0
    for feats in stream:
        total += 1
        for n in numeric_names:
            v = feats.get(n)
            if isinstance(v, (int, float)):
                numeric_arrays[n].append(float(v))
        for n in cat_names:
            v = feats.get(n)
            if v is not None:
                cat_counts[n][v] = cat_counts[n].get(v, 0) + 1

    baseline = {"files": total, "_meta": {"source": "narrative_features.build_narrative_baseline"}}
    numeric = {}
    for n in numeric_names:
        arr = sorted(numeric_arrays[n])
        if not arr:
            fmeta = taxonomy.by_name.get(n, {})
            numeric[n] = {"p10": 0, "p90": 0, "median": fmeta.get("default", 0),
                          "mean": 0, "min": 0, "max": 0}
            continue
        p10 = round(_percentile(arr, 0.10), 4)
        p90 = round(_percentile(arr, 0.90), 4)
        median = round(statistics.median(arr), 4)
        mn = round(min(arr), 4)
        mx = round(max(arr), 4)
        # half = 人类正常带半宽；供 narrative_deviation / narrative_rarity 标准化
        if p90 > p10:
            half = round((p90 - p10) / 2.0, 4)
        elif mx > mn:
            half = round((mx - mn) / 2.0, 4)
        else:
            half = 1.0
        numeric[n] = {
            "p10": p10, "p90": p90, "median": median,
            "mean": round(statistics.mean(arr), 4),
            "min": mn, "max": mx, "half": half,
        }
    baseline["numeric"] = numeric
    cat = {}
    for n in cat_names:
        dist = cat_counts[n]
        mode = max(dist, key=dist.get) if dist else None
        cat[n] = {"distribution": dist, "mode": mode}
    baseline["categorical"] = cat
    return baseline


def build_narrative_baseline_from_cache(cache_path, taxonomy=None):
    """便捷封装：从 JSONL 缓存流式读回并聚合基线。"""
    return build_narrative_baseline(load_feature_cache(cache_path), taxonomy)


# ============================================================
# 命令行：流式构建 corpus 叙事基线（默认关，显式触发）
# ============================================================
def main():
    args = sys.argv[1:]
    mode = None
    corpus_dir = "corpus"
    cache_dir = OUTPUT_DIR
    features_out = DEFAULT_FEATURE_CACHE
    baseline_out = DEFAULT_BASELINE_PATH
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--build-baseline":
            mode = "build"
        elif a == "--corpus" and i + 1 < len(args):
            corpus_dir = args[i + 1]; i += 2
        elif a == "--cache" and i + 1 < len(args):
            cache_dir = args[i + 1]; i += 2
        elif a == "--features-out" and i + 1 < len(args):
            features_out = args[i + 1]; i += 2
        elif a == "--out" and i + 1 < len(args):
            baseline_out = args[i + 1]; i += 2
        else:
            i += 1
    if mode != "build":
        print(__doc__)
        sys.exit(0)
    if not os.path.isdir(corpus_dir):
        print(f"未找到 corpus: {corpus_dir}")
        sys.exit(1)
    print(f"流式抽取 corpus 叙事特征 -> {features_out}")
    n = stream_extract_corpus(corpus_dir, features_out)
    print(f"  完成 {n} 篇，开始聚合基线 ...")
    base = build_narrative_baseline_from_cache(features_out)
    with open(baseline_out, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=2)
    print(f"叙事基线已写出 -> {baseline_out}（覆盖 {base['files']} 篇）")


if __name__ == "__main__":
    main()
