# 熔铸仿写 — 从零到短篇的完整系统

## 安装 (一次)

```bash
pip install -r requirements.txt
```

> 仅依赖 jieba 分词库，其余全为标准库。首次运行 fusion/clean 时会自动加载分词模型。

## 文件结构

```
熔铸版/
├── README.md                    ← 本文件
├── SKILL.md                     ← 方法论+规则 (给LLM读的)
├── requirements.txt             ← pip依赖清单
├── .gitignore                   ← 版本控制（禁止追踪产出文件）
│
├── run_pipeline.py              ← 核心入口: 12阶段管道
├── check_story.py               ← 质量检查: 9项爆款规则自动检测
│
├── prompt/                       ← 提示词库 (固定不可替代)
├── MAPPING.md                ← 文件映射表
├── prompt_inspiration.md     ← 创意构思+灵感风暴
├── prompt_character.md       ← 人设生成
├── prompt_outline.md         ← 大纲体系 (含 FILE_SECTION: 概要/大纲/细纲)
├── prompt_opening.md         ← 黄金开篇
├── prompt_writing.md         ← 写作规范
├── prompt_polish.md          ← 优化润色
├── prompt_expand.md          ← 续写扩写 (含 FILE_SECTION: 续写/扩写)
├── prompt_tools.md           ← 辅助工具
├── prompt_skill.md           ← 全流程 Skill
│
│
├── corpus/                      ← 语料库 (固定不可替代)
│   ├── 01_现代言情/              ← 都市/校园/职场
│   ├── 02_总裁豪门/              ← 霸总/豪门恩怨
│   ├── 03_重生复仇/              ← 重生/复仇/逆袭
│   ├── 04_穿越架空/              ← 穿越/架空历史
│   ├── 05_古代言情/              ← 宫斗/宅斗/古言 ← 现有122篇
│   ├── 06_玄幻仙侠/              ← 修仙/玄幻
│   ├── 07_悬疑惊悚/              ← 悬疑/灵异
│   ├── 08_甜宠虐恋/              ← 甜宠/虐文
│   └── 09_种田经商/              ← 种田/经商/美食
│
├── tools/                       ← 工具脚本 (固定不可替代)
│   ├── fusion.py                ← 指纹蒸馏: 5源文→类型公约数
│   ├── clean_commas.py          ← 后处理: 清理脏逗号
│   ├── inject_punctuation.py    ← 后处理: 按密度注入标点
│   └── audit.py                 ← 审计: 独创度+朱雀扫描
│
└── output/                      ← 所有生成产物 (临时，不入版本控制)
    └── (story.txt / *_llm_prompt.txt / fusion_context.txt 等)
```

### 三类文件定位

| 类型 | 目录 | 规则 |
|------|------|------|
| **源文件（固定不可替代）** | `run_pipeline.py` `check_story.py` `tools/` `prompt/` `corpus/` | 绝对不删，不能动位置 |
| **产出文件（临时生成）** | `output/` | 可随时清除，`.gitignore` 已忽略 |
| **项目数据** | `.workbuddy/` | WorkBuddy 工作日志和备份 |

## 使用流程

### Step 0: 准备语料

把同类型小说 `.txt` 放入对应分类目录。目前支持 9 个标准分类：

| 编号 | 分类 | 典型标签 |
|------|------|----------|
| 01 | 现代言情 | 都市/校园/职场 |
| 02 | 总裁豪门 | 霸总/豪门/契约 |
| 03 | 重生复仇 | 重生/复仇/逆袭/打脸 |
| 04 | 穿越架空 | 穿越/架空/异世 |
| 05 | 古代言情 | 宫斗/宅斗/古言/王爷/太子 |
| 06 | 玄幻仙侠 | 修仙/玄幻/仙侠 |
| 07 | 悬疑惊悚 | 悬疑/灵异/惊悚 |
| 08 | 甜宠虐恋 | 甜宠/虐文/追妻火葬场 |
| 09 | 种田经商 | 种田/经商/美食/科技兴国 |

每个分类下放 ≥5 篇 `.txt` 小说（管道默认选 5 篇做指纹互消，不足则取全部健康文件）。

### Step 1: 蒸馏指纹（管道运行）

```bash
python run_pipeline.py --category 05_古代言情
```

管道自动执行：

1. **扫描** — 从指定分类目录扫描所有 `.txt`
2. **筛选** — 剔除中文不足 500 字的损坏文件，随机选 5 篇健康源文
3. **蒸馏** — 提取每篇指纹（人物/情节/句式/高频词），5 份指纹取交集互消
4. **输出** — `output/fusion_context.txt`（LLM 生成用的完整上下文）

### Step 2: LLM 生成故事

将 `output/fusion_context.txt` 的全部内容**原封不动**复制给 LLM（Claude/GPT/DeepSeek 均可），LLM 据此生成一篇约 1000 字的原创短篇小说。

生成的故事保存为 `output/story.txt`。

### Step 3: 后处理

```bash
# 清理脏逗号（jieba 分词去除语法错误逗号）
python tools/clean_commas.py output/story.txt

# 注入标点密度（模拟番茄小说风格）
python tools/inject_punctuation.py output/story.txt --excl 0.15 --comma 1.2
```

| 参数 | 含义 | 默认值 |
|------|------|--------|
| `--excl` | 感叹号密度（每百字多少个！） | 0.15 |
| `--comma` | 逗号密度（每百字多少个，） | 1.2 |

### Step 4: 质量审计

```bash
# 爆款规则检查
python check_story.py output/story.txt

# 独创度审计（对比源文，确保 0 复制）
python tools/audit.py output/story.txt corpus/05_古代言情/*.txt
```

> 换分类只需改 `--category`：`01_现代言情` / `03_重生复仇` / `06_玄幻仙侠` ...

---

### 进阶: 分阶段创作（12 阶段提示词模式）

当需要对单个创作环节精细控制时，使用 `--stage` 切入指定阶段。

> **管道交叉**：蒸馏模式（无 `--stage`）和分阶段模式（有 `--stage`）共享 Step 1-2（扫描语料 + 蒸馏指纹）。区别仅在 Step 3：蒸馏模式输出 `fusion_context.txt`，分阶段模式加载提示词模板并输出 `{stage}_llm_prompt.txt`。

#### 基础用法

```bash
# 单阶段切入 → 输出 output/脑洞_llm_prompt.txt
python run_pipeline.py -s 脑洞 -c 05_古代言情

# 指定人设模板关键词
python run_pipeline.py -s 人设 -c 03_重生复仇 -t 黑莲花

# 交互式参数输入
python run_pipeline.py -s 开篇 -c 05_古代言情 --interactive
```

#### 链式传递（`--previous-output` / `-P`）

分阶段模式新增链式上下文传递，让后续阶段感知前序阶段的 LLM 输出，实现真正的流水线创作：

```bash
# Step 1: 脑洞 → 产出 output/脑洞_llm_prompt.txt (给LLM生成后保存为 output/脑洞_output.txt)
python run_pipeline.py -s 脑洞 -c 05_古代言情

# Step 2: 人设 ← 加载脑洞输出作为上下文
python run_pipeline.py -s 人设 -c 05_古代言情 -P output/脑洞_output.txt

# Step 3: 大纲 ← 加载人设输出
python run_pipeline.py -s 大纲 -c 05_古代言情 -P output/人设_output.txt

# ...以此类推，逐个阶段链式推进
```

> 管道也会自动推断：若 output/ 目录下存在 `{前阶段}_output.txt`，无需手动指定 `-P`，系统自动加载。每次运行重新扫描语料，但前序上下文保证了创作连续性。

完整 11 阶段：

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

> 前 8 个阶段为核心生成链，后 4 个为增强处理。每个阶段的提示词均为聚合蒸馏版（保留全部反 AI 检测技巧）。

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

不带 `--stage` 即为默认全流程模式：扫描→选文→蒸馏→输出 `fusion_context.txt`。

## 为什么朱雀检测不到

5篇不同作者的指纹在交集运算中互消。剩下的"睁眼/背叛/复仇"不属于任何单一作者，属于类型本身。朱雀对输出做16字扫描 vs 全部5篇源文 → 0匹配。

## 常见问题

**Q: 需要API密钥吗？**
A: 不需要。全本地运行。jieba是免费开源库。

**Q: 怎么添加新分类？**
A: 在 `corpus/` 下新建目录（如 `10_奇幻言情/`），放入该类型 .txt 小说，管道自动识别。

**Q: 生成的故事朱雀分数多少？**
A: 取决于LLM和后处理质量。熔铸保证内容层100%原创(0复制)，标点密度靠inject_punctuation补偿。

## 致谢

感谢真诚、友善、团结、专业的 [LinuxDo 社区](https://linux.do/latest)，让我学到很多 AI 相关的知识和玩法。

> LinuxDo — 学 AI，上 L 站

## 许可

MIT
