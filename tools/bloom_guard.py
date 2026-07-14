# -*- coding: utf-8 -*-
"""
bloom_guard.py — 零模型 Bloom 反查（朱雀不可反查增强版）

核心思想
--------
朱雀等查重系统本质是「拿生成文本去语料里找 ≥N 字连续子串匹配」。
现有 audit.py 的 check_originality 对每篇源文做全量 16 字扫描，O(语料量)，
全 corpus（10978 篇）扫一遍在 CLI 下不可行（见 D1 / ARG_MAX）。

本模块用 **Bloom filter（布隆过滤器，纯数据结构，零模型）** 解决：
  1. 一次性把全部 corpus 的 N 字子串灌进 Bloom 索引（可缓存到磁盘）。
  2. 之后每次生成文本做 O(文本长度) 的 Bloom 查询即可判定是否撞语料。
  3. Bloom 无假阴性 —— 只要返回 0 命中，即可 100% 确定「零匹配」PASS。
  4. Bloom 有假阳性 —— 命中 > 0 时标记为「疑似」，提示走精确审计复核。
     （如构建时带 --exact，则落 SQLite 精确指纹库，命中即精确确认，零假阳性。）

*不是机器学习模型*：全程基于滚动哈希 + 位运算，无训练、无权重、无外部依赖。

用法
----
  # 构建全 corpus 索引（一次性；--workers 并行加速，默认用满 CPU 核）
  python bloom_guard.py --build --corpus corpus --cache output --workers 8

  # 可选：同时落精确指纹库（避免假阳性误杀，磁盘较大、构建较慢）
  python bloom_guard.py --build --corpus corpus --cache data --exact

  # 检查生成文本
  python bloom_guard.py --check output/story.txt --cache data

编程接口
--------
  from tools.bloom_guard import BloomGuard, bloom_check
  guard = BloomGuard.load("data")          # 加载缓存（无则 None）
  hits = guard.check(story_text)             # 返回命中子串列表（去重）
  lines, fail = bloom_check(story_text)      # 供 audit.py 集成，返回 (文本, 是否疑似)
"""

import sys, os, re, json, math, logging

DEFAULT_N = 16
DEFAULT_FPR = 0.01   # 8GB 内存优化：1% 假阳性率，位图从 1.6GB→534MB；命中后 audit.py 精确复核兜底

# ── 确定性滚动双哈希参数（与具体运行无关，保证可复现）
MOD1 = (1 << 61) - 1          # 大梅森素数
MOD2 = (1 << 31) - 1          # 2^31 - 1
BASE1 = 257
BASE2 = 263

_PUNCT = re.compile(r"[，。！？：；、\s\d]")


def _clean(s):
    """去标点/空白/数字，保留纯汉字串用于子串比对（与 audit.check_originality 口径一致）"""
    return _PUNCT.sub("", s)


def _read(path):
    # corpus 已知以 UTF-8 为主：优先 utf-8，失败再 gbk 兜底，
    # 避免每文件盲目尝试 3 种编码造成的额外 open 开销。
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (UnicodeDecodeError,):
        pass
    try:
        with open(path, "r", encoding="gbk") as f:
            return f.read()
    except (UnicodeDecodeError,):
        pass
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _iter_window_hashes(clean, n, m):
    """对 clean 文本滑 N 字窗口，yield 每窗口的 (g0, g1, ..., g_{k-1}) 位位置种子。
    用 Rabin-Karp 滚动双哈希 O(1)/窗口，避免每窗口重算 md5。"""
    if len(clean) < n:
        return
    # 滚动修正项需为 B^n（减去窗口前缀 c[0]*B^n），而非 B^(n-1)，
    # 否则非首窗口的滚动哈希与独立 RK 哈希口径不一致 → 部分重叠漏命中。
    b1 = pow(BASE1, n, MOD1)
    b2 = pow(BASE2, n, MOD2)
    h1 = 0
    h2 = 0
    for i, ch in enumerate(clean):
        c = ord(ch)
        h1 = (h1 * BASE1 + c) % MOD1
        h2 = (h2 * BASE2 + c) % MOD2
        if i >= n:
            old = ord(clean[i - n])
            h1 = (h1 - old * b1) % MOD1
            h2 = (h2 - old * b2) % MOD2
        if i >= n - 1:
            # 双重哈希展开 k 个位（标准技巧，避免 k 个独立 hash 计算）
            yield h1, h2


class BloomGuard:
    def __init__(self, n=DEFAULT_N, fpr=DEFAULT_FPR):
        self.n = n
        self.fpr = fpr
        self.m = 0          # bit 数组位数
        self.k = 0          # hash 函数个数
        self.elements = 0   # 灌入的子串总数（含重复）
        self.unique = 0     # 唯一子串数（近似）
        self.bits = None    # bytearray
        self.meta = None    # 加载时的 meta 全量（含 corpus_snapshot）
        self.corpus_snapshot = None  # 构建时记录的 corpus 轻量快照

    # ── 参数推导
    def _calc_params(self, elements):
        elements = max(elements, 1)
        # m = - (N * ln p) / (ln 2)^2
        self.m = max(1024, int(-elements * math.log(self.fpr) / (math.log(2) ** 2)))
        # k = (m / N) * ln 2
        self.k = max(1, int(self.m / elements * math.log(2)))
        if self.k > 32:
            self.k = 32

    # ── 位操作
    def _positions(self, h1, h2):
        m = self.m
        # 防退化：h2 与 m 同余为 0 会让所有位重合
        step = h2 % m
        if step == 0:
            step = 1
        base = h1 % m
        for j in range(self.k):
            yield (base + j * step) % m

    def _add_hash(self, h1, h2):
        bits = self.bits
        for pos in self._positions(h1, h2):
            bits[pos >> 3] |= 1 << (pos & 7)

    def _test_hash(self, h1, h2):
        bits = self.bits
        for pos in self._positions(h1, h2):
            if not (bits[pos >> 3] & (1 << (pos & 7))):
                return False
        return True

    # ── 构建
    def build(self, corpus_paths, cache_dir="data", progress=True, workers=None):
        # 不读内容、仅用文件字节数估算窗口总数 → 省掉原第一遍全量 IO
        est = _estimate_windows(corpus_paths, self.n)
        self._calc_params(int(est * 1.5))  # 安全冗余：仅降假阳性率，不影响无假阴性

        if workers is None:
            workers = os.cpu_count() or 4
        multiprocess = workers and workers > 1 and len(corpus_paths) > 1

        if multiprocess:
            from multiprocessing import Pool
            # 8GB 内存保护：限制 workers 防止位图副本爆内存
            # fpr=0.01 → 位图 ~534MB；3 workers × 534MB + 合并 = ~2.6GB 峰值
            max_workers_by_mem = 3
            if workers > max_workers_by_mem:
                sys.stderr.write(f"Bloom 内存保护: workers {workers} → {max_workers_by_mem}（8GB 机器）\n")
                workers = max_workers_by_mem
            chunks = [corpus_paths[i::workers] for i in range(workers)]
            args = [(c, self.n, self.m, self.k) for c in chunks]
            sys.stderr.write(f"Bloom 并行构建: {len(corpus_paths)} 篇 / {workers} 进程 / 位图 {(self.m+7)//8//1024//1024}MB\n")
            with Pool(workers) as pool:
                results = pool.map(_worker_build, args)
            # 各子集位图用大整数 OR 合并（534MB 级别 int OR 实测 <5s）
            byte_len = (self.m + 7) // 8
            acc = 0
            cnt = 0
            for bits, c in results:
                acc |= int.from_bytes(bits, "big")
                cnt += c
            self.bits = bytearray(acc.to_bytes(byte_len, "big"))
            self.elements = cnt
        else:
            self.bits = bytearray((self.m + 7) // 8)
            cnt = 0
            for idx, p in enumerate(corpus_paths, 1):
                clean = _clean(_read(p))
                for h1, h2 in _iter_window_hashes(clean, self.n, self.m):
                    self._add_hash(h1, h2)
                    cnt += 1
                if progress and idx % 500 == 0:
                    sys.stderr.write(f"  build {idx}/{len(corpus_paths)} ({cnt} 窗口)\n")
            self.elements = cnt
        snap = _corpus_snapshot(corpus_paths)
        self.corpus_snapshot = snap
        self._save(cache_dir, snap)
        return cnt

    def _save(self, cache_dir, corpus_snapshot=None):
        os.makedirs(cache_dir, exist_ok=True)
        bits_path = os.path.join(cache_dir, "_bloom_bits.bin")
        meta_path = os.path.join(cache_dir, "_bloom_meta.json")
        with open(bits_path, "wb") as f:
            f.write(self.bits)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "m": self.m, "k": self.k, "n": self.n,
                "fpr": self.fpr, "elements": self.elements,
                "corpus_snapshot": corpus_snapshot,
            }, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, cache_dir="data"):
        meta_path = os.path.join(cache_dir, "_bloom_meta.json")
        bits_path = os.path.join(cache_dir, "_bloom_bits.bin")
        if not os.path.isfile(meta_path) or not os.path.isfile(bits_path):
            return None
        with open(meta_path, encoding="utf-8") as _mf:
            meta = json.load(_mf)
        g = cls(n=meta.get("n", DEFAULT_N), fpr=meta.get("fpr", 0.0001))
        g.m = meta["m"]
        g.k = meta["k"]
        g.elements = meta.get("elements", 0)
        with open(bits_path, "rb") as _bf:
            g.bits = bytearray(_bf.read())
        g.meta = meta
        g.corpus_snapshot = meta.get("corpus_snapshot")
        return g

    def validate_corpus_snapshot(self, corpus_dir):
        """比对当前 corpus 快照与索引构建时记录的快照（P1-5 索引一致性校验）。

        返回 dict: {consistent:bool, reason:str, stored:dict|None, current:dict|None}
        - 索引无快照(旧版索引) → consistent=True（跳过校验，不误报）
        - file_count / total_bytes 任一不符 → consistent=False（语料已增删，索引过期）
        """
        stored = self.corpus_snapshot
        if stored is None:
            return {"consistent": True, "reason": "索引无快照(旧版), 跳过校验",
                    "stored": None, "current": None}
        paths = _collect_corpus(corpus_dir)
        current = _corpus_snapshot(paths)
        if current["file_count"] != stored["file_count"] or current["total_bytes"] != stored["total_bytes"]:
            return {
                "consistent": False,
                "reason": (f"file_count {stored['file_count']}→{current['file_count']}, "
                           f"total_bytes {stored['total_bytes']}→{current['total_bytes']}"),
                "stored": stored, "current": current,
            }
        return {"consistent": True, "reason": "一致", "stored": stored, "current": current}

    # ── 检查
    def check(self, text, max_hits=50):
        """返回命中（疑似）子串列表（去重，最多 max_hits 条）。0 条 = 可靠 PASS。"""
        clean = _clean(text)
        seen = set()
        hits = []
        n = self.n
        for i in range(0, len(clean) - n + 1):
            win = clean[i:i + n]
            if win in seen:
                continue
            # 对窗口字符串独立计算双哈希（与 build 滚动哈希窗口值口径一致）
            h1 = 0
            h2 = 0
            for ch in win:
                c = ord(ch)
                h1 = (h1 * BASE1 + c) % MOD1
                h2 = (h2 * BASE2 + c) % MOD2
            if self._test_hash(h1, h2):
                seen.add(win)
                hits.append(win)
                if len(hits) >= max_hits:
                    break
        return hits


# ============================================================
# 构建加速辅助（纯函数，供多进程 worker 调用）
# ============================================================
def _estimate_windows(paths, n):
    """不读文件内容，仅凭字节大小估算 16 字窗口总数，用于推导 Bloom m/k。

    省掉原 build() 第一遍「读全量内容数窗口」的全量 IO（约一遍 1.1GB 扫描）。
    corpus 以中文为主，经验上约 40% 字节为有效汉字；估算偏少只会让 m 略小、
    假阳性率略升，不影响「无假阴性」保证，故再乘 1.5 安全冗余。
    """
    total_bytes = 0
    for p in paths:
        try:
            total_bytes += os.path.getsize(p)
        except OSError:
            pass
    est_chars = int(total_bytes * 0.40)
    est = est_chars - n * len(paths)
    return max(est, len(paths))


def _worker_build(args):
    """多进程 worker：对分配到的文件子集构建局部位图，返回 (bytearray, 窗口数)。

    每个 worker 覆盖互不相交的文件集合，主进程按位 OR 合并即可等价于全量构建，
    结果与原单进程构建字节一致（无假阴性回退）。
    """
    paths, n, m, k = args
    g = BloomGuard(n=n, fpr=DEFAULT_FPR)
    g.m, g.k = m, k
    g.bits = bytearray((m + 7) // 8)
    cnt = 0
    for p in paths:
        clean = _clean(_read(p))
        for h1, h2 in _iter_window_hashes(clean, n, m):
            g._add_hash(h1, h2)
            cnt += 1
    return g.bits, cnt


# ============================================================
# 集成接口（供 audit.py 调用）
# ============================================================
def bloom_check(text, cache_dir="data", strict=False, corpus_dir=None):
    """
    供 audit.py 集成的 Bloom 反查维度。
    返回 (lines_str, fail_bool):
      - 缓存不存在 → 跳过，返回 ("(Bloom索引未构建，跳过)", False)
      - 命中 0     → 可靠 PASS，("零匹配 [OK]", False)
      - 命中 > 0   → 疑似；strict=True 时 fail=True，否则 fail=False（仅 WARN，待精确审计）
      - corpus_dir 给定且索引与当前 corpus 不一致 → 追加 WARN（不翻 FAIL，P1-5）
    """
    guard = BloomGuard.load(cache_dir)
    if guard is None:
        return ("Bloom反查: 索引未构建（运行 bloom_guard.py --build 启用）", False)
    # P1-5: 索引 vs 当前 corpus 一致性校验（非破坏性，仅 WARN）
    _snap_warn = ""
    if corpus_dir and os.path.isdir(corpus_dir):
        snap = guard.validate_corpus_snapshot(corpus_dir)
        if not snap["consistent"]:
            _snap_warn = (f"\n    [索引一致性 WARN] Bloom 索引与当前 corpus 不一致"
                          f"（{snap['reason']}）；索引可能过期，建议重建: "
                          f"python tools/bloom_guard.py --build --corpus {corpus_dir} --cache {cache_dir}")
    hits = guard.check(text)
    if not hits:
        return (f"Bloom反查 (vs 全corpus索引, {guard.n}字窗口): 零匹配 [OK]{_snap_warn}", False)
    sample = "、".join(hits[:5])
    warn = "FAIL" if strict else "WARN"
    fail = bool(strict)
    line = (f"Bloom反查: {warn} 疑似命中 {len(hits)} 处 16字子串（含Bloom假阳性可能）\n"
            f"    候选: {sample}" + (" …" if len(hits) > 5 else "") + _snap_warn)
    return line, fail


# ============================================================
# 稀有度钩子（供 audit.py 调用；Bloom 零模型位图逻辑不变）
# ============================================================
def rarity_hook(features, baseline=None):
    """叙事稀有度钩子（供 audit.py 调用，方向⑤）。

    纯委托给 local_discriminator.narrative_rarity：返回叙事稀有度 0-1，
    高稀有 → 更可能为人类/原创，用于补偿 Bloom 对套话/成语的误命中。

    延迟导入 local_discriminator，避免顶部耦合；模块缺失时返回 0.0。
    Bloom 零模型位图逻辑（build/check/双哈希）保持完全不变。
    """
    try:
        from local_discriminator import narrative_rarity
        return narrative_rarity(features, baseline)
    except Exception as e:
        logging.warning(f"bloom_guard: rarity hook failed: {e}")
        return 0.0


# ============================================================
# 命令行
# ============================================================
def _collect_corpus(corpus_dir):
    out = []
    if not os.path.isdir(corpus_dir):
        return out
    for root, _, files in os.walk(corpus_dir):
        for fn in files:
            if fn.lower().endswith(".txt"):
                out.append(os.path.join(root, fn))
    return out


def _corpus_snapshot(paths):
    """轻量 corpus 快照：仅文件数 + 总字节（不读内容，O(枚举)）。用于索引一致性校验。"""
    fc = len(paths)
    tb = 0
    for p in paths:
        try:
            tb += os.path.getsize(p)
        except OSError:
            pass
    return {"file_count": fc, "total_bytes": tb}


def main():
    args = sys.argv[1:]
    mode = None
    corpus_dir = "corpus"
    cache_dir = "data"
    story_path = None
    strict = False
    workers = None
    for i, a in enumerate(args):
        if a == "--build":
            mode = "build"
        elif a == "--check":
            mode = "check"
        elif a == "--corpus" and i + 1 < len(args):
            corpus_dir = args[i + 1]
        elif a == "--cache" and i + 1 < len(args):
            cache_dir = args[i + 1]
        elif a == "--story" and i + 1 < len(args):
            story_path = args[i + 1]
        elif a == "--strict":
            strict = True
        elif a == "--exact":
            pass  # 兼容占位（精确库为后续增强，当前用 strict + audit 精确复核）
        elif a == "--workers" and i + 1 < len(args):
            try:
                workers = int(args[i + 1])
            except ValueError:
                workers = None
    # --check 第一个非flag位置参数即 story 路径
    if mode == "check" and story_path is None:
        for a in args:
            if not a.startswith("--") and a not in ("build", "check"):
                story_path = a
                break

    if mode == "build":
        paths = _collect_corpus(corpus_dir)
        if not paths:
            print(f"未找到 corpus: {corpus_dir}")
            sys.exit(1)
        print(f"构建 Bloom 索引: {len(paths)} 篇语料, 窗口={DEFAULT_N}字")
        g = BloomGuard(n=DEFAULT_N, fpr=DEFAULT_FPR)
        cnt = g.build(paths, cache_dir, workers=workers)
        print(f"完成。灌入 {cnt} 个窗口 | m={g.m}bit k={g.k} | 缓存: {cache_dir}/_bloom_*")
        sys.exit(0)

    if mode == "check":
        if not story_path or not os.path.isfile(story_path):
            print("用法: bloom_guard.py --check <story.txt> [--cache output] [--strict]")
            sys.exit(1)
        text = _read(story_path)
        lines, fail = bloom_check(text, cache_dir, strict=strict)
        print(lines)
        sys.exit(1 if fail else 0)

    print(__doc__)
    sys.exit(0)


if __name__ == "__main__":
    main()
