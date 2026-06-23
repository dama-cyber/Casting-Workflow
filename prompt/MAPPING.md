# prompt 文件映射表

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

## pipeline 映射

```
脑洞 → prompt_inspiration.md (FILE_SECTION: 脑洞生成器)
灵感风暴 → prompt_inspiration.md (FILE_SECTION: 灵感风暴)
人设 → prompt_character.md   (FILE_SECTION: 人设生成器)
大纲 → prompt_outline.md     (FILE_SECTION: 大纲相关)
细纲 → prompt_outline.md     (FILE_SECTION: 细纲生成)
概要 → prompt_outline.md     (FILE_SECTION: 概要生成器)
开篇 → prompt_opening.md     (FILE_SECTION: 黄金开篇)
正文 → prompt_writing.md     (FILE_SECTION: 写作要求)
优化 → prompt_polish.md      (FILE_SECTION: 优化建议)
润色 → prompt_polish.md      (FILE_SECTION: 润色)
续写 → prompt_expand.md      (FILE_SECTION: 续写)
扩写 → prompt_expand.md      (FILE_SECTION: 扩写)
```
