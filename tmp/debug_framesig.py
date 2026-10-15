# -*- coding: utf-8 -*-
"""调试：看画面变化时每格灰度均值到底差多少，用来定 CELL_DIFF 和阈值。"""
from __future__ import annotations
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import screen_translate as st
import audit_ocr as base

FONT = r"C:\Windows\Fonts\segoeui.ttf"
BG, FG = (0x15, 0x16, 0x1C), (0xE8, 0xE8, 0xEF)


def render(lines, width=1000, size=18, extra=None):
    img = Image.new("RGB", (width, 420), BG)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, size)
    for i, line in enumerate(lines):
        d.text((14, 18 + i * 45), line, font=f, fill=FG)
    if extra:
        d.text((extra[1], extra[2]), extra[0], font=f, fill=FG)
    return np.asarray(img)[:, :, :3].copy()


base_lines = base.PT_LINES
a = render(base_lines)
cases = {
    "顶行整条换新": render(["Acabei de entrar na live, boa noite a todos!"] + base_lines[1:]),
    "中间换一行": render(["Vou levar dois, tem desconto?"] + base_lines[1:-1]),
    "末行追加 ok": render(base_lines, extra=("ok", 700, 18 + 7 * 45)),
    "整屏滚动": render(["NOVO"] + base_lines[:-1]),
}
rng = np.random.default_rng(0)
cases["±3 灰度噪点"] = np.clip(a.astype(np.int16) + rng.integers(-3, 4, a.shape), 0, 255).astype(np.uint8)
cases["完全相同"] = a.copy()

sa = np.array(st.frame_signature(a), dtype=np.int32)
print(f"指纹: {len(sa)} 格  网格 {st.GRID_ROWS}x{st.GRID_COLS}")
print(f"{'用例':<14} {'最大差':>7} {'>0':>6} {'>1':>6} {'>2':>6} {'>3':>6} {'>4':>6} {'>6':>6} {'>10':>6}")
for name, img in cases.items():
    sb = np.array(st.frame_signature(img), dtype=np.int32)
    d = np.abs(sa - sb)
    row = [int((d > t).sum()) for t in (0, 1, 2, 3, 4, 6, 10)]
    print(f"{name:<14} {int(d.max()):>7} " + " ".join(f"{v:>6}" for v in row))
print(f"总格数 {len(sa)}，1% = {len(sa)*0.01:.1f} 格，0.5% = {len(sa)*0.005:.1f} 格")
