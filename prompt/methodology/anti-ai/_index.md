# 去 AI 导航（anti-ai）

> 本目录**不重复建规则**。去 AI 味与质量审查的权威规则由**目标侧**以下文件持有：
> - `config/banned.json` — 硬禁模板词（命中即 AI 套路）
> - `config/anti_ai_rules.json` — 去 AI 规则
> - `config/advisory_rules.json` — 软信号密度告警
> - `config/deslop_whitelist.txt` — 白名单豁免
> - `prompt/COMMON.md` → 「去 AI 味自检清单（生成侧预防）」段（生成侧镜像，与质检侧同源不同职）
> - `check_story.py` §十二~§十五 — 质检终判（去 AI 味 / 退化检测 / advisory 密度 / 统一质量矩阵）

## 来源说明

`story-deslop`（去 AI 味）与 `story-review`（审查）能力已**完整并入** `check_story.py`，**不单独建子技能**。源 `references/anti-ai-writing.md` / `banned-words.md` 仅作历史溯源；规则以目标侧为准。

## 使用方式

- **写前预防**：读 `prompt/COMMON.md` 的「去 AI 味自检清单」+ 三遍法（内容 / 去 AI 味 / 人类吻合度）。
- **写后终检**：跑 `python check_story.py 成稿.txt`（§十二~§十五 输出统一质量矩阵）。
- 详细指针与文件映射见 [`pointers.md`](pointers.md)。

> 本目录与 `prompt/methodology/` 其它子目录（plot-emotion / character / short / genre-prose-cards / deconstruction / hooks）分工：**那些讲「怎么写」**，本目录讲「写完怎么去 AI 味、去哪查规则」。
