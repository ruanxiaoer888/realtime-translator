# -*- coding: utf-8 -*-
"""静态检查 translate_core.py 的 TERM_FIXES：语法、重复键、危险错译串。

危险错译串 = 某个"正确译文"的子串，会让 apply_glossary 把该正确译文移出保护集。
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

p = Path(__file__).resolve().parent.parent / "translate_core.py"
src = p.read_text(encoding="utf-8")
tree = ast.parse(src)

fixes = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "TERM_FIXES":
        fixes = ast.literal_eval(node.value)

if fixes is None:
    print("FAIL 找不到 TERM_FIXES")
    sys.exit(1)

keys = list(fixes)
dupes = sorted({k for k in keys if keys.count(k) > 1})
print(f"语法        : OK")
print(f"TERM_FIXES  : {len(keys)} 条")
print(f"重复键      : {dupes if dupes else '无'}")

import markets  # noqa: E402

values = set()
for cat in markets.CATEGORIES:
    for lang in ("pt", "es", "en"):
        try:
            values.update(markets.get_glossary(cat, lang).values())
        except Exception:
            pass
print(f"全部正确译文: {len(values)} 个")

bad = []
for term, groups in fixes.items():
    for grp in groups:
        for w in grp:
            for v in values:
                if v != w and v in w:
                    bad.append((term, w, v))
print(f"危险错译串  : {len(bad)} 处")
for term, w, v in bad:
    print(f"    {term}: 错译 '{w}' 含有正确译文 '{v}' -> 会把 '{v}' 移出保护集")

if dupes:
    print("FAIL 有重复键（后者会静默覆盖前者）")
    sys.exit(1)
print("结果: OK")
