# -*- coding: utf-8 -*-
"""屏幕 OCR 冷启动 vs 稳定态 速度基准（900x420 真实屏幕尺寸合成图）。

为什么要有这个脚本：
    只测一次会把「冷启动」当成常态。之前的对比就是冷启动的拉丁模型（含 ~1.3 秒
    模型加载）去比热态的 Windows OCR，得出「快 128 倍」—— 那个数字不成立。
    两个口径必须分开报。

运行（项目根目录）:
    python tools\\bench_ocr_speed.py
"""
from __future__ import annotations

import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "libs"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

import audit_ocr as base  # noqa: E402
import screen_translate as st  # noqa: E402

N = 5
LOCALE = "pt-BR"
IMG = base.render(base.PT_LINES, size=18)
print(f"图像尺寸: {IMG.shape[1]}x{IMG.shape[0]}   重复次数: {N}   语种: {LOCALE}")
print(f"系统 OCR 支持 {LOCALE}: {st.win_ocr_available(LOCALE)}")
st.set_ocr_locale(LOCALE)


def reset_cache():
    """清掉引擎缓存，制造真正的冷启动。"""
    st._ocr_engine = None
    st._ocr_engine_key = None


def bench(pref: str, label: str):
    st.set_ocr_engine(pref)
    reset_cache()
    t0 = time.perf_counter()
    items = st.recognize(IMG)
    cold = time.perf_counter() - t0
    text = st.merge_lines(items)

    warm = []
    for _ in range(N):
        t0 = time.perf_counter()
        st.recognize(IMG)
        warm.append(time.perf_counter() - t0)

    print(f"\n【{label}】")
    print(f"  冷启动（含模型加载）: {cold*1000:8.0f} ms")
    print(f"  稳定态 中位/最小/最大: {statistics.median(warm)*1000:7.0f} / "
          f"{min(warm)*1000:.0f} / {max(warm)*1000:.0f} ms")
    print(f"  识别: {text[:90]}")
    return cold, statistics.median(warm)


c_lat, w_lat = bench("latin", "本地拉丁模型 RapidOCR")
c_win, w_win = bench("win", "Windows 自带 OCR (pt-BR)")

print("\n" + "=" * 70)
print("对比")
print("=" * 70)
print(f"  冷启动: 本地 {c_lat*1000:.0f} ms  vs  系统 {c_win*1000:.0f} ms"
      f"   -> 系统快 {c_lat/c_win:.1f} 倍")
print(f"  稳定态: 本地 {w_lat*1000:.0f} ms  vs  系统 {w_win*1000:.0f} ms"
      f"   -> 系统快 {w_lat/w_win:.1f} 倍")
print()
print("  对直播的实际意义：拉丁模型只有第一次识别慢（付一次加载成本），")
print("  之后每帧是稳定态的数字。")
