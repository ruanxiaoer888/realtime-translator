# -*- coding: utf-8 -*-
"""两个新功能的验收：悬浮窗鼠标穿透 + 回复助手（中文→市场语言）。

运行（项目根目录）: python tools\\verify_features.py
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
    import shutil

    import app as A
    import markets
    import translate_core

    # 干净起步，但**先备份用户的设置**：本脚本会用测试值覆盖并保存 settings.json
    # （第 2b 步把市场设成"墨西哥"再 on_close()），跑完必须还原 ——
    # 否则跑一次自检，用户的真实配置就被测试值顶掉了。真实踩到过：
    # 用户做的是巴西，settings.json 里却是"墨西哥"，就是这儿写进去的。
    sf = A.SETTINGS_FILE
    backup = sf + ".verify-backup"
    had_settings = os.path.exists(sf)
    if had_settings:
        shutil.copy2(sf, backup)
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
        # 置顶：两个独立开关，而且 show_overlay() 不能把它硬编码回 True。
        # 真实踩到的 bug：show_overlay() 里写死 -topmost True，
        # 于是取消勾选后一按「开始」悬浮窗又被强制置顶 —— 用户报的"勾了没反应"。
        a.var_top.set(False)
        a.apply_top()
        check("取消「悬浮窗置顶」后确实不置顶",
              not bool(a.overlay.attributes("-topmost")),
              str(a.overlay.attributes("-topmost")))
        a.show_overlay()
        a.root.update()
        check("show_overlay() 尊重取消勾选（曾硬编码 True）",
              not bool(a.overlay.attributes("-topmost")),
              str(a.overlay.attributes("-topmost")))
        a.var_top.set(True)
        a.apply_top()
        check("重新勾选后恢复置顶",
              bool(a.overlay.attributes("-topmost")),
              str(a.overlay.attributes("-topmost")))

        # 主窗口置顶必须是独立开关，不能被「悬浮窗置顶」连坐
        a.var_top_main.set(True)
        a.apply_top()
        check("「主窗口置顶」可独立开启",
              bool(a.root.attributes("-topmost")), str(a.root.attributes("-topmost")))
        a.var_top_main.set(False)
        a.apply_top()
        check("「主窗口置顶」可独立关闭（悬浮窗仍置顶）",
              not bool(a.root.attributes("-topmost")) and bool(a.overlay.attributes("-topmost")),
              f"root={a.root.attributes('-topmost')} overlay={a.overlay.attributes('-topmost')}")

        # 位置微调：鼠标穿透开着时悬浮窗收不到鼠标事件、拖不动，
        # 所以主窗口这套按钮是唯一能挪它的途径，必须真的能挪。
        a.overlay.deiconify()
        a.overlay_pos = (200, 300)
        a.overlay.geometry(f"{A.OVERLAY_W}x{A.OVERLAY_H}+200+300")
        a.root.update()

        a.nudge_overlay(-24, 0)
        a.root.update()
        check("◀ 让悬浮窗左移 24px",
              (a.overlay.winfo_x(), a.overlay.winfo_y()) == (176, 300),
              f"({a.overlay.winfo_x()}, {a.overlay.winfo_y()})")

        a.nudge_overlay(0, 24)
        a.root.update()
        check("▼ 让悬浮窗下移 24px",
              (a.overlay.winfo_x(), a.overlay.winfo_y()) == (176, 324),
              f"({a.overlay.winfo_x()}, {a.overlay.winfo_y()})")

        a.center_overlay()
        a.root.update()
        want_x = (a.root.winfo_screenwidth() - A.OVERLAY_W) // 2
        check("居中把悬浮窗放到屏幕水平中间",
              abs(a.overlay.winfo_x() - want_x) <= 2,
              f"x={a.overlay.winfo_x()} 期望≈{want_x}")

        check("位置标签跟着更新", "," in a.lbl_overlay_pos.cget("text"),
              a.lbl_overlay_pos.cget("text"))

        # 位置微调那一行不能撑出主窗口（撑出去控件会被裁掉，用户根本看不到）
        need = a.lbl_overlay_pos.master.winfo_reqwidth()
        check("位置微调行没超出窗口宽度", need <= 860, f"需要 {need}px / 窗口 880px")

        # 直接鼠标拖动：必须**整棵控件树**都能拖。
        # 真实踩过的坑：原来只绑了 header/lbl_overlay/wrap，而标题栏文字是 header
        # 里的一个 Label 且铺满 header —— 抓标题栏拖动完全没反应（位移 0,0）。
        for name, w, start in (("标题栏", a.lbl_overlay_hdr, (40, 8)),
                               ("正文", a.lbl_overlay, (60, 30)),
                               ("外框", a.lbl_overlay.master, (5, 5))):
            a.overlay.geometry("+400+400")
            a.root.update()
            w.event_generate("<Button-1>", x=start[0], y=start[1])
            w.event_generate("<B1-Motion>", x=start[0] + 30, y=start[1] + 25)
            a.root.update()
            got = (a.overlay.winfo_x() - 400, a.overlay.winfo_y() - 400)
            check(f"鼠标拖动悬浮窗（{name}）位移精确", got == (30, 25), f"拖 (30,25) 得到 {got}")

        # 拖不动的状态必须看得见，否则用户只会觉得"坏了"
        a.var_clickthrough.set(True)
        a.apply_clickthrough()
        check("穿透开启时悬浮窗上有可见提示",
              "穿透" in a.lbl_ct.cget("text"), a.lbl_ct.cget("text")[:36])
        a.var_clickthrough.set(False)
        a.apply_clickthrough()
        check("关闭穿透后提示消失", a.lbl_ct.cget("text") == "", repr(a.lbl_ct.cget("text")))

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
        b.overlay_pos = (321, 432)
        b.var_clickthrough.set(True)
        b.var_top.set(False)          # 悬浮窗不置顶
        b.var_top_main.set(True)      # 主窗口置顶
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
    check("settings.json 记下了悬浮窗位置",
          (saved.get("overlay_x"), saved.get("overlay_y")) == (321, 432),
          f"{saved.get('overlay_x')}, {saved.get('overlay_y')}")
    check("settings.json 记下了悬浮窗置顶", saved.get("topmost") is False, str(saved.get("topmost")))
    check("settings.json 记下了主窗口置顶", saved.get("topmost_main") is True, str(saved.get("topmost_main")))
    c = A.App()
    r2 = {}

    def step4():
        r2["穿透"] = c.var_clickthrough.get()
        r2["市场"] = c.var_market.get()
        r2["悬浮窗位置"] = (c.overlay.winfo_x(), c.overlay.winfo_y())
        r2["悬浮窗置顶"] = c.var_top.get()
        r2["主窗口置顶"] = c.var_top_main.get()
        r2["悬浮窗实际"] = bool(c.overlay.attributes("-topmost"))
        r2["主窗口实际"] = bool(c.root.attributes("-topmost"))
        c.root.destroy()

    c.root.after(700, step4)
    c.root.mainloop()
    check("重启后恢复穿透开关", r2["穿透"] is True, str(r2["穿透"]))
    check("重启后恢复市场", r2["市场"] == "墨西哥", str(r2["市场"]))
    check("重启后悬浮窗回到原位置", r2["悬浮窗位置"] == (321, 432), str(r2["悬浮窗位置"]))
    check("重启后悬浮窗置顶设置恢复", r2["悬浮窗置顶"] is False, str(r2["悬浮窗置顶"]))
    check("重启后主窗口置顶设置恢复", r2["主窗口置顶"] is True, str(r2["主窗口置顶"]))
    check("重启后置顶真的作用到窗口上（启动时曾漏调 apply_top）",
          r2["悬浮窗实际"] is False and r2["主窗口实际"] is True,
          f"overlay={r2['悬浮窗实际']} root={r2['主窗口实际']}")

    # 还原用户原来的 settings.json（跑自检不该动用户的配置）
    try:
        if had_settings and os.path.exists(backup):
            shutil.copy2(backup, sf)
            os.remove(backup)
        elif os.path.exists(sf):
            os.remove(sf)
    except Exception as e:  # noqa: BLE001
        print(f"  [WARN] 还原 settings.json 失败：{e}")

    print()
    print("=" * 78)
    print(f"结果: 通过 {len(PASS)} 项, 失败 {len(FAIL)} 项")
    for f in FAIL:
        print(f"  - {f}")
    print("=" * 78)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
