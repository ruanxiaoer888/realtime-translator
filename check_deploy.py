# -*- coding: utf-8 -*-
"""换电脑部署自检：把整个文件夹拷到新电脑后，先跑这个。

检查：Python 版本、libs/ 依赖是否齐全、模型文件、算力（GPU/CPU）、
      屏幕捕获、系统声音回环、翻译通道、OCR 引擎。

用法（在新电脑的本目录下打开 PowerShell）:
    python check_deploy.py
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
# 顺序不能反：先加 libs，再导入第三方包
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RESULTS: list[tuple[str, bool, str]] = []
FIXES: list[str] = []


def check(name, fn, fix=""):
    t0 = time.time()
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {str(e)[:120]}"
    dt = time.time() - t0
    RESULTS.append((name, ok, detail))
    flag = "OK  " if ok else "FAIL"
    print(f"[{flag}] {name}: {detail}" + (f"   ({dt:.1f}s)" if dt > 1 else ""))
    if not ok and fix:
        FIXES.append(fix)


# ---------------------------------------------------------------- checks
def c_python():
    v = sys.version_info
    ok = v[:2] == (3, 12) and sys.maxsize > 2**32
    return ok, f"{sys.version.split()[0]}  {'64位' if sys.maxsize > 2**32 else '32位!'}  ({sys.executable})"


def c_libs():
    """libs/ 是否齐全 —— 换电脑最容易缺的就是这个。"""
    import importlib
    need = ["numpy", "cffi", "requests", "ctranslate2", "faster_whisper",
            "onnxruntime", "rapidocr_onnxruntime", "soundcard", "mss", "yaml"]
    missing = []
    for m in need:
        try:
            importlib.import_module(m)
        except Exception:
            missing.append(m)
    if missing:
        return False, f"缺 {len(missing)} 个: {', '.join(missing)}"
    where = "libs/" if os.path.join(ROOT, "libs") in os.path.dirname(
        sys.modules["numpy"].__file__ or "") else "系统 Python"
    return True, f"{len(need)} 个核心依赖齐全（numpy 来自 {where}）"


def c_msvc_runtime():
    """Windows 的 VC++ 运行库（msvcp140/vcruntime140）。

    换到全新电脑最容易漏的一环：ctranslate2 / onnxruntime 都是 MSVC 编译的，
    系统里没有这个运行库时，Python 能起来、numpy 也能用（numpy 自带一份），
    但 ctranslate2/onnxruntime 会报 DLL load failed，看起来像"依赖没拷全"。
    """
    import glob
    sysdir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    need = ["msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"]
    missing = [n for n in need if not os.path.exists(os.path.join(sysdir, n))]
    if missing:
        return False, "缺 " + ", ".join(missing)
    return True, "msvcp140 / vcruntime140 都在"


def c_models():
    import asr_engine
    import nllb_translate
    have = [s for s in ("base", "small", "medium", "large-v3") if asr_engine.model_available(s)]
    nllb = nllb_translate.available()
    parts = [f"识别模型: {', '.join(have) if have else '无'}"]
    parts.append(f"NLLB离线翻译: {'有' if nllb else '无'}")
    return bool(have), " ｜ ".join(parts)


def c_ocr():
    import screen_translate as st
    st.get_ocr()
    return True, st.ocr_engine_name()


def c_compute():
    """算力：GPU 还是 CPU，实测一句的耗时。

    注意会真跑一次编码：有的机器有 N 卡驱动、ctranslate2 也报告有 CUDA 设备，
    但缺 cublas/cudnn，只有真编码那一刻才暴露。asr_engine 会当场验明并退到 CPU，
    这里把退的原因也显示出来，免得用户以为是"程序坏了"。
    """
    import asr_engine
    if not asr_engine.model_available("small"):
        return False, "没有 small 模型，无法测"
    t0 = time.time()
    asr_engine.get_model("small")
    load = time.time() - t0
    info = asr_engine.device_info()
    import numpy as np
    audio = (np.random.default_rng(0).standard_normal(16000 * 3) * 0.02).astype(np.float32)
    asr_engine.transcribe(audio, language="pt", size="small")          # 预热
    t0 = time.time()
    asr_engine.transcribe(audio, language="pt", size="small")
    dt = time.time() - t0
    cuda = asr_engine.cuda_available()
    note = ""
    reason = asr_engine.cuda_failed_reason() if hasattr(asr_engine, "cuda_failed_reason") else ""
    if reason:
        reason = reason.replace("GPU 试跑失败，已降级 CPU：", "")
        note = f"  ⚠ 检测到 N 卡但 CUDA 跑不起来，已自动改用 CPU（{reason[:60]}）"
    return True, (f"{info.get('device')}/{info.get('compute_type')}（CUDA可用={cuda}）"
                  f"  加载 {load:.1f}s  3秒音频 {dt:.2f}s{note}")


def c_screen():
    import mss
    with mss.mss() as sct:
        n = len(sct.monitors) - 1
        m = sct.monitors[1] if n else sct.monitors[0]
        return True, f"{n} 个屏幕，主屏 {m['width']}x{m['height']}"


def c_audio():
    import soundcard as sc
    spk = sc.default_speaker()
    mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
    return True, f"回环设备 {mic.name}（扬声器 {spk.name}）"


def c_audio_live():
    """真录 2 秒，确认回环真的能收到声音（不只是设备存在）。"""
    import live_caption as lc
    audio, dev = lc.record_seconds(2.0)
    rms = lc.rms(audio)
    return True, f"录到 {audio.size/16000:.1f} 秒，音量 RMS {rms:.4f}" + \
                 ("（安静，正常：现在没在放声音）" if rms < 0.001 else "（有声音）")


def c_translate():
    from translate_core import translate
    t0 = time.time()
    out = translate("Ola, bem-vindo a minha loja", "pt-BR", "zh-CN")
    return bool(out), f"葡->中 {time.time()-t0:.2f}s: {out!r}"


def c_logdir():
    d = os.path.join(ROOT, "记录")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, ".writetest")
    with open(p, "w", encoding="utf-8") as f:
        f.write("ok")
    os.remove(p)
    return True, f"可写: {d}"


def main():
    print("=" * 78)
    print("部署自检（换电脑后在新机器上跑这个）")
    print(f"目录: {ROOT}")
    print("=" * 78)

    check("Python 版本", c_python,
          "装 64 位 Python 3.12：https://www.python.org/downloads/release/python-3129/")
    check("VC++ 运行库", c_msvc_runtime,
          "装微软官方运行库（否则 ctranslate2/onnxruntime 会 DLL load failed）："
          "https://aka.ms/vs/17/release/vc_redist.x64.exe")
    check("libs 依赖完整性", c_libs, "在本目录运行: python fetch_wheels.py --core")
    check("模型文件", c_models, "运行: python fetch_model.py small  和  python fetch_ocr_model.py")
    check("OCR 引擎", c_ocr, "运行: python fetch_ocr_model.py")
    check("算力（识别速度）", c_compute)
    check("屏幕捕获", c_screen)
    check("系统声音回环", c_audio)
    check("回环实际录音", c_audio_live)
    check("翻译通道（要联网）", c_translate, "检查网络/代理；离线可用 NLLB 兜底")
    check("记录目录可写", c_logdir)

    bad = [n for n, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 78)
    if not bad:
        print("结论: 全部就绪 —— 双击 启动翻译助手.bat 即可")
    else:
        print(f"结论: {len(bad)} 项未就绪 -> {', '.join(bad)}")
        if FIXES:
            print("\n怎么修:")
            for f in dict.fromkeys(FIXES):
                print(f"  · {f}")
    print("=" * 78)
    return 1 if bad else 0


if __name__ == "__main__":
    _code = main()
    # 绕开解释器关停阶段的原生析构：实测本脚本在打印完结论后、Python 关停时
    # 会触发 Windows 访问冲突（0xC0000005，堆栈里没有 Python 帧）——是某个原生库
    # 的析构顺序问题，跟检查结果无关（10 项此时已全部跑完并打印）。
    # 先 flush 再 os._exit，免得用户在「全部就绪」后面看到一个崩溃弹窗。
    # 主程序 app.py 不受影响：它在 root.destroy() 之前就 save_settings()/close_cache() 了。
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_code)
