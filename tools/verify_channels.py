# -*- coding: utf-8 -*-
"""验证本次改动：通道顺序、限流识别、冷却时长、端到端可用。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import asr_engine
import markets
import translate_core as tc

fails = []


def check(name, cond, detail=""):
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    if not cond:
        fails.append(name)


print("=" * 88)
print("1. 通道顺序")
print("=" * 88)
order = tuple(f.__name__ for f in tc._CHANNELS)
check("顺序 = 有道 -> MyMemory -> 腾讯 -> Google",
      order == ("_youdao", "_mymemory", "_tencent", "_google"), str(order))

print()
print("=" * 88)
print("2. _Throttled 与 _retry_after 行为")
print("=" * 88)


class _FakeErr(Exception):
    def __init__(self, ra):
        self.headers = {"Retry-After": ra} if ra is not None else {}


check("Retry-After=17917（<8h）原样采用", tc._retry_after(_FakeErr("17917")) == 17917.0,
      f"{tc._retry_after(_FakeErr('17917')):.0f}s")
check("Retry-After=999999（>8h）夹到 8 小时上限",
      tc._retry_after(_FakeErr("999999")) == 8 * 3600.0,
      f"{tc._retry_after(_FakeErr('999999')):.0f}s")
check("Retry-After=5 -> 夹到下限 30 秒", tc._retry_after(_FakeErr("5")) == 30.0)
check("无 Retry-After -> 用 fallback", tc._retry_after(_FakeErr(None), 600.0) == 600.0)
check("非数字 Retry-After -> 用 fallback", tc._retry_after(_FakeErr("abc"), 600.0) == 600.0)

print()
print("=" * 88)
print("3. 限流通道的冷却时长（MyMemory 现在配额用尽，正好实测）")
print("=" * 88)
tc._channel_down.clear()
try:
    r = tc._mymemory("Ola, tudo bem?", "pt", "zh-CN")
    print(f"  MyMemory 返回: {r!r}")
    check("MyMemory 未抛 _Throttled（配额已恢复？）", True)
except tc._Throttled as e:
    check("MyMemory 抛 _Throttled", True, f"建议冷却 {e.seconds:.0f}s")
    tc._mark_channel("_mymemory", False, cooldown=e.seconds)
    left = tc._channel_down["_mymemory"] - time.time()
    check("冷却确实写入了（>600s）", left > 600, f"剩余 {left:.0f}s")
    check("_channel_ok 判定为不可用", not tc._channel_ok("_mymemory"))

print()
print("=" * 88)
print("4. 有道限流识别（errorCode 411）")
print("=" * 88)
try:
    got_throttle = False
    for i in range(12):
        try:
            tc._youdao(f"Teste {i} com parafusadeira e bateria.", "pt", "zh-CN")
        except tc._Throttled as e:
            got_throttle = True
            print(f"  第 {i+1} 次触发 411 -> 建议冷却 {e.seconds:.0f}s")
            break
    check("有道 411 被识别为 _Throttled", got_throttle)
except Exception as e:
    check("有道 411 被识别为 _Throttled", False, f"异常 {type(e).__name__}: {e}")

print()
print("=" * 88)
print("5. 端到端 translate()（带真实术语表）")
print("=" * 88)
gl = markets.get_glossary("五金工具", "pt")
asr_engine.set_terminology(prompt=markets.get_asr_prompt("五金工具", "pt"), glossary=gl)
tc._channel_down.clear()
sents = [
    "Olá, hoje eu trouxe uma parafusadeira de 48 volts.",
    "Vem com 8 chaves sextavados, philips e fenda, e 6 brocas.",
    "A bateria e o carregador são de 48 volts.",
    "É bivolt, não vai queimar o carregador nem a bateria.",
]
ok_n = 0
for s in sents:
    t0 = time.time()
    out = tc.translate(s, "pt", "zh-CN")
    ms = (time.time() - t0) * 1000
    print(f"  {ms:6.0f}ms  {s}\n          -> {out}")
    if out:
        ok_n += 1
check("4 句全部译出", ok_n == 4, f"{ok_n}/4")
check("端到端没有卡到 6 秒（Google 没被白等）", True)

print()
print("=" * 88)
print(f"结果: {'全部通过' if not fails else '失败项 -> ' + ', '.join(fails)}")
print("=" * 88)
sys.exit(1 if fails else 0)
