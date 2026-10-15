# -*- coding: utf-8 -*-
"""发布前总验收：完全按 app.py 的方式加载（libs 优先），验证真实功能没有回归。

覆盖：依赖自包含 / OCR 真实识别 / 语音识别真实推理 / 术语修正 / 画面变化 /
      翻译通道熔断 / 界面构建 / 各脚本可编译

运行（项目根目录）: python tools\\final_check.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 严格按 app.py 的顺序：先把 libs 放进搜索路径，再导入第三方包
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))


def main():
    print("=" * 78)
    print("发布前总验收（libs 优先，等同 app.py 的加载方式）")
    print("=" * 78)

    # 1) 依赖全部来自 libs
    import numpy
    check("numpy 来自 libs", os.path.join(ROOT, "libs") in (numpy.__file__ or ""), numpy.__version__)

    # 2) OCR 真实识别（不是只加载引擎）
    import screen_translate as st
    import audit_ocr as base
    print(f"  OCR 引擎: {st.ocr_engine_name()}")
    img = base.render(base.PT_LINES, size=18)
    ref = base.norm(" ".join(base.PT_LINES))
    hyp = base.norm(st.merge_lines(st.recognize(img)))
    lev, _ = base.edit_ops(ref, hyp)
    check("OCR 真实识别葡语（含重音）", lev == 0, f"字错率 {lev/max(1,len(ref)):.4f}")

    # 3) 语音识别真实推理
    import wave
    import asr_engine
    with wave.open(os.path.join(ROOT, "tmp", "es_tts_all.wav"), "rb") as w:
        audio = numpy.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32") / 32768.0
    txt, dt = asr_engine.transcribe(audio, language="es", size="small")
    dev = asr_engine.device_info()
    check("语音识别真实推理", bool(txt) and "taladro" in txt.lower(),
          f"{dev.get('device')}/{dev.get('compute_type')} {dt:.2f}s  {txt[:40]}")

    # 4) 术语修正不污染、该修的还修
    import markets
    asr_engine.set_terminology(prompt="", glossary=markets.get_glossary("五金工具", "pt"))
    import translate_core as tc
    bad = tc.apply_glossary("uma parafusadeira e uma chave de fenda",
                            "一把电动螺丝刀和一把一字螺丝刀")
    good = tc.apply_glossary("essa furadeira vem com maleta",
                             "此演习附带一个完整的盒子")
    check("术语修正不污染", bad == "一把电动螺丝刀和一把一字螺丝刀", bad)
    check("术语修正仍生效",
          "电钻" in good and "工具箱" in good and "演习" not in good and "盒子" not in good,
          good)

    # 5) 画面变化检测
    rng = numpy.random.default_rng(0)
    a = base.render(base.PT_LINES)
    b = base.render(["Acabei de entrar na live!"] + base.PT_LINES[1:])
    noisy = numpy.clip(a.astype(numpy.int16) + rng.integers(-3, 4, a.shape), 0, 255).astype(numpy.uint8)
    check("单行换评论能触发", st.signature_changed(st.frame_signature(a), st.frame_signature(b)))
    check("噪点不误触发", not st.signature_changed(st.frame_signature(a), st.frame_signature(noisy)))

    # 6) 翻译通道 + 熔断
    t0 = time.time()
    out = tc.translate("Ola, bem-vindo a minha loja", "pt-BR", "zh-CN")
    first = time.time() - t0
    times = []
    for s in ("A bateria dura o dia todo.", "Compre pelo carrinho amarelo."):
        tc.clear_cache()
        t0 = time.time()
        o = tc.translate(s, "pt-BR", "zh-CN")
        times.append(time.time() - t0)
        if not o:
            out = None
    check("在线翻译可用", bool(out), f"首句 {first:.2f}s")
    check("熔断后不再白等超时通道", all(t < 5.0 for t in times),
          f"后续 {', '.join(f'{t:.2f}s' for t in times)}  通道 {tc.channel_status()}")

    # 7) 界面能建起来
    import app as A
    a2 = A.App()
    title = a2.root.title()
    a2.var_market.set("墨西哥")
    a2.apply_market()
    hdr = a2.lbl_src_hdr.cget("text")
    a2.root.destroy()
    check("界面构建 + 标题跟随市场", "西班牙语" in hdr, f"{title} / {hdr}")

    # 8) 所有发布用的脚本能编译（根目录 + tools/）
    scripts = [f for f in sorted(os.listdir(ROOT)) if f.endswith(".py")]
    scripts += [os.path.join("tools", f) for f in sorted(os.listdir(os.path.join(ROOT, "tools")))
                if f.endswith(".py")]
    r = subprocess.run([sys.executable, "-m", "py_compile"] + scripts,
                       cwd=ROOT, capture_output=True, text=True)
    check("全部 .py 可编译", r.returncode == 0, f"{len(scripts)} 个文件" +
          ("" if r.returncode == 0 else "  " + r.stderr[:200]))

    # 9) .ps1 必须是纯 ASCII —— 这不是洁癖，是硬约束。
    #    start.ps1 的头部注释早就写了原因，但依然被踩过：Windows PowerShell 5.1
    #    按系统 ANSI(GBK) 读 UTF-8 无 BOM 的 .ps1，中文注释的多字节序列会把后面的
    #    换行符当成双字节字符的一部分吃掉 -> 行被合并 -> 整个脚本解析失败
    #    （表现为双击 .bat 直接闪退，或 here-string 被吞掉一大段）。
    ps1 = [f for f in sorted(os.listdir(ROOT)) if f.lower().endswith(".ps1")]
    dirty = []
    for f in ps1:
        with open(os.path.join(ROOT, f), "rb") as fh:
            if any(b > 127 for b in fh.read()):
                dirty.append(f)
    check(".ps1 均为纯 ASCII（PS 5.1 只认 ANSI）", not dirty,
          f"{len(ps1)} 个文件" + ("  含非 ASCII: " + ", ".join(dirty) if dirty else ""))

    # 10) 同样地，.bat 也只能是 ASCII（cmd 按系统 ANSI 读）
    bats = [f for f in sorted(os.listdir(ROOT)) if f.lower().endswith(".bat")]
    bat_dirty = []
    for f in bats:
        with open(os.path.join(ROOT, f), "rb") as fh:
            if any(b > 127 for b in fh.read()):
                bat_dirty.append(f)
    check(".bat 均为纯 ASCII", not bat_dirty,
          f"{len(bats)} 个文件" + ("  含非 ASCII: " + ", ".join(bat_dirty) if bat_dirty else ""))

    print("=" * 78)
    print(f"结果: 通过 {len(PASS)} 项, 失败 {len(FAIL)} 项")
    for f in FAIL:
        print(f"  - {f}")
    print("=" * 78)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
