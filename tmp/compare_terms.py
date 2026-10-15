# -*- coding: utf-8 -*-
"""术语对比：在线免费接口 vs NLLB 600M（同样 10 个五金术语）。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "tmp", "models"))

import translate_core as tc  # noqa: E402

CASES = [
    ("parafusadeira", "Hoje eu trouxe uma parafusadeira muito potente.", ["螺丝刀", "起子"]),
    ("furadeira", "Essa furadeira é profissional, tem muita força.", ["电钻", "钻"]),
    ("chave de fenda", "Olha essa chave de fenda de aço inoxidável.", ["螺丝刀", "起子"]),
    ("jogo de soquetes", "O jogo de soquetes vem com 40 peças.", ["套筒", "套装"]),
    ("alicate", "Esse alicate é muito resistente.", ["钳"]),
    ("martelo", "O martelo tem cabo de borracha.", ["锤"]),
    ("maleta", "Vem com maleta completa para guardar tudo.", ["工具箱", "箱"]),
    ("bateria", "A bateria tem 12 volts e dura o dia todo.", ["电池"]),
    ("carrinho amarelo", "Cliquem no carrinho amarelo para comprar.", ["购物车"]),
    ("frete grátis", "Frete grátis para todo o Brasil.", ["免运费", "包邮"]),
]

for mode, label in (("api", "在线免费接口"), ("nllb", "NLLB 600M")):
    tc.set_engine(mode)
    tc.clear_cache()
    print(f"\n{'='*76}\n{label}\n{'='*76}")
    ok = 0
    total = 0.0
    for term, sent, hints in CASES:
        t0 = time.time()
        zh = tc.translate(sent) or ""
        dt = time.time() - t0
        total += dt
        good = any(h in zh for h in hints)
        ok += 1 if good else 0
        print(f"  {term:16s} {zh[:32]:32s} {'✓' if good else '✗'}  {dt:.2f}s")
    print(f"  --- 命中 {ok}/{len(CASES)}，平均 {total/len(CASES):.2f}s/句")
