---
name: rongzhu-fangxie
description: 熔铸仿写 — 5源文指纹互消→类型公约数→100%原创+朱雀不可反查的番茄短篇生成系统。
license: MIT
compatibility: opencode>=3.0
metadata:
  version: "3.0"
  requires: pip install jieba
  author: ENI for LO
---

# 熔铸仿写

## 一句话

从5篇同类小说中提取公约数 → 用公约数生成全新故事 → 朱雀无法追溯到任何单一源文。

## 原理

```
仿写:   1篇源文 → 抽指纹 → 换皮 → 指纹残留 → 可被反查
熔铸:   5篇源文 → 5份指纹互消 → 只剩类型公约数 → 不可追溯
```

5个作者的不同指纹在交集运算中互相抵消。剩下的"女性/重生/背叛/复仇"不属于任何人——属于类型本身。

## 项目结构

```
熔铸版/
├── run_pipeline.py              ← 主入口 (12阶段管道)
├── check_story.py               ← 爆款规则自动检测
├── prompt/                       ← 9个聚合蒸馏提示词
├── corpus/                      ← 9分类语料库 (01-09)
├── tools/                       ← fusion/audit/clean/inject
└── output/                      ← 临时生成产物
```

prompt、corpus、tools 为固定不可替代文件。

## 完整流程

### Step 1: 蒸馏指纹

```bash
# 主入口（推荐）
python run_pipeline.py --category 05_古代言情

# 或直接用 fusion 工具
python tools/fusion.py --category 05_古代言情 --sample 5 -o output/fusion_context.txt
```

管道自动扫描 `corpus/分类名/` → 剔除损坏文件 → 随机选5篇 → 提取指纹 → 交集互消 → 输出 `output/fusion_context.txt`。

### Step 2: LLM生成

把 `output/fusion_context.txt` 的全部内容复制给LLM（Claude/GPT/DeepSeek），LLM据此生成约1000字原创短篇 → 保存为 `output/story.txt`。

### Step 3: 后处理

```bash
python tools/clean_commas.py output/story.txt
python tools/inject_punctuation.py output/story.txt --excl 0.15 --comma 1.2
```

### Step 4: 质检 + 审计

```bash
python check_story.py output/story.txt              # 9项爆款规则检查
python tools/audit.py output/story.txt corpus/05_古代言情/*.txt  # 独创度审计
```

## 分阶段创作 (12阶段提示词模式)

> 蒸馏模式（无 `--stage`）和分阶段模式共享 Step 1-2（扫描语料 + 蒸馏指纹），区别仅在 Step 3。

### 基础用法

```bash
python run_pipeline.py -s 脑洞 -c 05_古代言情       # 单阶段切入
python run_pipeline.py -s 人设 -c 03_重生复仇 -t 黑莲花  # 指定模板关键词
python run_pipeline.py -s 开篇 -c 05_古代言情 --interactive  # 交互式参数
```

### 链式传递 (`--previous-output` / `-P`)

后续阶段可感知前序阶段的 LLM 输出，实现真正的流水线创作。管道也会在 output/ 目录自动推断前序输出：

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

前8阶段为核心生成链，后4阶段为增强处理。所有提示词为聚合蒸馏版（保留全部反AI检测技巧）。

## 语料分类

9个标准分类目录（corpus/编号_名称/），管道自动识别：

`01_现代言情` `02_总裁豪门` `03_重生复仇` `04_穿越架空` `05_古代言情` `06_玄幻仙侠` `07_悬疑惊悚` `08_甜宠虐恋` `09_种田经商`

每分类建议放 ≥5 篇 `.txt`，不足5篇则取全部健康文件。

## 指纹互消规则

| 出现次数 | 判定 | 处理 |
|---|---|---|
| ≥3/5篇 | 类型公约数 | **保留使用** |
| 1-2/5篇 | 作者指纹 | **必须剔除** |

例: 5篇中死亡方式各不相同(坠机/沉塘/悬梁/踹死/车祸)→无公约数→禁止使用任何一篇的死亡方式→必须自创。

## 硬性约束

### 标点禁令 (永远)
- 禁止: ； ！！！ ？！ 「」

### 禁用句式
- 对X而言 / 一切都在 / 她心想/意识到/感到
- 一种说不出的 / 真正的X是Y / X的意义在于
- X既是Y也是Z / 谁说X就一定Y

### 禁用模板描写
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
