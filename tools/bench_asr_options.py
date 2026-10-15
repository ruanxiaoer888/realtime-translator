# -*- coding: utf-8 -*-
"""对同一段真实直播音频，并排比较不同识别设置的准确度。

为什么要这个：识别（ASR）错了，翻译再准也没用 —— 用户反馈"字幕看不懂"，
反查发现根因是识别出来的葡语本身就错了（parafusadeira 被听成 paposeira、
sextavado 听成 sabado、aço inox 听成 azul leite gel）。
光看耗时/字错率说不清哪组设置更好，得把同一段音频过的几组配置并排打出来，
人眼一比就知道。脚本默认把"程序当前用的参数"作为基线，其余每项只改一个变量，
这样结论可以直接搬回 asr_engine.transcribe()。

用法（在项目根目录）:
    python live_caption.py --wav 30          # 先录 30 秒到 tmp\\cap.wav（直播要在放）
    python tools\\bench_asr_options.py       # 再跑对比
    python tools\\bench_asr_options.py 别的录音.wav --models medium
"""
from __future__ import annotations

import os
import sys
import time
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

import asr_engine          # noqa: E402
import markets             # noqa: E402
import translate_core as tc  # noqa: E402

SAMPLE_RATE = 16000
CATEGORY = "五金工具"
MARKET = "巴西"


def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        ch, sw, fr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise SystemExit(f"只支持 16-bit wav，这个是 {sw * 8}-bit")
    a = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if fr != SAMPLE_RATE:
        idx = np.linspace(0, len(a) - 1, int(len(a) * SAMPLE_RATE / fr))
        a = np.interp(idx, np.arange(len(a)), a).astype("float32")
    return a


def vad(min_silence=300, pad=100):
    return {"min_silence_duration_ms": min_silence, "speech_pad_ms": pad}


def run(model, audio, lang: str, **kw):
    t0 = time.perf_counter()
    segs, _ = model.transcribe(
        audio, language=lang, vad_filter=True,
        condition_on_previous_text=False, no_speech_threshold=0.6, **kw)
    text = " ".join(s.text.strip() for s in segs).strip()
    return text, time.perf_counter() - t0


def build_configs(prompt_old: str, prompt_new: str):
    """每组只改一个变量，方便看出是谁起作用。"""
    return [
        ("① 现状：beam1 + pad100 + 旧提示词",
         dict(beam_size=1, initial_prompt=prompt_old, vad_parameters=vad(300, 100))),
        ("② 只换提示词（按品类）",
         dict(beam_size=1, initial_prompt=prompt_new, vad_parameters=vad(300, 100))),
        ("③ 只补语音留白 pad100->400",
         dict(beam_size=1, initial_prompt=prompt_old, vad_parameters=vad(300, 400))),
        ("④ 只换 beam1->5",
         dict(beam_size=5, initial_prompt=prompt_old, vad_parameters=vad(300, 100))),
        ("⑤ 留白+beam5（不改提示词）",
         dict(beam_size=5, initial_prompt=prompt_old, vad_parameters=vad(300, 400))),
        ("⑥ 全开：新提示词+beam5+pad400",
         dict(beam_size=5, initial_prompt=prompt_new, vad_parameters=vad(300, 400))),
    ]


def main():
    args = list(sys.argv[1:])
    models = ["medium"]
    if "--models" in args:
        i = args.index("--models")
        models = args[i + 1].split(",")
        del args[i:i + 2]
    wav = args[0] if args else os.path.join(ROOT, "tmp", "cap.wav")
    if not os.path.exists(wav):
        raise SystemExit(f"找不到音频 {wav}\n先录一段：python live_caption.py --wav 30")

    audio = read_wav(wav)
    dur = len(audio) / SAMPLE_RATE
    peak = float(np.abs(audio).max())
    rms = float(np.sqrt((audio ** 2).mean()))
    print("=" * 78)
    print(f"音频: {wav}")
    print(f"时长 {dur:.1f}s ｜ 峰值 {peak:.3f} ｜ RMS {rms:.4f}")
    if peak < 0.005:
        print("⚠ 这段音频几乎全是静音 —— 直播没在放？换个时间再录。")
        return 1
    print("=" * 78)

    m = markets.get_market(MARKET)
    lang = m["whisper"]
    prompt_old = m["asr_prompt"]
    prompt_new = markets.get_asr_prompt(CATEGORY, lang)
    print(f"旧提示词 {len(prompt_old)} 字符（四个品类混合）")
    print(f"新提示词 {len(prompt_new)} 字符（只当前品类 + 直播通用词）")
    tc.set_engine("api")

    summary = []
    for size in models:
        try:
            model = asr_engine.get_model(size)
        except Exception as e:
            print(f"\n[{size}] 模型加载失败: {e}")
            continue
        for label, kw in build_configs(prompt_old, prompt_new):
            try:
                text, dt = run(model, audio, lang, **kw)
            except Exception as e:
                print(f"\n[{size} {label}] 出错: {e}")
                continue
            zh = tc.translate(text, m["locale"], "zh-CN") if text else None
            summary.append((size, label, text, zh or "", dt))
            print(f"\n{'─' * 78}")
            print(f"[{size}] {label}   耗时 {dt:.2f}s（{dt / dur:.3f}x 实时）")
            print(f"  葡语: {text if text else '（空）'}")
            print(f"  中文: {zh if zh else '（无）'}")

    print("\n" + "=" * 78)
    print("汇总（重点看：专有名词有没有听对；中文读不读得通）")
    print("=" * 78)
    for size, label, text, zh, dt in summary:
        print(f"\n● [{size}] {label}   {dt:.2f}s")
        print(f"  葡: {text[:130] if text else '（空）'}")
        print(f"  中: {zh[:130]}")
    print("\n对照要点：")
    print("  · parafusadeira / furadeira / broca / soquete / sextavado 有没有听对")
    print("  · 有没有凭空多出主播没说的词（提示词过长会带偏解码）")
    print("  · 句首有没有被削掉（pad 太小会丢词头，如 parafusadeira -> usadeira）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
