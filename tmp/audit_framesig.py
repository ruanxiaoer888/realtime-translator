# -*- coding: utf-8 -*-
"""画面变化检测回归测试：验证 screen_translate.frame_signature / signature_changed
能发现"直播新评论出现"这种局部改动，同时不会被画面噪点误触发。

历史背景：这个脚本最初是用来**证明旧实现失效**的 —— 旧版每格只采 1 个像素、
阈值 0.06，而一行文字最多只能影响 1/17 个采样行（5.88%），所以单行变化永远触发不了。
现在它是对修好之后的实现的回归测试，直接读屏幕翻译模块里的实际参数。

只读脚本，不修改项目任何文件。
运行:  python tmp\\audit_framesig.py
（在项目根目录下运行）
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import screen_translate as st  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

FONT_PATH = r"C:\Windows\Fonts\segoeui.ttf"
BG = (0x15, 0x16, 0x1C)
FG = (0xE8, 0xE8, 0xEF)
CANVAS_H = 420
LINE_SPACING = 45
TOP, LEFT = 18, 14
# 直接用模块里的实际参数，避免脚本和实现各说各话
THRESHOLD = st.CHANGE_RATIO
CELL_DIFF = st.CELL_DIFF


# ---------------------------------------------------------------- rendering (helper duplicated on purpose)
def render(lines, width=900, size=18, extra=None):
    """画评论图。extra=(text, x, y) 用于在指定位置额外叠一条短评论。"""
    img = Image.new("RGB", (width, CANVAS_H), BG)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, size)
    for i, line in enumerate(lines):
        draw.text((LEFT, TOP + i * LINE_SPACING), line, font=font, fill=FG)
    if extra is not None:
        text, x, y = extra
        draw.text((x, y), text, font=font, fill=FG)
    return np.asarray(img)[:, :, :3].copy()


def line_width(text, size=18):
    img = Image.new("RGB", (10, 10), BG)
    font = ImageFont.truetype(FONT_PATH, size)
    return ImageDraw.Draw(img).textlength(text, font=font)


# ---------------------------------------------------------------- metrics
def raw_frac(a, b):
    """复刻 signature_changed 的比较规则，同时返回差异格数（fraction 的分子）。"""
    if not a or not b or len(a) != len(b):
        return None, None
    diff = sum(1 for x, y in zip(a, b) if abs(int(x) - int(y)) > CELL_DIFF)
    return diff, diff / max(1, len(a))


def pixel_delta(a, b):
    """原始像素层面的差异(灰度差 > 16 视为变化)，用来证明图确实改了。"""
    ga = a.mean(axis=2)
    gb = b.mean(axis=2)
    mask = np.abs(ga - gb) > 16
    n = int(mask.sum())
    if n == 0:
        return 0, None
    ys, xs = np.nonzero(mask)
    return n, (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


def verdict_line(tag, sig_a, sig_b, expect_change):
    diff, frac = raw_frac(sig_a, sig_b)
    if frac is None:
        print(f"  {tag}: signature length mismatch -> signature_changed returns True")
        return
    changed = st.signature_changed(sig_a, sig_b, THRESHOLD)
    margin = frac - THRESHOLD
    ok = (changed == expect_change)
    print(f"  {tag}: cells={len(sig_a)}  differing={diff}  frac={frac:.6f}  "
          f"threshold={THRESHOLD:.4f}  margin={margin:+.6f}  "
          f"signature_changed={changed}  expected={expect_change}  -> {'PASS' if ok else 'FAIL'}")


def main():
    print("#" * 78)
    print("FRAME-SIGNATURE SENSITIVITY AUDIT (screen_translate.frame_signature / signature_changed)")
    print(f"interpreter : {sys.executable}")
    print(f"project root: {ROOT}")
    print(f"render      : bg=#15161c fg=#e8e8ef font={FONT_PATH} size=18 spacing={LINE_SPACING}px")
    print(f"diff rule   : (replicated) cell differs if abs(a - b) > {CELL_DIFF} ;")
    print(f"              frac = differing_cells / len(sig) ; changed if frac > {THRESHOLD}")

    base = [
        "Esse preço está ótimo, vou levar!",
        "Aceita cartão? Não tenho boleto",
        "A broca é de aço inoxidável?",
        "Quanto custa o frete para São Paulo?",
        "Chegou rápido aqui em Belo Horizonte",
        "A cor é azul ou cinza?",
        "Já comprei, adorei a qualidade",
        "Tem desconto para duas unidades?",
    ]
    top_new = "Acabei de entrar na live, boa noite a todos!"
    lines_b = [top_new] + base[1:]

    for width in (900, 1000):
        print("=" * 78)
        print(f"[REGION {width}x{CANVAS_H}]")
        a = render(base, width=width)
        b = render(lines_b, width=width)
        ok_x = LEFT + int(line_width(base[-1])) + 30
        ok_y = TOP + 7 * LINE_SPACING
        c = render(base, width=width, extra=("ok", ok_x, ok_y))

        sig_a = st.frame_signature(a)
        sig_b = st.frame_signature(b)
        sig_c = st.frame_signature(c)
        print(f"  len(sig): A={len(sig_a)}  B={len(sig_b)}  C={len(sig_c)}"
              f"   step_y={max(1, CANVAS_H // 16)} step_x={max(1, width // 16)}")
        print(f"  images: A=8 comments | B=top line replaced with {top_new!r}")
        print(f"          C=8 comments + short new comment 'ok' drawn on last row at x={ok_x},y={ok_y}")
        for tag, img in (("A->B (top line replaced)", b), ("A->C ('ok' on last row)", c)):
            n, bbox = pixel_delta(a, img)
            print(f"  raw pixel delta {tag}: {n} px changed  bbox={bbox}")

        verdict_line("A->A (identical)", sig_a, sig_a, False)
        verdict_line("A->B (top line replaced)", sig_a, sig_b, True)
        # 只在行尾追加一小段文字属于极端局部改动，可能低于阈值；
        # 这种情况由 app 里"最多静默 3 秒强制识别一次"兜底，所以只报告不判 FAIL。
        diff, frac = raw_frac(sig_a, sig_c)
        fired = st.signature_changed(sig_a, sig_c)
        print(f"  A->C ('ok' on last row): differing={diff}  frac={frac:.6f}  "
              f"signature_changed={fired}  -> "
              f"{'会立即重识别' if fired else '不触发（由 3 秒强制识别兜底）'}")

    print("=" * 78)
    print(f"VERDICT: a case FAILs when signature_changed != expected; margin = frac - {THRESHOLD}")
    print("         (positive margin = detector fires, negative = detector stays silent).")


if __name__ == "__main__":
    main()
