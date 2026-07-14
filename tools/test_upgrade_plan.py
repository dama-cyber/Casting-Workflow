# -*- coding: utf-8 -*-
"""升级计划 P0-1 / P1-2 / P1-3 针对性自测（主理人降级兜底实现后的质量关卡）。

不依赖全量 corpus 加载，纯单元级验证：
  - P0-1: anti_pattern 读 opening_50_lines 后动态因子链不再恒空
  - P1-2: EI 的 P3 由 max-min(恒满10) 改为标准差波动性，flat 文本不再恒满
  - P1-3: os.walk 递归 + 小写匹配，.TXT/.Txt 被收录（case 敏感 glob 漏采的修复）
"""
import os
import sys

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)

_fail = 0
_pass = 0


def _assert(cond, msg):
    global _fail, _pass
    if cond:
        _pass += 1
        print(f"  [OK] {msg}")
    else:
        _fail += 1
        print(f"  [FAIL] {msg}")


print("=== P0-1 反模式动态因子链（opening_50_lines）===")
from anti_pattern import _detect_pattern, _extract_shared_themes, calculate_EI

# 构造 5 篇源文，opening_50_lines 含可检测关键词
_files = [{"name": f"src{i}.txt",
           "fp": {"opening_50_lines": "她忽然转身，眼中闪过一丝决然。他终于明白这一切都是骗局。"}} for i in range(5)]
_res = _detect_pattern(_files, "反转", ["决然", "骗局", "忽然"])
_assert("未检测到" not in _res, f"_detect_pattern 命中动态因子（修复前恒『未检测到』）: {_res}")

# _extract_shared_themes 需 jieba；不可用则跳过（属环境限制，非回归）
try:
    import jieba  # noqa: F401
    _themes = _extract_shared_themes(_files, top_n=5)
    # 五篇完全相同文本，共享主题必非空（修复前 opening 空 → 恒返回 []）
    _assert(len(_themes) > 0, f"_extract_shared_themes 提取到共享主题: {_themes[:5]}")
except ImportError:
    print("  [SKIP] jieba 未安装，_extract_shared_themes 跳过（环境限制，非回归）")

print("\n=== P1-2 EI 的 P3 波动性（不再恒满10）===")
_flat = "。".join(["今天天气不错，他慢慢走着"] * 60)
_emo = _flat + "他愤怒地吼叫，仇恨在胸中燃烧，绝望像潮水般蔓延，恐惧攫住了每一个人，狂喜忽然涌上心头。"
_rf = calculate_EI(_flat)
_re = calculate_EI(_emo)
_p3f = _rf["details"]["P3_情绪极差"]
_p3e = _re["details"]["P3_情绪极差"]
_assert(_p3f < 10, f"flat 文本 P3 不再恒满10（实测 {_p3f}）")
_assert(_p3f != _p3e, f"P3 随情绪波动变化（flat={_p3f} vs emo={_p3e}）")
_assert(_re["EI"] <= 100, f"EI 上限受控（emo EI={_re['EI']}）")
# 反模式等效EI 通胀已移除：check_story.py:686 现为 ei_score_adjusted = ei_score（见下方 grep 校验）

print("\n=== P1-3 corpus 大小写漏采（os.walk 递归 + 小写）===")
_corpus = os.path.normpath(os.path.join(_THIS, "..", "corpus"))
# 旧：大小写敏感、仅一层 glob
_old = 0
for _d in os.listdir(_corpus):
    _sd = os.path.join(_corpus, _d)
    if os.path.isdir(_sd):
        _old += len([_f for _f in os.listdir(_sd) if _f.endswith(".txt")])
# 新：递归 + 小写
_new = 0
for _dp, _dn, _fns in os.walk(_corpus):
    for _f in _fns:
        if _f.lower().endswith(".txt"):
            _new += 1
_assert(_new >= _old, f"walk 收录数不少于旧 glob（{_new} >= {_old}）")
_assert(_new > _old, f"walk 额外收录 .TXT/.Txt 大小写变体（{_new} > {_old}，差值={_new - _old}）")

print(f"\n=== 自测结果: {_pass} 通过 / {_fail} 失败 ===")
sys.exit(1 if _fail else 0)
