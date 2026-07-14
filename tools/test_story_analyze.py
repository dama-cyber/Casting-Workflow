# -*- coding: utf-8 -*-
"""story_analyze.py 确定性骨架生成器回归测试。

覆盖 QA 反馈的回归盲区：
  1. 短/长篇路由（auto 按字数 + 显式 --length）
  2. 空输入处理
  3. 章节切分正则（第X章 / Chapter X / N. 标题）
  4. --force 覆盖语义
  5. jieba 缺失回退
  6. 20000 阈值边界
  7. 只写 --out、绝不触碰 corpus/ 的副作用隔离
  8. 输出 schema 与 story_analyze.OUTPUT_SCHEMA 常量一致性
"""
import os
import sys
import json
import shutil
import tempfile
import contextlib
import io
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import story_analyze as si

# 构造任意长度中文文本（无「章」字，避免污染章节切分）
_BASE = "山有木兮木有枝，心悦君兮君不知。清风明月无人管，并作南楼一味凉。"
CHAPTERED = """第一章 风起青萍
（开篇内容）
第二章 云涌沧溟
（中段内容）
第三章 浪卷星河
（高潮内容）
"""


def _make_text(n: int) -> str:
    """返回正好 n 个字符的中文串。"""
    return (_BASE * ((n // len(_BASE)) + 1))[:n]


class TestStoryImportRouting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="story_analyze_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, text: str) -> str:
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_auto_short_routes_to_short_skeleton(self):
        src = self._write("short.txt", _make_text(3000))
        rc = si.main(["--input", src, "--out", self.tmp, "--book", "短篇书"])
        self.assertEqual(rc, 0)
        root = os.path.join(self.tmp, "短篇书")
        # 短篇产物：_meta.json 存在，_progress.md 不应存在
        self.assertTrue(os.path.isfile(os.path.join(root, "_meta.json")))
        self.assertFalse(os.path.isfile(os.path.join(root, "_progress.md")))
        with open(os.path.join(root, "_meta.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["length_type"], "short")

    def test_auto_long_routes_to_long_skeleton(self):
        src = self._write("long.txt", _make_text(25000))
        rc = si.main(["--input", src, "--out", self.tmp, "--book", "长篇书"])
        self.assertEqual(rc, 0)
        root = os.path.join(self.tmp, "长篇书")
        # 长篇产物：_progress.md 存在，_meta.json 不应存在
        self.assertTrue(os.path.isfile(os.path.join(root, "_progress.md")))
        self.assertFalse(os.path.isfile(os.path.join(root, "_meta.json")))

    def test_explicit_length_overrides_auto(self):
        # 显式 --length short 即便文本很长也走短篇
        src = self._write("big.txt", _make_text(25000))
        si.main(["--input", src, "--out", self.tmp, "--book", "强制短篇", "--length", "short"])
        root = os.path.join(self.tmp, "强制短篇")
        self.assertTrue(os.path.isfile(os.path.join(root, "_meta.json")))
        self.assertFalse(os.path.isfile(os.path.join(root, "_progress.md")))

        # 显式 --length long 即便文本很短也走长篇
        src2 = self._write("small.txt", _make_text(800))
        si.main(["--input", src2, "--out", self.tmp, "--book", "强制长篇", "--length", "long"])
        root2 = os.path.join(self.tmp, "强制长篇")
        self.assertTrue(os.path.isfile(os.path.join(root2, "_progress.md")))


class TestStoryImportEmptyInput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="story_analyze_empty_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_file_raises(self):
        p = os.path.join(self.tmp, "empty.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("")
        with self.assertRaises(SystemExit):
            si.main(["--input", p, "--out", self.tmp, "--book", "空书"])

    def test_whitespace_only_raises(self):
        p = os.path.join(self.tmp, "ws.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("   \n\n  ")
        with self.assertRaises(SystemExit):
            si.main(["--input", p, "--out", self.tmp, "--book", "空白书"])

    def test_nonexistent_path_raises(self):
        with self.assertRaises(SystemExit):
            si.main(["--input", os.path.join(self.tmp, "nope.txt"),
                     "--out", self.tmp, "--book", "无此书"])

    def test_empty_dir_raises(self):
        d = os.path.join(self.tmp, "emptydir")
        os.makedirs(d)
        with self.assertRaises(SystemExit):
            si.main(["--input", d, "--out", self.tmp, "--book", "空目录"])


class TestChapterSplitRegex(unittest.TestCase):
    def test_detect_three_marker_styles(self):
        text = "第一章 起\n内容\nChapter 3 转\n内容\n12. 终章\n内容\n第10章 余波\n内容"
        marks = si._detect_markers(text)
        nums = [m[1] for m in marks]
        # 三种风格均被识别：中文「第X章」/ 英文「Chapter N」/ 数字「N. 标题」
        self.assertIn("第一章", nums)
        self.assertIn("Chapter 3", nums)
        self.assertTrue(any(n.startswith("12.") for n in nums), "数字编号风格未被识别")
        self.assertIn("第10章", nums)
        self.assertEqual(len(marks), 4)

    def test_split_multi_chapter(self):
        chapters = si.split_chapters(CHAPTERED, None)
        self.assertEqual(len(chapters), 3)
        nums = [c[0] for c in chapters]
        self.assertEqual(nums, ["第一章", "第二章", "第三章"])
        # 第1章内容应包含「开篇内容」
        self.assertIn("开篇内容", chapters[0][2])

    def test_split_single_marker_fallback(self):
        # 只有一个章节标记 → 整体单章回退
        text = "第一章 唯一\n这是全部正文，没有后续章节标记。"
        chapters = si.split_chapters(text, None)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0][0], "第1章")
        self.assertEqual(chapters[0][1], "全文")

    def test_split_dir_input_per_file(self):
        tmp = tempfile.mkdtemp(prefix="chap_dir_")
        try:
            fa = os.path.join(tmp, "a.txt")
            fb = os.path.join(tmp, "b.txt")
            with open(fa, "w", encoding="utf-8") as f:
                f.write("甲篇内容")
            with open(fb, "w", encoding="utf-8") as f:
                f.write("乙篇内容")
            chapters = si.split_chapters("ignored", [fa, fb])
            self.assertEqual(len(chapters), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestForceOverwrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="story_analyze_force_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_force_on_existing_dir_raises(self):
        src = os.path.join(self.tmp, "s.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write(_make_text(3000))
        si.main(["--input", src, "--out", self.tmp, "--book", "覆盖书"])
        # 二次运行（无 --force）应拒绝
        with self.assertRaises(SystemExit):
            si.main(["--input", src, "--out", self.tmp, "--book", "覆盖书"])

    def test_force_overwrites(self):
        src = os.path.join(self.tmp, "s.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write(_make_text(3000))
        si.main(["--input", src, "--out", self.tmp, "--book", "覆盖书"])
        rc = si.main(["--input", src, "--out", self.tmp, "--book", "覆盖书", "--force"])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "覆盖书", "_meta.json")))


class TestJiebaFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="story_analyze_jieba_")
        self._orig = si._HAS_JIEBA

    def tearDown(self):
        si._HAS_JIEBA = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_compute_stats_fallback_keys(self):
        si._HAS_JIEBA = False
        stats = si.compute_stats("测试文本，用于统计回退路径。")
        for k in ("total_chars", "total_words", "avg_sentence_len",
                 "short_sentence_len_ratio", "long_sentence_len_ratio",
                 "sentence_count", "top_keywords"):
            self.assertIn(k, stats)
        self.assertEqual(stats["total_chars"], len("测试文本，用于统计回退路径。"))

    def test_main_emits_fallback_warning(self):
        si._HAS_JIEBA = False
        src = os.path.join(self.tmp, "s.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write(_make_text(3000))
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = si.main(["--input", src, "--out", self.tmp, "--book", "回退书"])
        self.assertEqual(rc, 0)
        self.assertIn("jieba", buf.getvalue())


class TestLongThresholdBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="story_analyze_thr_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, text: str) -> str:
        p = os.path.join(self.tmp, "t.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_exactly_threshold_is_long(self):
        src = self._write(_make_text(20000))  # >= LONG_THRESHOLD
        si.main(["--input", src, "--out", self.tmp, "--book", "边界长"])
        root = os.path.join(self.tmp, "边界长")
        self.assertTrue(os.path.isfile(os.path.join(root, "_progress.md")))
        self.assertFalse(os.path.isfile(os.path.join(root, "_meta.json")))

    def test_below_threshold_is_short(self):
        src = self._write(_make_text(19999))  # < LONG_THRESHOLD
        si.main(["--input", src, "--out", self.tmp, "--book", "边界短"])
        root = os.path.join(self.tmp, "边界短")
        self.assertTrue(os.path.isfile(os.path.join(root, "_meta.json")))
        self.assertFalse(os.path.isfile(os.path.join(root, "_progress.md")))


class TestSideEffectIsolation(unittest.TestCase):
    """只写 --out，绝不触碰 corpus/。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="story_analyze_iso_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_does_not_touch_corpus(self):
        # 预先在 --out 内放置一个 corpus/ 含哨兵文件
        corpus = os.path.join(self.tmp, "corpus")
        os.makedirs(corpus)
        sentinel = os.path.join(corpus, "DO_NOT_TOUCH.txt")
        with open(sentinel, "w", encoding="utf-8") as f:
            f.write("orig")

        src = os.path.join(self.tmp, "s.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write(_make_text(3000))

        rc = si.main(["--input", src, "--out", self.tmp, "--book", "隔离书"])
        self.assertEqual(rc, 0)

        # corpus/ 未被改动：哨兵仍在、目录内仍仅此一文件
        self.assertTrue(os.path.isfile(sentinel))
        self.assertEqual(os.listdir(corpus), ["DO_NOT_TOUCH.txt"])
        # 产物下不应生成名为 corpus 的子目录
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "隔离书", "corpus")))


class TestOutputSchemaConsistency(unittest.TestCase):
    """输出文件树须与 story_analyze.OUTPUT_SCHEMA 常量约定一致。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="story_analyze_schema_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, text: str) -> str:
        p = os.path.join(self.tmp, "s.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_long_schema_matches_contract(self):
        src = self._write(_make_text(25000))
        si.analyze(["--input", src, "--out", self.tmp, "--book", "长篇契约"])
        root = os.path.join(self.tmp, "长篇契约")
        for rel in si.OUTPUT_SCHEMA["long"]:
            full = os.path.join(root, rel)
            if rel.endswith("/"):
                self.assertTrue(os.path.isdir(full), f"长篇骨架缺失约定目录: {rel}")
            else:
                self.assertTrue(os.path.isfile(full), f"长篇骨架缺失约定文件: {rel}")

    def test_short_schema_matches_contract(self):
        src = self._write(_make_text(3000))
        si.analyze(["--input", src, "--out", self.tmp, "--book", "短篇契约"])
        root = os.path.join(self.tmp, "短篇契约")
        for rel in si.OUTPUT_SCHEMA["short"]:
            full = os.path.join(root, rel)
            if rel.endswith("/"):
                self.assertTrue(os.path.isdir(full), f"短篇骨架缺失约定目录: {rel}")
            else:
                self.assertTrue(os.path.isfile(full), f"短篇骨架缺失约定文件: {rel}")
        with open(os.path.join(root, "_meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta["length_type"], "short")
        self.assertEqual(meta["chapter_count"], 1)
        self.assertEqual(meta["schema_version"], si.SCHEMA_VERSION)
        self.assertIn("structure_counts", meta)


if __name__ == "__main__":
    unittest.main(verbosity=2)
