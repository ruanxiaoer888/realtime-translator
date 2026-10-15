# -*- coding: utf-8 -*-
"""一键生成诊断报告。

出问题、又联系不上助手的时候跑这个：

    python tools\\collect_report.py

它会在项目根目录生成 **诊断报告.txt**，里面把定位问题需要的东西都收集好了：
Python 版本与路径、libs 依赖、模型文件、当前设置、屏幕与音频设备、
系统声音回环、翻译通道、以及 check_deploy.py 的完整输出。

把这个文件发出去就能定位问题，不用来回问。
"""
from __future__ import annotations

import datetime
import os
import platform
import subprocess
import sys
import traceback
import warnings

# 项目里统一这么屏蔽（mss 的新旧 API 警告），跟随 check_env / screen_translate 的做法
warnings.filterwarnings("ignore", message="mss.mss is deprecated")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "诊断报告.txt")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "libs"))

LINES: list[str] = []


def w(s: str = ""):
    LINES.append(str(s))


def section(title: str):
    w()
    w("=" * 70)
    w(title)
    w("=" * 70)


def try_block(label: str, fn):
    """跑一段检查，出错也只记录不中断 —— 诊断脚本本身绝不能崩。"""
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        w(f"  [收集失败] {label}: {type(e).__name__}: {e}")


# ---------------------------------------------------------------- 1 基本信息
def basic():
    w(f"生成时间 : {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    w(f"项目目录 : {ROOT}")
    w(f"项目存在 : {os.path.isdir(ROOT)}")
    w(f"Python   : {sys.version.replace(chr(10), ' ')}")
    w(f"解释器   : {sys.executable}")
    w(f"位数     : {'64 位 OK' if sys.maxsize > 2**32 else '32 位 !! 不行'}")
    w(f"可执行名 : {os.path.basename(sys.executable)}"
      f"{'   (pythonw = 无控制台版，正常)' if 'pythonw' in sys.executable.lower() else ''}")


# ---------------------------------------------------------------- 2 系统硬件
def system_info():
    w(f"系统     : {platform.platform()}")
    w(f"机器名   : {platform.node()}")
    w(f"处理器   : {platform.processor()}")
    try:
        import shutil
        total, used, free = shutil.disk_usage(ROOT)
        w(f"磁盘     : 所在盘可用 {free/1024**3:.1f} GB / 共 {total/1024**3:.1f} GB")
    except Exception:
        pass
    try:
        nv = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                             "--format=csv,noheader"],
                            capture_output=True, text=True, timeout=15)
        w(f"显卡     : {nv.stdout.strip() or '(nvidia-smi 无输出)'}")
    except FileNotFoundError:
        w("显卡     : 没有 nvidia-smi（无 N 卡或未装驱动）—— CPU 也能跑")
    except Exception as e:
        w(f"显卡     : 查询失败 {type(e).__name__}: {e}")


# ---------------------------------------------------------------- 3 依赖
def deps():
    libs = os.path.join(ROOT, "libs")
    w(f"libs 目录: {'存在' if os.path.isdir(libs) else '**不存在** —— 必须整个拷过来'}")
    if os.path.isdir(libs):
        n = sum(len(f) for _, _, f in os.walk(libs))
        sz = sum(os.path.getsize(os.path.join(d, f))
                 for d, _, fs in os.walk(libs) for f in fs)
        w(f"           {n} 个文件 / {sz/1024**2:.0f} MB")
    for mod in ("numpy", "ctranslate2", "faster_whisper", "onnxruntime",
                "rapidocr_onnxruntime", "soundcard", "mss", "winsdk", "PIL", "cv2"):
        try:
            m = __import__(mod)
            w(f"  [OK  ] {mod:<24} {getattr(m, '__version__', '')}")
        except Exception as e:  # noqa: BLE001
            w(f"  [FAIL] {mod:<24} {type(e).__name__}: {e}")


# ---------------------------------------------------------------- 4 模型
def models():
    base = os.path.join(ROOT, "tmp", "models")
    w(f"模型目录 : {base}")
    if not os.path.isdir(base):
        w("  **不存在** —— 模型没拷过来")
        return
    for name in sorted(os.listdir(base)):
        p = os.path.join(base, name)
        if not os.path.isdir(p):
            continue
        files = [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs]
        sz = sum(os.path.getsize(f) for f in files)
        w(f"  {name:<20} {sz/1024**2:8.1f} MB   {len(files)} 文件")


# ---------------------------------------------------------------- 5 设置
def settings():
    sf = os.path.join(ROOT, "settings.json")
    if not os.path.isfile(sf):
        w("settings.json 不存在（会用默认值）")
        return
    w(open(sf, encoding="utf-8").read().strip())


# ---------------------------------------------------------------- 6 屏幕音频
def screen_audio():
    import mss
    with mss.mss() as sct:
        w(f"显示器   : {len(sct.monitors) - 1} 个")
        for i, m in enumerate(sct.monitors[1:], 1):
            w(f"  #{i}  {m['width']}x{m['height']}  位置 {m['left']},{m['top']}")
    import soundcard as sc
    spk = sc.default_speaker()
    w(f"默认扬声器: {spk.name}")
    mic = sc.get_microphone(str(spk.name), include_loopback=True)
    w(f"回环设备  : {mic.name}")
    import numpy as np
    with mic.recorder(samplerate=16000) as r:
        data = r.record(numframes=16000)
    rms = float(np.sqrt((data ** 2).mean()))
    peak = float(np.abs(data).max())
    w(f"回环实测  : RMS {rms:.4f}  峰值 {peak:.4f}  "
      f"{'(安静，正常：现在没在放声音)' if peak < 0.001 else '(有声音)'}")


# ---------------------------------------------------------------- 7 OCR
def ocr():
    import screen_translate as st
    w(f"拉丁模型可用: {st.latin_available()}")
    w(f"系统 OCR 语言: {st.win_ocr_tags_available()}")
    w(f"当前生效引擎: {st.ocr_engine_name()}")
    for loc in ("pt-BR", "es-MX", "en-US"):
        w(f"  {loc:<8} -> {st.win_ocr_available(loc) or '（不可用，回退本地模型）'}")


# ---------------------------------------------------------------- 8 翻译
def translate():
    import translate_core as tc
    w(f"通道顺序 : {tuple(f.__name__ for f in tc._CHANNELS)}")
    out = None
    try:
        out = tc.translate("Olá, bem-vindo à minha loja", "pt", "zh-CN")
    except Exception as e:  # noqa: BLE001
        w(f"试译异常 : {type(e).__name__}: {e}")
    w(f"试译结果 : {out!r}")
    w(f"通道状态 : {tc.channel_status()}")


# ---------------------------------------------------------------- 9 自检全文
def run_check_deploy():
    script = os.path.join(ROOT, "check_deploy.py")
    if not os.path.isfile(script):
        w("check_deploy.py 不存在")
        return
    w("正在跑 check_deploy.py（约半分钟）……")
    try:
        r = subprocess.run([sys.executable, script], cwd=ROOT,
                           capture_output=True, text=True, timeout=600,
                           encoding="utf-8", errors="replace")
        w(f"退出码: {r.returncode}")
        w("--- stdout ---")
        w((r.stdout or "").strip())
        if r.stderr and r.stderr.strip():
            w("--- stderr ---")
            w(r.stderr.strip())
    except subprocess.TimeoutExpired:
        w("超时（10 分钟）")
    except Exception as e:  # noqa: BLE001
        w(f"运行失败: {type(e).__name__}: {e}")


def main():
    w("实时翻译助手 · 诊断报告")
    w("把这个文件整个发给助手即可定位问题（不要只截一小段）")

    section("1. 基本信息")
    try_block("基本信息", basic)

    section("2. 操作系统与硬件")
    try_block("系统信息", system_info)

    section("3. 依赖（libs）")
    try_block("依赖", deps)

    section("4. 模型文件")
    try_block("模型", models)

    section("5. 当前设置（settings.json）")
    try_block("设置", settings)

    section("6. 屏幕与音频")
    try_block("屏幕音频", screen_audio)

    section("7. OCR 引擎")
    try_block("OCR", ocr)

    section("8. 翻译通道")
    try_block("翻译", translate)

    section("9. check_deploy.py 完整输出")
    try_block("自检", run_check_deploy)

    section("完")
    w("如果上面某一节只有 [收集失败]，那本身就说明问题出在那里。")

    text = "\n".join(LINES) + "\n"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print()
    print(f"已写入: {OUT}")
    print("把这个文件整个发出去即可。")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
