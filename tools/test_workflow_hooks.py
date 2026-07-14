# -*- coding: utf-8 -*-
"""tools/test_workflow_hooks.py — 统一流胶水模块单元测试（stdlib assert）。

覆盖：
  - read_capture_insights（Markdown 解析，capture 产物为 Markdown 非 JSON）
  - read_analysis_refs（analysis 目录 glob）
  - inject_capture_into_brainstorm / inject_analysis_into_characters_outline（注入）
  - build_capture_argv / build_cover_argv / build_browser_argv / build_analyze_argv
  - run_pipeline._resolve_steps（--capture/--analyze/--cover/--browser 与 --with 并集）
  - CLI --help：统一流用法，无独立 --mode 参数

运行（cwd=项目根）：
    <managed-python> tools/test_workflow_hooks.py
退出码 0 = 全部通过；非 0 = 存在失败。
零新增依赖：仅标准库（os/sys/subprocess/tempfile/shutil）。
"""

import os
import sys
import subprocess
import tempfile
import shutil

# ── 项目根（run_pipeline.py 所在目录）= 本文件上级目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# workflow_hooks 位于 tools/（运行脚本时脚本目录已在 sys.path[0]）
from workflow_hooks import (
    WorkflowState,
    build_capture_argv,
    build_analyze_argv,
    build_cover_argv,
    build_browser_argv,
    read_capture_insights,
    read_analysis_refs,
    inject_capture_into_brainstorm,
    inject_analysis_into_characters_outline,
)

# run_pipeline 顶层导入（模块级无副作用，不触发 jieba；jieba 仅在 _run_generate_trunk 运行时懒导入）
try:
    import run_pipeline
    _RUN_PIPELINE_ERR = None
except Exception as _e:  # pragma: no cover - 仅环境异常
    run_pipeline = None
    _RUN_PIPELINE_ERR = _e


# ── 测试登记 ──────────────────────────────────────────────
_RESULTS = []


def _register(name):
    def deco(fn):
        _RESULTS.append((name, fn))
        return fn
    return deco


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ── A. read_capture_insights（Markdown 解析）──────────────
@_register("read_capture_insights: 解析真实 Markdown 结构（品类/书名/标签）")
def test_read_capture_insights_parse():
    tmp = tempfile.mkdtemp(prefix="scan_out_")
    try:
        md_path = os.path.join(tmp, "番茄男频阅读榜_20250101.md")
        content = (
            "# 番茄 · 男频阅读榜 · 全 6 题材\n"
            "\n"
            "## 西方奇幻 — 20 本\n"
            "\n"
            "### #1 剑来\n"
            "*烽火戏诸侯 · 仙侠 · 连载 · 在读*\n"
            "**标签：** 仙侠、师徒、朝堂\n"
            "**简介**\n"
            "一个关于江湖与庙堂的群像故事。\n"
            "\n"
            "## 古代言情 — 15 本\n"
            "\n"
            "### #1 凤囚凰\n"
            "*天衣有风 · 古代言情 · 完结 · 在读*\n"
            "**标签：** 权谋、爱情\n"
            "**简介**\n"
            "南朝公主的权谋与爱恨。\n"
        )
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)

        res = read_capture_insights(tmp)
        _assert(isinstance(res, dict), "read_capture_insights 应返回 dict")
        _assert("text" in res, "返回 dict 应包含 text 字段")
        text = res["text"]
        _assert("西方奇幻" in text, "text 应含品类名 西方奇幻")
        _assert("剑来" in text, "text 应含书名 剑来")
        _assert("仙侠" in text, "text 应含标签 仙侠")
        _assert(res.get("platform") == "番茄", "platform 应解析为 番茄")
        _assert("西方奇幻" in (res.get("categories") or []), "categories 应含 西方奇幻")
        books = res.get("books") or []
        _assert(any(b.get("title") == "剑来" for b in books), "books 应含《剑来》")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@_register("read_capture_insights: 缺失目录/空路径返回 {} 不崩")
def test_read_capture_insights_missing_dir():
    res = read_capture_insights("")
    _assert(res == {}, "空路径应返回 {}")
    res = read_capture_insights(os.path.join(tempfile.gettempdir(), "no_such_scan_xyz_987"))
    _assert(res == {}, "不存在目录应返回 {}")


@_register("read_capture_insights: 目录无 .md 返回 {}")
def test_read_capture_insights_empty_dir():
    tmp = tempfile.mkdtemp(prefix="scan_empty_")
    try:
        res = read_capture_insights(tmp)
        _assert(res == {}, "无 .md 目录应返回 {}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── B. read_analysis_refs ─────────────────────────────────
@_register("read_analysis_refs: 解析 analysis/{书名} 目录")
def test_read_analysis_refs_parse():
    tmp = tempfile.mkdtemp(prefix="analysis_")
    try:
        book_dir = os.path.join(tmp, "某书")
        os.makedirs(book_dir)
        md_path = os.path.join(book_dir, "人设.md")
        marker = "主角性格冷硬寡言、行事凌厉"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# 人设\n" + marker + "\n")
        res = read_analysis_refs(book_dir)
        _assert(isinstance(res, dict), "应返回 dict")
        _assert("text" in res, "应含 text 字段")
        _assert(marker in res["text"], "text 应含文件内容")
        _assert("人设" in (res.get("files") or []), "files 应含 人设")
        _assert("人设" in (res.get("refs") or {}), "refs 应含 人设 键")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@_register("read_analysis_refs: 缺失目录返回 {}")
def test_read_analysis_refs_missing_dir():
    res = read_analysis_refs("")
    _assert(res == {}, "空路径应返回 {}")
    res = read_analysis_refs(os.path.join(tempfile.gettempdir(), "no_such_analysis_xyz_987"))
    _assert(res == {}, "不存在目录应返回 {}")


# ── C. inject_capture_into_brainstorm ─────────────────────
@_register("inject_capture_into_brainstorm: 有 text 注入 扫榜参考 键")
def test_inject_capture():
    state = WorkflowState(capture_insights={
        "text": "榜单来源：番茄 男频阅读榜\n热门题材：西方奇幻\n爆款示例：《剑来》标签：仙侠、师徒"
    })
    params = inject_capture_into_brainstorm(state, {"核心卖点": "x"})
    _assert("扫榜参考" in params, "应新增 扫榜参考 键")
    _assert("仙侠" in params["扫榜参考"], "扫榜参考 值应含 仙侠")
    _assert(params.get("核心卖点") == "x", "原 user_params 键应保留")


@_register("inject_capture_into_brainstorm: text 空原样返回")
def test_inject_capture_empty():
    state = WorkflowState(capture_insights={})
    user_params = {"核心卖点": "x"}
    out = inject_capture_into_brainstorm(state, user_params)
    _assert(out == user_params, "空 text 应原样返回 user_params")


# ── D. inject_analysis_into_characters_outline ────────────
@_register("inject_analysis_into_characters_outline: 有 text 返回参考块")
def test_inject_analysis():
    state = WorkflowState(analysis_refs={"text": "主角冷硬寡言，行事凌厉果断"})
    out = inject_analysis_into_characters_outline(state, "人设")
    _assert(isinstance(out, str), "应返回字符串")
    _assert("冷硬" in out, "返回文本应含 冷硬")


@_register("inject_analysis_into_characters_outline: text 空返回 ''")
def test_inject_analysis_empty():
    state = WorkflowState(analysis_refs={})
    out = inject_analysis_into_characters_outline(state, "人设")
    _assert(out == "", "空 text 应返回空串")


# ── E. build_*_argv ───────────────────────────────────────
@_register("build_capture_argv: 含 --platform + 平台值 + --outdir")
def test_build_capture_argv():
    opts = {"capture_platform": "fanqie"}
    state = WorkflowState(scan_output_dir="/tmp/scan_out")
    argv = build_capture_argv(opts, state)
    _assert("--platform" in argv, "应含 --platform")
    _assert("fanqie" in argv, "应含平台值 fanqie")
    _assert("--outdir" in argv, "应含 --outdir")
    _assert("/tmp/scan_out" in argv, "应含 outdir 值")


@_register("build_cover_argv: 有 prompt+key 含 --prompt")
def test_build_cover_argv_ok():
    opts = {"cover_prompt": "仙侠水墨风封面", "cover_api_key": "sk-test"}
    state = WorkflowState(analysis_dir="/proj/analysis")
    argv = build_cover_argv(opts, state)
    _assert(argv is not None, "有 prompt+key 不应返回 None")
    _assert("--prompt" in argv, "应含 --prompt")
    _assert("仙侠水墨风封面" in argv, "应含 prompt 值")


@_register("build_cover_argv: 全缺（无 prompt/key/环境变量）返回 None")
def test_build_cover_argv_none():
    saved = os.environ.pop("GPT_IMAGE_API_KEY", None)
    try:
        argv = build_cover_argv({}, WorkflowState())
        _assert(argv is None, "无 prompt/key 应返回 None")
    finally:
        if saved is not None:
            os.environ["GPT_IMAGE_API_KEY"] = saved


@_register("build_browser_argv: 含 --action")
def test_build_browser_argv():
    opts = {"browser_action": "browse", "browser_port": 9333}
    argv = build_browser_argv(opts)
    _assert("--action" in argv, "应含 --action")
    _assert("browse" in argv, "应含 action 值 browse")
    _assert("--port" in argv, "应含 --port")


@_register("build_analyze_argv: 无 input 返回 []，有 input 含 --input")
def test_build_analyze_argv():
    state = WorkflowState(analysis_dir="/proj/analysis")
    _assert(build_analyze_argv({}, state) == [], "无 --analyze-input 应返回 []")
    opts = {"analyze_input": "book.txt", "analyze_book": "某书"}
    argv = build_analyze_argv(opts, state)
    _assert("--input" in argv, "应含 --input")
    _assert("book.txt" in argv, "应含 input 值")


# ── F. _resolve_steps（run_pipeline）──────────────────────
def _need_run_pipeline():
    if run_pipeline is None:
        raise AssertionError("run_pipeline 导入失败: %r" % _RUN_PIPELINE_ERR)


@_register("_resolve_steps: --with capture,analyze 并集")
def test_resolve_with():
    _need_run_pipeline()
    state = run_pipeline.WorkflowState()
    run_pipeline._resolve_steps({"with": "capture,analyze"}, state)
    _assert(state.do_capture and state.do_analyze, "do_capture/do_analyze 应为 True")
    _assert(not state.do_cover, "do_cover 应为 False")
    _assert(not state.do_browser, "do_browser 应为 False")


@_register("_resolve_steps: 单独 --capture")
def test_resolve_capture_only():
    _need_run_pipeline()
    state = run_pipeline.WorkflowState()
    run_pipeline._resolve_steps({"capture": True}, state)
    _assert(state.do_capture, "do_capture 应为 True")
    _assert(not state.do_analyze and not state.do_cover and not state.do_browser,
            "其余步骤开关应为 False")


@_register("_resolve_steps: 单独开关与 --with 取并集")
def test_resolve_union():
    _need_run_pipeline()
    state = run_pipeline.WorkflowState()
    run_pipeline._resolve_steps({"capture": True, "with": "browser"}, state)
    _assert(state.do_capture and state.do_browser, "do_capture/do_browser 应为 True")
    _assert(not state.do_analyze and not state.do_cover, "analyze/cover 应为 False")


@_register("_resolve_steps: 未知 token 不破坏映射")
def test_resolve_unknown_token():
    _need_run_pipeline()
    state = run_pipeline.WorkflowState()
    run_pipeline._resolve_steps({"with": "capture,foobar"}, state)
    _assert(state.do_capture, "capture 应为 True")
    _assert(not state.do_cover, "未知 token 不应影响 do_cover（仍为 False）")


# ── G. CLI --help（subprocess）────────────────────────────
@_register("CLI --help: 统一流用法，无独立 --mode 参数")
def test_cli_help_no_mode():
    py = sys.executable
    # 子进程（run_pipeline.py）已将 stdout 重配置为 utf-8；父进程必须显式用 utf-8 解码，
    # 否则默认 gbk 会因中文帮助文本抛 UnicodeDecodeError 且 stdout 变 None。
    proc = subprocess.run(
        [py, "run_pipeline.py", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        encoding="utf-8",
    )
    out = proc.stdout
    _assert(proc.returncode == 0, "--help 应退出码 0")
    _assert("--capture" in out, "help 应含 --capture")
    _assert("--with" in out, "help 应含 --with（统一流用法）")
    _assert("--mode generate" not in out, "旧 --mode generate 用法示例不应出现")


# ── 运行器 ────────────────────────────────────────────────
def main():
    passed = 0
    failed = 0
    print("=" * 64)
    print("统一流胶水模块单元测试 (tools/test_workflow_hooks.py)")
    print("=" * 64)
    if run_pipeline is None:
        print("[WARN] run_pipeline 导入失败（仅影响 _resolve_steps 用例）: %r" % _RUN_PIPELINE_ERR)
    for name, fn in _RESULTS:
        try:
            fn()
            passed += 1
            print("PASS  %s" % name)
        except AssertionError as e:
            failed += 1
            print("FAIL  %s" % name)
            print("      ↳ %s" % e)
        except Exception as e:
            failed += 1
            print("FAIL  %s" % name)
            print("      ↳ [异常] %r" % e)
    print("-" * 64)
    print("总计: %d | 通过: %d | 失败: %d" % (len(_RESULTS), passed, failed))
    print("=" * 64)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
