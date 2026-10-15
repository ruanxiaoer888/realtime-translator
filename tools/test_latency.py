# -*- coding: utf-8 -*-
"""端到端延迟测试：播放音频 -> 回环录音 -> 新管线（VAD切句+CT2+翻译）出字幕。
记录 每句字幕出来的时间、识别耗时、翻译耗时、以及相对音频结束的延迟。
"""
import os
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "tmp", "models"))

import ctypes  # noqa: E402
import numpy as np  # noqa: E402
import soundcard as sc  # noqa: E402
import asr_engine  # noqa: E402
import translate_core as tc  # noqa: E402
from translate_core import translate  # noqa: E402

if len(sys.argv) > 2:
    tc.set_engine(sys.argv[2])
tc.clear_cache()

FFPLAY = shutil.which("ffplay") or "ffplay"
WAV = os.path.join(ROOT, "tmp", "speech16k.wav")
SIZE = sys.argv[1] if len(sys.argv) > 1 else "small"

speaker = sc.default_speaker()
mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
chunks = []
lock = threading.Lock()


def rec(stop_evt):
    ctypes.windll.ole32.CoInitializeEx(None, 0)
    with mic.recorder(samplerate=16000, channels=2, blocksize=1600) as r:
        while not stop_evt.is_set():
            d = r.record(numframes=1600)
            with lock:
                chunks.append(d.mean(axis=1).astype("float32"))


print(f"引擎: faster-whisper({SIZE})")
print(f"回环设备: {mic.name}")
print(f"模型就绪: {asr_engine.model_available(SIZE)}")
asr_engine.get_model(SIZE)

stop = threading.Event()
t = threading.Thread(target=rec, args=(stop,))
t.start()
time.sleep(0.5)

play_start = time.time()
proc = subprocess.Popen([FFPLAY, "-nodisp", "-autoexit", "-loglevel", "quiet", WAV],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
proc.wait(timeout=20)
play_end = time.time()

seg = asr_engine.StreamingSegmenter(max_seconds=7.0, min_seconds=1.5,
                                    silence_seconds=0.35, overlap_seconds=0.25)
events = []
dropped = 0
deadline = time.time() + 12
while time.time() < deadline:
    time.sleep(0.1)
    with lock:
        data = np.concatenate(chunks) if chunks else np.zeros(0, dtype="float32")
        chunks.clear()
    if data.size == 0:
        continue
    piece = seg.push(data)
    if piece is None:
        continue
    if seg.speech_level(piece) < seg.silence_rms:
        dropped += 1
        continue
    piece = seg.trim(piece)
    now = time.time()
    pt, asr_dt = asr_engine.transcribe(piece, language="en", size=SIZE)
    t1 = time.time()
    zh = translate(pt)
    tr_dt = time.time() - t1
    events.append((now, pt, zh, asr_dt, tr_dt, piece.size / 16000))
    print(f"\n[{now-play_start:6.2f}s 相对开播] 音频{piece.size/16000:.1f}s "
          f"识别{asr_dt:.2f}s 翻译{tr_dt:.2f}s")
    print(f"    葡/英原文: {pt}")
    print(f"    中文     : {zh}")

print(f"\n自动校准的静音阈值: {seg.silence_rms:.4f}（丢弃静音段 {dropped} 个）")

stop.set()
t.join(timeout=5)

print("\n" + "=" * 60)
if events:
    print(f"音频播放结束于 {play_end-play_start:.2f}s")
    for now, pt, zh, a, tr, dur in events:
        print(f"  字幕出现在 {now-play_start:.2f}s ｜ 音频段{dur:.1f}s ｜ "
              f"处理={a+tr:.2f}s ｜ 相对音频结束 {now-play_end:+.2f}s")
    worst = max(a + tr for _, _, _, a, tr, _ in events)
    print(f"单句处理耗时上限: {worst:.2f}s （这是感知延迟的主要部分）")
else:
    print("没有产生字幕")
