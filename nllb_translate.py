# -*- coding: utf-8 -*-
"""NLLB 离线翻译：葡萄牙语 -> 中文，本地 GPU 运行，不依赖任何在线接口。

模型: facebook/nllb-200-distilled-600M 的 CTranslate2 int8 量化版（约 620 MB）
断句: SentencePiece（NLLB 自带）
优点: 无限流、不降级、句级神经翻译，质量远好于抓取式免费接口

单独测试:
    python nllb_translate.py --selftest
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "libs"))
sys.path.insert(0, ROOT)

MODEL_DIR = os.path.join(ROOT, "tmp", "models", "nllb-ct2-int8")
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "tmp", "models"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
# 屏蔽 transformers 引入 TensorFlow 时刷的一堆 oneDNN 日志
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

# NLLB 的语言代码（FLORES-200）。市场档案里已给出 nllb 代码，
# 这里再兜一层：支持直接传 locale（pt-BR / es-MX / en-US / zh-CN）。
LANG_CODES = {
    "pt": "por_Latn",
    "pt-br": "por_Latn",
    "pt-pt": "por_Latn",
    "es": "spa_Latn",
    "es-mx": "spa_Latn",
    "es-ar": "spa_Latn",
    "es-es": "spa_Latn",
    "en": "eng_Latn",
    "en-us": "eng_Latn",
    "en-gb": "eng_Latn",
    "zh": "zho_Hans",
    "zh-cn": "zho_Hans",
    "zh-tw": "zho_Hant",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "it": "ita_Latn",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "ru": "rus_Cyrl",
    "ar": "arb_Arab",
    "hi": "hin_Deva",
    "id": "ind_Latn",
    "th": "tha_Thai",
    "vi": "vie_Latn",
    "tr": "tur_Latn",
    "nl": "nld_Latn",
    "pl": "pol_Latn",
    # 也接受 FLORES 原始写法
    "por_latn": "por_Latn",
    "spa_latn": "spa_Latn",
    "eng_latn": "eng_Latn",
    "zho_hans": "zho_Hans",
}


def to_nllb_code(code: str, default: str = "eng_Latn") -> str:
    """把 locale / Whisper 语言代码统一成 NLLB 的 FLORES-200 代码。"""
    c = (code or "").strip()
    if not c:
        return default
    hit = LANG_CODES.get(c.lower())
    if hit:
        return hit
    # 退一步：只取主语言部分（zz-ZZ -> zz）
    return LANG_CODES.get(c.split("-")[0].lower(), default)

_translator = None
_tok = None
_lock = threading.Lock()
_load_error: str | None = None


def available() -> bool:
    """模型文件是否齐全。"""
    need = ["model.bin", "shared_vocabulary.txt", "sentencepiece.bpe.model"]
    return all(os.path.exists(os.path.join(MODEL_DIR, f)) for f in need)


def _load():
    """惰性加载 CT2 翻译器和 NLLB tokenizer。

    注意：必须用 NLLB 自己的 tokenizer，它会按 FLORES 规则在句首插入源语言标记。
    直接用裸 SentencePiece 会编出错 token，模型会退化成反复输出同一个词。
    """
    global _translator, _tok, _load_error
    with _lock:
        if _translator is not None:
            return
        if not available():
            raise FileNotFoundError(
                f"本地没有 NLLB 模型，先运行：python fetch_nllb.py\n（期望目录：{MODEL_DIR}）"
            )
        import ctranslate2
        from transformers import AutoTokenizer

        _load_error = []
        for device, ct in (("cuda", "int8_float16"), ("cpu", "int8")):
            try:
                _translator = ctranslate2.Translator(MODEL_DIR, device=device, compute_type=ct)
                break
            except Exception as e:
                _load_error.append(f"{device}: {e}")
        if _translator is None:
            raise RuntimeError(f"NLLB 加载失败：{_load_error}")
        _tok = AutoTokenizer.from_pretrained(MODEL_DIR)


def _encode(text: str, src_code: str) -> list[str]:
    """用 NLLB tokenizer 编码。

    必须走 tokenizer 的完整流程（它会插入源语言标记，如 por_Latn）。
    实测：漏掉这个标记模型会退化成复读机；自己手工拼 token 也不行。
    """
    _tok.src_lang = src_code
    ids = _tok(text)["input_ids"]
    return _tok.convert_ids_to_tokens(ids)


def _detok(pieces: list[str]) -> str:
    ids = _tok.convert_tokens_to_ids(pieces)
    return _tok.decode(ids, skip_special_tokens=True)


# 强制修正表：NLLB 600M 对五金术语译得不准，这里做确定性修正。
# 左边是模型/接口常见的错误说法，右边是标准说法。顺序重要：先长词后短词。
FORCE = [
    ("螺旋", "电动螺丝刀"),          # parafusadeira
    ("螺栓", "电动螺丝刀"),          # parafusadeira（批量模式常见的另一种错译）
    ("钻机", "电钻"),                # furadeira
    ("行李箱", "工具箱"),            # maleta
    ("手提箱", "工具箱"),
    ("黄色车", "黄色购物车"),        # carrinho amarelo
    ("车里", "购物车"),              # carrinho
    ("播放", "直播"),                # transmissão（仅在"价格/独家"语境）
    ("现场", "直播"),                # live（"欢迎来到我的现场"应译"直播"）
    ("裂钥匙", "一字螺丝刀"),        # chave de fenda
    ("这个子", "这把钳子"),          # alicate
    ("这种材", "这种材质"),          # material（NLLB 会漏字）
    ("不钢", "不锈钢"),              # aço inoxidável
    ("免邮费", "免运费"),
]
# 只在这些葡语词出现时才做上面的替换，避免误伤普通句子
FORCE_TRIGGER = {
    "parafusadeira": ["螺旋", "螺栓"],
    "furadeira": ["钻机"],
    "maleta": ["行李箱", "手提箱"],
    "carrinho": ["黄色车", "车里"],
    "transmissão": ["播放"],
    "live": ["现场"],
    "chave de fenda": ["裂钥匙"],
    "alicate": ["这个子"],
    "material": ["这种材"],
    "aço": ["不钢"],
}


def _postprocess(text: str, src_text: str = "") -> str:
    """按原文修正译文里的错误说法。

    同样先保护"已经是正确说法"的片段，避免把已经译对的词改坏
    （和 translate_core.apply_glossary 用同一套思路）。
    """
    out = text.strip()
    low = (src_text or "").lower()
    slots: list[str] = []
    for right in sorted({r for _, r in FORCE}, key=len, reverse=True):
        if right and right in out:
            out = out.replace(right, f"\x00{len(slots)}\x00")
            slots.append(right)
    for trigger, wrongs in FORCE_TRIGGER.items():
        if trigger not in low:
            continue
        for wrong, right in FORCE:
            if wrong in wrongs and wrong in out:
                out = out.replace(wrong, right)
    for i, right in enumerate(slots):
        out = out.replace(f"\x00{i}\x00", right)
    return out


def suspicious(src_text: str, zh: str) -> bool:
    """判断 NLLB 译文是否可疑（幻觉），可疑时让上层回退到在线接口。

    实测 600M 模型偶发幻觉，例如：
      "Essa furadeira vem com maleta completa." -> "这小伙子带着完整的行李."
    （把 furadeira 当成"小伙子"，且丢掉了 maleta=工具箱）
    判定依据：译文过短、或对不上原文里的专业术语。
    """
    if not zh:
        return True
    src = (src_text or "").lower()
    # 1) 译文短得离谱
    zh_len = sum(1 for c in zh if "\u4e00" <= c <= "\u9fff")
    src_words = len([w for w in re.split(r"\W+", src) if w])
    if src_words >= 6 and zh_len < max(4, src_words // 3):
        return True
    # 2) 原文有工具术语，译文里却一个对应中文都没有
    TERM_HINTS = {
        "parafusadeira": ["螺丝刀", "起子"],
        "furadeira": ["电钻", "钻"],
        "alicate": ["钳"],
        "maleta": ["工具箱", "箱"],
        "soquete": ["套筒"],
        "martelo": ["锤"],
        "chave de fenda": ["螺丝刀", "起子"],
        "bateria": ["电池"],
        "carregador": ["充电器"],
        "carrinho": ["购物车", "车"],
    }
    for pt, hints in TERM_HINTS.items():
        if pt not in src:
            continue
        if not any(h in zh for h in hints):
            return True
    return False


def translate(text: str, src: str = "pt", tgt: str = "zh-CN",
              beam_size: int = 2, max_batch: int = 1) -> str | None:
    """把一段葡语翻译成中文；失败返回 None。"""
    text = (text or "").strip()
    if not text:
        return None
    _load()
    src_code = to_nllb_code(src, "por_Latn")
    tgt_code = to_nllb_code(tgt, "zho_Hans")
    try:
        tokens = _encode(text, src_code)
    except Exception:
        return None
    if not tokens:
        return None
    try:
        results = _translator.translate_batch(
            [tokens],
            # 必须带 target_prefix，否则模型会用默认语言输出（实测会跑出巴斯克语等）
            target_prefix=[[tgt_code]],
            beam_size=beam_size,
            max_decoding_length=256,
            length_penalty=1.0,
            repetition_penalty=1.1,
        )
    except Exception:
        return None
    if not results:
        return None
    hyp = results[0].hypotheses[0] if results[0].hypotheses else []
    # 去掉语言标记和特殊符号
    out_tokens = [t for t in hyp if t not in (tgt_code, src_code, "</s>", "<s>", "<pad>")]
    text_out = _detok(out_tokens)
    return _postprocess(text_out, text) or None


def translate_batch(texts: list[str], src: str = "pt", tgt: str = "zh-CN",
                    beam_size: int = 2) -> list[str | None]:
    """批量翻译（同一批共用一个 batch，比逐句快）。"""
    if not texts:
        return []
    _load()
    tgt_code = to_nllb_code(tgt, "zho_Hans")
    src_code = to_nllb_code(src, "por_Latn")
    token_lists = []
    keep = []
    for i, t in enumerate(texts):
        t = (t or "").strip()
        if t:
            tk = _encode(t, src_code)
            if tk:
                token_lists.append(tk)
                keep.append(i)
    out: list[str | None] = [None] * len(texts)
    if not token_lists:
        return out
    try:
        results = _translator.translate_batch(
            token_lists,
            target_prefix=[[tgt_code]] * len(token_lists),
            beam_size=beam_size,
            max_decoding_length=256,
            length_penalty=1.0,
            repetition_penalty=1.1,
        )
    except Exception:
        return out
    for idx, res in zip(keep, results):
        hyp = res.hypotheses[0] if res.hypotheses else []
        toks = [t for t in hyp if t not in (tgt_code, src_code, "</s>", "<s>", "<pad>")]
        out[idx] = _postprocess(_detok(toks), texts[idx]) or None
    return out


if __name__ == "__main__":
    if "--selftest" not in sys.argv:
        print(__doc__)
        sys.exit(0)
    print("模型可用:", available())
    if not available():
        print("先运行: python fetch_nllb.py")
        sys.exit(1)
    t0 = time.time()
    _load()
    print(f"加载耗时 {time.time()-t0:.1f}s")

    CASES = [
        "Olá pessoal, bem-vindos a minha live.",
        "Hoje eu trouxe uma parafusadeira muito potente.",
        "Essa furadeira vem com maleta completa, bateria de 12V e carregador rápido.",
        "O preço está exclusivo na transmissão, aproveitem e cliquem no carrinho amarelo.",
        "Pessoal, olha como esse alicate é resistente, olha a qualidade desse material.",
    ]
    print("\n=== 逐句翻译（含耗时）===")
    for s in CASES:
        t0 = time.time()
        zh = translate(s)
        print(f"  [{time.time()-t0:.2f}s] {s}")
        print(f"           -> {zh}")

    print("\n=== 批量翻译 ===")
    t0 = time.time()
    outs = translate_batch(CASES)
    print(f"  5 句共 {time.time()-t0:.2f}s")
    for s, o in zip(CASES, outs):
        print(f"  {o}")
