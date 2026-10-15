# -*- coding: utf-8 -*-
"""检查系统有没有装「葡萄牙语（巴西）」的语音识别 / OCR 组件。

为什么需要它：有两条路要先装 Windows 语言包才能走 ——
  1) Windows 实时字幕（Win+Ctrl+L）想识别葡语，必须有 pt-BR 的语音识别引擎
  2) 想把屏幕翻译从本地 OCR（约 1.3 秒/次）换成系统自带 OCR（约 0.1 秒/次），
     必须有 pt-BR 的光学字符识别组件
装完之后用这个脚本确认装好了没有。

**特别提醒**：语言包在设置页显示「已安装」不等于能用 —— OCR / 语音的模型文件
要等重启才落盘。这个脚本会检测待重启状态，避免把「等重启」误判成「没装」。

运行（在项目根目录下）:
    python tools\\check_pt_speech.py
"""
from __future__ import annotations

import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

TARGETS = {"pt": "葡萄牙语（巴西）", "es": "西班牙语"}

# 常见 LCID -> 语言标记（语音识别器的 token 名里带 LCID，如 MS-2052-110-WINMO-DNN）
LCID = {
    1033: "en-US", 2052: "zh-CN", 1028: "zh-TW",
    1046: "pt-BR", 2070: "pt-PT",
    1034: "es-ES", 3082: "es-ES", 2058: "es-MX", 1033 + 4096: "es-419",
}

SPEECH_KEYS = (
    (r"SOFTWARE\Microsoft\Speech_OneCore\Recognizers\Tokens", "OneCore（实时字幕用这个）"),
    (r"SOFTWARE\Microsoft\Speech\Recognizers\Tokens", "经典 SAPI"),
)
OCR_KEYS = (r"SOFTWARE\Microsoft\Speech_OneCore\Recognizers\Tokens",)


def check_speech_recognizers() -> dict[str, list[str]]:
    """读注册表里注册了哪些语音识别器。

    不走 WinRT：winsdk 没有暴露 SpeechRecognizer 的静态属性 installed_recognizers，
    调它会 AttributeError。注册表更直接，也更好解释。
    """
    import winreg
    out: dict[str, list[str]] = {}
    for path, label in SPEECH_KEYS:
        found: list[str] = []
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    m = re.search(r"MS-(\d+)-", name)
                    if m:
                        lcid = int(m.group(1))
                        found.append(LCID.get(lcid, f"LCID {lcid}"))
                    i += 1
        except Exception:
            pass
        out[label] = sorted(set(found))
    return out


def check_ocr_languages() -> tuple[bool, list[str], str]:
    """系统自带 OCR 支持哪些语言（WinRT，这条路是好的）。"""
    try:
        from winsdk.windows.media.ocr import OcrEngine
        tags = [l.language_tag for l in OcrEngine.available_recognizer_languages]
        return True, tags, ""
    except Exception as e:
        return False, [], f"{type(e).__name__}: {str(e)[:70]}"


def check_engine_dirs() -> dict[str, list[str]]:
    """看语音引擎 / OCR 的模型目录里有哪些语言（辅助参考）。"""
    out: dict[str, list[str]] = {}
    for d in (r"C:\Windows\Speech\Engines\SR", r"C:\Windows\Speech_OneCore\Engines\SR",
              r"C:\Windows\Speech\Common", r"C:\Windows\OCR"):
        try:
            out[d] = sorted(os.listdir(d))
        except Exception:
            out[d] = []
    return out


def installed_languages() -> list[str]:
    """用户在系统里添加了哪些语言。

    位置：HKCU\\Control Panel\\International\\User Profile，每种语言是一个**子键**
    （en-US / pt-BR / zh-Hans-CN），不是值 —— 按值枚举会一个都读不到。
    """
    import winreg
    out: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Control Panel\International\User Profile") as k:
            i = 0
            while True:
                try:
                    out.append(winreg.EnumKey(k, i))
                except OSError:
                    break
                i += 1
    except Exception:
        pass
    return sorted(out)


def boot_time() -> float:
    """上次开机时间（time.time() 时间戳）。

    用 TickCount64（开机以来的毫秒数）反推，不依赖 WMI（沙箱里常被拒）。
    """
    return time.time() - _uptime_seconds()


def _uptime_seconds() -> float:
    """开机至今的秒数。Windows 上 GetTickCount64 最直接。"""
    try:
        import ctypes
        return ctypes.windll.kernel32.GetTickCount64() / 1000.0
    except Exception:
        return 0.0


def component_time(lang: str = "pt-br") -> float:
    """该语言组件包写入系统仓库的时间（取最新的那个 .mum）。

    用途：和上次开机时间比 —— 如果组件是**开机之后**才写进来的，那确实需要重启；
    如果**开机之前**就写好了，说明重启已经试过，问题不在重启（本机实测就是这么踩的坑）。
    """
    import glob
    newest = 0.0
    for pat in ("LanguageFeatures-OCR", "LanguageFeatures-Speech", "LanguageFeatures-Basic"):
        for p in glob.glob(rf"C:\Windows\servicing\Packages\Microsoft-Windows-{pat}-{lang}-Package~*.mum"):
            try:
                newest = max(newest, os.path.getmtime(p))
            except Exception:
                pass
    return newest


def pending_reboot() -> str:
    """系统是否有待重启标志。

    ⚠️ 注意：这几个标志在有些机器上**重启后也不会清掉**（本机实测：
    CBS RebootPending 和 PendingFileRenameOperations 里的阿里旺旺项每次开机都还在）。
    所以它们只能当参考，**不能**用来判断"用户没重启"——
    要判断重启与否，请看 component_time() 和 boot_time() 的比较。
    """
    import winreg
    reasons = []
    for path, label in (
        (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending", "组件安装"),
        (r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired", "Windows 更新"),
    ):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path):
                reasons.append(label)
        except Exception:
            pass
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\Session Manager") as k:
            val, _t = winreg.QueryValueEx(k, "PendingFileRenameOperations")
            if val:
                reasons.append(f"待替换文件 {len(val)} 条")
    except Exception:
        pass
    return "、".join(reasons)


def staged_components(lang: str = "pt-br") -> dict[str, bool]:
    """该语言的各个组件有没有下载到系统仓库（C:\\Windows\\servicing\\Packages）。

    这一步很关键：组件"下载了但没生效"和"压根没下载"是两种完全不同的处置 ——
    前者重启就好，后者要回设置里勾选。只看 C:\\Windows\\OCR 有没有文件分不清这两者。
    """
    import glob
    base = r"C:\Windows\servicing\Packages"
    kinds = (("语言包", "LanguageFeatures-Basic"),
             ("OCR", "LanguageFeatures-OCR"),
             ("语音识别", "LanguageFeatures-Speech"),
             ("文本转语音", "LanguageFeatures-TextToSpeech"))
    out: dict[str, bool] = {}
    for label, pat in kinds:
        try:
            out[label] = bool(glob.glob(os.path.join(base, f"Microsoft-Windows-{pat}-{lang}-Package~*")))
        except Exception:
            out[label] = False
    return out


def stuck_transaction() -> tuple[bool, float]:
    """有没有卡住的部署事务（C:\\Windows\\WinSxS\\pending.xml）。

    pending.xml 正常情况在重启时被处理掉并删除。如果它长时间存在，说明有部署事务
    执行不完（本机实测：事务里的 OCR/Speech-pt-br-Deployment 操作都在，但 CBS 报
    Error 800f0983 组件仓库错误，事务卡了 1 个多小时没动）——
    这种情况下 Add-WindowsCapability / 重启都没用，要修组件仓库：
        DISM /Online /Cleanup-Image /RestoreHealth
    返回 (是否存在, 存在了多少小时)。
    """
    p = r"C:\Windows\WinSxS\pending.xml"
    try:
        age = (time.time() - os.path.getmtime(p)) / 3600.0
        return True, age
    except Exception:
        return False, 0.0


def main():
    print("=" * 66)
    print("系统语言组件检查（葡萄牙语 / 西班牙语）")
    print("=" * 66)

    langs = installed_languages()
    reboot = pending_reboot()
    staged = staged_components("pt-br")

    boot = boot_time()
    comp = component_time("pt-br")
    print(f"\n已添加的语言: {', '.join(langs) if langs else '（读不到）'}")
    print("组件是否已下载到系统仓库: " +
          "，".join(f"{k}{'✓' if v else '✗'}" for k, v in staged.items()))
    if comp:
        print(f"组件写入时间: {time.strftime('%m-%d %H:%M:%S', time.localtime(comp))}"
              f" ｜ 上次开机: {time.strftime('%m-%d %H:%M:%S', time.localtime(boot))}")
        rebooted_since = boot > comp
        print("  -> " + ("组件是开机之后写入的 —— 还没重启过" if not rebooted_since
                         else "组件是开机之前写入的 —— **重启已经试过了，问题不在重启**"))
    if reboot:
        print(f"（参考）系统有待重启标志: {reboot}")
        print("  注意：这几个标志在有些机器上重启后也不会清掉，不能当作「没重启」的证据。")

    sr = check_speech_recognizers()
    print("\n【语音识别引擎】（Windows 实时字幕要用）")
    for label, tags in sr.items():
        print(f"  {label}: {', '.join(tags) if tags else '（无）'}")

    ok_ocr, ocr_tags, ocr_err = check_ocr_languages()
    print("\n【系统 OCR 语言】（把屏幕翻译提速到约 0.1 秒/次要用）")
    if ok_ocr:
        print(f"  可用: {', '.join(ocr_tags) if ocr_tags else '（无）'}")
    else:
        print(f"  查询失败: {ocr_err}")

    print("\n【模型目录】（辅助参考）")
    for d, names in check_engine_dirs().items():
        print(f"  {d}\n      {', '.join(names) if names else '（读不到或为空）'}")

    sr_tags = [t for tags in sr.values() for t in tags]
    print("\n" + "=" * 66)
    print("结论")
    print("=" * 66)
    for code, label in TARGETS.items():
        has_sr = any(t.lower().startswith(code) for t in sr_tags)
        has_ocr = any(t.lower().startswith(code) for t in ocr_tags)
        print(f"  {label:14s} 语音识别 {'已就绪' if has_sr else '未就绪'} ｜ "
              f"OCR {'已就绪' if has_ocr else '未就绪'}")

    ready = any(t.lower().startswith(c) for t in sr_tags + ocr_tags for c in TARGETS)
    added = any(l.lower().startswith(c) for c in TARGETS for l in langs)

    if ready:
        print("\n  已就绪。实时字幕：Win+Ctrl+L → 右上角齿轮 → 把语言改成对应语言。")
        print("  屏幕 OCR 提速已内置：界面「屏幕识别」保持「自动」即用系统 OCR（实测约 0.012 秒/帧）。")
    elif added and staged.get("OCR") and boot <= comp:
        print("\n  语言已添加、组件已下载，但还没重启过 —— **重启一次电脑**。")
        print(f"  依据：组件写入时间晚于上次开机（组件 {time.strftime('%m-%d %H:%M', time.localtime(comp))}"
              f" > 开机 {time.strftime('%m-%d %H:%M', time.localtime(boot))}）。")
        print("  重启后再跑一次本脚本。")
    elif added and staged.get("OCR"):
        stuck, age = stuck_transaction()
        if stuck and age > 0.5:
            print("\n  语言已添加、组件已下载、重启也试过了，但**仍然没生效**。")
            print(f"  实测原因：有一个卡住的部署事务（pending.xml 已存在 {age:.1f} 小时没被处理），")
            print("  CBS 日志里的错误是组件仓库故障：Error 800f0983 "
                  "originated in ComponentStore::CRawStoreLayout。")
            print("  这种状态下重启和 Add-WindowsCapability 都不会生效，要先修组件仓库。")
            print("  在**管理员 PowerShell** 里跑（10~40 分钟，会走 Windows Update 取修复源）：")
            print("      DISM /Online /Cleanup-Image /RestoreHealth")
            print("  完成后再跑：")
            print("      sfc /scannow")
            print("      Add-WindowsCapability -Online -Name 'Language.OCR~~~pt-BR~0.0.1.0'")
            print("      Add-WindowsCapability -Online -Name 'Language.Speech~~~pt-BR~0.0.1.0'")
            print("  然后重启。若 RestoreHealth 报 0x800f0954/0x800f0906（连不上更新源），")
            print("  需要挂一份同版本 ISO 当源：")
            print("      DISM /Online /Cleanup-Image /RestoreHealth /Source:X:\\sources\\install.wim /LimitAccess")
            print("  注意：**不要手工删 pending.xml**，那样可能弄坏服务栈。")
        else:
            print("\n  语言已添加、组件也已下载，但没生效 —— 需要补装成「已安装的功能」。")
            print("  在**管理员 PowerShell** 里跑：")
            print("      Add-WindowsCapability -Online -Name 'Language.OCR~~~pt-BR~0.0.1.0'")
            print("      Add-WindowsCapability -Online -Name 'Language.Speech~~~pt-BR~0.0.1.0'")
            print("  跑完重启，再回来跑一次本脚本。")
            print("  （先看状态：Get-WindowsCapability -Online | "
                  "Where-Object Name -like '*pt-BR*' | Select Name,State）")
    elif added:
        print("\n  语言已添加，但没有组件下载记录 —— OCR / 语音组件可能没勾选。")
        print("  设置 → 时间和语言 → 语言和区域 → 葡萄牙语(巴西) → ⋯ → 语言选项")
        print("  确认「语言包」和「增强的语音识别」都显示已安装，装完重启。")
    else:
        print("\n  还没装。装法：")
        print("    设置 → 时间和语言 → 语言和区域 → 添加语言 → 搜 Português (Brasil) → 下一步")
        print("    勾选：语言包 + 增强的语音识别；不要勾「设为我的显示语言」")
        print("    装完重启电脑，再跑一次本脚本确认。")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
