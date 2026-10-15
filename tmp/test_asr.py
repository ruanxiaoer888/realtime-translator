# -*- coding: utf-8 -*-
"""验证语音识别 + 翻译链路（用本地 TTS 生成的音频当输入）。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)
os.environ.setdefault("XDG_CACHE_HOME", os.path.join(ROOT, "tmp", "models"))

import whisper  # noqa: E402
import numpy as np  # noqa: E402
from translate_core import translate  # noqa: E402

WAV = os.path.join(ROOT, "tmp", "tts_test.wav")

t0 = time.time()
model = whisper.load_model("small")
print(f"模型加载: {time.time()-t0:.1f}s")

import wave
with wave.open(WAV, "rb") as w:
    sr = w.getframerate()
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
print(f"音频: {audio.size/sr:.2f}s @ {sr}Hz")

for lang in ["en", "pt"]:
    t0 = time.time()
    res = model.transcribe(audio, language=lang, fp16=False, condition_on_previous_text=False)
    dt = time.time() - t0
    txt = res["text"].strip()
    print(f"\n[language={lang}] 耗时 {dt:.2f}s (音频 {audio.size/sr:.1f}s, 实时率 {dt/(audio.size/sr):.2f}x)")
    print("  识别:", txt)
    if txt:
        t1 = time.time()
        zh = translate(txt)
        print(f"  翻译({time.time()-t1:.2f}s):", zh)
