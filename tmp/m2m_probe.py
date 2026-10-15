# -*- coding: utf-8 -*-
r"""M2M-100 418M (CTranslate2, MIT) 离线翻译可行性探针。

步骤：
  1. 从 hf-mirror.com 下载 JustFrederik int8 CT2 模型 + facebook/m2m100_418M 的 tokenizer 文件
  2. 从 tokenizer 里推导真正的目标语言前缀 token（不猜）
  3. 葡语/西语 -> 中文，逐句打印，检查是否真人话
  4. 测速（GPU / CPU）并做三方质量对比（在线接口 / NLLB-600M / M2M-100）

只写 tmp\ 下的新文件，不改动项目里任何已有文件。
在线翻译统一走 translate_core，但把它的磁盘缓存改写到 tmp\m2m_online_cache.json，
避免碰到已有的 tmp\translate_cache.json。

运行：
    python tmp\m2m_probe.py --steps 1
    python tmp\m2m_probe.py --steps 2,3
    python tmp\m2m_probe.py                 # 全部

额外诊断（beam 消融，结论不受影响）：
    python tmp\m2m_probe.py --steps 2,3 --beam 5
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
import sys
import time
import traceback
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "tmp")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "libs"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

# 让 transformers 的缓存也落在 tmp\models 下（不要写到用户目录，且离线）
os.environ.setdefault("HF_HOME", os.path.join(TMP, "models"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

MIRROR = "https://hf-mirror.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

CT2_REPO = "JustFrederik/m2m_100_418m_ct2_int8"
TOK_REPO = "facebook/m2m100_418M"
FALLBACK_REPO = "michaelfeil/ct2fast-m2m100_418M"

MODEL_DIR = os.path.join(TMP, "models", "m2m-ct2-int8")     # 首选：int8 权重 + facebook tokenizer
FALLBACK_DIR = os.path.join(TMP, "models", "m2m-ct2-fast")  # 备选：float32 权重
RESULT_FILE = os.path.join(TMP, "m2m_probe_result.json")

CT2_FILES = ["model.bin", "shared_vocabulary.txt", "spm.128k.model", "config.json"]
# AutoTokenizer 真正需要的两个文件是 vocab.json + sentencepiece.bpe.model
# （见 libs\transformers\models\m2m_100\tokenization_m2m_100.py 的 VOCAB_FILES_NAMES），
# 其余是配置，为可复现一并抓下来。
TOK_FILES = ["vocab.json", "sentencepiece.bpe.model", "tokenizer_config.json",
             "special_tokens_map.json", "generation_config.json"]

PT_SENTENCES = [
    "Olá pessoal, bem-vindos a minha live.",
    "Hoje eu trouxe uma parafusadeira muito potente.",
    "Essa furadeira vem com maleta completa, bateria de 12V e carregador rápido.",
    "O preço está exclusivo na transmissão, aproveitem e cliquem no carrinho amarelo.",
    "Pessoal, olha como esse alicate é resistente, olha a qualidade desse material.",
    "Quanto custa o frete para São Paulo?",
]
ES_SENTENCES = ["Las balatas y el aceite lubricante son originales."]

# 术语打分用（只在原文出现该词时才算分）
TERM_HINTS = [
    ("parafusadeira", ["电动螺丝刀", "螺丝刀", "起子", "电批"]),
    ("furadeira", ["电钻", "钻孔机", "钻"]),
    ("maleta", ["工具箱", "工具包", "箱"]),
    ("alicate", ["钳"]),
    ("carrinho amarelo", ["购物车"]),
    ("frete", ["运费", "邮费", "货运", "快递"]),
]

DL = {"bytes": 0, "fresh": 0, "skipped": 0, "skipped_bytes": 0, "failed": []}
STATE: dict = {}


def hr(title: str = ""):
    print("\n" + "=" * 78)
    if title:
        print(title)
        print("=" * 78)


def _log(msg: str):
    print(msg, flush=True)


# ----------------------------------------------------------------------------
# 第 1 步：下载
# ----------------------------------------------------------------------------
def download_file(repo: str, fname: str, dest: str, retries: int = 3) -> bool:
    """下载单个文件；已存在且非空则跳过。返回是否成功。"""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        n = os.path.getsize(dest)
        DL["skipped"] += 1
        DL["skipped_bytes"] += n
        _log(f"  [跳过] {fname} 已存在 {n / 1e6:.1f} MB")
        return True
    url = f"{MIRROR}/{repo}/resolve/main/{fname}"
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            t0 = time.perf_counter()
            done = 0
            last_report = 0
            total = 0
            with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    DL["bytes"] += len(chunk)
                    if done - last_report >= (16 << 20):
                        last_report = done
                        pct = f"{done / total * 100:5.1f}%" if total else "  ?  "
                        spd = done / 1e6 / max(time.perf_counter() - t0, 1e-6)
                        _log(f"    {fname}: {done / 1e6:7.1f} MB {pct}  {spd:5.2f} MB/s")
            if total and done != total:
                raise IOError(f"大小不符 {done} != {total}")
            if done == 0:
                raise IOError("空文件")
            os.replace(part, dest)
            DL["fresh"] += 1
            _log(f"  [完成] {fname} {done / 1e6:.1f} MB / {time.perf_counter() - t0:.1f}s")
            return True
        except Exception as e:
            _log(f"  [失败 {attempt}/{retries}] {fname}: {type(e).__name__}: {str(e)[:160]}")
            try:
                os.remove(part)
            except Exception:
                pass
            time.sleep(2 * attempt)
    DL["failed"].append(f"{repo}/{fname}")
    return False


def _load_ct2_quick(device: str = "cpu", compute_type: str = "int8"):
    """试着加载 CT2，返回 (translator|None, 错误信息)。"""
    import ctranslate2
    try:
        t = ctranslate2.Translator(MODEL_DIR, device=device, compute_type=compute_type)
        return t, ""
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:300]}"


def _try_auto_tokenizer(**kw):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True, **kw)


def load_tokenizer():
    """拿到 M2M100 自己的 tokenizer，并把走通的那条路记下来。
    坑：facebook/m2m100_418M 的 tokenizer_config.json 里**没有** tokenizer_class，
    AutoTokenizer 于是去读 config.json 判断模型类型；但同一目录里的 config.json
    是 CTranslate2 的（只有 bos/eos/decoder_start_token，没有 model_type），
    直接报 "Unrecognized model in ... Should have a `model_type` key"。
    所以按 A/A2/B/C 依次降级，谁先走通用谁。
    """
    if STATE.get("tok") is not None:
        return STATE["tok"]
    from transformers import AutoConfig, M2M100Tokenizer
    cfg_path = os.path.join(MODEL_DIR, "config.json")
    hf_path = os.path.join(MODEL_DIR, "hf_config.json")
    bak_path = os.path.join(MODEL_DIR, "config.json.ct2")
    errs: list[str] = []

    # A) 原样 AutoTokenizer.from_pretrained(dir)
    try:
        tok = _try_auto_tokenizer()
        STATE["tok"] = tok
        STATE["tok_route"] = "A: AutoTokenizer.from_pretrained(dir) 直接可用"
        STATE["tok_notes"] = errs
        return tok
    except Exception as e:
        errs.append(f"A 失败: {type(e).__name__}: {str(e)[:140]}")

    # A2) 给 CT2 的 config.json 补一个 model_type，让 AutoConfig 能识别（前提：CT2 仍能加载）
    if os.path.exists(cfg_path) and os.path.exists(bak_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            cfg_patched = dict(cfg)
            cfg_patched["model_type"] = "m2m_100"
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg_patched, f, indent=2, ensure_ascii=False)
            t, cerr = _load_ct2_quick()
            if t is not None:
                del t
                tok = _try_auto_tokenizer()
                STATE["tok"] = tok
                STATE["tok_route"] = ("A2: 给 CT2 的 config.json 加 \"model_type\": \"m2m_100\" 后，"
                                      "AutoTokenizer.from_pretrained(dir) 可用，且 CT2 仍能加载")
                STATE["tok_notes"] = errs
                return tok
            errs.append(f"A2 失败: 加 model_type 后 CT2 反而加载不了: {cerr}")
            shutil.copy2(bak_path, cfg_path)
        except Exception as e:
            errs.append(f"A2 失败: {type(e).__name__}: {str(e)[:140]}")
            try:
                shutil.copy2(bak_path, cfg_path)
            except Exception:
                pass

    # B) 显式把 hf_config.json 交给 AutoTokenizer
    if os.path.exists(hf_path):
        try:
            hf_cfg = AutoConfig.from_pretrained(hf_path, local_files_only=True)
            tok = _try_auto_tokenizer(config=hf_cfg)
            STATE["tok"] = tok
            STATE["tok_route"] = "B: AutoTokenizer.from_pretrained(dir, config=AutoConfig(hf_config.json)) 可用"
            STATE["tok_notes"] = errs
            return tok
        except Exception as e:
            errs.append(f"B 失败: {type(e).__name__}: {str(e)[:140]}")

    # C) 直接用模型自己的 tokenizer 类
    try:
        tok = M2M100Tokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
        STATE["tok"] = tok
        STATE["tok_route"] = "C: M2M100Tokenizer.from_pretrained(dir) 可用（绕开 AutoTokenizer）"
        STATE["tok_notes"] = errs
        return tok
    except Exception as e:
        errs.append(f"C 失败: {type(e).__name__}: {str(e)[:140]}")

    STATE["tok_notes"] = errs
    raise RuntimeError("tokenizer 全部路线失败: " + " || ".join(errs))


def step1():
    hr("[1] 下载模型与 tokenizer")
    os.makedirs(MODEL_DIR, exist_ok=True)
    _log(f"  目标目录: {MODEL_DIR}")
    _log(f"  镜像: {MIRROR}")
    _log(f"  -- CT2 int8 权重: {CT2_REPO}")
    for f in CT2_FILES:
        download_file(CT2_REPO, f, os.path.join(MODEL_DIR, f))

    ct2_cfg = os.path.join(MODEL_DIR, "config.json")
    cfg_bak = os.path.join(MODEL_DIR, "config.json.ct2")
    if os.path.exists(ct2_cfg) and not os.path.exists(cfg_bak):
        shutil.copy2(ct2_cfg, cfg_bak)
        _log(f"  [备份] config.json -> config.json.ct2")

    _log(f"  -- tokenizer: {TOK_REPO}")
    for f in TOK_FILES:
        download_file(TOK_REPO, f, os.path.join(MODEL_DIR, f))
    # facebook 的 config.json 会覆盖 CT2 的 config.json，所以先存成 hf_config.json
    download_file(TOK_REPO, "config.json", os.path.join(MODEL_DIR, "hf_config.json"))

    # --- 关键检查：CT2 词表与 tokenizer 词表的语言 token 位置是否一致 ---
    _log("\n  [检查] tokenizer 加载路线 + shared_vocabulary.txt 语言 token 对齐")
    tok = None
    try:
        tok = load_tokenizer()
        _log(f"    tokenizer 路线: {STATE.get('tok_route')}")
        for n in STATE.get("tok_notes", []):
            _log(f"      （先前失败）{n}")
        with open(os.path.join(MODEL_DIR, "shared_vocabulary.txt"), encoding="utf-8") as f:
            ct2_vocab = [ln.rstrip("\n") for ln in f]
        ct2_index = {t: i for i, t in enumerate(ct2_vocab)}
        STATE["ct2_vocab_rows"] = len(ct2_vocab)
        STATE["tok_vocab_size"] = tok.vocab_size
        align_ok = True
        for lang in ("pt", "es", "zh", "en"):
            t = f"__{lang}__"
            tid = tok.get_lang_id(lang)
            cid = ct2_index.get(t, -1)
            align_ok &= (tid == cid)
            _log(f"    {t:8s} tokenizer_id={tid:7d}  ct2_vocab_index={cid:7d}  "
                 f"{'一致' if tid == cid else '不一致!'}")
        STATE["vocab_aligned"] = align_ok
        _log(f"    CT2 词表 {len(ct2_vocab)} 行; tokenizer 基础词表 {tok.vocab_size} 个")
    except Exception as e:
        _log(f"    [失败] {type(e).__name__}: {str(e)[:300]}")

    # --- 实验：用 transformers 版 config.json 覆盖 CT2 config.json，看还能否加载 ---
    _log("\n  [实验] 把 hf_config.json 覆盖成 config.json，再试 CT2 加载")
    hf_cfg = os.path.join(MODEL_DIR, "hf_config.json")
    if os.path.exists(hf_cfg):
        # 记住覆盖前 config.json 的原文（可能是原来的 CT2 配置，也可能是 A2 路线补过 model_type 的版本）
        with open(ct2_cfg, encoding="utf-8") as f:
            cfg_before = f.read()
        shutil.copy2(hf_cfg, ct2_cfg)
        t, err = _load_ct2_quick()
        STATE["overwrite_config_loads"] = t is not None
        if t is None:
            _log(f"    覆盖后加载失败: {err}")
        else:
            _log("    覆盖后加载成功 -> 跑一句看输出是否正常")
            try:
                out = m2m_translate(t, STATE["tok"], PT_SENTENCES[0], src="pt", tgt="zh", beam=2)
                STATE["overwrite_config_sample"] = out
                _log(f"    输出: {out}")
            except Exception as e:
                STATE["overwrite_config_sample"] = f"{type(e).__name__}: {str(e)[:200]}"
                _log(f"    翻译失败: {type(e).__name__}: {str(e)[:200]}")
            del t
        # 原样写回覆盖前的 config.json
        with open(ct2_cfg, "w", encoding="utf-8") as f:
            f.write(cfg_before)
        t2, err2 = _load_ct2_quick()
        STATE["restored_config_loads"] = t2 is not None
        _log(f"    写回原 config.json 后加载: {'成功' if t2 is not None else '失败 ' + err2}")
        if t2 is not None:
            del t2
        _log(f"    结论: 换成 transformers 版 config.json 后 CT2 "
             f"{'能' if STATE['overwrite_config_loads'] else '不能'}加载 -> "
             f"{'可以' if STATE['overwrite_config_loads'] else '必须保留 CT2 自己的 config.json'}")
    else:
        _log("    [跳过] 缺 hf_config.json")

    # --- 检查 tokenizer 到底需要哪些文件 ---
    _log("\n  [检查] tokenizer 最少需要哪些文件")
    try:
        import sentencepiece  # noqa: F401
        from transformers import M2M100Tokenizer
        minimal = M2M100Tokenizer(
            vocab_file=os.path.join(MODEL_DIR, "vocab.json"),
            spm_file=os.path.join(MODEL_DIR, "sentencepiece.bpe.model"),
        )
        tok = STATE["tok"]
        same = all(minimal.get_lang_id(l) == tok.get_lang_id(l) for l in ("pt", "es", "zh", "en"))
        STATE["minimal_tok_matches"] = same
        _log(f"    只给 vocab.json + sentencepiece.bpe.model 构造 M2M100Tokenizer: OK，"
             f"语言 token id 与完整版一致={same}")
        _log("    => 这两个文件是硬需求；tokenizer_config.json / special_tokens_map.json / "
             "generation_config.json / config.json 都是可选配置")
        # spm.128k.model 与 sentencepiece.bpe.model 是否同一个文件
        import hashlib

        def md5(p):
            h = hashlib.md5()
            with open(p, "rb") as fh:
                for b in iter(lambda: fh.read(1 << 20), b""):
                    h.update(b)
            return h.hexdigest()

        a = md5(os.path.join(MODEL_DIR, "spm.128k.model"))
        b = md5(os.path.join(MODEL_DIR, "sentencepiece.bpe.model"))
        STATE["spm_same"] = (a == b)
        _log(f"    spm.128k.model 与 sentencepiece.bpe.model 内容相同={a == b}")
    except Exception as e:
        _log(f"    [失败] {type(e).__name__}: {str(e)[:300]}")

    total = sum(os.path.getsize(os.path.join(MODEL_DIR, f))
                for f in os.listdir(MODEL_DIR) if os.path.isfile(os.path.join(MODEL_DIR, f)))
    STATE["model_dir"] = MODEL_DIR
    STATE["dir_mb"] = total / 1e6
    _log(f"\n  目录总大小: {total / 1e6:.1f} MB")
    _log(f"  本次新下载: {DL['fresh']} 个文件 {DL['bytes'] / 1e6:.1f} MB; "
         f"跳过已存在: {DL['skipped']} 个 {DL['skipped_bytes'] / 1e6:.1f} MB")
    if DL["failed"]:
        _log(f"  下载失败: {DL['failed']}")
    return True


# ----------------------------------------------------------------------------
# 第 2 步：推导语言 token
# ----------------------------------------------------------------------------
def step2():
    hr("[2] 推导语言 token（不猜，直接问 tokenizer）")
    tok = load_tokenizer()
    STATE["tok"] = tok
    _log(f"  加载路线: {STATE.get('tok_route')}")
    _log(f"  tokenizer 类: {type(tok).__name__}")
    _log(f"  基础词表大小: {tok.vocab_size}  总词表: {len(tok)}")
    _log(f"  language_codes: {tok.language_codes}")
    _log("\n  tokenizer.lang_code_to_token 里我们关心的几个:")
    for lang in ("pt", "es", "en", "zh"):
        token = tok.lang_code_to_token.get(lang)
        _log(f"    {lang:3s} -> token={token!r}  id=convert_tokens_to_ids={tok.convert_tokens_to_ids(token)}"
             f"  get_lang_id={tok.get_lang_id(lang)}")
    tgt = tok.get_lang_token("zh")
    src = tok.get_lang_token("pt")
    STATE["tgt_token"] = tgt
    STATE["src_token"] = src
    _log(f"\n  => 目标前缀 target_prefix=[[{tgt!r}]]  源语言标记 {src!r}")
    _log("\n  编码示例（tokenizer 会自动在句首插入源语言标记）:")
    tok.src_lang = "pt"
    ids = tok(PT_SENTENCES[1])["input_ids"]
    _log(f"    {PT_SENTENCES[1]}")
    _log(f"    ids[:8] = {ids[:8]}")
    _log(f"    tokens[:8] = {tok.convert_ids_to_tokens(ids[:8])}")
    return tok


# ----------------------------------------------------------------------------
# 翻译核心
# ----------------------------------------------------------------------------
def health_check(zh: str) -> list[str]:
    """第 3 步要求的健康检查：空输出 / 不是中文 / 复读 / 含未译标记。"""
    if zh is None or not zh.strip():
        return ["空输出"]
    flags = []
    cjk = sum(1 for c in zh if "\u4e00" <= c <= "\u9fff")
    latin = sum(1 for c in zh if c.isascii() and c.isalpha())
    if cjk == 0:
        flags.append("没有汉字（可能跑成别的语言）")
    elif latin > cjk:
        flags.append(f"拉丁字母 {latin} > 汉字 {cjk}（疑似跑成非中文）")
    if "<unk>" in zh:
        flags.append("含 <unk>：原文里的词模型不认识")
    t = "".join(c for c in zh if c.strip())
    if len(t) >= 8:
        grams = [t[i:i + 2] for i in range(len(t) - 1)]
        top = max(grams.count(g) for g in set(grams))
        if top >= 4:
            flags.append(f"2-gram 重复 {top} 次（疑似复读）")
    return flags


def m2m_translate(translator, tok, text: str, src: str = "pt", tgt: str = "zh",
                  beam: int = 2, target_prefix: bool = True,
                  with_src_token: bool = True, sp=None, raw_out: list | None = None) -> str:
    """M2M-100 翻译一句。target_prefix / with_src_token 用来复现两个已知坑。"""
    if sp is not None:
        tokens = sp.encode(text, out_type=str)
    else:
        tok.src_lang = src
        tokens = tok.convert_ids_to_tokens(tok(text)["input_ids"])
        if not with_src_token and tokens and tokens[0] == tok.get_lang_token(src):
            tokens = tokens[1:]
    kwargs = dict(beam_size=beam, max_decoding_length=256,
                  length_penalty=1.0, repetition_penalty=1.1)
    if target_prefix:
        kwargs["target_prefix"] = [[tok.get_lang_token(tgt)]]
    results = translator.translate_batch([tokens], **kwargs)
    hyp = results[0].hypotheses[0] if results[0].hypotheses else []
    if raw_out is not None:
        raw_out.extend(hyp)
    drop = {"</s>", "<s>", "<pad>", tok.get_lang_token(tgt), tok.get_lang_token(src)}
    out_ids = tok.convert_tokens_to_ids([t for t in hyp if t not in drop])
    return tok.decode(out_ids, skip_special_tokens=True)


def step3(beam: int = 2):
    hr("[3] 翻译验证：葡语 -> 中文 / 西语 -> 中文")
    tok = STATE.get("tok") or step2()
    import ctranslate2
    t, err = None, ""
    for dev, ct in (("cuda", "int8_float16"), ("cuda", "int8"), ("cpu", "int8")):
        try:
            t = ctranslate2.Translator(MODEL_DIR, device=dev, compute_type=ct)
            _log(f"  CT2 已加载: device={dev} compute_type={ct}")
            STATE["load_used"] = f"{dev}/{ct}"
            break
        except Exception as e:
            err += f" | {dev}/{ct}: {type(e).__name__}: {str(e)[:120]}"
            _log(f"  [加载失败] {dev}/{ct}: {type(e).__name__}: {str(e)[:160]}")
    if t is None:
        raise RuntimeError(f"CT2 加载全部失败: {err}")
    STATE["translator"] = t

    _log("\n  -- 6 句葡语（target_prefix 已按第 2 步推导出的 token 传入）--")
    outs = []
    health = {}
    for s in PT_SENTENCES:
        raw: list[str] = []
        try:
            t0 = time.perf_counter()
            zh = m2m_translate(t, tok, s, src="pt", tgt="zh", beam=beam, raw_out=raw)
            dt = time.perf_counter() - t0
        except Exception as e:
            zh = f"<ERROR {type(e).__name__}: {str(e)[:150]}>"
            dt = 0.0
        outs.append(zh)
        hf = health_check(zh)
        health[s] = hf
        _log(f"  PT  : {s}")
        _log(f"  ZH  : {zh}   ({dt:.2f}s)")
        _log(f"  健康检查: {'OK（有汉字、无复读、无空输出）' if not hf else ' / '.join(hf)}")
        if any(x.startswith("madeupword") for x in raw):
            _log(f"  原始输出 token: {raw}")
            _log("  （模型输出了 fairseq 的 madeupword token，HF 词表里没有 -> 会显示成 <unk>）")
        elif "<unk>" in zh:
            _log(f"  原始输出 token: {raw}")
            _log("  （不是词表缺 id 造成的：模型把不认识的原文词直接写成了字面的 <  unk  > 三个 token）")
        _log("")
    STATE["pt_out"] = outs
    STATE["pt_health"] = health
    STATE["raw_outputs"] = [{"pt": s, "zh": z, "health": health[s]}
                            for s, z in zip(PT_SENTENCES, outs)]

    _log("  -- 1 句西语（src=es）--")
    for s in ES_SENTENCES:
        try:
            zh = m2m_translate(t, tok, s, src="es", tgt="zh", beam=beam)
        except Exception as e:
            zh = f"<ERROR {type(e).__name__}: {str(e)[:150]}>"
        hf = health_check(zh)
        STATE.setdefault("es_health", {})[s] = hf
        _log(f"  ES  : {s}")
        _log(f"  ZH  : {zh}")
        _log(f"  健康检查: {'OK' if not hf else ' / '.join(hf)}")
        _log("  人工判读: 期望出现 刹车片 / 润滑油，实际见上（这是西语市场的关键用例）")
        STATE.setdefault("es_out", []).append(zh)

    # --- 复现两个已知坑 ---
    _log("\n  -- 复现坑 1：丢掉源语言标记（用裸 SentencePiece / 去掉 __pt__）--")
    s0 = PT_SENTENCES[1]
    try:
        bare = m2m_translate(t, tok, s0, src="pt", tgt="zh", beam=beam, with_src_token=False)
    except Exception as e:
        bare = f"<ERROR {type(e).__name__}: {str(e)[:150]}>"
    _log(f"  不加 __pt__ 前缀: {bare}")
    try:
        import sentencepiece
        sp = sentencepiece.SentencePieceProcessor()
        sp.Load(os.path.join(MODEL_DIR, "spm.128k.model"))
        raw = m2m_translate(t, tok, s0, src="pt", tgt="zh", beam=beam, sp=sp)
        STATE["bare_spm_out"] = raw
        _log(f"  裸 SentencePiece 编码: {raw}")
    except Exception as e:
        _log(f"  裸 SentencePiece 失败: {type(e).__name__}: {str(e)[:200]}")
    STATE["no_src_token_out"] = bare

    _log("\n  -- 复现坑 2：不传 target_prefix --")
    try:
        nop = m2m_translate(t, tok, s0, src="pt", tgt="zh", beam=beam, target_prefix=False)
    except Exception as e:
        nop = f"<ERROR {type(e).__name__}: {str(e)[:150]}>"
    STATE["no_target_prefix_out"] = nop
    _log(f"  不传 target_prefix: {nop}")
    return outs


# ----------------------------------------------------------------------------
# 第 4 步：测速 + 三方质量对比
# ----------------------------------------------------------------------------
def _bench_one(t, tok, texts, src, tgt, beam, reps):
    rows = []
    m2m_translate(t, tok, texts[0], src=src, tgt=tgt, beam=beam)  # 预热
    for s in texts:
        ts = []
        for _ in range(reps):
            t0 = time.perf_counter()
            m2m_translate(t, tok, s, src=src, tgt=tgt, beam=beam)
            ts.append(time.perf_counter() - t0)
        rows.append({"text": s, "min": min(ts), "mean": sum(ts) / len(ts)})
    # 批量（一句一批 vs 六句一批）
    m2m_translate(t, tok, texts[0], src=src, tgt=tgt, beam=beam)
    tok.src_lang = src
    toks = [tok.convert_ids_to_tokens(tok(s)["input_ids"]) for s in texts]
    t0 = time.perf_counter()
    t.translate_batch(toks, target_prefix=[[tok.get_lang_token(tgt)]] * len(toks),
                      beam_size=beam, max_decoding_length=256, length_penalty=1.0,
                      repetition_penalty=1.1)
    batch = time.perf_counter() - t0
    return rows, batch


def step4(beam: int = 2, reps: int = 3, do_online: bool = True):
    hr("[4] 测速 + 三方质量对比")
    import ctranslate2
    tok = STATE.get("tok")
    if tok is None:
        tok = step2()

    # ---- M2M GPU ----
    bench = {}
    for dev, ct in (("cuda", "int8_float16"), ("cuda", "int8"), ("cuda", "float16")):
        try:
            t = ctranslate2.Translator(MODEL_DIR, device=dev, compute_type=ct)
        except Exception as e:
            _log(f"  [GPU {ct} 不可用] {type(e).__name__}: {str(e)[:140]}")
            continue
        STATE["gpu_compute_type"] = ct
        _log(f"\n  -- M2M-100 GPU ({dev}/{ct}) --")
        rows, batch = _bench_one(t, tok, PT_SENTENCES, "pt", "zh", beam, reps)
        for r in rows:
            _log(f"    {r['min']:.3f}s (均 {r['mean']:.3f}s)  {r['text'][:60]}")
        mean = sum(r["min"] for r in rows) / len(rows)
        _log(f"    单句平均 {mean:.3f}s   6 句一批 {batch:.3f}s")
        bench[f"m2m_gpu_{ct}"] = {"per": rows, "mean": mean, "batch6": batch}
        break

    # ---- M2M CPU ----
    try:
        t = ctranslate2.Translator(MODEL_DIR, device="cpu", compute_type="int8")
        _log(f"\n  -- M2M-100 CPU (cpu/int8, 线程 {os.cpu_count()}) --")
        rows, batch = _bench_one(t, tok, PT_SENTENCES, "pt", "zh", beam, reps)
        for r in rows:
            _log(f"    {r['min']:.3f}s (均 {r['mean']:.3f}s)  {r['text'][:60]}")
        mean = sum(r["min"] for r in rows) / len(rows)
        _log(f"    单句平均 {mean:.3f}s   6 句一批 {batch:.3f}s")
        bench["m2m_cpu_int8"] = {"per": rows, "mean": mean, "batch6": batch}
        del t
    except Exception as e:
        _log(f"  [CPU 失败] {type(e).__name__}: {str(e)[:200]}")
    gc.collect()
    STATE["bench"] = bench

    # ---- NLLB 600M 对照 ----
    _log("\n  -- NLLB-200 600M（项目现用兜底模型）--")
    try:
        import nllb_translate
        t0 = time.perf_counter()
        nllb_translate._load()
        _log(f"    加载 {time.perf_counter() - t0:.1f}s")
        nllb_translate.translate(PT_SENTENCES[0])  # 预热
        rows = []
        for s in PT_SENTENCES:
            ts = []
            for _ in range(reps):
                t0 = time.perf_counter()
                nllb_translate.translate(s)
                ts.append(time.perf_counter() - t0)
            rows.append({"text": s, "min": min(ts), "mean": sum(ts) / len(ts)})
        for r in rows:
            _log(f"    {r['min']:.3f}s (均 {r['mean']:.3f}s)  {r['text'][:60]}")
        mean = sum(r["min"] for r in rows) / len(rows)
        _log(f"    单句平均 {mean:.3f}s")
        bench["nllb_gpu"] = {"per": rows, "mean": mean}
    except Exception as e:
        _log(f"  [NLLB 失败] {type(e).__name__}: {str(e)[:200]}")
        STATE["nllb_error"] = f"{type(e).__name__}: {str(e)[:200]}"

    if not do_online:
        return

    # ---- 在线接口 ----
    hr("[4b] 三方质量对比（在线接口 / NLLB-600M / M2M-100）")
    online, online_gl = {}, {}
    try:
        import translate_core
        # 把缓存文件改到新路径，绝不碰已有的 tmp\translate_cache.json
        translate_core.CACHE_FILE = os.path.join(TMP, "m2m_online_cache.json")
        translate_core.clear_cache()
        translate_core.set_engine("api")   # 只要在线，防止失败时悄悄回退到 NLLB 混淆对比
        _log(f"  translate_core 状态: {translate_core.engine_status()}  "
             f"(缓存写到 {translate_core.CACHE_FILE})")
        for s in PT_SENTENCES:
            translate_core.clear_cache()
            try:
                online[s] = translate_core.translate(s, "pt-BR", "zh-CN")
            except Exception as e:
                online[s] = f"<ERROR {type(e).__name__}: {str(e)[:120]}>"
        # 额外：注入项目自带的五金术语表（生产中 app.py 就是这么用的）
        try:
            import asr_engine
            import markets
            asr_engine.set_terminology(prompt="", glossary=markets.get_glossary("五金工具", "pt"))
            _log(f"  注入五金术语表 {len(markets.get_glossary('五金工具', 'pt'))} 条，再跑一遍在线接口")
            for s in PT_SENTENCES:
                translate_core.clear_cache()
                online_gl[s] = translate_core.translate(s, "pt-BR", "zh-CN")
        except Exception as e:
            _log(f"  术语表注入失败: {type(e).__name__}: {str(e)[:160]}")
    except Exception as e:
        _log(f"  [在线接口不可用] {type(e).__name__}: {str(e)[:200]}")
        STATE["online_error"] = f"{type(e).__name__}: {str(e)[:200]}"

    nllb = {}
    try:
        import nllb_translate
        for s in PT_SENTENCES:
            nllb[s] = nllb_translate.translate(s)
    except Exception as e:
        _log(f"  [NLLB 不可用] {type(e).__name__}: {str(e)[:200]}")

    t = STATE.get("translator")
    if t is None:
        t, _ = _load_ct2_quick("cuda", STATE.get("gpu_compute_type", "int8_float16"))
        if t is None:
            t, _ = _load_ct2_quick("cpu", "int8")
    m2m = {}
    for s in PT_SENTENCES:
        try:
            m2m[s] = m2m_translate(t, tok, s, src="pt", tgt="zh", beam=beam)
        except Exception as e:
            m2m[s] = f"<ERROR {type(e).__name__}: {str(e)[:120]}>"

    rows = []
    for i, s in enumerate(PT_SENTENCES, 1):
        _log(f"\n  [{i}] PT   : {s}")
        _log(f"      API  : {online.get(s)}")
        if s in online_gl:
            _log(f"      API+术语: {online_gl.get(s)}")
        _log(f"      NLLB : {nllb.get(s)}")
        _log(f"      M2M  : {m2m.get(s)}")
        _log(f"      健康检查: API={health_check(online.get(s)) or 'OK'}  "
             f"NLLB={health_check(nllb.get(s)) or 'OK'}  M2M={health_check(m2m.get(s)) or 'OK'}")
        rows.append({"pt": s, "api": online.get(s), "api_glossary": online_gl.get(s),
                     "nllb": nllb.get(s), "m2m": m2m.get(s)})
    STATE["quality_rows"] = rows

    _log("\n  -- 西语对照 --")
    for s in ES_SENTENCES:
        api = nlv = mm = None
        try:
            import translate_core
            translate_core.clear_cache()
            api = translate_core.translate(s, "es-MX", "zh-CN")
        except Exception:
            pass
        try:
            import nllb_translate
            nlv = nllb_translate.translate(s, src="es", tgt="zh-CN")
        except Exception:
            pass
        try:
            mm = m2m_translate(t, tok, s, src="es", tgt="zh", beam=beam)
        except Exception as e:
            mm = f"<ERROR {type(e).__name__}>"
        _log(f"      ES   : {s}")
        _log(f"      API  : {api}")
        _log(f"      NLLB : {nlv}")
        _log(f"      M2M  : {mm}")
        _log(f"      健康检查: API={health_check(api) or 'OK'}  NLLB={health_check(nlv) or 'OK'}  "
             f"M2M={health_check(mm) or 'OK'}（健康检查只看中文/复读，不判术语对错）")
        STATE.setdefault("es_three_way", []).append(
            {"es": s, "api": api, "nllb": nlv, "m2m": mm})

    # ---- 术语打分 ----
    _log("\n  -- 术语命中（子串判定，原文出现该词才算分）--")
    # M2M 再过一遍项目自己的术语表后处理，和生产链路口径一致
    m2m_gl = {}
    try:
        import translate_core as _tc
        for s in PT_SENTENCES:
            m2m_gl[s] = _tc.apply_glossary(s, m2m.get(s))
    except Exception as e:
        _log(f"  M2M+术语表 后处理失败: {type(e).__name__}: {str(e)[:150]}")
    _log("\n  -- M2M 加同样的术语表后处理 --")
    for s in PT_SENTENCES:
        _log(f"      {s}")
        _log(f"      -> {m2m_gl.get(s)}")
    STATE["m2m_glossary_out"] = m2m_gl

    table = {}
    for term, hints in TERM_HINTS:
        src_sentence = next((s for s in PT_SENTENCES if term in s.lower()), None)
        if src_sentence is None:
            continue
        cell = {}
        for label, outputs in (("API", online), ("API+术语", online_gl),
                               ("NLLB", nllb), ("M2M", m2m), ("M2M+术语", m2m_gl)):
            zh = outputs.get(src_sentence) or ""
            ok = any(h in zh for h in hints)
            cell[label] = ok
        table[term] = cell
        _log(f"    {term:18s} 期望 {hints}")
        _log(f"      API={'✓' if cell['API'] else '✗'}  "
             f"API+术语={'✓' if cell['API+术语'] else '✗'}  "
             f"NLLB={'✓' if cell['NLLB'] else '✗'}  M2M={'✓' if cell['M2M'] else '✗'}  "
             f"M2M+术语={'✓' if cell['M2M+术语'] else '✗'}")
    labels = ("API", "API+术语", "NLLB", "M2M", "M2M+术语")
    for label in labels:
        got = sum(1 for c in table.values() if c.get(label))
        _log(f"    {label:10s} {got}/{len(table)}")
    STATE["term_table"] = table
    STATE["term_scores"] = {l: f"{sum(1 for c in table.values() if c.get(l))}/{len(table)}"
                            for l in labels}


def step5_summary():
    hr("汇总")
    _log(f"  模型目录: {STATE.get('model_dir', MODEL_DIR)}")
    _log(f"  目录总大小: {STATE.get('dir_mb', 0):.1f} MB")
    _log(f"  本次新下载: {DL['fresh']} 文件 / {DL['bytes'] / 1e6:.1f} MB; "
         f"跳过 {DL['skipped']} 文件 / {DL['skipped_bytes'] / 1e6:.1f} MB")
    if DL["failed"]:
        _log(f"  下载失败: {DL['failed']}")
    _log(f"  目标语言前缀 token: {STATE.get('tgt_token')!r}  源语言标记: {STATE.get('src_token')!r}")
    _log(f"  实际加载: {STATE.get('load_used')}")
    _log(f"  tokenizer 路线: {STATE.get('tok_route')}")
    for n in STATE.get("tok_notes", []):
        _log(f"    （先前失败）{n}")
    _log(f"  CT2 词表与 tokenizer 语言 token id 对齐: {STATE.get('vocab_aligned')}")
    _log(f"  config.json 覆盖实验: 换成 transformers 版后 "
         f"{'能' if STATE.get('overwrite_config_loads') else '不能'}加载; "
         f"写回后 {'能' if STATE.get('restored_config_loads') else '不能'}加载")
    if STATE.get("overwrite_config_sample"):
        _log(f"    覆盖后样例输出: {STATE['overwrite_config_sample']}")
    _log(f"  tokenizer 最少文件: vocab.json + sentencepiece.bpe.model "
         f"(id 一致={STATE.get('minimal_tok_matches')})")
    _log(f"  spm.128k.model == sentencepiece.bpe.model: {STATE.get('spm_same')}")
    _log(f"  已知坑复现:")
    _log(f"    去掉 __pt__ 前缀   -> {STATE.get('no_src_token_out')}")
    _log(f"    不传 target_prefix -> {STATE.get('no_target_prefix_out')}")
    b = STATE.get("bench", {})
    _log("\n  速度（单句平均 / 6 句一批）:")
    for k, v in b.items():
        extra = f"  6句一批 {v['batch6']:.3f}s" if "batch6" in v else ""
        _log(f"    {k:22s} {v['mean']:.3f}s{extra}")
    if STATE.get("term_scores"):
        _log(f"\n  术语命中: {STATE['term_scores']}")
    try:
        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            json.dump({"DL": DL, "STATE": {k: v for k, v in STATE.items()
                                           if k not in ("tok", "translator")}},
                      f, ensure_ascii=False, indent=2, default=str)
        _log(f"\n  结构化结果: {RESULT_FILE}")
    except Exception as e:
        _log(f"  写结果文件失败: {type(e).__name__}: {e}")


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", default="1,2,3,4", help="要跑的步骤，如 1,2,3,4")
    ap.add_argument("--beam", type=int, default=2)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--no-online", action="store_true", help="跳过在线接口对比")
    args = ap.parse_args()
    steps = {s.strip() for s in args.steps.split(",") if s.strip()}

    hr(f"M2M-100 418M 探针  steps={sorted(steps)}  beam={args.beam}")
    t_start = time.perf_counter()
    try:
        if "1" in steps:
            step1()
        if "2" in steps:
            step2()
        if "3" in steps:
            step3(beam=args.beam)
        if "4" in steps:
            step4(beam=args.beam, reps=args.reps, do_online=not args.no_online)
    except Exception:
        traceback.print_exc()
    step5_summary()
    _log(f"\n总耗时 {time.perf_counter() - t_start:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
