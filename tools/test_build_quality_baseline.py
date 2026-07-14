# -*- coding: utf-8 -*-
"""qiaomu E build_quality_baseline 统计逻辑单测（合成文本，不依赖 corpus 全量）"""
import os
import sys
import unittest

_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import build_quality_baseline as B


class TestStat(unittest.TestCase):
    def test_pct(self):
        v = list(range(100))
        self.assertEqual(B._pct(v, 0.10), 10)
        self.assertEqual(B._pct(v, 0.50), 50)
        self.assertEqual(B._pct(v, 0.90), 89)
        self.assertEqual(B._pct([], 0.5), 0.0)

    def test_stat(self):
        s = B._stat([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(s["n"], 10)
        self.assertIn("p10", s)
        self.assertIn("p90", s)


class TestTriggerAndSuggest(unittest.TestCase):
    def test_high_direction(self):
        dl = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        trig, sug = B._trigger_rate_and_suggest(dl, 5.0, "high")
        self.assertEqual(trig, 0.5)   # >5 的有 5 个 /10
        self.assertEqual(sug, 9.0)    # p90

    def test_low_direction(self):
        dl = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        trig, sug = B._trigger_rate_and_suggest(dl, 5.0, "low")
        self.assertEqual(trig, 0.4)   # <5 的有 4 个 /10
        self.assertEqual(sug, 2.0)    # p10 = v[int(round(0.10*9))]=v[1]=2


class TestAdvisoryDensities(unittest.TestCase):
    def test_collect(self):
        rules = {"metrics": {
            "micro_action": {"enabled": True, "terms": ["眼皮一跳"], "per_1k_chars": 4.0},
            "metaphor_density": {"enabled": True, "markers": ["像"], "max_per_1k_chars": 8.0},
            "low_connectivity": {"enabled": True, "connectors": ["但是"], "min_per_1k_chars": 2.0},
            "official_tone": {"enabled": True, "terms": ["根据"], "per_1k_chars": 3.0},
            "fragment_short": {"enabled": True, "short_sentence_max_visible_chars": 5, "max_ratio": 0.18},
            "over_refined_short_para": {"enabled": True, "short_para_max_visible_chars": 10, "max_ratio": 0.20},
        }}
        text = "眼" * 1000 + "眼皮一跳眼皮一跳"
        dens = B._collect_advisory_densities(text, 1.0, rules)
        self.assertAlmostEqual(dens["micro_action"], 2.0, places=2)
        self.assertIn("fragment_short", dens)
        self.assertIn("over_refined_short_para", dens)


if __name__ == "__main__":
    unittest.main(verbosity=2)
