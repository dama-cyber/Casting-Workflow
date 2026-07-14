# -*- coding: utf-8 -*-
"""
clean_commas.py — jieba分词边界感知逗号清理

用法:
    python clean_commas.py story.txt

原理:
    对每个逗号，取左右各1个中文字符。
    检查这对字符在jieba中是否为有效词(词频50-500，非罕见词非超高频词)
    跳过结构助词边界(的/了/着/过/得/地)和分句起始字(风/雪/云等)
    仅在确认逗号切断了有效词时才删除，避免误删语义逗号。

依赖: pip install jieba
"""

import sys, re
import warnings
warnings.filterwarnings("ignore", message=".*pkg_resources.*")
import jieba


def count_chinese(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def clean_commas(text):
    chars = list(text)
    removed = 0
    i = 0

    _STRUCTURAL = frozenset("的了着过得地不也都就才还又再很太")
    _CLAUSE_START = frozenset("风雪花月日山水风雨云雷我你他她这那有在看")

    while i < len(chars):
        if chars[i] != "，":
            i += 1
            continue

        left = chars[i - 1] if i > 0 else ""
        right = chars[i + 1] if i + 1 < len(chars) else ""

        if not re.match(r"[\u4e00-\u9fff]", left) or not re.match(r"[\u4e00-\u9fff]", right):
            i += 1
            continue

        if left in _STRUCTURAL or right in _STRUCTURAL:
            i += 1
            continue

        pair = left + right
        try:
            freq = jieba.dt.FREQ.get(pair, -1)
        except Exception:
            freq = -1

        if freq < 0 or freq > 500:
            i += 1
            continue

        words = list(jieba.cut(pair))
        if len(words) == 1 and len(words[0]) == 2:
            if right in _CLAUSE_START:
                i += 1
                continue
            del chars[i]
            removed += 1
            continue

        i += 1

    result = "".join(chars)
    print(f"已删除 {removed} 个脏逗号")
    return result


def main():
    if len(sys.argv) < 2:
        print("用法: python clean_commas.py story.txt [output.txt]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else input_path

    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()

    zh = count_chinese(text)
    print(f"输入: {zh} 汉字")

    cleaned = clean_commas(text)
    print(f"输出: {count_chinese(cleaned)} 汉字 (不变)")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cleaned)

    print(f"已保存: {output_path}")


if __name__ == "__main__":
    main()
