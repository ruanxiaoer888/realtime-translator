# -*- coding: utf-8 -*-
"""两个新功能的验收：悬浮窗鼠标穿透 + 回复助手（中文→市场语言）。

运行（项目根目录）: python tmp\\verify_features.py
"""
from __future__ import annotations

import ctypes
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


WS_EX_TRANSPARENT = 0x00000020
GWL_EXSTYLE = -20


def transparent_bit(hwnd) -> bool:
    return bool(ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TRANSPARENT)


def main():
    import app as A
    import markets
    import translate_core

    # 干净起步
    sf = A.SETTINGS_FILE
    if os.path.exists(sf):
        os.remove(sf)

    print("=" * 78)
    print("1) 悬浮窗鼠标穿透")
    print("=" * 78)
    a = A.App()
    result = {}

    def step1():
        hwnds = a._overlay_hwnds()
        check("能拿到悬浮窗句柄", bool(hwnds), str(hwnds))
        check("初始未开穿透", not any(transparent_bit(h) for h in hwnds))
        a.var_clickthrough.set(True)
        a.apply_clickthrough()
        result["on"] = any(transparent_bit(h) for h in hwnds)
        check("开启后样式位确实设上了", result["on"], a.lbl_live.cget("text")[:40])
        a.var_clickthrough.set(False)
        a.apply_clickthrough()
        result["off"] = any(transparent_bit(h) for h in hwnds)
        check("关闭后样式位被清掉", not result["off"], a.lbl_live.cget("text")[:30])
        # 置顶仍然可用
        a.var_top.set(False)
        a.apply_top()
        check("置顶开关仍正常", a.overlay.attributes("-topmost") in (0, False))
        a.var_top.set(True)
        a.apply_top()
        a.root.destroy()

    a.root.after(700, step1)
    a.root.mainloop()

    print()
    print("=" * 78)
    print("2) 回复助手")
    print("=" * 78)

    # 2a 术语预替换（离线可测）
    rev = markets.get_reverse_glossary("五金工具", "pt")
    check("反向术语表可用", rev.get("电动螺丝刀") == "parafusadeira",
          f"电动螺丝刀->{rev.get('电动螺丝刀')}  工具箱->{rev.get('工具箱')}")
    sub = translate_core.presubstitute_terms("这把电动螺丝刀配一个工具箱", rev)
    check("预替换把中文术语换成葡语", "parafusadeira" in sub and "maleta" in sub, sub)
    rev_es = markets.get_reverse_glossary("五金工具", "es")
    check("西语反向术语表可用", bool(rev_es.get("电动螺丝刀")), f"电动螺丝刀->{rev_es.get('电动螺丝刀')}")

    # 2b 界面 + 端到端翻译
    b = A.App()
    out = {}

    def step2():
        out["方向标签"] = b.lbl_reply_dir.cget("text")
        out["预设数"] = len(A.REPLY_PRESETS)
        check("方向标签指向市场语言", "葡萄牙语" in out["方向标签"], out["方向标签"])
        check("预设回复已就位", out["预设数"] >= 6, f"{out['预设数']} 条")
        # 用第 2 条预设（7天可退换）跑一次真实翻译
        b.reply_preset(A.REPLY_PRESETS[1][1])
        b.root.after(16000, step3)

    def step3():
        out["译文"] = b.txt_reply_out.get("1.0", "end").strip()
        out["状态"] = b.lbl_reply.cget("text")
        check("预设回复翻译出结果", bool(out["译文"]), out["译文"][:70])
        check("译文是葡语（含退换相关词）",
              any(w in out["译文"].lower() for w in ("devolv", "troc", "satisfeit", "prazo")),
              out["状态"])
        # 复制到剪贴板
        b.reply_copy()
        check("复制按钮可用", "已复制" in b.lbl_reply.cget("text"), b.lbl_reply.cget("text"))
        # 切市场后方向标签跟着变
        b.var_market.set("墨西哥")
        b.apply_market()
        out["墨西哥方向"] = b.lbl_reply_dir.cget("text")
        check("切市场后方向标签跟随", "西班牙语" in out["墨西哥方向"], out["墨西哥方向"])
        # 穿透设置被持久化
        b.var_clickthrough.set(True)
        b.on_close()

    b.root.after(700, step2)
    b.root.mainloop()

    print()
    print("=" * 78)
    print("3) 设置持久化")
    print("=" * 78)
    import json
    saved = json.load(open(sf, encoding="utf-8"))
    check("settings.json 记下了穿透开关", saved.get("clickthrough") is True, str(saved.get("clickthrough")))
    check("settings.json 记下了市场", saved.get("market") == "墨西哥", str(saved.get("market")))
    c = A.App()
    r2 = {}

    def step4():
        r2["穿透"] = c.var_clickthrough.get()
        r2["市场"] = c.var_market.get()
        c.root.destroy()

    c.root.after(700, step4)
    c.root.mainloop()
    check("重启后恢复穿透开关", r2["穿透"] is True, str(r2["穿透"]))
    check("重启后恢复市场", r2["市场"] == "墨西哥", str(r2["市场"]))

    print()
    print("=" * 78)
    print(f"结果: 通过 {len(PASS)} 项, 失败 {len(FAIL)} 项")
    for f in FAIL:
        print(f"  - {f}")
    print("=" * 78)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
