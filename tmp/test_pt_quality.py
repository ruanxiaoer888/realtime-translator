# -*- coding: utf-8 -*-
"""用 MMS-TTS 巴西葡语模型生成语音，再交给 faster-whisper 识别，测真实葡语识别质量。"""
import os
import sys
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "tmp", "models"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np  # noqa: E402

TEXTS = [
    "Ola pessoal, bem-vindos a minha live. Hoje eu trouxe uma parafusadeira muito potente.",
    "Essa furadeira vem com maleta completa, bateria de doze volts e carregador rapido.",
    "O preco esta exclusivo na transmissao, aproveitem e cliquem no carrinho amarelo.",
]

print("=" * 74)
print("1. 加载 MMS-TTS 巴西葡语模型")
print("=" * 74)
t0 = time.time()
from transformers import VitsModel, AutoTokenizer  # noqa: E402

model_dir = os.path.join(ROOT, "tmp", "models", "mms-tts-por")
tts = VitsModel.from_pretrained(model_dir)
tok = AutoTokenizer.from_pretrained(model_dir)
print(f"   加载完成 {time.time()-t0:.1f}s，采样率 {tts.config.sampling_rate}")

print()
print("=" * 74)
print("2. 生成葡语语音并保存")
print("=" * 74)
sr_out = tts.config.sampling_rate
wavs = []
for i, text in enumerate(TEXTS, 1):
    t0 = time.time()
    inputs = tok(text, return_tensors="pt")
    with __import__("torch").no_grad():
        out = tts(**inputs).waveform
    audio = out.squeeze().numpy().astype("float32")
    wavs.append(audio)
    path = os.path.join(ROOT, "tmp", f"pt_tts_{i}.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr_out)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    print(f"   [{i}] {len(audio)/sr_out:.2f}s  生成 {time.time()-t0:.1f}s  -> {os.path.basename(path)}")
    print(f"       原文: {text}")

# 拼成一段连续语音，模拟直播
allv = np.concatenate(wavs)
path = os.path.join(ROOT, "tmp", "pt_tts_all.wav")
with wave.open(path, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr_out)
    w.writeframes((np.clip(allv, -1, 1) * 32767).astype("<i2").tobytes())
print(f"   合并音频 {len(allv)/sr_out:.2f}s -> pt_tts_all.wav")

print()
print("=" * 74)
print("3. 重采样到 16k，交给 faster-whisper 识别")
print("=" * 74)
import asr_engine  # noqa: E402


def resample(a, sr, target=16000):
    if sr == target:
        return a
    n = int(len(a) * target / sr)
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype("float32")


a16 = resample(allv, sr_out)
print(f"   音频 {len(a16)/16000:.2f}s @16k")

for size in [s for s in ("small", "medium") if asr_engine.model_available(s)]:
    t0 = time.time()
    text, dt = asr_engine.transcribe(a16, language="pt", size=size)
    print(f"\n   [{size}] 识别 {dt:.2f}s（实时率 {dt/(len(a16)/16000):.3f}x）")
    print(f"   识别结果: {text}")
    if text:
        from translate_core import translate
        t1 = time.time()
        print(f"   中文翻译({time.time()-t1:.2f}s): {translate(text)}")

print()
print("=" * 74)
print("4. 对照原文（人工比对用）")
print("=" * 74)
for i, t in enumerate(TEXTS, 1):
    print(f"   [{i}] {t}")
