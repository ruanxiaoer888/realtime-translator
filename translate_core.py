# -*- coding: utf-8 -*-
"""翻译核心：葡萄牙语 -> 中文。

多通道自动降级，不依赖任何 API Key：
  1. Google 网页翻译接口（clients5，dict-chrome-ex）
  2. MyMemory（备用，单次 500 字符以内）
  3. 有道公开演示接口（备用）
带本地缓存与失败重试，翻译不到时返回 None，不影响主流程。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(ROOT, "tmp", "translate_cache.json")
# 屏蔽 transformers 引入 TensorFlow 时的 oneDNN 日志（noisy 且无意义）
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

_cache: dict[str, str] = {}
_lock = threading.Lock()
_dirty = False


def _load_cache():
    global _cache
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except Exception:
        _cache = {}


def _save_cache():
    global _dirty
    with _lock:
        if not _dirty:
            return
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_cache, f, ensure_ascii=False)
            _dirty = False
        except Exception:
            pass


def _get(url: str, timeout: float = 6.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, context=_CTX, timeout=timeout) as r:
        return r.read()


def _google(text: str, src: str, dst: str) -> str | None:
    q = urllib.parse.quote(text)
    sl = _norm_lang(src, "google")
    tl = _norm_lang(dst, "google")
    url = (
        "https://clients5.google.com/translate_a/t"
        f"?client=dict-chrome-ex&sl={sl}&tl={tl}&q={q}"
    )
    raw = _get(url)
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, list):
        if data and isinstance(data[0], list):
            return "".join(seg[0] for seg in data[0] if seg)
        return "".join(x for x in data if isinstance(x, str)) or None
    if isinstance(data, dict):
        return data.get("sentences") and "".join(s["trans"] for s in data["sentences"])
    return None


def _mymemory(text: str, src: str, dst: str) -> str | None:
    if len(text) > 480:
        text = text[:480]
    sl = _norm_lang(src, "basic")
    if sl == "auto":
        sl = "Autodetect"      # MyMemory 要求显式写 Autodetect
    url = (
        "https://api.mymemory.translated.net/get?q="
        + urllib.parse.quote(text)
        + f"&langpair={sl}|{_norm_lang(dst, 'basic')}"
    )
    data = json.loads(_get(url).decode("utf-8"))
    out = (data.get("responseData") or {}).get("translatedText")
    if out and "MYMEMORY WARNING" not in out.upper():
        return out
    return None


def _youdao(text: str, src: str, dst: str) -> str | None:
    url = (
        "https://aidemo.youdao.com/trans?q="
        + urllib.parse.quote(text)
        + f"&from={_norm_lang(src, 'youdao')}&to={_norm_lang(dst, 'youdao')}"
    )
    data = json.loads(_get(url).decode("utf-8"))
    tr = data.get("translation")
    if isinstance(tr, list) and tr:
        return tr[0]
    return None


_CHANNELS = (_google, _mymemory, _youdao)

# 通道熔断：某个通道失败后在冷却期内直接跳过，不再白等它的超时。
# 实测教训：Google 那条接口在国内时通时不通，一次超时要等 6~8 秒；
# 不做熔断的话，每句字幕都要先等它超时再走兜底，实测 9.0 秒/句，
# 而正常情况下只要 0.1~1.6 秒 —— 直播同传会直接废掉。
_CHANNEL_COOLDOWN = 120.0          # 失败后冷却多少秒再重试该通道
_channel_down: dict[str, float] = {}


def _channel_ok(name: str) -> bool:
    until = _channel_down.get(name)
    if not until:
        return True
    if time.time() >= until:
        _channel_down.pop(name, None)      # 冷却结束，给它一次机会
        return True
    return False


def _mark_channel(name: str, ok: bool):
    if ok:
        _channel_down.pop(name, None)
    else:
        _channel_down[name] = time.time() + _CHANNEL_COOLDOWN


def channel_status() -> dict:
    """各在线通道当前状态（给界面/自检显示用）。"""
    now = time.time()
    return {
        fn.__name__.lstrip("_"): ("可用" if name not in _channel_down or _channel_down[name] <= now
                                 else f"冷却中（{int(_channel_down[name] - now)}s 后重试）")
        for fn in _CHANNELS
        for name in (fn.__name__,)
    }

# 翻译引擎模式：
#   'api'  只用在线接口（带通道熔断）—— **默认**
#   'auto' 在线优先，全部失败时用本地模型兜底
#   'nllb' 只用本地模型
# 默认选 'api' 而不是 'auto'，是因为本地兜底模型 NLLB 是 CC-BY-NC-4.0（禁止商用）。
# 想把本地兜底作为默认，调用方需要显式 set_engine("auto")。
_engine_mode = "api"
_nllb = None


def set_engine(mode: str):
    """切换翻译引擎：auto / nllb / api。"""
    global _engine_mode
    if mode in ("auto", "nllb", "api"):
        _engine_mode = mode


def engine_status() -> dict:
    """返回引擎可用情况，供界面显示。"""
    info = {"mode": _engine_mode, "nllb_available": False, "nllb_loaded": False}
    try:
        import nllb_translate
        info["nllb_available"] = nllb_translate.available()
        info["nllb_loaded"] = nllb_translate._translator is not None
    except Exception:
        pass
    return info


def _try_nllb(text: str, src: str, dst: str):
    """走本地 NLLB；不可用、失败、或译文可疑时返回 None（交给在线接口兜底）。

    实测数据（10 个五金术语）：在线接口命中 9/10，NLLB 600M 只有 5/10。
    所以默认策略是"在线优先、NLLB 兜底"：既保住质量，又不怕接口限流。
    """
    global _nllb
    if _engine_mode == "api":
        return None
    try:
        if _nllb is None:
            import nllb_translate
            if not nllb_translate.available():
                return None
            _nllb = nllb_translate
        out = _nllb.translate(text, src=src, tgt=dst)
        if out and _nllb.suspicious(text, out):
            return None          # 疑似幻觉，让在线接口重译
        return out
    except Exception:
        return None

# 术语修正规则：左边是"常见错译"，右边是标准说法。
# 触发条件：当前术语表里有这个原文词。模型/接口把哪个词译错就改哪个，语言无关。
TERM_FIXES = {
    "parafusadeira": [("螺旋", "螺栓"), ("螺丝刀", "起子")],
    "chave de fenda": [("裂钥匙", "螺丝刀")],
    "furadeira": [("钻机", "钻孔机", "演习")],
    "jogo de chaves": [("钥匙",)],
    "jogo de soquetes": [("插座",)],
    "maleta": [("手提箱", "行李箱", "手提包", "公文包", "工具包", "盒子", "外壳")],
    "bateria": [("鼓", "乐团")],
    "carregador": [("装载机",)],
    "carrinho amarelo": [("黄色车",)],
    "frete grátis": [("免邮费", "免费运输", "免费航运", "免费送货")],
    "transmissão ao vivo": [("播放", "现场")],
    "live": [("现场",)],
    "material": [("这种材",)],
    # 汽车与摩托（葡语）
    "pastilha de freio": [("刹车垫", "刹车皮")],
    "óleo lubrificante": [("润滑剂", "润滑油剂")],
    "filtro de óleo": [("机油过滤器", "油滤")],
    "vela de ignição": [("点火塞", "火花塞头")],
    # 西语
    "taladro": [("钻孔机", "钻机"), ("钻头",)],
    "destornillador": [("螺丝刀", "起子")],
    "caja de herramientas": [("行李箱", "手提箱", "工具包")],
    "amoladora": [("磨床", "磨光机"), ("角向磨光机",)],
    "esmeriladora": [("磨床",), ("角向磨光机",)],
    "pastillas de freno": [("刹车垫",)],
    "casco": [("头盔套",)],
    "envío gratis": [("免邮费", "免费运输")],
    # 英语
    "power drill": [("钻孔机",)],
    "screwdriver": [("起子",)],
    "toolbox": [("手提箱", "行李箱")],
    "free shipping": [("免邮费", "免运费")],
}


# 保护标记：替换期间把已经正确的片段临时换成一个不会出现在译文里的占位符。
# \x00 在正常译文里不会出现，且长度短，不会影响字符位置判断。
_PROTECT = "\x00"


def _protect(out: str, terms) -> tuple[str, list[str]]:
    """把"已经是正确说法"的片段临时换成占位符（长的先换，避免短词把长词切碎）。"""
    slots: list[str] = []
    for right in sorted({t for t in terms if t}, key=len, reverse=True):
        if right in out:
            out = out.replace(right, f"{_PROTECT}{len(slots)}{_PROTECT}")
            slots.append(right)
    return out, slots


def _restore(out: str, slots: list[str]) -> str:
    for i, right in enumerate(slots):
        out = out.replace(f"{_PROTECT}{i}{_PROTECT}", right)
    return out


def _apply_fix(out: str, wrong: str, right: str, protect=()) -> str:
    """把 out 里的错误说法换成标准说法，替换期间保护"已经是正确说法"的片段。

    保护必须在**每一次替换前**都做，不能只在整轮开始前做一次：
    前一条规则刚生成的正确说法，会被后一条规则当成错译再改一遍。真实踩到的例子：

        输入: 一把螺丝刀和一把一字螺丝刀      （原文含 parafusadeira + chave de fenda）
        parafusadeira 规则: 螺丝刀 -> 电动螺丝刀      得到 "一把电动螺丝刀和一把一字螺丝刀"
        chave de fenda 规则: 螺丝刀 -> 一字螺丝刀     把刚生成的"电动螺丝刀"改成"电动一字螺丝刀" ✗
    """
    if not wrong or wrong == right or wrong not in out:
        return out
    masked, slots = _protect(out, protect)
    masked = masked.replace(wrong, right)
    return _restore(masked, slots)


def presubstitute_terms(text: str, glossary: dict) -> str:
    """把中文原文里的术语先替换成目标语言的正确说法，然后再翻译。

    正向术语表是「外文 -> 中文」，做「中文 -> 外文」的回复时用不上；
    但先做一次替换，引擎就会沿用正确的术语。实测对比：

        这把电动螺丝刀很耐用，配一个工具箱
          直译   -> Esta chave de fenda elétrica é durável e vem com uma caixa de ferramentas
          预替换 -> Essa parafusadeira é muito resistente e vem com maleta        ← parafusadeira/maleta 都对
        电动螺丝刀和电钻一起买更划算
          直译   -> É mais econômico comprar uma chave de fenda elétrica e furar junto
          预替换 -> É mais econômico comprar parafusadeira e furadeira juntas

    glossary 形如 {中文: 目标语言说法}（markets.get_reverse_glossary）。长的先替换，避免短词先命中。
    """
    out = text or ""
    if not out or not glossary:
        return out
    for cn in sorted(glossary, key=len, reverse=True):
        target = glossary.get(cn)
        if cn and target and cn in out:
            out = out.replace(cn, target)
    return out


def _looks_untranslated(out: str, dst: str) -> bool:
    """判断译文是不是"根本没翻"。

    真实踩到过：MyMemory 偶尔把整句葡语直接译成**英文**返回，例如
        nova, soquete, sextavados, oitava, chaves, felipes e feias
        -> new、socket、hex、octave、keys、felips和ugly
    注意这句里夹了一个中文字「和」，所以不能简单用"有没有汉字"判断，要看比例。

    判据（目标语言是中文时）：
      · 一个汉字都没有，却有 ≥3 个英文单词   -> 没翻
      · 汉字 ≤2 个，却有 ≥5 个英文单词       -> 没翻（上面那种夹一个的情况）
    保留 "1350 RPM"、"42 Nm" 这类本来就该原样保留的片段（英文单词数不足）。
    """
    if not dst or not dst.lower().startswith("zh"):
        return False
    cjk = sum(1 for ch in out if "\u4e00" <= ch <= "\u9fff")
    words = len(re.findall(r"[A-Za-z]{2,}", out))
    return (cjk == 0 and words >= 3) or (cjk <= 2 and words >= 5)


def _glossary_now() -> dict:
    """取当前生效的术语表（由界面按市场/品类注入）。"""
    try:
        import asr_engine
        return asr_engine.get_glossary()
    except Exception:
        return {}


def apply_glossary(text_src: str, text_zh: str | None) -> str | None:
    """按当前术语表修正译文里的错误说法。语言无关：术语表是哪种语言就按哪种匹配。"""
    if not text_src or not text_zh:
        return text_zh
    low = text_src.lower()
    out = text_zh
    glossary = _glossary_now()
    if not glossary:
        return out

    # 1) 收集"当前术语表里的全部正确说法"—— 每次替换前都拿它做保护。
    #    只保护**当前术语表**的译文：修正只会把词改成这些译文，
    #    保护了它们，正确说法就不会被误伤；也不会像"保护所有语种的译文"
    #    那样把待修的错译一起保护掉。
    protect = {v for v in glossary.values() if v}

    # 2) 修错译。注意 protect 要传进去、每次替换前重新保护一遍 ——
    #    上一条规则刚生成的正确说法，否则会被下一条规则当成错译再改一次。
    for term, right in glossary.items():
        if term.lower() not in low:
            continue
        for wrongs in TERM_FIXES.get(term, ()):
            for wrong in wrongs:
                out = _apply_fix(out, wrong, right, protect)
    return out


def _norm_lang(code: str, style: str) -> str:
    """按各接口的要求规范化语言代码。"""
    c = (code or "").strip()
    if not c or c.lower() == "auto":
        return "auto"
    low = c.lower()
    if style == "youdao":
        # 有道：中文用 zh-CHS，其余用两字母
        if low.startswith("zh"):
            return "zh-CHS"
        return low.split("-")[0]
    if style == "basic":
        # MyMemory：只要两字母
        return low.split("-")[0]
    # Google / NLLB：接受 pt-BR、zh-CN 这种完整写法
    return c


def translate(text: str, src: str = "auto", dst: str = "zh-CN", retries: int = 2) -> str | None:
    """翻译一段文本；全部通道失败返回 None。

    src 支持 'auto'（自动检测）或具体语言代码（如 pt、es-MX、en）。
    """
    global _dirty
    text = (text or "").strip()
    if not text:
        return None
    key = hashlib.md5(f"{src}|{dst}|{text}".encode("utf-8")).hexdigest()
    with _lock:
        if key in _cache:
            return _cache[key]

    # 主通道：在线接口（实测术语准确率更高：9/10 vs NLLB 600M 的 5/10）
    if _engine_mode != "nllb":
        for attempt in range(retries):
            for fn in _CHANNELS:
                name = fn.__name__
                if not _channel_ok(name):
                    continue            # 这个通道刚失败过，冷却期内不再白等
                try:
                    out = fn(text, src, dst)
                    if out:
                        out = apply_glossary(text, out.strip())
                        if out and not _looks_untranslated(out, dst):
                            _mark_channel(name, True)
                            with _lock:
                                _cache[key] = out
                                _dirty = True
                            return out
                    _mark_channel(name, False)      # 有响应但没结果/没真译，同样算这个通道不行
                except Exception:
                    _mark_channel(name, False)
                    continue
            if all(not _channel_ok(f.__name__) for f in _CHANNELS):
                break                   # 全都在冷却，别再睡退避了，直接走本地兜底
            time.sleep(0.5 * (attempt + 1))

    # 兜底（或用户选了"仅本地"）：NLLB 离线翻译
    nllb_out = _try_nllb(text, src, dst)
    if nllb_out:
        with _lock:
            _cache[key] = nllb_out
            _dirty = True
        return nllb_out
    return None


def close():
    _save_cache()


def clear_cache():
    """清空内存翻译缓存（对比测试、或想强制重译时用）。"""
    global _dirty
    with _lock:
        _cache.clear()
        _dirty = True
    _save_cache()


_load_cache()
