"""Structure-only length profile of the published English story table.

Authorised counts only (protocol rule: no feature on the story texts before IPA):
texts, pages per text, whitespace-delimited tokens and characters per page and per text.
No sentence splitting, no tokenisation beyond str.split(), no story text printed.

Pages are recovered exactly as extract_story_texts.split_lines() does: the first line of
`text` is the title, each further line is a page, and the two characters backslash-n
inside a line are a line break within the page. The title is excluded from every count,
as the extraction's `words` column excludes it.

Per-text characters are counted on the registered page join (pages joined with one
U+0020), so they equal sum(page chars) + pages - 1: the string every model would see
before NFC and format-character deletion.

Usage: python -I -X utf8 length_profile.py <stories.csv.xz> <out_dir>
"""
import csv
import json
import lzma
import os
import statistics
import sys
from collections import Counter, defaultdict

csv.field_size_limit(2**31 - 1)
LINE_BREAK = "\\n"
QS = [0, 1, 5, 25, 50, 75, 95, 99, 100]


def split_lines(text):
    body = text.replace("\r\n", "\n")
    if body.endswith("\n"):
        body = body[:-1]
    lines = [line.replace(LINE_BREAK, "\n") for line in body.split("\n")]
    return lines[0], lines[1:]


def pct(values, q):
    """Type-7 (linear interpolation) percentile, as numpy's default."""
    v = sorted(values)
    if not v:
        return None
    if q <= 0:
        return v[0]
    if q >= 100:
        return v[-1]
    h = (len(v) - 1) * q / 100
    lo = int(h)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (h - lo) * (v[hi] - v[lo])


def summ(values):
    if not values:
        return {"n": 0}
    out = {"n": len(values), "mean": round(statistics.fmean(values), 2), "sum": sum(values)}
    for q in QS:
        x = pct(values, q)
        out[f"p{q}"] = round(x, 1) if isinstance(x, float) else x
    return out


def main():
    src, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    groups = defaultdict(lambda: defaultdict(list))
    meta_distinct = defaultdict(set)
    age_counts, prompt_counts = Counter(), Counter()
    words_mismatch = pages_mismatch = 0
    per_text_rows = []
    with lzma.open(src, "rt", encoding="utf-8", newline="") as f:
        rows = csv.DictReader(f)
        header = rows.fieldnames
        for r in rows:
            title, pages = split_lines(r["text"])
            classic = r["hero"] == "Public domain"
            kind = "classic" if classic else "generated"
            level = r["age"] or "(blank)"
            age_counts[(kind, level)] += 1
            prompt_counts[r["prompt"]] += 1
            for k in ("hero", "world", "theme", "prompt", "sidekick", "age", "lang"):
                meta_distinct[k].add(r[k])
            ptok = [len(p.split()) for p in pages]
            pchar = [len(p) for p in pages]
            n_pages = len(pages)
            t_tok = sum(ptok)
            t_char = sum(pchar) + max(0, n_pages - 1)
            if str(t_tok) != r["words"]:
                words_mismatch += 1
            if str(n_pages) != r["pages"]:
                pages_mismatch += 1
            for g in ("all", kind, f"{kind}|{level}", f"level|{level}"):
                d = groups[g]
                d["pages_per_text"].append(n_pages)
                d["tokens_per_text"].append(t_tok)
                d["chars_per_text"].append(t_char)
                d["tokens_per_page"].extend(ptok)
                d["chars_per_page"].extend(pchar)
                d["empty_pages"].append(sum(1 for x in ptok if x == 0))
            per_text_rows.append((r["id"], kind, level, n_pages, t_tok, t_char,
                                  " ".join(map(str, ptok)), " ".join(map(str, pchar))))
    res = {
        "source": os.path.basename(os.path.dirname(src)) + "/" + os.path.basename(src),
        "header": header,
        "n_texts": len(per_text_rows),
        "distinct_values_per_metadata_column": {k: len(v) for k, v in meta_distinct.items()},
        "texts_by_kind_and_level": {f"{k}|{lv}": n for (k, lv), n in sorted(age_counts.items())},
        "n_prompt_types": len(prompt_counts),
        "check_words_column_equals_whitespace_tokens": {"mismatches": words_mismatch},
        "check_pages_column_equals_lines_after_title": {"mismatches": pages_mismatch},
        "groups": {g: {k: (summ(v) if k != "empty_pages" else {"texts_with_empty_page": sum(1 for x in v if x),
                                                                  "empty_pages": sum(v)})
                       for k, v in d.items()} for g, d in groups.items()},
    }
    with open(os.path.join(out_dir, "en_length_profile.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    with open(os.path.join(out_dir, "en_per_text_structure.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("id\tkind\tlevel\tpages\ttokens\tchars_joined\ttokens_per_page\tchars_per_page\n")
        for row in per_text_rows:
            f.write("\t".join(map(str, row)) + "\n")
    print(json.dumps({k: res[k] for k in ("source", "header", "n_texts", "distinct_values_per_metadata_column",
                                           "texts_by_kind_and_level", "n_prompt_types",
                                           "check_words_column_equals_whitespace_tokens",
                                           "check_pages_column_equals_lines_after_title")}, indent=1))


if __name__ == "__main__":
    main()
