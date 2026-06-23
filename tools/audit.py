"""
audit.py — 熔铸输出审计

用法:
    python audit.py story.txt [source1.txt source2.txt ...]

检查:
    - 禁用模式/模板
    - 标点禁令
    - 独创度(16字扫描 vs N篇源文)
"""

import sys, re


def count_chinese(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def audit_story(text):
    results = []
    zh = count_chinese(text)
    sentences = [s for s in re.split(r"[。！？]", text) if re.search(r"[\u4e00-\u9fff]", s)]
    n = len(sentences)

    results.append(f"字数: {zh}  句数: {n}")
    results.append(f"！/句: {text.count('！')/n:.3f}  ，/句: {text.count('，')/n:.2f}")

    # 禁令
    issues = []
    if text.count("；") > 0:
        issues.append(f"分号 {text.count('；')}个")
    if text.count("！！！") > 0:
        issues.append(f"！！！ {text.count('！！！')}个")
    if text.count("？！") > 0:
        issues.append(f"？！ {text.count('？！')}个")
    if len(re.findall(r"[「」]", text)) > 0:
        issues.append("日式引号")

    # 禁用模式
    banned = ["对X而言", "一切都在", "一种说不出的", "的意义在于"]
    for b in banned:
        if b in text:
            issues.append(f"禁用句式: {b}")

    templates = ["眼中闪过", "嘴角勾起", "眼眶微红", "不可置信", "眼底闪过", "咬了咬唇"]
    for t in templates:
        if t in text:
            issues.append(f"禁用模板: {t}")

    if issues:
        results.append(f"\n问题 ({len(issues)}):")
        for iss in issues:
            results.append(f"  [FAIL] {iss}")
    else:
        results.append("\n固定规则: 全部通过 [OK]")

    return "\n".join(results)


def check_originality(story_text, source_paths):
    lines = []
    story_clean = re.sub(r"[，。！？：；、\s\d]", "", story_text)

    for sp in source_paths:
        with open(sp, "r", encoding="utf-8", errors="replace") as f:
            src = f.read()
        src_clean = re.sub(r"[，。！？：；、\s\d]", "", src)
        matches = 0
        for i in range(0, len(src_clean) - 16, 5):  # 抽样扫描
            if story_clean.find(src_clean[i:i+16]) >= 0:
                matches += 1
        name = sp.split("\\")[-1][:30]
        status = "OK" if matches == 0 else f"FAIL {matches}"
        lines.append(f"  {name}: {status}")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("用法: python audit.py story.txt [source1.txt source2.txt ...]")
        sys.exit(1)

    story_path = sys.argv[1]
    source_paths = sys.argv[2:]

    with open(story_path, "r", encoding="utf-8") as f:
        text = f.read()

    result = audit_story(text) + "\n"

    if source_paths:
        result += f"\n独创度 (vs {len(source_paths)}篇源文):\n"
        result += check_originality(text, source_paths) + "\n"

    out_path = story_path.replace(".txt", "_audit.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"审计完成 -> {out_path}")


if __name__ == "__main__":
    main()
