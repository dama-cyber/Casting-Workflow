# -*- coding: utf-8 -*-
"""
audit.py — 熔铸输出审计

用法:
    python audit.py story.txt [source1.txt source2.txt ...]

检查:
    - 禁用模式/模板
    - 标点禁令
    - 独创度(16字扫描 vs N篇源文)
"""

import sys, re, os, json, logging

# ── 同目录模块导入（确保从任意 cwd 运行都能找到 bloom_guard）
_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)
try:
    from bloom_guard import bloom_check as _bloom_check
    _BLOOM_OK = True
except Exception as e:
    logging.warning(f"audit: bloom_guard import failed: {e}")
    _BLOOM_OK = False

# 叙事稀有度降级弱判所需的叙事判别模块（延迟可用性探测；缺失时跳过该弱判，不影响主流程）
try:
    from local_discriminator import (  # noqa: F401
        extract_narrative_features as _nd_extract,
        narrative_rarity as _nd_rarity,
        load_baseline as _nd_load,
    )
    _ND_OK = True
except Exception as e:
    logging.warning(f"audit: local_discriminator import failed: {e}")
    _ND_OK = False

# 稀有度阈值（方向⑤ + 任务项6）
_RARITY_HIGH = 0.6   # 高稀有 → 更像人类原创 → 补偿 Bloom 对套话/成语的误命中
_RARITY_LOW = 0.35   # 低稀有 → 落入 AI 共享聚类 → 字面唯一也疑似套话结构

# ── 禁用清单：统一加载 config/banned.json（与 check_story 质检侧同源），缺失则回退硬编码 ──
_BANNED_JSON = os.path.normpath(os.path.join(_THIS, "..", "config", "banned.json"))
def _load_banned():
    try:
        with open(_BANNED_JSON, encoding="utf-8") as _f:
            _cfg = json.load(_f)
        _tmpl = list(_cfg.get("banned_templates", []))
        _patt = list(_cfg.get("banned_patterns", []))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning(f"audit: failed to load banned.json ({e}), using hardcoded fallback")
        _tmpl = ["眼中闪过", "嘴角勾起", "眼眶微红", "不可置信", "眼底闪过", "咬了咬唇"]
        _patt = []
    except Exception as e:
        logging.warning(f"audit: unexpected error loading banned.json: {e}")
        _tmpl = ["眼中闪过", "嘴角勾起", "眼眶微红", "不可置信", "眼底闪过", "咬了咬唇"]
        _patt = []
    # 安全网：保留原 audit 硬编码 4 禁用句式，避免收敛导致「的意义在于」等漏检回归
    for _legacy in ["对X而言", "一切都在", "一种说不出的", "的意义在于"]:
        if _legacy not in _tmpl:
            _tmpl.append(_legacy)
    return _tmpl, _patt
try:
    _BANNED_TEMPLATES, _BANNED_PATTERNS = _load_banned()
except Exception as e:
    logging.warning(f"audit: module-level _load_banned() failed: {e}, using empty fallback")
    _BANNED_TEMPLATES, _BANNED_PATTERNS = [], []

# 白名单词表豁免（核心 IP 质量扩展 · 方向 G）：命中 banned 但属世界观术语/绰号/口头禅则豁免。
# 复用 anti_ai_reporter.load_whitelist（同模块已含 banned 加载，零重型依赖）；缺失则空白名单。
try:
    from anti_ai_reporter import load_whitelist as _load_whitelist
    _WHITELIST = _load_whitelist()
except Exception as e:
    logging.warning(f"audit: whitelist loading failed: {e}")
    _WHITELIST = set()


def _apply_rarity_weakjudge(text, bloom_lines, bloom_fail, strict):
    """稀有度降级弱判（不破坏 Bloom 零模型位图逻辑，仅作辅助信号）。

    场景A（设计2.2）：Bloom 命中(strict→FAIL) 且叙事稀有度高 → FAIL 降级为 WARN，
        补偿「套话/成语」被 Bloom 误判为抄袭。
    场景B（任务项6）：Bloom 零命中(PASS) 且叙事稀有度低（落入 AI 共享聚类）→
        追加 WARN 提示「疑似套话结构」，不强制 FAIL（弱判）。

    返回 (bloom_lines, bloom_fail, rarity)。
    """
    rarity = 0.0
    if not _ND_OK:
        return bloom_lines, bloom_fail, rarity
    try:
        base = _nd_load()
        feats = _nd_extract(text)
        rarity = _nd_rarity(feats, base)
    except Exception as e:
        logging.warning(f"audit: rarity weak judge failed: {e}")
        return bloom_lines, bloom_fail, rarity

    if bloom_fail and rarity >= _RARITY_HIGH:
        # 场景A：strict 下 FAIL 降级为 WARN
        bloom_fail = False
        if "FAIL" in bloom_lines:
            bloom_lines = bloom_lines.replace("FAIL", "WARN", 1)
        bloom_lines += (f"\n    [稀有度降级] 叙事稀有度={rarity} 较高，疑似套话/成语"
                        f"Bloom误命中 → 降级 WARN")
    elif (not bloom_fail) and rarity <= _RARITY_LOW:
        # 场景B：字面唯一但叙事落入 AI 共享聚类 → 追加 WARN 提示
        bloom_lines += (f"\n    [稀有度提示] Bloom零命中，但叙事稀有度={rarity} 偏低"
                        f"（落入AI共享聚类），疑似套话结构 [WARN]")
    return bloom_lines, bloom_fail, rarity


def count_chinese(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def audit_story(text):
    results = []
    zh = count_chinese(text)
    sentences = [s for s in re.split(r"[。！？]", text) if re.search(r"[\u4e00-\u9fff]", s)]
    n = len(sentences) or 1

    results.append(f"字数: {zh}  句数: {n}")
    results.append(f"！/句: {text.count('！')/n:.3f}  ，/句: {text.count('，')/n:.2f}")

    # 禁令
    issues = []
    if text.count("；") > 0:
        issues.append(f"分号 {text.count('；')}个")
    if text.count("！！！") > 0:
        issues.append(f"！！！ {text.count('！！！')}个")
    if text.count("？！") > 0:
        issues.append(f"？！ {text.count('？！')}个")

    # 禁用模式/模板：统一从 config/banned.json 加载（与 check_story 质检侧一致）；缺失则回退硬编码
    # 白名单词表豁免（方向 G）：命中 banned 但属合法世界观术语/绰号/口头禅则跳过（wl in matched）。
    wl = _WHITELIST

    def _whitelisted(matched):
        if not wl:
            return False
        m = matched.lower()
        return any(w in m for w in wl)

    for b in _BANNED_TEMPLATES:
        if b and b in text and not _whitelisted(b):
            issues.append(f"禁用模板: {b}")
    for pat in _BANNED_PATTERNS:
        try:
            _m = re.search(pat, text)
        except re.error:
            _m = pat and pat in text
        if _m:
            _hit = _m.group(0) if hasattr(_m, "group") else (_m or "")
            if not _whitelisted(_hit):
                issues.append(f"禁用句式: {pat}")

    if issues:
        results.append(f"\n问题 ({len(issues)}):")
        for iss in issues:
            results.append(f"  [FAIL] {iss}")
        fail = True
    else:
        results.append("\n固定规则: 全部通过 [OK]")
        fail = False

    return "\n".join(results), fail


def check_originality(story_text, source_paths):
    lines = []
    fail = False
    story_clean = re.sub(r"[，。！？：；、\s\d]", "", story_text)

    for sp in source_paths:
        with open(sp, "r", encoding="utf-8", errors="replace") as f:
            src = f.read()
        src_clean = re.sub(r"[，。！？：；、\s\d]", "", src)
        matches = 0
        for i in range(0, len(src_clean) - 16, 1):  # 全量扫描
            if story_clean.find(src_clean[i:i+16]) >= 0:
                matches += 1
        name = os.path.basename(sp)[:30]
        status = "OK" if matches == 0 else f"FAIL {matches}"
        if matches > 0:
            fail = True
        lines.append(f"  {name}: {status}")

    return "\n".join(lines), fail


def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python audit.py story.txt [source1.txt ...] [--corpus DIR] [--strict]")
        sys.exit(1)

    strict = "--strict" in args
    corpus_dir = None
    if "--corpus" in args:
        i = args.index("--corpus")
        if i + 1 < len(args):
            corpus_dir = args[i + 1]

    # story 路径 = 第一个非 flag / 非 corpus 目录参数
    story_path = None
    for a in args:
        if (not a.startswith("--")) and a != corpus_dir and a not in ("build", "check"):
            story_path = a
            break
    if not story_path:
        print("错误: 缺少待审计文本路径")
        sys.exit(1)

    source_paths = [a for a in args
                    if (not a.startswith("--")) and a != story_path
                    and a != corpus_dir and a not in ("build", "check")]

    with open(story_path, "r", encoding="utf-8") as f:
        text = f.read()

    result, rule_fail = audit_story(text)
    result += "\n"

    orig_fail = False
    bloom_fail = False
    if corpus_dir:
        # D1 修复: 全量审计目录模式（规避 ARG_MAX 无法传 10978 文件路径）
        # 内部走 Bloom 全 corpus 索引 —— 秒级、零假阴性、等价于 16 字全量扫描
        if _BLOOM_OK:
            bloom_lines, bloom_fail = _bloom_check(text, "data", strict=strict, corpus_dir=corpus_dir)
            bloom_lines, bloom_fail, _rar = _apply_rarity_weakjudge(text, bloom_lines, bloom_fail, strict)
            result += f"全量独创度 (vs 全corpus索引, 目录={corpus_dir}):\n{bloom_lines}\n"
        else:
            result += "全量审计不可用: bloom_guard 未加载，请检查 tools/bloom_guard.py\n"
            bloom_fail = True
    else:
        if source_paths:
            result += f"独创度 (vs {len(source_paths)}篇源文):\n"
            orig_lines, orig_fail = check_originality(text, source_paths)
            result += orig_lines + "\n"
        # v6.3: Bloom 反查维度（全 corpus 索引，零模型）
        if _BLOOM_OK:
            bloom_lines, bloom_fail = _bloom_check(text, "data", strict=strict, corpus_dir="corpus")
            bloom_lines, bloom_fail, _rar = _apply_rarity_weakjudge(text, bloom_lines, bloom_fail, strict)
            result += f"{bloom_lines}\n"

    out_path = story_path.replace(".txt", "_audit.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"审计完成 -> {out_path}")

    # D4 修复: 退出码 (CI 友好)
    if rule_fail or orig_fail or bloom_fail:
        print("审计结果: FAIL")
        sys.exit(1)
    print("审计结果: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
