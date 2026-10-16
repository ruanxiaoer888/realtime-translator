# -*- coding: utf-8 -*-
"""GPU vs CPU 真实速度对比 —— 用来决定这台机器该用哪种计算精度。

**注意：必须关掉 vad_filter。** 用噪声/静音测 ASR 时 VAD 会把音频整段滤掉，
编码根本不发生，测出来是 0.01 秒的假数据（本项目踩过两次）。

用法（项目根目录）:
    py -3.12 tools/dsh_bench.py                 # small/medium × cpu/cuda
    py -3.12 tools/dsh_bench.py --size small    # 只测 small
    py -3.12 tools/dsh_bench.py --secs 6,25

判断标准：看 **实时率**（耗时 ÷ 音频长度），不是看单句耗时。
    < 0.5 很宽裕 | 0.5~0.8 勉强 | > 1.0 追不上主播说话
参考（2026-10 实测）：
    GTX 1650（无张量核心）int8_float16 比 float16 快 3 倍
    RTX 3060 Ti（有张量核心）建议两种都测一下再定
"""
from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
import time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)


def vram() -> str:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                              "--format=csv,noheader"], capture_output=True, text=True, timeout=15)
        return out.stdout.strip() or "?"
    except Exception:
        return "(nvidia-smi 不可用)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", default="6,25")
    ap.add_argument("--size", default="small,medium")
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()

    import asr_engine          # noqa: E402  （自动注册 libs/ 与 CUDA dll 目录）
    import numpy as np         # noqa: E402  （必须在 asr_engine 之后）

    secs = [float(x) for x in args.secs.split(",")]
    sizes = [s.strip() for s in args.size.split(",")]
    combos = [("cpu", "int8")] + ([("cuda", "int8_float16"), ("cuda", "float16")]
                                  if asr_engine.cuda_available() else [])
    print("CUDA 可用: %s   VRAM: %s" % (asr_engine.cuda_available(), vram()))
    print("（vad_filter 已关闭，音频为噪声，只测算力不比准确度）\n")

    results = []
    rng = np.random.default_rng(1)
    for size in sizes:
        for dev, ct in combos:
            importlib.reload(asr_engine)
            try:
                t0 = time.time()
                m = asr_engine.get_model(size, device=dev, compute_type=ct)
                load = time.time() - t0
            except Exception as e:
                print("  %-5s %-13s %-7s 加载失败: %s" % (dev, ct, size, str(e)[:90]))
                continue
            row = ["%-5s %-13s %-7s 加载%5.2fs  6s音频" % (dev, ct, size, load)]
            for sec in secs:
                a = (rng.standard_normal(int(16000 * sec)) * 0.03).astype(np.float32)

                def run():
                    seg, _ = m.transcribe(a, language="pt", beam_size=1, vad_filter=False,
                                          condition_on_previous_text=False)
                    return " ".join(s.text.strip() for s in seg).strip()

                try:
                    run()
                    best = None
                    for _ in range(args.rounds):
                        t = time.time()
                        run()
                        dt = time.time() - t
                        best = dt if best is None else min(best, dt)
                    row.append("%.0fs->%6.3fs(RTF %.2f)" % (sec, best, best / sec))
                    results.append((size, dev, ct, sec, best))
                except Exception as e:
                    row.append("%.0fs->失败 %s" % (sec, str(e)[:40]))
            print("  " + "  ".join(row))

    if results:
        print("\n=== 实时率排序（越低越好）===")
        for size, dev, ct, sec, dt in sorted(results, key=lambda r: r[4] / r[3])[:6]:
            print("  %-7s %-5s %-13s %.2f" % (size, dev, ct, dt / sec))
    print("\nVRAM 最终: %s" % vram())
    return 0


if __name__ == "__main__":
    sys.exit(main())
