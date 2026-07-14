# -*- coding: utf-8 -*-
"""
test_qiaomu_f.py — qiaomu 借鉴增量 · 方向 F 单测（对话绝对值门槛 + 开篇误导豁免）

覆盖：
  T1 对话字数占比 < 门槛 → dialogue_ratio_low 触发
  T2 对话字数占比 ≥ 门槛 → 不触发
  T3 开篇误导 + 闪回/梦境标记在开篇 → ambiguous_opening 被豁免（降假阳）
  T4 开篇误导但无豁免标记 → ambiguous_opening 仍触发
  T5 豁免后 ambiguous 计数仍如实回显（透明度）
  T6 返回契约含 dialogue_ratio / ambiguous_exempted / ambiguous_exempt_reason
  T7 全信号 severity ∈ [0,1] 且 alarm_severity ∈ {INFO,WARN}（绝不 FAIL）

红线：零模型、不依赖 corpus、不修改 fusion.py；纯正则，CI 友好。
运行：python tools/test_qiaomu_f.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anti_ai_reporter import report_ai_flavor, load_anti_ai_rules  # noqa: E402


def _run(text, rules=None):
    if rules is None:
        rules = load_anti_ai_rules()
    return report_ai_flavor(text, rules=rules)


def test_dialogue_ratio_low_disabled_by_default():
    # qiaomu E 校准：dialogue_ratio_min=0.0 已禁用该退化信号（人类语料 79.8% 误杀）
    text = "夜色沉下来。风穿过空荡的街。他独自走着，想起很多事。远处没有灯光，只有沉默长长地铺开。"
    r = _run(text)
    assert r["dialogue_ratio"] == 0.0
    assert "dialogue_ratio_low" not in r["flags"]
    assert "dialogue_sparse" in r["flags"]  # 行数<4 仍触发（dialogue_min 未改）


def test_dialogue_ratio_low_triggers_when_enabled():
    # 触发逻辑仍在：临时把阈值设为 0.03 验证低 ratio 仍触发（锁定实现，非默认行为）
    enabled = load_anti_ai_rules()
    enabled["thresholds"]["dialogue_ratio_min"] = 0.03
    text = "夜色沉下来。风穿过空荡的街。他独自走着，想起很多事。远处没有灯光，只有沉默长长地铺开。"
    r = _run(text, enabled)
    assert r["dialogue_ratio"] == 0.0
    assert "dialogue_ratio_low" in r["flags"]


def test_dialogue_ratio_ok_not_triggered():
    # 「」内字数占比充足（对话撑场）
    text = (
        "他站在门口。「你来了，」她说，「我还以为你不会来呢，这天实在太晚了，风又大，"
        "街口的灯也坏了。」他点头。「进去吧，外面冷。」她拉着他的手，「别站着，会感冒的。」"
    )
    r = _run(text)
    assert r["dialogue_ratio"] >= 0.06
    assert "dialogue_ratio_low" not in r["flags"]


def test_opening_misleading_exempted_by_flashback():
    # 开篇含「那一年」闪回标记 + 死人走来 → 应豁免
    text = (
        "那一年，他还是个少年。\n"
        "村口的槐树下，死人走来，浑身是血。\n"
        "「我没怕，」他说，「你别过来。」"
    )
    r = _run(text)
    assert r["ambiguous"]["count"] >= 1           # 计数仍如实
    assert "ambiguous_opening" not in r["flags"]  # 告警被豁免
    assert r["ambiguous_exempted"] is True
    assert "那一年" in r["ambiguous_exempt_reason"]


def test_opening_misleading_not_exempted_without_marker():
    # 死人走来但开篇无闪回/梦境标记 → 仍触发
    text = (
        "村口的槐树下，死人走来，浑身是血。\n"
        "「我没怕，」他说，「你别过来。」"
    )
    r = _run(text)
    assert r["ambiguous"]["count"] >= 1
    assert "ambiguous_opening" in r["flags"]
    assert r["ambiguous_exempted"] is False


def test_exempt_reason_absent_when_no_ambiguous():
    # 普通文本无误导开篇 → 豁免字段为 False、原因为空
    text = "清晨的雾还没散。他推开木门，听见远处有鸡叫。「吃饭了，」母亲在屋里喊。"
    r = _run(text)
    assert "ambiguous_opening" not in r["flags"]
    assert r["ambiguous_exempted"] is False
    assert r["ambiguous_exempt_reason"] == ""


def test_contract_keys_present():
    text = "那一年，他还是个少年。\n村口的槐树下，死人走来。\n「我没怕，」他说。"
    r = _run(text)
    for k in ("dialogue_ratio", "ambiguous_exempted", "ambiguous_exempt_reason"):
        assert k in r, f"返回契约缺字段: {k}"


def test_severity_bounds_and_level():
    # 低对话 + 误导开篇（无豁免）应触发多个 flag，但 level 仅 WARN/INFO
    text = (
        "夜色沉下来。风穿过空荡的街。他独自走着，想起很多事。\n"
        "村口的槐树下，死人走来，浑身是血。"
    )
    r = _run(text)
    assert 0.0 <= r["severity"] <= 1.0
    assert r["alarm_severity"] in ("INFO", "WARN")
    assert r["ai_flavor_alarm"] is True


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] {t.__name__}: {e}")
    total = len(tests)
    print(f"\n结果: {passed}/{total} 通过")
    sys.exit(0 if passed == total else 1)
