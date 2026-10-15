# -*- coding: utf-8 -*-
"""OCR 精度审计：合成葡语/西语直播评论文本图，测真实 OCR 的字错率 (CER)。

只读审计脚本，不修改项目任何文件。
运行:  python tools\\audit_ocr.py
（在项目根目录下运行）
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import screen_translate as st  # noqa: E402  (该模块自己把 libs/ 加进 sys.path)

try:  # 控制台默认 gbk，重配成 utf-8 以便打印重音字符
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

FONT_PATH = r"C:\Windows\Fonts\segoeui.ttf"
BG = (0x15, 0x16, 0x1C)      # #15161c
FG = (0xE8, 0xE8, 0xEF)      # #e8e8ef
CANVAS_W, CANVAS_H = 900, 420
LINE_SPACING = 45
TOP, LEFT = 18, 14

PT_LINES = [
    "Esse preço está ótimo, vou levar!",
    "Aceita cartão? Não tenho boleto",
    "A broca é de aço inoxidável?",
    "Quanto custa o frete para São Paulo?",
    "Chegou rápido aqui em Belo Horizonte",
    "A cor é azul ou cinza?",
    "Já comprei, adorei a qualidade",
    "Tem desconto para duas unidades?",
]

ES_LINES = [
    "¿Cuánto cuesta el envío a Monterrey?",
    "Acepta tarjeta? No tengo efectivo",
    "La broca es de acero inoxidable?",
    "Ya compré, me encantó la calidad",
    "Tiene descuento por dos piezas?",
    "La llave inglesa es de 10 pulgadas?",
    "Llegó rápido a Guadalajara",
    "El color es azul o gris?",
]

ACCENTS = "ãçéíóúñáàêôõü"
PUNCT = "?!,."


# ---------------------------------------------------------------- rendering
def render(lines, size=18):
    """把评论行画成 900x420 的 RGB 数组(与 app UI 深色底 + 近白字一致)。"""
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, size)
    for i, line in enumerate(lines):
        draw.text((LEFT, TOP + i * LINE_SPACING), line, font=font, fill=FG)
    return np.asarray(img)[:, :, :3].copy()


# ---------------------------------------------------------------- metrics
def norm(s: str) -> str:
    """小写 + 折叠空白。保留标点(按题意不允许靠去标点抹平差异)。"""
    return " ".join(s.lower().replace("\n", " ").split())


def alnum_only(s: str) -> str:
    """只留字母/数字/空格(重音字母算字母)。用于附加指标。"""
    return "".join(ch for ch in s if ch.isalnum() or ch == " ")


def edit_ops(ref: str, hyp: str):
    """Levenshtein DP + 回溯，返回 (距离, 操作序列)。操作: = / S / D / I。"""
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        ri = ref[i - 1]
        row, prev = dp[i], dp[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ri == hyp[j - 1] else 1
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost)

    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref[i - 1] == hyp[j - 1] and dp[i][j] == dp[i - 1][j - 1]:
            ops.append(("=", ref[i - 1], hyp[j - 1]))
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            ops.append(("S", ref[i - 1], hyp[j - 1]))
            i -= 1
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("D", ref[i - 1], ""))
            i -= 1
        else:
            ops.append(("I", "", hyp[j - 1]))
            j -= 1
    ops.reverse()
    return dp[n][m], ops


def damage_segments(ops, top=6):
    """把对齐结果切成连续的非匹配段，按影响面排序，取前 top 段。"""
    segs, cur = [], []
    for op in ops:
        if op[0] == "=":
            if cur:
                segs.append(cur)
                cur = []
        else:
            cur.append(op)
    if cur:
        segs.append(cur)

    out = []
    for seg in segs:
        ref_s = "".join(o[1] for o in seg)
        hyp_s = "".join(o[2] for o in seg)
        kinds = {}
        for o in seg:
            kinds[o[0]] = kinds.get(o[0], 0) + 1
        out.append({
            "ref": ref_s,
            "hyp": hyp_s,
            "weight": max(len(ref_s), len(hyp_s)),
            "ops": len(seg),
            "kinds": kinds,
        })
    out.sort(key=lambda s: (s["weight"], s["ops"]), reverse=True)
    return out[:top], len(out)


def count_chars(s, chars):
    return {c: s.count(c) for c in chars if s.count(c)}


def fmt_counts(d):
    return "  ".join(f"{c}={v}" for c, v in d.items()) if d else "(none)"


# ---------------------------------------------------------------- main
def run_case(label, lines, size):
    img = render(lines, size=size)
    ref = norm(" ".join(lines))
    t0 = time.perf_counter()
    items = st.recognize(img)
    dt_ms = (time.perf_counter() - t0) * 1000.0
    merged = st.merge_lines(items)
    hyp = norm(merged)

    lev, ops = edit_ops(ref, hyp)
    cer = lev / max(1, len(ref))
    ref_a, hyp_a = alnum_only(ref), alnum_only(hyp)
    lev_a, _ = edit_ops(ref_a, hyp_a)
    cer_a = lev_a / max(1, len(ref_a))

    print("=" * 78)
    print(f"[CASE] {label}   canvas={CANVAS_W}x{CANVAS_H}  font={FONT_PATH} size={size}  spacing={LINE_SPACING}px")
    print(f"  REF ({len(ref)} chars): {ref}")
    print(f"  HYP ({len(hyp)} chars): {hyp}")
    print(f"  OCR items: {len(items)}  (merge_lines min_score=0.5)")
    for t, s in items:
        print(f"      {s:5.3f}  {t}")
    if not items:
        print("      (no items)")
    print(f"  CER(punct kept)      = {cer:.4f}   lev={lev}  ref_len={len(ref)}  (1.0 = 全错/无输出)")
    print(f"  CER(alnum+space)     = {cer_a:.4f}   lev={lev_a}  ref_len={len(ref_a)}")
    print(f"  accent survival ref->hyp: {fmt_counts(count_chars(ref, ACCENTS))} -> {fmt_counts(count_chars(hyp, ACCENTS))}")
    print(f"  punct  survival ref->hyp: {fmt_counts(count_chars(ref, PUNCT))} -> {fmt_counts(count_chars(hyp, PUNCT))}")
    segs, nsegs = damage_segments(ops, top=6)
    print(f"  TOP DAMAGE (of {nsegs} mismatch segments, ranked by span length):")
    if not segs:
        print("      none - output matches reference exactly")
    for k, sg in enumerate(segs, 1):
        kind = ",".join(f"{v}{kk}" for kk, v in sorted(sg["kinds"].items()))
        print(f"    {k}. ref[{sg['ref']!r}] -> ocr[{sg['hyp']!r}]   span={sg['weight']}  ops={kind}")
    print(f"  recognize() wall time = {dt_ms:.1f} ms")
    return dt_ms


def main():
    print("#" * 78)
    print("OCR ACCURACY AUDIT  (synthetic render -> screen_translate.recognize/merge_lines)")
    print(f"interpreter : {sys.executable}")
    print(f"project root: {ROOT}")
    print(f"PIL {Image.__version__ if hasattr(Image, '__version__') else 'n/a'}  numpy {np.__version__}")
    print(f"canvas      : {CANVAS_W}x{CANVAS_H}  bg=#15161c  fg=#e8e8ef  font={FONT_PATH}  line spacing={LINE_SPACING}px")
    print(f"normalize   : lowercase + collapse whitespace, punctuation PRESERVED")
    print("#" * 78)

    timings = {}
    timings["PT size=18"] = run_case("PT size=18", PT_LINES, 18)
    timings["PT size=14"] = run_case("PT size=14", PT_LINES, 14)
    timings["ES size=18"] = run_case("ES size=18", ES_LINES, 18)
    timings["ES size=14"] = run_case("ES size=14", ES_LINES, 14)

    # 单独再测一次 900x420 的 OCR 耗时(引擎已加载，代表稳定态)
    img = render(PT_LINES, size=18)
    warm = []
    for _ in range(3):
        t0 = time.perf_counter()
        st.recognize(img)
        warm.append((time.perf_counter() - t0) * 1000.0)
    print("=" * 78)
    print("TIMING (900x420, PT size=18)")
    for k, v in timings.items():
        print(f"  {k:12s} first-call {v:8.1f} ms   (含引擎首次加载的用例除外)")
    print(f"  warm passes : {', '.join(f'{w:.1f}' for w in warm)} ms   -> median {sorted(warm)[1]:.1f} ms")
    print("=" * 78)
    print("VERDICT: see CER lines above; 0.0000 = perfect, 1.0000 = no usable output.")


if __name__ == "__main__":
    main()
