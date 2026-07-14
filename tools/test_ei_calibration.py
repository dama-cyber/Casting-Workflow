# -*- coding: utf-8 -*-
"""P1-2 EI 校准单元测试：验证 P1/P5 不再被纯连词虚高推满。

核心断言：
- 平淡文（无反转/回收词）-> P1/P5 低，EI 不虚高
- 纯连词文（大量但是/然而/所以/这就是，但无强信号词）-> P1/P5 仍为 0（不虚高）
- 爽文（密集强反转词）-> P1 显著 > 平淡文
- 回收文（密集强回收词）-> P5 显著 > 平淡文
- EI 始终在 0-100
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anti_pattern import calculate_EI


PLAIN = (
    "春天来了，河边柳树发芽。老人坐在长椅上。风吹过树叶。"
    "孩子跑过草地。远处有座小山。日子就这样过着。没有意外发生。"
    "一切平静。他每天散步。她总在窗边看。时间慢慢流走。生活没有波澜。"
)

# 纯连词但无强反转/回收信号：验证不虚高
PURE_CONJ = (
    "他喜欢读书，但是书很少。然而他坚持。可是没人理解。"
    "所以他孤独。这就是他的命。但是天气好了。然而他仍不出门。"
    "所以日子平淡。这就是生活。但是明天会更好。然而他不信。"
)

# 密集强反转词
SUBV = (
    "他以为赢了，竟然被反杀。谁知幕后另有其人。偏偏盟友背叛。"
    "没想到真相如此残酷。万万没想到结局反转。居然是陷阱。"
    "原来一切都是布局。果然他早有预谋。颠覆认知的真相浮出。"
    "怎么会这样。不可能这么简单。不对，有诈。"
)

# 密集强回收词
PAYOFF = (
    "线索回收。原来凶手是管家。事实上他是主谋。难怪行为古怪。"
    "这正是关键证据。果然不出所料。实际上早有伏笔。真相大白。"
    "原来如此。事实是她一直在演戏。"
)


class TestEICalibration(unittest.TestCase):

    def test_plain_low(self):
        r = calculate_EI(PLAIN)
        self.assertGreaterEqual(r["EI"], 0)
        self.assertLessEqual(r["EI"], 100)
        # 平淡文无强反转/回收 -> P1/P5 应极低
        self.assertLess(r["details"]["P1_预期违背密度"], 3)
        self.assertLess(r["details"]["P5_回收密度"], 3)

    def test_pure_conjunction_not_inflated(self):
        r = calculate_EI(PURE_CONJ)
        # 纯转折/因果连词不应推高 P1/P5（已剔除但是/然而/可是/所以/这就是）
        self.assertEqual(r["details"]["P1_预期违背密度"], 0)
        self.assertEqual(r["details"]["P5_回收密度"], 0)

    def test_subversion_sensitive(self):
        r = calculate_EI(SUBV)
        self.assertGreater(r["details"]["P1_预期违背密度"], 5)
        # 强反转文 EI 不应落入"平淡如水/略有起伏"低端
        self.assertGreater(r["EI"], 40)

    def test_payoff_sensitive(self):
        r = calculate_EI(PAYOFF)
        self.assertGreater(r["details"]["P5_回收密度"], 5)

    def test_ei_range(self):
        for t in (PLAIN, PURE_CONJ, SUBV, PAYOFF):
            r = calculate_EI(t)
            self.assertGreaterEqual(r["EI"], 0)
            self.assertLessEqual(r["EI"], 100)

    def test_subversion_beats_pure_conj(self):
        r_sub = calculate_EI(SUBV)
        r_conj = calculate_EI(PURE_CONJ)
        # 强反转文 P1 显著高于纯连词文（证明维度确实在测"反转"而非"连词"）
        self.assertGreater(
            r_sub["details"]["P1_预期违背密度"],
            r_conj["details"]["P1_预期违背密度"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
