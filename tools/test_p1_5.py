# -*- coding: utf-8 -*-
"""P1-5 索引一致性校验单测：审计 --corpus 索引未校验快照 hash 的闭环验证。

验证点：
  1. 构建后索引与 corpus 一致 → validate 返回 consistent=True
  2. 新增语料文件 → validate 返回 consistent=False（file_count 变）
  3. 删除语料文件 → validate 返回 consistent=False（file_count 变）
  4. 旧版索引（meta 无 corpus_snapshot）→ validate 跳过（consistent=True，不误报）
  5. bloom_check 在索引不一致时追加"[索引一致性 WARN]"且 fail=False（非破坏性）
"""
import os, sys, json, io, tempfile, shutil
import unittest

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)
from bloom_guard import BloomGuard, _collect_corpus, _corpus_snapshot, bloom_check


class TestP1_5(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.corpus = os.path.join(self.root, "corpus")
        self.cache = os.path.join(self.root, "cache")
        os.makedirs(self.corpus)
        os.makedirs(self.cache)
        for i in range(3):
            with io.open(os.path.join(self.corpus, f"f{i}.txt"), "w", encoding="utf-8") as f:
                f.write("这是一段测试文本用于构建布隆索引的示例内容而已。" * 20)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _build(self):
        paths = _collect_corpus(self.corpus)
        g = BloomGuard()
        g.build(paths, self.cache, progress=False)
        return g

    def test_consistent(self):
        g = self._build()
        snap = g.validate_corpus_snapshot(self.corpus)
        self.assertTrue(snap["consistent"], msg=snap)
        self.assertEqual(snap["stored"]["file_count"], 3)
        self.assertEqual(snap["stored"]["total_bytes"], snap["current"]["total_bytes"])

    def test_inconsistent_after_add(self):
        g = self._build()
        with io.open(os.path.join(self.corpus, "f9.txt"), "w", encoding="utf-8") as f:
            f.write("新增的文本导致索引过期的例子内容。" * 20)
        snap = g.validate_corpus_snapshot(self.corpus)
        self.assertFalse(snap["consistent"], msg=snap)
        self.assertEqual(snap["current"]["file_count"], 4)

    def test_inconsistent_after_delete(self):
        g = self._build()
        os.remove(os.path.join(self.corpus, "f0.txt"))
        snap = g.validate_corpus_snapshot(self.corpus)
        self.assertFalse(snap["consistent"], msg=snap)
        self.assertEqual(snap["current"]["file_count"], 2)

    def test_no_snapshot_skip(self):
        g = self._build()
        meta_path = os.path.join(self.cache, "_bloom_meta.json")
        m = json.load(io.open(meta_path, encoding="utf-8"))
        self.assertIn("corpus_snapshot", m)
        del m["corpus_snapshot"]
        json.dump(m, io.open(meta_path, "w", encoding="utf-8"))
        g2 = BloomGuard.load(self.cache)
        snap = g2.validate_corpus_snapshot(self.corpus)
        self.assertTrue(snap["consistent"])
        self.assertEqual(snap["reason"], "索引无快照(旧版), 跳过校验")

    def test_bloom_check_warn_on_inconsistent(self):
        g = self._build()
        with io.open(os.path.join(self.corpus, "f9.txt"), "w", encoding="utf-8") as f:
            f.write("新增文本导致索引过期。" * 20)
        lines, fail = bloom_check("这是一段测试文本。", cache_dir=self.cache, corpus_dir=self.corpus)
        self.assertIn("索引一致性 WARN", lines, msg=lines)
        self.assertFalse(fail, msg="索引不一致校验不得翻 FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
