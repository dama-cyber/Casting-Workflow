# -*- coding: utf-8 -*-
"""P1-3 残差闭环验证：fusion.py pick_files 必须大小写不敏感地纳入 .TXT/.Txt 文件。"""
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fusion import pick_files


class TestFusionCaseInsensitive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fusion_case_")
        self.corpus = os.path.join(self.tmp, "corpus")
        self.cat = os.path.join(self.corpus, "05_test")
        os.makedirs(self.cat)
        # 混合大小写 + 非 txt 干扰项
        for fn in ["a.txt", "b.TXT", "c.Txt", "d.md", "e.pdf"]:
            with open(os.path.join(self.cat, fn), "w", encoding="utf-8") as f:
                f.write("测试内容")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_picks_mixed_case_txt(self):
        cands = pick_files("05_test", 5, corpus_root=self.corpus)
        picked = {os.path.basename(p) for p in cands}
        # 必须纳入 b.TXT 和 c.Txt（原先大小写敏感会漏）
        self.assertIn("b.TXT", picked)
        self.assertIn("c.Txt", picked)
        self.assertIn("a.txt", picked)
        # 非 txt 必须排除
        self.assertNotIn("d.md", picked)
        self.assertNotIn("e.pdf", picked)
        self.assertEqual(len(picked), 3)

    def test_real_corpus_delta(self):
        """真实 corpus：大小写不敏感纳入的候选数 >= 敏感版本。"""
        root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "corpus"
        )
        if not os.path.isdir(root):
            self.skipTest("corpus 不存在")
        old_n = new_n = 0
        for d in os.listdir(root):
            sd = os.path.join(root, d)
            if not os.path.isdir(sd):
                continue
            for fn in os.listdir(sd):
                if fn.endswith(".txt"):
                    old_n += 1
                if fn.lower().endswith(".txt"):
                    new_n += 1
        # 真实数据存在 90 个 .TXT + 2 个 .Txt，new 必 > old
        self.assertGreater(new_n, old_n)
        self.assertGreaterEqual(new_n - old_n, 92)


if __name__ == "__main__":
    unittest.main(verbosity=2)
