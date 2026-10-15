# -*- coding: utf-8 -*-
"""限流压测：各免费翻译通道在持续调用下能撑多久。

⚠️ 会消耗真额度：MyMemory 走的是**每日**免费配额，跑完这一轮它当天就废了
   （实测跑完立刻回 HTTP 429，Retry-After 17917 秒 ≈ 5 小时）。
   所以必须显式加 --yes 才跑，避免误触。

用法：
    python tools\\rate_test.py --yes        # 完整压测（会打光 MyMemory 当日额度）
    python tools\\rate_test.py --dry-run    # 只看会跑哪些用例，不发请求
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import translate_core as tc

ARGS = set(sys.argv[1:])
if "--dry-run" in ARGS:
    print("会依次压测：")
    print("  A. 有道      零间隔 30 次")
    print("  B. 有道      间隔 2 秒 15 次")
    print("  C. 腾讯      零间隔 20 次")
    print("  D. MyMemory  零间隔 15 次   <-- 会打光当日免费额度")
    print("\n确认要跑就加 --yes")
    sys.exit(0)
if "--yes" not in ARGS:
    print(__doc__)
    print("拒绝执行：没加 --yes。加 --dry-run 可以先看会跑什么。")
    sys.exit(1)


def run(label, n, gap, fn, make):
    print(f"\n--- {label}（{n} 次，间隔 {gap}s）---")
    ok = fail = 0
    lats = []
    for i in range(n):
        s = make(i)
        t0 = time.time()
        try:
            r = fn(s, "pt", "zh-CN")
        except Exception as e:
            r = None
            err = f"{type(e).__name__}"
        ms = (time.time() - t0) * 1000
        if r:
            ok += 1
            lats.append(ms)
            if i % 5 == 0 or i == n - 1:
                print(f"  #{i+1:<3} {ms:6.0f}ms  {r}")
        else:
            fail += 1
            print(f"  #{i+1:<3} {ms:6.0f}ms  [失败]")
        if gap:
            time.sleep(gap)
    if lats:
        lats_sorted = sorted(lats)
        print(f"  成功 {ok}/{n}  失败 {fail}/{n}   "
              f"延迟 中位 {lats_sorted[len(lats_sorted)//2]:.0f}ms  "
              f"最小 {min(lats):.0f}ms  最大 {max(lats):.0f}ms")
    else:
        print(f"  成功 0/{n}  失败 {fail}/{n}")
    return ok, fail


def mk(prefix):
    def make(i):
        return f"{prefix} numero {i} com parafusadeira e bateria de 48 volts."
    return make


print("=" * 90)
print("A. 有道：零间隔连续 30 次（模拟密集字幕）")
print("=" * 90)
run("有道 无间隔", 30, 0, tc._youdao, mk("Ola,"))

print()
print("=" * 90)
print("B. 有道：间隔 2 秒连续 15 次（模拟真实直播节奏）")
print("=" * 90)
run("有道 2s 间隔", 15, 2.0, tc._youdao, mk("Bom dia,"))

print()
print("=" * 90)
print("C. 腾讯：零间隔连续 20 次")
print("=" * 90)
run("腾讯 无间隔", 20, 0, tc._tencent, mk("Ola,"))

print()
print("=" * 90)
print("D. MyMemory：零间隔连续 15 次")
print("=" * 90)
run("MyMemory 无间隔", 15, 0, tc._mymemory, mk("Ola,"))
