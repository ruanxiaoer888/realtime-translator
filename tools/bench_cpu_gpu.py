# -*- coding: utf-8 -*-
"""CPU 与 GPU 识别速度对比：决定公司电脑（GTX 1650）要不要折腾 CUDA 环境。

用真实语音文件测，输出 RTF（实时率）和一句（3 秒音频）的等效耗时。
运行: python tools\bench_cpu_gpu.py
"""
from __future__ import annotations

import os
import sys
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "libs"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

import numpy as np  # noqa: E402


def load_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32") / 32768.0
    return a, sr


def bench(model, audio, lang, label, reps=3):
    from faster_whisper import WhisperModel  # noqa: F401  (类型提示用)
    # 预热
    model.transcribe(audio[:16000 * 2], language=lang, beam_size=1, vad_filter=True)
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        segs, _ = model.transcribe(audio, language=lang, beam_size=1, vad_filter=True,
                                   condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segs).strip()
        ts.append(time.perf_counter() - t0)
    best = min(ts)
    dur = audio.size / 16000
    print(f"  {label:34s} 音频 {dur:5.1f}s  识别 {best:5.2f}s  实时率 {best/dur:6.3f}x  "
          f"≈ 每 3 秒音频 {best/dur*3:5.2f}s")
    print(f"      {text[:88]}")
    return best / dur


def main():
    import ctranslate2
    from faster_whisper import WhisperModel

    print("=" * 78)
    print("CPU vs GPU 识别速度对比")
    print("=" * 78)
    try:
        print(f"  CPU 逻辑核心数: {os.cpu_count()}")
    except Exception:
        pass
    print(f"  ctranslate2 {ctranslate2.__version__}  CUDA 设备数 {ctranslate2.get_cuda_device_count()}")

    wav = os.path.join(ROOT, "tmp", "es_tts_all.wav")
    if not os.path.exists(wav):
        print(f"缺测试音频 {wav}")
        return 1
    audio, sr = load_wav(wav)
    print(f"  测试音频: {os.path.basename(wav)}  {sr} Hz  {audio.size/16000:.1f} 秒\n")

    rows = []
    for size in ("small", "medium"):
        mdir = os.path.join(ROOT, "tmp", "models", f"ct2-{size}")
        if not os.path.exists(os.path.join(mdir, "model.bin")):
            print(f"  [跳过] {size} 模型不存在")
            continue
        print(f"--- {size} ---")
        try:
            gpu = WhisperModel(mdir, device="cuda", compute_type="float16")
            rows.append(("GPU float16", size, bench(gpu, audio, "es", f"{size} / GPU float16 (cuda)")))
            del gpu
        except Exception as e:
            print(f"  [GPU 不可用] {type(e).__name__}: {str(e)[:80]}")
        for threads in (0, 4):
            try:
                cpu = WhisperModel(mdir, device="cpu", compute_type="int8",
                                   cpu_threads=threads or 0)
                label = f"{size} / CPU int8 (线程 {threads or '全部'})"
                rows.append(("CPU int8", size, bench(cpu, audio, "es", label)))
                del cpu
            except Exception as e:
                print(f"  [CPU {threads} 失败] {type(e).__name__}: {str(e)[:80]}")
        print()

    print("=" * 78)
    print("结论（实时率 < 0.2x 就足够直播同传）")
    for kind, size, rtf in rows:
        verdict = "够用" if rtf < 0.2 else ("勉强" if rtf < 0.5 else "偏慢")
        print(f"  {size:7s} {kind:10s} 实时率 {rtf:6.3f}x  -> {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
