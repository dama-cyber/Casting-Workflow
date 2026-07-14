# -*- coding: utf-8 -*-
"""
tools/test_methodology_weaver.py — methodology_weaver 单元测试（纯 stdlib）

运行方式（cwd = 项目根）:
    cd E:/下载/bb1/Casting-Workflow-main
    python tools/test_methodology_weaver.py

设计要点:
    - 零第三方依赖，仅用 assert + 自带 if __name__=="__main__" 驱动；
    - 受被测模块「绝不抛异常」红线约束，任何 weaver 抛出都视为源码 bug；
    - 通过显式把项目根加入 sys.path，保证无论以何种方式调用都能
      `import tools.methodology_weaver`；
    - monkeypatch 测试在 finally 中还原 METHODOLOGY_DIR，避免污染其他用例。
"""

import os
import sys

# ── 路径修正：保证可以 import tools.methodology_weaver ───────────────────
# 直接 `python tools/test_methodology_weaver.py` 时，sys.path[0] 是 tools/
# 而非项目根；显式把项目根插入，使 `import tools.methodology_weaver` 可用。
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import tools.methodology_weaver as m  # noqa: E402


# ── 小工具 ────────────────────────────────────────────────────────────────
_RESULTS = []


def _record(name, ok, detail=""):
    _RESULTS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    extra = f"  ({detail})" if detail else ""
    print(f"[{status}] {name}{extra}")


def _run(name, fn):
    """运行单个用例：捕获 AssertionError / 其它异常，统一记 PASS/FAIL。"""
    try:
        fn()
        _record(name, True)
    except AssertionError as e:
        _record(name, False, f"assertion: {e}")
    except Exception as e:  # 被测模块若抛异常 = 源码 bug，这里记为 FAIL
        _record(name, False, f"{type(e).__name__}: {e}")


# ── 用例 ──────────────────────────────────────────────────────────────────
def test_mapping_body_with_genre():
    """映射有效性：正文 + 05_古代言情 → 非空，含 '古言脑洞' 与 '严禁原样写入正文'。"""
    r = m.weave_methodology("正文", "05_古代言情")
    assert isinstance(r, str), "应返回 str"
    assert r != "", "正文(05_古代言情) 应织入题材卡，返回非空"
    assert "古言脑洞" in r, "返回文本应含题材卡名 '古言脑洞'"
    assert "严禁原样写入正文" in r, "题材卡分节应含显式『严禁原样写入正文』指令"


def test_character_stage():
    """人设阶段：返回非空且含 character 相关内容。"""
    r = m.weave_methodology("人设")
    assert isinstance(r, str), "应返回 str"
    assert r != "", "人设阶段应织入 character 方法论，返回非空"
    assert "character" in r, "返回文本应含 character 方法论分节"


def test_budget_hard_cap():
    """预算硬上限：大纲(03_系统快穿) 多文件应触发截断，最终长度必 ≤ 2600。"""
    r = m.weave_methodology("大纲", "03_系统快穿", budget=2600)
    assert isinstance(r, str), "应返回 str"
    assert r != "", "大纲阶段应织入方法论，返回非空"
    assert len(r) <= 2600, f"返回长度 {len(r)} 超过预算上限 2600"


def test_genre_fallback_robust():
    """题材卡兜底（不在映射表的 category）：绝不可抛异常/崩溃，返回 str。"""
    # '都市玄幻异能' 不在 CATEGORY_GENRE_MAP，且无别名精确命中 → 预期优雅返回 ""；
    # 即便命中某卡返回非空也合法。核心断言：不抛异常、返回 str。
    r = m.weave_methodology("正文", "都市玄幻异能")
    assert isinstance(r, str), "兜底解析应返回 str（绝不抛异常）"
    assert r == "" or len(r) > 0, "结果应为空串或有效文本"


def test_genre_fallback_positive():
    """题材卡兜底（正向）：'都市修真文' 应包含子串 '都市修真' → 命中 都市修真 卡。"""
    r = m.weave_methodology("正文", "都市修真文")
    assert isinstance(r, str), "应返回 str"
    # 兜底子串命中：'都市修真' in '都市修真文' → 应解析到 都市修真 卡
    assert "都市修真" in r, "兜底子串匹配应解析到 '都市修真' 题材卡"


def test_backward_compat_no_category():
    """向后兼容：脑洞 阶段 category=None 应返回 ''（不崩、不报错）。"""
    r = m.weave_methodology("脑洞")  # category 默认 None
    assert isinstance(r, str), "应返回 str"
    assert r == "", "脑洞(category=None) 题材卡解析不到，应返回空串"


def test_robustness_missing_dir():
    """健壮性：把 METHODOLOGY_DIR 指向不存在目录，调用仍返回 '' 且不抛异常。"""
    saved = m.METHODOLOGY_DIR
    try:
        m.METHODOLOGY_DIR = "/tmp/__none__"  # 必不存在
        r = m.weave_methodology("人设")
        assert isinstance(r, str), "应返回 str"
        assert r == "", "目录不存在时，人设阶段应优雅返回空串"
    finally:
        m.METHODOLOGY_DIR = saved  # 还原，避免污染后续用例
    # 还原后功能应恢复正常
    assert m.METHODOLOGY_DIR == saved


def test_no_frontmatter_leak():
    """题材卡不泄漏 frontmatter：返回文本不应以 '---' 开头。"""
    r = m.weave_methodology("正文", "05_古代言情")
    assert isinstance(r, str), "应返回 str"
    if r:  # 仅当非空时校验（非空由 test_mapping_body_with_genre 保证）
        assert not r.startswith("---"), "织入文本首行不应是 '---'（frontmatter 须被剥离）"


# ── 主驱动 ────────────────────────────────────────────────────────────────
def main():
    print("=" * 64)
    print("methodology_weaver 单元测试")
    print("METHODOLOGY_DIR =", m.METHODOLOGY_DIR)
    print("=" * 64)

    _run("映射有效性: 正文+05_古代言情 含题材卡与禁抄指令", test_mapping_body_with_genre)
    _run("人设阶段: 返回非空且含 character 内容", test_character_stage)
    _run("预算硬上限: 大纲(03_系统快穿) len<=2600", test_budget_hard_cap)
    _run("题材卡兜底(鲁棒): 都市玄幻异能 不崩溃", test_genre_fallback_robust)
    _run("题材卡兜底(正向): 都市修真文 命中都市修真卡", test_genre_fallback_positive)
    _run("向后兼容: 脑洞(category=None) 返回 ''", test_backward_compat_no_category)
    _run("健壮性: METHODOLOGY_DIR 不存在 返回 ''", test_robustness_missing_dir)
    _run("题材卡不泄漏 frontmatter: 不以 '---' 开头", test_no_frontmatter_leak)

    total = len(_RESULTS)
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    failed = total - passed
    print("-" * 64)
    print(f"总计 {total} | PASS {passed} | FAIL {failed}")
    print("=" * 64)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
