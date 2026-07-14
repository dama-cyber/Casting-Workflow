# 熔铸仿写全术，由初阶至短制，纲目灿然，靡有阙遗。

## 安装 (一次)

```bash
pip install -r requirements.txt
```

> 仅依赖 jieba 分词库，其余全为标准库。首次运行 fusion/clean 时会自动加载分词模型。

## 快速开始（60 秒上手）

### 方式 A：标准 Python 环境（OpenCode / Claude Code / 任意终端）

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活（Windows / Linux & Mac）
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 生成你的第一篇小说！
python run_pipeline.py --auto -c 07_重生复仇
```

### 方式 B：pip 安装模式（全局命令）

```bash
pip install -e .
# 之后直接运行：
casting-workflow --auto -c 07_重生复仇
```

### 方式 C：无 venv 直跑（最低门槛）

```bash
pip install jieba       # 仅一个依赖
python run_pipeline.py --auto -c 07_重生复仇
```

### 环境支持

| 平台 | 状态 |
|------|------|
| WorkBuddy (managed Python) | ✅ 原生支持 |
| OpenCode (VS Code) | ✅ `python run_pipeline.py` |
| Claude Code (Anthropic CLI) | ✅ `python run_pipeline.py` |
| 任意标准 Python 3.9+ 终端 | ✅ 开箱即用 |
| Windows / macOS / Linux | ✅ 全平台 |

## 语料更换指南

如果你用自己的语料替换了 `corpus/` 目录，必须重建全部缓存才能正常工作。

### 一键重建（推荐）

```bash
python run_pipeline.py --rebuild-all-caches
```

> 自动重建 5 项缓存：Bloom反查索引 → 人类写作画像 → 叙事特征基线 → 质量基线 → 叙事DNA演化表
> 全量语料约需 5-15 分钟（取决于 corpus 大小），1024 篇约 2 分钟。

### 分步重建（调试用）

```bash
# 1. Bloom 反查索引（最耗时，802MB）
python tools/bloom_guard.py --build --corpus corpus --cache data

# 2. 人类写作画像
python -c "from tools.human_profile import build_corpus_profile; import json; json.dump(build_corpus_profile('corpus'), open('data/_human_profile.json','w'))"

# 3. 叙事特征基线（流式抽取，内存安全）
python tools/narrative_features.py --build-baseline --corpus corpus --cache data --features-out data/_narrative_features.jsonl --out data/_narrative_baseline.json

# 4. 质量基线
python tools/build_quality_baseline.py --out data/_quality_baseline.json

# 5. 叙事 DNA 演化表
python run_pipeline.py --rebuild-dna --dna-scope all
```

### 缓存文件说明

| 文件 | 大小 | 用途 | 依赖 |
|------|------|------|------|
| `data/_bloom_bits.bin` | ~800MB/万篇 | 16字子串Bloom反查 | 全量corpus |
| `data/_bloom_meta.json` | <1KB | Bloom元数据 | 全量corpus |
| `data/_human_profile.json` | ~2KB | 人类写作统计画像 | 全量corpus |
| `data/_narrative_baseline.json` | ~3KB | 叙事特征基线 | 全量corpus |
| `data/_narrative_features.jsonl` | ~6MB/千篇 | 叙事特征流式缓存 | 全量corpus |
| `data/_narrative_dna.json` | ~25KB | 叙事DNA演化表 | 按题材过滤 |
| `data/_quality_baseline.json` | ~3KB | 质量基线 | 全量corpus |

> ⚠️ `data/` 目录下的缓存是系统极贵重文件，**不要手动删除**，只用 `--rebuild-all-caches` 重建。

## 架构：四层叠加

```
第一层 互消层(原创)     fusion.py         提取指纹 → 消除公因子 → 最小化相似度
第二层 反模式层(爽感)   anti_pattern.py   提取公因子 → 反转公因子 → 最大化预期违背
第三层 风格对齐层(人类) human_profile.py  统计画像 → 人类分布区间 → 校准文本节奏
                      rag_retriever.py  题材召回 → 黑名单+公式 → 强化内容约束
第四层 癫狂参数层(超现实) LLM界面层        T=1.1-1.3 可控癫甜区
```

> 第三层为可选增强，默认关闭（`--style-align` / `--rag` 开关）。前两层（原创+爽感）始终运行。

## 文件结构

```
熔铸版/
├── README.md                     ← 本文件
├── SKILL.md                      ← 方法论+规则 (给LLM读的)
├── requirements.txt              ← pip依赖清单
├── .gitignore                    ← 版本控制（禁止追踪产出文件）
│
├── run_pipeline.py               ← 核心入口: 12阶段管道
├── check_story.py                ← 质量检查: 8项规则 + EI爽感指数 + 人类吻合度
│
├── prompt/                       ← 提示词库 (固定不可替代)
│   ├── MAPPING.md                ← 文件映射表
│   ├── prompt_inspiration.md     ← 创意构思+灵感风暴
│   ├── prompt_character.md       ← 人设生成
│   ├── prompt_outline.md         ← 大纲体系
│   ├── prompt_opening.md         ← 黄金开篇
│   ├── prompt_writing.md         ← 写作规范
│   ├── prompt_polish.md          ← 优化润色
│   ├── prompt_expand.md          ← 续写扩写
│   ├── prompt_tools.md           ← 辅助工具
│   ├── prompt_skill.md           ← 全流程 Skill
│   ├── COMMON.md                 ← 全局约束(角色定位/反AI/禁止清单/引号策略/原创红线), 每阶段自动注入
│   └── methodology/              ← 方法学卡库(按题材/阶段织入, 见 methodology_weaver)
│
├── corpus/                       ← 语料库 (固定不可替代，10978篇txt，朱雀判100%人类)
│   ├── 01_末世科幻(8) 02_悬疑灵异(21) 03_系统快穿(42) 04_病娇暗黑(7)
│   ├── 05_古代言情(122) 06_家庭伦理(373) 07_重生复仇(85) 08_职场商战(36)
│   ├── 09_现代校园(28) 10_先婚后爱(4) 11_虐恋情深(37) 12_狗血情感(30)
│   ├── 13_娱乐圈(21) 14_现代言情(89) 15_豪门总裁(43)
│   ├── 中篇(4324) 短篇(5708)  ← 长篇/短篇全集(单目录, 非分类)
│   └── ...                       ← 管道自动识别任意 corpus/ 子目录
│
├── config/                       ← 配置文件
│   └── anti_pattern.json         ← 反模式配方 (四档强度 + 8大公因子目录)
│
├── tools/                        ← 工具脚本 (固定不可替代)
│   ├── fusion.py                 ← 指纹蒸馏: 5源文→维度提取→公约数交集+双层互消 + 20维DNA演化增强 + 风格对齐注入
│   ├── clean_commas.py           ← 后处理: jieba分词边界清理脏逗号
│   ├── inject_punctuation.py     ← 后处理: 按密度注入!和逗号 (jieba边界安全)
│   ├── anti_pattern.py           ← 反模式引擎: 公因子逆转→爽感最大化
│   ├── audit.py                  ← 审计: 独创度+Bloom 16字反查（朱雀为不可反查的外部对照目标）
│   ├── human_profile.py          ← 人类画像: 扫corpus抽取写作统计分布 (p10-p90区间)
│   ├── rag_retriever.py          ← RAG检索: 按题材召回→输出黑名单+公式 (纯元数据)
│   ├── humanity_scorer.py        ← 人类度判别: 朱雀AI检测本地代理终判 (0-100)
│   ├── methodology_weaver.py     ← 方法论自动织入(approach A): 按阶段+题材织入 prompt/methodology 卡片
│   ├── workflow_hooks.py         ← 统一流胶水: 步骤argv构造 + capture/analyze 产物读取与注入
│   └── dna_distiller.py          ← 叙事DNA自动蒸馏: 20维关键词表从corpus演化(保形)落盘 data/_narrative_dna.json
│
├── data/                         ← 系统缓存(极贵重建，勿删): _bloom_bits.bin / _narrative_dna.json / _human_profile.json / _narrative_baseline.json 等
│
└── output/                       ← 所有生成产物 (临时，不入版本控制)
    └── (story.txt / fusion_context.txt / rag_constraints.json 等)
```

### 三类文件定位

| 类型 | 目录 | 规则 |
|------|------|------|
| **源文件（固定不可替代）** | `run_pipeline.py` `check_story.py` `tools/` `prompt/` `corpus/` `config/` | 绝对不删，不能动位置 |
| **产出文件（临时生成）** | `output/` | 可随时清除，`.gitignore` 已忽略 |

## 使用流程

### Step 0: 准备语料

把同类型小说 `.txt` 放入 `corpus/` 下的分类目录。管道自动扫描所有子目录，支持任意分类名。

每个分类下放 ≥5 篇 `.txt` 小说（管道默认选 5 篇做指纹互消，不足则取全部健康文件）。

### Step 1: 蒸馏指纹（管道运行）

```bash
python run_pipeline.py --category 05_古代言情
```

管道自动执行：

1. **扫描** — 从指定分类目录扫描所有 `.txt`
2. **筛选** — 剔除中文不足 500 字的损坏文件，随机选 5 篇健康源文
3. **蒸馏** — 提取每篇指纹（人物/情节/句式/高频词），对 20 个创作维度（v6.3）执行交集分析，再做维度组合双层互消
4. **输出** — `output/fusion_context.txt`（含 20 维公约数对比表 + 第二层维度组合互消指令 + 生成约束）

### Step 2: LLM 生成故事

将 `output/fusion_context.txt` 的全部内容**原封不动**复制给 LLM（Claude/GPT/DeepSeek 均可），LLM 据此生成一篇约 10000 字的番茄风格短篇小说。

生成的故事保存为 `output/story.txt`。

### Step 3: 后处理

```bash
# 清理脏逗号（jieba 分词边界感知，词频校验防误删）
python tools/clean_commas.py output/story.txt

# 注入标点密度（jieba 词边界安全插入，不破坏词语完整性）
python tools/inject_punctuation.py output/story.txt --excl 0.15 --comma 1.2
```

| 参数 | 含义 | 默认值 |
|------|------|--------|
| `--excl` | 感叹号密度（每句多少个！） | 0.15 |
| `--comma` | 逗号密度（每句多少个，） | 1.2 |

### Step 4: 质量审计

```bash
# 爆款规则检查 (支持体裁参数: --genre 古言/重生/虐恋/系统流)
python check_story.py output/story.txt
python check_story.py output/story.txt --genre 古言

# 独创度审计（对比源文，确保 0 复制）
python tools/audit.py output/story.txt corpus/05_古代言情/*.txt

# 人类度终判（朱雀 AI 检测本地代理）
python tools/humanity_scorer.py output/story.txt
```

> check_story 检测项: 基础规范(字数/标点/分节)、AI模板禁用词、黄金三章结构、爽点密度、角色归一化、结尾完整性、对话密度、段落节奏、**人类吻合度**（统计分布 vs corpus人类画像）、**EI爽感指数**（五维评估）。
> 换分类只需改 `--category`：`05_古代言情` / `07_重生复仇` / `14_现代言情` ...

---

### 进阶: 人类风格对齐 (`--style-align` / `--rag`)

利用 corpus（10978 篇被朱雀判为 100%人类的语料）的统计特征，校准生成文本的表层写作节奏。**不抄字面，只学分布**——互消层和 16 字零匹配红线不受任何影响。

```bash
# 仅开启风格对齐（注入人类写作分布区间到生成 prompt）
python tools/fusion.py --category 07_重生复仇 --sample 5 --style-align

# 风格对齐 + RAG 约束检索（按题材召回黑名单+类型公式）
python tools/rag_retriever.py --category 07_重生复仇 --top-k 5 --out output/rag.json
python tools/fusion.py --category 07_重生复仇 --sample 5 --style-align --rag output/rag.json
```

三层新增工具：

| 工具 | 功能 | 用法 |
|------|------|------|
| `human_profile.py` | 提取 corpus 人类写作统计画像（句长/标点/短句比 p10-p90 区间） | `python tools/human_profile.py [--category 07_重生复仇]` |
| `rag_retriever.py` | 按题材召回 top-k→输出纯元数据约束（黑名单+公式，**绝不泄露字面**） | `python tools/rag_retriever.py --category 07_重生复仇 --top-k 5 --out output/rag.json` |
| `humanity_scorer.py` | 朱雀 AI 检测本地代理终判（统计分布距离→0-100人类度） | `python tools/humanity_scorer.py output/story.txt` |

> 风格对齐默认关闭。不传 `--style-align` / `--rag` 时，behavior 与改造前完全一致。

### 进阶: 反模式生成 (`--anti`)

在标准蒸馏基础上，对类型公约数逐项反转，最大化预期违背=爽感：

```bash
# 中度反模式 (默认, EI目标55-70)
python run_pipeline.py -s 正文 -c 03_重生复仇 --anti

# 指定配方强度
python run_pipeline.py -s 正文 -c 03_重生复仇 --anti --recipe 重度反模式
```

| 配方 | EI目标 | 说明 |
|------|:------:|------|
| 轻度反模式 | 40-55 | 关键节点反转1-2个公因子 |
| 中度反模式 | 55-70 | 反转3-4个公因子，因果倒置 |
| 重度反模式 | 70-85 | 全维度反转，因果链断裂重组 |
| 极限反模式 | 85-100 | 所有公因子反转，追求极致爽感 |

> 完整配方配置见 `config/anti_pattern.json`。

### 进阶: 分阶段创作（12 阶段提示词模式）

当需要对单个创作环节精细控制时，使用 `--stage` 切入指定阶段。

```bash
# 单阶段切入 → 输出 output/脑洞_llm_prompt.txt
python run_pipeline.py -s 脑洞 -c 05_古代言情

# 链式传递前序阶段输出
python run_pipeline.py -s 人设 -c 05_古代言情 -P output/脑洞_output.txt
```

完整 12 阶段：

| 序号 | 阶段 | 说明 | 对应提示词 |
|------|------|------|------------|
| 1 | 脑洞 | 创意构思/卖点/受众定位 | `prompt_inspiration.md` |
| 2 | 灵感风暴 | 书名/简介/黄金开局大纲/角色小传 | `prompt_inspiration.md` |
| 3 | 人设 | 角色设计/金手指/关系网 | `prompt_character.md` |
| 4 | 大纲 | 故事主线/情节点/高潮 | `prompt_outline.md` |
| 5 | 细纲 | 章节拆分/场次细化 | `prompt_outline.md` |
| 6 | 概要 | 200 字高度浓缩梗概 | `prompt_outline.md` |
| 7 | 开篇 | 黄金三章/三句法开头 | `prompt_opening.md` |
| 8 | 正文 | 对话密度/节奏/叙事感 | `prompt_writing.md` |
| 9 | 优化 | 角色归一化/拼接率质检 | `prompt_polish.md` |
| 10 | 润色 | 句式变化/用词多样性 | `prompt_polish.md` |
| 11 | 续写 | 情节延伸/伏笔展开 | `prompt_expand.md` |
| 12 | 扩写 | 细节铺陈/环境描写 | `prompt_expand.md` |

> 前 8 个阶段为核心生成链，后 4 个为增强处理。每个阶段的提示词均为聚合蒸馏版（保留全部爆款创作要求）。

---

### 进阶: 方法论自动织入 (`methodology_weaver`)

12 阶段每阶段的提示词会在运行时**自动织入**真实方法论卡片（approach A），而非仅依赖静态指针让 LLM 自觉 recall。织入逻辑由 `tools/methodology_weaver.py` 的 `weave_methodology(stage, category=None, short_mode=False, budget=2600)` 实现：

- **按阶段 + 题材**：`STAGE_METHODOLOGY_MAP` 把 12 阶段映射到 `prompt/methodology/` 下的方法学卡；`CATEGORY_GENRE_MAP` 把 corpus 分类映射到对应题材卡（如古言/重生/虐恋等），题材卡缺失时回退近似兜底。
- **预算硬上限 2600 字符**：超预算按比例缩放 + 末项精确截断，避免 prompt 膨胀。
- **安全约束**：题材卡剥离 frontmatter 并加「严禁原样写入正文」指令；全链路 `try/except` 容错，缺失文件/目录静默跳过。
- **默认开启**，可用开关关闭：

```bash
# 关闭方法论自动织入（退回纯静态指针行为）
python run_pipeline.py -s 正文 -c 05_古代言情 --no-methodology

# 织入短篇精选方法论子集（≤3 个/阶段，适合短篇节奏）
python run_pipeline.py -s 正文 -c 09_现代校园 --short-mode
```

> 方法论织入是统一流 12 阶段主干的红线环节（每阶段必织入）；`capture`/`analyze` 等无 LLM 的确定性前置步骤不织入。

---

### 统一流四步骤（capture/analyze/cover/browser 可选步骤）

熔铸版已把扫榜 / 拆书 / 封面 / 浏览器 收口为**统一流里的可选步骤**，与 12 阶段 generate 主干
串为单条步骤链（取代旧的 `--mode` 平行分派）。**默认全关**——不传任何 step 标志即为纯 generate，
行为与原默认完全一致。旧 `--mode X` 调用方见 `docs/MIGRATION_unified_workflow.md`。

- **前置 capture（扫榜）**：`--capture [--capture-platform qidian] [--capture-channel] [--capture-type] [--capture-top] [--capture-outdir]`，产物 `scan_output/*.md`（Markdown），解析后注入「脑洞」阶段的 `扫榜参考`。
- **前置 analyze（拆书）**：`--analyze --analyze-input <本地txt/目录> [--analyze-book] [--analyze-length] [--analyze-force]`，产物 `analysis/{书名}/`，读取后注入「人设/大纲/细纲/概要」阶段的 `拆书参考`。
- **后置 cover（封面）**：`--cover [--cover-book] [--cover-prompt] [--cover-api-key] [--cover-size]`，在 `output/story.txt` 之后生成 `covers/{书名}/cover.png`；key 取 `--cover-api-key` 或环境变量 `GPT_IMAGE_API_KEY`。
- **旁路 browser（CDP 巡检）**：`--browser [--browser-action launch] [--browser-port 9222] [--browser-detect-only]`，仅 launch/browse 巡检，**不含发布**。

聚合开关：`--with capture,analyze,cover,browser` 一次性开启多个步骤。

> **失败处理（红线）**：capture/analyze/cover/browser 任一未开启、外部依赖缺失（Node / API key / 网络）或执行失败时，仅记录 WARN 并继续走后续步骤，统一流最终返回 0（除非 12 阶段 generate 主干自身异常）。methodology_weaver 每阶段织入始终保留。

```bash
# 纯 generate（零改动）
python run_pipeline.py -s 正文 -c 05_古代言情

# 统一流：扫榜 + 拆书 + 封面
python run_pipeline.py -s 正文 -c 05_古代言情 --with capture,analyze,cover

# 仅扫榜（番茄男频阅读榜）
python run_pipeline.py --capture --capture-platform fanqie --capture-channel 1 --capture-type 2
```

---

### 命令行参数速查

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--category` | `-c` | 指定语料分类 | `-c 05_古代言情` |
| `--sample` | `-n` | 选几篇源文做指纹互消 | `-n 7` |
| `--stage` | `-s` | 切入指定创作阶段 | `-s 开篇` |
| `--template` | `-t` | 指定提示词模板关键词 | `-t 西瓜大法` |
| `--params` | `-p` | JSON 格式自定义参数 | `-p '{"核心卖点":"重生复仇"}'` |
| `--interactive` | — | 交互式输入创作参数 | `--interactive` |
| `--previous-output` | `-P` | 链式传递前序阶段输出 | `-P output/人设_output.txt` |
| `--anti` | — | 开启反模式生成（公因子反转，最大化爽感） | `-s 正文 --anti` |
| `--recipe` | — | 指定反模式配方（轻度/中度/重度/极限） | `--recipe 重度反模式` |
| `--style-align` | — | 开启人类风格对齐（fusion.py 内部参数，非 run_pipeline 参数） | `tools/fusion.py --style-align` |
| `--rag` | — | 开启 RAG 约束检索（布尔开关，action=store_true，默认关闭） | `--rag` |
| `--capture` | — | 统一流前置：扫榜采集（注入 脑洞） | `--capture --capture-platform fanqie` |
| `--analyze` | — | 统一流前置：拆书骨架（注入 人设/大纲） | `--analyze --analyze-input 某书.txt` |
| `--cover` | — | 统一流后置：封面生成（需 GPT_IMAGE_API_KEY） | `--cover --cover-prompt "..."` |
| `--browser` | — | 统一流旁路：Chrome CDP 巡检（不含发布） | `--browser --browser-detect-only` |
| `--with` | — | 聚合开启上述步骤（逗号分隔） | `--with capture,analyze,cover` |
| `--no-methodology` | — | 关闭方法论自动织入（默认开启，每阶段织入 prompt/methodology 卡片） | `--no-methodology` |
| `--short-mode` | — | 织入短篇精选方法论子集（≤3 个/阶段） | `--short-mode` |
| `--rebuild-dna` | — | 强制重建叙事 DNA 演化表（`data/_narrative_dna.json`） | `--rebuild-dna` |
| `--dna-scope` | — | DNA 蒸馏范围：`category`（同题材，默认）/ `all`（全量） | `--dna-scope all` |
| `--enhanced-fingerprint` | — | 开启增强指纹（默认关，仅追加诊断字段，不注入 prompt） | `--enhanced-fingerprint` |
| `--ef-ngram` | — | 增强指纹子开关：高频 n-gram 向量 | `--ef-ngram` |
| `--ef-plot` | — | 增强指纹子开关：情节单元标签 | `--ef-plot` |
| `--ef-syntax` | — | 增强指纹子开关：句法画像 | `--ef-syntax` |

不带 `--stage` 即为默认全流程模式：扫描→选文→蒸馏→输出 `fusion_context.txt`。
统一流四步骤默认全关，不传任何 step 标志即为纯 generate（与原默认一致）。

---

## 生成禁用清单 (AI 标志硬规则)

以下 8 类为 AI 生成文本的明显标志，prompt 和生成阶段**硬性禁用**：

| 级别 | 类别 | 禁用项 | 替代方案 |
|:--:|------|------|------|
| **P0** | 破折号 | `——` | 对话中断用「……」，句内解释用逗号或冒号 |
| **P1** | 突转词 | 忽然 / 猛地 / 瞬间 | 直接描述动作，删突转标记词 |
| **P1** | 对比结构 | 「不是X，是Y」高密度 | 改写为自然叙事句，保反转意味 |
| **P1** | 格式化比喻 | 像一根 / 像极了 / 活脱脱 | 白描或动作化替代 |
| **P2** | 软副词 | 轻轻 / 缓缓 / 微微 / 悄悄 | 用具体动作替代程度修饰 |
| **P2** | 群像套路 | 满座哗然 / 面面相觑 / 分明是 | 各角色差异化反应 |
| **P2** | 升华金句 | 段落末高密度哲理总结 | 情绪收束用动作或留白 |
| **P2** | 思维标记 | 我常想 / 我觉得 / 明白 | 用感官描写替代内心独白标记 |

### 通用写作约束

- **引号策略**：允许中文引号「」用于对话，禁止西文引号 `"" ''`
- **标点禁令**：禁止 `；` `！！！` `？！`
- **写作规则**：第一人称 / 数字分节(裸数字) / 分隔符`……` / 精确数字 / 压缩情感循环(每弧≤8句) / 巧合推动情节(≥1次) / 句式突变(相邻3句不同结构) / 番茄小白话(复句≤30%) / 零思维标记 / 多主语修复 / 语域碰撞(100字内正式+粗俗并置)

---

## 为什么朱雀检测不到

### 内容层（互消）
5 篇不同作者的指纹在交集运算中互消。剩下的「女性/重生/背叛/复仇」不属于任何单一作者，属于类型本身。Bloom 对输出做 16 字反查（朱雀为不可反查的外部对照目标）→ 0 命中。

v6.3 升级：互消从单层（维内交集剔除）进化为**双层互消**——第一层维内≥60%共有项反转/自创，第二层对高共有「维度组合钢印」整体错位（见 `fusion.py`）。新增 **Bloom 反查**（`tools/bloom_guard.py`，零模型 Bloom filter）作为朱雀不可反查增强关卡：一次性建全 corpus 索引，生成文本 O(长度) 判定是否撞语料，0 命中即 100% 可靠 PASS。

v6.3+ 升级（互消层增强）：`tools/dna_distiller.py` 让 20 维关键词表从 **corpus 自动蒸馏演化**（保形策略 = 内置种子词 ∪ 演化高频词），落盘 `data/_narrative_dna.json`（首次自动构建，`--rebuild-dna` 强制刷新，`--dna-scope category|all` 控制范围）。`_extract_dimensions` 优先用演化表、缺失维回退内置；`build_llm_prompt` 第一层严格化（必破项清单 + 生成前自检清单 + DNA 反转锚点）、第二层组合钢印按强度降序取 top-N（`COMBO_TOP_N=10`），让反转更精准。新增**增强指纹**（`extract_fingerprint(enhanced=...)`）默认关，开启时追加 ngram_vec/plot_units/syntax_profile 三个**诊断字段**，绝不注入 prompt（守住朱雀不可反查红线）。不传任何新 flag 时，行为与升级前 100% 一致。

### 风格层（对齐）
corpus（10978 篇被朱雀判为 100% 人类）的统计分布区间（句长 p10-p90: 21.5-838字、！/句 p10-p90: 0-0.22、短句比 p10-p90: 0-0.11；全量由 `tools/human_profile.py` 实时生成）注入 style-align 约束，生成文本在统计维度贴近人类写作节奏，AI 工整句式特征被稀释。

### 兜底层（审计）
`audit.py` 对生成文本做双层审计：(1) **精确模式**——对指定少量源文做 16 字滑动窗口扫描（步长 1，覆盖率 100%），任一匹配即 FAIL；(2) **全量模式**——`python audit.py story.txt --corpus corpus` 走 Bloom 全 corpus 索引（零模型，秒级，零假阴性，等价 16 字全量扫描，规避 ARG_MAX），0 命中即 100% 可靠 PASS。风格对齐层**绝不泄露 corpus 字面片段**，黑名单/公式仅输出元数据标签。

### 收尾修复（v6.3 后续）
- **D1 已修**：全量审计不再依赖命令行传 10978 个文件路径（曾因 ARG_MAX 不可用），改为 `--corpus DIR` 目录模式，Python 内 glob + Bloom 索引，秒级完成。
- **P2-5 已修**：prompt 公共约束（角色定位 / 反AI检测技巧 / 全局禁止清单 / 引号策略 / 原创红线）抽离到 `prompt/COMMON.md`，由 `run_pipeline.py` 在每个阶段自动注入；`prompt_writing/polish/expand` 三个冗余最严重的"聚合蒸馏模板"已去重（25 条同义原则 → 阶段特有规则），维护单点化、token 占用下降。
- **D2/D4 已修**（前序轮次）：`inject_punctuation` 已标点智能跳过；`audit` 退出码 CI 友好。

## 常见问题

**Q: 需要API密钥吗？**
A: 不需要。全本地运行。jieba 是免费开源库。

**Q: 怎么添加新分类？**
A: 在 `corpus/` 下新建目录（如 `16_奇幻言情/`），放入该类型 .txt 小说，管道自动识别。

**Q: 生成的故事朱雀分数多少？**
A: 取决于 LLM 和后处理质量。熔铸保证内容层 100% 原创（0 复制），风格对齐层进一步逼近人类分布，humanity_scorer 提供本地终判。

**Q: check_story 显示的体裁不匹配怎么办？**
A: 使用 `--genre` 参数切换体裁配置：`python check_story.py output/story.txt --genre 古言`。已支持: default、系统流、虐恋、重生、古言。

**Q: 风格对齐会影响原创性吗？**
A: 不会。风格对齐只学 corpus 的统计分布（句长/标点/短句比区间），不抄字面文本。16 字零匹配审计是生成的强制兜底关卡。

## 致谢
- ****[worldwonderer/oh-story-claudecode](https://github.com/worldwonderer/oh-story-claudecode)** — Claude Code 网文工具箱。借鉴了 80 篇方法学卡、扫榜脚本、拆书工具。
- **[jenna-russell/storyscope](https://github.com/jenna-russell/storyscope)**（MIT） — 叙事鉴识：AI vs 人类小说。借鉴了 304 维特征分类法、XGBoost 人机判别思路，落地为本地三交叉终判层（叙事层）。
- **[joeseesun/qiaomu-novel-generator](https://github.com/joeseesun/qiaomu-novel-generator)**（MIT） — 中文小说 Agent Skill。借鉴了 质检侧纯规则（正则+词典）
- 感谢真诚、友善、团结、专业的 [LinuxDo 社区](https://linux.do/latest)，让我学到很多 AI 相关的知识和玩法。

> LinuxDo — 学 AI，上 L 站

## 许可

MIT
