# -*- coding: utf-8 -*-
"""多市场验收：每个市场 × 品类的术语与翻译是否都对。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "tmp", "models"))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import markets  # noqa: E402
import asr_engine  # noqa: E402
import translate_core as tc  # noqa: E402

# 每个市场：一句该市场的真实直播话术 + 期望出现的中文术语
CASES = {
    "巴西": ("Hoje eu trouxe uma parafusadeira muito potente com maleta completa.", ["电动螺丝刀", "工具箱"]),
    "墨西哥": ("Hoy traje un taladro muy potente con caja de herramientas completa.", ["电钻", "工具箱"]),
    "阿根廷": ("Hoy traje un taladro muy potente y una amoladora profesional.", ["电钻", "角磨机"]),
    "美区": ("Today I brought a power drill with a complete tool box.", ["电钻", "工具箱"]),
}

print("=" * 78)
print("多市场翻译验收（在线接口为主）")
print("=" * 78)
tc.set_engine("auto")

ok_all = True
for market_name, (sentence, expects) in CASES.items():
    m = markets.get_market(market_name)
    category = "五金工具"
    glossary = markets.get_glossary(category, m["whisper"])
    asr_engine.set_terminology(prompt=m["asr_prompt"], glossary=glossary)
    tc.clear_cache()

    t0 = time.time()
    zh = tc.translate(sentence, src=m["locale"], dst="zh-CN") or ""
    dt = time.time() - t0
    hits = [e for e in expects if e in zh]
    good = len(hits) == len(expects)
    ok_all = ok_all and good
    print(f"\n[{market_name}] 语言 {m['locale']} / 术语 {len(glossary)} 条 / {dt:.2f}s")
    print(f"  原文: {sentence}")
    print(f"  译文: {zh}")
    print(f"  期望术语 {expects} -> 命中 {hits}  {'✓ 通过' if good else '✗ 未命中'}")

print("\n" + "=" * 78)
print("跨品类验收（同一市场，换品类术语表应跟着换）")
print("=" * 78)
category_cases = {
    "五金工具": ("Essa parafusadeira vem com maleta.", ["电动螺丝刀", "工具箱"]),
    "汽车与摩托": ("O óleo lubrificante e a pastilha de freio são originais.", ["润滑油", "刹车片"]),
    "运动与户外": ("Essa barraca e o saco de dormir são leves.", ["帐篷", "睡袋"]),
}
for cat, (sentence, expects) in category_cases.items():
    glossary = markets.get_glossary(cat, "pt")
    asr_engine.set_terminology(prompt=markets.get_market("巴西")["asr_prompt"], glossary=glossary)
    tc.clear_cache()
    zh = tc.translate(sentence, src="pt-BR", dst="zh-CN") or ""
    hits = [e for e in expects if e in zh]
    good = len(hits) == len(expects)
    ok_all = ok_all and good
    print(f"\n[{cat}] 术语 {len(glossary)} 条")
    print(f"  原文: {sentence}")
    print(f"  译文: {zh}")
    print(f"  命中 {hits}  {'✓' if good else '✗'}")

print("\n" + "=" * 78)
print("结论:", "全部通过" if ok_all else "有未通过项，见上面 ✗")
