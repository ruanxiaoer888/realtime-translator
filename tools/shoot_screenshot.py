# -*- coding: utf-8 -*-
"""抓一张真实界面截图给 README 用。

启动 app.py -> 用 Win32 API 精确取到窗口矩形 -> 截图 -> 关闭程序。
运行（项目根目录）: python tools\\shoot_screenshot.py
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

from PIL import Image  # noqa: E402

TITLE = "实时翻译助手 · Realtime Translator"
OUT = os.path.join(ROOT, "screenshot.png")

user32 = ctypes.windll.user32


def window_rect(title: str, timeout: float = 20.0):
    """等窗口出现并返回它的屏幕矩形 (left, top, width, height)。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            r = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(r)):
                w, h = r.right - r.left, r.bottom - r.top
                if w > 200 and h > 200:
                    time.sleep(1.0)          # 让它画完
                    return r.left, r.top, w, h
        time.sleep(0.5)
    return None


def main():
    print("启动 app.py …")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "app.py")],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        rect = window_rect(TITLE)
        if rect is None:
            print("没找到窗口，放弃")
            return 1
        left, top, w, h = rect
        print(f"窗口矩形: {left},{top} {w}x{h}")
        # GetWindowRect 含 DWM 的隐形缩放边框（左右各约 8px），裁掉才是看得见的部分
        inset = 8
        left, top = left + inset, top
        w, h = w - inset * 2, h - inset
        print(f"实际截图区域: {left},{top} {w}x{h}")

        # 用 app 自己依赖的 mss 抓（和实时屏幕翻译同一条通路）
        import mss
        with mss.mss() as sct:
            shot = sct.grab({"left": left, "top": top, "width": w, "height": h})
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        img.save(OUT)
        import numpy as np
        a = np.asarray(img)
        print(f"已保存 {OUT}  {img.size[0]}x{img.size[1]}  亮度均值 {a.mean():.1f}")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        print("已关闭 app.py")


if __name__ == "__main__":
    sys.exit(main())
