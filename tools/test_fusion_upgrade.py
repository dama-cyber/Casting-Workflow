# -*- coding: utf-8 -*-
"""
test_fusion_upgrade.py — 互消层升级优化（v6.3+）单元测试

覆盖：
  T1  向后兼容 extract_fingerprint（20 维、无增强 key）
  T2  增强指纹开关（enhanced=True 追加 3 key；False 无；子开关部分开启）
  T3  distill 保形（内置词 ∪ 演化高频词 共存）
  T4  load_or_build_dna 真实小题材落盘 + scope 命中缓存 + scope 不一致触发重建
  T5  _extract_dimensions 演化表 ∪ 内置兜底
  T6  build_llm_prompt 第一层自检清单 + 第二层互消 + DNA 反转锚点（无/有 dna）
  T7  红线：DNA 落盘不含 corpus 字面（值均为短词、值内无换行）
  T8  红线：增强字段绝不注入 build_llm_prompt 输出
  T9  CLI 参数解析新增 flag（subprocess 跑 run_pipeline.py --help）
  T10 红线：核心 IP / narrative_features 未 import dna_distiller

运行：
  cd <project_root> && python tools/test_fusion_upgrade.py
退出码：0=全部 PASS，1=有 FAIL
仅依赖标准库 + 项目既有依赖（jieba）。
"""

import os
import sys
import json
import tempfile
import subprocess
import traceback

# 让 tools/ 下的模块可被 import
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)

import fusion  # noqa: E402
from dna_distiller import distill_dna_from_corpus, load_or_build_dna  # noqa: E402


# ───────────────────────── 轻量测试框架 ─────────────────────────
_RESULTS = []


def check(name, cond, detail=""):
    _RESULTS.append((name, bool(cond), detail))
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  -> {detail}" if detail and not cond else ""))


def run_test(name, fn):
    try:
        fn()
        # 若 fn 内部未显式调用 check 失败，则视为到达终点 PASS
        if not any(r[0] == name and r[1] for r in _RESULTS) and \
           not any(r[0] == name for r in _RESULTS):
            check(name, True)
    except AssertionError as e:
        check(name, False, f"AssertionError: {e}")
    except Exception as e:
        check(name, False, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ───────────────────────── 测试用例 ─────────────────────────
def t1_backward_compat_fingerprint():
    fp = fusion.extract_fingerprint("这是一段用于测试的任意文本，主角死了又活。")
    # 20 维
    assert len(fp["dimensions"]) == len(fusion._DIMENSION_KEYWORDS), \
        f"维度数 {len(fp['dimensions'])} != {len(fusion._DIMENSION_KEYWORDS)}"
    # 默认无增强 key
    for k in ("ngram_vec", "plot_units", "syntax_profile"):
        assert k not in fp, f"默认 enhanced=False 却出现增强字段 {k}"
    check("T1 向后兼容 extract_fingerprint(20维/无增强key)", True)


def t2_enhanced_fingerprint_toggle():
    text = "主角被杀，重生回到侯府，与太子成婚，宅斗不断，嫡女反击。"

    # enhanced=True + 全开子开关
    fp_on = fusion.extract_fingerprint(
        text, enhanced=True,
        enhanced_opts={"ngram": True, "plot": True, "syntax": True}
    )
    for k in ("ngram_vec", "plot_units", "syntax_profile"):
        assert k in fp_on, f"enhanced=True 却缺失 {k}"
    # 增强字段本身确实带内容
    assert isinstance(fp_on["ngram_vec"], dict) and len(fp_on["ngram_vec"]) > 0
    assert isinstance(fp_on["plot_units"], list) and len(fp_on["plot_units"]) > 0
    assert isinstance(fp_on["syntax_profile"], dict)

    # enhanced=False（即便传了 opts 也不可出现）
    fp_off = fusion.extract_fingerprint(
        text, enhanced=False,
        enhanced_opts={"ngram": True, "plot": True, "syntax": True}
    )
    for k in ("ngram_vec", "plot_units", "syntax_profile"):
        assert k not in fp_off, f"enhanced=False 却泄漏 {k}"

    # 子开关部分开启
    fp_part = fusion.extract_fingerprint(
        text, enhanced=True,
        enhanced_opts={"ngram": True, "plot": False, "syntax": False}
    )
    assert "ngram_vec" in fp_part, "子开关 ngram=True 却无 ngram_vec"
    assert "plot_units" not in fp_part, "plot=False 却出现 plot_units"
    assert "syntax_profile" not in fp_part, "syntax=False 却出现 syntax_profile"

    check("T2 增强指纹开关(enhanced=True有3key / False无 / 子开关部分开)", True)


def t3_distill_preservation():
    # 构造只含一个非内置高频词「丫鬟」的合成语料（jieba 已验证可整词切分）
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", encoding="utf-8", delete=False
    )
    try:
        tmp.write("丫鬟 " * 40 + "府中丫鬟端茶，丫鬟低头退下。")
        tmp.close()
        dims = distill_dna_from_corpus([tmp.name], fusion._DIMENSION_KEYWORDS)
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass

    assert len(dims) == len(fusion._DIMENSION_KEYWORDS), "蒸馏结果维度缺失"
    dim_vals = dims["死亡方式"]
    # 内置词必须保留
    assert "被杀" in dim_vals, "保形失败：内置词「被杀」被丢弃"
    # 演化高频词必须追加共存（丫鬟 非内置，应作为演化词并入）
    assert "丫鬟" in dim_vals, "保形失败：演化高频词「丫鬟」未并入"
    # 两者共存（并集）
    assert dim_vals.index("被杀") < len(dim_vals) and "丫鬟" in dim_vals
    check("T3 distill 保形(内置被杀 ∪ 演化丫鬟 共存)", True)


def t4_load_or_build_dna_scope():
    tmp_path = tempfile.mktemp(suffix=".json")
    try:
        # 真实小题材落盘（用 10_先婚后爱，仅 4 篇，速度快）
        cat_a = "10_先婚后爱"
        d1 = load_or_build_dna(cat_a, "category", force=True, dna_path=tmp_path)
        # 落盘
        assert os.path.isfile(tmp_path), "DNA 未落盘到 TMP"
        # scope 字段 = cat
        assert d1.get("scope") == cat_a, f"scope={d1.get('scope')} 期望 {cat_a}"
        # 20 维
        assert len(d1.get("dimensions", {})) == len(fusion._DIMENSION_KEYWORDS), "维度不足 20"
        # 元数据齐全
        for k in ("version", "built_at", "built_from"):
            assert k in d1, f"缺失元数据 {k}"

        # scope 一致 → 命中缓存（不再重建，返回同 scope）
        d2 = load_or_build_dna(cat_a, "category", force=False, dna_path=tmp_path)
        assert d2.get("scope") == cat_a, "force=False 且 scope 一致却未命中缓存"
        # 缓存文件内容 scope 一致
        with open(tmp_path, "r", encoding="utf-8") as fh:
            cached = json.load(fh)
        assert cached.get("scope") == cat_a, "落盘缓存 scope 与请求不一致"

        # scope 不一致（先建 10 缓存，再请求 03_系统快穿）→ 必须触发重建
        cat_b = "03_系统快穿"
        d3 = load_or_build_dna(cat_b, "category", force=False, dna_path=tmp_path)
        assert d3.get("scope") == cat_b, \
            f"scope 不一致未触发重建：返回 scope={d3.get('scope')} 期望 {cat_b}"
        assert d3.get("scope") != cat_a, "误用了旧缓存（10 的 scope）"
        check("T4 load_or_build_dna 落盘+scope缓存命中+scope不一致触发重建", True)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def t5_extract_dimensions_evo_union():
    # 演化表（某维带一个非内置词「凌迟」）
    dna = {"死亡方式": ["凌迟"]}
    text = "主角被凌迟处死，最终还是被杀身亡。"
    dims = fusion._extract_dimensions(text, dna)
    # 并集：内置「被杀」+ 演化「凌迟」都要命中
    assert "凌迟" in dims["死亡方式"], "演化词「凌迟」未命中"
    assert "被杀" in dims["死亡方式"], "内置词「被杀」未命中（并集失效）"

    # dna=None → 纯内置兜底
    dims2 = fusion._extract_dimensions("文中出现了被杀情节。", None)
    assert "被杀" in dims2["死亡方式"], "dna=None 时内置兜底失效"
    check("T5 _extract_dimensions 演化表∪内置兜底", True)


def _make_fp(shared):
    """构造 build_llm_prompt 所需的 fp 结构。"""
    dims = {k: [] for k in fusion._DIMENSION_KEYWORDS}
    for k, v in shared.items():
        dims[k] = list(v)
    return {
        "chars": 1000,
        "sentences": 50,
        "excl_per_sent": 0.1,
        "comma_per_sent": 1.0,
        "uses_quotes": False,
        "opening_50_lines": "开篇内容",
        "top_names": ["阿强"],
        "dimensions": dims,
    }


def t6_build_llm_prompt_layers():
    # 5 篇共享高共有项，制造第一层 reverse_items + 第二层 combos
    shared = {
        "死亡方式": ["被杀", "毒死"],
        "重生触发": ["重生", "穿越"],
        "主角身份": ["嫡女"],
        "核心冲突": ["宅斗"],
    }
    files_info = [
        {"name": f"src{i}.txt", "fp": _make_fp(shared)} for i in range(5)
    ]

    # 无 dna
    out_no = fusion.build_llm_prompt(files_info, include_rules=False)
    assert "生成前自检清单" in out_no, "缺少第一层『生成前自检清单』"
    assert "第二层互消" in out_no, "缺少第二层互消章节"
    assert "互消" in out_no, "输出不含『互消』字样"
    assert "演化 DNA 反转锚点" not in out_no, "无 dna 时不应出现 DNA 反转锚点"

    # 有 dna
    dna_param = {
        "死亡方式": ["凌迟", "鸩杀"],
        "重生触发": ["魂穿", "穿书"],
        "主角身份": ["医妃"],
    }
    out_with = fusion.build_llm_prompt(
        files_info, include_rules=False, dna=dna_param
    )
    assert "演化 DNA 反转锚点" in out_with, "有 dna 时缺少 DNA 反转锚点"
    assert "生成前自检清单" in out_with, "有 dna 时缺少自检清单"
    assert "第二层互消" in out_with, "有 dna 时缺少第二层互消"
    check("T6 build_llm_prompt 第一层自检+第二层互消+DNA锚点(无/有dna)", True)


def t7_redline_no_corpus_literal_in_dna():
    tmp_path = tempfile.mktemp(suffix=".json")
    try:
        # 用真实小题材蒸馏并落盘
        d = load_or_build_dna("10_先婚后爱", "category", force=True,
                              dna_path=tmp_path)
        assert d, "蒸馏返回空"
        # 读落盘文件逐值校验：均为短词且值内无换行
        with open(tmp_path, "r", encoding="utf-8") as fh:
            persisted = json.load(fh)
        dims = persisted.get("dimensions", {})
        assert isinstance(dims, dict) and len(dims) == len(fusion._DIMENSION_KEYWORDS)
        max_len = 0
        for dim, kws in dims.items():
            for kw in kws:
                assert isinstance(kw, str), f"{dim} 值非字符串: {kw!r}"
                assert "\n" not in kw, f"{dim} 值含换行(疑似 corpus 字面): {kw!r}"
                assert "\r" not in kw, f"{dim} 值含回车: {kw!r}"
                max_len = max(max_len, len(kw))
        assert max_len <= 10, f"存在过长值(疑似 corpus 字面)，最长={max_len}"
        check("T7 红线 DNA落盘不含corpus字面(值均短词/值内无换行)", True,
              f"max_len={max_len}")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def t8_redline_enhanced_not_injected():
    txt = "主角被杀，重生回到侯府，与太子成婚，宅斗不断，嫡女反击。"
    efp = fusion.extract_fingerprint(
        txt, enhanced=True,
        enhanced_opts={"ngram": True, "plot": True, "syntax": True}
    )
    # 确认增强字段确实存在于 fp
    assert "ngram_vec" in efp and "plot_units" in efp and "syntax_profile" in efp
    files_info = [{"name": "a.txt", "fp": efp}]
    out = fusion.build_llm_prompt(files_info, include_rules=False)
    for k in ("ngram_vec", "plot_units", "syntax_profile"):
        assert k not in out, f"增强字段 {k} 被注入生成指令（违反红线）"
    check("T8 红线 增强字段绝不注入 build_llm_prompt 输出", True)


def t9_cli_new_flags():
    exe = sys.executable
    proc = subprocess.run(
        [exe, os.path.join(_ROOT, "run_pipeline.py"), "--help"],
        cwd=_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, f"--help 非 0 退出: {proc.returncode}"
    for flag in ("--rebuild-dna", "--dna-scope", "--enhanced-fingerprint",
                 "--ef-ngram", "--ef-plot", "--ef-syntax"):
        assert flag in out, f"CLI 缺少新 flag: {flag}"
    check("T9 CLI 新增 flag(互消层升级) 出现在 --help", True)


def t10_redline_core_ip_not_import_dna_distiller():
    candidates = [
        "anti_pattern.py", "bloom_guard.py", "audit.py",
        "check_story.py", "narrative_features.py",
    ]
    scanned = 0
    for name in candidates:
        for base in (_HERE, _ROOT):
            path = os.path.join(base, name)
            if os.path.isfile(path):
                scanned += 1
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                assert "dna_distiller" not in content, \
                    f"{name} 中出现了 dna_distiller import（违反红线）"
    # 至少应扫到 narrative_features.py
    assert scanned >= 1, "未找到任何核心 IP / narrative_features 文件可供校验"
    check("T10 红线 核心IP/narrative_features 未 import dna_distiller", True,
          f"scanned={scanned}")


# ───────────────────────── 运行 ─────────────────────────
def main():
    print("=" * 64)
    print("互消层升级优化（v6.3+）单元测试")
    print("=" * 64)
    run_test("T1 向后兼容 extract_fingerprint(20维/无增强key)",
             t1_backward_compat_fingerprint)
    run_test("T2 增强指纹开关(enhanced=True有3key / False无 / 子开关部分开)",
             t2_enhanced_fingerprint_toggle)
    run_test("T3 distill 保形(内置被杀 ∪ 演化丫鬟 共存)",
             t3_distill_preservation)
    run_test("T4 load_or_build_dna 落盘+scope缓存命中+scope不一致触发重建",
             t4_load_or_build_dna_scope)
    run_test("T5 _extract_dimensions 演化表∪内置兜底",
             t5_extract_dimensions_evo_union)
    run_test("T6 build_llm_prompt 第一层自检+第二层互消+DNA锚点(无/有dna)",
             t6_build_llm_prompt_layers)
    run_test("T7 红线 DNA落盘不含corpus字面(值均短词/值内无换行)",
             t7_redline_no_corpus_literal_in_dna)
    run_test("T8 红线 增强字段绝不注入 build_llm_prompt 输出",
             t8_redline_enhanced_not_injected)
    run_test("T9 CLI 新增 flag(互消层升级) 出现在 --help",
             t9_cli_new_flags)
    run_test("T10 红线 核心IP/narrative_features 未 import dna_distiller",
             t10_redline_core_ip_not_import_dna_distiller)

    total = len(_RESULTS)
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    failed = total - passed
    print("=" * 64)
    print(f"总计: {total} | 通过: {passed} | 失败: {failed}")
    print("=" * 64)
    if failed:
        for name, ok, detail in _RESULTS:
            if not ok:
                print(f"  FAIL -> {name}\n        {detail}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
