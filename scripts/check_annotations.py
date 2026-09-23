#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文注释校验器（source-code-blog skill）

扫描 markdown 文档中的源码展示块（``` 围栏），校验是否携带【讲解】教学注释。
作为 skill 中“中文注释校验”硬性门槛的落地工具：机器可复现、只读不写。

判定规则（任一条满足即视为“该块已注释”）：
  1. 块内（围栏之间）存在含 【讲解】 的行；   ← 首选：块内就近注释
  2. 块闭合后 N 行内（允许空行）存在含 【讲解】 的行； ← 块后紧跟的注释段落

说明：
- 第 1 种是 skill 规范首选（annotated-source.md：局部说明在块内紧贴语句）。
- 第 2 种兼容“先把代码原样展示、再在块后用【讲解】段落逐句解释”的写法；
  校验器会标记为 adjacent，便于后续统一为块内注释。
- 两者皆无为“未注释”，判不通过。
- 纯示意 / 图类围栏（mermaid / plantuml / dot / ascii 等）跳过。

用法：
    python3 check_annotations.py <文件或目录> [<文件或目录> ...]
退出码：0 = 全部源码块均已注释；1 = 存在未注释块；2 = 用法错误。

注意：机械计数只报告“注释是否存在与分布”，不能替代对
“注释是否解释了真实因果”的语义判断（见 teaching-review.md）。
"""
import sys
import re
from pathlib import Path

ANNOTATION_MARK = "【讲解】"
FENCE_RE = re.compile(r"^(```+|~~~+)(.*)$")
ADJACENT_LOOKAHEAD = 3  # 块闭合后最多看这么多行（含空行）

SOURCE_LANGS = {
    "", "text", "c", "cpp", "cc", "cxx", "h", "hpp", "c++", "h++",
    "java", "kt", "kotlin", "go", "rs", "rust", "py", "python", "js",
    "ts", "javascript", "typescript", "sh", "bash", "zsh", "shell",
    "swift", "dart", "sql", "proto", "gradle", "xml", "yaml", "json",
    "make", "cmake", "dockerfile", "objective-c", "objc",
}
SKIP_LANGS = {"mermaid", "plantuml", "dot", "ascii", "text-ascii", "svg", "uml"}

# 片段头标记：按 skill 约定，源码片段前用 ```text 块写“源码：… 所处步骤：…”，
# 这类块是位置/步骤说明，不是待注释的代码，排除出校验。
LOCATION_HEADER_RE = re.compile(r"^\s*源码[:：]")


def scan_file(path: Path):
    """返回该文件所有围栏块的信息列表。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    results = []
    in_block = False
    lang = ""
    start = 0
    inline_annot = 0
    is_header = False
    for i, line in enumerate(lines, start=1):
        m = FENCE_RE.match(line)
        if not in_block:
            if m:
                in_block = True
                lang = m.group(2).strip().lower()
                start = i
                inline_annot = 0
                is_header = False
        else:
            if m:  # 闭合围栏
                in_block = False
                # 片段头标记块（源码：… 所处步骤：…）排除出校验
                if lang == "text" and is_header:
                    lang = ""
                    continue
                is_source = lang in SOURCE_LANGS and lang not in SKIP_LANGS
                # 向后看 ADJACENT_LOOKAHEAD 行，找块后紧跟的【讲解】
                adjacent = 0
                for j in range(i + 1, min(i + 1 + ADJACENT_LOOKAHEAD, len(lines)) + 1):
                    if j - 1 >= len(lines):
                        break
                    ln = lines[j - 1]
                    if ANNOTATION_MARK in ln:
                        adjacent += 1
                    if ln.strip() == "":
                        continue
                    # 遇到非空且非【讲解】的行，停止向后看
                    if ANNOTATION_MARK not in ln:
                        break
                results.append({
                    "start": start,
                    "end": i,
                    "lang": lang,
                    "inline": inline_annot,
                    "adjacent": adjacent,
                    "is_source": is_source,
                })
                lang = ""
            else:
                if ANNOTATION_MARK in line:
                    inline_annot += 1
                # 首行命中“源码：”即判定为片段头标记块
                if not is_header and LOCATION_HEADER_RE.match(line):
                    is_header = True
    return results


def report(path: Path):
    results = scan_file(path)
    source_blocks = [r for r in results if r["is_source"]]
    print(f"\n=== {path} ===")
    print(f"源码展示块：{len(source_blocks)}")
    missing = []
    for r in source_blocks:
        annotated = r["inline"] > 0 or r["adjacent"] > 0
        if not annotated:
            missing.append(r)
            print(f"  [缺失] 行 {r['start']}-{r['end']}  lang={r['lang']!r}")
        else:
            tag = "inline" if r["inline"] > 0 else "adjacent"
            print(f"  [ok:{tag}] 行 {r['start']}-{r['end']}  lang={r['lang']!r}"
                  f"  块内={r['inline']} 块后={r['adjacent']}")
    return missing


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    files = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.md")))
        elif p.exists():
            files.append(p)
        else:
            print(f"跳过不存在的路径：{arg}", file=sys.stderr)

    total_source = 0
    total_missing = 0
    total_adjacent = 0
    print("--- 逐文件校验 ---")
    for f in files:
        res = scan_file(f)
        sb = [r for r in res if r["is_source"]]
        miss = [r for r in sb if r["inline"] == 0 and r["adjacent"] == 0]
        adj = [r for r in sb if r["inline"] == 0 and r["adjacent"] > 0]
        total_source += len(sb)
        total_missing += len(miss)
        total_adjacent += len(adj)
        status = "OK" if not miss else f"缺失 {len(miss)}"
        print(f"{f}: 源码块 {len(sb)} / {status}"
              + (f" (其中 {len(adj)} 个仅块后注释)" if adj else ""))

    print("\n--- 汇总 ---")
    print(f"源码展示块总计 {total_source}")
    print(f"  含块内注释      : {total_source - total_adjacent - total_missing}")
    print(f"  仅块后相邻注释  : {total_adjacent}  (建议统一为块内)")
    print(f"  完全缺注释      : {total_missing}")
    if total_missing > 0:
        print("校验未通过：存在无任何中文教学注释的源码展示块，需返修。")
        sys.exit(1)
    print("校验通过：所有源码展示块均含【讲解】注释。")


if __name__ == "__main__":
    main()
