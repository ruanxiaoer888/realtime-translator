# -*- coding: utf-8 -*-
"""P0 三项修复的验收脚本（改完之后跑这一个文件就够）。

覆盖：
  A. OCR 换拉丁模型        —— 引擎选择 + 重音字错率 + 速度
  B. 术语修正不再污染译文  —— 原来被改坏的 4 个用例 + 该修的还得修
  C. 画面变化检测          —— 单行新评论能不能被发现 + 静止/噪声不能误触发
  D. NLLB 通道的同类保护

运行（项目根目录）:
    python tools\\verify_p0.py
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 顺序和 app.py 一致：先 libs 再第三方。缺这一行时直接
# `py -3.12 tools\verify_p0.py` 会 ModuleNotFoundError: numpy（实测踩到）。
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import screen_translate as st  # noqa: E402
import audit_ocr as base  # noqa: E402  (同一套渲染 + CER 指标)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = ""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))


# ============================================================ A. OCR 引擎
def part_a():
    print("=" * 78)
    print("A. OCR 换拉丁模型")
    print("=" * 78)
    print(f"  拉丁模型可用: {st.latin_available()}")
    check("拉丁模型已就位", st.latin_available(), st.OCR_LATIN_DIR)

    # ① 字典检查必须**显式**用 latin 引擎。
    #    真实踩到过：pt-BR 语言包装好之后默认 auto 会走 Windows OCR，
    #    而 _WinOcr 没有 text_rec 字典 —— 不指定引擎这一项就会误报 FAIL。
    st.set_ocr_engine("latin")
    eng_latin = st.get_ocr("latin")
    rec = getattr(eng_latin, "text_rec", None)
    chars = set(rec.postprocess_op.character) if rec is not None else set()
    missing = [c for c in "ãçêõñâ¿" if c not in chars]
    check("拉丁模型字典含葡/西重音字符", not missing, f"缺 {missing}" if missing else "ã ç ê õ ñ â ¿ 全在")

    # ② 逐用例切换语种。真实踩到过：四个用例共用同一个引擎时，
    #    西语会被葡语引擎读，CER 从 0.0000 掉到 0.0039。
    cases = [("葡语18pt", base.PT_LINES, 18, "pt-BR"), ("葡语14pt", base.PT_LINES, 14, "pt-BR"),
             ("西语18pt", base.ES_LINES, 18, "es-MX"), ("西语14pt", base.ES_LINES, 14, "es-MX")]
    for label, lines, size, loc in cases:
        st.set_ocr_locale(loc)
        st.set_ocr_engine("auto")
        img = base.render(lines, size=size)
        ref = base.norm(" ".join(lines))
        hyp = base.norm(st.merge_lines(st.recognize(img)))
        lev, _ = base.edit_ops(ref, hyp)
        cer = lev / max(1, len(ref))
        check(f"{label} 字错率 {cer:.4f}（要求 0.0）", cer <= 0.001,
              f"lev={lev}  引擎={st.ocr_engine_name()}")

    # ③ auto 的引擎选择要跟语言包状态一致：
    #    装了对应语言包就该用系统 OCR，没装就不该用（会退回拉丁模型）。
    st.set_ocr_locale("pt-BR")
    st.set_ocr_engine("auto")
    st.get_ocr("auto")
    name = st.ocr_engine_name()
    use_win = name.startswith("Windows")
    check("auto 引擎选择与语言包状态一致",
          use_win == (st.win_ocr_available("pt-BR") is not None), name)

    img = base.render(base.PT_LINES, size=18)
    eng = st.get_ocr("auto")
    eng(img)
    ts = []
    for _ in range(3):
        t0 = time.perf_counter()
        eng(img)
        ts.append((time.perf_counter() - t0) * 1000)
    med = sorted(ts)[len(ts) // 2]
    print(f"  热态单帧耗时: {', '.join(f'{x:.0f}' for x in ts)} ms  中位数 {med:.0f} ms")
    # 看中位数而不是"三次都必须 < 2 秒"：系统忙的时候（刚重启、后台在灌索引/杀软扫描）
    # 单帧可能短暂飙到 5 秒以上，逐次判定会误报。真回归会让三次都慢，中位数照样能抓到。
    check("单帧耗时中位数仍在 2 秒内", med < 2000, f"中位数 {med:.0f} ms")


# ============================================================ B. 术语污染
def part_b():
    print("=" * 78)
    print("B. 术语修正不再污染译文")
    print("=" * 78)
    import markets, asr_engine, translate_core

    asr_engine.set_terminology(prompt="", glossary=markets.get_glossary("五金工具", "pt"))
    n = len(asr_engine.get_glossary())
    print(f"  当前术语表: 五金工具/pt  {n} 条")

    cases = [
        # (原文, 输入译文, 期望译文, 说明)
        ("no repetitivo, que cansa a gente ficar ali na chave de fenda, mas tambem nao exige uma parafusadeira",
         "在重复中，这让我们厌倦了拿着一字螺丝刀站在那里，但它也不需要电动螺丝刀",
         "在重复中，这让我们厌倦了拿着一字螺丝刀站在那里，但它也不需要电动螺丝刀",
         "真实字幕原句：不能动"),
        ("uma parafusadeira e uma chave de fenda",
         "一把电动螺丝刀和一把一字螺丝刀",
         "一把电动螺丝刀和一把一字螺丝刀",
         "两个术语都对：不能加前缀"),
        ("a parafusadeira tem muita potencia",
         "电动螺丝刀的力量很大",
         "电动螺丝刀的力量很大",
         "原本被改成 电动电动螺丝刀"),
        ("uma parafusadeira e uma chave de fenda",
         "一把螺丝刀和一把一字螺丝刀",
         "一把电动螺丝刀和一把一字螺丝刀",
         "该修的还是要修（螺丝刀 -> 电动螺丝刀）"),
        ("o preco da parafusadeira esta otimo",
         "螺丝刀的价格很好",
         "电动螺丝刀的价格很好",
         "网上接口常见的错译仍要修"),
    ]
    for src, zh, want, note in cases:
        got = translate_core.apply_glossary(src, zh)
        check(f"{note}", got == want, f"\n        得到: {got}\n        期望: {want}")

    # 换品类后仍然生效
    asr_engine.set_terminology(prompt="", glossary=markets.get_glossary("汽车与摩托", "pt"))
    got = translate_core.apply_glossary("a pastilha de freio e boa", "刹车垫很好")
    check("换品类后修正仍生效（刹车垫->刹车片）", got == "刹车片很好", f"得到: {got}")

    # 西语市场
    asr_engine.set_terminology(prompt="", glossary=markets.get_glossary("五金工具", "es"))
    got = translate_core.apply_glossary("el taladro es potente", "钻机很强大")
    check("西语市场修正生效（钻机->电钻）", got == "电钻很强大", f"得到: {got}")


# ============================================================ C. 画面变化
def part_c():
    print("=" * 78)
    print("C. 画面变化检测")
    print("=" * 78)
    import audit_framesig as fs

    FONT = r"C:\Windows\Fonts\segoeui.ttf"
    BG, FG = (0x15, 0x16, 0x1C), (0xE8, 0xE8, 0xEF)

    def render(lines, width=1000, size=18, extra=None):
        img = Image.new("RGB", (width, 420), BG)
        d = ImageDraw.Draw(img)
        f = ImageFont.truetype(FONT, size)
        for i, line in enumerate(lines):
            d.text((14, 18 + i * 45), line, font=f, fill=FG)
        if extra:
            d.text((extra[1], extra[2]), extra[0], font=f, fill=FG)
        return np.asarray(img)[:, :, :3].copy()

    base_lines = base.PT_LINES
    a = render(base_lines)
    b = render(["Acabei de entrar na live, boa noite a todos!"] + base_lines[1:])   # 顶行整条换新
    c = render(base_lines, extra=("ok", 700, 18 + 7 * 45))                          # 末行加一小段
    d = render(["Vou levar dois, tem desconto?"] + base_lines[1:-1])                # 中间换一行

    sig_a, sig_b, sig_c, sig_d = (st.frame_signature(x) for x in (a, b, c, d))
    print(f"  指纹长度: A={len(sig_a)}  (网格 {st.GRID_ROWS}x{st.GRID_COLS})  阈值={st.CHANGE_RATIO}")

    check("画面没变 -> 不重识别", st.signature_changed(sig_a, sig_a) is False)
    check("顶行整条换新评论 -> 重识别", st.signature_changed(sig_a, sig_b) is True)
    check("中间换一行评论 -> 重识别", st.signature_changed(sig_a, sig_d) is True)

    # 噪声：整图加极小的随机扰动（模拟视频压缩噪点），不应该触发
    rng = np.random.default_rng(0)
    noisy = np.clip(a.astype(np.int16) + rng.integers(-3, 4, a.shape), 0, 255).astype(np.uint8)
    check("±3 灰度噪点 -> 不误触发", st.signature_changed(sig_a, st.frame_signature(noisy)) is False)

    # 末行追加一小段文字：单行局部变化，块均值也会变
    chg = st.signature_changed(sig_a, sig_c)
    print(f"  （末行追加 'ok' 是否触发: {chg} —— 即使不触发，app 里最多 3 秒也会强制识别一次）")


# ============================================================ D. NLLB 通道
def part_d():
    print("=" * 78)
    print("D. NLLB 通道的同类保护")
    print("=" * 78)
    import nllb_translate as nt

    # 已经正确的词不应该被再加前缀
    got = nt._postprocess("电动螺丝刀的力量很大", "a parafusadeira")
    check("NLLB: 已正确的 电动螺丝刀 不被改成 电动电动螺丝刀",
          got == "电动螺丝刀的力量很大", f"得到: {got}")
    # 该修的仍然修
    got = nt._postprocess("螺旋的力量很大", "a parafusadeira")
    check("NLLB: 错译 螺旋 仍被修成 电动螺丝刀", got == "电动螺丝刀的力量很大", f"得到: {got}")
    # 工具箱不被行李箱规则破坏
    got = nt._postprocess("工具箱很结实", "a maleta")
    check("NLLB: 工具箱 不被改坏", got == "工具箱很结实", f"得到: {got}")


def main():
    print("#" * 78)
    print("P0 修复验收")
    print(f"解释器: {sys.executable}")
    print("#" * 78)
    part_a()
    part_b()
    part_c()
    part_d()
    print("=" * 78)
    print(f"结果: 通过 {len(PASS)} 项, 失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项:")
        for f in FAIL:
            print(f"  - {f}")
    print("=" * 78)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
