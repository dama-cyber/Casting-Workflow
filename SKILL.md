---
name: rongzhu-fangxie
description: 熔铸仿写 — 5源文 20维指纹双层互消→类型公约数→100%原创+朱雀不可反查(含Bloom反查增强)的番茄短篇生成系统。含人类风格对齐层+RAG受限检索+本地人类度判别，全部零模型。
license: MIT
compatibility: opencode>=3.0
metadata:
  version: "6.3"
  requires: pip install jieba
  author: ENI for LO
---

# 熔铸仿写 v6.3

## 一句话

从5篇同类小说中提取公约数 → 用公约数生成全新故事 → 朱雀无法追溯到任何单一源文。可选人类风格对齐层，用 corpus 统计分布校准文本节奏逼近人类写作。

## 原理

```
仿写:   1篇源文 → 抽指纹 → 换皮 → 指纹残留 → 可被反查
熔铸:   5篇源文 → 5份指纹互消 → 只剩类型公约数 → 不可追溯
v4.0:   熔铸 + 风格对齐层 → 统计分布校准 → 逼近人类写作节奏
v6.3:   20维指纹 + 双层互消 + Bloom反查(零模型) → 朱雀不可反查增强
```

5个作者的不同指纹在交集运算中互相抵消。剩下的「女性/重生/背叛/复仇」不属于任何人——属于类型本身。

## 项目结构

```
熔铸版/
├── run_pipeline.py              ← 主入口 (统一流: 12阶段 + 可选 capture/analyze/cover/browser)
├── check_story.py               ← 爆款规则检测 (8项+EI爽感+人类吻合+叙事偏离)
├── pyproject.toml               ← 项目配置（pip install -e . 入口）
├── prompt/                      ← COMMON.md(全局约束,自动注入) + 12阶段提示词 + methodology/(方法学卡库)
├── corpus/                      ← 语料库 (17目录10978篇，朱雀判100%人类)
├── config/                      ← 配置 (anti_pattern.json / narrative_taxonomy.json / degeneration_rules.json / advisory_rules.json)
├── tools/                       ← 工具脚本 (固定不可替代)
│   ├── __init__.py              ← 包初始化
│   ├── fusion.py                ← 20维指纹蒸馏 + 双层互消 + DNA演化增强 + 风格对齐注入
│   ├── dna_distiller.py        ← 20维叙事DNA 自动蒸馏(保形, 落盘 data/_narrative_dna.json)
│   ├── methodology_weaver.py   ← 方法论自动织入(approach A): 阶段+题材 织入 prompt/methodology/
│   ├── workflow_hooks.py        ← 统一流胶水: 扫榜/拆书注入 + 可选步骤 argv 拼装
│   ├── anti_pattern.py          ← 反模式引擎(爽感最大化)
│   ├── audit.py                 ← 独创度审计(16字扫描 + 全量Bloom反查模式)
│   ├── bloom_guard.py          ← Bloom反查(零模型, 全corpus 16字索引, 0命中=100%可靠PASS)
│   ├── narrative_features.py    ← 叙事特征提取(本地三交叉·叙事层, 流式8G安全)
│   ├── local_discriminator.py   ← 叙事判别(规则化, 零重型依赖)
│   ├── clean_commas.py         ← 脏逗号清理(jieba边界)
│   ├── inject_punctuation.py    ← 标点密度注入(jieba边界安全)
│   ├── human_profile.py         ← 人类画像提取(p10-p90)
│   ├── rag_retriever.py        ← RAG受限检索(纯元数据)
│   └── humanity_scorer.py      ← 人类度判别(0-100) + triple_cross_judge() 三交叉终判
├── data/                        ← 极贵重建缓存(勿删): Bloom位图/_narrative_dna.json/人类画像/叙事基线
└── output/                      ← 临时生成产物(可整目录删除重来)
```

prompt、corpus、tools、config、data 为固定不可替代文件（data 极贵重建，勿删）。原生工具 story_capture/story_analyze/cover_gen/browser_ctl 置于 tools/*_scripts/ 子目录。

## 完整流程

### Step 1: 蒸馏指纹

```bash
# 主入口（推荐）
python run_pipeline.py --category 05_古代言情

# 或直接用 fusion 工具（加风格对齐）
python tools/fusion.py --category 05_古代言情 --sample 5 --style-align -o output/fusion_context.txt

# 风格对齐 + RAG 约束
python tools/rag_retriever.py --category 07_重生复仇 --top-k 5 --out output/rag.json
python tools/fusion.py --category 07_重生复仇 --sample 5 --style-align --rag output/rag.json
```

管道自动扫描 `corpus/分类名/` → 剔除损坏文件 → 随机选5篇 → 提取 20 维指纹 → 单层维内互消 + 第二层维度组合互消（双层互消）→ 输出 `output/fusion_context.txt`。

`--style-align` 会在 prompt 中注入人类写作统计分布（句长/标点/短句比 p10-p90 区间），引导 LLM 产出节奏更贴近人类的目标文本。`--rag` 额外注入按题材召回的内容黑名单和类型公式（纯元数据，不泄露字面）。

### Step 2: LLM生成

把 `output/fusion_context.txt` 的全部内容复制给 LLM → 生成约 10000 字原创短篇 → 保存为 `output/story.txt`。

### Step 3: 后处理

```bash
python tools/clean_commas.py output/story.txt
python tools/inject_punctuation.py output/story.txt --excl 0.15 --comma 1.2
```

- `clean_commas.py`: jieba分词边界感知 + 词频阈值校验，防止误删有效逗号
- `inject_punctuation.py`: 基于jieba分词组边界插入，保护固定词组不被拆散

### Step 4: 质检 + 审计 + 人类度终判

```bash
# 爆款规则检查 (含人类吻合度评分)
python check_story.py output/story.txt
python check_story.py output/story.txt --genre 古言

# 独创度审计 (16字子串扫描 vs 所有源文)
python tools/audit.py output/story.txt corpus/05_古代言情/*.txt

# 人类度终判 (朱雀AI检测本地代理)
python tools/humanity_scorer.py output/story.txt
```

## 人类风格对齐层 (v6.3)

三层新增工具，均为可选、可开关、可回退：

| 工具 | 输入 | 输出 | 红线 |
|------|------|------|------|
| `human_profile.py` | corpus（或指定分类） | 人类写作统计画像（p10-p90 区间） | 不泄露字面 |
| `rag_retriever.py` | 题材标签 + top-k | 内容黑名单 + 类型公式（结构化元数据） | 不泄露字面 |
| `humanity_scorer.py` | 生成文本 | 0-100 人类度分（五维加权） | 不影响互消 |

**核心保护**：风格对齐层仅对齐统计分布，不动互消层、反模式层、16字零匹配审计。任何 corpus 字面片段不会进入生成上下文。

## 方法论自动织入 (approach A, 默认开启)

12 阶段每阶段运行时，按「阶段 + 题材」自动从 `prompt/methodology/` 织入方法学卡片（`methodology_weaver.py`）：

- **织入映射**：`STAGE_METHODOLOGY_MAP`（阶段→卡）+ `CATEGORY_GENRE_MAP`（题材→类型卡），题材卡缺失时回退到通用卡，绝不中断管道。
- **预算上限**：单阶段织入文本 ≤ 2600 字，超出截断，避免挤占生成指令。
- **安全约束**：剥离卡片 frontmatter、严禁将卡片原文原样写回正文；只作 prompt 上下文增强。
- **开关**：`--no-methodology` 全关；`--short-mode` 额外织入 `prompt/methodology/short/` 短篇专属卡。

```bash
python run_pipeline.py -s 正文 -c 05_古代言情            # 默认织入方法论
python run_pipeline.py -s 正文 --no-methodology         # 关闭
python run_pipeline.py -s 正文 --short-mode             # 短篇专属方法论
```

## 本地三交叉终判层 (朱雀不可反查增强, P0-T1)

无外部检测 API / 无 GPU / 8G 内存约束下的纯本地终判，替代「朱雀单点终判」：

| 交叉方 | 层 | 工具 | 说明 |
|------|------|------|------|
| Bloom | 字面层 | `bloom_guard.py` | 零模型位图，全 corpus 16 字子串索引，0 命中=100% 可靠 PASS |
| 统计层 | 人类度 | `humanity_scorer.py` | 8 维统计特征 0-100 打分 |
| 叙事层 | 叙事特征 | `narrative_features.py` + `local_discriminator.py` | 规则化中文叙事特征，零重型依赖 |

`triple_cross_judge()` 多数一致 + 阈值汇总；叙事层不做新单点。集成点：`audit.py`（稀有度降级弱判 FAIL→WARN）、`check_story.py`（§11 叙事偏离度）、`run_pipeline.py --narrative-check`（默认关）。红线：与 fusion 零耦合、不泄字面、零模型 CPU。

## 反模式生成 (`--anti`)

对蒸馏出的类型公约数逐项反转，最大化预期违背=爽感：

```bash
python run_pipeline.py -s 正文 -c 03_重生复仇 --anti
python run_pipeline.py -s 正文 -c 03_重生复仇 --anti --recipe 重度反模式
```

四档强度（详见 `config/anti_pattern.json`）：轻度(40-55) / 中度(55-70) / 重度(70-85) / 极限(85-100)

## 分阶段创作 (12阶段提示词模式)

```bash
python run_pipeline.py -s 脑洞 -c 05_古代言情       # 单阶段切入
python run_pipeline.py -s 人设 -c 03_重生复仇 -t 黑莲花  # 指定模板关键词
python run_pipeline.py -s 开篇 -c 05_古代言情 --interactive  # 交互式参数
```

链式传递前序阶段输出：

```bash
python run_pipeline.py -s 脑洞 -c 05_古代言情                     # → 脑洞_llm_prompt.txt
# (LLM生成后保存为 output/脑洞_output.txt)
python run_pipeline.py -s 人设 -c 05_古代言情 -P output/脑洞_output.txt  # 链式传递
```

| 序号 | 阶段 | 说明 | 提示词 |
|------|------|------|--------|
| 1 | 脑洞 | 创意/卖点/受众 | prompt_inspiration.md |
| 2 | 灵感风暴 | 书名/简介/开局大纲/小传 | prompt_inspiration.md |
| 3 | 人设 | 角色/金手指/关系 | prompt_character.md |
| 4 | 大纲 | 主线/情节点/高潮 | prompt_outline.md |
| 5 | 细纲 | 章节拆分/场次 | prompt_outline.md |
| 6 | 概要 | 200字浓缩梗概 | prompt_outline.md |
| 7 | 开篇 | 三句法开头 | prompt_opening.md |
| 8 | 正文 | 对话/节奏/叙事 | prompt_writing.md |
| 9 | 优化 | 归一化/拼接率 | prompt_polish.md |
| 10 | 润色 | 句式/用词多样化 | prompt_polish.md |
| 11 | 续写 | 情节延伸 | prompt_expand.md |
| 12 | 扩写 | 细节铺陈 | prompt_expand.md |

前8阶段为核心生成链，后4阶段为增强处理。所有提示词为聚合蒸馏版（保留全部爆款创作要求）。


## 统一流：可选前置/后置步骤 (capture/analyze/cover/browser)

`run_pipeline.py` 现为单条统一工作流：可选前置 `capture`(扫榜→注入脑洞) / `analyze`(拆书→注入人设·大纲·细纲·概要) → 12 阶段 generate 主干（methodology_weaver 每阶段织入保留）→ 可选后置 `cover` → 可选旁路 `browser`。任意可选步骤失败仅 WARN 不阻断主干。单独开关与 `--with` 取并集。

```bash
# 纯 generate（不传任何 step 开关 ≡ 旧默认 generate）
python run_pipeline.py -s 正文 -c 05_古代言情

# 聚合开启可选步骤
python run_pipeline.py -s 正文 -c 05_古代言情 --with capture,analyze,cover

# 单独步骤
python run_pipeline.py --capture --capture-platform fanqie --capture-channel 1 --capture-type 2
python run_pipeline.py --analyze --analyze-input 某书.txt --analyze-book 某书
GPT_IMAGE_API_KEY=xxx python run_pipeline.py -s 正文 --cover --cover-prompt "..."
python run_pipeline.py --browser --browser-action launch --browser-detect-only
```

## 20维DNA演化蒸馏 (互消层升级)

20 维叙事 DNA 从硬编码升级为从 corpus 自动蒸馏（`dna_distiller.py`，保形策略 = 内置词 ∪ 演化高频词），落盘 `data/_narrative_dna.json`，供 fusion 反转锚点更精准：

```bash
python run_pipeline.py -s 正文 -c 07_重生复仇 --rebuild-dna     # 强制重建
python run_pipeline.py -s 正文 -c 07_重生复仇 --dna-scope all   # 数据源: all=全量 corpus/ ；默认 category=同题材
```

增强指纹（默认关，开启也不注入生成指令，仅内部向量化）：`--enhanced-fingerprint` + `--ef-ngram` / `--ef-plot` / `--ef-syntax` 子开关。

## 语料分类

管道自动识别 `corpus/` 下的任意子目录，无需注册：

```
corpus/
├── 01_末世科幻(8)    02_悬疑灵异(21)   03_系统快穿(42)   04_病娇暗黑(7)
├── 05_古代言情(122)  06_家庭伦理(373)  07_重生复仇(85)   08_职场商战(36)
├── 09_现代校园(28)   10_先婚后爱(4)    11_虐恋情深(37)   12_狗血情感(30)
├── 13_娱乐圈(21)     14_现代言情(89)   15_豪门总裁(43)
├── 中篇(4324)  短篇(5708)   ← 长篇/短篇全集(单目录, 非分类)
└── NN_自定义/         ← 新建即用，无需修改管道代码
```

每分类建议放 ≥5 篇 `.txt`，不足5篇则取全部健康文件。

## 指纹互消规则 (v6.3 双层互消)

| 层 | 规则 | 处理 |
|---|---|---|
| 第一层·单维 | ≥60%源文共有项（维度内交集≥3篇，动态阈值 `max(3, n*0.6)`） | **整体反转/自创**，不可直抄任一源文 |
| 第二层·组合 | 高共有「维度组合钢印」（按组合强度降序取 top-10） | **维度名+组合值同时错位自创** |
| 剔除项 | <60%源文独有（作者指纹） | **必须剔除** |

例: 5篇中死亡方式各不相同(坠机/沉塘/悬梁/踹死/车祸)→无公约数→禁止复用任何一篇→必须自创。

---

## 硬性约束

### 标点禁令 (永远)
- 禁止: `；` `！！！` `？！`
- **禁止破折号 `——`**（AI 明显标志），对话中断统一用「……」

### AI 标志禁用清单 (硬规则)

| 类别 | 禁用项 | 替代方案 |
|------|------|------|
| 破折号 | `——` | 对话中断→「……」，句内→逗号/冒号 |
| 突转词 | 忽然 / 猛地 / 瞬间 | 直接描述动作，删突转标记词 |
| 对比结构 | 「不是X，是Y」高密度 | 自然叙事句，保反转意味不套模板 |
| 格式化比喻 | 像一根 / 像极了 / 活脱脱 | 白描或动作化替代 |
| 软副词 | 轻轻 / 缓缓 / 微微 / 悄悄 | 具体动作替代程度修饰 |
| 群像套路 | 满座哗然 / 面面相觑 / 分明是 | 各角色差异化反应 |
| 升华金句 | 段落末高密度哲理总结 | 情绪收束用动作或留白 |
| 思维标记 | 我常想 / 我觉得 / 明白 | 感官描写替代内心独白标记 |

### 传统禁用句式
- 对X而言 / 一切都在 / 她心想/意识到/感到
- 一种说不出的 / 真正的X是Y / X的意义在于
- X既是Y也是Z / 谁说X就一定Y

### 传统禁用模板描写
- 眼中闪过 / 嘴角勾起 / 眼眶微红
- 不可置信 / 眼底闪过 / 咬了咬唇

### 写作规则
- 第一人称
- 数字分节: 1 2 3... (裸数字)
- 分隔符: ……
- 精确数字: 金额/时间/数量精确到个位
- 压缩情感循环: 每弧≤8句
- 巧合推动情节: ≥1次意外发现
- 句式突变: 相邻3句不同结构
- 番茄小白话: 复句≤30%
- 零思维标记: 禁用 心想/意识到/感到/觉得/认为
- 多主语修复: 无 他他他/她她她
- 语域碰撞: 100字内正式+粗俗并置
- 人设标签≥3: 杀伐果断/清醒独立/拒绝内耗/黑莲花/人间清醒/搞钱脑
- 禁用人设: 圣母/优柔寡断/憋屈/精神内耗
