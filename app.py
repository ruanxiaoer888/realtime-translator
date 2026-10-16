# -*- coding: utf-8 -*-
"""实时翻译助手 · Realtime Translator

一个窗口两件事（语言由顶部"市场"决定，随便切）：
  [实时屏幕翻译]  框选一块屏幕区域 -> 持续自动 OCR -> 悬浮窗实时显示译文
                  （主打：框一次就完事，不用反复截图；评论/标题/字段/弹窗都适用）
  [直播同传字幕]  抓系统声音 -> Whisper 识别 -> 实时翻译 + 自动写 srt

用法:
    python app.py
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

ROOT = os.path.dirname(os.path.abspath(__file__))
# 注意顺序：必须先把 libs/ 加进搜索路径，再导入任何第三方包（numpy 等）。
# 这个目录是要整体拷到别的电脑用的，那边可能没有装 numpy/requests，
# 全靠 libs/ 提供；顺序写反了就会在第一行 import 就崩。
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

# 换电脑最容易踩的两个坑，提前给中文提示，别让用户看一堆英文报错
if sys.version_info[:2] != (3, 12):
    raise SystemExit(
        f"Python 版本不对：当前 {sys.version.split()[0]}，本工具需要 64 位 Python 3.12。\n"
        "libs/ 里的组件是按 3.12（cp312）编译的，换版本会加载失败。\n"
        "下载地址：https://www.python.org/downloads/release/python-3129/（选 Windows installer 64-bit）"
    )
try:
    import numpy  # noqa: F401
except ImportError:
    raise SystemExit(
        "依赖缺失：找不到 numpy。\n"
        "多半是整个文件夹没拷全 —— libs 子目录必须一起拷过去。\n"
        "如果 libs 在但确实缺包，在本目录运行：python fetch_wheels.py --core"
    )

from translate_core import translate, close as close_cache, fix_source  # noqa: E402
import screen_translate as st  # noqa: E402
import markets  # noqa: E402

LOG_DIR = os.path.join(ROOT, "记录")
os.makedirs(LOG_DIR, exist_ok=True)

# 界面上的「翻译引擎」选项 → translate_core 的内部模式。
# 默认是"仅在线接口"：本地兜底模型 NLLB 是禁止商用许可，不做默认（详见 _default_engine）。
ENGINE_MODES = {
    "仅在线接口": "api",
    "在线优先 + 本地兜底": "auto",
    "仅本地模型": "nllb",
}

# 记住上次的选择（含引擎、市场、品类、目标语言、模型、框选区域等）
SETTINGS_FILE = os.path.join(ROOT, "settings.json")
SETTINGS_KEYS = ("market", "category", "target", "model", "engine",
                 "interval", "font", "topmost", "clickthrough", "region",
                 "chunk", "pause", "ocr", "overlay_x", "overlay_y", "topmost_main")

# 悬浮窗默认尺寸与落点（右下角上方，避开常见直播画面）
OVERLAY_W, OVERLAY_H = 760, 150
OVERLAY_FALLBACK = (120, 780)

# 屏幕识别引擎（界面显示名 -> screen_translate 的取值）
OCR_MODES = {
    "自动（推荐）": "auto",
    "系统 OCR（快）": "win",
    "本地模型（准）": "latin",
}

# 「回复助手」的常用回复。中文说法是**调过的** —— 有些中文读法会让引擎译歪，
# 例如「支持七天无理由退换」会译成 "Apoie sete dias..."（把"支持"当"拥护"），
# 换成「收到货7天内不满意可以退换」就译得对。这些说法都是实测过的。
REPLY_PRESETS = [
    ("有货·今天发", "库存充足，现在下单今天就发货"),
    ("7天可退换", "收到货7天内不满意可以退换"),
    ("新款质量更好", "这是最新款，质量比上一代更好"),
    ("满2件包邮", "满两件包邮，点下方黄色购物车下单"),
    ("点黄色购物车", "点击下方黄色购物车就能下单"),
    ("谢谢支持", "谢谢支持，有问题随时留言"),
]


class RegionSelector:
    """全屏半透明遮罩，拖拽选择区域。

    必须保证「选中」和「取消」**一定有一个会回调**：框选前主窗口已经 withdraw()，
    只要漏了回调，主窗口就永远藏在后台，用户会以为程序消失了。
    原来按 Esc、或拖得小于 8 像素，两条路都只 destroy() 不回调 —— 实测踩到。
    """

    def __init__(self, parent, callback, on_cancel=None):
        self.callback = callback
        self.on_cancel = on_cancel
        self._done = False
        self.win = tk.Toplevel(parent)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-alpha", 0.25)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black")
        self.win.config(cursor="crosshair")
        self.canvas = tk.Canvas(self.win, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            self.win.winfo_screenwidth() // 2, 40,
            text="按住鼠标左键拖拽框选要翻译的区域，松开即完成。按 Esc 取消。",
            fill="#00ff88", font=("Microsoft YaHei UI", 20), tags="hint",
        )
        self.start = None
        self.rect = None
        self.win.bind("<ButtonPress-1>", self.on_press)
        self.win.bind("<B1-Motion>", self.on_drag)
        self.win.bind("<ButtonRelease-1>", self.on_release)
        self.win.bind("<Escape>", self.cancel)

    def cancel(self, _evt=None):
        """取消框选（Esc / 拖得太小 / 关掉遮罩）：关掉遮罩并把主窗口还回来。"""
        if self._done:
            return
        self._done = True
        try:
            self.win.destroy()
        except Exception:
            pass
        if self.on_cancel:
            self.on_cancel()

    def on_press(self, e):
        self.start = (e.x_root, e.y_root)
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#00ff88", width=2)

    def on_drag(self, e):
        if not self.start:
            return
        x0, y0 = self.start
        self.canvas.delete("hint")
        self.canvas.coords(self.rect, x0, y0, e.x_root, e.y_root)

    def on_release(self, e):
        if not self.start:
            return
        x0, y0 = self.start
        x1, y1 = e.x_root, e.y_root
        region = (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
        if region[2] <= 8 or region[3] <= 8:
            self.cancel()        # 误点/拖得太小 = 当作取消，别让主窗口卡在隐藏状态
            return
        if self._done:
            return
        self._done = True
        self.win.destroy()
        self.callback(region)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("实时翻译助手 · Realtime Translator")
        self.root.geometry("880x640+80+60")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1f26")

        self.ui_queue: queue.Queue = queue.Queue()
        self.region = None
        self.overlay_pos = None            # (x, y)，None = 用默认落点
        self.screen_running = False
        self.screen_thread = None
        self.last_text = ""
        self.subs: list[tuple[float, str, str, float]] = []   # (时间, 原文, 中文, 音频时长)
        self.t0 = time.time()
        self.recorder = None
        self.live_running = False
        self.live_thread = None
        # 识别 + 翻译放到后台线程，录制循环不再被阻塞。
        # 2026-10 真实直播实测：单线程时每句积压 3 秒以上（识别固定耗时），
        # 而且只增不减 —— 8 分钟一场下来延迟累积到 100 秒以上。
        self._caption_q = None
        self._caption_worker = None
        self._subs_lock = threading.Lock()
        self._live_log_fp = None
        # 本场直播的 srt 文件名（开始听译时按时间生成）。
        # 原来固定写 记录\直播字幕.srt，第二场会把第一场的字幕直接覆盖掉。
        self._srt_path = None

        self._build_ui()
        # 当前语言配置（由市场决定；换市场就重算）
        self.src_locale = "pt-BR"
        self.whisper_lang = "pt"
        self.tgt_code = "zh-CN"
        self.load_settings()          # 先恢复上次的选择，再让市场/品类生效
        import translate_core
        translate_core.set_engine(ENGINE_MODES.get(self.var_engine.get(), "api"))
        self.apply_market()
        self.apply_top()                     # 让保存的置顶设置真正生效（以前漏了这一步）
        if self.var_clickthrough.get():      # 上次开着穿透，启动时恢复
            self.root.after(600, self.apply_clickthrough)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._closing = False
        self._pump_id = self.root.after(120, self.pump)

    # ---------------- 设置记忆 ----------------
    def load_settings(self):
        """恢复上次的选择（市场/品类/目标语言/模型/引擎/区域等）。文件不存在就跳过。"""
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            return
        try:
            if s.get("market") in markets.market_names():
                self.var_market.set(s["market"])
            if s.get("category") in markets.category_names():
                self.var_category.set(s["category"])
            if s.get("target") in markets.TARGET_LANGS:
                self.var_target.set(s["target"])
            if s.get("model") in ("base", "small", "medium", "large-v3"):
                self.var_model.set(s["model"])
            if s.get("engine") in ENGINE_MODES:
                self.var_engine.set(s["engine"])
            if isinstance(s.get("interval"), (int, float)):
                self.var_interval.set(max(0.2, min(5.0, float(s["interval"]))))
            if isinstance(s.get("chunk"), (int, float)):
                self.var_chunk.set(max(0.8, min(6.0, float(s["chunk"]))))
            if isinstance(s.get("pause"), (int, float)):
                self.var_pause.set(max(0.25, min(1.5, float(s["pause"]))))
            if s.get("ocr") in OCR_MODES.values():
                self.var_ocr.set(s["ocr"])
            if isinstance(s.get("font"), int):
                self.var_font.set(max(10, min(60, int(s["font"]))))
            if isinstance(s.get("topmost"), bool):
                self.var_top.set(s["topmost"])
            if isinstance(s.get("topmost_main"), bool):
                self.var_top_main.set(s["topmost_main"])
            if isinstance(s.get("clickthrough"), bool):
                self.var_clickthrough.set(s["clickthrough"])
            ox, oy = s.get("overlay_x"), s.get("overlay_y")
            if isinstance(ox, int) and isinstance(oy, int):
                self.overlay_pos = (ox, oy)
                # _build_overlay 是在本方法之前跑的，那时还不知道位置，
                # 所以这里要把它挪过去，光记属性不够。
                try:
                    self.overlay.geometry(f"+{ox}+{oy}")
                except Exception:
                    pass
            r = s.get("region")
            if (isinstance(r, list) and len(r) == 4
                    and all(isinstance(x, int) for x in r) and r[2] > 8 and r[3] > 8):
                self.region = tuple(r)
                self.lbl_region.config(text=f"区域 {r[0]},{r[1]}  {r[2]}x{r[3]}（上次的）")
        except Exception:
            pass

    def save_settings(self):
        data = {
            "market": self.var_market.get(),
            "category": self.var_category.get(),
            "target": self.var_target.get(),
            "model": self.var_model.get(),
            "engine": self.var_engine.get(),
            "interval": float(self.var_interval.get()),
            "chunk": float(self.var_chunk.get()),
            "pause": float(self.var_pause.get()),
            "ocr": self.var_ocr.get(),
            "font": int(self.var_font.get()),
            "topmost": bool(self.var_top.get()),
            "topmost_main": bool(self.var_top_main.get()),
            "clickthrough": bool(self.var_clickthrough.get()),
            "region": list(self.region) if self.region else None,
        }
        # 悬浮窗位置单独取（它记在实例属性上，不在界面的 Var 里）
        try:
            x, y = self.overlay_pos if self.overlay_pos else (
                self.overlay.winfo_x(), self.overlay.winfo_y())
            data["overlay_x"], data["overlay_y"] = int(x), int(y)
        except Exception:
            pass
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------------- 市场 / 品类 ----------------
    def apply_market(self):
        """把当前市场与品类同步到识别引擎、翻译层和界面提示。"""
        import asr_engine
        market = markets.get_market(self.var_market.get())
        target = markets.TARGET_LANGS.get(self.var_target.get(), "zh-CN")

        if self.var_market.get() == "自定义":
            # 自定义：沿用当前语言，只换目标语言
            wl = self.whisper_lang or "en"
            locale = self.src_locale or "en-US"
            prompt = ""
        else:
            wl = market["whisper"]
            locale = market["locale"]
            # 按**当前品类**拼提示词，不要用市场级那一坨（四个品类的词混在一起，
            # 卖五金时提示词里却带着 moto/carro/academia，会把识别带偏）
            prompt = markets.get_asr_prompt(self.var_category.get(), wl)

        glossary = markets.get_glossary(self.var_category.get(), wl)
        asr_engine.set_terminology(prompt=prompt, glossary=glossary)
        # 屏幕识别也按市场走：pt-BR 用葡语识别器、es-MX 用西语识别器
        st.set_ocr_locale(locale)
        self.whisper_lang = wl
        self.src_locale = locale
        self.tgt_code = target

        self.lbl_market.config(
            text=f"识别：{markets.WHISPER_LANGS.get(wl, wl)} ｜ 术语：{self.var_category.get()}"
                 f"（{len(glossary)} 条）｜ 译成：{self.var_target.get()}"
        )
        # 这几个标题跟市场走，别写死"葡萄牙语 / 中文翻译"
        self.lbl_src_hdr.config(text=f"识别的原文（{markets.WHISPER_LANGS.get(wl, wl)}）")
        dst_name = self.var_target.get() or "中文"
        for lbl in getattr(self, "_dst_headers", []):
            lbl.config(text=f"{dst_name}翻译（同步显示在悬浮窗）")
        if getattr(self, "lbl_overlay_hdr", None) is not None:
            self.lbl_overlay_hdr.config(text=f" {dst_name}翻译 ")
        if getattr(self, "lbl_reply_dir", None) is not None:
            lang_name = markets.WHISPER_LANGS.get(wl, wl)
            # 回复助手是反方向：中文 -> 市场语言（不是顶部的"翻译成"）
            self.lbl_reply_dir.config(text=f"中文 → {lang_name}（{self.var_market.get()}）")
            self.lbl_reply_out.config(text=f"{lang_name}译文")

    def on_market_change(self, _evt=None):
        import translate_core
        self.apply_market()
        translate_core.clear_cache()          # 换语言后旧译文不能复用
        self.lbl_live.config(text=f"已切换市场：{self.var_market.get()}",
                             foreground="#7ee787")

    def on_category_change(self, _evt=None):
        import translate_core
        self.apply_market()
        translate_core.clear_cache()
        self.lbl_live.config(text=f"已切换品类：{self.var_category.get()}",
                             foreground="#7ee787")

    def on_target_change(self, _evt=None):
        import translate_core
        self.apply_market()
        translate_core.clear_cache()
        self.lbl_live.config(text=f"已切换目标语言：{self.var_target.get()}",
                             foreground="#7ee787")

    def _tr(self, text):
        """按当前市场语言翻译。"""
        return translate(text, src=self.src_locale, dst=self.tgt_code)

    TR_FAIL_HINT = ("翻译失败：在线接口都不通（或被网络限制）。"
                    "可在「翻译引擎」里切到「在线优先 + 本地兜底」或「仅本地模型」")

    def _tr_fail(self):
        self.ui_queue.put(("error", self.TR_FAIL_HINT))

    # ---------------- 回复助手（中文 -> 市场语言） ----------------
    def _reply_target(self) -> tuple[str, str]:
        """返回 (目标语言 locale, 显示名)。"""
        name = self.var_market.get()
        if name == "自定义" or not self.src_locale:
            return (self.src_locale or "en-US"), (name or "自定义")
        return self.src_locale, name

    def reply_preset(self, text: str):
        self.txt_reply_in.delete("1.0", "end")
        self.txt_reply_in.insert("1.0", text)
        self.reply_translate()

    def reply_clear(self):
        self.txt_reply_in.delete("1.0", "end")
        self.txt_reply_out.delete("1.0", "end")
        self.lbl_reply.config(text="")

    def reply_copy(self):
        out = self.txt_reply_out.get("1.0", "end").strip()
        if not out:
            self.lbl_reply.config(text="还没译文", foreground="#ffd166")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(out)
        self.lbl_reply.config(text="已复制，粘到 TikTok 评论框即可", foreground="#7ee787")

    def reply_translate(self, _evt=None):
        import translate_core
        text = self.txt_reply_in.get("1.0", "end").strip()
        if not text:
            self.lbl_reply.config(text="先输入中文", foreground="#ffd166")
            return
        dst, name = self._reply_target()
        # 术语预替换：把中文术语先换成目标语言的正确说法，引擎才会沿用（见 translate_core）
        rev = markets.get_reverse_glossary(self.var_category.get(), self.whisper_lang)
        text = translate_core.presubstitute_terms(text, rev)
        self.lbl_reply.config(text=f"翻译中…（{name}）", foreground="#ffd166")

        def work():
            try:
                out = translate(text, src="zh-CN", dst=dst)
            except Exception as e:
                self.ui_queue.put(("reply", "", f"出错：{e}"))
                return
            self.ui_queue.put(("reply", out or "", ""))

        threading.Thread(target=work, daemon=True).start()

    # ---------------- UI ----------------
    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#1e1f26")
        style.configure("TFrame", background="#1e1f26")
        style.configure("TLabel", background="#1e1f26", foreground="#e8e8ef")
        style.configure("TCheckbutton", background="#1e1f26", foreground="#e8e8ef")
        style.configure("TButton", padding=6)
        style.configure("Header.TLabel", font=("Microsoft YaHei UI", 13, "bold"), foreground="#00d1ff")

        # ---- 顶部：市场 / 品类 / 目标语言 ----
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=(8, 0))

        ttk.Label(top, text="市场", style="Header.TLabel").pack(side="left")
        self.var_market = tk.StringVar(value="巴西")
        cb_market = ttk.Combobox(top, textvariable=self.var_market, values=markets.market_names(),
                                 width=7, state="readonly")
        cb_market.pack(side="left", padx=(4, 12))
        cb_market.bind("<<ComboboxSelected>>", self.on_market_change)

        ttk.Label(top, text="品类").pack(side="left")
        self.var_category = tk.StringVar(value="五金工具")
        cb_cat = ttk.Combobox(top, textvariable=self.var_category, values=markets.category_names(),
                              width=10, state="readonly")
        cb_cat.pack(side="left", padx=(4, 12))
        cb_cat.bind("<<ComboboxSelected>>", self.on_category_change)

        ttk.Label(top, text="翻译成").pack(side="left")
        self.var_target = tk.StringVar(value="中文")
        cb_tgt = ttk.Combobox(top, textvariable=self.var_target, values=list(markets.TARGET_LANGS),
                              width=8, state="readonly")
        cb_tgt.pack(side="left", padx=(4, 12))
        cb_tgt.bind("<<ComboboxSelected>>", self.on_target_change)

        self.lbl_market = ttk.Label(top, text="", foreground="#7ee787")
        self.lbl_market.pack(side="left", padx=6)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        # ---- 实时屏幕翻译 ----
        f1 = ttk.Frame(nb)
        nb.add(f1, text="  实时屏幕翻译  ")

        bar = ttk.Frame(f1)
        bar.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Button(bar, text="① 框选区域", command=self.pick_region).pack(side="left")
        self.lbl_region = ttk.Label(bar, text="未选择区域")
        self.lbl_region.pack(side="left", padx=10)
        ttk.Button(bar, text="② 开始", command=self.start_screen).pack(side="left", padx=4)
        ttk.Button(bar, text="停止", command=self.stop_screen).pack(side="left")

        ttk.Label(
            f1,
            text="框一次，之后这块区域里的文字会持续自动翻成中文，不用反复截图。"
                 "直播评论、商品标题、后台字段、弹窗、别的 App 界面都能盯。框得越小越快。",
            foreground="#8f93a8", wraplength=820, justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 6))

        opt = ttk.Frame(f1)
        opt.pack(fill="x", padx=10, pady=4)
        ttk.Label(opt, text="刷新间隔(秒)").pack(side="left")
        self.var_interval = tk.DoubleVar(value=0.4)
        ttk.Spinbox(opt, from_=0.2, to=5.0, increment=0.1, width=5, textvariable=self.var_interval).pack(side="left", padx=(4, 14))
        # 屏幕识别引擎：系统自带 OCR 实测约 14 毫秒/帧（本地模型约 1.3 秒），
        # 但要先装对应语言包；没装就自动退回本地模型。
        ttk.Label(opt, text="屏幕识别").pack(side="left")
        self.var_ocr = tk.StringVar(value=OCR_MODES["自动（推荐）"])
        ttk.Combobox(opt, textvariable=self.var_ocr, values=list(OCR_MODES.keys()),
                     width=14, state="readonly").pack(side="left", padx=(4, 14))
        ttk.Label(opt, text="字号").pack(side="left")
        self.var_font = tk.IntVar(value=22)
        ttk.Spinbox(opt, from_=10, to=60, width=5, textvariable=self.var_font).pack(side="left", padx=(4, 14))
        self.var_top = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="悬浮窗置顶", variable=self.var_top, command=self.apply_top).pack(side="left", padx=(0, 10))
        # 主窗口置顶是**独立**开关。原来一个勾同时管两个窗口，但标签只写「悬浮窗置顶」，
        # 用户勾/取消时主窗口跟着变，根本看不出是哪个生效了。
        # 默认关：直播时主窗口常年压在最上层很挡事，需要时能 Alt+Tab / 点任务栏叫回来。
        self.var_top_main = tk.BooleanVar(value=False)
        self.var_clickthrough = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="鼠标穿透", variable=self.var_clickthrough,
                        command=self.apply_clickthrough).pack(side="left", padx=(0, 14))
        ttk.Button(opt, text="翻译记录另存", command=self.save_log).pack(side="right")

        # 悬浮窗位置微调 + 位置记忆。
        # 为什么要有这一行：开了「鼠标穿透」之后悬浮窗收不到任何鼠标事件
        # （WS_EX_TRANSPARENT 会把点击整个透过去），连它自己的 ✕ 和拖动都点不到，
        # 于是窗口就"钉"在那儿挪不了了。这里给一套不依赖点击悬浮窗的移动方式。
        pos = ttk.Frame(f1)
        pos.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Label(pos, text="悬浮窗位置").pack(side="left")
        for txt, dx, dy in (("◀", -24, 0), ("▲", 0, -24), ("▼", 0, 24), ("▶", 24, 0)):
            ttk.Button(pos, text=txt, width=2,
                       command=lambda a=dx, b=dy: self.nudge_overlay(a, b)
                       ).pack(side="left", padx=1)
        ttk.Button(pos, text="居中", command=self.center_overlay).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(pos, text="主窗口置顶", variable=self.var_top_main,
                        command=self.apply_top).pack(side="left", padx=(10, 0))
        self.lbl_overlay_pos = ttk.Label(pos, text="", foreground="#8f93a8")
        self.lbl_overlay_pos.pack(side="left", padx=10)
        ttk.Label(pos, text="（穿透开着也能挪；位置会记住）",
                  foreground="#6f7385").pack(side="left")

        self.lbl_src_hdr = ttk.Label(f1, text="识别的原文", style="Header.TLabel")
        self.lbl_src_hdr.pack(anchor="w", padx=10, pady=(10, 2))
        self.txt_src = tk.Text(f1, height=5, bg="#15161c", fg="#9fd3ff", insertbackground="#fff",
                               font=("Consolas", 12), wrap="word", relief="flat")
        self.txt_src.pack(fill="x", padx=10)

        self.lbl_dst_hdr = ttk.Label(f1, text="译文（同步显示在悬浮窗）", style="Header.TLabel")
        self.lbl_dst_hdr.pack(anchor="w", padx=10, pady=(12, 2))
        self._dst_headers = [self.lbl_dst_hdr]
        self.txt_dst = tk.Text(f1, height=10, bg="#15161c", fg="#00ff9d", insertbackground="#fff",
                               font=("Microsoft YaHei UI", 16), wrap="word", relief="flat")
        self.txt_dst.pack(fill="both", expand=True, padx=10, pady=(0, 12))

        # ---- 直播同传 ----
        f2 = ttk.Frame(nb)
        nb.add(f2, text="  直播同传字幕  ")

        bar2 = ttk.Frame(f2)
        bar2.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(bar2, text="开始听译", command=self.start_live).pack(side="left")
        ttk.Button(bar2, text="停止", command=self.stop_live).pack(side="left", padx=6)
        ttk.Label(bar2, text="识别模型").pack(side="left", padx=(14, 4))
        self.var_model = tk.StringVar(value="small")
        ttk.Combobox(bar2, textvariable=self.var_model, values=["base", "small", "medium", "large-v3"],
                     width=9, state="readonly").pack(side="left")
        ttk.Label(bar2, text="每句最短(秒)").pack(side="left", padx=(14, 4))
        self.var_chunk = tk.DoubleVar(value=1.5)
        ttk.Spinbox(bar2, from_=0.8, to=6.0, increment=0.1, width=5, textvariable=self.var_chunk).pack(side="left")
        # 断句静音：连续安静多久才算"这句说完了"。调小 = 出字幕快但容易断在半句话中间；
        # 调大 = 等完整句，字幕更好懂但更慢。0.6 是"不切 0.4 秒换气"的默认值。
        ttk.Label(bar2, text="断句静音(秒)").pack(side="left", padx=(14, 4))
        self.var_pause = tk.DoubleVar(value=0.6)
        ttk.Spinbox(bar2, from_=0.25, to=1.5, increment=0.05, width=5,
                    textvariable=self.var_pause).pack(side="left")
        ttk.Label(bar2, text="翻译引擎").pack(side="left", padx=(14, 4))
        self.var_engine = tk.StringVar(value=self._default_engine())
        cb = ttk.Combobox(bar2, textvariable=self.var_engine,
                          values=list(ENGINE_MODES), width=22, state="readonly")
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self.on_engine_change)
        ttk.Button(bar2, text="模型状态", command=self.show_models).pack(side="left", padx=10)
        self.var_sound = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar2, text="记录音量", variable=self.var_sound).pack(side="left", padx=12)

        self.lbl_live = ttk.Label(f2, text="未开始", foreground="#ffd166")
        self.lbl_live.pack(anchor="w", padx=10, pady=4)

        ttk.Label(f2, text="原文（按市场语言自动识别）", style="Header.TLabel").pack(anchor="w", padx=10, pady=(8, 2))
        self.txt_pt = tk.Text(f2, height=8, bg="#15161c", fg="#9fd3ff",
                              font=("Consolas", 12), wrap="word", relief="flat")
        self.txt_pt.pack(fill="both", expand=True, padx=10)
        self.lbl_dst_hdr2 = ttk.Label(f2, text="译文（同步显示在悬浮窗）", style="Header.TLabel")
        self.lbl_dst_hdr2.pack(anchor="w", padx=10, pady=(10, 2))
        self._dst_headers.append(self.lbl_dst_hdr2)
        self.txt_zh = tk.Text(f2, height=8, bg="#15161c", fg="#00ff9d",
                              font=("Microsoft YaHei UI", 15), wrap="word", relief="flat")
        self.txt_zh.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        ttk.Label(f2, text="提示：字幕已自动录制到「记录」文件夹（每场一个文件，"
                           "最新一份同时存为 直播字幕.srt），可直接给直播录像做字幕。",
                  foreground="#8f93a8").pack(anchor="w", padx=10, pady=(0, 10))

        # ---- 回复助手 ----
        f3 = ttk.Frame(nb)
        nb.add(f3, text="  回复助手  ")

        self.lbl_reply_dir = ttk.Label(f3, text="中文 → 葡萄牙语（巴西）", style="Header.TLabel")
        self.lbl_reply_dir.pack(anchor="w", padx=10, pady=(10, 2))
        ttk.Label(f3, text="观众问完你得回话。在这里打中文，翻成市场语言，复制走贴到 TikTok 评论框。"
                           "（反向翻译同样会套用当前品类的术语表）",
                  foreground="#8f93a8", wraplength=830, justify="left").pack(anchor="w", padx=10, pady=(0, 6))

        pre = ttk.Frame(f3)
        pre.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Label(pre, text="常用回复").pack(side="left", padx=(0, 6))
        for label, text in REPLY_PRESETS:
            ttk.Button(pre, text=label, width=12,
                       command=lambda t=text: self.reply_preset(t)).pack(side="left", padx=2)

        ttk.Label(f3, text="中文（Ctrl+Enter 翻译）").pack(anchor="w", padx=10, pady=(8, 2))
        self.txt_reply_in = tk.Text(f3, height=5, bg="#15161c", fg="#e8e8ef", insertbackground="#fff",
                                    font=("Microsoft YaHei UI", 13), wrap="word", relief="flat")
        self.txt_reply_in.pack(fill="x", padx=10)
        self.txt_reply_in.bind("<Control-Return>", self.reply_translate)

        btns = ttk.Frame(f3)
        btns.pack(fill="x", padx=10, pady=6)
        ttk.Button(btns, text="翻译", command=self.reply_translate).pack(side="left")
        ttk.Button(btns, text="清空", command=self.reply_clear).pack(side="left", padx=6)
        ttk.Button(btns, text="复制译文", command=self.reply_copy).pack(side="left")
        self.lbl_reply = ttk.Label(btns, text="", foreground="#7ee787")
        self.lbl_reply.pack(side="left", padx=10)

        self.lbl_reply_out = ttk.Label(f3, text="译文", style="Header.TLabel")
        self.lbl_reply_out.pack(anchor="w", padx=10, pady=(8, 2))
        self.txt_reply_out = tk.Text(f3, height=5, bg="#15161c", fg="#00ff9d",
                                     font=("Microsoft YaHei UI", 15), wrap="word", relief="flat")
        self.txt_reply_out.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # ---- 悬浮窗 ----
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", bool(self.var_top.get()))
        self.overlay.attributes("-alpha", 0.93)
        self.overlay.configure(bg="#0d0d12")
        wrap = tk.Frame(self.overlay, bg="#0d0d12", highlightbackground="#00d1ff", highlightthickness=1)
        wrap.pack(fill="both", expand=True)
        self._overlay_wrap = wrap
        header = tk.Frame(wrap, bg="#0d0d12")
        header.pack(fill="x")
        self.lbl_overlay_hdr = tk.Label(header, text=" 中文翻译 ", bg="#0d0d12", fg="#00d1ff",
                                        font=("Microsoft YaHei UI", 9))
        self.lbl_overlay_hdr.pack(side="left")
        # 穿透开着的时候悬浮窗自己收不到鼠标事件，用户会以为是"拖不动了"。
        # 这里放一个显眼的标记，让"为什么拖不动"一眼可见。
        self.lbl_ct = tk.Label(header, text="", bg="#0d0d12", fg="#ffd166",
                               font=("Microsoft YaHei UI", 9))
        self.lbl_ct.pack(side="left")
        tk.Button(header, text="✕", command=self.hide_overlay, bg="#0d0d12", fg="#ff6b6b",
                  relief="flat", bd=0, font=("Segoe UI", 9)).pack(side="right")
        self.lbl_overlay = tk.Label(wrap, text="等待识别…", bg="#0d0d12", fg="#00ff9d",
                                    font=("Microsoft YaHei UI", 22), wraplength=700,
                                    justify="left", anchor="w")
        self.lbl_overlay.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        # 拖动绑定必须覆盖**整棵控件树**，不能只绑几个容器。
        # 真实踩到的坑：原来只绑了 header / lbl_overlay / wrap 三个，
        # 但标题栏文字是 header 里的一个 Label、且铺满 header —— 鼠标点上去
        # 命中的是那个 Label，没绑就等于"抓标题栏拖不动"（实测位移 0,0）。
        self._bind_drag_tree(wrap)
        x, y = self.overlay_pos or OVERLAY_FALLBACK
        self.overlay.geometry(f"{OVERLAY_W}x{OVERLAY_H}+{int(x)}+{int(y)}")
        self.overlay.withdraw()

    def _bind_drag_tree(self, w):
        """给悬浮窗里的每个控件绑上拖动，并设成"可移动"光标（按钮除外，✕ 要能点）。"""
        if not isinstance(w, (tk.Button, ttk.Button)):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            try:
                w.configure(cursor="fleur")
            except Exception:
                pass
        for child in w.winfo_children():
            self._bind_drag_tree(child)

    # ---------------- 悬浮窗拖动 ----------------
    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        x = self.overlay.winfo_x() + e.x - self._dx
        y = self.overlay.winfo_y() + e.y - self._dy
        self.overlay.geometry(f"+{x}+{y}")
        self.overlay_pos = (x, y)

    # ---- 位置微调：鼠标穿透开着时悬浮窗点不到、拖不动，
    #      所以主窗口必须留一套不依赖点击悬浮窗的移动方式 ----
    def nudge_overlay(self, dx: int, dy: int):
        self.overlay_pos = (self.overlay.winfo_x() + dx, self.overlay.winfo_y() + dy)
        self.overlay.geometry(f"+{self.overlay_pos[0]}+{self.overlay_pos[1]}")
        self._refresh_overlay_pos()

    def center_overlay(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.overlay_pos = ((sw - OVERLAY_W) // 2, max(0, sh - OVERLAY_H - 120))
        self.overlay.geometry(f"{OVERLAY_W}x{OVERLAY_H}+{self.overlay_pos[0]}+{self.overlay_pos[1]}")
        self._refresh_overlay_pos()

    def _refresh_overlay_pos(self):
        try:
            self.lbl_overlay_pos.config(text=f"当前位置 {self.overlay.winfo_x()}, {self.overlay.winfo_y()}")
        except Exception:
            pass

    def hide_overlay(self):
        self.overlay.withdraw()

    def apply_top(self):
        """按两个独立开关分别设置置顶：悬浮窗 / 主窗口。

        真实踩到的 bug：原来一个开关同时设这两个窗口，而且 show_overlay() 里
        把悬浮窗的置顶**硬编码成 True** —— 于是取消勾选后只要一按「开始」，
        悬浮窗又被强制置顶，"勾了没反应"。而且 apply_top() 启动时从没被调用过，
        保存的置顶设置重启后也不生效。
        """
        self.overlay.attributes("-topmost", bool(self.var_top.get()))
        self.root.attributes("-topmost", bool(self.var_top_main.get()))

    def _overlay_hwnds(self) -> list[int]:
        """悬浮窗可能的窗口句柄（Tk 顶层窗口在某些情况下要取父窗口）。"""
        try:
            import ctypes
            hwnd = self.overlay.winfo_id()
            parent = ctypes.windll.user32.GetParent(hwnd)
            return [h for h in (parent, hwnd) if h]
        except Exception:
            return []

    def apply_clickthrough(self):
        """开启/关闭悬浮窗的鼠标穿透（让点击穿过悬浮窗落到下面的界面上）。

        Windows 下就是给窗口加上 WS_EX_TRANSPARENT 扩展样式。
        设完会读回来确认真的生效了 —— 不然用户以为开了、实际还挡着鼠标。
        注意：开启后悬浮窗自己就点不到了（包括那个 ✕），要关掉得回主窗口取消勾选。
        """
        on = bool(self.var_clickthrough.get())
        GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x00080000, 0x00000020
        ok = False
        try:
            import ctypes
            user32 = ctypes.windll.user32
            for hwnd in self._overlay_hwnds():
                ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                new = (ex | WS_EX_LAYERED | WS_EX_TRANSPARENT) if on else (ex & ~WS_EX_TRANSPARENT)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new)
                if bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TRANSPARENT) == on:
                    ok = True
                    break
        except Exception as e:
            self.lbl_live.config(text=f"鼠标穿透设置失败：{e}", foreground="#ff6b6b")
            return
        if not ok:
            self.lbl_live.config(text="鼠标穿透设置失败（未能作用到悬浮窗）", foreground="#ff6b6b")
            return
        if on:
            self.lbl_ct.config(text="  · 穿透中，拖不动（用主窗口 ◀▲▼▶ 挪）")
            try:
                self._overlay_wrap.config(highlightbackground="#ffd166")
            except Exception:
                pass
            self.lbl_live.config(
                text="悬浮窗已开启鼠标穿透：点击会穿过去，悬浮窗自己也点不到、拖不动了。"
                     "要挪位置用上面那排 ◀▲▼▶（不用关穿透）；要直接用鼠标拖动就先取消这个勾",
                foreground="#ffd166")
        else:
            self.lbl_ct.config(text="")
            try:
                self._overlay_wrap.config(highlightbackground="#00d1ff")
            except Exception:
                pass
            self.lbl_live.config(text="悬浮窗鼠标穿透已关闭，现在可以直接用鼠标拖动悬浮窗",
                                 foreground="#7ee787")

    def show_overlay(self):
        self.overlay.deiconify()
        # 必须尊重「悬浮窗置顶」勾选 —— 这里以前硬编码 True，
        # 导致取消勾选后一按「开始」又被强制置顶（用户报的"勾了没反应"）。
        self.overlay.attributes("-topmost", bool(self.var_top.get()))
        self._refresh_overlay_pos()

    # ---------------- 实时屏幕翻译 ----------------
    def pick_region(self):
        self.root.withdraw()
        self.root.after(250, lambda: RegionSelector(
            self.root, self._region_done, self._region_cancel))

    def _region_done(self, region):
        self.region = region
        self.lbl_region.config(text=f"区域 {region[0]},{region[1]}  {region[2]}x{region[3]}")
        self.root.deiconify()

    def _region_cancel(self):
        """取消框选（Esc / 拖太小）：必须把主窗口收回来。

        原来 Esc 只销毁遮罩、不回调，主窗口就一直停在 withdraw 状态。
        """
        self.root.deiconify()
        self.lbl_live.config(text="已取消框选（区域未变）", foreground="#ffd166")

    def start_screen(self):
        if self.screen_running:
            return
        if not self.region:
            messagebox.showinfo("提示", "请先点「① 框选区域」选择要翻译的屏幕范围")
            return
        self.screen_running = True
        self.last_text = ""
        self.show_overlay()
        self.screen_thread = threading.Thread(target=self.screen_loop, daemon=True)
        self.screen_thread.start()
        self.set_overlay("识别中…")

    def stop_screen(self):
        self.screen_running = False
        self.set_overlay("已停止")

    def screen_loop(self):
        try:
            st.set_ocr_engine(OCR_MODES.get(self.var_ocr.get(), "auto"))
            st.get_ocr()  # 预热
            self.ui_queue.put(("live_label", f"OCR 引擎已就绪：{st.ocr_engine_name()}"))
        except Exception as e:
            self.ui_queue.put(("error", f"OCR 初始化失败: {e}"))
            self.screen_running = False
            return
        last_sig = ()
        last_ocr_at = 0.0
        while self.screen_running:
            t0 = time.time()
            region = self.region
            interval = max(0.2, float(self.var_interval.get()))
            try:
                rgb = st.grab(region)
                sig = st.frame_signature(rgb)
            except Exception as e:
                self.ui_queue.put(("error", f"抓屏失败: {e}"))
                time.sleep(1.0)
                continue
            # 画面没变就不做识别，省掉 1-2 秒的 OCR；
            # 但最多静默 3 秒必须识别一次，免得指纹漏掉的变化一直不翻。
            changed = st.signature_changed(sig, last_sig)
            if not changed and (time.time() - last_ocr_at) < 3.0:
                time.sleep(interval)
                continue
            last_sig = sig
            last_ocr_at = time.time()
            try:
                items = st.recognize(rgb)
                text = st.merge_lines(items)
            except Exception as e:
                self.ui_queue.put(("error", f"识别失败: {e}"))
                time.sleep(1.0)
                continue
            if text and self._changed(text):
                self.last_text = text
                zh = self._tr(text)
                if zh:
                    self.ui_queue.put(("screen", text, zh))
                else:
                    self._tr_fail()
            time.sleep(max(0.0, interval - (time.time() - t0)))

    @staticmethod
    def _norm(s: str) -> str:
        return "".join(ch for ch in s.lower() if ch.isalnum())

    def _changed(self, text: str) -> bool:
        a, b = self._norm(text), self._norm(self.last_text)
        if not b:
            return True
        if a == b:
            return False
        # 变化很小（OCR 抖动）视为没变
        if abs(len(a) - len(b)) <= 2 and (a in b or b in a):
            return False
        return True

    # ---------------- 直播同传 ----------------
    def start_live(self):
        if self.live_running:
            return
        self.live_running = True
        self.t0 = time.time()
        with self._subs_lock:
            self.subs = []
        # 每场直播单独一个 srt（时间戳命名），最新的一份另外复制成
        # 记录\直播字幕.srt，保持以前的用法不变。
        self._srt_path = os.path.join(
            LOG_DIR, time.strftime("直播字幕-%Y%m%d-%H%M%S.srt"))
        self.show_overlay()
        self.lbl_live.config(text="正在启动…")
        self.live_thread = threading.Thread(target=self.live_loop, daemon=True)
        self.live_thread.start()

    def stop_live(self):
        self.live_running = False

    def live_loop(self):
        """直播同传主循环：VAD 切句 -> CT2 识别 -> 翻译 -> 悬浮窗。"""
        import live_caption as lc
        import asr_engine
        size = self.var_model.get()
        try:
            self.ui_queue.put(("live_label", f"正在加载识别模型 {size} …"))
            if not asr_engine.model_available(size):
                self.ui_queue.put(("error", f"本地没有 {size} 模型。请先运行：python fetch_model.py {size}"))
                self.live_running = False
                return
            asr_engine.get_model(size)
            dev = asr_engine.device_info()
            rec = lc.LoopbackRecorder()
            self.recorder = rec
            rec.start()
            self.ui_queue.put(("live_label",
                               f"正在听：{rec.device_name} ｜ 引擎 faster-whisper({size}) "
                               f"｜ 算力：{dev.get('device', '?')} {dev.get('compute_type', '')}"))
        except Exception as e:
            self.ui_queue.put(("error", f"启动失败: {e}"))
            self.live_running = False
            return

        # 每段最短/断句静音由界面控制（"每句最短(秒)"、"断句静音(秒)"）。
        #
        # 这里原来是 max_seconds = max(3.0, chunk*2) = 3.0、silence_seconds = 0.35，
        # 结果不管主播有没有说完，每 3 秒就被强切一刀，0.35 秒的换气也算"这句完了" ——
        # 真实字幕里大量"半句话"（"…a sua frente, tá?"、"de matos, oito chaves"），
        # 每条又被单独送去翻译，没有上下文，中文自然读不通。
        # 之后改成最长 6 秒，句子完整了但出字幕偏慢。
        #
        # 2026-10 上 GPU 后实测实时率从 1.28x（过载）降到 0.41x，有 2.4 倍余量，
        # 所以把硬切上限收到 4.5 秒：字幕早 1.5 秒出来，实时率升到约 0.6x 仍然安全。
        # 界面「每句最短(秒)」依旧能调：1.5 -> 上限 4.5s，2.0 -> 6.0s，3.0 -> 9.0s。
        chunk = float(self.var_chunk.get())
        pause = float(self.var_pause.get())
        seg = asr_engine.StreamingSegmenter(
            max_seconds=max(4.5, chunk * 3.0),
            min_seconds=chunk,
            silence_seconds=pause,
            overlap_seconds=0.25,
        )
        # 识别 + 翻译丢到后台线程：主循环只管录制和切段，永远不被识别卡住。
        # 队列只留 2 条，满了丢最旧的 —— 直播场景里"追上实时"比"一句不落"重要。
        self._open_live_log()
        self._live_log("开始听译：模型=%s 引擎=%s 每句最短=%.1fs 断句静音=%.1fs"
                       % (size, self.var_engine.get(), chunk, pause))
        self._caption_q = queue.Queue(maxsize=2)
        self._caption_worker = threading.Thread(
            target=self.caption_worker, args=(asr_engine, size), daemon=True)
        self._caption_worker.start()

        while self.live_running:
            time.sleep(0.12)
            data = rec.take()
            # 录音线程失败（回环设备被占用/被禁用）原来只存进 LoopbackRecorder._error
            # 就没人管了：界面照样显示「正在听：xxx」，却永远等不到字幕。
            err = getattr(rec, "_error", None)
            if err is not None:
                self.ui_queue.put(("error", f"录音失败（系统声音回环不可用）：{err}"))
                self._live_log("录音失败：%r" % (err,))
                self.live_running = False
                break
            if data.size == 0:
                continue
            piece = seg.push(data)
            if piece is None:
                continue
            # 纯静音段直接丢掉，不去打扰识别和翻译
            if seg.speech_level(piece) < seg.silence_rms:
                continue
            self._submit_caption(seg.trim(piece))

        # 录音必须在这里关掉。原来只有关窗口时才 stop()，于是「停止听译」之后
        # 回环线程还在往 _chunks 里灌音频、又没人 take()：实测约 64 KB/s
        # （≈230 MB/小时）只涨不降，而且音频设备一直被占着，再点「开始听译」
        # 就是两个回环流同时在跑。
        try:
            rec.stop()
        except Exception:
            pass
        self.recorder = None

        # 收尾：把缓冲里没说完的半句也处理掉，然后等后台线程把队列跑完
        try:
            tail = seg.flush()
            if tail is not None:
                self._submit_caption(tail)
        except Exception:
            pass
        worker = self._caption_worker
        if worker is not None:
            worker.join(timeout=90)
        self._live_log("停止听译")
        # 本场字幕单独留档，再复制一份「最新」出来（记录\直播字幕.srt）
        try:
            if self._srt_path and os.path.exists(self._srt_path):
                import shutil
                shutil.copyfile(self._srt_path, os.path.join(LOG_DIR, "直播字幕.srt"))
                self._live_log("本场字幕：%s" % os.path.basename(self._srt_path))
        except Exception:
            pass
        try:
            if self._live_log_fp:
                self._live_log_fp.close()
        except Exception:
            pass
        self._live_log_fp = None

    def _open_live_log(self):
        """开始听译时开一个带表头的日志，出问题时有据可查。

        之前没有这个日志，直播间延迟大到 132 秒都只能靠猜。
        """
        try:
            if self._live_log_fp:
                self._live_log_fp.close()
        except Exception:
            pass
        self._live_log_fp = None
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            self._live_log_fp = open(os.path.join(LOG_DIR, "运行日志.txt"),
                                     "a", encoding="utf-8")
            import asr_engine
            dev = asr_engine.device_info()
            self._live_log("=" * 72)
            self._live_log("开始 %s ｜ 市场=%s 品类=%s 模型=%s 引擎=%s ｜ 算力=%s/%s"
                           % (time.strftime("%Y-%m-%d %H:%M:%S"), self.var_market.get(),
                              self.var_category.get(), self.var_model.get(),
                              self.var_engine.get(), dev.get("device", "?"),
                              dev.get("compute_type", "")))
        except Exception:
            self._live_log_fp = None

    def _live_log(self, msg: str):
        fp = self._live_log_fp
        if fp is None:
            return
        try:
            fp.write("%s  %s\n" % (time.strftime("%H:%M:%S"), msg))
            fp.flush()
        except Exception:
            pass

    def _submit_caption(self, piece):
        """把一段音频交给后台线程；队列满了丢最旧的一条。"""
        if piece is None or piece.size < 16000 * 0.5:
            return
        q = self._caption_q
        if q is None:
            return
        item = (time.time(), piece, piece.size / 16000, q.qsize())
        try:
            q.put_nowait(item)
        except queue.Full:
            try:
                q.get_nowait()
                self._live_log("队列已满，丢弃最旧的一句（识别跟不上）")
            except queue.Empty:
                pass
            try:
                q.put_nowait(item)
            except queue.Full:
                pass

    def caption_worker(self, asr_engine, size):
        """后台线程：从队列取音频 -> 识别 -> 翻译 -> 写字幕。"""
        while True:
            q = self._caption_q
            if q is None:
                break
            if not self.live_running and q.empty():
                break
            try:
                item = q.get(timeout=0.3)
            except queue.Empty:
                continue
            if item is None:
                break
            t_enq, piece, audio_sec, qsize = item
            try:
                self._emit_caption(asr_engine, piece, size, t_enq, audio_sec, qsize)
            except Exception as e:
                self._live_log("处理异常：%r" % (e,))

    def _emit_caption(self, asr_engine, piece, size, t_enq=None, audio_sec=None, qsize=0):
        """识别 + 翻译一段音频并推给界面（只被 caption_worker 调用）。"""
        if piece is None or piece.size < 16000 * 0.5:
            return
        if t_enq is None:
            t_enq = time.time()
        if audio_sec is None:
            audio_sec = piece.size / 16000
        wait = time.time() - t_enq                    # 排队等待：>1.5s 说明识别跟不上
        try:
            pt, asr_dt = asr_engine.transcribe(piece, language=self.whisper_lang, size=size)
        except Exception as e:
            self.ui_queue.put(("error", f"识别失败: {e}"))
            self._live_log("识别失败 队列等待%.1fs | %r" % (wait, e))
            return
        pt = fix_source(pt)          # 先把 Whisper 听错的葡语词改回来，再翻译
        if not self._is_meaningful(pt):
            self._live_log("丢弃(无意义) 识别%.2fs 队列等待%.1fs 队列%d | %r"
                           % (asr_dt, wait, qsize, pt[:40]))
            return
        t1 = time.time()
        zh = self._tr(pt)
        tr_dt = time.time() - t1
        if not zh:
            self._tr_fail()
            self._live_log("翻译失败 识别%.2fs 翻译%.2fs 队列等待%.1fs | %s"
                           % (asr_dt, tr_dt, wait, pt[:60]))
            return
        # 时间轴取「这段音频说完的时刻」，不是「识别+翻译完的时刻」。
        # 原来用 time.time()，字幕会整体后移一整个识别+翻译的耗时
        # （GPU 场实测约 2.2 秒、CPU 场 4~5 秒），给直播录像配字幕时对不上嘴。
        tick = max(0.0, (t_enq - audio_sec) - self.t0)
        with self._subs_lock:
            self.subs.append((tick, pt, zh, audio_sec))
            n = len(self.subs)
        self.ui_queue.put(("live", pt, zh, asr_dt, tr_dt, audio_sec))
        self._live_log("#%-3d 队列等待%.1fs 识别%.2fs 翻译%.2fs 音频%.1fs 队列%d"
                       % (n, wait, asr_dt, tr_dt, audio_sec, qsize))
        self.save_srt()

    @staticmethod
    def _is_meaningful(text: str) -> bool:
        """过滤幻听：只有标点、或者字母数字太少的结果直接丢弃。"""
        if not text:
            return False
        alnum = sum(1 for ch in text if ch.isalnum())
        return alnum >= 3

    # ---------------- 输出 ----------------
    def set_overlay(self, text: str):
        self.lbl_overlay.config(text=text, font=("Microsoft YaHei UI", max(12, int(self.var_font.get()))))

    def _append(self, widget: tk.Text, prefix: str, text: str, keep: int = 4000):
        widget.insert("end", f"{prefix}{text}\n")
        if len(widget.get("1.0", "end")) > keep:
            widget.delete("1.0", "2.0")
        widget.see("end")

    def save_srt(self):
        with self._subs_lock:
            subs = list(self.subs)
        if not subs:
            return
        path = self._srt_path or os.path.join(LOG_DIR, "直播字幕.srt")
        with open(path, "w", encoding="utf-8") as f:
            for i, (tick, pt, zh, audio_dur) in enumerate(subs, 1):
                # 结束时间 = 下一句开始时间（若已到末尾则按句长+1秒）
                if i < len(subs):
                    end = subs[i][0]
                else:
                    end = tick + max(1.5, audio_dur)
                if end <= tick:
                    end = tick + 1.0
                f.write(f"{i}\n{self._ts(tick)} --> {self._ts(end)}\n{pt}\n{zh}\n\n")

    @staticmethod
    def _ts(sec: float) -> str:
        h = int(sec // 3600)
        m = int(sec % 3600 // 60)
        s = int(sec % 60)
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def save_log(self):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(LOG_DIR, f"屏幕翻译-{stamp}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.txt_src.get("1.0", "end"))
            f.write("\n===== 中文 =====\n")
            f.write(self.txt_dst.get("1.0", "end"))
        messagebox.showinfo("已保存", path)

    # ---------------- 队列泵 ----------------
    def pump(self):
        if self._closing:
            return
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                kind = msg[0]
                if kind == "screen":
                    _, src, dst = msg
                    self._append(self.txt_src, "· ", src)
                    self._append(self.txt_dst, "▶ ", dst)
                    self.set_overlay(dst)
                elif kind == "live":
                    _, pt, zh, asr_dt, tr_dt, audio_s = msg
                    self._append(self.txt_pt, f"[{audio_s:.1f}s] ", pt)
                    self._append(self.txt_zh, f"[识别{asr_dt:.2f}s 翻译{tr_dt:.2f}s] ", zh)
                    self.set_overlay(zh)
                    total = asr_dt + tr_dt
                    import asr_engine as _ae
                    dev = _ae.device_info().get("device") or "-"
                    self.lbl_live.config(
                        text=f"运行中 ｜ faster-whisper({self.var_model.get()})·{dev} ｜ "
                             f"本句 识别{asr_dt:.2f}s + 翻译{tr_dt:.2f}s = {total:.2f}s",
                        foreground="#7ee787" if total < 2.0 else "#ffd166")
                elif kind == "live_label":
                    self.lbl_live.config(text=msg[1], foreground="#ffd166")
                elif kind == "reply":
                    _, out, err = msg
                    if err:
                        self.lbl_reply.config(text=err, foreground="#ff6b6b")
                    elif out:
                        self.txt_reply_out.delete("1.0", "end")
                        self.txt_reply_out.insert("1.0", out)
                        self.lbl_reply.config(text="翻译完成，点「复制译文」", foreground="#7ee787")
                    else:
                        self.lbl_reply.config(text="翻译失败（网络？可换翻译引擎重试）", foreground="#ff6b6b")
                elif kind == "error":
                    self.lbl_live.config(text=msg[1], foreground="#ff6b6b")
        except queue.Empty:
            pass
        self._pump_id = self.root.after(120, self.pump)

    def _default_engine(self):
        """默认只用在线接口。

        为什么不默认带本地兜底：本地兜底模型 NLLB 是 CC-BY-NC-4.0（**禁止商用**）许可。
        分发一个"能调用它"的软件没问题，但把它设成默认，等于替所有使用者
        （包括商用的人）做了选择 —— 默认行为才是最需要干净的那一环。
        熔断修好之后在线通道已经够稳（实测 0.1~1.6 秒），想留兜底的人
        在「翻译引擎」里自己选「在线优先 + 本地兜底」即可，选择会被记住。
        """
        return "仅在线接口"

    def on_engine_change(self, _evt=None):
        import translate_core
        mode = ENGINE_MODES.get(self.var_engine.get(), "api")
        translate_core.set_engine(mode)
        if mode == "nllb":
            self.lbl_live.config(
                text="翻译引擎：仅本地模型（完全离线，不联网）", foreground="#7ee787")
        elif mode == "auto":
            self.lbl_live.config(
                text="翻译引擎：在线优先 + 本地兜底 ｜ 注意本地模型 NLLB 为 CC-BY-NC-4.0，"
                     "商用请自行评估许可", foreground="#ffd166")
        else:
            self.lbl_live.config(
                text="翻译引擎：仅在线接口（免费公开接口，无需 Key）", foreground="#ffd166")

    def show_models(self):
        try:
            import asr_engine
            import nllb_translate
            sizes = ("base", "small", "medium", "large-v3")
            have = [s for s in sizes if asr_engine.model_available(s)]
            miss = [s for s in sizes if not asr_engine.model_available(s)]
            lines = ["【语音识别模型】",
                     "本地已有：" + ("、".join(have) if have else "无")]
            if miss:
                lines.append("还缺：" + "、".join(miss))
                lines.append("下载命令（在本目录打开 PowerShell 运行）：")
                for m in miss:
                    lines.append(f"    python fetch_model.py {m}")
            lines += ["", "【本地翻译模型（可选）】",
                      "NLLB 离线翻译：" + ("已安装" if nllb_translate.available() else "未安装"),
                      "    ！许可提醒：NLLB 是 CC-BY-NC-4.0，**禁止商用**。",
                      "    商用请自行评估；不用它程序照常工作（默认只用在线接口）。"]
            if not nllb_translate.available():
                lines.append("    安装命令：python fetch_nllb.py")
            lines += ["", f"当前翻译引擎：{self.var_engine.get()}"
                          f"（内部模式 {ENGINE_MODES.get(self.var_engine.get(), 'api')}）"]
            import translate_core
            lines.append("在线通道状态：" + "，".join(
                f"{k}:{v}" for k, v in translate_core.channel_status().items()))
            messagebox.showinfo("模型状态", "\n".join(lines))
        except Exception as e:
            messagebox.showerror("出错", str(e))

    def on_close(self):
        self._closing = True
        # 先取消排队中的 pump，否则窗口销毁后它还会跑一次，控制台留一行 Tcl 报错
        try:
            if self._pump_id:
                self.root.after_cancel(self._pump_id)
                self._pump_id = None
        except Exception:
            pass
        self.screen_running = False
        self.live_running = False
        try:
            if self.recorder:
                self.recorder.stop()
        except Exception:
            pass
        self.save_srt()
        self.save_settings()
        close_cache()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
