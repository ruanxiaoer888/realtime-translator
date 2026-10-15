# -*- coding: utf-8 -*-
"""验证识别端的语言切换：同一段英语音频，用不同语言参数识别，看结果是否跟着变。"""
import os
import sys
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "tmp", "models"))

import numpy as np  # noqa: E402
import markets  # noqa: E402
import asr_engine  # noqa: E402

WAV = os.path.join(ROOT, "tmp", "speech16k.wav")
if not os.path.exists(WAV):
    print("缺少测试音频 tmp/speech16k.wav")
    sys.exit(1)
with wave.open(WAV, "rb") as w:
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32") / 32768.0
print(f"测试音频: {len(audio)/16000:.2f}s（英语人声）\n")

# 每个市场用自己的语言 + 自己的提示词识别同一段音频
for market_name in ("巴西", "墨西哥", "美国" if False else "美区"):
    m = markets.get_market(market_name)
    glossary = markets.get_glossary("五金工具", m["whisper"])
    asr_engine.set_terminology(prompt=m["asr_prompt"], glossary=glossary)
    t0 = time.time()
    text, dt = asr_engine.transcribe(audio, language=m["whisper"], size="small")
    print(f"[{market_name}] language={m['whisper']}  识别 {dt:.2f}s")
    print(f"    -> {text!r}")

# 对比：自动检测
asr_engine.set_terminology(prompt="", glossary={})
text, dt = asr_engine.transcribe(audio, language="", size="small")
print(f"\n[不指定语言] 识别 {dt:.2f}s\n    -> {text!r}")

print("\n说明：音频是英语，所以 language=en 时才该出正确英文；")
print("      language=pt/es 会得到音近的乱码——这正是切换语言必须生效的证据。")
