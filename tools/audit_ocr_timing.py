# -*- coding: utf-8 -*-
"""同一进程内交替测量：中文 rec 模型 vs 拉丁 rec 模型 的单帧耗时（排除 CPU 争用干扰）。"""
from __future__ import annotations

import os
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
from rapidocr_onnxruntime import RapidOCR  # noqa: E402

LATIN = os.path.join(ROOT, "tmp", "models", "ocr-latin")


def bench(engine, img, n=5):
    engine(img)  # 预热
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        engine(img)
        ts.append((time.perf_counter() - t0) * 1000)
    return ts


def main():
    img = base.render(base.PT_LINES, size=18)
    ch = RapidOCR()
    latin = RapidOCR(rec_model_path=os.path.join(LATIN, "rec.onnx"),
                     rec_keys_path=os.path.join(LATIN, "dict.txt"))

    # 交替跑两轮，消除先后顺序带来的偏差
    for rnd in (1, 2):
        a = bench(ch, img, 5)
        b = bench(latin, img, 5)
        print(f"[轮次 {rnd}]")
        print(f"  中文 ch_PP-OCRv4 : {', '.join(f'{x:.0f}' for x in a)} ms   median {sorted(a)[2]:.0f} ms")
        print(f"  拉丁 latin rec   : {', '.join(f'{x:.0f}' for x in b)} ms   median {sorted(b)[2]:.0f} ms")

    ta = bench(ch, img, 7)
    tb = bench(latin, img, 7)
    print("\n[合计 7 次]")
    print(f"  中文 median {sorted(ta)[3]:.0f} ms   mean {sum(ta)/len(ta):.0f} ms")
    print(f"  拉丁 median {sorted(tb)[3]:.0f} ms   mean {sum(tb)/len(tb):.0f} ms")
    print(f"  差值 median {sorted(tb)[3]-sorted(ta)[3]:+.0f} ms   mean {sum(tb)/len(tb)-sum(ta)/len(ta):+.0f} ms")

    # 两种模型在同一张图上的识别结果对比（取第一行）
    print("\n[同一张图 第一行识别对比]")
    for name, eng in (("中文", ch), ("拉丁", latin)):
        res, _ = eng(img)
        print(f"  {name}: {res[0][1] if res else '(空)'}")


if __name__ == "__main__":
    main()
