# -*- coding: utf-8 -*-
"""检查系统有没有装「葡萄牙语（巴西）」的语音识别 / OCR 组件。

为什么需要它：有两条路要先装 Windows 语言包才能走 ——
  1) Windows 实时字幕（Win+Ctrl+L）想识别葡语，必须有 pt-BR 的语音识别引擎
  2) 想把屏幕翻译从本地 OCR（约 1.3 秒/次）换成系统自带 OCR（约 0.1 秒/次），
     必须有 pt-BR 的光学字符识别组件
装完之后用这个脚本确认装好了没有。

运行（在项目根目录下）:
    python tools\\check_pt_speech.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

TARGETS = {"pt": "葡萄牙语（巴西）", "es": "西班牙语"}


def check_speech_recognizers() -> tuple[bool, list[str], str]:
    """用 WinRT 问系统装了哪些语音识别器。"""
    try:
        from winsdk.windows.media.speech_recognition import SpeechRecognizer
        tags = [r.language.language_tag for r in SpeechRecognizer.installed_recognizers]
        return True, tags, ""
    except Exception as e:
        return False, [], f"{type(e).__name__}: {str(e)[:70]}"


def check_ocr_languages() -> tuple[bool, list[str], str]:
    """系统自带 OCR 支持哪些语言。"""
    try:
        from winsdk.windows.media.ocr import OcrEngine
        tags = [l.language_tag for l in OcrEngine.available_recognizer_languages]
        return True, tags, ""
    except Exception as e:
        return False, [], f"{type(e).__name__}: {str(e)[:70]}"


def check_engine_dirs() -> dict[str, list[str]]:
    """看语音引擎目录里有哪些语言（读不到就跳过，不算失败）。"""
    out: dict[str, list[str]] = {}
    for d in (r"C:\Windows\Speech\Engines\SR", r"C:\Windows\Speech_OneCore\Engines\SR",
              r"C:\Windows\Speech\Common", r"C:\Windows\OCR"):
        try:
            out[d] = sorted(os.listdir(d))
        except Exception:
            out[d] = []
    return out


def main():
    print("=" * 66)
    print("系统语言组件检查（葡萄牙语 / 西班牙语）")
    print("=" * 66)

    ok_sr, sr_tags, sr_err = check_speech_recognizers()
    print("\n【语音识别器】（Windows 实时字幕要用）")
    if ok_sr:
        print(f"  已安装: {', '.join(sr_tags) if sr_tags else '（无）'}")
    else:
        print(f"  查询失败: {sr_err}")
        print("  （不影响本工具的直播同传，那条路用 faster-whisper，不依赖系统语言包）")

    ok_ocr, ocr_tags, ocr_err = check_ocr_languages()
    print("\n【系统 OCR 语言】（把屏幕翻译提速到约 0.1 秒/次要用）")
    if ok_ocr:
        print(f"  可用: {', '.join(ocr_tags) if ocr_tags else '（无）'}")
    else:
        print(f"  查询失败: {ocr_err}")

    print("\n【语音引擎目录】（辅助参考）")
    for d, names in check_engine_dirs().items():
        print(f"  {d}")
        print(f"      {', '.join(names) if names else '（读不到或为空）'}")

    print("\n" + "=" * 66)
    print("结论")
    print("=" * 66)
    verdict = []
    for code, label in TARGETS.items():
        has_sr = any(t.lower().startswith(code) for t in sr_tags)
        has_ocr = any(t.lower().startswith(code) for t in ocr_tags)
        verdict.append((label, has_sr, has_ocr))
        print(f"  {label:14s} 语音识别 {'已就绪' if has_sr else '未安装'} ｜ "
              f"OCR {'已就绪' if has_ocr else '未安装'}")

    if any(v[1] or v[2] for v in verdict):
        print("\n  已装好。实时字幕：Win+Ctrl+L → 右上角齿轮 → 把语言改成对应语言。")
        print("  想换成系统 OCR 提速，告诉我一声改 screen_translate.py 即可。")
    else:
        print("\n  还没装。装法：")
        print("    设置 → 时间和语言 → 语言和区域 → 添加语言 → 搜 Português (Brasil) → 下一步")
        print("    勾选：语言包 + 增强的语音识别；不要勾「设为我的显示语言」")
        print("    装完重启电脑，再跑一次本脚本确认。")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
