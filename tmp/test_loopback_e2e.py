# -*- coding: utf-8 -*-
"""严格测试：一边播放音频，一边用回环采集，验证直播同传的输入链路。"""
import os
import shutil
import subprocess
import sys
import threading
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)
os.environ.setdefault("XDG_CACHE_HOME", os.path.join(ROOT, "tmp", "models"))

import ctypes  # noqa: E402
import numpy as np  # noqa: E402
import soundcard as sc  # noqa: E402

FFPLAY = shutil.which("ffplay") or "ffplay"
WAV = os.path.join(ROOT, "tmp", "speech16k.wav")
speaker = sc.default_speaker()
mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
print("回环设备:", mic.name)

chunks = []
errors = []


def rec(seconds):
    ctypes.windll.ole32.CoInitializeEx(None, 0)
    try:
        with mic.recorder(samplerate=16000, channels=2, blocksize=1600) as r:
            end = time.time() + seconds
            while time.time() < end:
                d = r.record(numframes=1600)
                chunks.append(d.mean(axis=1).astype("float32"))
    except Exception as e:
        errors.append(repr(e))


t = threading.Thread(target=rec, args=(8,))
t.start()
time.sleep(1.0)  # 先开始录音，再播放
proc = subprocess.Popen([FFPLAY, "-nodisp", "-autoexit", "-loglevel", "quiet", WAV],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
proc.wait(timeout=15)
t.join(timeout=10)

buf = np.concatenate(chunks) if chunks else np.zeros(0, dtype="float32")
print(f"录制总长 {buf.size/16000:.2f}s  峰值 {abs(buf).max() if buf.size else 0:.4f}  "
      f"RMS {np.sqrt(np.mean(buf**2)) if buf.size else 0:.4f}  errors={errors}")

if buf.size:
    with wave.open(os.path.join(ROOT, "tmp", "loopback_cap.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(buf, -1, 1) * 32767).astype("<i2").tobytes())
    print("已保存 tmp/loopback_cap.wav")

    import whisper
    model = whisper.load_model("small")
    t0 = time.time()
    res = model.transcribe(buf, language="en", fp16=False, condition_on_previous_text=False)
    dt = time.time() - t0
    txt = res["text"].strip()
    print(f"\n对录到的声音做识别（{dt:.2f}s）: {txt!r}")
    if txt:
        from translate_core import translate
        print("中文翻译:", translate(txt))
        print(">>> 直播同传全链路（系统声音 -> 识别 -> 翻译）: 通过")
    else:
        print(">>> 录到的声音不含可识别语音")
