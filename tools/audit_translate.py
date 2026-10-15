# -*- coding: utf-8 -*-
"""只读审计脚本：翻译链路 6 项检查。

不修改任何既有文件；只在本脚本内 monkeypatch 运行时对象（check 6），跑完立即还原。
运行方式（工作目录 = 项目根）：
    python tools\\audit_translate.py
"""
from __future__ import annotations

import io
import json
import os
import statistics
import sys
import time

# ---- 让控制台按 UTF-8 输出，避免 Windows GBK 报错 ----
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import translate_core  # noqa: E402
import asr_engine  # noqa: E402
import markets  # noqa: E402
import nllb_translate  # noqa: E402

RESULTS: dict = {}
FAKE_CALLS = {"n": 0}


def sec(title: str):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def sub(title: str):
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def out(tag: str, value) -> None:
    print(f"{tag}{value}")


# ============================================================================
# 1. 分通道延迟
# ============================================================================
SENT_PT = "Hoje eu trouxe uma parafusadeira muito potente com maleta completa."
N_CALLS = 5

sec("CHECK 1 | 分通道延迟（每个通道直调 5 次，同一句葡语）")
print(f"句子 ({len(SENT_PT)} chars): {SENT_PT}")
print("参数: src='pt-BR', dst='zh-CN'")

CHANNELS = [
    ("_google", translate_core._google),
    ("_mymemory", translate_core._mymemory),
    ("_youdao", translate_core._youdao),
]

check1 = {}
for name, fn in CHANNELS:
    sub(f"通道 {name}")
    times, texts, errs = [], [], []
    for i in range(1, N_CALLS + 1):
        t0 = time.perf_counter()
        try:
            r = fn(SENT_PT, "pt-BR", "zh-CN")
            err = ""
        except Exception as e:  # 网络/解析异常都要记录下来，不能吞
            r = None
            err = f"{type(e).__name__}: {e}"
        dt = time.perf_counter() - t0
        times.append(dt)
        texts.append(r)
        errs.append(err)
        shown = repr(r) if r else "<EMPTY/None>"
        print(f"  call {i}: {dt:7.3f}s  non_empty={bool(r)!s:5s}  out={shown}"
              + (f"  ERR={err}" if err else ""))

    warm = times[1:]  # 第 2..5 次
    all_nonempty = all(bool(t) for t in texts)
    entry = {
        "times": times,
        "min": min(times),
        "avg": statistics.mean(times),
        "max": max(times),
        "warm_avg": statistics.mean(warm) if warm else None,
        "cold": times[0],
        "all_nonempty": all_nonempty,
        "non_empty_count": sum(1 for t in texts if t),
        "outputs": texts,
        "errors": errs,
    }
    check1[name] = entry
    print(f"  -> min={entry['min']:.3f}s  avg={entry['avg']:.3f}s  max={entry['max']:.3f}s  "
          f"non_empty={all_nonempty} ({entry['non_empty_count']}/{N_CALLS})")
    print(f"  -> 第1次(冷)={entry['cold']:.3f}s  第2..5次均值(暖)={entry['warm_avg']:.3f}s")

RESULTS["check1"] = check1

# ============================================================================
# 2. 连接复用
# ============================================================================
sec("CHECK 2 | 连接复用：重复调用同一主机是否变快（TLS 重新握手证据）")
check2 = {}
for name, e in check1.items():
    cold_ms = e["cold"] * 1000.0
    warm_ms = e["warm_avg"] * 1000.0
    delta_ms = warm_ms - cold_ms
    faster = warm_ms < cold_ms
    check2[name] = {"cold_ms": cold_ms, "warm_ms": warm_ms, "delta_ms": delta_ms,
                    "warm_faster": faster}
    print(f"  {name:11s} cold(mean of 1st)={cold_ms:8.1f} ms   "
          f"warm(mean 2..5)={warm_ms:8.1f} ms   delta={delta_ms:+8.1f} ms   "
          f"warm_faster={faster}")
print("\n解读口径：delta 为负 = 暖调用更快（连接被复用）；接近 0 或为正 = 每次调用都在重建连接/TLS。")
print("证据：通道实现见 translate_core._get()，每次调用都新建 urllib.request.urlopen()，"
      "未使用 keep-alive 会话对象。")
RESULTS["check2"] = check2

# ============================================================================
# 3. 术语表污染检查
# ============================================================================
sec("CHECK 3 | 术语表污染检查（apply_glossary 直接调用）")

gl_pt = markets.get_glossary("五金工具", "pt")
asr_engine.set_terminology(prompt="", glossary=gl_pt)
after = asr_engine.get_glossary()
print(f"注入术语表 = markets.get_glossary('五金工具','pt')  -> {len(gl_pt)} 条")
print(f"asr_engine.get_glossary() 回读 -> {len(after)} 条, 一致={after == gl_pt}")
print(f"  parafusadeira -> {gl_pt.get('parafusadeira')!r}")
print(f"  chave de fenda -> {gl_pt.get('chave de fenda')!r}")
print(f"  TERM_FIXES['parafusadeira'] = {translate_core.TERM_FIXES.get('parafusadeira')}")
print(f"  TERM_FIXES['chave de fenda'] = {translate_core.TERM_FIXES.get('chave de fenda')}")

SRC3 = "Hoje trouxe uma parafusadeira e uma chave de fenda"
CASES3 = [
    ("case A", SRC3, "今天带来了一把螺丝刀和一把一字螺丝刀"),
    ("case B", SRC3, "电动螺丝刀和螺丝刀"),
]
check3 = {"glossary_pt_count": len(gl_pt), "cases": []}
for label, s, z in CASES3:
    r = translate_core.apply_glossary(s, z)
    corrupted = (r != z)
    row = {"label": label, "src": s, "zh_in": z, "zh_out": r, "changed": corrupted}
    check3["cases"].append(row)
    sub(label)
    print(f"  src  (in) : {s}")
    print(f"  zh   (in) : {z}")
    print(f"  zh  (out) : {r}")
    print(f"  是否被改写: {corrupted}")
    if label == "case A":
        print(f"  正确术语 '一字螺丝刀' 是否被破坏: {'一字螺丝刀' not in r}")
        print(f"  正确术语 '电动螺丝刀' 是否被破坏: {'电动螺丝刀' not in (r or '')}")
    else:
        print(f"  正确术语 '电动螺丝刀' 是否被破坏: {'电动螺丝刀' not in (r or '')}")
RESULTS["check3"] = check3

# ============================================================================
# 4. 品类术语表在 NLLB-only 路径上是否生效
# ============================================================================
sec("CHECK 4 | 品类术语表是否作用于 NLLB-only 路径")
SENT_ES = "Las balatas y el aceite lubricante son originales."
gl_es = markets.get_glossary("汽车与摩托", "es")
print(f"句子: {SENT_ES}   (src='es-MX', dst='zh-CN')")
print(f"注入术语表 = markets.get_glossary('汽车与摩托','es') -> {len(gl_es)} 条；"
      f"balatas={gl_es.get('balatas')!r}, aceite lubricante={gl_es.get('aceite lubricante')!r}")

check4 = {"glossary_es_count": len(gl_es)}

# (a) 在线路径
asr_engine.set_terminology(prompt="", glossary=gl_es)
translate_core.set_engine("api")
translate_core.clear_cache()
t0 = time.perf_counter()
try:
    out_a = translate_core.translate(SENT_ES, src="es-MX", dst="zh-CN")
    err_a = ""
except Exception as e:
    out_a, err_a = None, f"{type(e).__name__}: {e}"
ta = time.perf_counter() - t0
sub("4a) 在线路径（set_engine('api')，clear_cache 后）")
print(f"  engine_mode={translate_core.engine_status()['mode']}")
print(f"  online result: {out_a!r}   ({ta:.2f}s){('  ERR=' + err_a) if err_a else ''}")
check4["a_online"] = {"result": out_a, "seconds": ta, "error": err_a}

# (b) NLLB-only 路径（带术语表）
translate_core.set_engine("nllb")
translate_core.clear_cache()
t0 = time.perf_counter()
try:
    out_b = translate_core.translate(SENT_ES, src="es-MX", dst="zh-CN")
    err_b = ""
except Exception as e:
    out_b, err_b = None, f"{type(e).__name__}: {e}"
tb = time.perf_counter() - t0
sub("4b) NLLB-only 路径（set_engine('nllb')，带品类术语表）")
print(f"  engine_mode={translate_core.engine_status()['mode']}")
print(f"  nllb result  : {out_b!r}   ({tb:.2f}s){('  ERR=' + err_b) if err_b else ''}")
check4["b_nllb_with_glossary"] = {"result": out_b, "seconds": tb, "error": err_b}

# (c) NLLB-only 路径（术语表清空）
asr_engine.set_terminology(prompt="", glossary={})
translate_core.clear_cache()
t0 = time.perf_counter()
try:
    out_c = translate_core.translate(SENT_ES, src="es-MX", dst="zh-CN")
    err_c = ""
except Exception as e:
    out_c, err_c = None, f"{type(e).__name__}: {e}"
tc = time.perf_counter() - t0
sub("4c) NLLB-only 路径（set_terminology(prompt='', glossary={}) 后重跑）")
print(f"  术语表条数 = {len(asr_engine.get_glossary())}")
print(f"  nllb result  : {out_c!r}   ({tc:.2f}s){('  ERR=' + err_c) if err_c else ''}")
print(f"\n  (b) 与 (c) 输出相同? {out_b == out_c}")
check4["c_nllb_no_glossary"] = {"result": out_c, "seconds": tc, "error": err_c}
check4["glossary_changed_nllb_output"] = (out_b != out_c)
RESULTS["check4"] = check4

# ============================================================================
# 5. src="auto" 在 NLLB 路径上
# ============================================================================
sec("CHECK 5 | src='auto' 在 NLLB 路径上的行为")
auto_code = nllb_translate.to_nllb_code("auto")
print(f"nllb_translate.to_nllb_code('auto') = {auto_code!r}")
print(f"nllb_translate.to_nllb_code('pt-BR') = {nllb_translate.to_nllb_code('pt-BR')!r}")
print(f"nllb_translate.to_nllb_code('en-US') = {nllb_translate.to_nllb_code('en-US')!r}")
print(f"LANG_CODES 里有 'auto' 键吗: {'auto' in nllb_translate.LANG_CODES}")

translate_core.set_engine("nllb")
translate_core.clear_cache()
t0 = time.perf_counter()
try:
    out_auto = translate_core.translate("This drill is great", src="auto", dst="zh-CN")
    err_auto = ""
except Exception as e:
    out_auto, err_auto = None, f"{type(e).__name__}: {e}"
t_auto = time.perf_counter() - t0
sub("nllb 模式下 translate('This drill is great', src='auto', dst='zh-CN')")
print(f"  result: {out_auto!r}   ({t_auto:.2f}s){('  ERR=' + err_auto) if err_auto else ''}")

# 对照：显式 en-US / pt-BR，看 auto 更像哪一个
translate_core.clear_cache()
out_en = translate_core.translate("This drill is great", src="en-US", dst="zh-CN")
translate_core.clear_cache()
try:
    out_pt = nllb_translate.translate("Hoje eu trouxe uma parafusadeira muito potente.", src="pt-BR",
                                      tgt="zh-CN")
except Exception as e:
    out_pt = f"<ERR {type(e).__name__}: {e}>"
print(f"  对照 (src='en-US'): {out_en!r}")
print(f"  对照 (src='auto' 但文本是葡语, 走 nllb_translate 直调): {out_pt!r}")
RESULTS["check5"] = {
    "to_nllb_code_auto": auto_code,
    "result_auto": out_auto,
    "seconds": t_auto,
    "error": err_auto,
    "control_en": out_en,
    "control_pt_text_auto": out_pt,
}

# ============================================================================
# 6. 网络全挂时的最坏停顿（合成测量）
# ============================================================================
sec("CHECK 6 | 合成测量：网络全挂时的最坏停顿（SYNTHETIC / 非真实网络）")
print("※ 本节为合成测量：手工把 _CHANNELS 换成 3 个 sleep(8.0) 后抛 TimeoutError 的假函数，")
print("  不依赖真实网络。retries 用 app 默认值 2。")

_orig_channels = translate_core._CHANNELS
print(f"原始 _CHANNELS = {tuple(f.__name__ for f in _orig_channels)}")
print(f"translate() 默认 retries = "
      f"{translate_core.translate.__defaults__}")


def _fake_a(text, src, dst):
    FAKE_CALLS["n"] += 1
    time.sleep(8.0)
    raise TimeoutError("synthetic timeout A")


def _fake_b(text, src, dst):
    FAKE_CALLS["n"] += 1
    time.sleep(8.0)
    raise TimeoutError("synthetic timeout B")


def _fake_c(text, src, dst):
    FAKE_CALLS["n"] += 1
    time.sleep(8.0)
    raise TimeoutError("synthetic timeout C")


try:
    translate_core.set_engine("api")          # 关掉 NLLB 兜底，隔离在线通道耗时
    translate_core._CHANNELS = (_fake_a, _fake_b, _fake_c)
    translate_core.clear_cache()
    uniq = f"__audit_stall_{time.time_ns()}__"   # 唯一文本，绕开翻译缓存
    FAKE_CALLS["n"] = 0
    t0 = time.perf_counter()
    res6 = translate_core.translate(uniq, src="pt-BR", dst="zh-CN", retries=2)
    wall = time.perf_counter() - t0
finally:
    translate_core._CHANNELS = _orig_channels
    translate_core.set_engine("auto")
    translate_core.clear_cache()

print(f"  engine_mode(测量时) = 'api'（只走在线通道）")
print(f"  假通道被调用次数 = {FAKE_CALLS['n']}  (3 通道 x retries=2 = 6)")
print(f"  假通道每次 sleep = 8.0 s")
print(f"  实测 wall-clock = {wall:.2f} s")
print(f"  translate() 返回 = {res6!r}")
theoretical_calls = 3 * 2
theoretical_sleep = theoretical_calls * 8.0
theoretical_plus_backoff = theoretical_sleep + 0.5 * (1 + 2)
print(f"  源码推算：通道数 3 x timeout 8.0s x retries 2 = {theoretical_sleep:.1f} s 纯超时")
print(f"  再加上 retries 之间的 time.sleep(0.5*(attempt+1)) = 0.5+1.0 = 1.5 s")
print(f"  -> 理论总停顿 ≈ {theoretical_plus_backoff:.1f} s（不含 NLLB 兜底）")
print(f"  还原后 _CHANNELS = {tuple(f.__name__ for f in translate_core._CHANNELS)}")
print(f"  还原后 engine_mode = {translate_core.engine_status()['mode']}")
RESULTS["check6"] = {
    "synthetic": True,
    "fake_channel_calls": FAKE_CALLS["n"],
    "sleep_per_call_s": 8.0,
    "wall_seconds": wall,
    "result": res6,
    "theoretical_timeout_seconds": theoretical_sleep,
    "theoretical_with_backoff_seconds": theoretical_plus_backoff,
}

# ============================================================================
# 收尾
# ============================================================================
translate_core.set_engine("auto")
asr_engine.set_terminology(prompt="", glossary={})
try:
    translate_core.close()
except Exception:
    pass

JSON_PATH = os.path.join(ROOT, "tmp", "audit_translate_results.json")
try:
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[数字明细已写入] {JSON_PATH}")
except Exception as e:
    print(f"\n[写 JSON 失败] {type(e).__name__}: {e}")

print("\nAUDIT COMPLETE")
