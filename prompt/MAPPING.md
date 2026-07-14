# prompt 文件映射表 (v3.1)

## 文件结构

| 文件 | 对应阶段 | FILE_SECTION |
|------|----------|--------------|
| `prompt_inspiration.md` | 脑洞/灵感风暴 | 脑洞生成器、灵感风暴 |
| `prompt_character.md` | 人设 | 人设生成器 |
| `prompt_outline.md` | 大纲/细纲/概要 | 大纲相关、细纲生成、概要生成器 |
| `prompt_opening.md` | 开篇 | 黄金开篇 |
| `prompt_writing.md` | 正文 | 写作要求 |
| `prompt_polish.md` | 优化/润色 | 优化建议、润色 |
| `prompt_expand.md` | 续写/扩写 | 续写、扩写 |
| `prompt_tools.md` | 辅助工具 | 拆书、提示词优化（手动使用） |
| `prompt_skill.md` | 全流程 | 全流程Skill（给LLM读，非管道阶段） |

## pipeline 映射 (12阶段)

```
脑洞   → prompt_inspiration.md (FILE_SECTION: 脑洞生成器)
灵感风暴 → prompt_inspiration.md (FILE_SECTION: 灵感风暴)
人设   → prompt_character.md   (FILE_SECTION: 人设生成器)
大纲   → prompt_outline.md     (FILE_SECTION: 大纲相关)
细纲   → prompt_outline.md     (FILE_SECTION: 细纲生成)
概要   → prompt_outline.md     (FILE_SECTION: 概要生成器)
开篇   → prompt_opening.md     (FILE_SECTION: 黄金开篇)
正文   → prompt_writing.md     (FILE_SECTION: 写作要求)
优化   → prompt_polish.md      (FILE_SECTION: 优化建议)
润色   → prompt_polish.md      (FILE_SECTION: 润色)
续写   → prompt_expand.md      (FILE_SECTION: 续写)
扩写   → prompt_expand.md      (FILE_SECTION: 扩写)
```

## 工具映射

| 工具 | 文件 | 说明 |
|------|------|------|
| 指纹蒸馏 | `tools/fusion.py` | 5源文→20维指纹提取→公约数交集分析 |
| 脏逗号清理 | `tools/clean_commas.py` | jieba分词边界+词频校验（防误删） |
| 标点注入 | `tools/inject_punctuation.py` | jieba词边界安全插入（防拆散词组） |
| 独创度审计 | `tools/audit.py` | Bloom 16字反查（朱雀为不可反查的外部对照目标）vs 全部源文 |
| 反模式引擎 | `tools/anti_pattern.py` | 公因子逆转→爽感最大化 |
| 爆款检测 | `check_story.py` | 12项规则+EI爽感指数（体裁感知） |
| Bloom 反查 | `tools/bloom_guard.py` | 零模型 16 字位图索引，全 corpus 反查（朱雀不可反查的外部对照） |
| DNA 蒸馏 | `tools/dna_distiller.py` | 20维叙事DNA 自动蒸馏（保形，落盘 data/_narrative_dna.json） |
| 方法论织入 | `tools/methodology_weaver.py` | 阶段+题材自动织入 prompt/methodology/（--no-methodology/--short-mode） |
| 统一流胶水 | `tools/workflow_hooks.py` | 扫榜/拆书注入 + 可选步骤 argv 拼装 |
| 叙事特征 | `tools/narrative_features.py` | 本地三交叉·叙事层特征提取 |
| 叙事判别 | `tools/local_discriminator.py` | 规则化叙事判别（零重型依赖） |
| 扫榜 | `tools/story_capture.py` | 外部榜单抓取（Node/CDP），写 scan_output/ |
| 拆书 | `tools/story_analyze.py` | 对标拆解骨架生成，写 analysis/{书名}/ |
| 封面生成 | `tools/cover_gen.py` | 封面生成封装（generate-cover.sh + 图像 API） |
| 浏览器操控 | `tools/browser_ctl.py` | Chrome CDP 操控封装（无 LLM） |
