"""
inject_punctuation.py — 后处理: 按目标密度注入！和逗号

用法:
    python inject_punctuation.py story.txt --excl 0.15 --comma 1.2

LLM输出天然缺！和逗号。此脚本机械补偿。
"""

import sys, re, random


def count_chinese(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def inject_exclamation(text, target_per_sent):
    """每N个。替换为！直到密度达标"""
    sentences = re.split(r"([。！？])", text)
    result_parts = []
    excl_count = text.count("！")
    period_count = text.count("。")

    if target_per_sent <= 0:
        return text

    # 计算需要多少！
    total_sent = len([s for s in re.split(r"[。！？]", text) if re.search(r"[\u4e00-\u9fff]", s)])
    target_total = int(total_sent * target_per_sent)
    need = max(0, target_total - excl_count)

    if need <= 0 or period_count == 0:
        return text

    # 每隔 period_count/need 个。替换一个
    interval = max(1, period_count // need)
    count = 0
    replaced = 0

    new_text = list(text)
    for i in range(len(new_text)):
        if new_text[i] == "。":
            count += 1
            if count % interval == 0 and replaced < need:
                # 检查不是数字或英文后面的句号
                if i > 0 and new_text[i - 1] not in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ":
                    new_text[i] = "！"
                    replaced += 1

    return "".join(new_text)


def inject_commas(text, target_per_sent):
    """对12字以上零逗号的句子插入逗号"""
    sentences = re.split(r"(?<=[。！？])", text)
    result = []

    for sent in sentences:
        zh = count_chinese(sent)
        commas = sent.count("，")
        if zh >= 12 and commas == 0 and zh <= 30:
            # 在中间位置插入一个逗号
            chars = list(sent)
            zh_pos = 0
            target = zh // 2
            inserted = False
            for i, ch in enumerate(chars):
                if re.match(r"[\u4e00-\u9fff]", ch):
                    zh_pos += 1
                    if zh_pos == target and i + 1 < len(chars):
                        chars.insert(i + 1, "，")
                        inserted = True
                        break
            sent = "".join(chars)
        result.append(sent)

    return "".join(result)


def main():
    if len(sys.argv) < 2:
        print("用法: python inject_punctuation.py story.txt [--excl 0.15] [--comma 1.2] [-o output.txt]")
        sys.exit(1)

    text = ""
    target_excl = 0.15
    target_comma = 1.2
    output = None
    story = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--excl" and i + 1 < len(args):
            target_excl = float(args[i + 1]); i += 2
        elif a == "--comma" and i + 1 < len(args):
            target_comma = float(args[i + 1]); i += 2
        elif a == "-o" and i + 1 < len(args):
            output = args[i + 1]; i += 2
        elif not a.startswith("-") and story is None:
            story = a; i += 1
        else:
            i += 1

    if not story:
        print("错误: 未指定输入文件")
        sys.exit(1)

    with open(story, "r", encoding="utf-8") as f:
        text = f.read()

    zh_before = count_chinese(text)
    sn_before = len([s for s in re.split(r"[。！？]", text) if re.search(r"[\u4e00-\u9fff]", s)])
    exc_before = text.count("！")
    cm_before = text.count("，")

    text = inject_exclamation(text, target_excl)
    text = inject_commas(text, target_comma)

    zh_after = count_chinese(text)
    exc_after = text.count("！")
    cm_after = text.count("，")

    out_path = output or story
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"！注入: {exc_before} → {exc_after} (目标 {target_excl:.2f}/句)")
    print(f"，注入: {cm_before} → {cm_after} (目标 {target_comma:.1f}/句)")
    print(f"已保存: {out_path}")


if __name__ == "__main__":
    main()
