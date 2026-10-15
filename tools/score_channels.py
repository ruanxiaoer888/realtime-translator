# -*- coding: utf-8 -*-
"""客观评分：术语命中率 + 延迟 + 可靠性，横向对比三通道（带真实术语表）。

评分口径：对每句原文抽出命中的术语（先长后短，去重叠），
        再看 apply_glossary 后的最终译文里出现了多少个对应的中文说法。
"""
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import asr_engine
import markets
import translate_core as tc

gl = markets.get_glossary("五金工具", "pt")
asr_engine.set_terminology(prompt=markets.get_asr_prompt("五金工具", "pt"), glossary=gl)

SENTS = [
    "Olá, hoje eu trouxe uma parafusadeira e uma furadeira.",
    "Vem com chave de fenda, chave philips e um jogo de chaves.",
    "O kit tem jogo de soquetes, soquete e alicate.",
    "Também tem martelo, trena e 6 brocas.",
    "Tem esmerilhadeira, serra circular e kit de ferramentas na maleta.",
    "A bateria e o carregador são de 48 volts.",
    "Vem com 8 chaves sextavados, philips e fenda.",
    "O martelete com ponteira e o adaptador estão inclusos.",
    "Tem parafuso, porca e arruela.",
    "A chave inglesa, o nível e o estilete completam o kit.",
    "Tem lixadeira e serra tico-tico para madeira.",
    "É bivolt, então a voltagem 110 e 220 funciona.",
    "Serve para espelho, quadro e móveis.",
    "É fácil de montar e desmontar.",
]


def terms_in(s):
    """抽出一句里命中的术语，先长后短去重叠。"""
    low = s.lower()
    keys = sorted([k for k in gl if k.lower() in low], key=len, reverse=True)
    picked, spans = [], []
    for k in keys:
        idx = low.find(k.lower())
        while idx != -1:
            if all(idx + len(k) <= a or idx >= b for a, b in spans):
                spans.append((idx, idx + len(k)))
                picked.append(k)
                break
            idx = low.find(k.lower(), idx + 1)
    return picked


CHANS = [("有道", tc._youdao), ("腾讯", tc._tencent), ("MyMemory", tc._mymemory)]

stats = {n: {"hit": 0, "tot": 0, "ms": [], "fail": 0} for n, _ in CHANS}
rows = []

for s in SENTS:
    ts = terms_in(s)
    exp = [(t, gl[t]) for t in ts]
    rec = {"src": s, "exp": exp, "out": {}}
    for name, fn in CHANS:
        t0 = time.time()
        try:
            raw = fn(s, "pt", "zh-CN")
        except Exception:
            raw = None
        ms = (time.time() - t0) * 1000
        if not raw:
            stats[name]["fail"] += 1
            rec["out"][name] = (None, ms, 0, len(exp))
        else:
            final = tc.apply_glossary(s, raw) or ""
            hit = sum(1 for _, v in exp if v in final)
            stats[name]["hit"] += hit
            stats[name]["tot"] += len(exp)
            stats[name]["ms"].append(ms)
            rec["out"][name] = (final, ms, hit, len(exp))
        time.sleep(0.7)
    rows.append(rec)

print("=" * 104)
print("逐句明细（评分 = 命中术语数 / 该句术语数）")
print("=" * 104)
for r in rows:
    print(f"\n【原文】{r['src']}")
    print(f"  期望术语: " + ("; ".join(f"{k}={v}" for k, v in r["exp"]) or "（无）"))
    for name, _ in CHANS:
        final, ms, hit, tot = r["out"][name]
        if final is None:
            print(f"  {name:<9} [失败] {ms:6.0f}ms  0/{tot}")
        else:
            print(f"  {name:<9} {hit}/{tot}  {ms:6.0f}ms  {final}")

print()
print("=" * 104)
print("汇总")
print("=" * 104)
print(f"{'通道':<10}{'术语命中率':>14}{'中位延迟':>12}{'失败次数':>12}")
for name, _ in CHANS:
    st = stats[name]
    rate = f"{st['hit']}/{st['tot']}" + (f" = {st['hit']/st['tot']*100:.0f}%" if st["tot"] else "")
    med = f"{sorted(st['ms'])[len(st['ms'])//2]:.0f} ms" if st["ms"] else "—"
    print(f"{name:<10}{rate:>14}{med:>12}{st['fail']:>9}/{len(SENTS)}")
