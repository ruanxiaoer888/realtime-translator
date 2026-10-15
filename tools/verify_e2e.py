# -*- coding: utf-8 -*-
"""端到端复核：拿真实直播字幕里的原文句子，走完整翻译链路（在线接口 + 术语修正），
确认修好之后不会再出现"电动一字螺丝刀""电动电动螺丝刀"这类污染。

运行（项目根目录）:
    python tools\\verify_e2e.py
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

import markets
import asr_engine
import translate_core

# 直接取自 记录\直播字幕.srt 的葡语原文（当时就是这些句子译出了"电动一字螺丝刀"）
SENTENCES = [
    "no repetitivo, que cansa a gente ficar ali na chave de fenda, mas também não exige uma parafusadeira, essa daqui olha",
    "prática, chave de fenda",
    "carregando e maleta, bolsa de ferramenta",
    "a parafusadeira tem muita potencia",
    "por aqui, por esse carrinho laranja entrega super rápido",
]

BAD = ("电动一字", "电动电动", "一字电动")


def main():
    asr_engine.set_terminology(prompt="", glossary=markets.get_glossary("五金工具", "pt"))
    print(f"市场=巴西  品类=五金工具  术语 {len(asr_engine.get_glossary())} 条  目标=中文\n")

    bad_hits = []
    for s in SENTENCES:
        translate_core.clear_cache()
        t0 = time.time()
        zh = translate_core.translate(s, src="pt-BR", dst="zh-CN")
        dt = time.time() - t0
        hit = [b for b in BAD if b and b in (zh or "")]
        if hit:
            bad_hits.append((s, zh, hit))
        print(f"[{dt:4.2f}s] {s}")
        print(f"        -> {zh}")
        print(f"        污染检查: {'发现 ' + str(hit) if hit else '干净'}\n")

    print("=" * 74)
    if bad_hits:
        print(f"失败：{len(bad_hits)} 句出现术语污染")
        return 1
    print(f"通过：{len(SENTENCES)} 句全部无术语污染（电动一字/电动电动/一字电动 均未出现）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
