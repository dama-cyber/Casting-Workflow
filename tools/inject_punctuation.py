# -*- coding: utf-8 -*-
"""
inject_punctuation.py — 后处理: 按目标密度注入！和逗号

用法:
    python inject_punctuation.py story.txt --excl 0.15 --comma 1.2

LLM输出天然缺！和逗号。此脚本在jieba分词组边界安全插入，不破坏词语完整性。
固定词组(一个/不可/就是/这个/第一等)和jieba高频词组自动跳过，避免误拆。
"""

import sys, re, random, jieba


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


def _jieba_cut_safe(text):
    try:
        return list(jieba.cut(text))
    except Exception:
        return list(text)


def inject_commas(text, target_per_sent):
    """按目标句子密度注入逗号，在jieba词边界插入，不破坏词语完整性"""
    if target_per_sent <= 0:
        return text

    _ATOMIC_PAIRS = frozenset({
        "一个", "这个", "那个", "几个", "上百", "上千", "上万",
        "第一", "第二", "第三", "第四", "第五",
        "不可", "不太", "不是", "就要", "就是",
    })

    punctuation = r"([。！？\n])"
    parts = re.split(punctuation, text)

    total_sent = len([p for p in parts if re.search(r"[\u4e00-\u9fff]", p) and p not in "。！？\n"])
    current_commas = text.count("，")
    target_total = int(total_sent * target_per_sent)
    need = max(0, target_total - current_commas)

    if need <= 0:
        return text

    result_parts = []
    inserted_total = 0

    for idx, part in enumerate(parts):
        if not part or part in "。！？\n" or not re.search(r"[\u4e00-\u9fff]", part):
            result_parts.append(part)
            continue

        zh = count_chinese(part)
        commas_in = part.count("，")
        max_insertable = max(0, zh // 6 - commas_in)
        to_insert = min(max_insertable, need - inserted_total)

        if to_insert <= 0:
            result_parts.append(part)
            continue

        words = _jieba_cut_safe(part)
        span_count = len(words)
        if span_count < 3:
            result_parts.append(part)
            continue

        interval = max(1, span_count // (to_insert + 1))
        new_chars = []
        inserted_here = 0

        for wi, w in enumerate(words):
            new_chars.append(w)
            if inserted_here >= to_insert or wi <= 0 or wi >= span_count - 2:
                continue
            if wi % interval != 0:
                continue
            if w in ("，", "。", "！", "？", "\n"):
                continue
            next_w = words[wi + 1] if wi + 1 < span_count else ""
            if next_w in ("，", "。", "！", "？", "\n"):
                continue
            pair = w + next_w
            if pair in _ATOMIC_PAIRS:
                continue
            try:
                pair_freq = jieba.dt.FREQ.get(pair, -1)
            except Exception:
                pair_freq = -1
            if pair_freq > 500:
                continue
            new_chars.append("，")
            inserted_here += 1
            inserted_total += 1

        result_parts.append("".join(new_chars))

    return "".join(result_parts)


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

    # D2 修复: 已标点文本智能跳过，避免过注入
    cur_excl = exc_before / sn_before if sn_before else 0
    cur_comma = cm_before / sn_before if sn_before else 0
    SKIP_EPS = 0.9
    out_path = output or story
    if sn_before > 0 and cur_excl >= target_excl * SKIP_EPS and cur_comma >= target_comma * SKIP_EPS:
        print(f"标点密度已充足 (!/句 {cur_excl:.2f}≥{target_excl*SKIP_EPS:.2f}, ，/句 {cur_comma:.2f}≥{target_comma*SKIP_EPS:.2f})，跳过注入")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"已保存: {out_path}")
        return

    text = inject_exclamation(text, target_excl)
    text = inject_commas(text, target_comma)

    zh_after = count_chinese(text)
    exc_after = text.count("！")
    cm_after = text.count("，")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"！注入: {exc_before} → {exc_after} (目标 {target_excl:.2f}/句)")
    print(f"，注入: {cm_before} → {cm_after} (目标 {target_comma:.1f}/句)")
    print(f"已保存: {out_path}")


if __name__ == "__main__":
    main()
