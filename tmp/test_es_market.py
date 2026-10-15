# -*- coding: utf-8 -*-
"""下载 MMS-TTS 西语模型，生成西语语音，验证西语市场的识别是否准确。"""
import os
import ssl
import sys
import time
import urllib.request
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "tmp", "models"))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

REPO = "facebook/mms-tts-spa"
DEST = os.path.join(ROOT, "tmp", "models", "mms-tts-spa")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0"}


def fetch(name):
    dest = os.path.join(DEST, name)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    for host in ("https://huggingface.co", "https://hf-mirror.com"):
        try:
            url = f"{host}/{REPO}/resolve/main/{name}"
            req = urllib.request.Request(url, headers=UA)
            data = urllib.request.urlopen(req, context=CTX, timeout=300).read()
            if data:
                with open(dest, "wb") as f:
                    f.write(data)
                print(f"    下载 {name}: {len(data)/1024:.0f} KB")
                return True
        except Exception as e:
            print(f"    {name} 从 {host.split('//')[1]} 失败: {str(e)[:60]}")
    return False


os.makedirs(DEST, exist_ok=True)
print("=== 下载西语 TTS 模型 ===")
for f in ("config.json", "model.safetensors", "vocab.json", "tokenizer_config.json"):
    fetch(f)

print("\n=== 生成西语语音 ===")
from transformers import VitsModel, AutoTokenizer  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402

try:
    tts = VitsModel.from_pretrained(DEST)
    tok = AutoTokenizer.from_pretrained(DEST)
except Exception as e:
    print("模型加载失败:", e)
    sys.exit(1)

TEXTS = [
    "Hoy traje un taladro muy potente con caja de herramientas completa.",
    "Esta amoladora profesional y el juego de dados son de alta calidad.",
    "El precio exclusivo es solo durante la transmisión en vivo, aprovechen.",
]
sr = tts.config.sampling_rate
wavs = []
for i, t in enumerate(TEXTS, 1):
    ids = tok(t, return_tensors="pt")
    with torch.no_grad():
        wave_out = tts(**ids).waveform.squeeze().numpy().astype("float32")
    wavs.append(wave_out)
    path = os.path.join(ROOT, "tmp", f"es_tts_{i}.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(wave_out, -1, 1) * 32767).astype("<i2").tobytes())
    print(f"  [{i}] {len(wave_out)/sr:.2f}s  {t}")

allv = np.concatenate(wavs)
path = os.path.join(ROOT, "tmp", "es_tts_all.wav")
with wave.open(path, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes((np.clip(allv, -1, 1) * 32767).astype("<i2").tobytes())
print(f"  合并 {len(allv)/sr:.2f}s -> es_tts_all.wav")

print("\n=== 用西语参数识别（墨西哥市场的配置）===")
import asr_engine  # noqa: E402
import markets  # noqa: E402

# 重采样到 16k
n = int(len(allv) * 16000 / sr)
a16 = np.interp(np.linspace(0, len(allv) - 1, n), np.arange(len(allv)), allv).astype("float32")

for market_name in ("墨西哥", "巴西"):
    m = markets.get_market(market_name)
    g = markets.get_glossary("五金工具", m["whisper"])
    asr_engine.set_terminology(prompt=m["asr_prompt"], glossary=g)
    t0 = time.time()
    text, dt = asr_engine.transcribe(a16, language=m["whisper"], size="small")
    print(f"\n[{market_name}] language={m['whisper']}  {dt:.2f}s")
    print(f"  -> {text}")

print("\n=== 原文对照 ===")
for t in TEXTS:
    print(f"  {t}")
