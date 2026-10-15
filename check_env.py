# -*- coding: utf-8 -*-
"""环境自检：确认屏幕翻译 + 直播同传所需的各项能力是否就绪。

用法:
    python check_env.py
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore", message="mss.mss is deprecated")

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "libs"))

RESULTS = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    RESULTS.append((name, ok, detail))
    print(f"[{'OK  ' if ok else 'FAIL'}] {name}: {detail}")


def c_python():
    return True, f"{sys.version.split()[0]} ({sys.executable})"


def c_mss():
    import mss
    with mss.mss() as sct:
        n = len(sct.monitors) - 1
        m = sct.monitors[1] if n else sct.monitors[0]
        return True, f"可捕获 {n} 个屏幕，主屏 {m['width']}x{m['height']}"


def c_ocr_local():
    """用**程序实际使用的**那个 OCR 引擎试识别一次（不要另外 new 一个中文模型）。"""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    import screen_translate as st
    img = Image.new("RGB", (460, 80), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 20)
    except Exception:
        font = None
    d.text((12, 24), "Adicionar nome", fill="black", font=font)
    items = st.recognize(np.asarray(img)[:, :, :3])
    txt = " | ".join(t for t, _ in items) if items else "(空)"
    return True, f"{st.ocr_engine_name()}，试识别: {txt}"


def c_winocr():
    langs = []
    try:
        import winrt.windows.media.ocr as ocr  # noqa
        langs = [l.language_tag for l in ocr.OcrEngine.available_recognizer_languages]
    except Exception:
        # 退回到 PowerShell 探测结果
        return False, "未安装 winrt/winsdk 绑定（不影响本地 OCR 方案）"
    pt = [l for l in langs if l.lower().startswith("pt")]
    return bool(pt), f"系统 OCR 语言: {', '.join(langs)}" + (f"；葡语: {pt}" if pt else "；无葡语包")


def c_audio():
    import soundcard as sc
    mic = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
    return True, f"回环设备: {mic.name}（扬声器: {sc.default_speaker().name}）"


def c_translate():
    from translate_core import translate, channel_status
    out = translate("Ola, bem-vindo a minha loja", "pt-BR", "zh-CN")
    chans = "，".join(f"{k}:{v}" for k, v in channel_status().items())
    return bool(out), f"葡->中: {out!r}  ｜ 通道 {chans}"


def c_asr():
    """检查程序**真正使用**的识别引擎：faster-whisper + CTranslate2。

    早期这里检查的是 openai-whisper + torch，而程序根本不用它们
    （openai-whisper 只是一条不会触发的老回退路径）。
    结果就是在完全正常的机器上也会误报 FAIL，换电脑时尤其误导。
    """
    import asr_engine
    import ctranslate2
    have = [s for s in ("base", "small", "medium", "large-v3") if asr_engine.model_available(s)]
    if not have:
        return False, "没有本地识别模型（运行 python fetch_model.py small）"
    return True, (f"faster-whisper + ctranslate2 {ctranslate2.__version__}"
                  f" ｜ 模型 {', '.join(have)}"
                  f" ｜ CUDA {'可用' if asr_engine.cuda_available() else '不可用，走 CPU（实测够用）'}")


def c_ffmpeg():
    import shutil
    p = shutil.which("ffmpeg")
    return bool(p), p or "PATH 中找不到 ffmpeg"


def main():
    print(f"工作区: {ROOT}\n")
    check("Python 版本", c_python)
    check("屏幕捕获 (mss)", c_mss)
    check("本地 OCR 引擎", c_ocr_local)
    check("系统 OCR (可选)", c_winocr)
    check("系统声音回环", c_audio)
    check("翻译通道", c_translate)
    check("语音识别 (faster-whisper)", c_asr)
    check("ffmpeg", c_ffmpeg)
    bad = [n for n, ok, _ in RESULTS if not ok]
    print("\n结论:", "全部就绪" if not bad else f"{len(bad)} 项未就绪 -> {', '.join(bad)}")


if __name__ == "__main__":
    main()
