# 去 AI 规则指针（anti-ai/pointers）

本文件把「去 AI 味 / 审查」的需求映射到目标侧权威文件，避免规则重复维护。

## 文件映射

| 需求 | 目标侧权威文件 | 说明 |
|---|---|---|
| 硬禁模板词（眼中闪过 / 嘴角勾起 / 破折号断句 …） | `config/banned.json` | 命中即 AI 套路 |
| 去 AI 规则（句式 / 节奏 / 软信号） | `config/anti_ai_rules.json` | 生成侧与质检侧同源 |
| 软信号密度告警（比喻 / 连接词 / 对话占比 …） | `config/advisory_rules.json` | 密度超限告警 |
| 白名单豁免 | `config/deslop_whitelist.txt` | 合法手法豁免硬禁 |
| 生成侧预防自检 | `prompt/COMMON.md`「去 AI 味自检清单」 | 写前预防，三遍法 |
| 质检终判 | `check_story.py` §十二~§十五 | 去 AI 味 / 退化 / advisory / 质量矩阵 |
| 统一质量矩阵 | `config/quality_matrix_rules.json` | §十五 矩阵规则 |

## 三遍法（写后静默执行，仅输出成稿）

1. **内容**：冲突直接、角色不降智、钩子到位、无背景铺垫废笔
2. **去 AI 味**：逐条核对 `banned.json` + `anti_ai_rules.json` 硬禁项，删尽；软信号压到 `advisory_rules.json` 阈值内
3. **人类吻合度**：句长长短交错、有不完美闲笔、情绪有起伏、像真人手笔

## 红线（与全局一致）

- 禁止西文引号；禁止破折号断句（对话中断用「……」）
- 禁止「忽然 / 猛地 / 瞬间」突转词；禁止格式化比喻 / 软副词 / 群像套路词
- 禁用思维标记（我常想 / 我觉得 / 明白）
- 原创红线：朱雀 16 字扫描零命中 + Bloom 反查零命中（详见 `prompt/COMMON.md`）

> `story-deslop` / `story-review` 已并入 `check_story.py`，**不单独建子技能**；规则以目标侧为准。
