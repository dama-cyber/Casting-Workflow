# -*- coding: utf-8 -*-
"""
test_anti_ai_qa.py — 独立 QA 回归测试（qa 工程师严过关）

对 Casting-Workflow 熔铸版 v6.3「qiaomu 借鉴」P0 增量（方向 A 去 AI 味报告
+ 方向 B 生成禁用清单 QA 闭环）做独立回归验证。**只用标准库 unittest / re / json /
subprocess**，不引入 pytest 等第三方依赖（零新增依赖红线）。

覆盖任务 6 大断言：
  1) 报告引擎正确性（report_ai_flavor 计数 / 阈值告警）
  2) 引号豁免（not_x_but_y 软信号豁免；banned 硬项不豁免）
  3) 终判弱信号红线（triple_cross_judge 注入 qiaomu WARN 层：绝不 FAIL、conf≤0.5、
     _consensus 不变、不传时无回归）
  4) CLI 与报告落盘（--ai-flavor / --no-ai-flavor）
  5) banned.json 首次被消费 + 无误杀
  6) 红线核验（fusion.py 未改、requirements 仅 jieba、anti_ai_rules 无 corpus 泄露）

运行：
  python tools/test_anti_ai_qa.py            # 或
  python -u -m unittest tools.test_anti_ai_qa -v
"""
import os
import re
import sys
import json
import unittest
from unittest import mock

# ---- 路径与导入（tools 为隐式命名空间包；human_profile/local_discriminator 需 tools 在 path）----
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_TOOLS = os.path.join(_ROOT, "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from tools.anti_ai_reporter import (  # noqa: E402
    report_ai_flavor,
    load_anti_ai_rules,
    load_banned,
)
from tools.humanity_scorer import (  # noqa: E402
    triple_cross_judge,
    _consensus,
    _CONSENSUS_THRESHOLD,
)


# ============================================================
# 共享工具
# ============================================================
def _find_novels(max_count=400, max_bytes=60000):
    """返回 corpus 下前若干个小体积 .txt 路径（保证 CLI 测试快）。"""
    out = []
    for root, _, files in os.walk(os.path.join(_ROOT, "corpus")):
        for fn in files:
            if not fn.endswith(".txt"):
                continue
            p = os.path.join(root, fn)
            try:
                if os.path.getsize(p) <= max_bytes:
                    out.append(p)
                    if len(out) >= max_count:
                        return out
            except OSError:
                continue
    return out


def _find_banned_hit_novel(max_count=400, head_bytes=300000):
    """扫描 corpus，返回第一个含 banned 硬项命中的 (path, text) 。"""
    banned = load_banned()
    pats = banned.get("banned_patterns", []) or []
    temps = banned.get("banned_templates", []) or []
    puncts = banned.get("banned_punctuation", []) or []

    def has_banned(t):
        for b in puncts:
            if t.count(b) > 0:
                return True
        for b in pats:
            if re.search(b, t):
                return True
        for b in temps:
            if t.count(b) > 0:
                return True
        return False

    n = 0
    for root, _, files in os.walk(os.path.join(_ROOT, "corpus")):
        for fn in files:
            if not fn.endswith(".txt"):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    head = fh.read(head_bytes)
            except OSError:
                continue
            n += 1
            if has_banned(head):
                return p, head
            if n >= max_count:
                return None, None
    return None, None


def _make_alarm(severity=1.0, alarm=True):
    """构造一个最小可用的 ai_flavor 弱信号 dict（模仿 report_ai_flavor 返回）。"""
    return {
        "ai_flavor_alarm": alarm,
        "severity": float(severity),
        "alarm_detail": "qa-test-signal",
    }


# ============================================================
# 1) 报告引擎正确性
# ============================================================
class TestReportEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_anti_ai_rules()
        cls.terms = cls.rules["dictionaries"]["abstract_terms"]
        cls.scene = cls.rules["dictionaries"]["scene_markers"]
        cls.th = cls.rules["thresholds"]

    def test_abstract_count_matches_text_count(self):
        """抽象术语计数须逐项等于 text.count 求和（qiaomu 口径=原始计数）。"""
        text = "需求流程系统规范策略机制能力价值痛点闭环效率协同模型方案架构规则。"
        expected = sum(text.count(t) for t in self.terms)
        r = report_ai_flavor(text)
        self.assertEqual(r["abstract"]["count"], expected)
        self.assertGreater(expected, 0)

    def test_abstract_dense_triggers_alarm_warn(self):
        """abstract>2*scene 且 >12 → ai_flavor_alarm=True 且 alarm_severity='WARN'。"""
        # 13 个抽象词，0 个场景词 → 满足 abstract>2*0 且 >12
        text = "需求流程系统规范策略机制能力价值痛点闭环效率模型方案架构规则。"
        r = report_ai_flavor(text)
        self.assertIn("abstract_dense", r["flags"])
        self.assertTrue(r["ai_flavor_alarm"])
        self.assertEqual(r["alarm_severity"], "WARN")

    def test_scene_sparse_triggers_warn(self):
        """scene<8 → scene_sparse 触发告警。"""
        # 仅 2 个场景词（窗/雨），无抽象词，避免 abstract_dense 干扰判定
        text = "窗外的雨落下来。她端起杯子。他看向屏幕。"  # 窗,雨,屏幕 = 3? 用更少
        text2 = "窗边下着雨。"  # 窗,雨 = 2 个场景词
        r = report_ai_flavor(text2)
        self.assertIn("scene_sparse", r["flags"])
        self.assertLess(r["scene"]["count"], int(self.th["scene_min"]))

    def test_scene_rich_no_scene_sparse(self):
        """场景词充足（>=8）时不触发 scene_sparse。"""
        text = "会议室门口窗雨灯桌屏幕手机街车手眼血杯纸门椅走廊都布置好了。"
        r = report_ai_flavor(text)
        self.assertNotIn("scene_sparse", r["flags"])
        self.assertGreaterEqual(r["scene"]["count"], 8)

    def test_dash_overuse_triggers(self):
        """破折号 > 3 → dash_overuse 触发。"""
        text = "他说——她笑——天黑了——路很长——风停了。"
        r = report_ai_flavor(text)
        self.assertIn("dash_overuse", r["flags"])
        self.assertGreater(r["dash"]["count"], int(self.th["dash_max"]))

    def test_ambiguous_opening_triggers(self):
        """误导开篇正则命中 → ambiguous_opening 触发。"""
        text = "死人走进了房间，尸体来到桌前，死者开口说话。"
        r = report_ai_flavor(text)
        self.assertIn("ambiguous_opening", r["flags"])
        self.assertGreaterEqual(r["ambiguous"]["count"], 1)
        self.assertGreater(r["ambiguous"]["breakdown"].get("dead_person_walking", 0), 0)

    def test_normal_human_no_massive_false_kill(self):
        """真实人类文本不应被大规模误杀（不会同时触发全部重度 AI 味标志）。"""
        novels = _find_novels(max_count=50, max_bytes=60000)
        self.assertTrue(novels, "未找到可用于抽样的 corpus 小说")
        text = open(novels[0], encoding="utf-8", errors="replace").read()
        r = report_ai_flavor(text)
        heavy = {"abstract_dense", "scene_sparse", "dash_overuse", "ambiguous_opening"}
        triggered = set(r["flags"]) & heavy
        # 人类文本最多只可能偶发其中一两项，绝不会四项齐发（那才是“重度 AI 味”）
        self.assertFalse(heavy.issubset(set(r["flags"])),
                         f"人类文本被判定为重度 AI 味: flags={r['flags']}")
        # 即便触发，也只是轻量 WARN 级别信号，绝不产生 FAIL
        self.assertNotEqual(r["alarm_severity"], "FAIL")


# ============================================================
# 2) 引号豁免
# ============================================================
class TestQuoteExemption(unittest.TestCase):
    def test_in_quote_not_x_but_y_exempt(self):
        """「」内的 not_x_but_y 软信号应被豁免（不计入软告警）。"""
        text = ("「你不是英雄，而是懦夫。」"              # 引号内 → 应豁免
                "这不是我们想要的，而是彻底的失败。")     # 引号外 → 应命中
        r = report_ai_flavor(text)
        self.assertEqual(r["aiish"]["breakdown"].get("not_x_but_y", 0), 1,
                         "引号内 not_x_but_y 应被豁免，仅计引号外 1 次")

    def test_out_of_quote_not_x_but_y_hits(self):
        """「」外的 not_x_but_y 照常命中。"""
        text = "这件事不是结束，而是新的开始。"
        r = report_ai_flavor(text)
        self.assertGreaterEqual(r["aiish"]["breakdown"].get("not_x_but_y", 0), 1)

    def test_banned_hard_in_quote_not_exempt(self):
        """banned 硬项（软副词『轻轻』）在「」内不豁免，仍计入 issues。"""
        text = "「他轻轻叹了口气。」"
        r = report_ai_flavor(text)
        hit = any("轻轻" in it["value"] for it in r["issues"])
        self.assertTrue(hit, "「」内的 banned 软副词『轻轻』应仍被计入 issues（不豁免）")

    def test_not_x_but_y_only_in_quote_no_soft_signal(self):
        """仅有引号内 not_x_but_y 时，软信号不应产生 aiish 告警。"""
        text = "「你不是英雄，而是懦夫。」"
        r = report_ai_flavor(text)
        self.assertEqual(r["aiish"]["count"], 0,
                         "全在引号内的 not_x_but_y 应被完全豁免")


# ============================================================
# 3) 终判弱信号红线（最关键）
# ============================================================
class TestFinalJudgeWeakSignal(unittest.TestCase):
    # 受控的统计层 / 叙事层（mock 掉，保证 verdict 确定性，避免依赖 corpus 画像）
    STAT_PASS = {"humanity_score": 90.0}
    STAT_FAIL = {"humanity_score": 30.0}
    NAR_PASS = {"human_score": 80.0, "narrative_deviation": 0.1, "features": {}}
    NAR_FAIL = {"human_score": 30.0, "narrative_deviation": 0.9, "features": {}}

    def _run(self, bloom, ai_flavor, stat=STAT_PASS, nar=NAR_PASS):
        with mock.patch("tools.humanity_scorer.score_humanity", return_value=stat):
            with mock.patch("local_discriminator.score", return_value=nar):
                with mock.patch("local_discriminator.load_baseline", return_value={}):
                    with mock.patch("local_discriminator.narrative_rarity", return_value=0.0):
                        return triple_cross_judge("样本文本用于终判。",
                                                 bloom_result=bloom,
                                                 ai_flavor=ai_flavor)

    def test_pass_sample_plus_ai_flavor_never_fail(self):
        """本来 PASS 的样例 + ai_flavor 告警 → verdict 仍为 PASS/WARN，绝不 FAIL。"""
        tc = self._run(bloom=(False, None), ai_flavor=_make_alarm(1.0))
        self.assertIn(tc["verdict"], ("PASS", "WARN"))
        self.assertNotEqual(tc["verdict"], "FAIL")
        self.assertEqual(tc["layers"]["ai_flavor"]["verdict"], "WARN")
        self.assertLessEqual(tc["layers"]["ai_flavor"]["confidence"], 0.5)

    def test_pass_sample_stays_pass_with_strong_signal(self):
        """强 PASS（三层全 PASS）+ 最强 ai_flavor → 仍 PASS（弱信号无法翻盘）。"""
        tc = self._run(bloom=(False, None), ai_flavor=_make_alarm(1.0))
        self.assertEqual(tc["verdict"], "PASS")

    def test_fail_sample_plus_ai_flavor_still_fail(self):
        """本来 FAIL 的样例（bloom 命中 + 统计/叙事双 FAIL）+ ai_flavor → 终判仍 FAIL。"""
        tc = self._run(bloom=(True, "bloom-hit"),
                       ai_flavor=_make_alarm(1.0),
                       stat=self.STAT_FAIL, nar=self.NAR_FAIL)
        self.assertEqual(tc["verdict"], "FAIL",
                         "qiaomu 弱信号(WARN)绝不能把本就 FAIL 的终判翻成别的")
        # 注入层本身依旧是 WARN、conf≤0.5
        self.assertEqual(tc["layers"]["ai_flavor"]["verdict"], "WARN")
        self.assertLessEqual(tc["layers"]["ai_flavor"]["confidence"], 0.5)

    def test_no_ai_flavor_no_regression(self):
        """不传 ai_flavor → 行为与改动前一致：无 ai_flavor 层，verdict 确定性。"""
        with mock.patch("tools.humanity_scorer.score_humanity", return_value=self.STAT_PASS):
            with mock.patch("local_discriminator.score", return_value=self.NAR_PASS):
                with mock.patch("local_discriminator.load_baseline", return_value={}):
                    with mock.patch("local_discriminator.narrative_rarity", return_value=0.0):
                        tc = triple_cross_judge("样本文本。", bloom_result=(False, None))
        self.assertNotIn("ai_flavor", tc["layers"],
                         "不传 ai_flavor 时不应出现 ai_flavor 层（无回归）")
        self.assertEqual(tc["verdict"], "PASS")

    def test_severity_capped_at_point_five(self):
        """无论 severity 多大，ai_flavor confidence 封顶 0.5。"""
        tc = self._run(bloom=(False, None), ai_flavor=_make_alarm(999.0))
        self.assertLessEqual(tc["layers"]["ai_flavor"]["confidence"], 0.5)
        self.assertAlmostEqual(tc["layers"]["ai_flavor"]["confidence"], 0.5, places=3)

    def test_severity_zero_gives_floor(self):
        """severity=0 时 conf=0.2（≤0.5）。"""
        tc = self._run(bloom=(False, None), ai_flavor=_make_alarm(0.0))
        self.assertLessEqual(tc["layers"]["ai_flavor"]["confidence"], 0.5)
        self.assertGreaterEqual(tc["layers"]["ai_flavor"]["confidence"], 0.2)

    def test_consensus_unchanged_and_safe(self):
        """直接验证 _consensus：ai_flavor 仅向 WARN 桶累加，数学上不可能翻成 FAIL。"""
        # 三层全 PASS + ai_flavor WARN(0.5) → PASS 不变
        layers = {
            "literal": {"verdict": "PASS", "confidence": 0.95},
            "statistical": {"verdict": "PASS", "confidence": 0.7},
            "narrative": {"verdict": "PASS", "confidence": 0.6},
            "ai_flavor": {"verdict": "WARN", "confidence": 0.5},
        }
        v, _ = _consensus(layers)
        self.assertEqual(v, "PASS")

        # 三层 FAIL(0.7+0.6+0.6=1.9 明确>1.3) + ai_flavor WARN(0.5) → 仍 FAIL（WARN 无法压制）
        # 注：用三层 FAIL 以稳健越过 1.3 阈值（避免 0.7+0.6=1.2999… 浮点刚好低于 1.3 的边界歧义）
        layers2 = {
            "literal": {"verdict": "FAIL", "confidence": 0.7},
            "statistical": {"verdict": "FAIL", "confidence": 0.6},
            "narrative": {"verdict": "FAIL", "confidence": 0.6},
            "ai_flavor": {"verdict": "WARN", "confidence": 0.5},
        }
        v2, _ = _consensus(layers2)
        self.assertEqual(v2, "FAIL")

        # 边界：仅 literal PASS + 其余 WARN + ai_flavor WARN → WARN（不 FAIL）
        layers3 = {
            "literal": {"verdict": "PASS", "confidence": 0.95},
            "statistical": {"verdict": "WARN", "confidence": 0.5},
            "narrative": {"verdict": "WARN", "confidence": 0.3},
            "ai_flavor": {"verdict": "WARN", "confidence": 0.5},
        }
        v3, _ = _consensus(layers3)
        self.assertIn(v3, ("PASS", "WARN"))
        self.assertNotEqual(v3, "FAIL")
        self.assertEqual(_CONSENSUS_THRESHOLD, 1.3)


# ============================================================
# 4) CLI 与报告落盘
# ============================================================
class TestCLIAndReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.novels = _find_novels(max_count=60, max_bytes=60000)
        cls.novel = cls.novels[0] if cls.novels else None

    def _run_check(self, extra_args):
        import shutil
        import subprocess
        tmp = os.path.join(_ROOT, "output", "_qa_cli_story.txt")
        rep = tmp.replace(".txt", "_check_report.txt")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        shutil.copyfile(self.novel, tmp)
        try:
            proc = subprocess.run(
                [sys.executable, "check_story.py", tmp] + extra_args,
                cwd=_ROOT, capture_output=True, timeout=300,
            )
            out = ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", "replace")
            rf = open(rep, encoding="utf-8").read() if os.path.exists(rep) else ""
            return proc.returncode, out, rf
        finally:
            for p in (tmp, rep):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    def test_ai_flavor_cli_terminal_and_file(self):
        """--ai-flavor：退出码 0；终端与 _check_report.txt 均含『十二、去 AI 味报告』。"""
        self.assertTrue(self.novel, "未找到 corpus 小说")
        rc, out, rf = self._run_check(["--ai-flavor"])
        self.assertEqual(rc, 0, msg=f"check_story 退出码非0:\n{out[-2000:]}")
        self.assertIn("十二、去 AI 味报告", out, "终端缺少第十二节标题")
        # 任务硬性要求：报告落盘文件也必须含『十二、去 AI 味报告』
        self.assertIn("十二、去 AI 味报告", rf,
                      "报告文件(_check_report.txt)缺少『十二、去 AI 味报告』——"
                      "当前文件头仅写『去 AI 味报告』，与终端标签不一致")

    def test_no_ai_flavor_skips_section(self):
        """--no-ai-flavor：第十二节被跳过，其余报告节（如叙事偏离度）正常。"""
        self.assertTrue(self.novel, "未找到 corpus 小说")
        rc, out, rf = self._run_check(["--no-ai-flavor"])
        self.assertEqual(rc, 0)
        self.assertIn("已通过 --no-ai-flavor 关闭去 AI 味报告", out)
        self.assertNotIn("去 AI 味报告", rf, "--no-ai-flavor 下报告文件不应含第十二节")
        self.assertIn("叙事偏离度报告", rf, "其余报告节（十一、叙事偏离度）应正常输出")


# ============================================================
# 5) banned.json 首次被消费 + 无误杀
# ============================================================
class TestBannedConsumption(unittest.TestCase):
    def test_check_story_wires_load_banned(self):
        """check_story.py 须真正 import 并消费 load_banned / banned.json（死配置复活）。"""
        src = open(os.path.join(_ROOT, "check_story.py"), encoding="utf-8").read()
        self.assertIn("load_banned", src, "check_story 未加载 banned.json")
        self.assertIn("anti_ai_reporter", src, "check_story 未接入 anti_ai_reporter")

    def test_real_novel_reports_banned_hits_true_positive(self):
        """真实小说应被消费 banned.json 并报告硬项命中；且每个命中都是真阳性（无误杀）。"""
        path, text = _find_banned_hit_novel()
        self.assertTrue(path, "未在 corpus 中找到含 banned 命中的小说（请确认 banned.json 生效）")
        r = report_ai_flavor(text)
        self.assertTrue(r["issues"], "真实小说应触发 banned 硬项（证明 banned.json 已被消费）")
        # 真阳性校验：每个 issue 的值确实出现在文本中
        for it in r["issues"]:
            v = it["value"]
            if it["type"] == "pattern":
                self.assertTrue(re.search(v, text),
                                f"banned 正则误报（文本中找不到匹配）: {v}")
            else:
                self.assertIn(v, text,
                              f"banned 子串误报（文本中找不到）: {v}")
        # 抽查『不是X是Y / 软副词』类命中确属真阳性（非引号豁免逻辑误判产生的幻影）
        xy = [it for it in r["issues"] if "不是" in it["value"]]
        soft = [it for it in r["issues"] if any(w in it["value"] for w in ("轻轻", "缓缓", "微微", "悄悄"))]
        for it in xy + soft:
            self.assertTrue(re.search(it["value"], text) or it["value"] in text,
                            f"『不是X是Y/软副词』命中非真阳性: {it['value']}")


# ============================================================
# 6) 红线核验
# ============================================================
class TestRedLines(unittest.TestCase):
    def test_fusion_py_untouched(self):
        """tools/fusion.py（互消层红线）不得引用 anti_ai / 第十二节。"""
        src = open(os.path.join(_ROOT, "tools", "fusion.py"), encoding="utf-8").read()
        low = src.lower()
        self.assertNotIn("anti_ai", low, "fusion.py 不得引用 anti_ai")
        self.assertNotIn("第十二节", src, "fusion.py 不得引用第十二节")

    def test_requirements_only_jieba(self):
        """requirements.txt 仍是零新增依赖（仅 jieba）。"""
        lines = [ln.strip() for ln in
                 open(os.path.join(_ROOT, "requirements.txt"), encoding="utf-8").read().splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
        self.assertEqual(lines, ["jieba"], f"requirements.txt 不应变化: {lines}")

    def test_anti_ai_rules_no_corpus_leak(self):
        """anti_ai_rules.json 只存通用词典/正则/阈值，不得含 corpus 字面长句。"""
        data = json.load(open(os.path.join(_ROOT, "config", "anti_ai_rules.json"),
                              encoding="utf-8"))
        REGEX_META = set("[](){}|?*+.^$\\")
        SAFE_KEYS = {"_comment", "source", "version", "meta", "note",
                     "name", "type", "value", "detail"}

        def scan(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in SAFE_KEYS:
                        continue
                    scan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    scan(v, f"{path}[{i}]")
            elif isinstance(obj, str):
                if REGEX_META & set(obj):
                    # 正则串：剥离元字符后，连续中文不得是长句（>15 字）
                    stripped = re.sub(r"[\[\](){}|?*+.^$\\],;:：，。！？、\n\t ]", "", obj)
                    max_han = max((len(m) for m in re.findall(r"[一-鿿]+", stripped)), default=0)
                    self.assertLessEqual(max_han, 15,
                                         f"疑似 corpus 字面泄露(正则内含长句) @ {path}: {obj!r}")
                else:
                    # 纯词典/标点/模板 token：须为短串（≤8 字），不得是句子
                    self.assertLessEqual(len(obj), 8,
                                         f"疑似 corpus 字面泄露(长串) @ {path}: {obj!r}")

        scan(data)


# ============================================================
# 7) 规格偏差（qiaomu oracle 对照）——预期失败，作为源码 Bug 反馈
# ============================================================
class TestQiaomuFidelityDeviations(unittest.TestCase):
    def test_hook_counts_only_first_three_paragraphs(self):
        """qiaomu oracle：hook_hits(前3段)==0 才告警。前3段无 hook、第4段才有时须触发 no_hook。

        当前实现对全文计数（sum(text.count)），导致真实故事几乎必含 16 个常见 hook 字之一，
        no_hook 告警形同虚设 → 与 oracle/设计§7-②/任务断言不符。
        """
        sample = ("第一章，阳光照在窗台上。\n"
                  "她走进房间，倒了一杯水放在桌上。\n"
                  "门外传来脚步声，走廊的灯亮着。\n"
                  "死寂的夜里，血色的月光照在屏幕上。")  # hook 字(死/血)仅在第4段
        r = report_ai_flavor(sample)
        # 按 qiaomu 口径：前3段 hook==0 → 应触发 no_hook
        self.assertIn("no_hook", r["flags"],
                      "前3段无 hook 字但第4段才有时，应按 qiaomu oracle 触发 no_hook 告警")


if __name__ == "__main__":
    unittest.main(verbosity=2)
