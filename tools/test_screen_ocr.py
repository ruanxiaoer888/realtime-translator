# -*- coding: utf-8 -*-
"""端到端验证：在屏幕上显示一张葡语图 -> 用真实抓屏管线 OCR -> 翻译。

用法: python tools/test_screen_ocr.py
"""
import os
import sys
import time
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

import screen_translate as st  # noqa: E402
from translate_core import translate  # noqa: E402

IMG = os.path.join(ROOT, "tmp", "teste_pt.png")

win = tk.Tk()
win.title("OCR TEST")
win.geometry("1000x420+400+300")
win.attributes("-topmost", True)
pic = tk.PhotoImage(file=IMG)
tk.Label(win, image=pic, borderwidth=0).pack()
win.update()
win.after(300, lambda: None)
win.update_idletasks()
time.sleep(0.8)


def run():
    region = (400, 300, 1000, 420)
    t0 = time.time()
    text, items = st.ocr_region(region)
    dt = time.time() - t0
    print(f"抓屏+OCR 耗时: {dt:.2f}s")
    print("识别原文:", text)
    for t, s in items:
        print(f"   {s:.2f}  {t}")
    zh = translate(text)
    print("中文翻译:", zh)
    win.destroy()


win.after(600, run)
win.mainloop()
