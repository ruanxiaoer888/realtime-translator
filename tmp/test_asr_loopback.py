# -*- coding: utf-8 -*-
"""1) 验证 whisper 识别真有语音的音频；2) 验证系统声音回环采集能录到播放的声音。"""
import os
import shutil
import subprocess
import sys
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)
os.environ.setdefault("XDG_CACHE_HOME", os.path.join(ROOT, "tmp", "models"))

import numpy as np  # noqa: E402

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPLAY = shutil.which("ffplay") or "ffplay"
WAV = os.path.join(ROOT, "tmp", "speech16k.wav")


def read_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32") / 32768.0
    return a, sr


print("=" * 60)
print("测试1: whisper 识别真实语音")
print("=" * 60)
audio, sr = read_wav(WAV)
print(f"音频时长 {len(audio)/sr:.2f}s @ {sr}Hz，峰值 {abs(audio).max():.3f}")

import whisper  # noqa: E402

t0 = time.time()
model = whisper.load_model("small")
print(f"模型加载 {time.time()-t0:.1f}s")
t0 = time.time()
res = model.transcribe(audio, language="en", fp16=False, condition_on_previous_text=False)
dt = time.time() - t0
print(f"识别耗时 {dt:.2f}s (实时率 {dt/(len(audio)/sr):.3f}x)")
print("识别结果:", repr(res["text"].strip()))
if res["text"].strip():
    from translate_core import translate
    print("中文翻译:", translate(res["text"].strip()))
    print(">>> 语音识别+翻译链路: 通过")
else:
    print(">>> 未识别出文字（样本可能不是语音）")

print()
print("=" * 60)
print("测试2: 系统声音回环采集（播放声音同时录音）")
print("=" * 60)
import soundcard as sc  # noqa: E402

speaker = sc.default_speaker()
print("默认扬声器:", speaker.name)
mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
print("回环录音设备:", mic.name)

proc = subprocess.Popen([FFPLAY, "-nodisp", "-autoexit", "-loglevel", "quiet", WAV])
chunks = []


def rec():
    with mic.recorder(samplerate=16000, channels=2, blocksize=1600) as r:
        end = time.time() + 5
        while time.time() < end:
            data = r.record(numframes=1600)
            mono = data.mean(axis=1) if data.ndim > 1 else data
            chunks.append(mono.astype("float32"))


import threading  # noqa: E402

t = threading.Thread(target=rec)
t.start()
t.join()
proc.wait(timeout=10)
buf = np.concatenate(chunks) if chunks else np.zeros(0, dtype="float32")
peak = float(np.abs(buf).max()) if buf.size else 0.0
rms = float(np.sqrt(np.mean(np.square(buf)))) if buf.size else 0.0
print(f"录到 {buf.size/16000:.1f}s 音频，峰值 {peak:.4f}，RMS {rms:.4f}")
if peak > 0.01:
    print(">>> 回环采集: 通过（能录到扬声器播放的声音）")
    with wave.open(os.path.join(ROOT, "tmp", "loopback_cap.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(buf, -1, 1) * 32767).astype("<i2").tobytes())
else:
    print(">>> 回环采集: 失败或当前无声音输出（峰值过低）")
