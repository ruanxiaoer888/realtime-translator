# -*- coding: utf-8 -*-
"""给「回复助手」页签抓一张真实截图（含真实翻译结果，不是假数据）。

运行（项目根目录）: python tools\\shoot_reply_shot.py
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

from PIL import Image  # noqa: E402

TITLE = "实时翻译助手 · Realtime Translator"
OUT = os.path.join(ROOT, "screenshot-reply.png")
user32 = ctypes.windll.user32


def window_rect(title, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            r = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(r)):
                w, h = r.right - r.left, r.bottom - r.top
                if w > 200 and h > 200:
                    return r.left, r.top, w, h
        time.sleep(0.3)
    return None


def main():
    import app as A

    a = A.App()
    state = {"shot": False}

    def prepare():
        # 切到「回复助手」页签
        for tab in a.root.winfo_children():
            if tab.winfo_class() == "TNotebook":
                tab.select(2)
        # 用预设跑一次真实翻译（输出框里是引擎真实返回的葡语）
        a.reply_preset(A.REPLY_PRESETS[3][1])       # 满2件包邮
        a.root.after(15000, shoot)

    def shoot():
        out = a.txt_reply_out.get("1.0", "end").strip()
        print(f"译文盒内容: {out[:80]!r}")
        if not out:
            print("没拿到译文，放弃")
            a.root.after(200, a.root.destroy)
            return
        a.root.update_idletasks()
        time.sleep(0.5)
        rect = window_rect(TITLE)
        if rect:
            left, top, w, h = rect
            inset = 8
            import mss
            with mss.mss() as sct:
                shot = sct.grab({"left": left + inset, "top": top,
                                 "width": w - inset * 2, "height": h - inset})
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            img.save(OUT)
            import numpy as np
            print(f"已保存 {OUT}  {img.size[0]}x{img.size[1]}  亮度均值 {np.asarray(img).mean():.1f}")
            state["shot"] = True
        a.root.after(200, a.root.destroy)

    a.root.after(800, prepare)
    a.root.mainloop()
    return 0 if state["shot"] else 1


if __name__ == "__main__":
    sys.exit(main())
