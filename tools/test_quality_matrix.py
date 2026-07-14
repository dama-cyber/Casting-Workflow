# -*- coding: utf-8 -*-
"""qiaomu D 统一创作质量矩阵 独立单测（与既有 26/21/18/14/7 同构，仅 WARN 软信号）。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from quality_matrix import report_quality_matrix
from deslop_reporter import merge_ai_flavor_signals
from anti_ai_reporter import report_ai_flavor, load_anti_ai_rules, load_banned
from deslop_reporter import report_degeneration, load_degeneration_rules
from advisory_reporter import report_advisory, load_advisory_rules


def _ai(ai_flavor_alarm=False, severity=0.2, flags=None, issues=None):
    return {"ai_flavor_alarm": ai_flavor_alarm, "severity": severity,
            "flags": flags or [], "issues": issues or [], "hook": {"count": 2}}


def _deg(flags=None, issues=None):
    return {"flags": flags or [], "issues": issues or []}


def _adv(flags=None):
    return {"flags": flags or []}


def test_show_dont_tell_alarm():
    # 高密度思维标记 + 软副词 → 触发
    t = "他心想这不对。" * 50 + "她感到难过。" * 30 + "他轻轻摇头。" * 20
    r = report_quality_matrix(t, {"ai": _ai(), "deg": _deg(), "adv": _adv()})
    assert r["show_dont_tell"]["alarm"] is True, r["show_dont_tell"]
    assert r["show_dont_tell"]["severity"] > 0
    print("PASS test_show_dont_tell_alarm")


def test_show_dont_tell_ok():
    # 动作 + 感官描写 → 不触发，score 高
    t = "他看见门外的灯。" * 10 + "她听见雨打瓦当的声音。" * 10 + "指尖触到冰凉的杯壁。" * 10
    r = report_quality_matrix(t, {"ai": _ai(), "deg": _deg(), "adv": _adv()})
    assert r["show_dont_tell"]["alarm"] is False, r["show_dont_tell"]
    assert r["show_dont_tell"]["score"] >= 0.6, r["show_dont_tell"]
    print("PASS test_show_dont_tell_ok")


def test_matrix_dimensions():
    t = "测试文本" * 100
    r = report_quality_matrix(t, {"ai": _ai(), "deg": _deg(), "adv": _adv()})
    dims = [m["dim"] for m in r["matrix"]]
    assert dims == ["去AI味", "画面感", "开篇钩子", "质量清单"], dims
    for m in r["matrix"]:
        assert m["level"] in ("OK", "WARN", "INFO", "ISSUE"), m
        assert 0.0 <= m["score"] <= 1.0, m
    print("PASS test_matrix_dimensions")


def test_composite_mirrors_show():
    r = report_quality_matrix("他心想不对。" * 60, {"ai": _ai(), "deg": _deg(), "adv": _adv()})
    assert r["composite"]["alarm"] == r["show_dont_tell"]["alarm"]
    assert r["quality_matrix_alarm"] == r["show_dont_tell"]["alarm"]
    print("PASS test_composite_mirrors_show")


def test_compat_missing_ai():
    # reports 缺 ai / 为 None 不崩
    r = report_quality_matrix("普通文本" * 50, {"deg": _deg(), "adv": _adv()})
    assert "matrix" in r
    r2 = report_quality_matrix("普通文本" * 50, None)
    assert "matrix" in r2
    print("PASS test_compat_missing_ai")


def test_merge_receives_show():
    t = "他心想这不对劲。" * 60
    _a = report_ai_flavor(t, rules=load_anti_ai_rules(), banned=load_banned())
    _d = report_degeneration(t, rules=load_degeneration_rules())
    _v = report_advisory(t, rules=load_advisory_rules())
    _qm = report_quality_matrix(t, {"ai": _a, "deg": _d, "adv": _v})
    merged = merge_ai_flavor_signals(_a, _d, _v, _qm)
    # show_dont_tell 触发 → merged 含 quality_matrix 细节
    assert merged["ai_flavor_alarm"] is True
    assert "quality_matrix" in merged["alarm_detail"]
    print("PASS test_merge_receives_show")


def test_no_fail_ever():
    # 任意文本 level 绝不含 FAIL
    for t in ["", "他心想。" * 80, "她看见月亮。" * 40]:
        r = report_quality_matrix(t, {"ai": _ai(), "deg": _deg(), "adv": _adv()})
        for m in r["matrix"]:
            assert m["level"] != "FAIL", m
    print("PASS test_no_fail_ever")


if __name__ == "__main__":
    test_show_dont_tell_alarm()
    test_show_dont_tell_ok()
    test_matrix_dimensions()
    test_composite_mirrors_show()
    test_compat_missing_ai()
    test_merge_receives_show()
    test_no_fail_ever()
    print("\nALL QIAOMU-D TESTS PASSED")
