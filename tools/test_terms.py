# -*- coding: utf-8 -*-
"""术语准确率实测：NLLB 600M 对五金工具术语的表现。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "tmp", "models"))

import nllb_translate as n  # noqa: E402

n._load()  # 预热，避免首次推理的几秒开销混进来

CASES = [
    ("parafusadeira", "Hoje eu trouxe uma parafusadeira muito potente."),
    ("furadeira", "Essa furadeira é profissional, tem muita força."),
    ("chave de fenda", "Olha essa chave de fenda de aço inoxidável."),
    ("jogo de soquetes", "O jogo de soquetes vem com 40 peças."),
    ("alicate", "Esse alicate é muito resistente."),
    ("martelo", "O martelo tem cabo de borracha."),
    ("maleta", "Vem com maleta completa para guardar tudo."),
    ("bateria", "A bateria tem 12 volts e dura o dia todo."),
    ("carrinho amarelo", "Cliquem no carrinho amarelo para comprar."),
    ("frete grátis", "Frete grátis para todo o Brasil."),
]
EXPECT = {
    "parafusadeira": ["螺丝刀", "起子"],
    "furadeira": ["电钻", "钻"],
    "chave de fenda": ["螺丝刀", "起子"],
    "jogo de soquetes": ["套筒", "套装"],
    "alicate": ["钳"],
    "martelo": ["锤"],
    "maleta": ["工具箱", "箱"],
    "bateria": ["电池"],
    "carrinho amarelo": ["购物车"],
    "frete grátis": ["免运费", "包邮"],
}

print(f"{'术语':16s} {'译文':34s} 判定  耗时")
print("-" * 78)
ok = 0
total = 0.0
for term, sent in CASES:
    t0 = time.time()
    zh = n.translate(sent) or ""
    dt = time.time() - t0
    total += dt
    good = any(h in zh for h in EXPECT[term])
    ok += 1 if good else 0
    print(f"{term:16s} {zh[:34]:34s} {'✓' if good else '✗'}    {dt:.2f}s")

print("-" * 78)
print(f"术语命中 {ok}/{len(CASES)}，平均 {total/len(CASES):.2f}s/句")
print()
print("说明：译文已过术语强修正表；判定看是否出现标准中文说法。")
