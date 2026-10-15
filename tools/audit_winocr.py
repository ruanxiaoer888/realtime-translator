# -*- coding: utf-8 -*-
"""Windows 自带 OCR 与当前拉丁 RapidOCR 的对比测试（装完葡语语言包后跑这个）。

做三件事：
  1. 列出系统 OCR 可用语言，检查 pt-BR / es-MX 装了没有
  2. 用当前可用的语言做一次管线冒烟（验证 winsdk -> SoftwareBitmap -> recognize 走得通）
  3. 如果 pt-BR 已就绪：拿同一批合成评论图，对比两个引擎的**字错率**和**单帧耗时**

运行（项目根目录）:
    python tools\\audit_winocr.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "libs"))

import numpy as np  # noqa: E402

import audit_ocr as base  # noqa: E402  (同一套渲染 + CER 指标)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

EN_LINES = [
    "Is the price still available today?",
    "I just ordered two pieces, thank you",
    "Does it come with a carrying case?",
    "Shipping to Miami took three days",
    "The battery lasts a whole day",
    "Can you show the blue color again?",
    "Great quality for this price",
    "Any discount for three units?",
]

# ------------------------------------------------------------ Windows OCR
_winsdk_error = None
try:
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import (
        BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap,
    )
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage.streams import DataWriter
except Exception as e:  # noqa: BLE001
    _winsdk_error = f"{type(e).__name__}: {e}"
    OcrEngine = None


def available_langs() -> list[str]:
    if OcrEngine is None:
        return []
    return [l.language_tag for l in OcrEngine.available_recognizer_languages]


def make_engine(tag: str):
    return OcrEngine.try_create_from_language(Language(tag))


def to_software_bitmap(rgb: np.ndarray) -> "SoftwareBitmap":
    """RGB numpy 数组 -> Windows 的 SoftwareBitmap（BGRA8）。"""
    h, w = rgb.shape[:2]
    bgra = np.empty((h, w, 4), dtype=np.uint8)
    bgra[:, :, 0] = rgb[:, :, 2]      # B
    bgra[:, :, 1] = rgb[:, :, 1]      # G
    bgra[:, :, 2] = rgb[:, :, 0]      # R
    bgra[:, :, 3] = 255               # A
    writer = DataWriter()
    writer.write_bytes(bgra.tobytes())
    buf = writer.detach_buffer()
    return SoftwareBitmap.create_copy_from_buffer(
        buf, BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.PREMULTIPLIED
    )


async def _recognize(engine, sb):
    return await engine.recognize_async(sb)


def win_ocr(engine, rgb: np.ndarray) -> tuple[str, float]:
    """返回 (识别文本, 耗时秒)。"""
    sb = to_software_bitmap(rgb)
    t0 = time.perf_counter()
    res = asyncio.run(_recognize(engine, sb))
    dt = time.perf_counter() - t0
    text = " ".join(ln.text.strip() for ln in res.lines) if res else ""
    return text.strip(), dt


def recognize_latin(rgb: np.ndarray) -> tuple[str, float]:
    """拉丁 RapidOCR 的识别（返回文本 + 耗时），口径与 win_ocr 一致。

    必须**显式** set_ocr_engine("latin")。踩过的坑：st.recognize() 用的是界面上的
    「屏幕识别」偏好（默认 auto），pt-BR 语言包装好之后 auto 会走 Windows OCR ——
    那样这一列测的就成了 Windows OCR 自己，两列 CER 全 0.0000、耗时一模一样。
    """
    import screen_translate as st
    st.set_ocr_engine("latin")
    t0 = time.perf_counter()
    items = st.recognize(rgb)
    dt = time.perf_counter() - t0
    return st.merge_lines(items), dt


# ------------------------------------------------------------ main
def status_only():
    """只看语言包装到哪一步了（秒出，不做任何 OCR）。"""
    if OcrEngine is None:
        print(f"winsdk 不可用: {_winsdk_error}")
        print("安装: python fetch_wheels.py winsdk")
        return 2
    langs = available_langs()
    pt = [l for l in langs if l.lower().startswith("pt")]
    es = [l for l in langs if l.lower().startswith("es")]
    print(f"系统 OCR 语言 : {', '.join(langs) if langs else '(无)'}")
    print(f"葡语 OCR      : {'已就绪 ' + str(pt) if pt else '还没装上'}")
    print(f"西语 OCR      : {'已就绪 ' + str(es) if es else '还没装上'}")

    # 语音识别引擎目录（实时字幕要用）
    sr = []
    for d in (r"C:\Windows\Speech_OneCore\Engines\SR", r"C:\Windows\Speech\Engines\SR"):
        try:
            sr += [f"{os.path.basename(d)}/{n}" for n in os.listdir(d)]
        except Exception:
            pass
    pt_sr = [x for x in sr if "pt" in x.lower()]
    print(f"语音识别引擎  : {', '.join(sr) if sr else '(读不到，可能被沙箱拦了)'}")
    print(f"葡语语音引擎  : {'已就绪 ' + str(pt_sr) if pt_sr else '还没装上'}")

    # 待重启判断：语言包在设置页显示「已安装」不等于生效，模型文件要重启才落盘。
    # 这个判断从 check_pt_speech.py 复用，避免两处各写一套。
    try:
        from check_pt_speech import installed_languages, pending_reboot
        reboot = pending_reboot()
        added = installed_languages()
    except Exception:
        reboot, added = "", []

    if pt:
        print("\n葡语 OCR 已可用 -> 跑完整对比: python tools\\audit_winocr.py")
    elif reboot and any(l.lower().startswith("pt") for l in added):
        print("\n**请重启电脑。** 语言包已装、pt-BR 也已添加，但引擎文件还没落盘。")
        print(f"  依据：系统有待重启项（{reboot}）。")
        print("  设置页显示「已安装」只是功能登记；重启后再跑一次本脚本即可看到葡语 OCR 就绪。")
        print("  （更详细的检查: python tools\\check_pt_speech.py）")
    else:
        print("\n葡语组件还没装。需要装这两项：")
        print("   · 光学字符识别（'所需的语言功能'里自动带的，对应上面的葡语 OCR）")
        print("   · 增强的语音识别（实时字幕要用，对应上面的葡语语音引擎）")
        print("  装法见 python tools\\check_pt_speech.py 的输出。")
    return 0


def main():
    if "--status" in sys.argv:
        return status_only()
    print("#" * 78)
    print("Windows OCR vs 拉丁 RapidOCR 对比")
    print("#" * 78)

    if OcrEngine is None:
        print(f"[FAIL] winsdk 不可用: {_winsdk_error}")
        print("       安装: python fetch_wheels.py winsdk")
        return 2

    langs = available_langs()
    print(f"[1] 系统 OCR 可用语言: {', '.join(langs) if langs else '(无)'}")
    pt = [l for l in langs if l.lower().startswith("pt")]
    es = [l for l in langs if l.lower().startswith("es")]
    print(f"    葡语: {pt or '未安装'}")
    print(f"    西语: {es or '未安装'}")

    # ---- [2] 管线冒烟：用当前能用的任意语言验证整条链路 ----
    print("\n[2] 管线冒烟")
    probe_tag = None
    probe_lines = None
    for tag, lines in (("pt-BR", base.PT_LINES), ("es-MX", base.ES_LINES),
                       ("en-US", EN_LINES), ("zh-Hans-CN", None)):
        if tag in langs and lines is not None:
            eng = make_engine(tag)
            if eng is not None:
                probe_tag, probe_lines, probe_engine = tag, lines, eng
                break
    if probe_tag is None:
        print("    [SKIP] 没有可用于拉丁文本的 OCR 语言")
    else:
        img = base.render(probe_lines, size=18)
        text, dt = win_ocr(probe_engine, img)
        print(f"    使用语言 {probe_tag}  耗时 {dt*1000:.0f} ms")
        print(f"    识别: {text[:110]}")
        print(f"    行数: {len(probe_lines)}")

    # ---- [3] 装了葡语/西语就做正式对比 ----
    if not pt and not es:
        print("\n[3] 正式对比：跳过 —— pt-BR / es-MX 语言包还没装好")
        print("    装好后重跑本脚本即可。安装路径：")
        print("    设置 → 时间和语言 → 语言和区域 → 添加语言 → Português (Brasil)")
        print("    （语言包 + 光学字符识别 必须装；'设置为我的显示语言' 不要勾）")
        return 0

    print("\n[3] 正式对比（同一批合成评论图）")
    import screen_translate as st
    # 两个引擎都预热：否则某一列会把模型加载的 2~3 秒算进去，对比失真。
    # 顺序必须是 win 在前、latin 在后 —— screen_translate 只缓存**一个**引擎，
    # 最后留在缓存里的那个才不会在正式对比时被重新加载。
    for pref in ("win", "latin"):
        st.set_ocr_engine(pref)
        st.get_ocr(pref)
        st.recognize(base.render(base.PT_LINES, size=18))
    print("    两个引擎均已预热（各自的模型加载成本已各付一次）")

    cases = []
    if pt:
        cases.append(("葡语 18pt", base.PT_LINES, 18, "pt-BR"))
        cases.append(("葡语 14pt", base.PT_LINES, 14, "pt-BR"))
    if es:
        cases.append(("西语 18pt", base.ES_LINES, 18, "es-MX"))
        cases.append(("西语 14pt", base.ES_LINES, 14, "es-MX"))

    print(f"\n    {'用例':<12} {'Windows OCR':>26} {'拉丁 RapidOCR':>26}")
    print(f"    {'':<12} {'CER':>10} {'耗时':>13} {'CER':>10} {'耗时':>13}")
    results = []
    for label, lines, size, tag in cases:
        img = base.render(lines, size=size)
        ref = base.norm(" ".join(lines))

        eng = make_engine(tag)
        wtext, wdt = win_ocr(eng, img)
        wlev, _ = base.edit_ops(ref, base.norm(wtext))
        wcer = wlev / max(1, len(ref))

        rtext, rdt = recognize_latin(img)
        rlev, _ = base.edit_ops(ref, base.norm(rtext))
        rcer = rlev / max(1, len(ref))

        results.append((label, wcer, wdt, rcer, rdt))
        print(f"    {label:<12} {wcer:>10.4f} {wdt*1000:>10.0f} ms {rcer:>10.4f} {rdt*1000:>10.0f} ms")

    print("\n    结论：")
    for label, wcer, wdt, rcer, rdt in results:
        if wcer < rcer - 0.001:
            verdict = f"Windows OCR 更准（{wcer:.4f} vs {rcer:.4f}）"
        elif rcer < wcer - 0.001:
            verdict = f"拉丁模型更准（{rcer:.4f} vs {wcer:.4f}）"
        else:
            verdict = "准确率持平"
        speed = f"，快 {rdt/wdt:.1f} 倍" if wdt > 0 and rdt > wdt else ""
        print(f"      {label}: {verdict}{speed}")
    print("\n    说明：app.py 里「屏幕识别」选「自动」就会在语言包就绪时用 Windows OCR，")
    print("    不需要改代码；想固定用某一个就选「系统 OCR（快）」或「本地模型（准）」。")
    print("    单帧冷/热两个口径的完整数据见 python tools\\bench_ocr_speed.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
